"""Deadlines repository — matters / deadlines CRUD + interaction_log。

層次邊界（同 tasks pattern）：
- 進 sqlite3.Connection + primitive、出 Row / id / int
- 不 commit / rollback（transaction ownership 在 service）
"""
import sqlite3

from shared.utils import _like_param


# ───────────────────────── matters ─────────────────────────

def insert_matter(
    db: sqlite3.Connection,
    matter_no: str | None,
    title: str,
    client_name: str | None,
    practice_area: str | None,
    court: str | None,
    court_case_no: str | None,
    stage: str | None,
    status: str,
    lead_attorney: str | None,
    has_local_agent: int,
    confidential: int,
    business_unit: str | None,
    opened_at: str | None,
) -> int:
    cursor = db.execute(
        "INSERT INTO matters "
        "(matter_no, title, client_name, practice_area, court, court_case_no, stage, "
        " status, lead_attorney, has_local_agent, confidential, business_unit, opened_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (matter_no, title, client_name, practice_area, court, court_case_no, stage,
         status, lead_attorney, has_local_agent, confidential, business_unit, opened_at),
    )
    return cursor.lastrowid


def get_matter(db: sqlite3.Connection, matter_id: int) -> sqlite3.Row | None:
    return db.execute("SELECT * FROM matters WHERE id = ?", (matter_id,)).fetchone()


def get_matter_by_no(db: sqlite3.Connection, matter_no: str) -> sqlite3.Row | None:
    return db.execute("SELECT * FROM matters WHERE matter_no = ?", (matter_no,)).fetchone()


def list_matters(
    db: sqlite3.Connection,
    status: str = "",
    lead_attorney: str = "",
    limit: int = 20,
    include_confidential: bool = True,
) -> list[sqlite3.Row]:
    query = "SELECT * FROM matters WHERE 1=1"
    params: list = []
    if status:
        query += " AND status = ?"
        params.append(status)
    if lead_attorney:
        query += " AND lead_attorney = ?"
        params.append(lead_attorney)
    if not include_confidential:
        query += " AND confidential = 0"  # 機密軸：非全權限層過濾（同 query_knowledge migration 006）
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    return db.execute(query, params).fetchall()


def find_matter_by_party(
    db: sqlite3.Connection,
    party_name: str,
    limit: int = 20,
    include_confidential: bool = True,
) -> list[sqlite3.Row]:
    """用當事人/委任人名字模糊比對案件（client_name LIKE）。也比對案由與案號、放寬命中。"""
    like = _like_param(party_name)
    query = (
        "SELECT * FROM matters "
        "WHERE (client_name LIKE ? OR title LIKE ? OR matter_no LIKE ?)"
    )
    params: list = [like, like, like]
    if not include_confidential:
        query += " AND confidential = 0"  # 機密軸：非全權限層過濾
    query += " ORDER BY CASE status WHEN 'open' THEN 0 ELSE 1 END, id DESC LIMIT ?"
    params.append(limit)
    return db.execute(query, params).fetchall()


# ───────────────────────── deadlines ─────────────────────────

def insert_deadline(db: sqlite3.Connection, fields: dict) -> int:
    cols = list(fields.keys())
    placeholders = ",".join("?" for _ in cols)
    cursor = db.execute(
        f"INSERT INTO deadlines ({','.join(cols)}) VALUES ({placeholders})",
        [fields[c] for c in cols],
    )
    return cursor.lastrowid


def get_deadline(db: sqlite3.Connection, deadline_id: int) -> sqlite3.Row | None:
    return db.execute("SELECT * FROM deadlines WHERE id = ?", (deadline_id,)).fetchone()


def list_deadlines(
    db: sqlite3.Connection,
    matter_id: int = 0,
    status: str = "",
    assignee: str = "",
    limit: int = 20,
    include_confidential: bool = True,
) -> list[sqlite3.Row]:
    query = (
        "SELECT d.*, m.matter_no AS matter_no, m.title AS matter_title "
        "FROM deadlines d JOIN matters m ON m.id = d.matter_id WHERE 1=1"
    )
    params: list = []
    if matter_id:
        query += " AND d.matter_id = ?"
        params.append(matter_id)
    if status:
        query += " AND d.status = ?"
        params.append(status)
    if assignee:
        query += " AND d.assignee = ?"
        params.append(assignee)
    if not include_confidential:
        query += " AND m.confidential = 0"  # 機密軸：時限隨母案件機密性過濾
    # pending 在前、再按內部期限升冪（最急在前）
    query += (
        " ORDER BY CASE d.status WHEN 'pending' THEN 0 ELSE 1 END, "
        " d.internal_deadline ASC LIMIT ?"
    )
    params.append(limit)
    return db.execute(query, params).fetchall()


