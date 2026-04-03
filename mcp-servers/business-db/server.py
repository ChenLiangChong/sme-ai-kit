"""
SME-AI-Kit Business DB MCP Server
SQLite 企業營運資料庫，34 個 MCP tools。
涵蓋：知識管理、任務、員工、客戶、庫存、帳務、訂單、審核、快照、設定。
"""
import sqlite3
import json
import os
from datetime import datetime
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
    """首次啟動時建立所有表。"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = get_db()
    if SCHEMA_PATH.exists():
        db.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    db.close()


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


# === MCP Server ===

init_db()
mcp = FastMCP("business-db")


# ============================================================
# 知識管理（5 核心工具）
# ============================================================

@mcp.tool()
def store_fact(
    category: str,
    title: str,
    content: str,
    source_type: str = "explicit",
    source_quote: str = "",
    set_by: str = "",
) -> str:
    """儲存企業規則或知識。反捏造機制：source_type='explicit' 時必須附上 source_quote（老闆原話）。

    Args:
        category: 規則類別（如 return_policy, pricing, hr, supplier, sop）
        title: 規則標題
        content: 規則內容詳述
        source_type: 來源類型 — explicit（老闆明確指示）| observed（觀察到的慣例）| inferred（AI推斷）
        source_quote: 老闆原話引用（source_type=explicit 時必填）
        set_by: 誰設定的（如老闆姓名）
    """
    if source_type not in ("explicit", "observed", "inferred"):
        return "ERROR: source_type 必須是 explicit, observed, 或 inferred"
    if source_type == "explicit" and not source_quote.strip():
        return "ERROR: explicit 規則必須附上 source_quote（老闆的原話），不可省略"

    db = get_db()
    try:
        # 矛盾檢查：在同一 category 中搜尋相似的現有規則
        like = _like_param(title)
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
            "INSERT INTO business_rules (category, title, content, source_type, source_quote, set_by) VALUES (?,?,?,?,?,?)",
            (category, title, content, source_type, source_quote.strip() or None, set_by.strip() or None),
        )
        rule_id = cursor.lastrowid

        db.execute(
            "INSERT INTO interaction_log (actor, action, target_type, target_id, detail) VALUES (?,?,?,?,?)",
            (set_by or "system", "rule_created", "rule", rule_id, f"[{category}] {title}"),
        )
        db.commit()
        return f"✅ 已儲存規則 #{rule_id} [{category}] {title}" + warning
    finally:
        db.close()


@mcp.tool()
def query_knowledge(question: str, category: str = "") -> str:
    """搜尋企業知識庫（規則、任務、客戶、庫存）。使用 FTS5 全文搜尋。

    Args:
        question: 搜尋關鍵字或問題
        category: 可選，限定搜尋特定的規則類別
    """
    like = _like_param(question)
    db = get_db()
    try:
        results = []

        # 搜尋規則
        if category:
            rules = db.execute(
                """SELECT id, category, title, content, source_type, set_by, created_at
                   FROM business_rules
                   WHERE category = ? AND superseded_by IS NULL
                   AND (title LIKE ? OR content LIKE ?)
                   LIMIT 10""",
                (category, like, like),
            ).fetchall()
        else:
            rules = db.execute(
                """SELECT id, category, title, content, source_type, set_by, created_at
                   FROM business_rules
                   WHERE superseded_by IS NULL
                   AND (title LIKE ? OR content LIKE ?)
                   LIMIT 10""",
                (like, like),
            ).fetchall()

        if rules:
            results.append("## 📋 企業規則")
            for r in rules:
                src = {"explicit": "老闆指示", "observed": "觀察慣例", "inferred": "AI推斷"}.get(r["source_type"], r["source_type"])
                results.append(f"- **[#{r['id']}] {r['title']}** [{r['category']}] ({src})")
                results.append(f"  {r['content'][:200]}")

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
def update_rule(rule_id: int, new_content: str, reason: str) -> str:
    """更新企業規則。舊規則標記為已取代，建立新規則。

    Args:
        rule_id: 要更新的規則 ID
        new_content: 新的規則內容
        reason: 更新原因
    """
    db = get_db()
    try:
        old = db.execute("SELECT * FROM business_rules WHERE id = ? AND superseded_by IS NULL", (rule_id,)).fetchone()
        if not old:
            return f"ERROR: 找不到有效規則 #{rule_id}（可能已被取代或不存在）"

        # 建立新規則
        cursor = db.execute(
            "INSERT INTO business_rules (category, title, content, source_type, source_quote, set_by) VALUES (?,?,?,?,?,?)",
            (old["category"], old["title"], new_content, old["source_type"], old["source_quote"], old["set_by"]),
        )
        new_id = cursor.lastrowid

        # 標記舊規則為已取代
        db.execute("UPDATE business_rules SET superseded_by = ? WHERE id = ?", (new_id, rule_id))

        db.execute(
            "INSERT INTO interaction_log (actor, action, target_type, target_id, detail) VALUES (?,?,?,?,?)",
            ("system", "rule_updated", "rule", new_id, f"取代 #{rule_id}，原因：{reason}"),
        )
        db.commit()
        return f"✅ 規則已更新：#{rule_id} → #{new_id}\n原因：{reason}"
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

        # 等待審核
        approvals = db.execute(
            "SELECT id, type, summary, requester, created_at FROM approvals WHERE status = 'waiting' ORDER BY created_at",
        ).fetchall()
        if approvals:
            sections.append(f"\n## ⏳ 等待審核（{len(approvals)} 項）")
            for a in approvals:
                sections.append(f"- [#{a['id']}] {a['type']}: {a['summary']} (申請人:{a['requester'] or '?'})")

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

            # 進行中的訂單
            active_orders = db.execute(
                "SELECT o.id, o.status, o.total_amount, c.name as customer_name FROM orders o LEFT JOIN customers c ON o.customer_id = c.id WHERE o.status IN ('pending','confirmed','shipped') ORDER BY o.created_at DESC LIMIT 5"
            ).fetchall()
            if active_orders:
                sections.append(f"\n## 📦 進行中訂單（{len(active_orders)} 筆）")
                status_icon = {"pending": "⏳", "confirmed": "✅", "shipped": "🚚"}
                for o in active_orders:
                    sections.append(f"- {status_icon.get(o['status'], '')} [#{o['id']}] {o['customer_name'] or '?'} NT${o['total_amount']:,.0f}")

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
) -> str:
    """記錄操作日誌（審計追蹤）。

    Args:
        actor: 操作者（員工姓名或 'system'）
        action: 動作（如 rule_created, task_completed, stock_updated）
        target_type: 對象類型（task, rule, inventory, customer, approval）
        target_id: 對象 ID
        detail: 詳細說明
    """
    db = get_db()
    try:
        db.execute(
            "INSERT INTO interaction_log (actor, action, target_type, target_id, detail) VALUES (?,?,?,?,?)",
            (actor, action, target_type or None, target_id or None, detail or None),
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
            "INSERT INTO tasks (title, description, assignee, priority, category, tags, due_date, parent_task_id, created_by) VALUES (?,?,?,?,?,?,?,?,?)",
            (title, description or None, assignee or None, priority, category, tags or None, due_date or None, parent_task_id or None, created_by or None),
        )
        task_id = cursor.lastrowid
        db.execute(
            "INSERT INTO interaction_log (actor, action, target_type, target_id, detail) VALUES (?,?,?,?,?)",
            (created_by or "system", "task_created", "task", task_id, title),
        )
        db.commit()
        pri_icon = {"urgent": "🔴", "normal": "🟡", "low": "🟢"}[priority]
        return f"✅ 任務 #{task_id} 已建立 {pri_icon} {title}" + (f" → {assignee}" if assignee else "")
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

        params.append(task_id)
        db.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", params)
        db.execute(
            "INSERT INTO interaction_log (actor, action, target_type, target_id, detail) VALUES (?,?,?,?,?)",
            ("system", "task_updated", "task", task_id, f"更新: {', '.join(updates)}"),
        )
        db.commit()
        return f"✅ 任務 #{task_id} 已更新"
    finally:
        db.close()


@mcp.tool()
def list_tasks(status: str = "", assignee: str = "", category: str = "", parent_task_id: int = 0, limit: int = 20) -> str:
    """列出任務。

    Args:
        status: 篩選狀態（pending, in_progress, done, cancelled），空白=全部
        assignee: 篩選指派對象
        category: 篩選分類
        parent_task_id: 列出指定父任務的子任務（0=列出頂層任務）
        limit: 最多顯示幾筆
    """
    db = get_db()
    try:
        query = "SELECT id, title, assignee, status, priority, category, due_date, parent_task_id, created_at FROM tasks WHERE 1=1"
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
) -> str:
    """註冊員工並綁定 LINE 帳號。

    Args:
        name: 員工姓名
        role: 角色 — boss | manager | staff
        department: 部門
        line_user_id: LINE User ID（用於綁定 LINE 身份）
        permissions: 權限等級 — admin | manager | basic
        phone: 聯絡電話
    """
    db = get_db()
    try:
        cursor = db.execute(
            "INSERT INTO employees (name, role, department, line_user_id, permissions, phone) VALUES (?,?,?,?,?,?)",
            (name, role, department or None, line_user_id or None, permissions, phone or None),
        )
        emp_id = cursor.lastrowid
        db.commit()
        return f"✅ 員工 #{emp_id} {name} 已註冊（{role}/{permissions}）" + (f" LINE已綁定" if line_user_id else "")
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
    if active >= 0:
        updates.append("active = ?")
        params.append(active)
    if notes:
        updates.append("notes = ?")
        params.append(notes)

    if not updates:
        return "ERROR: 沒有指定要更新的欄位"

    params.append(employee_id)
    db = get_db()
    try:
        result = db.execute(
            f"UPDATE employees SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        db.commit()
        if result.rowcount == 0:
            return f"ERROR: 找不到員工 #{employee_id}"
        changed = ", ".join(u.split(" = ")[0] for u in updates)
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
        return (
            f"## 👤 {emp['name']}\n"
            f"- 角色：{emp['role']} | 權限：{emp['permissions']}\n"
            f"- 部門：{emp['department'] or '未設定'}\n"
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
        query = "SELECT id, name, role, department, permissions, line_user_id FROM employees"
        if active_only:
            query += " WHERE active = 1"
        query += " ORDER BY CASE role WHEN 'boss' THEN 0 WHEN 'manager' THEN 1 ELSE 2 END, name"
        emps = db.execute(query).fetchall()
        if not emps:
            return "目前沒有員工資料。"
        lines = [f"## 👥 員工名冊（{len(emps)} 人）"]
        for e in emps:
            line_status = "📱" if e["line_user_id"] else "❌"
            lines.append(f"- [#{e['id']}] **{e['name']}** ({e['role']}/{e['permissions']}) {e['department'] or ''} {line_status}")
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
    tags: str = "",
    notes: str = "",
) -> str:
    """新增客戶、供應商或經銷商。

    Args:
        name: 名稱（公司名或個人名）
        type: 類型 — customer（客戶）| supplier（供應商）| distributor（經銷商）| partner | prospect
        phone: 電話
        email: Email
        tags: 標籤（逗號分隔，如 vip,wholesale）
        notes: 備註
    """

    db = get_db()
    try:
        cursor = db.execute(
            "INSERT INTO customers (name, type, phone, email, tags, notes) VALUES (?,?,?,?,?,?)",
            (name, type, phone or None, email or None, tags or None, notes or None),
        )
        db.commit()
        return f"✅ 客戶 #{cursor.lastrowid} {name} 已建立"
    finally:
        db.close()


@mcp.tool()
def find_customer(query: str, type: str = "") -> str:
    """搜尋客戶、供應商或經銷商。

    Args:
        query: 搜尋關鍵字
        type: 篩選類型（customer/supplier/distributor/partner/prospect），空白=全部
    """
    like = _like_param(query)
    db = get_db()
    try:
        if type:
            customers = db.execute(
                """SELECT id, name, type, phone, email, tags, notes, pipeline_stage, total_purchases, last_purchase_date
                   FROM customers WHERE type = ? AND (name LIKE ? OR notes LIKE ? OR tags LIKE ? OR phone LIKE ?)
                   LIMIT 10""",
                (type, like, like, like, like),
            ).fetchall()
        else:
            customers = db.execute(
                """SELECT id, name, type, phone, email, tags, notes, pipeline_stage, total_purchases, last_purchase_date
                   FROM customers WHERE name LIKE ? OR notes LIKE ? OR tags LIKE ? OR phone LIKE ?
                   LIMIT 10""",
                (like, like, like, like),
            ).fetchall()
        if not customers:
            return f"找不到與「{query}」相關的{'客戶' if not type else type}。"
        type_icon = {"customer": "👤", "supplier": "🏭", "distributor": "🚚", "partner": "🤝", "prospect": "🎯"}
        stage_icon = {"prospect": "🔵", "contacted": "🟡", "negotiating": "🟠", "closed_won": "🟢", "closed_lost": "🔴"}
        lines = [f"## 搜尋結果：「{query}」"]
        for c in customers:
            icon = type_icon.get(c['type'], '👤')
            stage = ""
            if c['pipeline_stage'] and c['pipeline_stage'] != 'none':
                s_icon = stage_icon.get(c['pipeline_stage'], '')
                stage = f" {s_icon}{c['pipeline_stage']}"
            lines.append(
                f"- {icon} [#{c['id']}] **{c['name']}** ({c['type']}){stage} {c['phone'] or ''} "
                f"{'💰' + str(c['total_purchases']) if c['total_purchases'] else ''} "
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
    tags: str = "",
    notes: str = "",
    pipeline_stage: str = "",
    total_purchases: float = -1,
) -> str:
    """更新客戶/供應商/經銷商資訊。

    Args:
        customer_id: 客戶 ID
        name: 新姓名（空白=不更新）
        phone: 新電話
        email: 新 Email
        tags: 新標籤
        notes: 新備註
        pipeline_stage: 業務階段 — none | prospect | contacted | negotiating | closed_won | closed_lost
        total_purchases: 累計消費金額（-1=不更新）
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

        if not updates:
            return "沒有指定要更新的欄位。"

        params.append(customer_id)
        db.execute(f"UPDATE customers SET {', '.join(updates)} WHERE id = ?", params)
        db.commit()
        return f"✅ 客戶 #{customer_id} 已更新"
    finally:
        db.close()


