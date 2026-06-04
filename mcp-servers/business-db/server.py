"""
SME-AI-Kit Business DB MCP Server
SQLite 企業營運資料庫，51 個 MCP tools。
涵蓋：知識管理、任務、員工、客戶、庫存、帳務、訂單、審核、快照、設定。
"""
import sqlite3
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Import migration runner — append (not insert(0)) so we don't shadow stdlib / third-party
_HERE = str(Path(__file__).parent)
if _HERE not in sys.path:
    sys.path.append(_HERE)
from shared.auth import _check_permission  # noqa: E402,F401
from shared.business_units import _get_approval_threshold, _validate_business_unit  # noqa: E402,F401
from shared.db import DB_PATH, _now, get_db, get_db_path  # noqa: E402,F401
from shared.migrations import run_migrations  # noqa: E402
from shared.floor_policy import apply_floor_policy  # noqa: E402
from shared.utils import _build_guidance, _like_param, _safe_update  # noqa: E402,F401

# Pure helpers（無 @mcp.tool）— init_db backfill 跟 orders 等都用到
from modules.inventory.lookup import _find_inventory  # noqa: E402,F401
from modules.orders.items import _parse_items_json  # noqa: E402,F401

# === 設定 ===

SCHEMA_PATH = Path(__file__).parent / "schema.sql"

# === 資料庫 ===
# get_db / DB_PATH / _now 已抽到 shared/db.py（Phase 1.1）
# _PERM_LEVEL / _check_permission → shared/auth.py（Phase 1.2）
# _validate_business_unit / _get_approval_threshold → shared/business_units.py（Phase 1.2）
# _build_guidance / _safe_update / _rows_to_str / _like_param → shared/utils.py（Phase 1.2）


def init_db():
    """首次啟動時建立所有表。既有 DB 自動補新欄位。"""
    # 用 get_db_path() 動態解析（不用 stale module-level DB_PATH），跟 get_db() 一致
    os.makedirs(os.path.dirname(get_db_path()), exist_ok=True)
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
    # 注意：修正：原條件左側帶空格、右側移除空格，永遠不匹配，導致 rebuild 每次 init_db 都觸發。
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
        # rebuild 必須包含 schema.sql 內定義的所有欄位（含 v4 reserved）— 否則之後 create_order 等查 reserved 會炸
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
            reserved INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT (datetime('now', 'localtime'))
        )""")
        # dynamic column detection — 舊 DB 可能還沒走過 ADD COLUMN（理論上 init_db 開頭已加）
        old_inv_cols = {r[1] for r in db.execute("PRAGMA table_info(_inventory_migrate)").fetchall()}
        reserved_sel = "COALESCE(reserved, 0)" if "reserved" in old_inv_cols else "0"
        db.execute(f"""INSERT INTO inventory
            (id, sku, name, category, current_stock, min_stock, unit, unit_cost, sell_price,
             business_unit, location, last_restock_date, notes, reserved, created_at)
            SELECT id, sku, name, category, current_stock, min_stock, unit, unit_cost, sell_price,
             business_unit, location, last_restock_date, notes, {reserved_sel}, created_at
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
        # rebuild 必須包含 schema.sql 內定義的所有欄位（含 v4 sales aggregate split）— 否則之後 fulfill_order/record_payment 等更新會炸
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
            primary_business_unit TEXT,
            total_ordered REAL DEFAULT 0,
            total_fulfilled REAL DEFAULT 0,
            total_paid REAL DEFAULT 0,
            last_order_date TEXT,
            last_fulfilled_date TEXT,
            last_payment_date TEXT,
            created_at DATETIME DEFAULT (datetime('now', 'localtime')),
            CHECK (type IN ('customer', 'supplier', 'distributor'))
        )""")
        # dynamic column detection — 舊 DB 可能還沒走過 ADD COLUMN（理論上 init_db 開頭已加）
        old_cust_cols = {r[1] for r in db.execute("PRAGMA table_info(_customers_migrate)").fetchall()}
        def _csel(col, default="NULL"):
            return col if col in old_cust_cols else default
        db.execute(f"""INSERT INTO customers
            (id, name, type, phone, email, line_user_id, tags, notes,
             pipeline_stage, total_purchases, last_purchase_date, discount_rate, payment_terms,
             primary_business_unit, total_ordered, total_fulfilled, total_paid,
             last_order_date, last_fulfilled_date, last_payment_date, created_at)
            SELECT id, name, CASE WHEN type IN ('customer','supplier','distributor') THEN type ELSE 'customer' END,
             phone, email, line_user_id, tags, notes,
             pipeline_stage, total_purchases, last_purchase_date, discount_rate, payment_terms,
             {_csel("primary_business_unit")}, {_csel("total_ordered", "0")}, {_csel("total_fulfilled", "0")},
             {_csel("total_paid", "0")}, {_csel("last_order_date")}, {_csel("last_fulfilled_date")},
             {_csel("last_payment_date")}, created_at
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

    # === Migration runner（baseline 001 已 applied、跑 002+ pending migrations）===
    run_migrations(db)

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