def list_upcoming_deadlines(
    db: sqlite3.Connection,
    assignee: str = "",
    within_days: int = 0,
    limit: int = 50,
    include_confidential: bool = True,
) -> list[sqlite3.Row]:
    """列出 status='pending' 的時限，按 internal_deadline 升冪（最急在前）。

    供每日彙整與查詢。only pending（已遞交/逾期/取消不入）。
    - assignee：篩負責律師
    - within_days：>0 時只回 internal_deadline 在「今天起 N 個日曆日內」的（含逾期 pending）
    """
    query = (
        "SELECT d.*, m.matter_no AS matter_no, m.title AS matter_title, "
        "       m.lead_attorney AS lead_attorney "
        "FROM deadlines d JOIN matters m ON m.id = d.matter_id "
        "WHERE d.status = 'pending'"
    )
    params: list = []
    if not include_confidential:
        query += " AND m.confidential = 0"  # 機密軸：時限隨母案件機密性過濾
    if assignee:
        query += " AND d.assignee = ?"
        params.append(assignee)
    if within_days and within_days > 0:
        # date(now,localtime)+N 日；含逾期（internal_deadline 已過 today 的 pending 也撈出）
        query += " AND d.internal_deadline <= date('now', 'localtime', ? || ' days')"
        params.append(str(int(within_days)))
    # 內部期限升冪（NULL 殿後）、最急在前
    query += (
        " ORDER BY CASE WHEN d.internal_deadline IS NULL THEN 1 ELSE 0 END, "
        " d.internal_deadline ASC LIMIT ?"
    )
    params.append(limit)
    return db.execute(query, params).fetchall()


def mark_filed(
    db: sqlite3.Connection, deadline_id: int, filed_at: str, filed_by: str | None
) -> int:
    cur = db.execute(
        "UPDATE deadlines SET status='filed', filed_at=?, filed_by=? "
        "WHERE id=? AND status='pending'",
        (filed_at, filed_by, deadline_id),
    )
    return cur.rowcount


def mark_reviewed(
    db: sqlite3.Connection, deadline_id: int, reviewed_by: str | None, reviewed_at: str
) -> int:
    """律師覆核留痕：寫 reviewed_by/reviewed_at 並解除 needs_manual_review（具名人已確認計算）。
    只對未取消的時限生效（cancelled 不可再覆核）。回 rowcount。"""
    cur = db.execute(
        "UPDATE deadlines SET reviewed_by=?, reviewed_at=?, needs_manual_review=0 "
        "WHERE id=? AND status != 'cancelled'",
        (reviewed_by, reviewed_at, deadline_id),
    )
    return cur.rowcount


def mark_calendared(
    db: sqlite3.Connection,
    deadline_id: int,
    calendar_event_id: str,
    calendar_provider: str | None,
    synced_at: str,
) -> int:
    """落回外部行事曆 event_id（calendar-agnostic，SPEC『寫兩處』的回填）。"""
    cur = db.execute(
        "UPDATE deadlines SET calendar_event_id=?, calendar_provider=?, calendar_synced_at=? "
        "WHERE id=?",
        (calendar_event_id, calendar_provider, synced_at, deadline_id),
    )
    return cur.rowcount


# ───────────────────────── pending_intakes（#H2 待確認跟催）─────────────────────────

def insert_pending_intake(db: sqlite3.Connection, fields: dict) -> int:
    cols = list(fields.keys())
    placeholders = ",".join("?" for _ in cols)
    cursor = db.execute(
        f"INSERT INTO pending_intakes ({','.join(cols)}) VALUES ({placeholders})",
        [fields[c] for c in cols],
    )
    return cursor.lastrowid


def get_pending_intake(db: sqlite3.Connection, intake_id: int) -> sqlite3.Row | None:
    return db.execute(
        "SELECT p.*, m.matter_no AS matter_no, m.title AS matter_title, "
        "       m.confidential AS matter_confidential "
        "FROM pending_intakes p LEFT JOIN matters m ON m.id = p.matter_id "
        "WHERE p.id = ?",
        (intake_id,),
    ).fetchone()


def list_awaiting_intakes(
    db: sqlite3.Connection, limit: int = 50, include_confidential: bool = True
) -> list[sqlite3.Row]:
    """待確認（status='awaiting'）的暫存時限，最舊在前（等最久的最該催）。

    機密軸過濾在 SQL 端（codex#中）：非全權限層傳 include_confidential=False，機密母案件的暫存
    在 LIMIT 之前就排除——否則「先 LIMIT 再 Python 過濾」會被前面的機密列吃掉配額、把可見 backlog
    靜默吞成「空」。NULL matter（未建案）視為非機密、一律保留。
    """
    query = (
        "SELECT p.*, m.matter_no AS matter_no, m.title AS matter_title, "
        "       m.confidential AS matter_confidential "
        "FROM pending_intakes p LEFT JOIN matters m ON m.id = p.matter_id "
        "WHERE p.status = 'awaiting'"
    )
    if not include_confidential:
        query += " AND (m.confidential IS NULL OR m.confidential = 0)"
    query += " ORDER BY p.created_at ASC, p.id ASC LIMIT ?"
    return db.execute(query, (limit,)).fetchall()


def resolve_pending_intake(
    db: sqlite3.Connection,
    intake_id: int,
    status: str,
    resolved_at: str,
    resolved_by: str | None,
    resolved_deadline_id: int | None,
) -> int:
    """把待確認 row 收掉（confirmed / discarded）。只在 status='awaiting' 時生效（rowcount guard
    防重複收 / 防把已收的再改）。回 rowcount。"""
    cur = db.execute(
        "UPDATE pending_intakes "
        "SET status=?, resolved_at=?, resolved_by=?, resolved_deadline_id=? "
        "WHERE id=? AND status='awaiting'",
        (status, resolved_at, resolved_by, resolved_deadline_id, intake_id),
    )
    return cur.rowcount


# ───────────────────────── interaction_log ─────────────────────────

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
