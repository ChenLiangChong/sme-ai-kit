"""Approvals repository — approvals CRUD + interaction_log 寫入。

層次邊界（同 P2.1 pattern）：
- 進 sqlite3.Connection + primitive args、出 Row / id / None
- 不 commit / rollback（transaction ownership 在 service）
"""
import sqlite3


def insert_approval(
    db: sqlite3.Connection,
    type_: str,
    summary: str,
    detail: str | None,
    requester: str,
    approver: str | None,
    business_unit: str | None,
    expires_at: str,
) -> int:
    cursor = db.execute(
        "INSERT INTO approvals "
        "(type, summary, detail, requester, approver, business_unit, expires_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (type_, summary, detail, requester, approver, business_unit, expires_at),
    )
    return cursor.lastrowid


def get_waiting(
    db: sqlite3.Connection, approval_id: int
) -> sqlite3.Row | None:
    return db.execute(
        "SELECT * FROM approvals WHERE id = ? AND status = 'waiting'",
        (approval_id,),
    ).fetchone()


def get_expired(
    db: sqlite3.Connection, approval_id: int
) -> sqlite3.Row | None:
    return db.execute(
        "SELECT * FROM approvals WHERE id = ? AND status = 'expired'",
        (approval_id,),
    ).fetchone()


def get(db: sqlite3.Connection, approval_id: int) -> sqlite3.Row | None:
    """通用 getter — 不 filter status。給 reject_leave / cancel_leave 等需要看
    approval 狀態（含 rejected / expired）的 caller 用。"""
    return db.execute(
        "SELECT * FROM approvals WHERE id = ?", (approval_id,)
    ).fetchone()


def get_approved_unused(
    db: sqlite3.Connection, approval_id: int
) -> sqlite3.Row | None:
    """取已核准、尚未消耗的 approval。供 record_transaction / create_order 等
    需要 HITL 通過的 caller 使用，並在使用後呼叫 mark_consumed 綁定到建立的 record。"""
    return db.execute(
        "SELECT * FROM approvals "
        "WHERE id = ? AND status = 'approved' AND consumed_at IS NULL",
        (approval_id,),
    ).fetchone()


def mark_consumed(
    db: sqlite3.Connection,
    approval_id: int,
    consumed_at: str,
    consumed_by_type: str,
    consumed_by_id: int,
) -> int:
    """把 approval 標為已消耗、綁定到 consumed_by_type/id。WHERE consumed_at IS NULL
    防止 race 雙寫；回傳實際 UPDATE 行數（0 = 同 tx 內已被消耗、abort）。"""
    cursor = db.execute(
        "UPDATE approvals SET consumed_at = ?, consumed_by_type = ?, consumed_by_id = ? "
        "WHERE id = ? AND consumed_at IS NULL",
        (consumed_at, consumed_by_type, consumed_by_id, approval_id),
    )
    return cursor.rowcount


def mark_expired(db: sqlite3.Connection, approval_id: int) -> None:
    db.execute(
        "UPDATE approvals SET status = 'expired' WHERE id = ?",
        (approval_id,),
    )


def mark_decided(
    db: sqlite3.Connection,
    approval_id: int,
    decision: str,
    decided_by: str,
    decided_at: str,
) -> None:
    db.execute(
        "UPDATE approvals SET status = ?, approver = ?, decided_at = ? WHERE id = ?",
        (decision, decided_by, decided_at, approval_id),
    )


def insert_interaction_log(
    db: sqlite3.Connection,
    actor: str,
    action: str,
    target_type: str,
    target_id: int,
    detail: str,
    business_unit: str | None,
) -> None:
    """interaction_log 是 cross-cutting：approval / order / task / payment 都會寫。
    暫放這裡，若其他 module 也需要、未來抽到 shared/audit.py。"""
    db.execute(
        "INSERT INTO interaction_log "
        "(actor, action, target_type, target_id, detail, business_unit) "
        "VALUES (?,?,?,?,?,?)",
        (actor, action, target_type, target_id, detail, business_unit),
    )
