"""
SME-AI-Kit Business DB MCP Server
SQLite 企業營運資料庫，51 個 MCP tools。
涵蓋：知識管理、任務、員工、客戶、庫存、帳務、訂單、審核、快照、設定。
"""
import sqlite3
import json
import os
from collections import OrderedDict, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# === 設定 ===

DB_PATH = os.environ.get("SME_DB_PATH", str(Path(__file__).parent.parent.parent / "data" / "business.db"))
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

# === 資料庫 ===

def get_db() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=5000")
    db.row_factory = sqlite3.Row
    return db


def init_db():
    """首次啟動時建立所有表。既有 DB 自動補新欄位。"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = get_db()
    # 既有 DB 補新欄位（必須在 schema.sql 之前，因為 schema.sql 的 CREATE INDEX 引用新欄位）
    # ALTER TABLE 失敗表示表不存在（新安裝）或欄位已存在，兩者都靜默忽略
    for stmt in [
        "ALTER TABLE customers ADD COLUMN line_user_id TEXT",
        "ALTER TABLE customers ADD COLUMN discount_rate REAL DEFAULT 0",
        "ALTER TABLE customers ADD COLUMN payment_terms TEXT DEFAULT 'net30'",
        "ALTER TABLE line_messages ADD COLUMN channel_id TEXT DEFAULT 'default'",
        "ALTER TABLE line_groups ADD COLUMN channel_id TEXT DEFAULT 'default'",
        "ALTER TABLE business_rules ADD COLUMN business_unit TEXT",
        "ALTER TABLE tasks ADD COLUMN business_unit TEXT",
        "ALTER TABLE inventory ADD COLUMN business_unit TEXT",
        "ALTER TABLE transactions ADD COLUMN business_unit TEXT",
        "ALTER TABLE orders ADD COLUMN business_unit TEXT",
        "ALTER TABLE customers ADD COLUMN pipeline_stage TEXT DEFAULT 'none'",
        "ALTER TABLE customers ADD COLUMN total_purchases REAL DEFAULT 0",
        "ALTER TABLE customers ADD COLUMN last_purchase_date TEXT",
        "ALTER TABLE inventory ADD COLUMN location TEXT",
        "ALTER TABLE inventory ADD COLUMN last_restock_date TEXT",
        "ALTER TABLE inventory ADD COLUMN notes TEXT",
        "ALTER TABLE tasks ADD COLUMN completed_at DATETIME",
        "ALTER TABLE approvals ADD COLUMN requester TEXT",
        # v2: multi-BU support for approvals, interaction_log, daily_snapshots
        "ALTER TABLE approvals ADD COLUMN business_unit TEXT",
        "ALTER TABLE interaction_log ADD COLUMN business_unit TEXT",
        "ALTER TABLE daily_snapshots ADD COLUMN business_unit TEXT DEFAULT ''",
        "ALTER TABLE employees ADD COLUMN business_units TEXT",
        # v3: orders capture payment_terms and discount at creation time
        "ALTER TABLE orders ADD COLUMN payment_terms TEXT",
        "ALTER TABLE orders ADD COLUMN discount_applied REAL DEFAULT 0",
        # v4: customer sales aggregation split (Bug #2) + cross-BU primary (Obs #6)
        "ALTER TABLE customers ADD COLUMN primary_business_unit TEXT",
        "ALTER TABLE customers ADD COLUMN total_ordered REAL DEFAULT 0",
        "ALTER TABLE customers ADD COLUMN total_fulfilled REAL DEFAULT 0",
        "ALTER TABLE customers ADD COLUMN total_paid REAL DEFAULT 0",
        "ALTER TABLE customers ADD COLUMN last_order_date TEXT",
        "ALTER TABLE customers ADD COLUMN last_fulfilled_date TEXT",
        "ALTER TABLE customers ADD COLUMN last_payment_date TEXT",
        # v4: inventory reservation (Bug #4)
        "ALTER TABLE inventory ADD COLUMN reserved INTEGER DEFAULT 0",
        # v4+: line_groups 加 purpose 欄位（群組功能描述）
        "ALTER TABLE line_groups ADD COLUMN purpose TEXT",
    ]:
        try:
            db.execute(stmt)
        except sqlite3.OperationalError:
            pass

    # 載入完整 schema（CREATE TABLE IF NOT EXISTS + CREATE INDEX IF NOT EXISTS）
    # 放在 ALTER TABLE 之後，確保舊 DB 的新欄位已補齊，CREATE INDEX 不會失敗
    if SCHEMA_PATH.exists():
        db.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

    # CHECK constraint migration：orders.status 加 'returned'
    # SQLite 不支援 ALTER CHECK，需重建表
    schema_row = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='orders'").fetchone()
    if schema_row and schema_row["sql"] and "'returned'" not in schema_row["sql"]:
        # legacy_alter_table=ON 關閉 SQLite 3.25+ 的 FK 自動改寫（避免改到其他表的 FK 後 DROP 造成 stale reference）
        db.execute("PRAGMA legacy_alter_table=ON")
        db.execute("PRAGMA foreign_keys=OFF")
        db.execute("ALTER TABLE orders RENAME TO _orders_migrate")
        db.execute("""CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER REFERENCES customers(id) ON DELETE SET NULL,
            status TEXT DEFAULT 'pending',
            total_amount REAL DEFAULT 0,
            items TEXT,
            business_unit TEXT,
            notes TEXT,
            payment_terms TEXT,
            discount_applied REAL DEFAULT 0,
            qc_status TEXT DEFAULT 'pending' CHECK (qc_status IN ('pending', 'passed', 'failed', 'partial')),
            qc_notes TEXT,
            qc_checked_by TEXT,
            qc_checked_at DATETIME,
            driver TEXT,
            estimated_delivery TEXT,
            delivered_at DATETIME,
            created_by TEXT,
            created_at DATETIME DEFAULT (datetime('now', 'localtime')),
            updated_at DATETIME DEFAULT (datetime('now', 'localtime')),
            CHECK (status IN ('pending', 'confirmed', 'shipped', 'delivered', 'paid', 'cancelled', 'returned'))
        )""")
        db.execute("""INSERT INTO orders
            (id, customer_id, status, total_amount, items, business_unit, notes,
             payment_terms, discount_applied,
             qc_status, qc_notes, qc_checked_by, qc_checked_at, driver,
             estimated_delivery, delivered_at, created_by, created_at, updated_at)
            SELECT id, customer_id, status, total_amount, items, business_unit, notes,
             payment_terms, COALESCE(discount_applied, 0),
             qc_status, qc_notes, qc_checked_by, qc_checked_at, driver,
             estimated_delivery, delivered_at, created_by, created_at, updated_at
            FROM _orders_migrate""")
        db.execute("DROP TABLE _orders_migrate")
        db.execute("CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA legacy_alter_table=OFF")

    # daily_snapshots UNIQUE constraint migration: (snapshot_date) → (snapshot_date, business_unit)
    # Detect old schema: inline UNIQUE on snapshot_date means per-BU snapshots are impossible
    snap_schema = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='daily_snapshots'").fetchone()
    needs_snap_rebuild = snap_schema and snap_schema["sql"] and "UNIQUE" in snap_schema["sql"]
    if needs_snap_rebuild:
        db.execute("PRAGMA legacy_alter_table=ON")
        db.execute("PRAGMA foreign_keys=OFF")
        db.execute("ALTER TABLE daily_snapshots RENAME TO _snapshots_migrate")
        db.execute("""CREATE TABLE daily_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date TEXT NOT NULL,
            business_unit TEXT DEFAULT '',
            pending_tasks INTEGER DEFAULT 0,
            completed_tasks_today INTEGER DEFAULT 0,
            overdue_tasks INTEGER DEFAULT 0,
            total_income REAL DEFAULT 0,
            total_expense REAL DEFAULT 0,
            pending_receivables REAL DEFAULT 0,
            low_stock_count INTEGER DEFAULT 0,
            total_customers INTEGER DEFAULT 0,
            line_messages_today INTEGER DEFAULT 0,
            active_orders INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT (datetime('now', 'localtime'))
        )""")
        # Migrate existing rows (set business_unit to '' for old global snapshots)
        db.execute("""INSERT INTO daily_snapshots
            (id, snapshot_date, business_unit, pending_tasks, completed_tasks_today, overdue_tasks,
             total_income, total_expense, pending_receivables, low_stock_count, total_customers,
             line_messages_today, active_orders, created_at)
            SELECT id, snapshot_date, '', pending_tasks, completed_tasks_today, overdue_tasks,
             total_income, total_expense, pending_receivables, low_stock_count, total_customers,
             line_messages_today, active_orders, created_at
            FROM _snapshots_migrate""")
        db.execute("DROP TABLE _snapshots_migrate")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_snapshots_date_bu ON daily_snapshots(snapshot_date, COALESCE(business_unit, ''))")
        db.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_date ON daily_snapshots(snapshot_date)")
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA legacy_alter_table=OFF")

    # Migration: line_groups UNIQUE(group_id) → UNIQUE(channel_id, group_id)
    # ⚠️ 修正：原條件左側帶空格、右側移除空格，永遠不匹配，導致 rebuild 每次 init_db 都觸發。
    # 現在兩邊都 normalize。
    lg_schema = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='line_groups'").fetchone()
    if lg_schema and lg_schema["sql"] and "UNIQUE(channel_id,group_id)" not in lg_schema["sql"].replace(" ", ""):
        db.execute("PRAGMA legacy_alter_table=ON")
        db.execute("PRAGMA foreign_keys=OFF")
        db.execute("ALTER TABLE line_groups RENAME TO _line_groups_migrate")
        db.execute("""CREATE TABLE line_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT DEFAULT 'default',
            group_id TEXT NOT NULL,
            group_name TEXT,
            group_type TEXT DEFAULT 'other',
            purpose TEXT,
            notes TEXT,
            created_at DATETIME DEFAULT (datetime('now', 'localtime')),
            updated_at DATETIME DEFAULT (datetime('now', 'localtime')),
            UNIQUE(channel_id, group_id)
        )""")
        # 動態偵測舊表有沒有 purpose 欄位（v4 之前沒有）
        old_cols = {r[1] for r in db.execute("PRAGMA table_info(_line_groups_migrate)").fetchall()}
        has_purpose = "purpose" in old_cols
        purpose_sel = "purpose" if has_purpose else "NULL"
        db.execute(f"""INSERT INTO line_groups
            (id, channel_id, group_id, group_name, group_type, purpose, notes, created_at, updated_at)
            SELECT id, COALESCE(channel_id, 'default'), group_id, group_name, group_type,
             {purpose_sel}, notes, created_at, updated_at
            FROM _line_groups_migrate""")
        db.execute("DROP TABLE _line_groups_migrate")
        db.execute("CREATE INDEX IF NOT EXISTS idx_line_groups_type ON line_groups(group_type)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_line_groups_channel ON line_groups(channel_id)")
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA legacy_alter_table=OFF")

    # Migration: inventory UNIQUE(sku) → UNIQUE(sku, COALESCE(business_unit, ''))
    inv_schema = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='inventory'").fetchone()
    if inv_schema and inv_schema["sql"] and "UNIQUE" in inv_schema["sql"]:
        db.execute("PRAGMA legacy_alter_table=ON")
        db.execute("PRAGMA foreign_keys=OFF")
        db.execute("ALTER TABLE inventory RENAME TO _inventory_migrate")
        db.execute("""CREATE TABLE inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT NOT NULL,
            name TEXT NOT NULL,
            category TEXT,
            current_stock INTEGER DEFAULT 0,
            min_stock INTEGER DEFAULT 0,
            unit TEXT DEFAULT '個',
            unit_cost REAL,
            sell_price REAL,
            business_unit TEXT,
            location TEXT,
            last_restock_date TEXT,
            notes TEXT,
            created_at DATETIME DEFAULT (datetime('now', 'localtime'))
        )""")
        db.execute("""INSERT INTO inventory
            (id, sku, name, category, current_stock, min_stock, unit, unit_cost, sell_price,
             business_unit, location, last_restock_date, notes, created_at)
            SELECT id, sku, name, category, current_stock, min_stock, unit, unit_cost, sell_price,
             business_unit, location, last_restock_date, notes, created_at
            FROM _inventory_migrate""")
        db.execute("DROP TABLE _inventory_migrate")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_inventory_sku_bu ON inventory(sku, COALESCE(business_unit, ''))")
        db.execute("CREATE INDEX IF NOT EXISTS idx_inventory_alert ON inventory(id) WHERE current_stock <= min_stock")
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA legacy_alter_table=OFF")

    # Migration: customers.type CHECK constraint
    cust_schema = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='customers'").fetchone()
    if cust_schema and cust_schema["sql"] and "CHECK" not in cust_schema["sql"]:
        db.execute("PRAGMA legacy_alter_table=ON")
        db.execute("PRAGMA foreign_keys=OFF")
        db.execute("ALTER TABLE customers RENAME TO _customers_migrate")
        db.execute("""CREATE TABLE customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT DEFAULT 'customer',
            phone TEXT,
            email TEXT,
            line_user_id TEXT,
            tags TEXT,
            notes TEXT,
            pipeline_stage TEXT DEFAULT 'none',
            total_purchases REAL DEFAULT 0,
            last_purchase_date TEXT,
            discount_rate REAL DEFAULT 0,
            payment_terms TEXT DEFAULT 'net30',
            created_at DATETIME DEFAULT (datetime('now', 'localtime')),
            CHECK (type IN ('customer', 'supplier', 'distributor'))
        )""")
        db.execute("""INSERT INTO customers
            (id, name, type, phone, email, line_user_id, tags, notes,
             pipeline_stage, total_purchases, last_purchase_date, discount_rate, payment_terms, created_at)
            SELECT id, name, CASE WHEN type IN ('customer','supplier','distributor') THEN type ELSE 'customer' END,
             phone, email, line_user_id, tags, notes,
             pipeline_stage, total_purchases, last_purchase_date, discount_rate, payment_terms, created_at
            FROM _customers_migrate""")
        db.execute("DROP TABLE _customers_migrate")
        db.execute("CREATE INDEX IF NOT EXISTS idx_customers_type ON customers(type)")
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA legacy_alter_table=OFF")

    # Ensure all indexes exist (idempotent, covers both new installs and migrations)
    for idx_stmt in [
        "CREATE INDEX IF NOT EXISTS idx_rules_bu ON business_rules(business_unit) WHERE business_unit IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_tasks_bu ON tasks(business_unit) WHERE business_unit IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_inventory_bu ON inventory(business_unit) WHERE business_unit IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_transactions_bu ON transactions(business_unit) WHERE business_unit IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_orders_bu ON orders(business_unit) WHERE business_unit IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_approvals_bu ON approvals(business_unit) WHERE business_unit IS NOT NULL",
        # Identity lookup indexes
        "CREATE INDEX IF NOT EXISTS idx_customers_line ON customers(line_user_id) WHERE line_user_id IS NOT NULL",
        # FK indexes for join performance
        "CREATE INDEX IF NOT EXISTS idx_transactions_customer ON transactions(related_customer_id) WHERE related_customer_id IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_transactions_order ON transactions(related_order_id) WHERE related_order_id IS NOT NULL",
        # Composite indexes for common queries
        "CREATE INDEX IF NOT EXISTS idx_transactions_customer_status ON transactions(related_customer_id, payment_status) WHERE related_customer_id IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_tasks_assignee_status ON tasks(assignee, status) WHERE assignee IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_orders_status_bu ON orders(status, business_unit)",
        # v4: new indexes for Bug #4 (reserved) + Obs #6 (primary_business_unit)
        "CREATE INDEX IF NOT EXISTS idx_customers_primary_bu ON customers(primary_business_unit) WHERE primary_business_unit IS NOT NULL",
    ]:
        try:
            db.execute(idx_stmt)
        except sqlite3.OperationalError:
            pass

    # === One-shot: legacy business_entities.approval_threshold = -1 → NULL
    # (Bug #8：-1 本意是 sentinel「繼承公司預設」，但舊資料可能寫入實際 -1，
    #  早期版本的 _get_approval_threshold 沒處理負值 fallback) ===
    db.execute("UPDATE business_entities SET approval_threshold = NULL WHERE approval_threshold < 0")

    # === One-shot repair: existing DBs may have orders/transactions/customer_entity_terms
    # with FK pointing to _customers_migrate / _orders_migrate (dropped tables) due to
    # SQLite 3.25+ auto-rewriting FK on ALTER TABLE RENAME. See Bug #1 in plan. ===
    for _tbl in ("orders", "transactions", "customer_entity_terms"):
        _row = db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (_tbl,)
        ).fetchone()
        if _row and _row["sql"] and ("_customers_migrate" in _row["sql"] or "_orders_migrate" in _row["sql"]):
            _repair_stale_fk_table(db, _tbl)

    # === Backfill inventory.reserved from open orders (first-run only) ===
    # 若 reserved 全 0，掃 pending/confirmed 訂單回補預留數
    _reserved_max = db.execute(
        "SELECT COALESCE(MAX(reserved), 0) FROM inventory"
    ).fetchone()[0]
    if _reserved_max == 0:
        _pending = db.execute(
            "SELECT items, business_unit FROM orders WHERE status IN ('pending', 'confirmed')"
        ).fetchall()
        for _ord in _pending:
            for _item in _parse_items_json(_ord["items"] or "[]"):
                _sku = (_item.get("sku") or "").strip()
                _qty = int(_item.get("qty") or 0)
                if not _sku or _qty <= 0:
                    continue
                _inv = _find_inventory(db, _sku, _ord["business_unit"] or "")
                if _inv:
                    db.execute(
                        "UPDATE inventory SET reserved = COALESCE(reserved, 0) + ? WHERE id = ?",
                        (_qty, _inv["id"]),
                    )

    db.commit()
    db.close()


def _repair_stale_fk_table(db, tbl: str):
    """Rebuild a table whose FK references stale _customers_migrate / _orders_migrate.

    One-shot fix for DBs migrated under SQLite 3.25+ where ALTER TABLE RENAME
    auto-rewrote FK references that later became orphaned when the migrate tables
    were dropped.
    """
    # Preserve data
    cols_info = db.execute(f"PRAGMA table_info({tbl})").fetchall()
    cols = [c["name"] for c in cols_info]
    rows = db.execute(f"SELECT * FROM {tbl}").fetchall()

    # Disable FK enforcement + disable SQLite 3.25+ FK auto-rewrite
    db.execute("PRAGMA legacy_alter_table=ON")
    db.execute("PRAGMA foreign_keys=OFF")
    try:
        db.execute(f"DROP TABLE {tbl}")
        # Re-run schema.sql to recreate with correct FK (CREATE TABLE IF NOT EXISTS)
        if SCHEMA_PATH.exists():
            db.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        # schema.sql re-enables FK; we need it OFF to do bulk INSERT without validation
        db.execute("PRAGMA foreign_keys=OFF")
        # Restore data using original columns (handles schemas with fewer cols than current)
        if rows:
            col_list = ",".join(f'"{c}"' for c in cols)
            placeholders = ",".join("?" for _ in cols)
            db.executemany(
                f'INSERT INTO {tbl} ({col_list}) VALUES ({placeholders})',
                [tuple(r[c] for c in cols) for r in rows],
            )
    finally:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA legacy_alter_table=OFF")


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _rows_to_str(rows: list[sqlite3.Row], max_rows: int = 50) -> str:
    if not rows:
        return "（無資料）"
    results = []
    for r in rows[:max_rows]:
        results.append(" | ".join(f"{k}={r[k]}" for k in r.keys() if r[k] is not None))
    if len(rows) > max_rows:
        results.append(f"... 還有 {len(rows) - max_rows} 筆")
    return "\n".join(results)


def _like_param(query: str) -> str:
    """將使用者輸入轉為 LIKE 查詢參數。SME 資料量小，LIKE 比 FTS5 更適合 CJK。"""
    cleaned = query.strip().replace("%", "").replace("_", "")
    return f"%{cleaned}%"


def _get_customer_terms(db, customer_id: int, business_unit: str = "") -> dict:
    """取得客戶的折扣率和付款條件。先查 customer_entity_terms（事業體專屬），fallback 到 customers 預設值。"""
    customer = db.execute("SELECT discount_rate, payment_terms FROM customers WHERE id = ?", (customer_id,)).fetchone()
    if not customer:
        return {"discount_rate": 0, "payment_terms": "net30"}
    defaults = {"discount_rate": customer["discount_rate"] or 0, "payment_terms": customer["payment_terms"] or "net30"}
    if not business_unit:
        return defaults
    entity_terms = db.execute(
        "SELECT discount_rate, payment_terms FROM customer_entity_terms WHERE customer_id = ? AND business_unit = ?",
        (customer_id, business_unit),
    ).fetchone()
    if entity_terms:
        return {"discount_rate": entity_terms["discount_rate"] or 0, "payment_terms": entity_terms["payment_terms"] or "net30"}
    return defaults


def _validate_business_unit(db, business_unit: str) -> str:
    """驗證 business_unit 是否存在於 business_entities 表。
    Returns: 空字串=OK，非空=警告訊息（不阻擋操作）。"""
    if not business_unit:
        return ""
    entity = db.execute("SELECT id FROM business_entities WHERE id = ?", (business_unit,)).fetchone()
    if not entity:
        return f"\n⚠️ 事業體 '{business_unit}' 未登錄（register_business_entity），資料已存入但無法按事業體篩選彙總。"
    return ""


def _get_approval_threshold(db, business_unit: str = "") -> float:
    """取得審核門檻。先查事業體設定（必須 >= 0 才有效），否則 fallback 到公司預設。
    注意：事業體的 approval_threshold 若為負值（常見 -1 sentinel）視為未設定，需 fallback。"""
    if business_unit:
        entity = db.execute("SELECT approval_threshold FROM business_entities WHERE id = ?", (business_unit,)).fetchone()
        if entity and entity["approval_threshold"] is not None and entity["approval_threshold"] >= 0:
            return entity["approval_threshold"]
    company = db.execute("SELECT approval_threshold FROM company WHERE id = 1").fetchone()
    return company["approval_threshold"] if company else 5000


def _build_guidance(
    auto_done: list[str] | None = None,
    next_steps: list[str] | None = None,
    warnings: list[str] | None = None,
) -> str:
    """Build structured guidance block for tool returns."""
    parts: list[str] = []
    if auto_done:
        parts.append("\n📋 已自動完成：\n" + "\n".join(f"- {s}" for s in auto_done))
    if next_steps:
        parts.append("\n👉 下一步：\n" + "\n".join(f"{i+1}. {s}" for i, s in enumerate(next_steps)))
    if warnings:
        parts.append("\n⚠️ 注意：\n" + "\n".join(f"- {s}" for s in warnings))
    return "\n".join(parts) if parts else ""


def _safe_update(db, table: str, allowed_columns: set[str], updates: list[str], params: list, where: str, where_params: list) -> int:
    """Execute UPDATE with column-name whitelist validation.
    updates: list of 'column = ?' or 'column = expr' strings. Each column name (before '=') is validated against allowed_columns.
    Returns rowcount."""
    for u in updates:
        col = u.split("=")[0].strip()
        if col not in allowed_columns:
            raise ValueError(f"Column '{col}' not in allowed set for {table}")
    sql = f"UPDATE {table} SET {', '.join(updates)} WHERE {where}"
    result = db.execute(sql, params + where_params)
    return result.rowcount


def _parse_items_json(raw) -> list:
    """Safely parse order items JSON. Returns [] on None, empty string, or invalid JSON."""
    if not raw:
        return []
    try:
        result = json.loads(raw) if isinstance(raw, str) else raw
        return result if isinstance(result, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


_PERM_LEVEL = {"basic": 0, "manager": 1, "admin": 2}

# 訂單狀態轉換表（update_order 專用，cancel/fulfill 有各自的工具）
_ORDER_TRANSITIONS = {
    "pending": {"confirmed"},
    "confirmed": set(),       # → shipped 只能透過 fulfill_order
    "shipped": {"delivered"},
    "delivered": {"paid"},
}


def _find_inventory(db, sku: str, business_unit: str):
    """查找庫存紀錄。先精確匹配 SKU+BU，再 fallback 到無歸屬（共用）庫存，絕不跨 BU。"""
    if business_unit:
        inv = db.execute(
            "SELECT * FROM inventory WHERE sku = ? AND business_unit = ?",
            (sku, business_unit),
        ).fetchone()
        if inv:
            return inv
    # Fallback：只查無歸屬（共用）庫存，避免跨 BU 誤扣
    return db.execute(
        "SELECT * FROM inventory WHERE sku = ? AND (business_unit IS NULL OR business_unit = '')",
        (sku,),
    ).fetchone()


def _check_permission(db, actor_user_id: str, required: str, business_unit: str = "") -> str:
    """Check actor permission. Returns empty string if OK, error message (starting with 'ERROR:') if denied.
    actor_user_id='' means system/Cowork call → always allowed.
    business_unit: if provided, logs warning when employee is not assigned to that BU (does not block)."""
    if not actor_user_id:
        return ""
    emp = db.execute(
        "SELECT name, permissions, business_units FROM employees WHERE line_user_id = ? AND active = 1",
        (actor_user_id,),
    ).fetchone()
    if not emp:
        return "ERROR: 找不到該使用者的員工記錄，無法驗證權限"
    if _PERM_LEVEL.get(emp["permissions"], 0) < _PERM_LEVEL.get(required, 0):
        return f"ERROR: 權限不足 — {emp['name']}（{emp['permissions']}）需要 {required} 以上權限"
    # BU 驗證（soft warning — 不阻擋，記錄到 interaction_log 供追蹤）
    if business_unit and emp["business_units"]:
        allowed = [u.strip() for u in emp["business_units"].split(",")]
        if business_unit not in allowed:
            db.execute(
                "INSERT INTO interaction_log (actor, action, target_type, target_id, detail, business_unit) VALUES (?,?,?,?,?,?)",
                (emp["name"], "cross_bu_access", "employee", 0,
                 f"{emp['name']} 操作 {business_unit} 事業體（指派：{emp['business_units']}）", business_unit),
            )
    return ""


# === MCP Server ===

init_db()
mcp = FastMCP("business-db")


# ============================================================
# 知識管理（9 核心工具）
# ============================================================

@mcp.tool()
def store_fact(
    category: str,
    title: str,
    content: str,
    source_type: str = "explicit",
    source_quote: str = "",
    set_by: str = "",
    business_unit: str = "",
) -> str:
    """儲存企業規則或知識。反捏造機制：source_type='explicit' 時必須附上 source_quote（老闆原話）。

    Args:
        category: 規則類別（如 return_policy, pricing, hr, supplier, sop）
        title: 規則標題
        content: 規則內容詳述
        source_type: 來源類型 — explicit（老闆明確指示）| observed（觀察到的慣例）| inferred（AI推斷）
        source_quote: 老闆原話引用（source_type=explicit 時必填）
        set_by: 誰設定的（如老闆姓名）
        business_unit: 所屬事業體（如 brand_c, brand_d），留空=全域規則
    """
    if source_type not in ("explicit", "observed", "inferred"):
        return "ERROR: source_type 必須是 explicit, observed, 或 inferred"
    if source_type == "explicit" and not source_quote.strip():
        return "ERROR: explicit 規則必須附上 source_quote（老闆的原話），不可省略"

    db = get_db()
    try:
        # 矛盾檢查：在同一 category（和 business_unit）中搜尋相似的現有規則
        like = _like_param(title)
        if business_unit:
            conflicts = db.execute(
                """SELECT id, title, content FROM business_rules
                   WHERE category = ? AND superseded_by IS NULL AND (business_unit = ? OR business_unit IS NULL)
                   AND (title LIKE ? OR content LIKE ?)""",
                (category, business_unit, like, like),
            ).fetchall()
        else:
            conflicts = db.execute(
                """SELECT id, title, content FROM business_rules
                   WHERE category = ? AND superseded_by IS NULL
                   AND (title LIKE ? OR content LIKE ?)""",
                (category, like, like),
            ).fetchall()

        warning = ""
        if conflicts:
            conflict_list = "\n".join(
                f"  - [#{r['id']}] {r['title']}: {r['content'][:80]}" for r in conflicts[:5]
            )
            warning = f"\n⚠️ 發現 {len(conflicts)} 條可能衝突的規則：\n{conflict_list}\n如需取代舊規則，請用 update_rule 工具。"

        cursor = db.execute(
            "INSERT INTO business_rules (category, title, content, source_type, source_quote, set_by, business_unit) VALUES (?,?,?,?,?,?,?)",
            (category, title, content, source_type, source_quote.strip() or None, set_by.strip() or None, business_unit or None),
        )
        rule_id = cursor.lastrowid

        db.execute(
            "INSERT INTO interaction_log (actor, action, target_type, target_id, detail, business_unit) VALUES (?,?,?,?,?,?)",
            (set_by or "system", "rule_created", "rule", rule_id, f"[{category}] {title}", business_unit or None),
        )

        # 自動建立交叉引用（利用已有的 conflicts 結果）
        if conflicts:
            for cr in conflicts[:5]:
                a, b = min(rule_id, cr["id"]), max(rule_id, cr["id"])
                try:
                    db.execute(
                        "INSERT INTO rule_relations (rule_id_a, rule_id_b, relation_type, created_by) VALUES (?,?,?,?)",
                        (a, b, "related", "auto"),
                    )
                except sqlite3.IntegrityError:
                    pass

        db.commit()
        bu_warn = _validate_business_unit(db, business_unit)
        return f"✅ 已儲存規則 #{rule_id} [{category}] {title}" + warning + bu_warn
    finally:
        db.close()


@mcp.tool()
def query_knowledge(question: str, category: str = "", business_unit: str = "") -> str:
    """搜尋企業知識庫（規則、任務、客戶、庫存）。使用 LIKE 模糊比對（CJK 友好）。

    Args:
        question: 搜尋關鍵字或問題
        category: 可選，限定搜尋特定的規則類別
        business_unit: 可選，限定搜尋特定事業體的規則（同時包含全域規則）
    """
    like = _like_param(question)
    db = get_db()
    try:
        results = []

        # 搜尋規則（含事業體篩選：查事業體專屬 + 全域規則）
        bu_filter = ""
        params = []
        if category and business_unit:
            bu_filter = "WHERE category = ? AND superseded_by IS NULL AND (business_unit = ? OR business_unit IS NULL) AND (title LIKE ? OR content LIKE ?)"
            params = [category, business_unit, like, like]
        elif category:
            bu_filter = "WHERE category = ? AND superseded_by IS NULL AND (title LIKE ? OR content LIKE ?)"
            params = [category, like, like]
        elif business_unit:
            bu_filter = "WHERE superseded_by IS NULL AND (business_unit = ? OR business_unit IS NULL) AND (title LIKE ? OR content LIKE ?)"
            params = [business_unit, like, like]
        else:
            bu_filter = "WHERE superseded_by IS NULL AND (title LIKE ? OR content LIKE ?)"
            params = [like, like]

        rules = db.execute(
            f"""SELECT id, category, title, content, source_type, set_by, business_unit, created_at
                FROM business_rules {bu_filter} LIMIT 10""",
            params,
        ).fetchall()

        if rules:
            results.append("## 📋 企業規則")
            for r in rules:
                src = {"explicit": "老闆指示", "observed": "觀察慣例", "inferred": "AI推斷"}.get(r["source_type"], r["source_type"])
                bu_label = f" [{r['business_unit']}]" if r["business_unit"] else " [全域]"
                results.append(f"- **[#{r['id']}] {r['title']}** [{r['category']}]{bu_label} ({src})")
                results.append(f"  {r['content'][:200]}")

            # 交叉引用
            rule_ids = [r["id"] for r in rules]
            placeholders = ",".join("?" * len(rule_ids))
            relations = db.execute(
                f"""SELECT rr.relation_type,
                           ba.id as id_a, ba.title as title_a,
                           bb.id as id_b, bb.title as title_b
                    FROM rule_relations rr
                    JOIN business_rules ba ON rr.rule_id_a = ba.id
                    JOIN business_rules bb ON rr.rule_id_b = bb.id
                    WHERE (rr.rule_id_a IN ({placeholders}) OR rr.rule_id_b IN ({placeholders}))
                    AND ba.superseded_by IS NULL AND bb.superseded_by IS NULL
                    LIMIT 10""",
                rule_ids + rule_ids,
            ).fetchall()
            if relations:
                type_labels = {"related": "相關", "depends_on": "依賴", "conflicts_with": "⚠️衝突"}
                results.append("\n## 🔗 相關規則（交叉引用）")
                for rel in relations:
                    label = type_labels.get(rel["relation_type"], rel["relation_type"])
                    results.append(f"- [{label}] [#{rel['id_a']}] {rel['title_a']} ↔ [#{rel['id_b']}] {rel['title_b']}")

        # 搜尋任務
        tasks = db.execute(
            """SELECT id, title, description, assignee, status, due_date
               FROM tasks
               WHERE title LIKE ? OR description LIKE ?
               LIMIT 5""",
            (like, like),
        ).fetchall()

        if tasks:
            results.append("\n## 📝 相關任務")
            for t in tasks:
                status_icon = {"pending": "⏳", "in_progress": "🔄", "done": "✅", "cancelled": "❌"}.get(t["status"], "")
                results.append(f"- {status_icon} [#{t['id']}] {t['title']} → {t['assignee'] or '未指派'}")

        # 搜尋客戶
        customers = db.execute(
            """SELECT id, name, phone, tags, notes
               FROM customers
               WHERE name LIKE ? OR notes LIKE ? OR tags LIKE ?
               LIMIT 5""",
            (like, like, like),
        ).fetchall()

        if customers:
            results.append("\n## 👤 相關客戶")
            for c in customers:
                results.append(f"- **{c['name']}** {c['phone'] or ''} {c['tags'] or ''}")

        # 搜尋庫存
        inventory = db.execute(
            """SELECT id, sku, name, current_stock, min_stock, unit
               FROM inventory
               WHERE name LIKE ? OR sku LIKE ? OR category LIKE ?
               LIMIT 5""",
            (like, like, like),
        ).fetchall()

        if inventory:
            results.append("\n## 📦 相關庫存")
            for i in inventory:
                alert = " ⚠️ 低於安全庫存" if i["current_stock"] <= i["min_stock"] else ""
                results.append(f"- [{i['sku']}] {i['name']}: {i['current_stock']}{i['unit']}{alert}")

        if not results:
            return f"找不到與「{question}」相關的資料。"
        return "\n".join(results)
    finally:
        db.close()


@mcp.tool()
def update_rule(rule_id: int, new_content: str, reason: str, actor_user_id: str = "") -> str:
    """更新企業規則。舊規則標記為已取代，建立新規則。

    Args:
        rule_id: 要更新的規則 ID
        new_content: 新的規則內容
        reason: 更新原因
        actor_user_id: 操作者 LINE user_id（用於權限驗證，留空=系統呼叫，不驗證）
    """
    db = get_db()
    try:
        perm_err = _check_permission(db, actor_user_id, "admin")
        if perm_err:
            return perm_err
        old = db.execute("SELECT * FROM business_rules WHERE id = ? AND superseded_by IS NULL", (rule_id,)).fetchone()
        if not old:
            return f"ERROR: 找不到有效規則 #{rule_id}（可能已被取代或不存在）"

        # Transactional flip：避免 idx_rules_unique_active（partial unique on superseded_by IS NULL）衝突
        # 1) INSERT 新規則，暫時 superseded_by=rule_id（非 NULL → 退出 partial index）
        # 2) UPDATE 舊規則 superseded_by=new_id（退出 partial index）
        # 3) UPDATE 新規則 superseded_by=NULL（進入 partial index；此時舊規則已退出，無衝突）
        cursor = db.execute(
            "INSERT INTO business_rules "
            "(category, title, content, source_type, source_quote, set_by, business_unit, superseded_by) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (old["category"], old["title"], new_content, old["source_type"], old["source_quote"],
             old["set_by"], old["business_unit"], rule_id),
        )
        new_id = cursor.lastrowid
        db.execute("UPDATE business_rules SET superseded_by = ? WHERE id = ?", (new_id, rule_id))
        db.execute("UPDATE business_rules SET superseded_by = NULL WHERE id = ?", (new_id,))

        db.execute(
            "INSERT INTO interaction_log (actor, action, target_type, target_id, detail, business_unit) VALUES (?,?,?,?,?,?)",
            ("system", "rule_updated", "rule", new_id, f"取代 #{rule_id}，原因：{reason}", old["business_unit"]),
        )

        # 遷移交叉引用：舊 rule_id → 新 new_id（重新正規化 a < b，避免 UNIQUE 衝突）
        old_rels = db.execute(
            "SELECT id, rule_id_a, rule_id_b, relation_type, created_by FROM rule_relations WHERE rule_id_a = ? OR rule_id_b = ?",
            (rule_id, rule_id),
        ).fetchall()
        for rel in old_rels:
            other = rel["rule_id_b"] if rel["rule_id_a"] == rule_id else rel["rule_id_a"]
            db.execute("DELETE FROM rule_relations WHERE id = ?", (rel["id"],))
            # 正規化：symmetric 類型保持 a < b
            if rel["relation_type"] in ("related", "conflicts_with"):
                ra, rb = min(new_id, other), max(new_id, other)
            elif rel["rule_id_a"] == rule_id:
                ra, rb = new_id, other  # depends_on 是方向性的
            else:
                ra, rb = other, new_id
            try:
                db.execute(
                    "INSERT INTO rule_relations (rule_id_a, rule_id_b, relation_type, created_by) VALUES (?,?,?,?)",
                    (ra, rb, rel["relation_type"], rel["created_by"]),
                )
            except sqlite3.IntegrityError:
                pass  # 已存在相同關聯

        # 查關聯規則，提醒可能需要連動
        relations = db.execute(
            """SELECT rr.relation_type,
                      CASE WHEN rr.rule_id_a = ? THEN rr.rule_id_b ELSE rr.rule_id_a END as related_id,
                      br.title, br.category
               FROM rule_relations rr
               JOIN business_rules br ON br.id = CASE WHEN rr.rule_id_a = ? THEN rr.rule_id_b ELSE rr.rule_id_a END
               WHERE (rr.rule_id_a = ? OR rr.rule_id_b = ?) AND br.superseded_by IS NULL""",
            (new_id, new_id, new_id, new_id),
        ).fetchall()

        related_warning = ""
        if relations:
            type_labels = {"related": "相關", "depends_on": "依賴", "conflicts_with": "⚠️衝突"}
            rel_list = "\n".join(
                f"  - [#{r['related_id']}] {r['title']} [{r['category']}]（{type_labels.get(r['relation_type'], r['relation_type'])}）"
                for r in relations[:5]
            )
            related_warning = f"\n\n🔗 以下 {len(relations)} 條關聯規則可能也需要檢查：\n{rel_list}"

        db.commit()
        return f"✅ 規則已更新：#{rule_id} → #{new_id}\n原因：{reason}" + related_warning
    finally:
        db.close()


@mcp.tool()
def knowledge_changelog(days: int = 7) -> str:
    """知識變更日誌：顯示指定天數內的規則新增、更新記錄。

    Args:
        days: 回溯天數（預設 7 天）
    """
    db = get_db()
    try:
        rows = db.execute(
            """SELECT il.action, il.detail, il.created_at, il.target_id,
                      br.category, br.title
               FROM interaction_log il
               LEFT JOIN business_rules br ON il.target_id = br.id AND il.target_type = 'rule'
               WHERE il.action IN ('rule_created', 'rule_updated')
               AND il.created_at >= datetime('now', 'localtime', '-' || ? || ' days')
               ORDER BY il.created_at DESC""",
            (str(days),),
        ).fetchall()

        if not rows:
            return f"最近 {days} 天沒有知識變更記錄。"

        # 按日期分組
        by_date: dict[str, list] = OrderedDict()
        total_created = total_updated = 0
        for r in rows:
            date_key = r["created_at"][:10]
            by_date.setdefault(date_key, []).append(r)
            if r["action"] == "rule_created":
                total_created += 1
            else:
                total_updated += 1

        lines = [f"## 知識變更日誌（最近 {days} 天）\n"]
        today = _now()[:10]
        for date_key, entries in by_date.items():
            label = "（今天）" if date_key == today else ""
            lines.append(f"### {date_key}{label}")
            created = [e for e in entries if e["action"] == "rule_created"]
            updated = [e for e in entries if e["action"] == "rule_updated"]
            if created:
                lines.append(f"📝 新增 {len(created)} 條：")
                for e in created:
                    cat = f"[{e['category']}] " if e["category"] else ""
                    title = e["title"] or e["detail"] or ""
                    lines.append(f"- [#{e['target_id']}] {cat}{title}")
            if updated:
                lines.append(f"🔄 更新 {len(updated)} 條：")
                for e in updated:
                    cat = f"[{e['category']}] " if e["category"] else ""
                    title = e["title"] or ""
                    detail = e["detail"] or ""
                    lines.append(f"- [#{e['target_id']}] {cat}{title} — {detail}")
            lines.append("")

        lines.append(f"---\n共計：新增 {total_created} 條 | 更新 {total_updated} 條")
        return "\n".join(lines)
    finally:
        db.close()


_KNOWN_CATEGORIES = [
    "hr", "pricing", "return_policy", "supplier", "customer_service",
    "inventory", "finance", "sop", "brand", "general",
]


@mcp.tool()
def lint_knowledge(checks: str = "all") -> str:
    """知識庫健檢：偵測矛盾、過期、覆蓋缺口、孤立鏈。

    Args:
        checks: 要執行的檢查，逗號分隔。可選值：contradictions, stale, coverage, orphaned, all（預設）
    """
    requested = {c.strip() for c in checks.split(",")}
    run_all = "all" in requested

    db = get_db()
    try:
        sections = []
        suggestions = []

        # --- 1. 矛盾檢查 ---
        if run_all or "contradictions" in requested:
            rules = db.execute(
                "SELECT id, category, title, content FROM business_rules WHERE superseded_by IS NULL ORDER BY category",
            ).fetchall()
            # 按 category 分組
            by_cat: dict[str, list] = defaultdict(list)
            for r in rules:
                by_cat[r["category"]].append(r)

            pairs = []
            for cat, cat_rules in by_cat.items():
                for i, a in enumerate(cat_rules):
                    a_key = a["title"].strip()
                    for b in cat_rules[i + 1:]:
                        b_key = b["title"].strip()
                        # 短 title（< 4 字）用完全匹配避免假陽性；長 title 用子字串匹配
                        if len(a_key) < 4 and len(b_key) < 4:
                            hit = a_key == b_key
                        elif len(a_key) < 4:
                            hit = a_key in b["title"]
                        elif len(b_key) < 4:
                            hit = b_key in a["title"]
                        else:
                            a_in_b = a_key in (b["title"] + " " + b["content"])
                            b_in_a = b_key in (a["title"] + " " + a["content"])
                            hit = a_in_b or b_in_a
                        if hit:
                            pairs.append((a, b))

            if pairs:
                sections.append(f"### 🔍 潛在矛盾（{len(pairs)} 組）")
                for a, b in pairs[:10]:
                    sections.append(f"- [#{a['id']}] {a['title']} ↔ [#{b['id']}] {b['title']} [{a['category']}]")
                    sections.append(f"  #{a['id']}: {a['content'][:80]}")
                    sections.append(f"  #{b['id']}: {b['content'][:80]}")
                suggestions.append(f"檢討 {len(pairs)} 組可能矛盾的規則")
            else:
                sections.append("### 🔍 潛在矛盾\n✅ 未發現矛盾")

        # --- 2. 過期檢查 ---
        if run_all or "stale" in requested:
            stale = db.execute(
                """SELECT id, category, title, created_at FROM business_rules
                   WHERE superseded_by IS NULL
                   AND created_at < datetime('now', 'localtime', '-6 months')
                   ORDER BY created_at""",
            ).fetchall()

            if stale:
                sections.append(f"\n### ⏰ 可能過期（{len(stale)} 條，超過 6 個月未更新）")
                for r in stale[:15]:
                    sections.append(f"- [#{r['id']}] {r['title']} [{r['category']}] — 建立於 {r['created_at'][:10]}")
                suggestions.append(f"檢討 {len(stale)} 條可能過期的規則")
            else:
                sections.append("\n### ⏰ 過期檢查\n✅ 所有規則都在 6 個月內")

        # --- 3. 覆蓋分析 ---
        if run_all or "coverage" in requested:
            counts = db.execute(
                """SELECT category, COUNT(*) as cnt FROM business_rules
                   WHERE superseded_by IS NULL GROUP BY category""",
            ).fetchall()
            count_map = {r["category"]: r["cnt"] for r in counts}

            sections.append("\n### 📊 覆蓋分析")
            empty_cats = []
            low_cats = []
            for cat in _KNOWN_CATEGORIES:
                cnt = count_map.get(cat, 0)
                if cnt == 0:
                    sections.append(f"- ❌ {cat}: 0 條（空白）")
                    empty_cats.append(cat)
                elif cnt <= 2:
                    sections.append(f"- ⚠️ {cat}: {cnt} 條（偏少）")
                    low_cats.append(cat)
                else:
                    sections.append(f"- ✅ {cat}: {cnt} 條")
            # 顯示不在已知類別的自訂類別
            for cat, cnt in count_map.items():
                if cat not in _KNOWN_CATEGORIES:
                    sections.append(f"- 📁 {cat}: {cnt} 條（自訂類別）")

            if empty_cats:
                suggestions.append(f"補充 {', '.join(empty_cats)} 類別的規則")
            if low_cats:
                suggestions.append(f"充實 {', '.join(low_cats)} 類別（目前偏少）")

        # --- 4. 孤立鏈檢查 ---
        if run_all or "orphaned" in requested:
            orphaned = db.execute(
                """SELECT id, title, superseded_by FROM business_rules
                   WHERE superseded_by IS NOT NULL
                   AND superseded_by NOT IN (SELECT id FROM business_rules)""",
            ).fetchall()

            if orphaned:
                sections.append(f"\n### 🔗 孤立鏈（{len(orphaned)} 條）")
                for r in orphaned[:10]:
                    sections.append(f"- [#{r['id']}] {r['title']} → superseded_by #{r['superseded_by']}（不存在）")
                suggestions.append(f"修復 {len(orphaned)} 條孤立引用")
            else:
                sections.append("\n### 🔗 孤立鏈檢查\n✅ 資料完整性正常")

        # --- 建議 ---
        if suggestions:
            sections.append("\n### 📋 建議")
            for s in suggestions:
                sections.append(f"- {s}")

        return "## 知識庫健檢報告\n\n" + "\n".join(sections)
    finally:
        db.close()


@mcp.tool()
def link_rules(rule_id_a: int, rule_id_b: int, relation_type: str = "related") -> str:
    """建立規則之間的關聯（交叉引用）。

    Args:
        rule_id_a: 第一條規則 ID
        rule_id_b: 第二條規則 ID
        relation_type: 關聯類型 — related（相關）| depends_on（A 依賴 B）| conflicts_with（潛在衝突）
    """
    if relation_type not in ("related", "depends_on", "conflicts_with"):
        return "ERROR: relation_type 必須是 related, depends_on, 或 conflicts_with"
    if rule_id_a == rule_id_b:
        return "ERROR: 不能將規則與自身建立關聯"

    db = get_db()
    try:
        # 驗證兩條規則都存在且 active
        a = db.execute("SELECT id, title, business_unit FROM business_rules WHERE id = ? AND superseded_by IS NULL", (rule_id_a,)).fetchone()
        b = db.execute("SELECT id, title, business_unit FROM business_rules WHERE id = ? AND superseded_by IS NULL", (rule_id_b,)).fetchone()
        if not a:
            return f"ERROR: 找不到有效規則 #{rule_id_a}"
        if not b:
            return f"ERROR: 找不到有效規則 #{rule_id_b}"

        # symmetric 類型正規化為 a < b
        ra, rb = rule_id_a, rule_id_b
        if relation_type in ("related", "conflicts_with") and ra > rb:
            ra, rb = rb, ra

        try:
            db.execute(
                "INSERT INTO rule_relations (rule_id_a, rule_id_b, relation_type, created_by) VALUES (?,?,?,?)",
                (ra, rb, relation_type, "manual"),
            )
            db.execute(
                "INSERT INTO interaction_log (actor, action, target_type, target_id, detail, business_unit) VALUES (?,?,?,?,?,?)",
                ("system", "rule_linked", "rule", ra, f"#{ra} ↔ #{rb} ({relation_type})", a["business_unit"]),
            )
            db.commit()
        except sqlite3.IntegrityError:
            return f"ℹ️ 關聯已存在：#{ra} ↔ #{rb} ({relation_type})"

        type_label = {"related": "相關", "depends_on": "依賴", "conflicts_with": "衝突"}.get(relation_type, relation_type)
        return f"✅ 已建立關聯：[#{ra}] {a['title']} ↔ [#{rb}] {b['title']} （{type_label}）"
    finally:
        db.close()


@mcp.tool()
def get_rule_relations(rule_id: int) -> str:
    """查詢規則的所有關聯（交叉引用）。

    Args:
        rule_id: 規則 ID
    """
    db = get_db()
    try:
        rule = db.execute("SELECT id, title, category FROM business_rules WHERE id = ?", (rule_id,)).fetchone()
        if not rule:
            return f"ERROR: 找不到規則 #{rule_id}"

        relations = db.execute(
            """SELECT rr.relation_type,
                      ba.id as id_a, ba.title as title_a, ba.category as cat_a,
                      bb.id as id_b, bb.title as title_b, bb.category as cat_b
               FROM rule_relations rr
               JOIN business_rules ba ON rr.rule_id_a = ba.id
               JOIN business_rules bb ON rr.rule_id_b = bb.id
               WHERE (rr.rule_id_a = ? OR rr.rule_id_b = ?)
               AND ba.superseded_by IS NULL AND bb.superseded_by IS NULL""",
            (rule_id, rule_id),
        ).fetchall()

        if not relations:
            return f"規則 [#{rule_id}] {rule['title']} 沒有任何關聯。"

        type_labels = {"related": "相關", "depends_on": "依賴", "conflicts_with": "⚠️衝突"}
        lines = [f"## 規則 [#{rule_id}] {rule['title']} 的關聯\n"]
        for rel in relations:
            label = type_labels.get(rel["relation_type"], rel["relation_type"])
            # 顯示「另一條」規則
            if rel["id_a"] == rule_id:
                other_id, other_title, other_cat = rel["id_b"], rel["title_b"], rel["cat_b"]
            else:
                other_id, other_title, other_cat = rel["id_a"], rel["title_a"], rel["cat_a"]
            lines.append(f"- [{label}] [#{other_id}] {other_title} [{other_cat}]")

        return "\n".join(lines)
    finally:
        db.close()


@mcp.tool()
def get_context_summary(scope: str = "full") -> str:
    """取得當前系統狀態摘要。壓縮恢復或新 session 啟動時必須呼叫。

    Args:
        scope: 'full'（完整狀態）或 'compact'（精簡版）
    """
    db = get_db()
    try:
        sections = []

        # 公司資訊
        company = db.execute("SELECT * FROM company WHERE id = 1").fetchone()
        if company:
            sections.append(f"## 🏢 {company['name']}（{company['industry'] or '未設定'}）")

        # 待處理任務
        pending = db.execute(
            "SELECT id, title, assignee, priority, due_date FROM tasks WHERE status IN ('pending','in_progress') ORDER BY CASE priority WHEN 'urgent' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END, due_date LIMIT ?",
            (20 if scope == "full" else 5,),
        ).fetchall()
        if pending:
            sections.append(f"\n## 📝 待處理任務（{len(pending)} 項）")
            for t in pending:
                pri = {"urgent": "🔴", "normal": "🟡", "low": "🟢"}.get(t["priority"], "")
                due = f" 截止:{t['due_date']}" if t["due_date"] else ""
                sections.append(f"- {pri} [#{t['id']}] {t['title']} → {t['assignee'] or '未指派'}{due}")

        # 自動過期已超時的審核
        db.execute(
            "UPDATE approvals SET status = 'expired' WHERE status = 'waiting' AND expires_at IS NOT NULL AND expires_at < ?",
            (_now(),),
        )
        db.commit()

        # 等待審核（含 detail 提示 + 逾時警告）
        approvals = db.execute(
            "SELECT id, type, summary, detail, requester, created_at, expires_at FROM approvals WHERE status = 'waiting' ORDER BY created_at",
        ).fetchall()
        if approvals:
            sections.append(f"\n## ⏳ 等待審核（{len(approvals)} 項）")
            now = datetime.now()
            for a in approvals:
                detail_hint = ""
                if a["detail"]:
                    try:
                        d = json.loads(a["detail"])
                        resume = d.get("resume_action", "")
                        if resume:
                            detail_hint = f" → 核准後執行 {resume}"
                    except (json.JSONDecodeError, AttributeError):
                        detail_hint = f" | {a['detail'][:50]}"
                # 檢查是否等待超過 48 小時
                age_warning = ""
                try:
                    created = datetime.strptime(a["created_at"], "%Y-%m-%d %H:%M:%S")
                    hours_waiting = (now - created).total_seconds() / 3600
                    if hours_waiting > 48:
                        age_warning = f" 🔴 已等待 {int(hours_waiting)}h — 建議重新通知主管"
                except (ValueError, TypeError):
                    pass
                sections.append(f"- [#{a['id']}] {a['type']}: {a['summary']} (申請人:{a['requester'] or '?'}){detail_hint}{age_warning}")

        # 未處理 LINE 訊息
        queued = db.execute(
            "SELECT id, user_name, content, created_at FROM line_messages WHERE direction='inbound' AND status='queued' ORDER BY created_at",
        ).fetchall()
        if queued:
            sections.append(f"\n## 💬 未處理 LINE 訊息（{len(queued)} 則）")
            for m in queued:
                sections.append(f"- [{m['created_at']}] {m['user_name'] or '?'}: {m['content'][:100]}")

        # 庫存警報
        alerts = db.execute(
            "SELECT sku, name, current_stock, min_stock, unit FROM inventory WHERE current_stock <= min_stock AND min_stock > 0",
        ).fetchall()
        if alerts:
            sections.append(f"\n## ⚠️ 庫存警報（{len(alerts)} 項）")
            for a in alerts:
                sections.append(f"- [{a['sku']}] {a['name']}: 剩 {a['current_stock']}{a['unit']}（安全庫存 {a['min_stock']}）")

        if scope == "full":
            # 核心規則摘要
            rules_count = db.execute("SELECT COUNT(*) as c FROM business_rules WHERE superseded_by IS NULL").fetchone()["c"]
            if rules_count:
                recent_rules = db.execute(
                    "SELECT category, title FROM business_rules WHERE superseded_by IS NULL ORDER BY created_at DESC LIMIT 10"
                ).fetchall()
                sections.append(f"\n## 📋 企業規則（共 {rules_count} 條有效）")
                for r in recent_rules:
                    sections.append(f"- [{r['category']}] {r['title']}")

            # 最近的 session handoff
            handoff = db.execute(
                "SELECT summary, pending_items, created_at FROM session_handoffs ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            if handoff:
                sections.append(f"\n## 🔄 上次 Session 交接（{handoff['created_at']}）")
                sections.append(handoff["summary"])

            # 進行中的訂單（含下一步提示）
            active_orders = db.execute(
                """SELECT o.id, o.status, o.qc_status, o.total_amount, c.name as customer_name
                   FROM orders o LEFT JOIN customers c ON o.customer_id = c.id
                   WHERE o.status IN ('pending','confirmed','shipped','delivered')
                   ORDER BY o.created_at DESC LIMIT 10"""
            ).fetchall()
            if active_orders:
                sections.append(f"\n## 📦 進行中訂單（{len(active_orders)} 筆）")
                status_icon = {"pending": "⏳", "confirmed": "✅", "shipped": "🚚", "delivered": "📦"}
                for o in active_orders:
                    hint = ""
                    if o["status"] == "pending":
                        hint = " → 待確認"
                    elif o["status"] == "confirmed" and o["qc_status"] == "pending":
                        hint = f" → 待品檢 qc_order(order_id={o['id']})"
                    elif o["status"] == "confirmed" and o["qc_status"] == "passed":
                        hint = f" → 可出貨 fulfill_order(order_id={o['id']})"
                    elif o["status"] == "confirmed" and o["qc_status"] == "failed":
                        hint = " → QC不合格，需處理"
                    elif o["status"] == "shipped":
                        hint = " → 待送達確認"
                    elif o["status"] == "delivered":
                        hint = " → 待收款"
                    sections.append(
                        f"- {status_icon.get(o['status'], '')} [#{o['id']}] "
                        f"{o['customer_name'] or '?'} NT${o['total_amount']:,.0f}{hint}"
                    )

            # 逾期帳款
            overdue_count = db.execute("SELECT COUNT(*) as c FROM transactions WHERE payment_status = 'overdue'").fetchone()["c"]
            if overdue_count:
                overdue_total = db.execute("SELECT COALESCE(SUM(amount - paid_amount), 0) as s FROM transactions WHERE payment_status = 'overdue'").fetchone()["s"]
                sections.append(f"\n## 🔴 逾期帳款：{overdue_count} 筆，合計 NT${overdue_total:,.0f}")

            # 統計
            stats = {
                "員工": db.execute("SELECT COUNT(*) as c FROM employees WHERE active=1").fetchone()["c"],
                "客戶": db.execute("SELECT COUNT(*) as c FROM customers WHERE type='customer'").fetchone()["c"],
                "供應商": db.execute("SELECT COUNT(*) as c FROM customers WHERE type='supplier'").fetchone()["c"],
                "庫存品項": db.execute("SELECT COUNT(*) as c FROM inventory").fetchone()["c"],
            }
            sections.append(f"\n## 📊 數據統計")
            sections.append(" | ".join(f"{k}: {v}" for k, v in stats.items()))

            # 昨日快照趨勢比較
            yesterday = db.execute("SELECT * FROM daily_snapshots ORDER BY snapshot_date DESC LIMIT 1").fetchone()
            if yesterday:
                sections.append(f"\n## 📈 趨勢（vs {yesterday['snapshot_date']}）")
                current_pending = db.execute("SELECT COUNT(*) as c FROM tasks WHERE status IN ('pending','in_progress')").fetchone()["c"]
                delta_tasks = current_pending - yesterday["pending_tasks"]
                delta_str = f"+{delta_tasks}" if delta_tasks > 0 else str(delta_tasks)
                sections.append(f"- 待處理任務：{current_pending}（{delta_str}）")

            # 日期提醒（台灣稅務 + 固定支出）
            today = datetime.now()
            day, month = today.day, today.month
            reminders = []
            if day <= 5:
                reminders.append("每月 1-5 日：月結作業，確認上月帳務")
            if day in (4, 5):
                reminders.append("5 日前後：提醒發薪水")
            if 23 <= day <= 25:
                reminders.append("25 日前後：提醒繳勞健保")
            if month % 2 == 1 and 10 <= day <= 15:
                reminders.append(f"{month}/15：營業稅申報截止")
            if month == 5:
                reminders.append("5 月：營所稅 + 綜所稅申報")
            if reminders:
                sections.append("\n## 📅 日期提醒")
                for r in reminders:
                    sections.append(f"- {r}")

            # LINE push 額度追蹤
            month_start = today.strftime("%Y-%m-01")
            push_counts = db.execute(
                "SELECT channel_id, COUNT(*) as cnt FROM line_messages "
                "WHERE direction IN ('outbound', 'broadcast') AND created_at >= ? "
                "GROUP BY channel_id", (month_start,),
            ).fetchall()
            if push_counts:
                sections.append("\n## 📨 LINE 推送額度（免費方案 200 則/月）")
                for pc in push_counts:
                    used = pc["cnt"]
                    pct = used / 200 * 100
                    tag = " 🔴 超限" if pct >= 100 else " ⚠️ 接近上限" if pct >= 80 else ""
                    sections.append(f"- {pc['channel_id']}: {used}/200 ({pct:.0f}%){tag}")

        if not sections:
            return "系統剛初始化，尚無資料。請從建立公司資訊和員工名單開始。"
        return "\n".join(sections)
    finally:
        db.close()


@mcp.tool()
def log_interaction(
    actor: str,
    action: str,
    target_type: str = "",
    target_id: int = 0,
    detail: str = "",
    business_unit: str = "",
) -> str:
    """記錄操作日誌（審計追蹤）。

    Args:
        actor: 操作者（員工姓名或 'system'）
        action: 動作（如 rule_created, task_completed, stock_updated）
        target_type: 對象類型（task, rule, inventory, customer, approval）
        target_id: 對象 ID
        detail: 詳細說明
        business_unit: 所屬事業體（如 brand_d, content），留空=不分
    """
    db = get_db()
    try:
        db.execute(
            "INSERT INTO interaction_log (actor, action, target_type, target_id, detail, business_unit) VALUES (?,?,?,?,?,?)",
            (actor, action, target_type or None, target_id or None, detail or None, business_unit or None),
        )
        db.commit()
        return f"✅ 已記錄：{actor} → {action}"
    finally:
        db.close()


# ============================================================
# 任務管理（4 工具）
# ============================================================

@mcp.tool()
def create_task(
    title: str,
    description: str = "",
    assignee: str = "",
    priority: str = "normal",
    category: str = "general",
    tags: str = "",
    business_unit: str = "",
    due_date: str = "",
    parent_task_id: int = 0,
    created_by: str = "",
) -> str:
    """建立新任務。可指定 parent_task_id 建立子任務（多階段專案）。

    Args:
        title: 任務標題
        description: 任務描述
        assignee: 指派給誰（員工姓名）
        priority: 優先級 — urgent | normal | low
        category: 分類（如 general, production, content, design, delivery, meeting, admin, rock）
        tags: 標籤（逗號分隔，可多標籤，如 q2-goal,urgent,客戶A相關）
        business_unit: 所屬事業體（如 product, design, content），留空=不分
        due_date: 截止日期（YYYY-MM-DD）
        parent_task_id: 父任務 ID（建立子任務時用，0=獨立任務）
        created_by: 建立者
    """
    if priority not in ("urgent", "normal", "low"):
        return "ERROR: priority 必須是 urgent, normal, 或 low"

    db = get_db()
    try:
        # 驗證父任務存在
        if parent_task_id:
            parent = db.execute("SELECT id, title FROM tasks WHERE id = ?", (parent_task_id,)).fetchone()
            if not parent:
                return f"ERROR: 找不到父任務 #{parent_task_id}"

        cursor = db.execute(
            "INSERT INTO tasks (title, description, assignee, priority, category, tags, business_unit, due_date, parent_task_id, created_by) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (title, description or None, assignee or None, priority, category, tags or None, business_unit or None, due_date or None, parent_task_id or None, created_by or None),
        )
        task_id = cursor.lastrowid
        db.execute(
            "INSERT INTO interaction_log (actor, action, target_type, target_id, detail, business_unit) VALUES (?,?,?,?,?,?)",
            (created_by or "system", "task_created", "task", task_id, title, business_unit or None),
        )
        db.commit()
        pri_icon = {"urgent": "🔴", "normal": "🟡", "low": "🟢"}[priority]
        bu_warn = _validate_business_unit(db, business_unit)
        return f"✅ 任務 #{task_id} 已建立 {pri_icon} {title}" + (f" → {assignee}" if assignee else "") + bu_warn
    finally:
        db.close()


@mcp.tool()
def update_task(
    task_id: int,
    status: str = "",
    assignee: str = "",
    description: str = "",
    priority: str = "",
) -> str:
    """更新任務狀態或資訊。

    Args:
        task_id: 任務 ID
        status: 新狀態 — pending | in_progress | done | cancelled
        assignee: 重新指派
        description: 更新描述
        priority: 更新優先級
    """
    db = get_db()
    try:
        task = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not task:
            return f"ERROR: 找不到任務 #{task_id}"

        updates = []
        params = []
        if status:
            if status not in ("pending", "in_progress", "done", "cancelled"):
                return "ERROR: status 必須是 pending, in_progress, done, 或 cancelled"
            updates.append("status = ?")
            params.append(status)
            if status == "done":
                updates.append("completed_at = ?")
                params.append(_now())
        if assignee:
            updates.append("assignee = ?")
            params.append(assignee)
        if description:
            updates.append("description = ?")
            params.append(description)
        if priority:
            if priority not in ("urgent", "normal", "low"):
                return "ERROR: priority 必須是 urgent, normal, 或 low"
            updates.append("priority = ?")
            params.append(priority)

        if not updates:
            return "沒有指定要更新的欄位。"

        _safe_update(db, "tasks",
                     {"status", "completed_at", "assignee", "description", "priority"},
                     updates, params, "id = ?", [task_id])
        db.execute(
            "INSERT INTO interaction_log (actor, action, target_type, target_id, detail, business_unit) VALUES (?,?,?,?,?,?)",
            ("system", "task_updated", "task", task_id, f"更新: {', '.join(updates)}", task["business_unit"]),
        )
        db.commit()
        return f"✅ 任務 #{task_id} 已更新"
    finally:
        db.close()


@mcp.tool()
def list_tasks(status: str = "", assignee: str = "", category: str = "", business_unit: str = "", parent_task_id: int = 0, limit: int = 20) -> str:
    """列出任務。

    Args:
        status: 篩選狀態（pending, in_progress, done, cancelled），空白=全部
        assignee: 篩選指派對象
        category: 篩選分類
        business_unit: 篩選事業體（留空=全部）
        parent_task_id: 列出指定父任務的子任務（0=列出頂層任務）
        limit: 最多顯示幾筆
    """
    db = get_db()
    try:
        query = "SELECT id, title, assignee, status, priority, category, business_unit, due_date, parent_task_id, created_at FROM tasks WHERE 1=1"
        params: list = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if assignee:
            query += " AND assignee = ?"
            params.append(assignee)
        if category:
            query += " AND category = ?"
            params.append(category)
        if business_unit:
            query += " AND business_unit = ?"
            params.append(business_unit)
        if parent_task_id:
            query += " AND parent_task_id = ?"
            params.append(parent_task_id)
        query += " ORDER BY CASE priority WHEN 'urgent' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END, due_date LIMIT ?"
        params.append(limit)

        tasks = db.execute(query, params).fetchall()
        if not tasks:
            return "沒有符合條件的任務。"

        lines = [f"## 📝 任務列表（{len(tasks)} 項）"]
        for t in tasks:
            status_icon = {"pending": "⏳", "in_progress": "🔄", "done": "✅", "cancelled": "❌"}.get(t["status"], "")
            pri = {"urgent": "🔴", "normal": "", "low": "🟢"}.get(t["priority"], "")
            due = f" 截止:{t['due_date']}" if t["due_date"] else ""
            parent = f" (子任務 of #{t['parent_task_id']})" if t["parent_task_id"] else ""
            # 查子任務數量
            sub_count = db.execute("SELECT COUNT(*) as c FROM tasks WHERE parent_task_id = ?", (t["id"],)).fetchone()["c"]
            subs = f" 📂{sub_count}子任務" if sub_count > 0 else ""
            lines.append(f"- {status_icon}{pri} [#{t['id']}] {t['title']} → {t['assignee'] or '未指派'}{due}{parent}{subs}")
        return "\n".join(lines)
    finally:
        db.close()


@mcp.tool()
def search_tasks(query: str) -> str:
    """全文搜尋任務。

    Args:
        query: 搜尋關鍵字
    """
    like = _like_param(query)
    db = get_db()
    try:
        tasks = db.execute(
            """SELECT id, title, description, assignee, status, priority, due_date
               FROM tasks WHERE title LIKE ? OR description LIKE ? LIMIT 10""",
            (like, like),
        ).fetchall()
        if not tasks:
            return f"找不到與「{query}」相關的任務。"
        lines = [f"## 🔍 搜尋結果：「{query}」"]
        for t in tasks:
            status_icon = {"pending": "⏳", "in_progress": "🔄", "done": "✅", "cancelled": "❌"}.get(t["status"], "")
            lines.append(f"- {status_icon} [#{t['id']}] {t['title']} → {t['assignee'] or '未指派'}")
        return "\n".join(lines)
    finally:
        db.close()


# ============================================================
# 員工管理（3 工具）
# ============================================================

@mcp.tool()
def register_employee(
    name: str,
    role: str = "staff",
    department: str = "",
    line_user_id: str = "",
    permissions: str = "basic",
    phone: str = "",
    business_units: str = "",
) -> str:
    """註冊員工並綁定 LINE 帳號。

    Args:
        name: 員工姓名
        role: 角色 — boss | manager | staff
        department: 部門
        line_user_id: LINE User ID（用於綁定 LINE 身份）
        permissions: 權限等級 — admin | manager | basic
        phone: 聯絡電話
        business_units: 所屬事業體（逗號分隔，如 'brand_d,distribution'）。留空=全部事業體
    """
    db = get_db()
    try:
        cursor = db.execute(
            "INSERT INTO employees (name, role, department, line_user_id, permissions, phone, business_units) VALUES (?,?,?,?,?,?,?)",
            (name, role, department or None, line_user_id or None, permissions, phone or None, business_units or None),
        )
        emp_id = cursor.lastrowid
        db.execute(
            "INSERT INTO interaction_log (actor, action, target_type, target_id, detail, business_unit) VALUES (?,?,?,?,?,?)",
            ("system", "employee_registered", "employee", emp_id, f"註冊 {name}（{role}/{permissions}）", None),
        )
        db.commit()
        bu_label = f" 事業體:{business_units}" if business_units else ""
        return f"✅ 員工 #{emp_id} {name} 已註冊（{role}/{permissions}）{bu_label}" + (f" LINE已綁定" if line_user_id else "")
    except sqlite3.IntegrityError as e:
        if "line_user_id" in str(e):
            return f"ERROR: 此 LINE 帳號已被其他員工綁定"
        return f"ERROR: {e}"
    finally:
        db.close()


@mcp.tool()
def update_employee(
    employee_id: int,
    name: str = "",
    role: str = "",
    department: str = "",
    line_user_id: str = "__SKIP__",
    permissions: str = "",
    phone: str = "",
    business_units: str = "__SKIP__",
    active: int = -1,
    notes: str = "",
) -> str:
    """更新員工資料。只傳入要修改的欄位。

    Args:
        employee_id: 員工 ID（必填）
        name: 新姓名
        role: 新角色 — boss | manager | staff
        department: 新部門
        line_user_id: LINE User ID（傳空字串清除綁定）
        permissions: 新權限 — admin | manager | basic | none
        phone: 新電話
        business_units: 所屬事業體（逗號分隔，如 'brand_d,distribution'）。傳空字串清除（=全部事業體）
        active: 1=在職 0=離職
        notes: 備註
    """
    updates = []
    params = []
    if name:
        updates.append("name = ?")
        params.append(name)
    if role:
        updates.append("role = ?")
        params.append(role)
    if department:
        updates.append("department = ?")
        params.append(department)
    if line_user_id != "__SKIP__":
        updates.append("line_user_id = ?")
        params.append(line_user_id or None)
    if permissions:
        updates.append("permissions = ?")
        params.append(permissions)
    if phone:
        updates.append("phone = ?")
        params.append(phone)
    if business_units != "__SKIP__":
        updates.append("business_units = ?")
        params.append(business_units or None)
    if active >= 0:
        updates.append("active = ?")
        params.append(active)
    if notes:
        updates.append("notes = ?")
        params.append(notes)

    if not updates:
        return "ERROR: 沒有指定要更新的欄位"

    db = get_db()
    try:
        rowcount = _safe_update(db, "employees",
                                {"name", "role", "department", "line_user_id", "permissions", "phone", "business_units", "active", "notes"},
                                updates, params, "id = ?", [employee_id])
        if rowcount == 0:
            return f"ERROR: 找不到員工 #{employee_id}"
        changed = ", ".join(u.split(" = ")[0] for u in updates)
        db.execute(
            "INSERT INTO interaction_log (actor, action, target_type, target_id, detail, business_unit) VALUES (?,?,?,?,?,?)",
            ("system", "employee_updated", "employee", employee_id, f"更新：{changed}", None),
        )
        db.commit()
        return f"✅ 員工 #{employee_id} 已更新（{changed}）"
    except sqlite3.IntegrityError as e:
        return f"ERROR: {e}"
    finally:
        db.close()


@mcp.tool()
def lookup_employee(name_or_line_id: str) -> str:
    """查詢員工資訊（用姓名或 LINE User ID）。

    Args:
        name_or_line_id: 員工姓名或 LINE User ID
    """
    db = get_db()
    try:
        emp = db.execute(
            "SELECT * FROM employees WHERE (name = ? OR line_user_id = ?) AND active = 1",
            (name_or_line_id, name_or_line_id),
        ).fetchone()
        if not emp:
            return f"找不到員工：{name_or_line_id}"
        bu = emp['business_units'] if emp['business_units'] else '全部'
        return (
            f"## 👤 {emp['name']}\n"
            f"- 角色：{emp['role']} | 權限：{emp['permissions']}\n"
            f"- 部門：{emp['department'] or '未設定'}\n"
            f"- 事業體：{bu}\n"
            f"- LINE：{'已綁定' if emp['line_user_id'] else '未綁定'}\n"
            f"- 電話：{emp['phone'] or '未設定'}\n"
            f"- 備註：{emp['notes'] or '無'}"
        )
    finally:
        db.close()


@mcp.tool()
def list_employees(active_only: bool = True) -> str:
    """列出所有員工。

    Args:
        active_only: True 只顯示在職員工
    """
    db = get_db()
    try:
        query = "SELECT id, name, role, department, permissions, line_user_id, business_units FROM employees"
        if active_only:
            query += " WHERE active = 1"
        query += " ORDER BY CASE role WHEN 'boss' THEN 0 WHEN 'manager' THEN 1 ELSE 2 END, name"
        emps = db.execute(query).fetchall()
        if not emps:
            return "目前沒有員工資料。"
        lines = [f"## 👥 員工名冊（{len(emps)} 人）"]
        for e in emps:
            line_status = "📱" if e["line_user_id"] else "❌"
            bu = f" [{e['business_units']}]" if e["business_units"] else ""
            lines.append(f"- [#{e['id']}] **{e['name']}** ({e['role']}/{e['permissions']}) {e['department'] or ''}{bu} {line_status}")
        return "\n".join(lines)
    finally:
        db.close()


# ============================================================
# LINE 訊息查詢
# ============================================================

@mcp.tool()
def search_line_messages(
    query: str = "",
    user_id: str = "",
    user_name: str = "",
    direction: str = "",
    channel_id: str = "",
    days: int = 7,
    limit: int = 30,
) -> str:
    """查詢 LINE 訊息歷史紀錄。

    Args:
        query: 搜尋關鍵字（模糊比對訊息內容）
        user_id: 篩選特定用戶的 LINE user ID
        user_name: 篩選特定用戶暱稱（模糊比對）
        direction: 篩選方向 — inbound（收到）| outbound（發出）| 留空=全部
        channel_id: 篩選 LINE OA channel（多品牌模式），留空=全部
        days: 查詢最近幾天（預設 7 天）
        limit: 最多回傳幾則（預設 30）
    """
    db = get_db()
    try:
        conditions = []
        params: list = []

        if query:
            conditions.append("content LIKE ?")
            params.append(_like_param(query))
        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)
        if user_name:
            conditions.append("user_name LIKE ?")
            params.append(_like_param(user_name))
        if direction:
            conditions.append("direction = ?")
            params.append(direction)
        if channel_id:
            conditions.append("channel_id = ?")
            params.append(channel_id)

        conditions.append("created_at >= datetime('now', 'localtime', ?)")
        params.append(f"-{days} days")

        where = " AND ".join(conditions)
        params.append(limit)

        rows = db.execute(
            f"SELECT id, channel_id, user_id, user_name, direction, content, msg_type, source_type, group_id, status, created_at "
            f"FROM line_messages WHERE {where} ORDER BY created_at DESC LIMIT ?",
            params,
        ).fetchall()

        if not rows:
            return "沒有找到符合條件的 LINE 訊息。"

        lines = [f"## LINE 訊息（{len(rows)} 則）\n"]
        for m in rows:
            arrow = "→" if m["direction"] == "outbound" else "←"
            src = ""
            if m["source_type"] == "group" and m["group_id"]:
                src = f" [群組 {m['group_id']}]"
            name = m["user_name"] or m["user_id"][:8]
            chat_id = m["group_id"] if m["source_type"] == "group" and m["group_id"] else m["user_id"]
            ch_label = f" [{m['channel_id']}]" if m["channel_id"] and m["channel_id"] != "default" else ""
            lines.append(
                f"- {arrow} [{m['created_at']}]{ch_label} **{name}** (user_id={m['user_id']}){src} (chat_id={chat_id}): {m['content'][:200]}"
            )
        return "\n".join(lines)
    finally:
        db.close()


# ============================================================
# LINE 群組管理
# ============================================================

@mcp.tool()
def register_line_group(
    group_id: str,
    group_name: str = "",
    group_type: str = "other",
    channel_id: str = "",
    purpose: str = "",
    notes: str = "",
) -> str:
    """註冊 LINE 群組。當 bot 加入新群組或老闆告知群組用途時呼叫。

    Args:
        group_id: LINE 群組 ID（從 channel tag 的 chat_id 取得）
        group_name: 群組名稱（例：公司工作群、經銷商群）
        group_type: 群組類型 — work（工作）| customer（客戶）| supplier（供應商）| marketing（行銷）| other
        channel_id: 來自哪個 LINE OA（多品牌模式），留空=default
        purpose: 一句話描述群組功能（例：品牌 C內勤訂單協調、鼎新供應商交期追蹤）
        notes: 備註（成員、特殊 SOP、限制等自由文字）
    """
    ch = channel_id or "default"
    db = get_db()
    try:
        existing = db.execute(
            "SELECT id FROM line_groups WHERE group_id = ? AND channel_id = ?",
            (group_id, ch),
        ).fetchone()
        if existing:
            db.execute(
                "UPDATE line_groups SET "
                "  group_name=COALESCE(NULLIF(?,''),group_name),"
                "  group_type=?,"
                "  purpose=COALESCE(NULLIF(?,''),purpose),"
                "  notes=COALESCE(NULLIF(?,''),notes),"
                "  updated_at=datetime('now','localtime') "
                "WHERE group_id=? AND channel_id=?",
                (group_name, group_type, purpose, notes, group_id, ch),
            )
            db.commit()
            purpose_label = f" — {purpose}" if purpose else ""
            return f"✅ 群組已更新：{group_name or group_id}（{group_type}）{purpose_label}"
        else:
            db.execute(
                "INSERT INTO line_groups (group_id, group_name, group_type, channel_id, purpose, notes) "
                "VALUES (?,?,?,?,?,?)",
                (group_id, group_name, group_type, ch, purpose or None, notes or None),
            )
            db.commit()
            purpose_label = f" — {purpose}" if purpose else ""
            return f"✅ 群組已註冊：{group_name or group_id}（{group_type}）{purpose_label}"
    finally:
        db.close()


@mcp.tool()
def list_line_groups(group_type: str = "", channel_id: str = "") -> str:
    """列出所有已註冊的 LINE 群組。

    Args:
        group_type: 篩選類型 — work | customer | supplier | marketing | other | 留空=全部
        channel_id: 篩選 LINE OA channel（多品牌模式），留空=全部
    """
    db = get_db()
    try:
        conditions: list[str] = []
        params: list = []
        if group_type:
            conditions.append("group_type = ?")
            params.append(group_type)
        if channel_id:
            conditions.append("channel_id = ?")
            params.append(channel_id)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        rows = db.execute(
            f"SELECT group_id, group_name, group_type, channel_id, purpose, notes, created_at FROM line_groups{where} ORDER BY created_at",
            params,
        ).fetchall()

        if not rows:
            return "目前沒有已註冊的 LINE 群組。"

        type_icon = {"work": "💼", "customer": "👤", "supplier": "🏭", "marketing": "📢", "other": "💬"}
        lines = [f"## LINE 群組（{len(rows)} 個）\n"]
        for g in rows:
            icon = type_icon.get(g["group_type"], "💬")
            name = g["group_name"] or g["group_id"][:12]
            lines.append(f"- {icon} **{name}** ({g['group_type']}) — chat_id={g['group_id']}")
            if g["purpose"]:
                lines.append(f"  🎯 功能：{g['purpose']}")
            if g["notes"]:
                lines.append(f"  📝 備註：{g['notes']}")
        return "\n".join(lines)
    finally:
        db.close()


# ============================================================
# 客戶管理（3 工具）
# ============================================================

@mcp.tool()
def add_customer(
    name: str,
    type: str = "customer",
    phone: str = "",
    email: str = "",
    line_user_id: str = "",
    tags: str = "",
    notes: str = "",
    discount_rate: float = 0.0,
    payment_terms: str = "net30",
    primary_business_unit: str = "",
) -> str:
    """新增客戶、供應商或經銷商。

    Args:
        name: 名稱（公司名或個人名）
        type: 類型 — customer（客戶）| supplier（供應商）| distributor（經銷商）
        phone: 電話
        email: Email
        line_user_id: LINE User ID（用於 LINE 身份辨識）
        tags: 標籤（逗號分隔，如 vip,wholesale）
        notes: 備註
        discount_rate: 折扣率（0=原價, 0.15=85折, 0.2=8折）
        payment_terms: 付款條件 — prepaid | cod | deposit_30 | net30 | net60
        primary_business_unit: 主要歸屬事業體（如 brand_c, brand_a），留空=無特定歸屬
    """
    if type not in ("customer", "supplier", "distributor"):
        return "ERROR: type 必須是 customer, supplier, 或 distributor"

    db = get_db()
    try:
        bu_warn = _validate_business_unit(db, primary_business_unit) if primary_business_unit else ""
        cursor = db.execute(
            "INSERT INTO customers (name, type, phone, email, line_user_id, tags, notes, discount_rate, payment_terms, primary_business_unit) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (name, type, phone or None, email or None, line_user_id or None,
             tags or None, notes or None, discount_rate, payment_terms,
             primary_business_unit or None),
        )
        cust_id = cursor.lastrowid
        type_label = {"customer": "客戶", "supplier": "供應商", "distributor": "經銷商"}.get(type, type)
        db.execute(
            "INSERT INTO interaction_log (actor, action, target_type, target_id, detail, business_unit) VALUES (?,?,?,?,?,?)",
            ("system", "customer_added", "customer", cust_id, f"新增{type_label} {name}", primary_business_unit or None),
        )
        db.commit()
        bu_label = f" [{primary_business_unit}]" if primary_business_unit else ""
        return f"✅ 客戶 #{cust_id} {name}{bu_label} 已建立（{payment_terms}）" + (f" LINE已綁定" if line_user_id else "") + bu_warn
    finally:
        db.close()


@mcp.tool()
def find_customer(query: str, type: str = "") -> str:
    """搜尋客戶、供應商或經銷商。

    Args:
        query: 搜尋關鍵字
        type: 篩選類型（customer/supplier/distributor），空白=全部
    """
    like = _like_param(query)
    db = get_db()
    try:
        # v4: 新增 total_ordered/total_fulfilled/total_paid 與 last_*_date 及 primary_business_unit
        fields = ("id, name, type, phone, email, line_user_id, tags, notes, pipeline_stage, "
                  "total_purchases, last_purchase_date, total_ordered, total_fulfilled, total_paid, "
                  "last_order_date, last_fulfilled_date, last_payment_date, "
                  "discount_rate, payment_terms, primary_business_unit")
        if type:
            customers = db.execute(
                f"""SELECT {fields}
                   FROM customers WHERE type = ? AND (name LIKE ? OR notes LIKE ? OR tags LIKE ? OR phone LIKE ? OR line_user_id = ?)
                   LIMIT 10""",
                (type, like, like, like, like, query.strip()),
            ).fetchall()
        else:
            customers = db.execute(
                f"""SELECT {fields}
                   FROM customers WHERE name LIKE ? OR notes LIKE ? OR tags LIKE ? OR phone LIKE ? OR line_user_id = ?
                   LIMIT 10""",
                (like, like, like, like, query.strip()),
            ).fetchall()
        if not customers:
            return f"找不到與「{query}」相關的{'客戶' if not type else type}。"
        type_icon = {"customer": "👤", "supplier": "🏭", "distributor": "🚚"}
        stage_icon = {"prospect": "🔵", "contacted": "🟡", "negotiating": "🟠", "closed_won": "🟢", "closed_lost": "🔴"}
        lines = [f"## 搜尋結果：「{query}」"]
        for c in customers:
            icon = type_icon.get(c['type'], '👤')
            stage = ""
            if c['pipeline_stage'] and c['pipeline_stage'] != 'none':
                s_icon = stage_icon.get(c['pipeline_stage'], '')
                stage = f" {s_icon}{c['pipeline_stage']}"
            terms_str = f" 📄{c['payment_terms']}" if c['payment_terms'] and c['payment_terms'] != 'net30' else ""
            discount_str = f" 🏷️{c['discount_rate']*100:.0f}%off" if c['discount_rate'] and c['discount_rate'] > 0 else ""
            # v4: primary_business_unit 顯示
            bu_label = f" [{c['primary_business_unit']}]" if c['primary_business_unit'] else ""
            # v4: 優先顯示 total_fulfilled（已認列營收），fallback 到舊欄位 total_purchases
            sales_fig = c['total_fulfilled'] or c['total_purchases'] or 0
            sales_label = f" 💰{sales_fig:,.0f}" if sales_fig else ""
            # 顯示最近日期（出貨日優先）
            last_date = c['last_fulfilled_date'] or c['last_purchase_date']
            date_label = f" 📅{last_date}" if last_date else ""
            lines.append(
                f"- {icon} [#{c['id']}] **{c['name']}**{bu_label} ({c['type']}){stage} {c['phone'] or ''}"
                f"{sales_label}{date_label}"
                f"{terms_str}{discount_str} "
                f"{c['tags'] or ''}"
            )
        return "\n".join(lines)
    finally:
        db.close()


@mcp.tool()
def update_customer(
    customer_id: int,
    name: str = "",
    phone: str = "",
    email: str = "",
    line_user_id: str = "__SKIP__",
    tags: str = "",
    notes: str = "",
    pipeline_stage: str = "",
    total_purchases: float = -1,
    discount_rate: float = -1.0,
    payment_terms: str = "",
    primary_business_unit: str = "__SKIP__",
) -> str:
    """更新客戶/供應商/經銷商資訊。

    Args:
        customer_id: 客戶 ID
        name: 新姓名（空白=不更新）
        phone: 新電話
        email: 新 Email
        line_user_id: LINE User ID（傳空字串清除綁定）
        tags: 新標籤
        notes: 新備註
        pipeline_stage: 業務階段 — none | prospect | contacted | negotiating | closed_won | closed_lost
        total_purchases: 累計消費金額（-1=不更新）
        discount_rate: 折扣率（-1=不更新，0=原價，0.15=85折）
        payment_terms: 付款條件 — prepaid | cod | deposit_30 | net30 | net60（空白=不更新）
        primary_business_unit: 主要歸屬事業體（傳空字串清除歸屬）
    """
    db = get_db()
    try:
        cust = db.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
        if not cust:
            return f"ERROR: 找不到客戶 #{customer_id}"

        updates = []
        params = []
        if name:
            updates.append("name = ?")
            params.append(name)
        if phone:
            updates.append("phone = ?")
            params.append(phone)
        if email:
            updates.append("email = ?")
            params.append(email)
        if line_user_id != "__SKIP__":
            updates.append("line_user_id = ?")
            params.append(line_user_id or None)
        if tags:
            updates.append("tags = ?")
            params.append(tags)
        if notes:
            updates.append("notes = ?")
            params.append(notes)
        if pipeline_stage:
            updates.append("pipeline_stage = ?")
            params.append(pipeline_stage)
        if total_purchases >= 0:
            updates.append("total_purchases = ?")
            params.append(total_purchases)
        if discount_rate >= 0:
            updates.append("discount_rate = ?")
            params.append(discount_rate)
        if payment_terms:
            updates.append("payment_terms = ?")
            params.append(payment_terms)
        if primary_business_unit != "__SKIP__":
            updates.append("primary_business_unit = ?")
            params.append(primary_business_unit or None)

        if not updates:
            return "沒有指定要更新的欄位。"

        _safe_update(db, "customers",
                     {"name", "type", "phone", "email", "line_user_id", "tags", "notes", "pipeline_stage", "total_purchases", "discount_rate", "payment_terms", "primary_business_unit"},
                     updates, params, "id = ?", [customer_id])
        changed = ", ".join(u.split(" = ")[0] for u in updates)
        db.execute(
            "INSERT INTO interaction_log (actor, action, target_type, target_id, detail, business_unit) VALUES (?,?,?,?,?,?)",
            ("system", "customer_updated", "customer", customer_id, f"更新 {cust['name']}：{changed}", None),
        )
        db.commit()
        return f"✅ 客戶 #{customer_id} 已更新"
    finally:
        db.close()


@mcp.tool()
def set_customer_entity_terms(
    customer_id: int,
    business_unit: str,
    discount_rate: float = -1.0,
    payment_terms: str = "",
) -> str:
    """設定客戶在特定事業體的折扣率和付款條件。覆寫 customers 表的預設值。

    Args:
        customer_id: 客戶 ID
        business_unit: 事業體（如 brand_c, brand_d）
        discount_rate: 折扣率（-1=不設定，0=原價，0.15=85折）
        payment_terms: 付款條件 — prepaid | cod | deposit_30 | net30 | net60（空白=不設定）
    """
    db = get_db()
    try:
        cust = db.execute("SELECT name FROM customers WHERE id = ?", (customer_id,)).fetchone()
        if not cust:
            return f"ERROR: 找不到客戶 #{customer_id}"

        existing = db.execute(
            "SELECT * FROM customer_entity_terms WHERE customer_id = ? AND business_unit = ?",
            (customer_id, business_unit),
        ).fetchone()

        if existing:
            updates, params = [], []
            if discount_rate >= 0:
                updates.append("discount_rate = ?")
                params.append(discount_rate)
            if payment_terms:
                updates.append("payment_terms = ?")
                params.append(payment_terms)
            if not updates:
                return "沒有指定要更新的欄位。"
            _safe_update(db, "customer_entity_terms",
                         {"discount_rate", "payment_terms"},
                         updates, params, "customer_id = ? AND business_unit = ?", [customer_id, business_unit])
            detail = f"更新 {cust['name']} 在 {business_unit} 條件：{', '.join(u.split(' = ')[0] for u in updates)}"
            db.execute(
                "INSERT INTO interaction_log (actor, action, target_type, target_id, detail, business_unit) VALUES (?,?,?,?,?,?)",
                ("system", "customer_terms_updated", "customer", customer_id, detail, business_unit),
            )
            db.commit()
            return f"✅ 已更新 {cust['name']} 在 {business_unit} 的條件"
        else:
            dr = discount_rate if discount_rate >= 0 else 0
            pt = payment_terms or "net30"
            db.execute(
                "INSERT INTO customer_entity_terms (customer_id, business_unit, discount_rate, payment_terms) VALUES (?,?,?,?)",
                (customer_id, business_unit, dr, pt),
            )
            db.execute(
                "INSERT INTO interaction_log (actor, action, target_type, target_id, detail, business_unit) VALUES (?,?,?,?,?,?)",
                ("system", "customer_terms_set", "customer", customer_id,
                 f"設定 {cust['name']} 在 {business_unit} 條件：折扣 {dr*100:.0f}%，付款 {pt}", business_unit),
            )
            db.commit()
            return f"✅ 已設定 {cust['name']} 在 {business_unit} 的條件：折扣 {dr*100:.0f}%，付款 {pt}"
    finally:
        db.close()


# ============================================================
# 外包夥伴管理（4 工具）
# ============================================================

@mcp.tool()
def register_partner(
    name: str,
    role: str = "",
    line_user_id: str = "",
    phone: str = "",
    email: str = "",
    business_units: str = "",
    payment_terms: str = "",
    notes: str = "",
) -> str:
    """註冊外包夥伴（非員工、非客戶的協作者，如剪輯師、攝影、社群發布等）。

    Args:
        name: 夥伴姓名或公司名
        role: 職責（自由文字，如「影片剪輯」「社群發布」「外景拍攝」）
        line_user_id: LINE User ID（用於 LINE 身份辨識）
        phone: 電話
        email: Email
        business_units: 服務的事業體（逗號分隔，如 'brand_e,brand_a'；留空=全部）
        payment_terms: 付款條件（「月結」「案件計酬」「預付」等自由文字）
        notes: 備註（如多 OA LINE user_id、合約細節、費用標準）
    """
    db = get_db()
    try:
        cursor = db.execute(
            "INSERT INTO external_partners (name, role, line_user_id, phone, email, business_units, payment_terms, notes) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (name, role or None, line_user_id or None, phone or None, email or None,
             business_units or None, payment_terms or None, notes or None),
        )
        pid = cursor.lastrowid
        db.execute(
            "INSERT INTO interaction_log (actor, action, target_type, target_id, detail, business_unit) VALUES (?,?,?,?,?,?)",
            ("system", "partner_registered", "external_partner", pid,
             f"註冊外包 {name} ({role or '未指定職責'})", None),
        )
        db.commit()
        bu_label = f" [BU: {business_units}]" if business_units else ""
        line_label = " 📱" if line_user_id else ""
        return f"✅ 外包夥伴 #{pid} {name}{bu_label}{line_label} 已註冊（{role or '未指定職責'}）"
    finally:
        db.close()


@mcp.tool()
def update_partner(
    partner_id: int,
    name: str = "",
    role: str = "",
    line_user_id: str = "__SKIP__",
    phone: str = "",
    email: str = "",
    business_units: str = "__SKIP__",
    payment_terms: str = "",
    notes: str = "",
    active: int = -1,
) -> str:
    """更新外包夥伴資料。

    Args:
        partner_id: 夥伴 ID
        line_user_id: LINE User ID（傳空字串清除綁定）
        business_units: 服務的事業體（傳空字串清除）
        active: 1=活躍 0=停用（-1=不更新）
    """
    db = get_db()
    try:
        p = db.execute("SELECT * FROM external_partners WHERE id = ?", (partner_id,)).fetchone()
        if not p:
            return f"ERROR: 找不到外包夥伴 #{partner_id}"

        updates, params = [], []
        if name:
            updates.append("name = ?"); params.append(name)
        if role:
            updates.append("role = ?"); params.append(role)
        if line_user_id != "__SKIP__":
            updates.append("line_user_id = ?"); params.append(line_user_id or None)
        if phone:
            updates.append("phone = ?"); params.append(phone)
        if email:
            updates.append("email = ?"); params.append(email)
        if business_units != "__SKIP__":
            updates.append("business_units = ?"); params.append(business_units or None)
        if payment_terms:
            updates.append("payment_terms = ?"); params.append(payment_terms)
        if notes:
            updates.append("notes = ?"); params.append(notes)
        if active in (0, 1):
            updates.append("active = ?"); params.append(active)

        if not updates:
            return "沒有指定要更新的欄位。"

        _safe_update(db, "external_partners",
                     {"name", "role", "line_user_id", "phone", "email",
                      "business_units", "payment_terms", "notes", "active"},
                     updates, params, "id = ?", [partner_id])
        changed = ", ".join(u.split(" = ")[0] for u in updates)
        db.execute(
            "INSERT INTO interaction_log (actor, action, target_type, target_id, detail, business_unit) VALUES (?,?,?,?,?,?)",
            ("system", "partner_updated", "external_partner", partner_id,
             f"更新 {p['name']}：{changed}", None),
        )
        db.commit()
        return f"✅ 外包夥伴 #{partner_id} 已更新（{changed}）"
    finally:
        db.close()


@mcp.tool()
def list_partners(active_only: bool = True, role: str = "", business_unit: str = "") -> str:
    """列出外包夥伴。

    Args:
        active_only: 只列活躍夥伴（預設 True）
        role: 篩選職責關鍵字（模糊比對）
        business_unit: 篩選服務特定事業體的夥伴
    """
    db = get_db()
    try:
        conditions, params = [], []
        if active_only:
            conditions.append("active = 1")
        if role:
            conditions.append("role LIKE ?"); params.append(_like_param(role))
        if business_unit:
            conditions.append("(business_units LIKE ? OR business_units IS NULL OR business_units = '')")
            params.append(_like_param(business_unit))
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        rows = db.execute(
            f"SELECT id, name, role, line_user_id, phone, business_units, payment_terms, active "
            f"FROM external_partners{where} ORDER BY active DESC, id",
            params,
        ).fetchall()
        if not rows:
            return "目前沒有符合條件的外包夥伴。"
        lines = [f"## 🤝 外包夥伴（{len(rows)} 位）"]
        for p in rows:
            status = "" if p["active"] else " ⚠️ 停用"
            line_label = " 📱" if p["line_user_id"] else " ❌"
            bu_label = f" [{p['business_units']}]" if p["business_units"] else ""
            terms_label = f" | {p['payment_terms']}" if p["payment_terms"] else ""
            lines.append(
                f"- [#{p['id']}] **{p['name']}** ({p['role'] or '未指定'}){bu_label}{line_label}"
                f" {p['phone'] or ''}{terms_label}{status}"
            )
        return "\n".join(lines)
    finally:
        db.close()


@mcp.tool()
def find_partner(query: str) -> str:
    """搜尋外包夥伴（姓名、職責、電話或 LINE user ID）。

    Args:
        query: 搜尋關鍵字，或傳 LINE user_id 查身份
    """
    db = get_db()
    try:
        like = _like_param(query)
        rows = db.execute(
            """SELECT * FROM external_partners
               WHERE name LIKE ? OR role LIKE ? OR phone LIKE ? OR line_user_id = ? OR notes LIKE ?
               ORDER BY active DESC, id LIMIT 10""",
            (like, like, like, query.strip(), like),
        ).fetchall()
        if not rows:
            return f"找不到符合「{query}」的外包夥伴。"
        lines = [f"## 🔍 外包夥伴搜尋：「{query}」"]
        for p in rows:
            status = "" if p["active"] else " ⚠️ 停用"
            line_label = f" LINE:{p['line_user_id'][:8]}..." if p["line_user_id"] else ""
            bu_label = f" [{p['business_units']}]" if p["business_units"] else ""
            lines.append(
                f"- [#{p['id']}] **{p['name']}** ({p['role'] or '未指定'}){bu_label}"
                f" {p['phone'] or ''}{line_label}{status}"
            )
            if p["notes"]:
                lines.append(f"  備註：{p['notes'][:100]}")
        return "\n".join(lines)
    finally:
        db.close()


# ============================================================
# 庫存管理（3 工具）
# ============================================================

@mcp.tool()
def check_stock(sku_or_name: str, business_unit: str = "") -> str:
    """查詢庫存。可用 SKU 或品名搜尋。

    Args:
        sku_or_name: SKU 編號或品名關鍵字
        business_unit: 篩選特定事業體（如 brand_c, brand_d），留空=全部
    """
    db = get_db()
    try:
        # 先精確查 SKU（優先 SKU+BU 組合）
        item = None
        if business_unit:
            item = db.execute("SELECT * FROM inventory WHERE sku = ? AND business_unit = ?", (sku_or_name, business_unit)).fetchone()
        if not item:
            item = db.execute("SELECT * FROM inventory WHERE sku = ?", (sku_or_name,)).fetchone()
        if item:
            bu_label = f" [{item['business_unit']}]" if item["business_unit"] else ""
            # v4: Bug #4 — 顯示預留 + 可用量
            reserved = item["reserved"] or 0
            available = item["current_stock"] - reserved
            alert = ""
            if item["current_stock"] <= item["min_stock"] and item["min_stock"] > 0:
                alert = " ⚠️ 實體庫存低於安全庫存！"
            elif available <= item["min_stock"] and item["min_stock"] > 0:
                alert = " ⚠️ 可用量低於安全庫存（已有預留佔用）"
            cross_bu = ""
            if business_unit and item["business_unit"] and item["business_unit"] != business_unit:
                cross_bu = f"\n- ⚠️ 注意：此品項屬於事業體 {item['business_unit']}，非 {business_unit}"
            return (
                f"## 📦 {item['name']} [{item['sku']}]{bu_label}\n"
                f"- 庫存：{item['current_stock']}{item['unit']}（預留 {reserved}，可用 {available}）{alert}\n"
                f"- 安全庫存：{item['min_stock']}{item['unit']}\n"
                f"- 成本：{item['unit_cost'] or '?'} | 售價：{item['sell_price'] or '?'}\n"
                f"- 位置：{item['location'] or '未設定'}\n"
                f"- 最後進貨：{item['last_restock_date'] or '無紀錄'}"
                + cross_bu
            )

        # LIKE 搜尋
        like = _like_param(sku_or_name)
        if business_unit:
            items = db.execute(
                "SELECT * FROM inventory WHERE (name LIKE ? OR sku LIKE ? OR category LIKE ?) AND business_unit = ? LIMIT 5",
                (like, like, like, business_unit),
            ).fetchall()
        else:
            items = db.execute(
                "SELECT * FROM inventory WHERE name LIKE ? OR sku LIKE ? OR category LIKE ? LIMIT 5",
                (like, like, like),
            ).fetchall()
        if not items:
            return f"找不到庫存品項：{sku_or_name}" + (f"（事業體：{business_unit}）" if business_unit else "")
        lines = [f"## 🔍 庫存搜尋：「{sku_or_name}」" + (f"（{business_unit}）" if business_unit else "")]
        for i in items:
            bu_label = f" [{i['business_unit']}]" if i["business_unit"] else ""
            reserved = i["reserved"] or 0
            available = i["current_stock"] - reserved
            alert = " ⚠️" if i["current_stock"] <= i["min_stock"] and i["min_stock"] > 0 else ""
            reserved_label = f"（預留 {reserved}，可用 {available}）" if reserved else ""
            lines.append(f"- [{i['sku']}] {i['name']}{bu_label}: {i['current_stock']}{i['unit']}{reserved_label}{alert}")
        return "\n".join(lines)
    finally:
        db.close()


@mcp.tool()
def update_stock(
    sku: str,
    quantity_change: int,
    reason: str = "",
    name: str = "",
    sell_price: float = -1,
    unit_cost: float = -1,
    min_stock: int = -1,
    unit: str = "",
    category: str = "",
    business_unit: str = "",
) -> str:
    """調整庫存數量（正數=進貨，負數=出貨/損耗）。SKU 不存在時自動建立新品項。

    Args:
        sku: SKU 編號
        quantity_change: 數量變動（正=進貨，負=出貨）
        reason: 調整原因
        name: 品項名稱（新建 SKU 時使用）
        sell_price: 售價（-1=不設定）
        unit_cost: 成本（-1=不設定）
        min_stock: 安全庫存（-1=不設定）
        unit: 單位（如「個」「箱」「組」）
        category: 品項分類
        business_unit: 所屬事業體（如 brand_c, brand_d），留空=不分
    """
    db = get_db()
    try:
        # 優先查 SKU+business_unit 組合，fallback 到無歸屬（共用）庫存，絕不跨 BU
        item = None
        if business_unit:
            item = db.execute("SELECT * FROM inventory WHERE sku = ? AND business_unit = ?", (sku, business_unit)).fetchone()
        if not item:
            item = db.execute(
                "SELECT * FROM inventory WHERE sku = ? AND (business_unit IS NULL OR business_unit = '')",
                (sku,),
            ).fetchone()
        if not item:
            if quantity_change < 0:
                return f"ERROR: 找不到 SKU={sku}（新增品項請用 0 或正數）"
            # SKU 不存在 → 自動建立新品項（quantity_change=0 允許純建檔）
            cols = ["sku", "name", "current_stock"]
            vals = [sku, name or sku, max(quantity_change, 0)]
            if business_unit:
                cols.append("business_unit"); vals.append(business_unit)
            if sell_price >= 0:
                cols.append("sell_price"); vals.append(sell_price)
            if unit_cost >= 0:
                cols.append("unit_cost"); vals.append(unit_cost)
            if min_stock >= 0:
                cols.append("min_stock"); vals.append(min_stock)
            if unit:
                cols.append("unit"); vals.append(unit)
            if category:
                cols.append("category"); vals.append(category)
            placeholders = ",".join("?" for _ in cols)
            inv_cursor = db.execute(f"INSERT INTO inventory ({','.join(cols)}) VALUES ({placeholders})", vals)
            db.execute(
                "INSERT INTO interaction_log (actor, action, target_type, target_id, detail, business_unit) VALUES (?,?,?,?,?,?)",
                ("system", "stock_created", "inventory", inv_cursor.lastrowid,
                 f"新建品項 [{sku}] {name or sku}，初始庫存 {quantity_change}。{reason or ''}", business_unit or None),
            )
            db.commit()
            # 新建品項的進貨記帳提醒
            new_item_guidance = ""
            item_unit = unit or "個"
            item_name = name or sku
            if unit_cost >= 0 and quantity_change > 0:
                cost = quantity_change * unit_cost
                new_item_guidance = _build_guidance(next_steps=[
                    f"record_transaction(type='expense', amount={cost}, category='inventory_purchase', "
                    f"description='進貨 {item_name} {quantity_change}{item_unit} @ NT${unit_cost:,.0f}')",
                    "問使用者：已付款(payment_status='paid')還是賒帳(payment_status='pending')？",
                ])
            elif quantity_change > 0:
                new_item_guidance = _build_guidance(next_steps=[
                    f"record_transaction(type='expense', category='inventory_purchase', "
                    f"description='進貨 {item_name} {quantity_change}{item_unit}') — 需確認進貨金額",
                ])
            bu_warn = _validate_business_unit(db, business_unit)
            return f"✅ 新建品項 [{sku}] {name or sku}，初始庫存 {quantity_change}{unit or '個'}" + new_item_guidance + bu_warn

        new_stock = item["current_stock"] + quantity_change
        if new_stock < 0:
            return f"ERROR: 庫存不足。目前 {item['current_stock']}{item['unit']}，無法扣減 {abs(quantity_change)}"

        stock_updates = ["current_stock = ?"]
        stock_params: list = [new_stock]
        if quantity_change > 0:
            stock_updates.append("last_restock_date = ?")
            stock_params.append(_now()[:10])

        # v4+: Obs #7 — 允許對既有 SKU 更新 metadata（min_stock / sell_price / unit_cost）
        if min_stock >= 0:
            stock_updates.append("min_stock = ?")
            stock_params.append(min_stock)
        if sell_price >= 0:
            stock_updates.append("sell_price = ?")
            stock_params.append(sell_price)
        if unit_cost >= 0:
            stock_updates.append("unit_cost = ?")
            stock_params.append(unit_cost)

        _safe_update(db, "inventory",
                     {"current_stock", "last_restock_date", "min_stock", "sell_price", "unit_cost"},
                     stock_updates, stock_params, "id = ?", [item["id"]])

        direction = "進貨" if quantity_change > 0 else "出貨"
        db.execute(
            "INSERT INTO interaction_log (actor, action, target_type, target_id, detail, business_unit) VALUES (?,?,?,?,?,?)",
            ("system", "stock_updated", "inventory", item["id"],
             f"{direction} {abs(quantity_change)}{item['unit']}，{reason or '無說明'}。{item['current_stock']}→{new_stock}",
             item["business_unit"]),
        )
        db.commit()

        alert = ""
        if new_stock <= item["min_stock"] and item["min_stock"] > 0:
            alert = f"\n⚠️ 庫存警報：{item['name']} 剩 {new_stock}{item['unit']}，低於安全庫存 {item['min_stock']}"

        guidance = ""
        if quantity_change > 0:
            if item["unit_cost"]:
                cost = abs(quantity_change) * item["unit_cost"]
                guidance = _build_guidance(next_steps=[
                    f"record_transaction(type='expense', amount={cost}, category='inventory_purchase', "
                    f"description='進貨 {item['name']} {quantity_change}{item['unit']} @ NT${item['unit_cost']:,.0f}')",
                    "問使用者：已付款(payment_status='paid')還是賒帳(payment_status='pending')？",
                ])
            else:
                guidance = _build_guidance(next_steps=[
                    f"record_transaction(type='expense', category='inventory_purchase', "
                    f"description='進貨 {item['name']} {quantity_change}{item['unit']}') — 需確認進貨金額",
                ])

        return f"✅ [{sku}] {item['name']}: {item['current_stock']} → {new_stock}{item['unit']}" + alert + guidance
    finally:
        db.close()


@mcp.tool()
def low_stock_alerts(business_unit: str = "") -> str:
    """列出所有低於安全庫存的品項。

    Args:
        business_unit: 篩選特定事業體（如 brand_c, brand_d），留空=全部
    """
    db = get_db()
    try:
        if business_unit:
            items = db.execute(
                "SELECT sku, name, current_stock, min_stock, unit, location, business_unit FROM inventory WHERE current_stock <= min_stock AND min_stock > 0 AND business_unit = ? ORDER BY (current_stock * 1.0 / min_stock)",
                (business_unit,),
            ).fetchall()
        else:
            items = db.execute(
                "SELECT sku, name, current_stock, min_stock, unit, location, business_unit FROM inventory WHERE current_stock <= min_stock AND min_stock > 0 ORDER BY (current_stock * 1.0 / min_stock)",
            ).fetchall()
        if not items:
            return "✅ 所有品項庫存正常，無警報。" + (f"（{business_unit}）" if business_unit else "")
        header = f"## ⚠️ 庫存警報（{len(items)} 項）" + (f"（{business_unit}）" if business_unit else "")
        lines = [header]
        for i in items:
            pct = round(i["current_stock"] / i["min_stock"] * 100) if i["min_stock"] else 0
            bu_label = f" [{i['business_unit']}]" if i["business_unit"] and not business_unit else ""
            lines.append(f"- 🔴 [{i['sku']}] {i['name']}{bu_label}: {i['current_stock']}/{i['min_stock']}{i['unit']} ({pct}%) {i['location'] or ''}")
        return "\n".join(lines)
    finally:
        db.close()


# ============================================================
# 審核管理（2 工具）
# ============================================================

@mcp.tool()
def create_approval(
    type: str,
    summary: str,
    detail: str = "",
    approver: str = "",
    requester: str = "",
    business_unit: str = "",
) -> str:
    """建立審核請求（HITL 人機協作）。

    Args:
        type: 審核類型（email, purchase, refund, announcement, other）
        summary: 摘要
        detail: 詳細內容（JSON 或純文字）
        approver: 指定審核人
        requester: 申請人名稱（留空=system）
        business_unit: 所屬事業體（如 brand_d, content），留空=不分
    """
    db = get_db()
    try:
        expires = (datetime.now() + timedelta(hours=72)).strftime("%Y-%m-%d %H:%M:%S")
        cursor = db.execute(
            "INSERT INTO approvals (type, summary, detail, requester, approver, business_unit, expires_at) VALUES (?,?,?,?,?,?,?)",
            (type, summary, detail or None, requester or "system", approver or None, business_unit or None, expires),
        )
        approval_id = cursor.lastrowid
        db.commit()
        bu_label = f"\n事業體：{business_unit}" if business_unit else ""
        bu_warn = _validate_business_unit(db, business_unit)
        return f"✅ 審核請求 #{approval_id} 已建立\n類型：{type}{bu_label}\n摘要：{summary}\n等待審核中（72 小時內有效）。請透過 LINE 通知主管。" + bu_warn
    finally:
        db.close()


@mcp.tool()
def resolve_approval(approval_id: int, decision: str, decided_by: str) -> str:
    """處理審核結果。

    Args:
        approval_id: 審核請求 ID
        decision: 決定 — approved | rejected
        decided_by: 審核人姓名
    """
    if decision not in ("approved", "rejected"):
        return "ERROR: decision 必須是 approved 或 rejected"

    db = get_db()
    try:
        approval = db.execute("SELECT * FROM approvals WHERE id = ? AND status = 'waiting'", (approval_id,)).fetchone()
        if not approval:
            # 也檢查是否已過期
            expired = db.execute("SELECT * FROM approvals WHERE id = ? AND status = 'expired'", (approval_id,)).fetchone()
            if expired:
                return f"ERROR: 審核 #{approval_id} 已過期，請重新建立審核請求"
            return f"ERROR: 找不到待審核項目 #{approval_id}"

        # 檢查是否已過期
        if approval["expires_at"]:
            try:
                expires = datetime.strptime(approval["expires_at"], "%Y-%m-%d %H:%M:%S")
                if datetime.now() > expires:
                    db.execute("UPDATE approvals SET status = 'expired' WHERE id = ?", (approval_id,))
                    db.commit()
                    return f"ERROR: 審核 #{approval_id} 已過期（{approval['expires_at']}），請重新建立審核請求"
            except (ValueError, TypeError):
                pass

        db.execute(
            "UPDATE approvals SET status = ?, approver = ?, decided_at = ? WHERE id = ?",
            (decision, decided_by, _now(), approval_id),
        )
        db.execute(
            "INSERT INTO interaction_log (actor, action, target_type, target_id, detail, business_unit) VALUES (?,?,?,?,?,?)",
            (decided_by, f"approval_{decision}", "approval", approval_id, approval["summary"],
             approval["business_unit"]),
        )
        db.commit()
        icon = "✅" if decision == "approved" else "❌"
        decision_label = "核准" if decision == "approved" else "駁回"
        msg = f"{icon} 審核 #{approval_id} 已{decision_label}（{decided_by}）"
        msg += f"\n類型：{approval['type']}\n摘要：{approval['summary']}"

        if approval["detail"]:
            if decision == "approved":
                try:
                    detail_obj = json.loads(approval["detail"])
                    resume_action = detail_obj.get("resume_action", "")
                    resume_params = detail_obj.get("resume_params", {})
                    then_desc = detail_obj.get("then", "")
                    if resume_action:
                        resume_params["approved_id"] = approval_id
                        params_str = ", ".join(f"{k}={repr(v)}" for k, v in resume_params.items())
                        steps = [f"{resume_action}({params_str})"]
                        if then_desc:
                            steps.append(then_desc)
                        msg += _build_guidance(next_steps=steps)
                except (json.JSONDecodeError, AttributeError):
                    msg += f"\n詳情：{approval['detail'][:200]}"
            else:
                msg += f"\n原始請求：{approval['detail'][:200]}"

        return msg
    finally:
        db.close()


# ============================================================
# 帳務管理（4 工具）— 框架，具體科目分類由各公司透過 business_rules 定義
# ============================================================

@mcp.tool()
def record_transaction(
    type: str,
    amount: float,
    category: str,
    description: str = "",
    transaction_date: str = "",
    related_customer_id: int = 0,
    related_order_id: int = 0,
    related_invoice: str = "",
    business_unit: str = "",
    payment_status: str = "paid",
    due_date: str = "",
    recorded_by: str = "",
    approved_id: int = 0,
) -> str:
    """記錄一筆收入或支出。

    Args:
        type: 類型 — income（收入）| expense（支出）
        amount: 金額（正數）
        category: 分類（如 sales_revenue, rent, supplies, salary, marketing, meals, transportation, other）
        description: 說明
        transaction_date: 交易日期（YYYY-MM-DD），空白=今天
        related_customer_id: 關聯客戶 ID（可選）
        related_order_id: 關聯訂單 ID（可選，用於追蹤預收款或訂單付款）
        related_invoice: 關聯發票號碼（可選）
        business_unit: 所屬事業體（如 product, design, content），留空=不分
        payment_status: 付款狀態 — paid（已付）| pending（待收/待付）| overdue（逾期）
        due_date: 帳期到期日（YYYY-MM-DD），B2B 應收應付用
        recorded_by: 記錄者
        approved_id: 已核准的審核 ID（繞過門檻檢查）
    """
    if type not in ("income", "expense"):
        return "ERROR: type 必須是 income 或 expense"
    if amount <= 0:
        return "ERROR: 金額必須是正數"

    if not transaction_date:
        transaction_date = _now()[:10]

    db = get_db()
    try:
        # 檢查是否超過審核門檻（已核准的 approved_id 可繞過）
        threshold = _get_approval_threshold(db, business_unit)
        threshold_bypassed = False
        if approved_id:
            approval = db.execute("SELECT status FROM approvals WHERE id = ? AND status = 'approved'", (approved_id,)).fetchone()
            if approval:
                threshold_bypassed = True
            else:
                return f"ERROR: 審核 #{approved_id} 不存在或尚未核准"

        if amount >= threshold and not threshold_bypassed:
            detail_json = json.dumps({
                "resume_action": "record_transaction",
                "resume_params": {
                    "type": type, "amount": amount, "category": category,
                    "description": description, "transaction_date": transaction_date,
                    "related_customer_id": related_customer_id,
                    "related_order_id": related_order_id,
                    "business_unit": business_unit,
                    "payment_status": payment_status, "due_date": due_date,
                },
                "then": "記帳完成後通知相關人員",
            }, ensure_ascii=False)
            bu_param = f", business_unit={business_unit!r}" if business_unit else ""
            return (
                f"⚠️ 金額 NT${amount:,.0f} 超過審核門檻 NT${threshold:,.0f}。"
                + _build_guidance(next_steps=[
                    f"create_approval(type={type!r}, summary='{type} NT${amount:,.0f} [{category}]', detail='{detail_json}'{bu_param})",
                    "LINE 通知主管審核",
                ])
            )

        if payment_status not in ("paid", "pending", "overdue"):
            payment_status = "paid"

        paid = amount if payment_status == "paid" else 0.0

        cursor = db.execute(
            """INSERT INTO transactions (type, amount, category, description, transaction_date,
               related_customer_id, related_order_id, related_invoice, business_unit, payment_status, due_date, paid_amount, recorded_by)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (type, amount, category, description or None, transaction_date,
             related_customer_id or None, related_order_id or None, related_invoice or None,
             business_unit or None, payment_status, due_date or None, paid, recorded_by or None),
        )
        txn_id = cursor.lastrowid
        db.execute(
            "INSERT INTO interaction_log (actor, action, target_type, target_id, detail, business_unit) VALUES (?,?,?,?,?,?)",
            (recorded_by or "system", "transaction_recorded", "transaction", txn_id,
             f"{type} NT${amount:,.0f} [{category}] {payment_status} {description or ''}", business_unit or None),
        )
        db.commit()

        icon = "💰" if type == "income" else "💸"
        status_label = {"paid": "已付", "pending": "待收付", "overdue": "逾期"}.get(payment_status, "")
        base_msg = f"✅ {icon} 帳目 #{txn_id}：{type} NT${amount:,.0f} [{category}] {status_label} {transaction_date}"

        guidance = ""
        if related_order_id and type == "income" and payment_status == "paid":
            order = db.execute(
                "SELECT status, total_amount FROM orders WHERE id = ?", (related_order_id,)
            ).fetchone()
            if order and order["status"] not in ("paid", "cancelled"):
                total_paid = db.execute(
                    "SELECT COALESCE(SUM(amount), 0) as s FROM transactions "
                    "WHERE related_order_id = ? AND type = 'income' AND payment_status = 'paid'",
                    (related_order_id,),
                ).fetchone()["s"]
                if total_paid >= order["total_amount"]:
                    guidance = _build_guidance(next_steps=[
                        f"update_order(order_id={related_order_id}, status='paid') — 訂單已全額收款",
                        "LINE 通知客戶：已收到款項，感謝！",
                    ])
                else:
                    remaining = order["total_amount"] - total_paid
                    guidance = _build_guidance(next_steps=[
                        f"訂單 #{related_order_id} 尚欠 NT${remaining:,.0f}，等待後續付款",
                    ])

        bu_warn = _validate_business_unit(db, business_unit)
        return base_msg + guidance + bu_warn
    finally:
        db.close()


