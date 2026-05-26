"""Leave repository — leave_types / leave_balances / leave_requests 純 SQL。

層次邊界：進 sqlite3.Connection + primitive args、出 Row / id / None / rowcount。
不 commit / rollback（transaction ownership 在 service）。
"""
import sqlite3


# ---- leave_types ----

def insert_leave_type(
    db: sqlite3.Connection,
    code: str,
    name: str,
    default_quota_days: float,
    requires_approval: int,
    is_paid: int,
    notes: str | None,
) -> int:
    cursor = db.execute(
        "INSERT INTO leave_types "
        "(code, name, default_quota_days, requires_approval, is_paid, notes) "
        "VALUES (?,?,?,?,?,?)",
        (code, name, default_quota_days, requires_approval, is_paid, notes),
    )
    return cursor.lastrowid


def get_leave_type_by_code(
    db: sqlite3.Connection, code: str
) -> sqlite3.Row | None:
    return db.execute(
        "SELECT * FROM leave_types WHERE code = ?", (code,)
    ).fetchone()


def get_leave_type(
    db: sqlite3.Connection, leave_type_id: int
) -> sqlite3.Row | None:
    return db.execute(
        "SELECT * FROM leave_types WHERE id = ?", (leave_type_id,)
    ).fetchone()


def list_leave_types(db: sqlite3.Connection) -> list:
    return db.execute(
        "SELECT * FROM leave_types ORDER BY id"
    ).fetchall()


# ---- leave_balances ----

def get_balance(
    db: sqlite3.Connection,
    employee_id: int,
    leave_type_id: int,
    year: int,
) -> sqlite3.Row | None:
    return db.execute(
        "SELECT * FROM leave_balances "
        "WHERE employee_id = ? AND leave_type_id = ? AND year = ?",
        (employee_id, leave_type_id, year),
    ).fetchone()


def upsert_balance(
    db: sqlite3.Connection,
    employee_id: int,
    leave_type_id: int,
    year: int,
    allocated_days: float,
    now: str,
) -> None:
    """設定／覆寫某員工某假別某年度的 allocated_days（used_days 保留既有值）。"""
    existing = get_balance(db, employee_id, leave_type_id, year)
    if existing:
        db.execute(
            "UPDATE leave_balances SET allocated_days = ?, updated_at = ? "
            "WHERE id = ?",
            (allocated_days, now, existing["id"]),
        )
    else:
        db.execute(
            "INSERT INTO leave_balances "
            "(employee_id, leave_type_id, year, allocated_days, used_days, updated_at) "
            "VALUES (?,?,?,?,0,?)",
            (employee_id, leave_type_id, year, allocated_days, now),
        )


def add_used_days(
    db: sqlite3.Connection,
    employee_id: int,
    leave_type_id: int,
    year: int,
    delta_days: float,
    now: str,
) -> int:
    """原子條件式扣餘額（codex P3b C3 修法）：必須 allocated - used >= delta。
    回傳 rowcount：1=成功扣減、0=餘額不足或 row 不存在（caller 應 raise → rollback）。"""
    cursor = db.execute(
        "UPDATE leave_balances "
        "SET used_days = used_days + ?, updated_at = ? "
        "WHERE employee_id = ? AND leave_type_id = ? AND year = ? "
        "AND allocated_days - used_days >= ?",
        (delta_days, now, employee_id, leave_type_id, year, delta_days),
    )
    return cursor.rowcount


def restore_used_days(
    db: sqlite3.Connection,
    employee_id: int,
    leave_type_id: int,
    year: int,
    delta_days: float,
    now: str,
) -> int:
    """回補餘額（cancel approved leave 用）。原子條件式 UPDATE（codex P3b round-2 MEDIUM
    修法）：WHERE used_days >= delta、防止資料異常下 used_days 跑成負數。
    回傳 rowcount：1=成功；0=row 不存在 / used_days < delta（caller 應 raise → rollback）。"""
    cursor = db.execute(
        "UPDATE leave_balances "
        "SET used_days = used_days - ?, updated_at = ? "
        "WHERE employee_id = ? AND leave_type_id = ? AND year = ? "
        "AND used_days >= ?",
        (delta_days, now, employee_id, leave_type_id, year, delta_days),
    )
    return cursor.rowcount


def sum_pending_days(
    db: sqlite3.Connection,
    employee_id: int,
    leave_type_id: int,
    year: int,
) -> float:
    """加總同員工同假別同年度（按 start_date 年算）的 pending days、給 pre-check 防 overdraw（C1）。"""
    row = db.execute(
        "SELECT COALESCE(SUM(days), 0) FROM leave_requests "
        "WHERE employee_id = ? AND leave_type_id = ? AND status = 'pending' "
        "AND substr(start_date, 1, 4) = ?",
        (employee_id, leave_type_id, str(year)),
    ).fetchone()
    return row[0] or 0


