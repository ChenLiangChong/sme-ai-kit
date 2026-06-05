"""Accounting repository — transactions / approvals lookup / customer payment totals / orders lookup。

層次邊界（同 P2.1 pattern）：
- 進 sqlite3.Connection + primitive、出 Row / id
- 不 commit / rollback；transaction ownership 在 service
- 不知道 approval gate / guidance（codex P2 spot-check 警告）
"""
import sqlite3

from shared.utils import _safe_update

_TRANSACTION_COLUMNS = {
    "category", "description", "business_unit", "payment_status",
    "paid_amount", "due_date", "related_order_id", "related_customer_id",
}


# ---- transactions ----
# 註：approval lookup 改由 modules.approvals.repository 統一管，配合 P2.13 consume 邏輯。

def insert_transaction(
    db: sqlite3.Connection,
    type_: str,
    amount: float,
    category: str,
    description: str | None,
    transaction_date: str,
    related_customer_id: int | None,
    related_order_id: int | None,
    related_invoice: str | None,
    business_unit: str | None,
    payment_status: str,
    due_date: str | None,
    paid_amount: float,
    recorded_by: str | None,
) -> int:
    cursor = db.execute(
        "INSERT INTO transactions "
        "(type, amount, category, description, transaction_date, "
        " related_customer_id, related_order_id, related_invoice, "
        " business_unit, payment_status, due_date, paid_amount, recorded_by) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (type_, amount, category, description, transaction_date,
         related_customer_id, related_order_id, related_invoice,
         business_unit, payment_status, due_date, paid_amount, recorded_by),
    )
    return cursor.lastrowid


def get_transaction(
    db: sqlite3.Connection, transaction_id: int
) -> sqlite3.Row | None:
    return db.execute(
        "SELECT * FROM transactions WHERE id = ?", (transaction_id,)
    ).fetchone()


def list_transactions(
    db: sqlite3.Connection,
    start_date: str,
    end_date: str,
    has_date_filter: bool,
    type_: str,
    category: str,
    business_unit: str,
    related_order_id: int,
    limit: int,
) -> list[sqlite3.Row]:
    cols = (
        "id, type, amount, category, description, transaction_date, recorded_by, "
        "payment_status, paid_amount, related_order_id, business_unit"
    )
    if has_date_filter:
        query = f"SELECT {cols} FROM transactions WHERE transaction_date BETWEEN ? AND ?"
        params: list = [start_date, end_date]
    else:
        query = f"SELECT {cols} FROM transactions WHERE 1=1"
        params = []

    if type_:
        query += " AND type = ?"; params.append(type_)
    if category:
        query += " AND category = ?"; params.append(category)
    if business_unit:
        query += " AND business_unit = ?"; params.append(business_unit)
    if related_order_id:
        query += " AND related_order_id = ?"; params.append(related_order_id)

    query += " ORDER BY transaction_date DESC, id DESC LIMIT ?"
    params.append(limit)
    return db.execute(query, params).fetchall()


def delete_transaction(db: sqlite3.Connection, transaction_id: int) -> None:
    db.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))


def safe_update_transaction(
    db: sqlite3.Connection, transaction_id: int, updates: list[str], params: list
) -> None:
    _safe_update(
        db, "transactions", _TRANSACTION_COLUMNS, updates, params,
        "id = ?", [transaction_id],
    )


def update_paid_amount(
    db: sqlite3.Connection,
    transaction_id: int,
    new_paid: float,
    new_status: str,
) -> None:
    db.execute(
        "UPDATE transactions SET paid_amount = ?, payment_status = ? WHERE id = ?",
        (new_paid, new_status, transaction_id),
    )


def mark_overdue_by_due_date(db: sqlite3.Connection, today: str) -> None:
    """auto-promote pending → overdue。在 service 的 with transaction() 內呼叫。"""
    db.execute(
        "UPDATE transactions SET payment_status = 'overdue' "
        "WHERE payment_status = 'pending' AND due_date IS NOT NULL "
        "AND due_date < ? AND paid_amount < amount",
        (today,),
    )