# _rows_to_str / _like_param → shared/utils.py（Phase 1.2）


# _get_customer_terms → modules/crm/terms.py（Phase 1.4.4）


# _validate_business_unit / _get_approval_threshold → shared/business_units.py（Phase 1.2）
# _build_guidance / _safe_update → shared/utils.py（Phase 1.2）


# _parse_items_json → modules/orders/items.py（Phase 1.4.4）


# _PERM_LEVEL → shared/auth.py（Phase 1.2，re-imported above）

# _ORDER_TRANSITIONS → modules/orders/tools.py（Phase 1.4.4）



# _find_inventory → modules/inventory/lookup.py（Phase 1.4.3）


# _check_permission → shared/auth.py（Phase 1.2，re-imported above）


# === MCP Server ===

init_db()

# Shared MCP instance（Phase 1.1）— modules 也 import 同一個 mcp 註冊 tool
from shared.mcp_instance import mcp  # noqa: E402

# Register tools from extracted modules（Phase 1.1 起逐步搬出）
from modules import accounting as _accounting_mod  # noqa: E402,F401
from modules import approvals as _approvals_mod  # noqa: E402,F401
from modules import attachments as _attachments_mod  # noqa: E402,F401
from modules import crm as _crm_mod  # noqa: E402,F401
from modules import deadlines as _deadlines_mod  # noqa: E402,F401
from modules import hr as _hr_mod  # noqa: E402,F401
from modules import inventory as _inventory_mod  # noqa: E402,F401
from modules import knowledge as _knowledge_mod  # noqa: E402,F401
from modules import leave as _leave_mod  # noqa: E402,F401
from modules import notifications as _notifications_mod  # noqa: E402,F401
from modules import orders as _orders_mod  # noqa: E402,F401
from modules import settings as _settings_mod  # noqa: E402,F401
from modules import snapshots as _snapshots_mod  # noqa: E402,F401
from modules import tasks as _tasks_mod  # noqa: E402,F401

# Re-export 搬出的 tool 到 server module namespace（既有 test/import 用 `server.X` 仍可用）
from modules.accounting.tools import (  # noqa: E402,F401
    check_overdue,
    delete_transaction,
    get_transaction,
    list_transactions,
    monthly_summary,
    record_payment,
    record_transaction,
    update_transaction,
)
from modules.approvals.tools import create_approval, get_approval, resolve_approval  # noqa: E402,F401
from modules.attachments.tools import add_attachment, list_attachments  # noqa: E402,F401
from modules.crm.tools import (  # noqa: E402,F401
    add_customer,
    find_customer,
    get_customer,
    set_customer_entity_terms,
    update_customer,
)
from modules.deadlines.tools import (  # noqa: E402,F401
    create_deadline,
    create_matter,
    find_matter_by_party,
    get_deadline,
    get_matter,
    list_deadlines,
    list_matters,
    list_upcoming_deadlines,
    mark_deadline_calendared,
    mark_deadline_filed,
)
from modules.hr.tools import (  # noqa: E402,F401
    find_partner,
    get_partner,
    list_employees,
    list_partners,
    lookup_employee,
    register_employee,
    register_partner,
    update_employee,
    update_partner,
)
from modules.inventory.tools import check_stock, low_stock_alerts, update_stock  # noqa: E402,F401
from modules.knowledge.tools import (  # noqa: E402,F401
    get_context_summary,
    get_rule,
    get_rule_relations,
    knowledge_changelog,
    lint_knowledge,
    link_rules,
    log_decision,
    log_interaction,
    query_knowledge,
    store_fact,
    update_rule,
)
from modules.leave.tools import (  # noqa: E402,F401
    approve_leave,
    cancel_leave,
    get_leave_balance,
    get_leave_request,
    list_leave_requests,
    list_pending_leave_requests,
    register_leave_type,
    reject_leave,
    request_leave,
    set_leave_balance,
)
from modules.notifications.tools import list_line_groups, register_line_group, search_line_messages  # noqa: E402,F401
from modules.orders.tools import (  # noqa: E402,F401
    cancel_order,
    create_order,
    fulfill_order,
    get_order,
    list_orders,
    qc_order,
    update_order,
)
from modules.settings.tools import (  # noqa: E402,F401
    get_setting,
    list_business_entities,
    register_business_entity,
    resolve_handoff,
    save_session_handoff,
    update_company,
)
from modules.snapshots.tools import save_daily_snapshot  # noqa: E402,F401
from modules.tasks.tools import create_task, get_task, list_tasks, search_tasks, update_task  # noqa: E402,F401


# ============================================================
# 知識管理（已搬到 modules/knowledge/，Phase 1.3.3）
# ============================================================
# store_fact / query_knowledge / update_rule / knowledge_changelog / lint_knowledge / link_rules /
# get_rule / get_rule_relations / get_context_summary / log_interaction / log_decision
# → modules/knowledge/tools.py


# ============================================================
# 任務管理（已搬到 modules/tasks/，Phase 1.4.6）
# ============================================================
# create_task / update_task / list_tasks / search_tasks / get_task
# → modules/tasks/tools.py


