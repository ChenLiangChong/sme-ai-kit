"""Orders repository — orders + cross-table 寫入（customer 累計 / inventory 預留+扣減 / receivable）。

層次邊界（同 P2.1 pattern）：
- 進 sqlite3.Connection + primitive、出 Row / id
- 不 commit / rollback；service 用 with transaction() 統一管
- 不產生 LINE wording / approval prompt（codex P2.10 警告 #4）
"""
import sqlite3

from shared.utils import _safe_update

_ORDER_COLUMNS = {
    "updated_at", "status", "delivered_at", "notes", "driver", "estimated_delivery",
}


# ---- orders ----

def get_order(db: sqlite3.Connection, order_id: int) -> sqlite3.Row | None:
    return db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()


def list_orders(
    db: sqlite3.Connection,
    customer_id: int,
    status: str,
    business_unit: str,
    limit: int,
) -> list[sqlite3.Row]:
    query = (
        "SELECT o.*, c.name as customer_name FROM orders o "
        "LEFT JOIN customers c ON o.customer_id = c.id WHERE 1=1"
    )
    params: list = []
    if customer_id:
        query += " AND o.customer_id = ?"; params.append(customer_id)
    if status:
        query += " AND o.status = ?"; params.append(status)
    if business_unit:
        query += " AND o.business_unit = ?"; params.append(business_unit)
    query += " ORDER BY o.created_at DESC LIMIT ?"
    params.append(limit)
    return db.execute(query, params).fetchall()


def insert_order(
    db: sqlite3.Connection,
    customer_id: int,
    total_amount: float,
    items_json: str,
    business_unit: str | None,
    notes: str | None,
    created_by: str | None,
    payment_terms: str,
    discount_applied: float,
) -> int:
    cursor = db.execute(
        "INSERT INTO orders "
        "(customer_id, total_amount, items, business_unit, notes, created_by, "
        " payment_terms, discount_applied) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (customer_id, total_amount, items_json, business_unit, notes, created_by,
         payment_terms, discount_applied),
    )
    return cursor.lastrowid


def safe_update_order(
    db: sqlite3.Connection, order_id: int, updates: list[str], params: list
) -> None:
    _safe_update(
        db, "orders", _ORDER_COLUMNS, updates, params, "id = ?", [order_id]
    )


def update_status(
    db: sqlite3.Connection, order_id: int, status: str, updated_at: str
) -> None:
    db.execute(
        "UPDATE orders SET status = ?, updated_at = ? WHERE id = ?",
        (status, updated_at, order_id),
    )


def update_qc(
    db: sqlite3.Connection,
    order_id: int,
    result: str,
    notes: str | None,
    checked_by: str | None,
    checked_at: str,
    updated_at: str,
) -> None:
    db.execute(
        "UPDATE orders SET qc_status = ?, qc_notes = ?, qc_checked_by = ?, "
        "qc_checked_at = ?, updated_at = ? WHERE id = ?",
        (result, notes, checked_by, checked_at, updated_at, order_id),
    )


def update_items_with_note(
    db: sqlite3.Connection, order_id: int, items_json: str, note_label: str
) -> None:
    db.execute(
        "UPDATE orders SET items = ?, "
        "notes = COALESCE(notes || '\\n', '') || ? WHERE id = ?",
        (items_json, note_label, order_id),
    )


def update_cancel(
    db: sqlite3.Connection,
    order_id: int,
    cancel_type: str,
    cancel_note: str,
    updated_at: str,
) -> None:
    db.execute(
        "UPDATE orders SET status = ?, "
        "notes = COALESCE(notes || '\\n', '') || ?, updated_at = ? WHERE id = ?",
        (cancel_type, cancel_note, updated_at, order_id),
    )


# ---- cross-module read：customers + approvals ----

def get_customer_for_order(
    db: sqlite3.Connection, customer_id: int
) -> sqlite3.Row | None:
    """訂單建立用、讀 customer payment_terms / discount_rate / name。"""
    return db.execute(
        "SELECT name, payment_terms, discount_rate FROM customers WHERE id = ?",
        (customer_id,),
    ).fetchone()


def get_customer_name(
    db: sqlite3.Connection, customer_id: int
) -> sqlite3.Row | None:
    return db.execute(
        "SELECT name FROM customers WHERE id = ?", (customer_id,)
    ).fetchone()


def get_customer_full(
    db: sqlite3.Connection, customer_id: int
) -> sqlite3.Row | None:
    return db.execute(
        "SELECT * FROM customers WHERE id = ?", (customer_id,)
    ).fetchone()


# 註：approval lookup 改由 modules.approvals.repository 統一管，配合 P2.13 consume 邏輯。

# ---- cross-module write：customer 累計 ----

def add_customer_ordered(
    db: sqlite3.Connection, customer_id: int, amount: float, order_date: str
) -> None:
    db.execute(
        "UPDATE customers SET "
        "  total_ordered = COALESCE(total_ordered, 0) + ?, "
        "  last_order_date = ? "
        "WHERE id = ?",
        (amount, order_date, customer_id),
    )