def list_overdue(
    db: sqlite3.Connection, business_unit: str
) -> list[sqlite3.Row]:
    cols = (
        "id, type, amount, paid_amount, category, description, due_date, "
        "related_customer_id, related_order_id, transaction_date, business_unit"
    )
    if business_unit:
        return db.execute(
            f"SELECT {cols} FROM transactions "
            f"WHERE payment_status = 'overdue' AND business_unit = ? "
            f"ORDER BY due_date",
            (business_unit,),
        ).fetchall()
    return db.execute(
        f"SELECT {cols} FROM transactions WHERE payment_status = 'overdue' ORDER BY due_date"
    ).fetchall()


# ---- aggregates ----

def monthly_by_type_category(
    db: sqlite3.Connection, year_month: str, business_unit: str
) -> list[sqlite3.Row]:
    bu_filter = ""
    params: list = [f"{year_month}%"]
    if business_unit:
        bu_filter = " AND business_unit = ?"
        params.append(business_unit)
    return db.execute(
        f"SELECT type, category, SUM(amount) as total, COUNT(*) as count "
        f"FROM transactions WHERE transaction_date LIKE ?{bu_filter} "
        f"GROUP BY type, category ORDER BY type, total DESC",
        params,
    ).fetchall()


def monthly_by_business_unit(
    db: sqlite3.Connection, year_month: str
) -> list[sqlite3.Row]:
    return db.execute(
        "SELECT business_unit, type, SUM(amount) as total FROM transactions "
        "WHERE transaction_date LIKE ? AND business_unit IS NOT NULL "
        "GROUP BY business_unit, type ORDER BY business_unit",
        (f"{year_month}%",),
    ).fetchall()


def monthly_unassigned(
    db: sqlite3.Connection, year_month: str
) -> list[sqlite3.Row]:
    return db.execute(
        "SELECT type, SUM(amount) as total FROM transactions "
        "WHERE transaction_date LIKE ? AND business_unit IS NULL GROUP BY type",
        (f"{year_month}%",),
    ).fetchall()


# ---- cross-module read（customers + orders）----

def get_customer_name(
    db: sqlite3.Connection, customer_id: int
) -> sqlite3.Row | None:
    return db.execute(
        "SELECT name FROM customers WHERE id = ?", (customer_id,)
    ).fetchone()


def update_customer_payment_totals(
    db: sqlite3.Connection, customer_id: int, amount: float, payment_date: str
) -> None:
    """v4 Bug #2 修：客戶累計已收款 + 最後付款日。"""
    db.execute(
        "UPDATE customers SET "
        "  total_paid = COALESCE(total_paid, 0) + ?, "
        "  last_payment_date = ? "
        "WHERE id = ?",
        (amount, payment_date, customer_id),
    )


def adjust_customer_total_paid(
    db: sqlite3.Connection, customer_id: int, delta: float
) -> None:
    """只調整 total_paid（不動 last_payment_date）。

    codex 稽核：刪帳回沖 / 改付款狀態或客戶掛載重算時用。delta 可為負（回沖）。
    last_payment_date 刻意不動——回沖/重算無法可靠推回前一次付款日，亂寫會誤導 CRM；
    保留現值較安全（最後付款日只在 record_payment / record_transaction 正向進帳時前進）。
    """
    db.execute(
        "UPDATE customers SET total_paid = COALESCE(total_paid, 0) + ? WHERE id = ?",
        (delta, customer_id),
    )


def get_order_status_total(
    db: sqlite3.Connection, order_id: int
) -> sqlite3.Row | None:
    return db.execute(
        "SELECT status, total_amount FROM orders WHERE id = ?", (order_id,)
    ).fetchone()


def get_order_status(
    db: sqlite3.Connection, order_id: int
) -> sqlite3.Row | None:
    return db.execute(
        "SELECT status FROM orders WHERE id = ?", (order_id,)
    ).fetchone()


def sum_paid_income_for_order(
    db: sqlite3.Connection, order_id: int
) -> float:
    return db.execute(
        "SELECT COALESCE(SUM(amount), 0) as s FROM transactions "
        "WHERE related_order_id = ? AND type = 'income' AND payment_status = 'paid'",
        (order_id,),
    ).fetchone()["s"]


# ---- interaction_log ----

def insert_interaction_log(
    db: sqlite3.Connection,
    actor: str,
    action: str,
    target_id: int,
    detail: str,
    business_unit: str | None,
) -> None:
    db.execute(
        "INSERT INTO interaction_log "
        "(actor, action, target_type, target_id, detail, business_unit) "
        "VALUES (?,?,'transaction',?,?,?)",
        (actor, action, target_id, detail, business_unit),
    )