@mcp.tool()
def list_transactions(
    start_date: str = "",
    end_date: str = "",
    type: str = "",
    category: str = "",
    business_unit: str = "",
    related_order_id: int = 0,
    limit: int = 30,
) -> str:
    """查詢收支記錄。

    Args:
        start_date: 起始日期（YYYY-MM-DD），空白=本月 1 號（指定 related_order_id 時不限日期）
        end_date: 結束日期（YYYY-MM-DD），空白=今天
        type: 篩選類型 — income | expense，空白=全部
        category: 篩選分類，空白=全部
        business_unit: 篩選事業體（留空=全部）
        related_order_id: 篩選關聯訂單 ID（0=不篩選）
        limit: 最多顯示幾筆
    """
    # 指定 related_order_id 時不限日期範圍（訂單可能跨月）
    has_date_filter = bool(start_date or end_date) or not related_order_id
    if has_date_filter:
        if not start_date:
            start_date = _now()[:8] + "01"  # 本月 1 號
        if not end_date:
            end_date = _now()[:10]

    db = get_db()
    try:
        if has_date_filter:
            query = "SELECT id, type, amount, category, description, transaction_date, recorded_by, payment_status, paid_amount, related_order_id, business_unit FROM transactions WHERE transaction_date BETWEEN ? AND ?"
            params: list = [start_date, end_date]
        else:
            query = "SELECT id, type, amount, category, description, transaction_date, recorded_by, payment_status, paid_amount, related_order_id, business_unit FROM transactions WHERE 1=1"
            params: list = []

        if type:
            query += " AND type = ?"
            params.append(type)
        if category:
            query += " AND category = ?"
            params.append(category)
        if business_unit:
            query += " AND business_unit = ?"
            params.append(business_unit)
        if related_order_id:
            query += " AND related_order_id = ?"
            params.append(related_order_id)

        query += " ORDER BY transaction_date DESC, id DESC LIMIT ?"
        params.append(limit)

        rows = db.execute(query, params).fetchall()
        if not rows:
            if related_order_id:
                return f"找不到訂單 #{related_order_id} 的相關帳目。"
            return f"在 {start_date} ~ {end_date} 期間沒有收支記錄。"

        total_income = sum(r["amount"] for r in rows if r["type"] == "income")
        total_expense = sum(r["amount"] for r in rows if r["type"] == "expense")

        date_label = f"{start_date} ~ {end_date}" if has_date_filter else "全部"
        lines = [f"## 💹 收支記錄（{date_label}，共 {len(rows)} 筆）"]
        lines.append(f"收入合計: NT${total_income:,.0f} | 支出合計: NT${total_expense:,.0f} | 淨額: NT${total_income - total_expense:,.0f}\n")

        for r in rows:
            icon = "💰" if r["type"] == "income" else "💸"
            status_tag = ""
            if r["payment_status"] == "pending":
                status_tag = f" ⏳待收付(已收{r['paid_amount']:,.0f})"
            elif r["payment_status"] == "overdue":
                status_tag = f" 🔴逾期(已收{r['paid_amount']:,.0f})"
            order_tag = f" 訂單#{r['related_order_id']}" if r["related_order_id"] else ""
            bu_tag = f" [{r['business_unit']}]" if r["business_unit"] and not business_unit else ""
            lines.append(f"- {icon} [#{r['id']}] {r['transaction_date']} NT${r['amount']:,.0f} [{r['category'] or '?'}]{bu_tag}{status_tag}{order_tag} {r['description'] or ''}")
        return "\n".join(lines)
    finally:
        db.close()