# ============================================================
# 庫存管理（3 工具）
# ============================================================

@mcp.tool()
def check_stock(sku_or_name: str) -> str:
    """查詢庫存。可用 SKU 或品名搜尋。

    Args:
        sku_or_name: SKU 編號或品名關鍵字
    """
    db = get_db()
    try:
        # 先精確查 SKU
        item = db.execute("SELECT * FROM inventory WHERE sku = ?", (sku_or_name,)).fetchone()
        if item:
            alert = " ⚠️ 低於安全庫存！" if item["current_stock"] <= item["min_stock"] and item["min_stock"] > 0 else ""
            return (
                f"## 📦 {item['name']} [{item['sku']}]\n"
                f"- 庫存：{item['current_stock']}{item['unit']}{alert}\n"
                f"- 安全庫存：{item['min_stock']}{item['unit']}\n"
                f"- 成本：{item['unit_cost'] or '?'} | 售價：{item['sell_price'] or '?'}\n"
                f"- 位置：{item['location'] or '未設定'}\n"
                f"- 最後進貨：{item['last_restock_date'] or '無紀錄'}"
            )

        # LIKE 搜尋
        like = _like_param(sku_or_name)
        items = db.execute(
            "SELECT * FROM inventory WHERE name LIKE ? OR sku LIKE ? OR category LIKE ? LIMIT 5",
            (like, like, like),
        ).fetchall()
        if not items:
            return f"找不到庫存品項：{sku_or_name}"
        lines = [f"## 🔍 庫存搜尋：「{sku_or_name}」"]
        for i in items:
            alert = " ⚠️" if i["current_stock"] <= i["min_stock"] and i["min_stock"] > 0 else ""
            lines.append(f"- [{i['sku']}] {i['name']}: {i['current_stock']}{i['unit']}{alert}")
        return "\n".join(lines)
    finally:
        db.close()