def add_customer_fulfilled(
    db: sqlite3.Connection,
    customer_id: int,
    amount: float,
    fulfilled_date: str,
) -> None:
    """v4 Bug #2：total_fulfilled = 新語意「已認列營收」；total_purchases 保留向後相容。"""
    db.execute(
        "UPDATE customers SET "
        "  total_fulfilled = COALESCE(total_fulfilled, 0) + ?, "
        "  total_purchases = COALESCE(total_purchases, 0) + ?, "
        "  last_fulfilled_date = ?, "
        "  last_purchase_date = ? "
        "WHERE id = ?",
        (amount, amount, fulfilled_date, fulfilled_date, customer_id),
    )


def reduce_customer_ordered(
    db: sqlite3.Connection, customer_id: int, amount: float
) -> None:
    db.execute(
        "UPDATE customers SET "
        "  total_ordered = MAX(COALESCE(total_ordered, 0) - ?, 0) "
        "WHERE id = ?",
        (amount, customer_id),
    )


def reduce_customer_fulfilled(
    db: sqlite3.Connection, customer_id: int, amount: float
) -> None:
    db.execute(
        "UPDATE customers SET "
        "  total_fulfilled = MAX(COALESCE(total_fulfilled, 0) - ?, 0), "
        "  total_purchases = MAX(COALESCE(total_purchases, 0) - ?, 0) "
        "WHERE id = ?",
        (amount, amount, customer_id),
    )


# ---- cross-module write：inventory 預留 / 扣減 ----

def add_inventory_reserved(
    db: sqlite3.Connection, inv_id: int, qty: int
) -> None:
    db.execute(
        "UPDATE inventory SET reserved = COALESCE(reserved, 0) + ? WHERE id = ?",
        (qty, inv_id),
    )


def release_inventory_reserved(
    db: sqlite3.Connection, inv_id: int, qty: int
) -> None:
    db.execute(
        "UPDATE inventory SET reserved = MAX(COALESCE(reserved, 0) - ?, 0) "
        "WHERE id = ?",
        (qty, inv_id),
    )


def deduct_inventory_stock_and_release(
    db: sqlite3.Connection, inv_id: int, qty: int
) -> None:
    """fulfill_order 同步扣 current_stock 和釋放 reserved（v4 Bug #4）。"""
    db.execute(
        "UPDATE inventory SET "
        "  current_stock = current_stock - ?, "
        "  reserved = MAX(COALESCE(reserved, 0) - ?, 0) "
        "WHERE id = ?",
        (qty, qty, inv_id),
    )


def restore_inventory_stock(
    db: sqlite3.Connection, inv_id: int, qty: int
) -> None:
    db.execute(
        "UPDATE inventory SET current_stock = current_stock + ? WHERE id = ?",
        (qty, inv_id),
    )


def get_inventory_status(
    db: sqlite3.Connection, inv_id: int
) -> sqlite3.Row | None:
    return db.execute(
        "SELECT current_stock, min_stock, unit FROM inventory WHERE id = ?",
        (inv_id,),
    ).fetchone()


# ---- cross-module: transactions（應收帳款 + 收款累計）----

def sum_paid_income_for_order(
    db: sqlite3.Connection, order_id: int
) -> float:
    return db.execute(
        "SELECT COALESCE(SUM(amount), 0) as total FROM transactions "
        "WHERE related_order_id = ? AND type = 'income' AND payment_status = 'paid'",
        (order_id,),
    ).fetchone()["total"]


def insert_receivable(
    db: sqlite3.Connection,
    amount: float,
    description: str,
    transaction_date: str,
    customer_id: int,
    order_id: int,
    due_date: str | None,
    business_unit: str | None,
) -> None:
    db.execute(
        "INSERT INTO transactions "
        "(type, amount, category, description, transaction_date, "
        " related_customer_id, related_order_id, payment_status, paid_amount, "
        " due_date, recorded_by, business_unit) "
        "VALUES ('income', ?, 'sales_revenue', ?, ?, ?, ?, 'pending', 0, ?, 'system', ?)",
        (amount, description, transaction_date, customer_id, order_id,
         due_date, business_unit),
    )


def list_income_txns_for_order(
    db: sqlite3.Connection, order_id: int
) -> list[sqlite3.Row]:
    return db.execute(
        "SELECT id, amount, paid_amount, payment_status FROM transactions "
        "WHERE related_order_id = ? AND type = 'income'",
        (order_id,),
    ).fetchall()


def delete_transaction(
    db: sqlite3.Connection, transaction_id: int
) -> None:
    db.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))


# ---- interaction_log ----

def insert_interaction_log(
    db: sqlite3.Connection,
    actor: str,
    action: str,
    target_type: str,
    target_id: int,
    detail: str,
    business_unit: str | None,
) -> None:
    db.execute(
        "INSERT INTO interaction_log "
        "(actor, action, target_type, target_id, detail, business_unit) "
        "VALUES (?,?,?,?,?,?)",
        (actor, action, target_type, target_id, detail, business_unit),
    )