@mcp.tool()
def monthly_summary(year_month: str = "", business_unit: str = "") -> str:
    """月度收支彙總。

    Args:
        year_month: 年月（YYYY-MM），空白=本月
        business_unit: 篩選事業體（留空=全部合計）
    """
    if not year_month:
        year_month = _now()[:7]

    db = get_db()
    try:
        bu_filter = ""
        params: list = [f"{year_month}%"]
        if business_unit:
            bu_filter = " AND business_unit = ?"
            params.append(business_unit)

        rows = db.execute(
            f"""SELECT type, category, SUM(amount) as total, COUNT(*) as count
               FROM transactions
               WHERE transaction_date LIKE ?{bu_filter}
               GROUP BY type, category
               ORDER BY type, total DESC""",
            params,
        ).fetchall()

        if not rows:
            bu_label = f"（{business_unit}）" if business_unit else ""
            return f"{year_month}{bu_label} 沒有收支記錄。"

        income_rows = [r for r in rows if r["type"] == "income"]
        expense_rows = [r for r in rows if r["type"] == "expense"]
        total_income = sum(r["total"] for r in income_rows)
        total_expense = sum(r["total"] for r in expense_rows)

        bu_label = f"（{business_unit}）" if business_unit else ""
        lines = [f"## 📊 {year_month} 月度收支彙總{bu_label}"]
        lines.append(f"**收入**: NT${total_income:,.0f} | **支出**: NT${total_expense:,.0f} | **淨額**: NT${total_income - total_expense:,.0f}\n")

        if income_rows:
            lines.append("### 💰 收入明細")
            for r in income_rows:
                lines.append(f"- [{r['category'] or '未分類'}] NT${r['total']:,.0f}（{r['count']} 筆）")

        if expense_rows:
            lines.append("\n### 💸 支出明細")
            for r in expense_rows:
                lines.append(f"- [{r['category'] or '未分類'}] NT${r['total']:,.0f}（{r['count']} 筆）")

        # 如果沒指定 business_unit 且有多個事業體，附加分類摘要
        if not business_unit:
            bu_rows = db.execute(
                f"""SELECT business_unit, type, SUM(amount) as total
                    FROM transactions
                    WHERE transaction_date LIKE ? AND business_unit IS NOT NULL
                    GROUP BY business_unit, type
                    ORDER BY business_unit""",
                (f"{year_month}%",),
            ).fetchall()
            if bu_rows:
                lines.append("\n### 📂 事業體分類")
                bus = {}
                for r in bu_rows:
                    bu = r["business_unit"]
                    if bu not in bus:
                        bus[bu] = {"income": 0, "expense": 0}
                    bus[bu][r["type"]] = r["total"]
                for bu, vals in bus.items():
                    net = vals["income"] - vals["expense"]
                    lines.append(f"- **{bu}**: 收入 NT${vals['income']:,.0f} / 支出 NT${vals['expense']:,.0f} / 淨額 NT${net:,.0f}")
                # 未歸類（business_unit IS NULL）
                unassigned = db.execute(
                    "SELECT type, SUM(amount) as total FROM transactions WHERE transaction_date LIKE ? AND business_unit IS NULL GROUP BY type",
                    (f"{year_month}%",),
                ).fetchall()
                if unassigned:
                    ua = {r["type"]: r["total"] for r in unassigned}
                    ua_income = ua.get("income", 0)
                    ua_expense = ua.get("expense", 0)
                    lines.append(f"- **未歸類**: 收入 NT${ua_income:,.0f} / 支出 NT${ua_expense:,.0f} / 淨額 NT${ua_income - ua_expense:,.0f}")

        return "\n".join(lines)
    finally:
        db.close()