@mcp.tool()
def update_stock(sku: str, quantity_change: int, reason: str = "") -> str:
    """調整庫存數量（正數=進貨，負數=出貨/損耗）。

    Args:
        sku: SKU 編號
        quantity_change: 數量變動（正=進貨，負=出貨）
        reason: 調整原因
    """
    db = get_db()
    try:
        item = db.execute("SELECT * FROM inventory WHERE sku = ?", (sku,)).fetchone()
        if not item:
            return f"ERROR: 找不到 SKU={sku}"

        new_stock = item["current_stock"] + quantity_change
        if new_stock < 0:
            return f"ERROR: 庫存不足。目前 {item['current_stock']}{item['unit']}，無法扣減 {abs(quantity_change)}"

        updates = {"current_stock": new_stock}
        if quantity_change > 0:
            updates["last_restock_date"] = _now()[:10]

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        db.execute(f"UPDATE inventory SET {set_clause} WHERE sku = ?", [*updates.values(), sku])

        direction = "進貨" if quantity_change > 0 else "出貨"
        db.execute(
            "INSERT INTO interaction_log (actor, action, target_type, target_id, detail) VALUES (?,?,?,?,?)",
            ("system", "stock_updated", "inventory", item["id"],
             f"{direction} {abs(quantity_change)}{item['unit']}，{reason or '無說明'}。{item['current_stock']}→{new_stock}"),
        )
        db.commit()

        alert = ""
        if new_stock <= item["min_stock"] and item["min_stock"] > 0:
            alert = f"\n⚠️ 庫存警報：{item['name']} 剩 {new_stock}{item['unit']}，低於安全庫存 {item['min_stock']}"
        return f"✅ [{sku}] {item['name']}: {item['current_stock']} → {new_stock}{item['unit']}" + alert
    finally:
        db.close()


