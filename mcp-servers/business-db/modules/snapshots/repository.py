"""Snapshots repository — 純 DB access（cross-table aggregate + insert）。

層次邊界（同 P2.1 attachments pattern）：
- 進 sqlite3.Connection + primitive args
- 出 dict / list / int
- 不 commit / rollback（transaction ownership 在 service）
- 知道 schema（多表 SELECT），不知道 MCP，不做格式化
"""
import sqlite3


def compute_metrics(
    db: sqlite3.Connection, today: str, business_unit: str = ""
) -> dict:
    """跨表 aggregate：算當日所有營運指標。bu_filter 是 static SQL fragment，值都 parameterized。"""
    bu_filter = " AND business_unit = ?" if business_unit else ""
    bu: tuple = (business_unit,) if business_unit else ()
    month = today[:7]

    pending = db.execute(
        "SELECT COUNT(*) as c FROM tasks WHERE status IN ('pending','in_progress')" + bu_filter,
        bu,
    ).fetchone()["c"]
    completed = db.execute(
        "SELECT COUNT(*) as c FROM tasks WHERE status = 'done' AND completed_at LIKE ?" + bu_filter,
        (f"{today}%", *bu),
    ).fetchone()["c"]
    overdue = db.execute(
        "SELECT COUNT(*) as c FROM tasks WHERE status IN ('pending','in_progress') "
        "AND due_date IS NOT NULL AND due_date < ?" + bu_filter,
        (today, *bu),
    ).fetchone()["c"]
    income = db.execute(
        "SELECT COALESCE(SUM(amount),0) as s FROM transactions "
        "WHERE type='income' AND transaction_date LIKE ?" + bu_filter,
        (f"{month}%", *bu),
    ).fetchone()["s"]
    expense = db.execute(
        "SELECT COALESCE(SUM(amount),0) as s FROM transactions "
        "WHERE type='expense' AND transaction_date LIKE ?" + bu_filter,
        (f"{month}%", *bu),
    ).fetchone()["s"]
    receivables = db.execute(
        "SELECT COALESCE(SUM(amount - paid_amount),0) as s FROM transactions "
        "WHERE type='income' AND payment_status IN ('pending','overdue')" + bu_filter,
        bu,
    ).fetchone()["s"]
    low_stock = db.execute(
        "SELECT COUNT(*) as c FROM inventory WHERE current_stock <= min_stock AND min_stock > 0" + bu_filter,
        bu,
    ).fetchone()["c"]
    orders_count = db.execute(
        "SELECT COUNT(*) as c FROM orders WHERE status IN ('pending','confirmed','shipped')" + bu_filter,
        bu,
    ).fetchone()["c"]

    if business_unit:
        customers = db.execute(
            "SELECT COUNT(DISTINCT customer_id) as c FROM orders WHERE business_unit = ?",
            (business_unit,),
        ).fetchone()["c"]
        be = db.execute(
            "SELECT channel_id FROM business_entities WHERE id = ?", (business_unit,)
        ).fetchone()
        if be and be["channel_id"]:
            messages = db.execute(
                "SELECT COUNT(*) as c FROM line_messages WHERE channel_id = ? AND created_at LIKE ?",
                (be["channel_id"], f"{today}%"),
            ).fetchone()["c"]
        else:
            messages = 0
    else:
        customers = db.execute(
            "SELECT COUNT(*) as c FROM customers WHERE type='customer'"
        ).fetchone()["c"]
        messages = db.execute(
            "SELECT COUNT(*) as c FROM line_messages WHERE created_at LIKE ?",
            (f"{today}%",),
        ).fetchone()["c"]

    return dict(
        pending_tasks=pending,
        completed_tasks_today=completed,
        overdue_tasks=overdue,
        total_income=income,
        total_expense=expense,
        pending_receivables=receivables,
        low_stock_count=low_stock,
        total_customers=customers,
        line_messages_today=messages,
        active_orders=orders_count,
    )


def snapshot_exists(
    db: sqlite3.Connection, today: str, business_unit_key: str
) -> bool:
    row = db.execute(
        "SELECT id FROM daily_snapshots WHERE snapshot_date = ? AND COALESCE(business_unit, '') = ?",
        (today, business_unit_key),
    ).fetchone()
    return row is not None


def insert_snapshot_if_absent(
    db: sqlite3.Connection, today: str, business_unit_key: str, metrics: dict
) -> bool:
    """原子寫入：INSERT OR IGNORE 對唯一鍵 (snapshot_date, COALESCE(business_unit,'')) 衝突時 no-op。
    回傳 True=本次真有插入、False=已存在被略過（用 rowcount 判斷）。避免 check-then-insert 在併發下
    撞鍵 raise、整批 tx 回滾。"""
    cursor = db.execute(
        "INSERT OR IGNORE INTO daily_snapshots "
        "(snapshot_date, business_unit, pending_tasks, completed_tasks_today, overdue_tasks, "
        "total_income, total_expense, pending_receivables, low_stock_count, total_customers, "
        "line_messages_today, active_orders) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            today,
            business_unit_key,
            metrics["pending_tasks"],
            metrics["completed_tasks_today"],
            metrics["overdue_tasks"],
            metrics["total_income"],
            metrics["total_expense"],
            metrics["pending_receivables"],
            metrics["low_stock_count"],
            metrics["total_customers"],
            metrics["line_messages_today"],
            metrics["active_orders"],
        ),
    )
    return cursor.rowcount > 0


def list_entity_ids(db: sqlite3.Connection) -> list[str]:
    return [row["id"] for row in db.execute("SELECT id FROM business_entities").fetchall()]