@mcp.tool()
def delete_transaction(transaction_id: int, reason: str, actor_user_id: str = "") -> str:
    """刪除一筆帳目（需填原因，會留下審計紀錄）。

    Args:
        transaction_id: 帳目 ID
        reason: 刪除原因（必填）
        actor_user_id: 操作者 LINE user_id（用於權限驗證，留空=系統呼叫，不驗證）
    """
    if not reason.strip():
        return "ERROR: 刪除帳目必須填寫原因"

    db = get_db()
    try:
        perm_err = _check_permission(db, actor_user_id, "manager")
        if perm_err:
            return perm_err
        txn = db.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,)).fetchone()
        if not txn:
            return f"ERROR: 找不到帳目 #{transaction_id}"

        db.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
        db.execute(
            "INSERT INTO interaction_log (actor, action, target_type, target_id, detail, business_unit) VALUES (?,?,?,?,?,?)",
            ("system", "transaction_deleted", "transaction", transaction_id,
             f"刪除 {txn['type']} NT${txn['amount']:,.0f} [{txn['category']}]，原因：{reason}", txn["business_unit"]),
        )
        db.commit()
        return f"✅ 帳目 #{transaction_id} 已刪除（原因：{reason}）"
    finally:
        db.close()


@mcp.tool()
def update_transaction(
    transaction_id: int,
    category: str = "",
    description: str = "",
    business_unit: str = "__SKIP__",
    payment_status: str = "",
    due_date: str = "",
    related_order_id: int = -1,
    related_customer_id: int = -1,
) -> str:
    """修正帳目欄位（不含金額，金額修正請刪除重建）。

    Args:
        transaction_id: 帳目 ID
        category: 新分類（留空=不改）
        description: 新說明（留空=不改）
        business_unit: 新事業體（'__SKIP__'=不改，空字串=清除）
        payment_status: 新付款狀態 paid|pending|overdue（留空=不改）
        due_date: 新到期日 YYYY-MM-DD（留空=不改）
        related_order_id: 關聯訂單 ID（-1=不改，0=清除）
        related_customer_id: 關聯客戶 ID（-1=不改，0=清除）
    """
    db = get_db()
    try:
        txn = db.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,)).fetchone()
        if not txn:
            return f"ERROR: 找不到帳目 #{transaction_id}"

        updates = []
        params: list = []
        detail_parts = []

        if category:
            updates.append("category = ?")
            params.append(category)
            detail_parts.append(f"分類→{category}")
        if description:
            updates.append("description = ?")
            params.append(description)
            detail_parts.append("說明已更新")
        if business_unit != "__SKIP__":
            updates.append("business_unit = ?")
            params.append(business_unit or None)
            detail_parts.append(f"事業體→{business_unit or '(清除)'}")
        if payment_status:
            if payment_status not in ("paid", "pending", "overdue"):
                return "ERROR: payment_status 必須是 paid, pending, overdue"
            updates.append("payment_status = ?")
            params.append(payment_status)
            if payment_status == "paid":
                updates.append("paid_amount = amount")
            detail_parts.append(f"狀態→{payment_status}")
        if due_date:
            updates.append("due_date = ?")
            params.append(due_date)
            detail_parts.append(f"到期日→{due_date}")
        if related_order_id != -1:
            updates.append("related_order_id = ?")
            params.append(related_order_id or None)
            detail_parts.append(f"訂單→#{related_order_id}" if related_order_id else "訂單→(清除)")
        if related_customer_id != -1:
            updates.append("related_customer_id = ?")
            params.append(related_customer_id or None)
            detail_parts.append(f"客戶→#{related_customer_id}" if related_customer_id else "客戶→(清除)")

        if not updates:
            return "沒有要更新的欄位。"

        _safe_update(db, "transactions",
                     {"category", "description", "business_unit", "payment_status", "paid_amount", "due_date", "related_order_id", "related_customer_id"},
                     updates, params, "id = ?", [transaction_id])
        db.execute(
            "INSERT INTO interaction_log (actor, action, target_type, target_id, detail, business_unit) VALUES (?,?,?,?,?,?)",
            ("system", "transaction_updated", "transaction", transaction_id, " | ".join(detail_parts), txn["business_unit"]),
        )
        db.commit()
        return f"✅ 帳目 #{transaction_id} 已更新（{', '.join(detail_parts)}）"
    finally:
        db.close()


