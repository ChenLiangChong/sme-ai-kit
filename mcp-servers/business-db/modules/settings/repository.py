"""Settings repository — system_settings / company / business_entities / session_handoffs SQL。

層次邊界（同 P2.1 pattern）：
- 進 sqlite3.Connection + primitive args、出 Row / id / None
- 不 commit / rollback（transaction ownership 在 service）
- 知道 schema（含 _safe_update 的 column whitelist），不知道 MCP
"""
import sqlite3

from shared.utils import _safe_update


# ---- audit ----

def insert_interaction_log(
    db: sqlite3.Connection,
    actor: str,
    action: str,
    target_type: str,
    target_id: int,
    detail: str,
    business_unit: str | None = None,
) -> None:
    db.execute(
        "INSERT INTO interaction_log (actor, action, target_type, target_id, detail, business_unit) "
        "VALUES (?,?,?,?,?,?)",
        (actor, action, target_type, target_id, detail, business_unit),
    )


# ---- system_settings ----

def get_setting_content(db: sqlite3.Connection, key: str) -> str | None:
    row = db.execute(
        "SELECT content FROM business_rules WHERE category = 'settings' "
        "AND title = ? AND superseded_by IS NULL",
        (key,),
    ).fetchone()
    return row["content"] if row else None


# ---- company（單例 id=1）----

_COMPANY_COLUMNS = {"name", "industry", "boss_name", "boss_title", "boss_line_id", "approval_threshold"}


def get_company(db: sqlite3.Connection) -> sqlite3.Row | None:
    return db.execute("SELECT * FROM company WHERE id = 1").fetchone()


def insert_company(
    db: sqlite3.Connection,
    name: str,
    industry: str | None,
    boss_name: str | None,
    boss_title: str,
    boss_line_id: str | None,
    approval_threshold: float,
) -> None:
    db.execute(
        "INSERT INTO company (id, name, industry, boss_name, boss_title, boss_line_id, approval_threshold) "
        "VALUES (1,?,?,?,?,?,?)",
        (name, industry, boss_name, boss_title, boss_line_id, approval_threshold),
    )


def safe_update_company(
    db: sqlite3.Connection, updates: list[str], params: list
) -> None:
    _safe_update(db, "company", _COMPANY_COLUMNS, updates, params, "id = 1", [])


# ---- business_entities ----

_ENTITY_COLUMNS = {"name", "channel_id", "approval_threshold", "notes"}


def get_entity(db: sqlite3.Connection, entity_id: str) -> sqlite3.Row | None:
    return db.execute(
        "SELECT * FROM business_entities WHERE id = ?", (entity_id,)
    ).fetchone()


def insert_entity(
    db: sqlite3.Connection,
    entity_id: str,
    name: str,
    channel_id: str | None,
    approval_threshold: float | None,
    notes: str | None,
) -> None:
    db.execute(
        "INSERT INTO business_entities (id, name, channel_id, approval_threshold, notes) "
        "VALUES (?,?,?,?,?)",
        (entity_id, name, channel_id, approval_threshold, notes),
    )


def safe_update_entity(
    db: sqlite3.Connection, entity_id: str, updates: list[str], params: list
) -> None:
    _safe_update(db, "business_entities", _ENTITY_COLUMNS, updates, params, "id = ?", [entity_id])


def list_entities(db: sqlite3.Connection) -> list[sqlite3.Row]:
    return db.execute("SELECT * FROM business_entities ORDER BY id").fetchall()


# ---- session_handoffs ----

def insert_handoff(
    db: sqlite3.Connection, session_id: str, summary: str, pending_items: str
) -> int:
    cursor = db.execute(
        "INSERT INTO session_handoffs (session_id, summary, pending_items) VALUES (?,?,?)",
        (session_id, summary, pending_items),
    )
    return cursor.lastrowid


def get_handoff_status(
    db: sqlite3.Connection, handoff_id: int
) -> sqlite3.Row | None:
    return db.execute(
        "SELECT id, status FROM session_handoffs WHERE id = ?", (handoff_id,)
    ).fetchone()


def mark_handoff_resolved(
    db: sqlite3.Connection, handoff_id: int, resolved_at: str, note: str | None
) -> None:
    db.execute(
        "UPDATE session_handoffs SET status='resolved', resolved_at=?, resolved_note=? WHERE id=?",
        (resolved_at, note, handoff_id),
    )
