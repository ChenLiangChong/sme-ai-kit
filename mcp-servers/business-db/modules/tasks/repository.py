"""Tasks repository — tasks CRUD + 子任務查詢 + interaction_log。

層次邊界（同 P2.1 pattern）：
- 進 sqlite3.Connection + primitive、出 Row / id / int
- 不 commit / rollback（transaction ownership 在 service）
"""
import sqlite3

from shared.utils import _like_param, _safe_update

_TASK_COLUMNS = {"status", "completed_at", "assignee", "description", "priority"}


def get_parent_title(
    db: sqlite3.Connection, parent_task_id: int
) -> sqlite3.Row | None:
    return db.execute(
        "SELECT id, title FROM tasks WHERE id = ?", (parent_task_id,)
    ).fetchone()


def insert_task(
    db: sqlite3.Connection,
    title: str,
    description: str | None,
    assignee: str | None,
    priority: str,
    category: str,
    tags: str | None,
    business_unit: str | None,
    due_date: str | None,
    parent_task_id: int | None,
    created_by: str | None,
) -> int:
    cursor = db.execute(
        "INSERT INTO tasks "
        "(title, description, assignee, priority, category, tags, business_unit, "
        " due_date, parent_task_id, created_by) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (title, description, assignee, priority, category, tags, business_unit,
         due_date, parent_task_id, created_by),
    )
    return cursor.lastrowid


def get_task(db: sqlite3.Connection, task_id: int) -> sqlite3.Row | None:
    return db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()


def safe_update_task(
    db: sqlite3.Connection, task_id: int, updates: list[str], params: list
) -> None:
    _safe_update(db, "tasks", _TASK_COLUMNS, updates, params, "id = ?", [task_id])


def list_tasks(
    db: sqlite3.Connection,
    status: str = "",
    assignee: str = "",
    category: str = "",
    business_unit: str = "",
    parent_task_id: int = 0,
    limit: int = 20,
) -> list[sqlite3.Row]:
    """parent_task_id sentinel：
    - 0   = 只列頂層任務（parent_task_id IS NULL）← 對外預設語義
    - -1  = 不過濾（列出所有任務含子任務）
    - >0  = 列出該父任務的子任務
    """
    query = (
        "SELECT id, title, assignee, status, priority, category, business_unit, "
        "due_date, parent_task_id, created_at FROM tasks WHERE 1=1"
    )
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
    if business_unit:
        query += " AND business_unit = ?"
        params.append(business_unit)
    if parent_task_id == 0:
        query += " AND parent_task_id IS NULL"
    elif parent_task_id > 0:
        query += " AND parent_task_id = ?"
        params.append(parent_task_id)
    # parent_task_id < 0（sentinel -1）= 不過濾、不加條件
    query += (
        " ORDER BY CASE priority WHEN 'urgent' THEN 0 WHEN 'normal' THEN 1 "
        "ELSE 2 END, due_date LIMIT ?"
    )
    params.append(limit)
    return db.execute(query, params).fetchall()


def count_subtasks(db: sqlite3.Connection, task_id: int) -> int:
    return db.execute(
        "SELECT COUNT(*) as c FROM tasks WHERE parent_task_id = ?", (task_id,)
    ).fetchone()["c"]


def list_subtasks(
    db: sqlite3.Connection, parent_task_id: int
) -> list[sqlite3.Row]:
    return db.execute(
        "SELECT id, title, status FROM tasks WHERE parent_task_id = ? ORDER BY id",
        (parent_task_id,),
    ).fetchall()


def search_tasks(db: sqlite3.Connection, query: str) -> list[sqlite3.Row]:
    like = _like_param(query)
    return db.execute(
        "SELECT id, title, description, assignee, status, priority, due_date "
        "FROM tasks WHERE title LIKE ? OR description LIKE ? LIMIT 10",
        (like, like),
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
        "VALUES (?,?,'task',?,?,?)",
        (actor, action, target_id, detail, business_unit),
    )