# ============================================================
# 附件管理（2 工具）
# ============================================================

@mcp.tool()
def add_attachment(
    target_type: str,
    target_id: int,
    file_path: str,
    file_name: str = "",
    description: str = "",
    uploaded_by: str = "",
) -> str:
    """為任務、訂單、客戶等附加檔案（存路徑，不存檔案本身）。

    Args:
        target_type: 附加對象類型 — task | order | customer | inventory | rule
        target_id: 對象 ID
        file_path: 檔案路徑（本地路徑或 URL）
        file_name: 檔案名稱（空白=從路徑推斷）
        description: 說明
        uploaded_by: 上傳者
    """
    import os as _os
    if not file_name:
        file_name = _os.path.basename(file_path)

    # 推斷 file_type
    ext = _os.path.splitext(file_path)[1].lower()
    type_map = {
        ".jpg": "image", ".jpeg": "image", ".png": "image", ".gif": "image",
        ".pdf": "pdf", ".doc": "document", ".docx": "document",
        ".xls": "spreadsheet", ".xlsx": "spreadsheet",
        ".mp4": "video", ".m4a": "audio", ".mp3": "audio",
    }
    file_type = type_map.get(ext, "other")

    db = get_db()
    try:
        cursor = db.execute(
            "INSERT INTO attachments (target_type, target_id, file_path, file_type, file_name, description, uploaded_by) VALUES (?,?,?,?,?,?,?)",
            (target_type, target_id, file_path, file_type, file_name, description or None, uploaded_by or None),
        )
        db.commit()
        return f"✅ 附件 #{cursor.lastrowid} 已新增 → {target_type} #{target_id}（{file_name}）"
    finally:
        db.close()


