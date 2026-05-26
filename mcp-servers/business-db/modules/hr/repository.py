"""HR repository — employees + external_partners SQL + interaction_log。

層次邊界（同 P2.1 pattern）：
- 進 sqlite3.Connection + primitive、出 Row / id / rowcount
- 不 commit / rollback；IntegrityError 直接 propagate up，service 接
"""
import sqlite3

from shared.utils import _like_param, _safe_update

_EMPLOYEE_COLUMNS = {
    "name", "role", "department", "line_user_id", "permissions",
    "phone", "business_units", "active", "notes",
}
_PARTNER_COLUMNS = {
    "name", "role", "line_user_id", "phone", "email",
    "business_units", "payment_terms", "notes", "active",
}


# ---- employees ----

def insert_employee(
    db: sqlite3.Connection,
    name: str,
    role: str,
    department: str | None,
    line_user_id: str | None,
    permissions: str,
    phone: str | None,
    business_units: str | None,
) -> int:
    cursor = db.execute(
        "INSERT INTO employees "
        "(name, role, department, line_user_id, permissions, phone, business_units) "
        "VALUES (?,?,?,?,?,?,?)",
        (name, role, department, line_user_id, permissions, phone, business_units),
    )
    return cursor.lastrowid


def safe_update_employee(
    db: sqlite3.Connection, employee_id: int, updates: list[str], params: list
) -> int:
    return _safe_update(
        db, "employees", _EMPLOYEE_COLUMNS, updates, params, "id = ?", [employee_id]
    )


def get_employee_by_name_or_line(
    db: sqlite3.Connection, name_or_line_id: str
) -> sqlite3.Row | None:
    return db.execute(
        "SELECT * FROM employees WHERE (name = ? OR line_user_id = ?) AND active = 1",
        (name_or_line_id, name_or_line_id),
    ).fetchone()


def list_employees(
    db: sqlite3.Connection, active_only: bool
) -> list[sqlite3.Row]:
    query = (
        "SELECT id, name, role, department, permissions, line_user_id, business_units "
        "FROM employees"
    )
    if active_only:
        query += " WHERE active = 1"
    query += (
        " ORDER BY CASE role WHEN 'boss' THEN 0 WHEN 'manager' THEN 1 ELSE 2 END, name"
    )
    return db.execute(query).fetchall()


# ---- external_partners ----

def insert_partner(
    db: sqlite3.Connection,
    name: str,
    role: str | None,
    line_user_id: str | None,
    phone: str | None,
    email: str | None,
    business_units: str | None,
    payment_terms: str | None,
    notes: str | None,
) -> int:
    cursor = db.execute(
        "INSERT INTO external_partners "
        "(name, role, line_user_id, phone, email, business_units, payment_terms, notes) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (name, role, line_user_id, phone, email, business_units, payment_terms, notes),
    )
    return cursor.lastrowid


def get_partner(
    db: sqlite3.Connection, partner_id: int
) -> sqlite3.Row | None:
    return db.execute(
        "SELECT * FROM external_partners WHERE id = ?", (partner_id,)
    ).fetchone()


def safe_update_partner(
    db: sqlite3.Connection, partner_id: int, updates: list[str], params: list
) -> None:
    _safe_update(
        db, "external_partners", _PARTNER_COLUMNS, updates, params, "id = ?", [partner_id]
    )


def list_partners(
    db: sqlite3.Connection,
    active_only: bool,
    role: str,
    business_unit: str,
) -> list[sqlite3.Row]:
    conditions: list[str] = []
    params: list = []
    if active_only:
        conditions.append("active = 1")
    if role:
        conditions.append("role LIKE ?")
        params.append(_like_param(role))
    if business_unit:
        conditions.append(
            "(business_units LIKE ? OR business_units IS NULL OR business_units = '')"
        )
        params.append(_like_param(business_unit))
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    return db.execute(
        f"SELECT id, name, role, line_user_id, phone, business_units, payment_terms, active "
        f"FROM external_partners{where} ORDER BY active DESC, id",
        params,
    ).fetchall()


def search_partners(db: sqlite3.Connection, query: str) -> list[sqlite3.Row]:
    like = _like_param(query)
    return db.execute(
        "SELECT * FROM external_partners "
        "WHERE name LIKE ? OR role LIKE ? OR phone LIKE ? OR line_user_id = ? OR notes LIKE ? "
        "ORDER BY active DESC, id LIMIT 10",
        (like, like, like, query.strip(), like),
    ).fetchall()


# ---- interaction_log（cross-cutting，同 approvals/repository 的設計）----

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
