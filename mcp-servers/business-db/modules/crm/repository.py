"""CRM repository — customers + customer_entity_terms SQL + interaction_log。

層次邊界（同 P2.1 pattern）：
- 進 sqlite3.Connection + primitive、出 Row / id
- 不 commit / rollback

注意：modules/crm/terms.py 是 P1 抽出的 cross-module helper（orders 跨 module 用），
保留不動；本檔不重複定義 fallback 邏輯。
"""
import sqlite3

from shared.utils import _like_param, _safe_update

_CUSTOMER_COLUMNS = {
    "name", "type", "phone", "email", "line_user_id", "tags", "notes",
    "pipeline_stage", "total_purchases", "discount_rate", "payment_terms",
    "primary_business_unit",
}
_ENTITY_TERMS_COLUMNS = {"discount_rate", "payment_terms"}

# v4: 新增 total_ordered/total_fulfilled/total_paid 與 last_*_date 及 primary_business_unit
_CUSTOMER_SEARCH_FIELDS = (
    "id, name, type, phone, email, line_user_id, tags, notes, pipeline_stage, "
    "total_purchases, last_purchase_date, total_ordered, total_fulfilled, total_paid, "
    "last_order_date, last_fulfilled_date, last_payment_date, "
    "discount_rate, payment_terms, primary_business_unit"
)


# ---- customers ----

def insert_customer(
    db: sqlite3.Connection,
    name: str,
    type_: str,
    phone: str | None,
    email: str | None,
    line_user_id: str | None,
    tags: str | None,
    notes: str | None,
    discount_rate: float,
    payment_terms: str,
    primary_business_unit: str | None,
) -> int:
    cursor = db.execute(
        "INSERT INTO customers "
        "(name, type, phone, email, line_user_id, tags, notes, "
        "discount_rate, payment_terms, primary_business_unit) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (name, type_, phone, email, line_user_id, tags, notes,
         discount_rate, payment_terms, primary_business_unit),
    )
    return cursor.lastrowid


def get_customer(db: sqlite3.Connection, customer_id: int) -> sqlite3.Row | None:
    return db.execute(
        "SELECT * FROM customers WHERE id = ?", (customer_id,)
    ).fetchone()


def get_customer_name(db: sqlite3.Connection, customer_id: int) -> sqlite3.Row | None:
    return db.execute(
        "SELECT name FROM customers WHERE id = ?", (customer_id,)
    ).fetchone()


def safe_update_customer(
    db: sqlite3.Connection, customer_id: int, updates: list[str], params: list
) -> None:
    _safe_update(
        db, "customers", _CUSTOMER_COLUMNS, updates, params, "id = ?", [customer_id]
    )


def search_customers(
    db: sqlite3.Connection, query: str, type_: str
) -> list[sqlite3.Row]:
    like = _like_param(query)
    if type_:
        return db.execute(
            f"SELECT {_CUSTOMER_SEARCH_FIELDS} FROM customers "
            f"WHERE type = ? AND (name LIKE ? OR notes LIKE ? OR tags LIKE ? "
            f"OR phone LIKE ? OR line_user_id = ?) LIMIT 10",
            (type_, like, like, like, like, query.strip()),
        ).fetchall()
    return db.execute(
        f"SELECT {_CUSTOMER_SEARCH_FIELDS} FROM customers "
        f"WHERE name LIKE ? OR notes LIKE ? OR tags LIKE ? OR phone LIKE ? OR line_user_id = ? "
        f"LIMIT 10",
        (like, like, like, like, query.strip()),
    ).fetchall()


# ---- customer_entity_terms ----

def list_entity_terms(
    db: sqlite3.Connection, customer_id: int
) -> list[sqlite3.Row]:
    return db.execute(
        "SELECT business_unit, discount_rate, payment_terms "
        "FROM customer_entity_terms WHERE customer_id = ?",
        (customer_id,),
    ).fetchall()


def get_entity_terms(
    db: sqlite3.Connection, customer_id: int, business_unit: str
) -> sqlite3.Row | None:
    return db.execute(
        "SELECT * FROM customer_entity_terms WHERE customer_id = ? AND business_unit = ?",
        (customer_id, business_unit),
    ).fetchone()


def insert_entity_terms(
    db: sqlite3.Connection,
    customer_id: int,
    business_unit: str,
    discount_rate: float,
    payment_terms: str,
) -> None:
    db.execute(
        "INSERT INTO customer_entity_terms "
        "(customer_id, business_unit, discount_rate, payment_terms) VALUES (?,?,?,?)",
        (customer_id, business_unit, discount_rate, payment_terms),
    )


def upsert_entity_terms(
    db: sqlite3.Connection,
    customer_id: int,
    business_unit: str,
    discount_rate: float,
    payment_terms: str,
) -> None:
    """原子 upsert：依 UNIQUE(customer_id, business_unit) 衝突時改 UPDATE，
    避免「先 SELECT 再 INSERT」在併發下撞唯一鍵 raise。"""
    db.execute(
        "INSERT INTO customer_entity_terms "
        "(customer_id, business_unit, discount_rate, payment_terms) VALUES (?,?,?,?) "
        "ON CONFLICT(customer_id, business_unit) DO UPDATE SET "
        "discount_rate = excluded.discount_rate, payment_terms = excluded.payment_terms",
        (customer_id, business_unit, discount_rate, payment_terms),
    )


def safe_update_entity_terms(
    db: sqlite3.Connection,
    customer_id: int,
    business_unit: str,
    updates: list[str],
    params: list,
) -> None:
    _safe_update(
        db, "customer_entity_terms", _ENTITY_TERMS_COLUMNS, updates, params,
        "customer_id = ? AND business_unit = ?", [customer_id, business_unit],
    )


# ---- interaction_log（cross-cutting）----

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