@mcp.tool()
def list_attachments(target_type: str, target_id: int) -> str:
    """列出某對象的所有附件。

    Args:
        target_type: 對象類型 — task | order | customer | inventory | rule
        target_id: 對象 ID
    """
    db = get_db()
    try:
        attachments = db.execute(
            "SELECT id, file_path, file_type, file_name, description, uploaded_by, created_at FROM attachments WHERE target_type = ? AND target_id = ? ORDER BY created_at",
            (target_type, target_id),
        ).fetchall()

        if not attachments:
            return f"{target_type} #{target_id} 沒有附件。"

        type_icon = {"image": "🖼️", "pdf": "📄", "document": "📝", "spreadsheet": "📊", "video": "🎬", "audio": "🎵", "other": "📎"}
        lines = [f"## 📎 {target_type} #{target_id} 的附件（{len(attachments)} 個）"]
        for a in attachments:
            icon = type_icon.get(a["file_type"], "📎")
            lines.append(f"- {icon} [#{a['id']}] {a['file_name']} — {a['description'] or '無說明'}")
            lines.append(f"  路徑：{a['file_path']}")
        return "\n".join(lines)
    finally:
        db.close()


# ============================================================
# 應收應付（2 工具）
# ============================================================

@mcp.tool()
def check_overdue(business_unit: str = "") -> str:
    """檢查所有逾期帳款。自動判斷：到期日已過且未全額付清。

    Args:
        business_unit: 篩選特定事業體（如 brand_c, brand_d），留空=全部
    """
    db = get_db()
    try:
        today = _now()[:10]
        # 自動更新 pending → overdue
        db.execute(
            "UPDATE transactions SET payment_status = 'overdue' WHERE payment_status = 'pending' AND due_date IS NOT NULL AND due_date < ? AND paid_amount < amount",
            (today,),
        )
        db.commit()

        if business_unit:
            overdue = db.execute(
                """SELECT id, type, amount, paid_amount, category, description, due_date, related_customer_id, related_order_id, transaction_date, business_unit
                   FROM transactions WHERE payment_status = 'overdue' AND business_unit = ? ORDER BY due_date""",
                (business_unit,),
            ).fetchall()
        else:
            overdue = db.execute(
                """SELECT id, type, amount, paid_amount, category, description, due_date, related_customer_id, related_order_id, transaction_date, business_unit
                   FROM transactions WHERE payment_status = 'overdue' ORDER BY due_date""",
            ).fetchall()

        if not overdue:
            return "✅ 目前沒有逾期帳款。" + (f"（{business_unit}）" if business_unit else "")

        total_receivable = sum(r["amount"] - r["paid_amount"] for r in overdue if r["type"] == "income")
        total_payable = sum(r["amount"] - r["paid_amount"] for r in overdue if r["type"] == "expense")

        header = f"## 🔴 逾期帳款（{len(overdue)} 筆）" + (f"（{business_unit}）" if business_unit else "")
        lines = [header]
        if total_receivable > 0:
            lines.append(f"\n### 應收未收：NT${total_receivable:,.0f}")
            for r in overdue:
                if r["type"] == "income":
                    remaining = r["amount"] - r["paid_amount"]
                    days = (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(r["due_date"], "%Y-%m-%d")).days
                    bu_label = f" [{r['business_unit']}]" if r["business_unit"] and not business_unit else ""
                    order_tag = f" 訂單#{r['related_order_id']}" if r["related_order_id"] else ""
                    lines.append(f"- [#{r['id']}]{bu_label}{order_tag} NT${remaining:,.0f} 逾期 {days} 天 | {r['description'] or r['category']}")

        if total_payable > 0:
            lines.append(f"\n### 應付未付：NT${total_payable:,.0f}")
            for r in overdue:
                if r["type"] == "expense":
                    remaining = r["amount"] - r["paid_amount"]
                    days = (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(r["due_date"], "%Y-%m-%d")).days
                    bu_label = f" [{r['business_unit']}]" if r["business_unit"] and not business_unit else ""
                    order_tag = f" 訂單#{r['related_order_id']}" if r["related_order_id"] else ""
                    lines.append(f"- [#{r['id']}]{bu_label}{order_tag} NT${remaining:,.0f} 逾期 {days} 天 | {r['description'] or r['category']}")

        return "\n".join(lines)
    finally:
        db.close()


@mcp.tool()
def record_payment(transaction_id: int, amount: float, notes: str = "", actor_user_id: str = "") -> str:
    """記錄一筆付款（部分付款或全額付清）。

    Args:
        transaction_id: 帳目 ID
        amount: 本次付款金額
        notes: 備註
        actor_user_id: 操作者 LINE user_id（用於權限驗證，留空=系統呼叫，不驗證）
    """
    if amount <= 0:
        return "ERROR: 金額必須是正數"

    db = get_db()
    try:
        perm_err = _check_permission(db, actor_user_id, "manager")
        if perm_err:
            return perm_err
        txn = db.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,)).fetchone()
        if not txn:
            return f"ERROR: 找不到帳目 #{transaction_id}"

        new_paid = txn["paid_amount"] + amount
        remaining = txn["amount"] - new_paid

        if new_paid >= txn["amount"]:
            new_status = "paid"
            new_paid = txn["amount"]  # 不超付
            remaining = 0
        else:
            new_status = "pending"

        db.execute(
            "UPDATE transactions SET paid_amount = ?, payment_status = ? WHERE id = ?",
            (new_paid, new_status, transaction_id),
        )

        # v4: Bug #2 — 更新客戶已收款累計（僅 income 且關聯客戶時）
        if txn["type"] == "income" and txn["related_customer_id"]:
            db.execute(
                "UPDATE customers SET "
                "  total_paid = COALESCE(total_paid, 0) + ?, "
                "  last_payment_date = ? "
                "WHERE id = ?",
                (amount, _now()[:10], txn["related_customer_id"]),
            )

        db.execute(
            "INSERT INTO interaction_log (actor, action, target_type, target_id, detail, business_unit) VALUES (?,?,?,?,?,?)",
            ("system", "payment_recorded", "transaction", transaction_id,
             f"付款 NT${amount:,.0f}，累計 NT${new_paid:,.0f}/{txn['amount']:,.0f}。{notes}",
             txn["business_unit"]),
        )
        db.commit()

        guidance = ""
        if new_status == "paid" and txn["related_order_id"]:
            order = db.execute(
                "SELECT status FROM orders WHERE id = ?", (txn["related_order_id"],)
            ).fetchone()
            if order and order["status"] not in ("paid", "cancelled"):
                guidance = _build_guidance(next_steps=[
                    f"update_order(order_id={txn['related_order_id']}, status='paid') — 訂單全額收款完成",
                    "LINE 通知客戶：已收到款項，感謝！",
                ])
        elif new_status != "paid" and txn["related_order_id"]:
            guidance = _build_guidance(next_steps=[
                f"訂單 #{txn['related_order_id']} 尚欠 NT${remaining:,.0f}",
            ])

        if new_status == "paid":
            return f"✅ 帳目 #{transaction_id} 已全額付清（NT${txn['amount']:,.0f}）" + guidance
        else:
            return f"✅ 帳目 #{transaction_id} 已收到 NT${amount:,.0f}，剩餘 NT${remaining:,.0f}" + guidance
    finally:
        db.close()


# ============================================================
# 訂單管理（5 工具）
# ============================================================