@mcp.tool()
def low_stock_alerts() -> str:
    """列出所有低於安全庫存的品項。"""
    db = get_db()
    try:
        items = db.execute(
            "SELECT sku, name, current_stock, min_stock, unit, location FROM inventory WHERE current_stock <= min_stock AND min_stock > 0 ORDER BY (current_stock * 1.0 / min_stock)",
        ).fetchall()
        if not items:
            return "✅ 所有品項庫存正常，無警報。"
        lines = [f"## ⚠️ 庫存警報（{len(items)} 項）"]
        for i in items:
            pct = round(i["current_stock"] / i["min_stock"] * 100) if i["min_stock"] else 0
            lines.append(f"- 🔴 [{i['sku']}] {i['name']}: {i['current_stock']}/{i['min_stock']}{i['unit']} ({pct}%) {i['location'] or ''}")
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
) -> str:
    """建立審核請求（HITL 人機協作）。

    Args:
        type: 審核類型（email, purchase, refund, announcement, other）
        summary: 摘要
        detail: 詳細內容（JSON 或純文字）
        approver: 指定審核人
    """
    db = get_db()
    try:
        cursor = db.execute(
            "INSERT INTO approvals (type, summary, detail, requester, approver) VALUES (?,?,?,?,?)",
            (type, summary, detail or None, "system", approver or None),
        )
        approval_id = cursor.lastrowid
        db.commit()
        return f"✅ 審核請求 #{approval_id} 已建立\n類型：{type}\n摘要：{summary}\n等待審核中。請透過 LINE 通知主管。"
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
            return f"ERROR: 找不到待審核項目 #{approval_id}"

        db.execute(
            "UPDATE approvals SET status = ?, approver = ?, decided_at = ? WHERE id = ?",
            (decision, decided_by, _now(), approval_id),
        )
        db.execute(
            "INSERT INTO interaction_log (actor, action, target_type, target_id, detail) VALUES (?,?,?,?,?)",
            (decided_by, f"approval_{decision}", "approval", approval_id, approval["summary"]),
        )
        db.commit()
        icon = "✅" if decision == "approved" else "❌"
        return f"{icon} 審核 #{approval_id} 已{('核准' if decision == 'approved' else '駁回')}（{decided_by}）"
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
    payment_status: str = "paid",
    due_date: str = "",
    recorded_by: str = "",
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
        payment_status: 付款狀態 — paid（已付）| pending（待收/待付）| overdue（逾期）
        due_date: 帳期到期日（YYYY-MM-DD），B2B 應收應付用
        recorded_by: 記錄者
    """
    if type not in ("income", "expense"):
        return "ERROR: type 必須是 income 或 expense"
    if amount <= 0:
        return "ERROR: 金額必須是正數"

    if not transaction_date:
        transaction_date = _now()[:10]

    db = get_db()
    try:
        # 檢查是否超過審核門檻
        company = db.execute("SELECT approval_threshold FROM company WHERE id = 1").fetchone()
        threshold = company["approval_threshold"] if company else 5000

        if amount >= threshold:
            return (
                f"⚠️ 金額 NT${amount:,.0f} 超過審核門檻 NT${threshold:,.0f}。\n"
                f"請先用 create_approval 建立審核請求，核准後再記帳。"
            )

        if payment_status not in ("paid", "pending", "overdue"):
            payment_status = "paid"

        paid = amount if payment_status == "paid" else 0.0

        cursor = db.execute(
            """INSERT INTO transactions (type, amount, category, description, transaction_date,
               related_customer_id, related_order_id, related_invoice, payment_status, due_date, paid_amount, recorded_by)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (type, amount, category, description or None, transaction_date,
             related_customer_id or None, related_order_id or None, related_invoice or None,
             payment_status, due_date or None, paid, recorded_by or None),
        )
        txn_id = cursor.lastrowid
        db.execute(
            "INSERT INTO interaction_log (actor, action, target_type, target_id, detail) VALUES (?,?,?,?,?)",
            (recorded_by or "system", "transaction_recorded", "transaction", txn_id,
             f"{type} NT${amount:,.0f} [{category}] {payment_status} {description or ''}"),
        )
        db.commit()

        icon = "💰" if type == "income" else "💸"
        status_label = {"paid": "已付", "pending": "待收付", "overdue": "逾期"}.get(payment_status, "")
        return f"✅ {icon} 帳目 #{txn_id}：{type} NT${amount:,.0f} [{category}] {status_label} {transaction_date}"
    finally:
        db.close()


