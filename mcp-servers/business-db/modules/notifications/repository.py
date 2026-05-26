"""Notifications repository — line_messages 查詢 + line_groups CRUD。

層次邊界（同 P2.1 pattern）：
- 進 sqlite3.Connection + filter primitives、出 Row / Row list / None
- 不 commit / rollback（transaction ownership 在 service）
- 知道 SQL（含 LIKE / COALESCE / NULLIF）、不知道 MCP
"""
import sqlite3

from shared.utils import _like_param


# ---- line_messages ----

def search_messages(
    db: sqlite3.Connection,
    query: str = "",
    user_id: str = "",
    user_name: str = "",
    direction: str = "",
    channel_id: str = "",
    days: int = 7,
    limit: int = 30,
) -> list[sqlite3.Row]:
    conditions: list[str] = []
    params: list = []

    if query:
        conditions.append("content LIKE ?")
        params.append(_like_param(query))
    if user_id:
        conditions.append("user_id = ?")
        params.append(user_id)
    if user_name:
        conditions.append("user_name LIKE ?")
        params.append(_like_param(user_name))
    if direction:
        conditions.append("direction = ?")
        params.append(direction)
    if channel_id:
        conditions.append("channel_id = ?")
        params.append(channel_id)

    conditions.append("created_at >= datetime('now', 'localtime', ?)")
    params.append(f"-{days} days")

    where = " AND ".join(conditions)
    params.append(limit)

    return db.execute(
        f"SELECT id, channel_id, user_id, user_name, direction, content, msg_type, "
        f"source_type, group_id, status, created_at "
        f"FROM line_messages WHERE {where} ORDER BY created_at DESC LIMIT ?",
        params,
    ).fetchall()


# ---- line_groups ----

def get_line_group(
    db: sqlite3.Connection, group_id: str, channel_id: str
) -> sqlite3.Row | None:
    return db.execute(
        "SELECT id FROM line_groups WHERE group_id = ? AND channel_id = ?",
        (group_id, channel_id),
    ).fetchone()


def insert_line_group(
    db: sqlite3.Connection,
    group_id: str,
    group_name: str,
    group_type: str,
    channel_id: str,
    purpose: str | None,
    notes: str | None,
) -> None:
    db.execute(
        "INSERT INTO line_groups (group_id, group_name, group_type, channel_id, purpose, notes) "
        "VALUES (?,?,?,?,?,?)",
        (group_id, group_name, group_type, channel_id, purpose, notes),
    )


def update_line_group(
    db: sqlite3.Connection,
    group_id: str,
    channel_id: str,
    group_name: str,
    group_type: str,
    purpose: str,
    notes: str,
) -> None:
    """COALESCE(NULLIF(?, ''), col) trick：空字串不覆寫原值。group_type 一律覆寫（必填）。"""
    db.execute(
        "UPDATE line_groups SET "
        "  group_name=COALESCE(NULLIF(?,''),group_name),"
        "  group_type=?,"
        "  purpose=COALESCE(NULLIF(?,''),purpose),"
        "  notes=COALESCE(NULLIF(?,''),notes),"
        "  updated_at=datetime('now','localtime') "
        "WHERE group_id=? AND channel_id=?",
        (group_name, group_type, purpose, notes, group_id, channel_id),
    )


def list_line_groups(
    db: sqlite3.Connection, group_type: str = "", channel_id: str = ""
) -> list[sqlite3.Row]:
    conditions: list[str] = []
    params: list = []
    if group_type:
        conditions.append("group_type = ?")
        params.append(group_type)
    if channel_id:
        conditions.append("channel_id = ?")
        params.append(channel_id)
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    return db.execute(
        f"SELECT group_id, group_name, group_type, channel_id, purpose, notes, created_at "
        f"FROM line_groups{where} ORDER BY created_at",
        params,
    ).fetchall()