@mcp.tool()
def create_order(customer_id: int, items_json: str, notes: str = "", business_unit: str = "", created_by: str = "", approved_id: int = 0) -> str:
    """建立訂單。

    Args:
        customer_id: 客戶 ID
        items_json: 訂單品項 JSON，格式：[{"sku":"A200","name":"特殊零件","qty":10,"price":350}]
        notes: 備註
        business_unit: 所屬事業體（如 product, design, content），留空=不分
        created_by: 建立者
        approved_id: 已核准的審核 ID（繞過門檻檢查）
    """
    db = get_db()
    try:
        # 驗證客戶存在
        customer = db.execute(
            "SELECT name, payment_terms, discount_rate FROM customers WHERE id = ?", (customer_id,)
        ).fetchone()
        if not customer:
            return f"ERROR: 找不到客戶 #{customer_id}"

        # 解析 items
        try:
            items = json.loads(items_json) if isinstance(items_json, str) else items_json
        except json.JSONDecodeError:
            return "ERROR: items_json 格式錯誤，需要 JSON 陣列"

        total = sum(item.get("qty", 0) * item.get("price", 0) for item in items)

        # 套用客戶折扣率（先查事業體專屬條件，fallback 到客戶預設）
        terms_info = _get_customer_terms(db, customer_id, business_unit)
        discount = terms_info["discount_rate"]
        if discount > 0:
            total = round(total * (1 - discount))

        # 檢查審核門檻（已核准的 approved_id 可繞過）
        threshold = _get_approval_threshold(db, business_unit)
        threshold_bypassed = False
        if approved_id:
            approval = db.execute("SELECT status FROM approvals WHERE id = ? AND status = 'approved'", (approved_id,)).fetchone()
            if approval:
                threshold_bypassed = True
            else:
                return f"ERROR: 審核 #{approved_id} 不存在或尚未核准"
        if total >= threshold and not threshold_bypassed:
            items_str = "\n".join(f"  - {i.get('name', i.get('sku', '?'))} × {i.get('qty', 0)} @ NT${i.get('price', 0):,.0f}" for i in items)
            detail_json = json.dumps({
                "resume_action": "create_order",
                "resume_params": {
                    "customer_id": customer_id, "items_json": items_json,
                    "notes": notes, "business_unit": business_unit, "created_by": created_by,
                },
                "then": "訂單建立後通知客戶和倉管",
            }, ensure_ascii=False)
            discount_note = f"（已含折扣 {discount*100:.0f}%）" if discount > 0 else ""
            return (
                f"⚠️ 訂單金額 NT${total:,.0f}{discount_note} 超過審核門檻 NT${threshold:,.0f}，需先核准。\n"
                f"客戶：{customer['name']}\n品項：\n{items_str}"
                + _build_guidance(next_steps=[
                    f"create_approval(type='purchase', summary='建立訂單：{customer['name']} NT${total:,.0f}', detail='{detail_json}')",
                    "LINE 通知主管審核",
                    "主管核准後再執行 create_order",
                ])
            )

        cursor = db.execute(
            "INSERT INTO orders (customer_id, total_amount, items, business_unit, notes, created_by, payment_terms, discount_applied) VALUES (?,?,?,?,?,?,?,?)",
            (customer_id, total, json.dumps(items, ensure_ascii=False), business_unit or None, notes or None, created_by or None,
             terms_info["payment_terms"], discount),
        )
        order_id = cursor.lastrowid

        # v4: Bug #4 — 預留庫存（排單時預留，fulfill_order 才真正扣 current_stock）
        reservation_notes = []
        for item in items:
            sku = (item.get("sku") or "").strip()
            qty = int(item.get("qty") or 0)
            if not sku or qty <= 0:
                continue
            inv = _find_inventory(db, sku, business_unit or "")
            if not inv:
                reservation_notes.append(f"SKU={sku} 不在庫存（跳過預留）")
                continue
            available = (inv["current_stock"] or 0) - (inv["reserved"] or 0)
            if available < qty:
                reservation_notes.append(
                    f"{inv['name']}({sku}) 可用 {available} 不足 {qty}（仍預留，出貨時會再驗）"
                )
            db.execute(
                "UPDATE inventory SET reserved = COALESCE(reserved, 0) + ? WHERE id = ?",
                (qty, inv["id"]),
            )

        # v4: Bug #2 — 更新客戶下單累計（total_ordered / last_order_date）
        db.execute(
            "UPDATE customers SET "
            "  total_ordered = COALESCE(total_ordered, 0) + ?, "
            "  last_order_date = ? "
            "WHERE id = ?",
            (total, _now()[:10], customer_id),
        )

        db.execute(
            "INSERT INTO interaction_log (actor, action, target_type, target_id, detail, business_unit) VALUES (?,?,?,?,?,?)",
            (created_by or "system", "order_created", "order", order_id,
             f"客戶 {customer['name']}，金額 NT${total:,.0f}，{len(items)} 項品項", business_unit or None),
        )
        db.commit()

        items_str = "\n".join(f"  - {i.get('name', i.get('sku', '?'))} × {i.get('qty', 0)} @ NT${i.get('price', 0):,.0f}" for i in items)
        base_msg = f"✅ 訂單 #{order_id} 已建立\n客戶：{customer['name']}\n金額：NT${total:,.0f}\n品項：\n{items_str}"

        # 建構下一步指引
        terms = terms_info["payment_terms"]

        next_steps = []

        # 解析 deposit 比例（支援 deposit_30, deposit_50 等格式）
        deposit_pct = 0.0
        if terms.startswith("deposit_"):
            try:
                deposit_pct = int(terms.split("_")[1]) / 100.0
            except (IndexError, ValueError):
                deposit_pct = 0.3  # fallback

        terms_actions = {
            "prepaid": f"通知客戶匯款 NT${total:,.0f}，收到後 record_transaction(type='income', amount={total}, category='sales_revenue', related_order_id={order_id}, payment_status='paid')",
            "net30": f"update_order(order_id={order_id}, status='confirmed') → 進入品檢流程",
            "net60": f"update_order(order_id={order_id}, status='confirmed') → 進入品檢流程",
            "cod": f"update_order(order_id={order_id}, status='confirmed') → 進入品檢流程",
        }
        if deposit_pct > 0:
            deposit_amt = round(total * deposit_pct)
            terms_actions[terms] = (
                f"通知客戶付 {int(deposit_pct*100)}% 訂金 NT${deposit_amt:,.0f}，"
                f"收到後 record_transaction(type='income', amount={deposit_amt}, related_order_id={order_id}, payment_status='paid')"
            )
        default_action = f"update_order(order_id={order_id}, status='confirmed')"
        next_steps.append(f"付款條件 {terms}：{terms_actions.get(terms, default_action)}")
        next_steps.append(f"LINE 通知客戶：訂單 #{order_id} 已建立，金額 NT${total:,.0f}")
        next_steps.append(f"LINE 通知倉管/業務：新訂單 #{order_id}，請準備備貨")

        warnings = []
        bu_warn = _validate_business_unit(db, business_unit)
        if bu_warn:
            warnings.append(bu_warn.strip())
        if discount > 0:
            warnings.append(f"已套用客戶折扣率 {discount*100:.0f}%")
        # v4: 反映 Bug #4 新行為（預留，不直接扣 current_stock）
        reserved_qty = sum(int(i.get("qty") or 0) for i in items if i.get("sku"))
        if reserved_qty > 0:
            warnings.append(f"已為訂單預留 {reserved_qty} 單位庫存（出貨時才扣 current_stock）")
        if reservation_notes:
            warnings.extend(reservation_notes)
        guidance = _build_guidance(next_steps=next_steps, warnings=warnings)

        return base_msg + guidance
    finally:
        db.close()


@mcp.tool()
def get_order(order_id: int) -> str:
    """查看單筆訂單完整資訊。

    Args:
        order_id: 訂單 ID
    """
    db = get_db()
    try:
        order = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if not order:
            return f"ERROR: 找不到訂單 #{order_id}"

        customer = db.execute("SELECT name FROM customers WHERE id = ?", (order["customer_id"],)).fetchone()
        customer_name = customer["name"] if customer else "未知"

        status_icon = {"pending": "⏳", "confirmed": "✅", "shipped": "🚚", "delivered": "📦", "paid": "💰", "cancelled": "❌", "returned": "↩️"}.get(order["status"], "")

        items = _parse_items_json(order["items"])
        items_str = "\n".join(f"  - {i.get('name', i.get('sku', '?'))} × {i.get('qty', 0)} @ NT${i.get('price', 0):,.0f}" for i in items)

        qc_info = ""
        if order["qc_status"] != "pending":
            qc_icon = {"passed": "✅", "failed": "❌", "partial": "⚠️"}.get(order["qc_status"], "")
            qc_info = (
                f"\n- 🔍 QC：{qc_icon} {order['qc_status']}"
                f"{' — ' + order['qc_notes'] if order['qc_notes'] else ''}"
                f"{' by ' + order['qc_checked_by'] if order['qc_checked_by'] else ''}"
            )

        logistics = ""
        if order["driver"] or order["estimated_delivery"] or order["delivered_at"]:
            logistics = (
                f"\n- 🚛 物流：\n"
                f"  - 司機：{order['driver'] or '未指派'}\n"
                f"  - 預計送達：{order['estimated_delivery'] or '未設定'}\n"
                f"  - 實際送達：{order['delivered_at'] or '尚未送達'}"
            )

        terms_str = ""
        if order["payment_terms"]:
            discount_str = f" 折扣 {order['discount_applied']*100:.0f}%" if order["discount_applied"] else ""
            terms_str = f"\n- 付款條件：{order['payment_terms']}{discount_str}"

        return (
            f"## 訂單 #{order_id} {status_icon}\n"
            f"- 客戶：{customer_name}\n"
            f"- 狀態：{order['status']}\n"
            f"- 金額：NT${order['total_amount']:,.0f}"
            f"{terms_str}\n"
            f"- 品項：\n{items_str}"
            f"{qc_info}"
            f"{logistics}\n"
            f"- 備註：{order['notes'] or '無'}\n"
            f"- 建立：{order['created_at']}\n"
            f"- 更新：{order['updated_at']}"
        )
    finally:
        db.close()


@mcp.tool()
def update_order(order_id: int, status: str = "", notes: str = "", driver: str = "", estimated_delivery: str = "") -> str:
    """更新訂單狀態、物流資訊或備註。狀態轉換受限：取消/退貨用 cancel_order，出貨用 fulfill_order。

    Args:
        order_id: 訂單 ID
        status: 新狀態 — confirmed | delivered | paid（其他轉換請用專門工具）
        notes: 更新備註
        driver: 配送司機/物流人員
        estimated_delivery: 預計送達日期（YYYY-MM-DD）
    """
    db = get_db()
    try:
        order = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if not order:
            return f"ERROR: 找不到訂單 #{order_id}"

        updates = ["updated_at = ?"]
        params = [_now()]

        if status:
            cur = order["status"]
            # 狀態轉換驗證
            if status in ("cancelled", "returned"):
                return (
                    f"ERROR: 請使用 cancel_order(order_id={order_id}, reason='...'"
                    + (", cancel_type='returned'" if status == "returned" else "")
                    + ") 來處理取消/退貨（會自動回補庫存、作廢帳款）"
                )
            if status == "shipped":
                return f"ERROR: 請使用 fulfill_order(order_id={order_id}) 來出貨（會自動扣庫存、建立應收帳款）"
            allowed = _ORDER_TRANSITIONS.get(cur, set())
            if status not in allowed:
                hint = f"目前狀態 {cur} 可轉換為：{', '.join(allowed)}" if allowed else f"目前狀態 {cur} 無法透過 update_order 轉換"
                return f"ERROR: 訂單 #{order_id} 無法從 {cur} 轉為 {status}。{hint}"
            updates.append("status = ?")
            params.append(status)
            if status == "delivered":
                updates.append("delivered_at = ?")
                params.append(_now())
        if notes:
            updates.append("notes = ?")
            params.append(notes)
        if driver:
            updates.append("driver = ?")
            params.append(driver)
        if estimated_delivery:
            updates.append("estimated_delivery = ?")
            params.append(estimated_delivery)

        _safe_update(db, "orders",
                     {"updated_at", "status", "delivered_at", "notes", "driver", "estimated_delivery"},
                     updates, params, "id = ?", [order_id])

        detail_parts = []
        if status:
            detail_parts.append(f"狀態: {order['status']}→{status}")
        if driver:
            detail_parts.append(f"司機: {driver}")
        if estimated_delivery:
            detail_parts.append(f"預計送達: {estimated_delivery}")

        db.execute(
            "INSERT INTO interaction_log (actor, action, target_type, target_id, detail, business_unit) VALUES (?,?,?,?,?,?)",
            ("system", "order_updated", "order", order_id, " | ".join(detail_parts) or "備註更新", order["business_unit"]),
        )
        db.commit()
        return f"✅ 訂單 #{order_id} 已更新" + (f"（{', '.join(detail_parts)}）" if detail_parts else "")
    finally:
        db.close()


@mcp.tool()
def list_orders(customer_id: int = 0, status: str = "", business_unit: str = "", limit: int = 20) -> str:
    """列出訂單。

    Args:
        customer_id: 篩選客戶（0=全部）
        status: 篩選狀態（空白=全部）
        business_unit: 篩選事業體（留空=全部）
        limit: 最多顯示幾筆
    """
    db = get_db()
    try:
        query = "SELECT o.*, c.name as customer_name FROM orders o LEFT JOIN customers c ON o.customer_id = c.id WHERE 1=1"
        params: list = []
        if customer_id:
            query += " AND o.customer_id = ?"
            params.append(customer_id)
        if status:
            query += " AND o.status = ?"
            params.append(status)
        if business_unit:
            query += " AND o.business_unit = ?"
            params.append(business_unit)
        query += " ORDER BY o.created_at DESC LIMIT ?"
        params.append(limit)

        orders = db.execute(query, params).fetchall()
        if not orders:
            return "沒有符合條件的訂單。"

        status_icon = {"pending": "⏳", "confirmed": "✅", "shipped": "🚚", "delivered": "📦", "paid": "💰", "cancelled": "❌", "returned": "↩️"}
        lines = [f"## 📋 訂單列表（{len(orders)} 筆）"]
        for o in orders:
            icon = status_icon.get(o["status"], "")
            lines.append(f"- {icon} [#{o['id']}] {o['customer_name'] or '?'} | NT${o['total_amount']:,.0f} | {o['status']} | {o['created_at'][:10]}")
        return "\n".join(lines)
    finally:
        db.close()


@mcp.tool()
def qc_order(order_id: int, result: str, notes: str = "", checked_by: str = "") -> str:
    """品質檢查（QC）。出貨前必須通過 QC。

    Args:
        order_id: 訂單 ID
        result: 檢查結果 — passed（通過）| failed（不合格）| partial（部分合格）
        notes: QC 備註（瑕疵描述、檢查項目等）
        checked_by: 檢查人員
    """
    if result not in ("passed", "failed", "partial"):
        return "ERROR: result 必須是 passed, failed, 或 partial"

    db = get_db()
    try:
        order = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if not order:
            return f"ERROR: 找不到訂單 #{order_id}"
        if order["status"] not in ("confirmed", "shipped"):
            if order["status"] == "pending":
                return f"ERROR: 訂單 #{order_id} 尚未確認，請先 update_order(order_id={order_id}, status='confirmed') 後再品檢。"
            return f"ERROR: 訂單 #{order_id} 狀態是 {order['status']}，無法進行品檢（需要 confirmed 或 shipped 狀態）"

        db.execute(
            "UPDATE orders SET qc_status = ?, qc_notes = ?, qc_checked_by = ?, qc_checked_at = ?, updated_at = ? WHERE id = ?",
            (result, notes or None, checked_by or None, _now(), _now(), order_id),
        )
        db.execute(
            "INSERT INTO interaction_log (actor, action, target_type, target_id, detail, business_unit) VALUES (?,?,?,?,?,?)",
            (checked_by or "system", "qc_completed", "order", order_id, f"QC {result}: {notes or '無備註'}", order["business_unit"]),
        )
        db.commit()

        icon = {"passed": "✅", "failed": "❌", "partial": "⚠️"}[result]
        # 顯示前次 QC 紀錄（如有）
        prev_qc = ""
        if order["qc_status"] != "pending":
            prev_icon = {"passed": "✅", "failed": "❌", "partial": "⚠️"}.get(order["qc_status"], "")
            prev_qc = f"\n📋 前次 QC：{prev_icon} {order['qc_status']}"
            if order["qc_notes"]:
                prev_qc += f"（{order['qc_notes']}）"
            if order["qc_checked_by"]:
                prev_qc += f" by {order['qc_checked_by']}"
        msg = f"{icon} 訂單 #{order_id} QC {result}{prev_qc}"
        if result == "passed":
            msg += _build_guidance(next_steps=[f"fulfill_order(order_id={order_id})"])
        elif result == "failed":
            msg += _build_guidance(next_steps=[
                "通知主管處理品質問題",
                f"LINE 通知相關人員：訂單 #{order_id} QC 不合格" + (f"，原因：{notes}" if notes else ""),
            ])
        elif result == "partial":
            msg += _build_guidance(next_steps=[
                "列出合格/不合格品項，詢問主管是否部分出貨",
                f"主管核准部分出貨 → fulfill_order(order_id={order_id})",
            ])
        return msg
    finally:
        db.close()


@mcp.tool()
def fulfill_order(order_id: int, partial_items_json: str = "") -> str:
    """確認訂單出貨：自動扣庫存 + 建立應收帳款。

    Args:
        order_id: 訂單 ID
        partial_items_json: 部分出貨品項 JSON（僅 QC partial 時使用）。格式：[{"sku":"A001","qty":5}, ...]。留空=出貨全部品項。
    """
    db = get_db()
    try:
        order = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if not order:
            return f"ERROR: 找不到訂單 #{order_id}"
        if order["status"] not in ("confirmed", "shipped"):
            if order["status"] == "pending":
                return f"ERROR: 訂單 #{order_id} 尚未確認，請先 update_order(order_id={order_id}, status='confirmed') 確認訂單，再進行品檢和出貨。"
            return f"ERROR: 訂單 #{order_id} 狀態是 {order['status']}，無法出貨"

        is_followup = order["status"] == "shipped"
        is_partial = False

        if is_followup:
            # 補出貨：之前已部分出貨，現在出剩餘品項
            if not partial_items_json:
                items_list = _parse_items_json(order["items"])
                unshipped = [{"sku": i.get("sku", ""), "qty": i.get("qty", 0) - i.get("shipped_qty", 0)}
                             for i in items_list if i.get("qty", 0) - i.get("shipped_qty", 0) > 0]
                if not unshipped:
                    return f"ERROR: 訂單 #{order_id} 所有品項都已出貨完畢。"
                items_hint = json.dumps(unshipped, ensure_ascii=False)
                return (
                    f"⚠️ 訂單 #{order_id} 已部分出貨，需指定本次要補出的品項。\n"
                    f"fulfill_order(order_id={order_id}, partial_items_json='...')\n"
                    f"未出貨品項：{items_hint}"
                )
            is_partial = True
        elif order["qc_status"] == "partial":
            if not partial_items_json:
                items_list = _parse_items_json(order["items"])
                items_hint = json.dumps([{"sku": i.get("sku", ""), "qty": i.get("qty", 0)} for i in items_list], ensure_ascii=False)
                return (
                    f"⚠️ 訂單 #{order_id} QC 狀態為 partial（部分合格）。\n"
                    f"請指定要出貨的品項：fulfill_order(order_id={order_id}, partial_items_json='[{{\"sku\":\"...\",\"qty\":...}}, ...]')\n"
                    f"原始品項參考：{items_hint}\n"
                    f"QC 備註：{order['qc_notes'] or '無'}"
                )
            is_partial = True
        elif order["qc_status"] != "passed":
            return f"ERROR: 訂單 #{order_id} 尚未通過品質檢查（目前 QC 狀態: {order['qc_status']}）。請先用 qc_order 工具完成 QC。"

        # 使用訂單建立時凍結的付款條件（避免客戶條件變更影響已建訂單）
        customer = db.execute("SELECT * FROM customers WHERE id = ?", (order["customer_id"],)).fetchone()
        terms = order["payment_terms"]
        if not terms:
            # 向後相容：舊訂單沒有 payment_terms，fallback 到客戶當前條件
            terms_info = _get_customer_terms(db, order["customer_id"], order["business_unit"] or "")
            terms = terms_info["payment_terms"]

        # 決定出貨品項
        if is_partial:
            try:
                ship_items = json.loads(partial_items_json) if isinstance(partial_items_json, str) else partial_items_json
            except json.JSONDecodeError:
                return "ERROR: partial_items_json 格式錯誤，需要 JSON 陣列"
        else:
            ship_items = _parse_items_json(order["items"])

        # 計算出貨金額（部分出貨時按比例分攤訂單總額，確保折扣正確套用）
        if is_partial:
            all_items = _parse_items_json(order["items"])
            all_items_map = {i.get("sku", ""): i for i in all_items}
            # 計算原始品項總額（未折扣）和本次出貨品項原始總額
            full_raw_total = sum(i.get("price", 0) * i.get("qty", 0) for i in all_items) or 1
            ship_raw_total = 0.0
            for si in ship_items:
                orig = all_items_map.get(si.get("sku", ""))
                if orig and orig.get("price"):
                    ship_raw_total += orig["price"] * si.get("qty", 0)
            # 按比例分攤（order.total_amount 已含折扣），確保部分出貨金額正確
            if ship_raw_total > 0:
                ship_total = round(order["total_amount"] * (ship_raw_total / full_raw_total))
            else:
                ship_total = order["total_amount"]  # fallback if no price info
        else:
            ship_total = order["total_amount"]

        if terms == "prepaid":
            paid = db.execute(
                "SELECT COALESCE(SUM(amount), 0) as total FROM transactions WHERE related_order_id = ? AND type = 'income' AND payment_status = 'paid'",
                (order_id,),
            ).fetchone()["total"]
            if paid < ship_total:
                return f"ERROR: 訂單 #{order_id} 客戶付款條件是 prepaid，需先收到全額 NT${ship_total:,.0f}（目前已收 NT${paid:,.0f}）"

        elif terms.startswith("deposit_"):
            try:
                deposit_pct = int(terms.split("_")[1]) / 100.0
            except (IndexError, ValueError):
                deposit_pct = 0.3
            paid = db.execute(
                "SELECT COALESCE(SUM(amount), 0) as total FROM transactions WHERE related_order_id = ? AND type = 'income' AND payment_status = 'paid'",
                (order_id,),
            ).fetchone()["total"]
            required = ship_total * deposit_pct
            if paid < required:
                return f"ERROR: 訂單 #{order_id} 客戶付款條件是 {terms}，需先收到 {int(deposit_pct*100)}% 訂金 NT${required:,.0f}（目前已收 NT${paid:,.0f}）"

        errors = []
        deductions = []  # (inventory_id, sku, qty, name)
        order_bu = order["business_unit"] or ""

        # 檢查出貨品項庫存（精確匹配 BU，fallback 僅限無歸屬庫存）
        for item in ship_items:
            sku = item.get("sku", "")
            qty = item.get("qty", 0)
            if not sku or qty <= 0:
                continue
            inv = _find_inventory(db, sku, order_bu)
            if not inv:
                errors.append(f"找不到 SKU={sku}")
            elif inv["current_stock"] < qty:
                errors.append(f"{inv['name']}({sku}) 庫存 {inv['current_stock']} 不足，需要 {qty}")
            else:
                deductions.append((inv["id"], sku, qty, inv["name"]))

        if errors:
            return "❌ 無法出貨，庫存不足：\n" + "\n".join(f"- {e}" for e in errors)

        # 扣庫存（用 inventory.id 精確扣減，避免跨事業體誤扣）
        # v4: Bug #4 — 同步扣減 reserved（釋放在 create_order 時做的預留）
        for inv_id, sku, qty, name in deductions:
            db.execute(
                "UPDATE inventory SET "
                "  current_stock = current_stock - ?, "
                "  reserved = MAX(COALESCE(reserved, 0) - ?, 0) "
                "WHERE id = ?",
                (qty, qty, inv_id),
            )

        # 更新訂單狀態
        db.execute("UPDATE orders SET status = 'shipped', updated_at = ? WHERE id = ?", (_now(), order_id))

        # 部分出貨時更新 items 的 shipped_qty（累加，支援多次補出貨）
        if is_partial:
            all_items = _parse_items_json(order["items"])
            shipped_skus = {si.get("sku"): si.get("qty", 0) for si in ship_items}
            for ai in all_items:
                sku = ai.get("sku", "")
                if sku in shipped_skus:
                    ai["shipped_qty"] = ai.get("shipped_qty", 0) + shipped_skus[sku]
            note_label = "[補出貨]" if is_followup else "[部分出貨] 僅出貨合格品項"
            db.execute("UPDATE orders SET items = ?, notes = COALESCE(notes || '\n', '') || ? WHERE id = ?",
                       (json.dumps(all_items, ensure_ascii=False), note_label, order_id))

        # 建立應收帳款（根據付款條件設 due_date）
        today = datetime.now()
        due_date = None
        if terms == "net30":
            due_date = (today + timedelta(days=30)).strftime("%Y-%m-%d")
        elif terms == "net60":
            due_date = (today + timedelta(days=60)).strftime("%Y-%m-%d")
        elif terms == "cod":
            due_date = order["estimated_delivery"] or (today + timedelta(days=7)).strftime("%Y-%m-%d")
        # prepaid/deposit 已收全額/部分，應收 = 剩餘金額
        receivable = ship_total
        already_paid = 0.0
        if terms == "prepaid" or terms.startswith("deposit_"):
            already_paid = db.execute(
                "SELECT COALESCE(SUM(amount), 0) as total FROM transactions WHERE related_order_id = ? AND type = 'income' AND payment_status = 'paid'",
                (order_id,),
            ).fetchone()["total"]
            receivable = ship_total - already_paid

        if receivable > 0:
            desc_suffix = "（部分出貨）" if is_partial else ""
            db.execute(
                """INSERT INTO transactions (type, amount, category, description, transaction_date,
                   related_customer_id, related_order_id, payment_status, paid_amount, due_date, recorded_by, business_unit)
                   VALUES ('income', ?, 'sales_revenue', ?, ?, ?, ?, 'pending', 0, ?, 'system', ?)""",
                (receivable, f"訂單 #{order_id} {customer['name'] if customer else ''}{desc_suffix}",
                 _now()[:10], order["customer_id"], order_id, due_date, order["business_unit"]),
            )

        action_label = "order_partial_fulfilled" if is_partial else "order_fulfilled"
        db.execute(
            "INSERT INTO interaction_log (actor, action, target_type, target_id, detail, business_unit) VALUES (?,?,?,?,?,?)",
            ("system", action_label, "order", order_id,
             f"出貨 {len(deductions)} 項品項，應收 NT${ship_total:,.0f}", order["business_unit"]),
        )

        # v4: Bug #2 — 更新客戶已出貨累計
        # total_fulfilled = 新語意「已認列營收」；total_purchases + last_purchase_date 保留以向後相容
        if order["customer_id"]:
            db.execute(
                "UPDATE customers SET "
                "  total_fulfilled = COALESCE(total_fulfilled, 0) + ?, "
                "  total_purchases = COALESCE(total_purchases, 0) + ?, "
                "  last_fulfilled_date = ?, "
                "  last_purchase_date = ? "
                "WHERE id = ?",
                (ship_total, ship_total, _now()[:10], _now()[:10], order["customer_id"]),
            )
        db.commit()

        # 查扣庫存後的低庫存警報
        low_stock_items = []
        for inv_id, sku, qty, name in deductions:
            inv_after = db.execute(
                "SELECT current_stock, min_stock, unit FROM inventory WHERE id = ?", (inv_id,)
            ).fetchone()
            if inv_after and inv_after["min_stock"] > 0 and inv_after["current_stock"] <= inv_after["min_stock"]:
                low_stock_items.append(
                    f"{name}({sku}) 剩 {inv_after['current_stock']}{inv_after['unit']}，安全庫存 {inv_after['min_stock']}"
                )

        deduct_str = "\n".join(f"  - {name}({sku}) -{qty}" for inv_id, sku, qty, name in deductions)
        customer_name = customer["name"] if customer else ""
        partial_label = "（部分出貨）" if is_partial else ""

        auto_done = [
            f"庫存已扣減（{len(deductions)} 項品項）{partial_label}",
            "訂單狀態 → shipped",
        ]
        if receivable > 0:
            auto_done.append(f"應收帳款 NT${receivable:,.0f} 已建立（{terms}）")

        next_steps = [
            f"update_order(order_id={order_id}, driver='司機名或物流單號', estimated_delivery='YYYY-MM-DD')",
            f"LINE 通知客戶 {customer_name}：訂單 #{order_id} 已出貨{partial_label}",
        ]
        if is_partial:
            next_steps.append("處理不合格品項：退回供應商 / 報廢 / 重新品檢")
        if low_stock_items:
            next_steps.append("庫存警報需處理：\n   " + "\n   ".join(low_stock_items))

        warnings = [
            "不要再手動 update_stock（已自動扣庫存）",
            "不要再手動 record_transaction（已自動建應收帳款）",
        ]

        guidance = _build_guidance(auto_done=auto_done, next_steps=next_steps, warnings=warnings)

        return (
            f"✅ 訂單 #{order_id} 已出貨{partial_label}\n"
            f"庫存扣減：\n{deduct_str}\n"
            f"應收帳款：NT${receivable:,.0f}（{terms}）"
            + guidance
        )
    finally:
        db.close()


