"""Attachments repository — 純 DB access、不含業務邏輯。

層次邊界：
- 進來：sqlite3.Connection + primitive args
- 出去：lastrowid / sqlite3.Row list
- 不知道 MCP、不做格式化、不推斷業務值（如 file_type）
- **不 commit / rollback** — transaction ownership 在 service，repository 只 execute。
  這樣未來 service 要包多個 repository call 進同一 transaction（cross-table 寫入）才能正確 rollback。
"""
import sqlite3


def target_exists(db: sqlite3.Connection, table: str, target_id: int) -> bool:
    """檢查 target_id 在 table 是否存在。table 由 service 的白名單映射來（非使用者輸入）、
    可安全拼進 SQL；target_id parameterized。"""
    row = db.execute(
        f"SELECT 1 FROM {table} WHERE id = ? LIMIT 1", (target_id,)
    ).fetchone()
    return row is not None


def insert(
    db: sqlite3.Connection,
    target_type: str,
    target_id: int,
    file_path: str,
    file_type: str,
    file_name: str,
    description: str | None,
    uploaded_by: str | None,
) -> int:
    cursor = db.execute(
        "INSERT INTO attachments "
        "(target_type, target_id, file_path, file_type, file_name, description, uploaded_by) "
        "VALUES (?,?,?,?,?,?,?)",
        (target_type, target_id, file_path, file_type, file_name, description, uploaded_by),
    )
    return cursor.lastrowid


def list_by_target(
    db: sqlite3.Connection, target_type: str, target_id: int
) -> list[sqlite3.Row]:
    return db.execute(
        "SELECT id, file_path, file_type, file_name, description, uploaded_by, created_at "
        "FROM attachments WHERE target_type = ? AND target_id = ? ORDER BY created_at",
        (target_type, target_id),
    ).fetchall()