# ============================================================
# 員工 + 外包夥伴（已搬到 modules/hr/，Phase 1.4.1）
# ============================================================
# register_employee / update_employee / lookup_employee / list_employees +
# register_partner / update_partner / list_partners / find_partner / get_partner
# → modules/hr/tools.py

# ============================================================
# LINE 訊息 + 群組（已搬到 modules/notifications/，Phase 1.3.1）
# ============================================================
# search_line_messages / register_line_group / list_line_groups → modules/notifications/tools.py

# ============================================================
# 客戶管理（已搬到 modules/crm/，Phase 1.4.2）
# ============================================================
# add_customer / find_customer / get_customer / update_customer / set_customer_entity_terms
# → modules/crm/tools.py

# ============================================================
# 庫存管理（已搬到 modules/inventory/，Phase 1.4.3）
# ============================================================
# check_stock / update_stock / low_stock_alerts → modules/inventory/tools.py
# _find_inventory helper → modules/inventory/lookup.py（被 orders 等共用）

# ============================================================
# 審核管理（已搬到 modules/approvals/，Phase 1.3.2）
# ============================================================
# create_approval / resolve_approval → modules/approvals/tools.py

# ============================================================
# 帳務管理（已搬到 modules/accounting/，Phase 1.4.5）
# ============================================================
# record_transaction / list_transactions / monthly_summary /
# get_transaction / delete_transaction / update_transaction
# → modules/accounting/tools.py

# ============================================================
# 附件管理（已搬到 modules/attachments/，Phase 1.1）
# ============================================================
# add_attachment / list_attachments → modules/attachments/tools.py


# ============================================================
# 應收應付（已搬到 modules/accounting/，Phase 1.4.5）
# ============================================================
# check_overdue / record_payment → modules/accounting/tools.py

# ============================================================
# 訂單管理（已搬到 modules/orders/，Phase 1.4.4）
# ============================================================
# create_order / get_order / update_order / list_orders /
# qc_order / fulfill_order / cancel_order → modules/orders/tools.py
# _parse_items_json → modules/orders/items.py
# _ORDER_TRANSITIONS → inline 在 modules/orders/tools.py


# ============================================================
# 每日快照（已搬到 modules/snapshots/，Phase 1.1）
# ============================================================
# save_daily_snapshot → modules/snapshots/tools.py（P2.2 三層化：tools/service/repository）

# ============================================================
# 系統設定 + 公司 + 事業體 + Session（已搬到 modules/settings/，Phase 1.4.7）
# ============================================================
# get_setting / update_company / register_business_entity /
# list_business_entities / save_session_handoff / resolve_handoff
# → modules/settings/tools.py


# ============================================================
# 啟動
# ============================================================

# Floor gate（決策 #159 / #160）：依啟動端(start-line.sh)注入的 SME_FLOOR 移除該層不該有的
# 機密工具。必須在所有 module tool 註冊完之後、mcp.run() 之前。floor='' / 'confidential' = 全權限。
_removed_tools = apply_floor_policy(mcp)
if _removed_tools:
    print(
        f"[business-db] SME_FLOOR='{os.environ.get('SME_FLOOR', '')}' → 移除 {len(_removed_tools)} 個機密工具",
        file=sys.stderr,
    )


@mcp.tool()
def floor_status() -> str:
    """回報此 session 的安全層(SME_FLOOR)與被移除的機密工具，供稽核/驗證分層 gate 是否生效。
    不含任何業務資料、各層皆可呼叫。"""
    floor = os.environ.get("SME_FLOOR", "").strip()
    label = floor if floor else "(未設定 = operator/Cowork 全權限)"
    if _removed_tools:
        return (
            f"安全層 floor='{label}'；此 session 已移除 {len(_removed_tools)} 個機密工具："
            f"{', '.join(_removed_tools)}"
        )
    return f"安全層 floor='{label}'；未移除任何工具（全權限層、或 floor 未設定/未生效）"


@mcp.tool()
def floor_config_status() -> str:
    """回報此 session 的能力設定（floor-map 解析結果，決策 #171）：可碰 BU / 財務可見度 /
    角色 / 上報對象 / 來源。供驗證 #6 能力設定層是否生效。不含業務資料、各層皆可呼叫。"""
    from shared.floor_map import get_floor_config
    from shared.floor_policy import get_floor
    floor = get_floor()
    label = floor if floor else "(未設定 = operator 全權限)"
    cfg = get_floor_config(floor)
    return (
        f"floor='{label}' 能力設定（來源：{cfg.source}）：\n"
        f"- 可碰事業體 business_units：{cfg.business_units or '（未指定）'}\n"
        f"- 財務可見度 financial_visibility：{cfg.financial_visibility} "
        f"（all=看全部財務 / own_bu=只看自己BU[待#11] / none=看不到）\n"
        f"- 角色 role：{cfg.role}\n"
        f"- 上報對象 escalation_target：{cfg.escalation_target}\n"
        f"- 部門標籤：{cfg.department or '（無）'}"
    )


if __name__ == "__main__":
    mcp.run()