@mcp.tool()
def list_transactions(
    start_date: str = "",
    end_date: str = "",
    type: str = "",
    category: str = "",
    limit: int = 30,
) -> str:
    """查詢收支記錄。

    Args:
        start_date: 起始日期（YYYY-MM-DD），空白=本月 1 號
        end_date: 結束日期（YYYY-MM-DD），空白=今天
        type: 篩選類型 — income | expense，空白=全部
        category: 篩選分類，空白=全部
        limit: 最多顯示幾筆
    """
    if not start_date:
        start_date = _now()[:8] + "01"  # 本月 1 號
    if not end_date:
        end_date = _now()[:10]

    db = get_db()
    try:
        query = "SELECT id, type, amount, category, description, transaction_date, recorded_by FROM transactions WHERE transaction_date BETWEEN ? AND ?"
        params: list = [start_date, end_date]

        if type:
            query += " AND type = ?"
            params.append(type)
        if category:
            query += " AND category = ?"
            params.append(category)

        query += " ORDER BY transaction_date DESC, id DESC LIMIT ?"
        params.append(limit)

        rows = db.execute(query, params).fetchall()
        if not rows:
            return f"在 {start_date} ~ {end_date} 期間沒有收支記錄。"

        total_income = sum(r["amount"] for r in rows if r["type"] == "income")
        total_expense = sum(r["amount"] for r in rows if r["type"] == "expense")

        lines = [f"## 💹 收支記錄（{start_date} ~ {end_date}，共 {len(rows)} 筆）"]
        lines.append(f"收入合計: NT${total_income:,.0f} | 支出合計: NT${total_expense:,.0f} | 淨額: NT${total_income - total_expense:,.0f}\n")

        for r in rows:
            icon = "💰" if r["type"] == "income" else "💸"
            lines.append(f"- {icon} [#{r['id']}] {r['transaction_date']} NT${r['amount']:,.0f} [{r['category'] or '?'}] {r['description'] or ''}")
        return "\n".join(lines)
    finally:
        db.close()


@mcp.tool()
def monthly_summary(year_month: str = "") -> str:
    """月度收支彙總。

    Args:
        year_month: 年月（YYYY-MM），空白=本月
    """
    if not year_month:
        year_month = _now()[:7]

    db = get_db()
    try:
        rows = db.execute(
            """SELECT type, category, SUM(amount) as total, COUNT(*) as count
               FROM transactions
               WHERE transaction_date LIKE ?
               GROUP BY type, category
               ORDER BY type, total DESC""",
            (f"{year_month}%",),
        ).fetchall()

        if not rows:
            return f"{year_month} 沒有收支記錄。"

        income_rows = [r for r in rows if r["type"] == "income"]
        expense_rows = [r for r in rows if r["type"] == "expense"]
        total_income = sum(r["total"] for r in income_rows)
        total_expense = sum(r["total"] for r in expense_rows)

        lines = [f"## 📊 {year_month} 月度收支彙總"]
        lines.append(f"**收入**: NT${total_income:,.0f} | **支出**: NT${total_expense:,.0f} | **淨額**: NT${total_income - total_expense:,.0f}\n")

        if income_rows:
            lines.append("### 💰 收入明細")
            for r in income_rows:
                lines.append(f"- [{r['category'] or '未分類'}] NT${r['total']:,.0f}（{r['count']} 筆）")

        if expense_rows:
            lines.append("\n### 💸 支出明細")
            for r in expense_rows:
                lines.append(f"- [{r['category'] or '未分類'}] NT${r['total']:,.0f}（{r['count']} 筆）")

        return "\n".join(lines)
    finally:
        db.close()