@mcp.tool()
def cancel_order(order_id: int, reason: str, cancel_type: str = "cancelled", actor_user_id: str = "") -> str:
    """取消或退貨訂單。自動回補庫存（若已出貨）並作廢應收帳款。

    Args:
        order_id: 訂單 ID
        reason: 取消/退貨原因（必填）
        cancel_type: cancelled（取消）| returned（退貨）
        actor_user_id: 操作者 LINE user_id（用於權限驗證，留空=系統呼叫，不驗證）
    """
    if not reason.strip():
        return "ERROR: 必須提供取消/退貨原因"
    if cancel_type not in ("cancelled", "returned"):
        return "ERROR: cancel_type 必須是 cancelled 或 returned"

    db = get_db()
    try:
        perm_err = _check_permission(db, actor_user_id, "manager")
        if perm_err:
            return perm_err
        order = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if not order:
            return f"ERROR: 找不到訂單 #{order_id}"
        if order["status"] in ("cancelled", "returned"):
            return f"ERROR: 訂單 #{order_id} 已經是 {order['status']} 狀態"

        auto_done = []
        warnings = []
        was_fulfilled = order["status"] in ("shipped", "delivered", "paid")

        # 如果已出貨，回補庫存（用 shipped_qty 回補實際扣減量，避免部分出貨時多補）
        # 未出貨 → 只需釋放 reserved（create_order 當時的預留）
        stock_restored = []
        reserved_released = []
        items = _parse_items_json(order["items"])
        order_bu = order["business_unit"] or ""
        if was_fulfilled:
            for item in items:
                sku = item.get("sku", "")
                qty = item.get("shipped_qty", item.get("qty", 0))
                if not sku or qty <= 0:
                    continue
                inv = _find_inventory(db, sku, order_bu)
                if inv:
                    db.execute("UPDATE inventory SET current_stock = current_stock + ? WHERE id = ?", (qty, inv["id"]))
                    stock_restored.append(f"{inv['name']}({sku}) +{qty}")
                else:
                    warnings.append(f"找不到 SKU={sku} 的庫存紀錄，無法回補")
            if stock_restored:
                auto_done.append(f"庫存已回補：{', '.join(stock_restored)}")
        else:
            # v4: Bug #4 — 未出貨訂單取消：釋放 reserved（create_order 當時的預留）
            for item in items:
                sku = (item.get("sku") or "").strip()
                qty = int(item.get("qty") or 0)
                if not sku or qty <= 0:
                    continue
                inv = _find_inventory(db, sku, order_bu)
                if inv:
                    db.execute(
                        "UPDATE inventory SET reserved = MAX(COALESCE(reserved, 0) - ?, 0) "
                        "WHERE id = ?",
                        (qty, inv["id"]),
                    )
                    reserved_released.append(f"{inv['name']}({sku}) -{qty}")
            if reserved_released:
                auto_done.append(f"預留已釋放：{', '.join(reserved_released)}")

        # v4: Bug #2 — 更新客戶累計：反扣下單（所有情境）+ 若已出貨再反扣已出貨
        if order["customer_id"]:
            db.execute(
                "UPDATE customers SET "
                "  total_ordered = MAX(COALESCE(total_ordered, 0) - ?, 0) "
                "WHERE id = ?",
                (order["total_amount"], order["customer_id"]),
            )
            if was_fulfilled:
                db.execute(
                    "UPDATE customers SET "
                    "  total_fulfilled = MAX(COALESCE(total_fulfilled, 0) - ?, 0), "
                    "  total_purchases = MAX(COALESCE(total_purchases, 0) - ?, 0) "
                    "WHERE id = ?",
                    (order["total_amount"], order["total_amount"], order["customer_id"]),
                )

        # 先統計所有已收金額（含部分付款），再作廢待收帳款
        all_income_txns = db.execute(
            "SELECT id, amount, paid_amount, payment_status FROM transactions WHERE related_order_id = ? AND type = 'income'",
            (order_id,),
        ).fetchall()
        total_paid = sum(t["paid_amount"] for t in all_income_txns)

        # 作廢待收帳款（pending/overdue）
        voided_txns = [t for t in all_income_txns if t["payment_status"] in ("pending", "overdue")]
        for txn in voided_txns:
            db.execute("DELETE FROM transactions WHERE id = ?", (txn["id"],))
            db.execute(
                "INSERT INTO interaction_log (actor, action, target_type, target_id, detail, business_unit) VALUES (?,?,?,?,?,?)",
                ("system", "transaction_voided", "transaction", txn["id"],
                 f"訂單 #{order_id} {cancel_type}，作廢應收帳款 NT${txn['amount']:,.0f}（已收 NT${txn['paid_amount']:,.0f}）",
                 order["business_unit"]),
            )
        if voided_txns:
            voided_total = sum(t["amount"] - t["paid_amount"] for t in voided_txns)
            auto_done.append(f"已作廢 {len(voided_txns)} 筆待收帳款（未收 NT${voided_total:,.0f}）")

        # 更新訂單狀態
        db.execute(
            "UPDATE orders SET status = ?, notes = COALESCE(notes || '\n', '') || ?, updated_at = ? WHERE id = ?",
            (cancel_type, f"[{cancel_type}] {reason}", _now(), order_id),
        )
        db.execute(
            "INSERT INTO interaction_log (actor, action, target_type, target_id, detail, business_unit) VALUES (?,?,?,?,?,?)",
            ("system", f"order_{cancel_type}", "order", order_id, reason, order["business_unit"]),
        )
        db.commit()

        auto_done.append(f"訂單狀態 → {cancel_type}")

        next_steps = []
        if total_paid > 0:
            next_steps.append(
                f"客戶已付 NT${total_paid:,.0f} 需退款 → "
                f"record_transaction(type='expense', category='refund', amount={total_paid}, "
                f"description='退款 訂單#{order_id}', related_order_id={order_id})"
            )
            next_steps.append("LINE 通知客戶退款事宜")
        else:
            next_steps.append("LINE 通知客戶訂單已取消")

        guidance = _build_guidance(auto_done=auto_done, next_steps=next_steps, warnings=warnings or None)
        label = "退貨" if cancel_type == "returned" else "取消"
        return f"✅ 訂單 #{order_id} 已{label}\n原因：{reason}" + guidance
    finally:
        db.close()


# ============================================================
# 每日快照（2 工具）
# ============================================================

def _snapshot_metrics(db, today: str, business_unit: str = "") -> dict:
    """Collect snapshot metrics, optionally filtered by business_unit."""
    # bu_filter is a static SQL fragment (never user data), values always parameterized
    bu_filter = " AND business_unit = ?" if business_unit else ""
    bu: tuple = (business_unit,) if business_unit else ()
    month = today[:7]

    pending = db.execute("SELECT COUNT(*) as c FROM tasks WHERE status IN ('pending','in_progress')" + bu_filter, bu).fetchone()["c"]
    completed = db.execute("SELECT COUNT(*) as c FROM tasks WHERE status = 'done' AND completed_at LIKE ?" + bu_filter, (f"{today}%", *bu)).fetchone()["c"]
    overdue = db.execute("SELECT COUNT(*) as c FROM tasks WHERE status IN ('pending','in_progress') AND due_date IS NOT NULL AND due_date < ?" + bu_filter, (today, *bu)).fetchone()["c"]
    income = db.execute("SELECT COALESCE(SUM(amount),0) as s FROM transactions WHERE type='income' AND transaction_date LIKE ?" + bu_filter, (f"{month}%", *bu)).fetchone()["s"]
    expense = db.execute("SELECT COALESCE(SUM(amount),0) as s FROM transactions WHERE type='expense' AND transaction_date LIKE ?" + bu_filter, (f"{month}%", *bu)).fetchone()["s"]
    receivables = db.execute("SELECT COALESCE(SUM(amount - paid_amount),0) as s FROM transactions WHERE type='income' AND payment_status IN ('pending','overdue')" + bu_filter, bu).fetchone()["s"]
    low_stock = db.execute("SELECT COUNT(*) as c FROM inventory WHERE current_stock <= min_stock AND min_stock > 0" + bu_filter, bu).fetchone()["c"]
    orders_count = db.execute("SELECT COUNT(*) as c FROM orders WHERE status IN ('pending','confirmed','shipped')" + bu_filter, bu).fetchone()["c"]

    if business_unit:
        # 事業體客戶數：有該 BU 訂單的不重複客戶
        customers = db.execute(
            "SELECT COUNT(DISTINCT customer_id) as c FROM orders WHERE business_unit = ?",
            (business_unit,),
        ).fetchone()["c"]
        # 事業體 LINE 訊息數：透過 business_entities.channel_id 對應 line_messages.channel_id
        be = db.execute("SELECT channel_id FROM business_entities WHERE id = ?", (business_unit,)).fetchone()
        if be and be["channel_id"]:
            messages = db.execute(
                "SELECT COUNT(*) as c FROM line_messages WHERE channel_id = ? AND created_at LIKE ?",
                (be["channel_id"], f"{today}%"),
            ).fetchone()["c"]
        else:
            messages = 0
    else:
        customers = db.execute("SELECT COUNT(*) as c FROM customers WHERE type='customer'").fetchone()["c"]
        messages = db.execute("SELECT COUNT(*) as c FROM line_messages WHERE created_at LIKE ?", (f"{today}%",)).fetchone()["c"]

    return dict(pending_tasks=pending, completed_tasks_today=completed, overdue_tasks=overdue,
                total_income=income, total_expense=expense, pending_receivables=receivables,
                low_stock_count=low_stock, total_customers=customers, line_messages_today=messages,
                active_orders=orders_count)


@mcp.tool()
def save_daily_snapshot() -> str:
    """擷取今日所有營運指標存入快照（全域 + 各事業體）。CLAUDE.md 啟動流程觸發。"""
    db = get_db()
    try:
        today = _now()[:10]
        saved = []
        skipped = []

        def _save_snapshot(bu_key: str, label: str):
            """Save a single snapshot. Skip if already exists (idempotent)."""
            existing = db.execute(
                "SELECT id FROM daily_snapshots WHERE snapshot_date = ? AND COALESCE(business_unit, '') = ?",
                (today, bu_key),
            ).fetchone()
            if existing:
                skipped.append(label)
                return
            m = _snapshot_metrics(db, today, bu_key) if bu_key else _snapshot_metrics(db, today)
            db.execute(
                """INSERT INTO daily_snapshots (snapshot_date, business_unit, pending_tasks, completed_tasks_today, overdue_tasks,
                   total_income, total_expense, pending_receivables, low_stock_count, total_customers,
                   line_messages_today, active_orders) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (today, bu_key, m["pending_tasks"], m["completed_tasks_today"], m["overdue_tasks"],
                 m["total_income"], m["total_expense"], m["pending_receivables"], m["low_stock_count"],
                 m["total_customers"], m["line_messages_today"], m["active_orders"]),
            )
            saved.append(label)

        # 全域快照
        _save_snapshot("", "全域")

        # 各事業體快照（即使全零也保存，確保趨勢分析連續性）
        entities = db.execute("SELECT id FROM business_entities").fetchall()
        for entity in entities:
            _save_snapshot(entity["id"], entity["id"])

        db.commit()
        if not saved:
            return f"今天（{today}）的快照已全部存在，跳過。"
        msg = f"✅ {today} 快照已儲存（{', '.join(saved)}）"
        if skipped:
            msg += f"，已存在跳過（{', '.join(skipped)}）"
        return msg
    finally:
        db.close()


@mcp.tool()
def get_setting(key: str) -> str:
    """讀取系統設定（從 business_rules category='settings' 讀取）。

    Args:
        key: 設定名稱（如 marketing_frequency_limit, overdue_days_warning）
    """
    db = get_db()
    try:
        rule = db.execute(
            "SELECT content FROM business_rules WHERE category = 'settings' AND title = ? AND superseded_by IS NULL",
            (key,),
        ).fetchone()
        if rule:
            return rule["content"]
        return f"（未設定 {key}）"
    finally:
        db.close()


# ============================================================
# 公司設定（1 工具）
# ============================================================

@mcp.tool()
def update_company(
    name: str = "",
    industry: str = "",
    boss_name: str = "",
    boss_title: str = "",
    boss_line_id: str = "__SKIP__",
    approval_threshold: float = -1,
) -> str:
    """更新公司基本資訊（company 表 id=1）。首次呼叫會自動建立。

    Args:
        name: 公司名稱
        industry: 產業別
        boss_name: 老闆名
        boss_title: 老闆稱謂（如「總經理」「老闆」「執行長」）
        boss_line_id: 老闆的 LINE User ID（用於 LINE 通知路由，傳空字串清除）
        approval_threshold: 審核門檻金額（-1=不更新）
    """
    db = get_db()
    try:
        existing = db.execute("SELECT * FROM company WHERE id = 1").fetchone()
        if not existing:
            db.execute(
                "INSERT INTO company (id, name, industry, boss_name, boss_title, boss_line_id, approval_threshold) VALUES (1,?,?,?,?,?,?)",
                (name or "未設定", industry or None, boss_name or None,
                 boss_title or "老闆", boss_line_id if boss_line_id != "__SKIP__" else None,
                 approval_threshold if approval_threshold >= 0 else 5000),
            )
            db.commit()
            return f"✅ 公司資訊已建立：{name or '未設定'}"

        updates = []
        params = []
        if name:
            updates.append("name = ?")
            params.append(name)
        if industry:
            updates.append("industry = ?")
            params.append(industry)
        if boss_name:
            updates.append("boss_name = ?")
            params.append(boss_name)
        if boss_title:
            updates.append("boss_title = ?")
            params.append(boss_title)
        if boss_line_id != "__SKIP__":
            updates.append("boss_line_id = ?")
            params.append(boss_line_id or None)
        if approval_threshold >= 0:
            updates.append("approval_threshold = ?")
            params.append(approval_threshold)

        if not updates:
            return "沒有指定要更新的欄位。"

        _safe_update(db, "company",
                     {"name", "industry", "boss_name", "boss_title", "boss_line_id", "approval_threshold"},
                     updates, params, "id = 1", [])
        db.commit()
        changed = ", ".join(u.split(" = ")[0] for u in updates)
        return f"✅ 公司資訊已更新（{changed}）"
    finally:
        db.close()


@mcp.tool()
def register_business_entity(
    entity_id: str,
    name: str,
    channel_id: str = "",
    approval_threshold: float = -1,
    notes: str = "",
) -> str:
    """登錄或更新事業體。用於多事業體/多品牌場景。

    Args:
        entity_id: 事業體 ID（如 brand_c, brand_d），也作為 business_unit 值
        name: 事業體名稱
        channel_id: 對應的 LINE OA channel_id
        approval_threshold: 該事業體的審核門檻（-1=沿用公司預設）
        notes: 備註
    """
    db = get_db()
    try:
        existing = db.execute("SELECT * FROM business_entities WHERE id = ?", (entity_id,)).fetchone()
        if existing:
            updates, params = [], []
            if name:
                updates.append("name = ?"); params.append(name)
            if channel_id:
                updates.append("channel_id = ?"); params.append(channel_id)
            if approval_threshold >= 0:
                updates.append("approval_threshold = ?"); params.append(approval_threshold)
            if notes:
                updates.append("notes = ?"); params.append(notes)
            if not updates:
                return "沒有指定要更新的欄位。"
            _safe_update(db, "business_entities",
                         {"name", "channel_id", "approval_threshold", "notes"},
                         updates, params, "id = ?", [entity_id])
            db.commit()
            return f"✅ 事業體 {entity_id} ({name}) 已更新"
        else:
            db.execute(
                "INSERT INTO business_entities (id, name, channel_id, approval_threshold, notes) VALUES (?,?,?,?,?)",
                (entity_id, name, channel_id or None,
                 approval_threshold if approval_threshold >= 0 else None,
                 notes or None),
            )
            db.commit()
            return f"✅ 事業體 {entity_id} ({name}) 已登錄"
    finally:
        db.close()


@mcp.tool()
def list_business_entities() -> str:
    """列出所有已登錄的事業體。"""
    db = get_db()
    try:
        entities = db.execute("SELECT * FROM business_entities ORDER BY id").fetchall()
        if not entities:
            return "目前沒有登錄任何事業體。使用 register_business_entity 登錄。"
        lines = [f"## 事業體（{len(entities)} 個）"]
        for e in entities:
            threshold_str = f"審核門檻 NT${e['approval_threshold']:,.0f}" if e["approval_threshold"] else "沿用公司預設"
            channel_str = f"LINE OA: {e['channel_id']}" if e["channel_id"] else "未綁定 LINE OA"
            lines.append(f"- **{e['id']}** — {e['name']} | {channel_str} | {threshold_str}")
        return "\n".join(lines)
    finally:
        db.close()


# ============================================================
# Session 管理（1 工具）
# ============================================================

@mcp.tool()
def save_session_handoff(session_id: str, summary: str, pending_items: str = "[]") -> str:
    """儲存 session 交接資訊。在關閉 session 或定期保存時呼叫。

    Args:
        session_id: 當前 session ID
        summary: 交接摘要（目前在做什麼、等待什麼）
        pending_items: JSON 格式的待處理項目清單
    """
    db = get_db()
    try:
        db.execute(
            "INSERT INTO session_handoffs (session_id, summary, pending_items) VALUES (?,?,?)",
            (session_id, summary, pending_items),
        )
        db.commit()
        return f"✅ Session 交接已儲存（{session_id[:8]}...）"
    finally:
        db.close()


# ============================================================
# 啟動
# ============================================================

if __name__ == "__main__":
    mcp.run()