def list_balances_by_employee(
    db: sqlite3.Connection,
    employee_id: int,
    year: int = 0,
) -> list:
    if year:
        return db.execute(
            "SELECT lb.*, lt.code as type_code, lt.name as type_name "
            "FROM leave_balances lb JOIN leave_types lt ON lb.leave_type_id = lt.id "
            "WHERE lb.employee_id = ? AND lb.year = ? "
            "ORDER BY lt.id",
            (employee_id, year),
        ).fetchall()
    return db.execute(
        "SELECT lb.*, lt.code as type_code, lt.name as type_name "
        "FROM leave_balances lb JOIN leave_types lt ON lb.leave_type_id = lt.id "
        "WHERE lb.employee_id = ? "
        "ORDER BY lb.year DESC, lt.id",
        (employee_id,),
    ).fetchall()


# ---- leave_requests ----

def insert_leave_request(
    db: sqlite3.Connection,
    employee_id: int,
    leave_type_id: int,
    start_date: str,
    end_date: str,
    days: float,
    reason: str | None,
    status: str,
    approval_id: int | None,
) -> int:
    cursor = db.execute(
        "INSERT INTO leave_requests "
        "(employee_id, leave_type_id, start_date, end_date, days, reason, "
        "status, approval_id) VALUES (?,?,?,?,?,?,?,?)",
        (employee_id, leave_type_id, start_date, end_date, days,
         reason, status, approval_id),
    )
    return cursor.lastrowid


def set_request_approval_id(
    db: sqlite3.Connection, leave_request_id: int, approval_id: int
) -> None:
    db.execute(
        "UPDATE leave_requests SET approval_id = ? WHERE id = ?",
        (approval_id, leave_request_id),
    )


def get_leave_request(
    db: sqlite3.Connection, leave_request_id: int
) -> sqlite3.Row | None:
    return db.execute(
        "SELECT lr.*, lt.code as type_code, lt.name as type_name, "
        "lt.requires_approval, e.name as employee_name "
        "FROM leave_requests lr "
        "JOIN leave_types lt ON lr.leave_type_id = lt.id "
        "LEFT JOIN employees e ON lr.employee_id = e.id "
        "WHERE lr.id = ?",
        (leave_request_id,),
    ).fetchone()


def list_pending_requests(
    db: sqlite3.Connection,
    business_unit: str = "",
) -> list:
    """列出所有 pending 請假（JOIN 員工、假別、簽核 id）。

    business_unit 篩選規則：
    - 空字串 = 不篩選、回所有 pending
    - 有值 = 員工的 business_units 含此值（用 ',xxx,' 包逗號比對防部分匹配）
      『或』員工的 business_units 為 NULL / 空字串（視為「全公司」員工、出現在所有 BU 中）
      『或』 employee_id 為 NULL（離職員工的 pending、保留以利老闆檢視）"""
    conditions = ["lr.status = 'pending'"]
    params: list = []
    if business_unit:
        conditions.append(
            "(e.id IS NULL OR e.business_units IS NULL OR e.business_units = '' "
            "OR (',' || e.business_units || ',') LIKE ?)"
        )
        params.append(f"%,{business_unit},%")

    return db.execute(
        "SELECT lr.*, lt.code as type_code, lt.name as type_name, "
        "e.name as employee_name "
        "FROM leave_requests lr "
        "JOIN leave_types lt ON lr.leave_type_id = lt.id "
        "LEFT JOIN employees e ON lr.employee_id = e.id "
        f"WHERE {' AND '.join(conditions)} "
        "ORDER BY lr.created_at",
        params,
    ).fetchall()


def update_request_status(
    db: sqlite3.Connection,
    leave_request_id: int,
    status: str,
    decided_by: str,
    decided_at: str,
) -> int:
    cursor = db.execute(
        "UPDATE leave_requests SET status = ?, decided_by = ?, decided_at = ? "
        "WHERE id = ?",
        (status, decided_by, decided_at, leave_request_id),
    )
    return cursor.rowcount


def list_requests(
    db: sqlite3.Connection,
    employee_id: int = 0,
    status: str = "",
    year: int = 0,
    leave_type_code: str = "",
    limit: int = 30,
) -> list:
    """通用查詢請假紀錄。

    所有 filter 均為選用、空值=不篩。回最新 limit 筆（按 created_at DESC）。"""
    conditions = ["1 = 1"]
    params: list = []
    if employee_id:
        conditions.append("lr.employee_id = ?")
        params.append(employee_id)
    if status:
        conditions.append("lr.status = ?")
        params.append(status)
    if year:
        conditions.append("substr(lr.start_date, 1, 4) = ?")
        params.append(str(year))
    if leave_type_code:
        conditions.append("lt.code = ?")
        params.append(leave_type_code.strip().lower())

    where_clause = " AND ".join(conditions)
    params.append(limit)

    return db.execute(
        "SELECT lr.*, lt.code as type_code, lt.name as type_name, "
        "e.name as employee_name "
        "FROM leave_requests lr "
        "JOIN leave_types lt ON lr.leave_type_id = lt.id "
        "LEFT JOIN employees e ON lr.employee_id = e.id "
        f"WHERE {where_clause} "
        "ORDER BY lr.created_at DESC "
        "LIMIT ?",
        params,
    ).fetchall()


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
        "VALUES (?,?,?,?,?,?)",
        (actor, action, "leave_request", target_id, detail, business_unit),
    )