@mcp.tool()
def delete_transaction(transaction_id: int, reason: str) -> str:
    """刪除一筆帳目（需填原因，會留下審計紀錄）。

    Args:
        transaction_id: 帳目 ID
        reason: 刪除原因（必填）
    """
    if not reason.strip():
        return "ERROR: 刪除帳目必須填寫原因"

    db = get_db()
    try:
        txn = db.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,)).fetchone()
        if not txn:
            return f"ERROR: 找不到帳目 #{transaction_id}"

        db.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
        db.execute(
            "INSERT INTO interaction_log (actor, action, target_type, target_id, detail) VALUES (?,?,?,?,?)",
            ("system", "transaction_deleted", "transaction", transaction_id,
             f"刪除 {txn['type']} NT${txn['amount']:,.0f} [{txn['category']}]，原因：{reason}"),
        )
        db.commit()
        return f"✅ 帳目 #{transaction_id} 已刪除（原因：{reason}）"
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
def check_overdue() -> str:
    """檢查所有逾期帳款。自動判斷：到期日已過且未全額付清。"""
    db = get_db()
    try:
        today = _now()[:10]
        # 自動更新 pending → overdue
        db.execute(
            "UPDATE transactions SET payment_status = 'overdue' WHERE payment_status = 'pending' AND due_date IS NOT NULL AND due_date < ? AND paid_amount < amount",
            (today,),
        )
        db.commit()

        overdue = db.execute(
            """SELECT id, type, amount, paid_amount, category, description, due_date, related_customer_id, transaction_date
               FROM transactions WHERE payment_status = 'overdue' ORDER BY due_date""",
        ).fetchall()

        if not overdue:
            return "✅ 目前沒有逾期帳款。"

        total_receivable = sum(r["amount"] - r["paid_amount"] for r in overdue if r["type"] == "income")
        total_payable = sum(r["amount"] - r["paid_amount"] for r in overdue if r["type"] == "expense")

        lines = [f"## 🔴 逾期帳款（{len(overdue)} 筆）"]
        if total_receivable > 0:
            lines.append(f"\n### 應收未收：NT${total_receivable:,.0f}")
            for r in overdue:
                if r["type"] == "income":
                    remaining = r["amount"] - r["paid_amount"]
                    days = (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(r["due_date"], "%Y-%m-%d")).days
                    lines.append(f"- [#{r['id']}] NT${remaining:,.0f} 逾期 {days} 天 | {r['description'] or r['category']}")

        if total_payable > 0:
            lines.append(f"\n### 應付未付：NT${total_payable:,.0f}")
            for r in overdue:
                if r["type"] == "expense":
                    remaining = r["amount"] - r["paid_amount"]
                    days = (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(r["due_date"], "%Y-%m-%d")).days
                    lines.append(f"- [#{r['id']}] NT${remaining:,.0f} 逾期 {days} 天 | {r['description'] or r['category']}")

        return "\n".join(lines)
    finally:
        db.close()


@mcp.tool()
def record_payment(transaction_id: int, amount: float, notes: str = "") -> str:
    """記錄一筆付款（部分付款或全額付清）。

    Args:
        transaction_id: 帳目 ID
        amount: 本次付款金額
        notes: 備註
    """
    if amount <= 0:
        return "ERROR: 金額必須是正數"

    db = get_db()
    try:
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
        db.execute(
            "INSERT INTO interaction_log (actor, action, target_type, target_id, detail) VALUES (?,?,?,?,?)",
            ("system", "payment_recorded", "transaction", transaction_id,
             f"付款 NT${amount:,.0f}，累計 NT${new_paid:,.0f}/{txn['amount']:,.0f}。{notes}"),
        )
        db.commit()

        if new_status == "paid":
            return f"✅ 帳目 #{transaction_id} 已全額付清（NT${txn['amount']:,.0f}）"
        else:
            return f"✅ 帳目 #{transaction_id} 已收到 NT${amount:,.0f}，剩餘 NT${remaining:,.0f}"
    finally:
        db.close()


# ============================================================
# 訂單管理（5 工具）
# ============================================================

@mcp.tool()
def create_order(customer_id: int, items_json: str, notes: str = "", created_by: str = "") -> str:
    """建立訂單。

    Args:
        customer_id: 客戶 ID
        items_json: 訂單品項 JSON，格式：[{"sku":"A200","name":"特殊零件","qty":10,"price":350}]
        notes: 備註
        created_by: 建立者
    """
    db = get_db()
    try:
        # 驗證客戶存在
        customer = db.execute("SELECT name FROM customers WHERE id = ?", (customer_id,)).fetchone()
        if not customer:
            return f"ERROR: 找不到客戶 #{customer_id}"

        # 解析 items
        try:
            items = json.loads(items_json) if isinstance(items_json, str) else items_json
        except json.JSONDecodeError:
            return "ERROR: items_json 格式錯誤，需要 JSON 陣列"

        total = sum(item.get("qty", 0) * item.get("price", 0) for item in items)

        cursor = db.execute(
            "INSERT INTO orders (customer_id, total_amount, items, notes, created_by) VALUES (?,?,?,?,?)",
            (customer_id, total, json.dumps(items, ensure_ascii=False), notes or None, created_by or None),
        )
        order_id = cursor.lastrowid
        db.execute(
            "INSERT INTO interaction_log (actor, action, target_type, target_id, detail) VALUES (?,?,?,?,?)",
            (created_by or "system", "order_created", "order", order_id,
             f"客戶 {customer['name']}，金額 NT${total:,.0f}，{len(items)} 項品項"),
        )
        db.commit()

        items_str = "\n".join(f"  - {i.get('name', i.get('sku', '?'))} × {i.get('qty', 0)} @ NT${i.get('price', 0):,.0f}" for i in items)
        return f"✅ 訂單 #{order_id} 已建立\n客戶：{customer['name']}\n金額：NT${total:,.0f}\n品項：\n{items_str}"
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

        status_icon = {"pending": "⏳", "confirmed": "✅", "shipped": "🚚", "delivered": "📦", "paid": "💰", "cancelled": "❌"}.get(order["status"], "")

        items = json.loads(order["items"]) if order["items"] else []
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

        return (
            f"## 訂單 #{order_id} {status_icon}\n"
            f"- 客戶：{customer_name}\n"
            f"- 狀態：{order['status']}\n"
            f"- 金額：NT${order['total_amount']:,.0f}\n"
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
    """更新訂單狀態、物流資訊或備註。

    Args:
        order_id: 訂單 ID
        status: 新狀態 — pending | confirmed | shipped | delivered | paid | cancelled
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

        params.append(order_id)
        db.execute(f"UPDATE orders SET {', '.join(updates)} WHERE id = ?", params)

        detail_parts = []
        if status:
            detail_parts.append(f"狀態: {order['status']}→{status}")
        if driver:
            detail_parts.append(f"司機: {driver}")
        if estimated_delivery:
            detail_parts.append(f"預計送達: {estimated_delivery}")

        db.execute(
            "INSERT INTO interaction_log (actor, action, target_type, target_id, detail) VALUES (?,?,?,?,?)",
            ("system", "order_updated", "order", order_id, " | ".join(detail_parts) or "備註更新"),
        )
        db.commit()
        return f"✅ 訂單 #{order_id} 已更新" + (f"（{', '.join(detail_parts)}）" if detail_parts else "")
    finally:
        db.close()


@mcp.tool()
def list_orders(customer_id: int = 0, status: str = "", limit: int = 20) -> str:
    """列出訂單。

    Args:
        customer_id: 篩選客戶（0=全部）
        status: 篩選狀態（空白=全部）
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
        query += " ORDER BY o.created_at DESC LIMIT ?"
        params.append(limit)

        orders = db.execute(query, params).fetchall()
        if not orders:
            return "沒有符合條件的訂單。"

        status_icon = {"pending": "⏳", "confirmed": "✅", "shipped": "🚚", "delivered": "📦", "paid": "💰", "cancelled": "❌"}
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

        db.execute(
            "UPDATE orders SET qc_status = ?, qc_notes = ?, qc_checked_by = ?, qc_checked_at = ?, updated_at = ? WHERE id = ?",
            (result, notes or None, checked_by or None, _now(), _now(), order_id),
        )
        db.execute(
            "INSERT INTO interaction_log (actor, action, target_type, target_id, detail) VALUES (?,?,?,?,?)",
            (checked_by or "system", "qc_completed", "order", order_id, f"QC {result}: {notes or '無備註'}"),
        )
        db.commit()

        icon = {"passed": "✅", "failed": "❌", "partial": "⚠️"}[result]
        msg = f"{icon} 訂單 #{order_id} QC {result}"
        if result == "passed":
            msg += "\n可以用 fulfill_order 出貨了。"
        elif result == "failed":
            msg += "\n請處理品質問題後重新 QC。"
        elif result == "partial":
            msg += "\n部分合格，請確認是否要出貨合格品項。"
        return msg
    finally:
        db.close()


@mcp.tool()
def fulfill_order(order_id: int) -> str:
    """確認訂單出貨：自動扣庫存 + 建立應收帳款。

    Args:
        order_id: 訂單 ID
    """
    db = get_db()
    try:
        order = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if not order:
            return f"ERROR: 找不到訂單 #{order_id}"
        if order["status"] not in ("pending", "confirmed"):
            return f"ERROR: 訂單 #{order_id} 狀態是 {order['status']}，無法出貨"
        if order["qc_status"] != "passed":
            return f"ERROR: 訂單 #{order_id} 尚未通過品質檢查（目前 QC 狀態: {order['qc_status']}）。請先用 qc_order 工具完成 QC。"

        items = json.loads(order["items"]) if order["items"] else []
        errors = []
        deductions = []

        # 檢查所有品項庫存
        for item in items:
            sku = item.get("sku", "")
            qty = item.get("qty", 0)
            if not sku or qty <= 0:
                continue
            inv = db.execute("SELECT current_stock, name FROM inventory WHERE sku = ?", (sku,)).fetchone()
            if not inv:
                errors.append(f"找不到 SKU={sku}")
            elif inv["current_stock"] < qty:
                errors.append(f"{inv['name']}({sku}) 庫存 {inv['current_stock']} 不足，需要 {qty}")
            else:
                deductions.append((sku, qty, inv["name"]))

        if errors:
            return "❌ 無法出貨，庫存不足：\n" + "\n".join(f"- {e}" for e in errors)

        # 扣庫存
        for sku, qty, name in deductions:
            db.execute("UPDATE inventory SET current_stock = current_stock - ? WHERE sku = ?", (qty, sku))

        # 更新訂單狀態
        db.execute("UPDATE orders SET status = 'shipped', updated_at = ? WHERE id = ?", (_now(), order_id))

        # 建立應收帳款
        customer = db.execute("SELECT name FROM customers WHERE id = ?", (order["customer_id"],)).fetchone()
        db.execute(
            """INSERT INTO transactions (type, amount, category, description, transaction_date,
               related_customer_id, related_order_id, payment_status, paid_amount, recorded_by)
               VALUES ('income', ?, 'sales_revenue', ?, ?, ?, ?, 'pending', 0, 'system')""",
            (order["total_amount"], f"訂單 #{order_id} {customer['name'] if customer else ''}", _now()[:10], order["customer_id"], order_id),
        )

        db.execute(
            "INSERT INTO interaction_log (actor, action, target_type, target_id, detail) VALUES (?,?,?,?,?)",
            ("system", "order_fulfilled", "order", order_id,
             f"出貨 {len(deductions)} 項品項，應收 NT${order['total_amount']:,.0f}"),
        )
        db.commit()

        deduct_str = "\n".join(f"  - {name}({sku}) -{qty}" for sku, qty, name in deductions)
        return (
            f"✅ 訂單 #{order_id} 已出貨\n"
            f"庫存扣減：\n{deduct_str}\n"
            f"應收帳款：NT${order['total_amount']:,.0f}（pending）"
        )
    finally:
        db.close()


# ============================================================
# 每日快照（2 工具）
# ============================================================

@mcp.tool()
def save_daily_snapshot() -> str:
    """擷取今日所有營運指標存入快照。CLAUDE.md 啟動流程觸發。"""
    db = get_db()
    try:
        today = _now()[:10]

        # 檢查今天是否已存
        existing = db.execute("SELECT id FROM daily_snapshots WHERE snapshot_date = ?", (today,)).fetchone()
        if existing:
            return f"今天（{today}）的快照已存在，跳過。"

        pending = db.execute("SELECT COUNT(*) as c FROM tasks WHERE status IN ('pending','in_progress')").fetchone()["c"]
        completed = db.execute("SELECT COUNT(*) as c FROM tasks WHERE status = 'done' AND completed_at LIKE ?", (f"{today}%",)).fetchone()["c"]
        overdue = db.execute("SELECT COUNT(*) as c FROM tasks WHERE status IN ('pending','in_progress') AND due_date IS NOT NULL AND due_date < ?", (today,)).fetchone()["c"]

        month = today[:7]
        income = db.execute("SELECT COALESCE(SUM(amount),0) as s FROM transactions WHERE type='income' AND transaction_date LIKE ?", (f"{month}%",)).fetchone()["s"]
        expense = db.execute("SELECT COALESCE(SUM(amount),0) as s FROM transactions WHERE type='expense' AND transaction_date LIKE ?", (f"{month}%",)).fetchone()["s"]
        receivables = db.execute("SELECT COALESCE(SUM(amount - paid_amount),0) as s FROM transactions WHERE type='income' AND payment_status IN ('pending','overdue')").fetchone()["s"]

        low_stock = db.execute("SELECT COUNT(*) as c FROM inventory WHERE current_stock <= min_stock AND min_stock > 0").fetchone()["c"]
        customers = db.execute("SELECT COUNT(*) as c FROM customers WHERE type='customer'").fetchone()["c"]
        messages = db.execute("SELECT COUNT(*) as c FROM line_messages WHERE created_at LIKE ?", (f"{today}%",)).fetchone()["c"]
        orders = db.execute("SELECT COUNT(*) as c FROM orders WHERE status IN ('pending','confirmed','shipped')").fetchone()["c"]

        db.execute(
            """INSERT INTO daily_snapshots (snapshot_date, pending_tasks, completed_tasks_today, overdue_tasks,
               total_income, total_expense, pending_receivables, low_stock_count, total_customers,
               line_messages_today, active_orders) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (today, pending, completed, overdue, income, expense, receivables, low_stock, customers, messages, orders),
        )
        db.commit()
        return f"✅ {today} 快照已儲存"
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
