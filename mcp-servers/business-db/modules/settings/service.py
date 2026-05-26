"""Settings service — system / company / business_entities / session_handoffs 業務邏輯。

層次邊界：transaction ownership 在這層，repository 不 commit。
"""
from shared.db import _now, get_db, transaction

from . import repository


# ---- system_settings ----

def read_setting(key: str) -> str:
    db = get_db()
    try:
        content = repository.get_setting_content(db, key)
        return content if content is not None else f"（未設定 {key}）"
    finally:
        db.close()


# ---- company ----

def upsert_company(
    name: str,
    industry: str,
    boss_name: str,
    boss_title: str,
    boss_line_id: str,
    approval_threshold: float,
) -> str:
    """name/industry/... 留空（或 boss_line_id='__SKIP__'）= 不更新；首次呼叫自動建立。"""
    with transaction() as db:
        existing = repository.get_company(db)
        if not existing:
            repository.insert_company(
                db,
                name=name or "未設定",
                industry=industry or None,
                boss_name=boss_name or None,
                boss_title=boss_title or "老闆",
                boss_line_id=boss_line_id if boss_line_id != "__SKIP__" else None,
                approval_threshold=approval_threshold if approval_threshold >= 0 else 5000,
            )
            return f"公司資訊已建立：{name or '未設定'}"

        updates: list[str] = []
        params: list = []
        if name:
            updates.append("name = ?"); params.append(name)
        if industry:
            updates.append("industry = ?"); params.append(industry)
        if boss_name:
            updates.append("boss_name = ?"); params.append(boss_name)
        if boss_title:
            updates.append("boss_title = ?"); params.append(boss_title)
        if boss_line_id != "__SKIP__":
            updates.append("boss_line_id = ?"); params.append(boss_line_id or None)
        if approval_threshold >= 0:
            updates.append("approval_threshold = ?"); params.append(approval_threshold)

        if not updates:
            return "沒有指定要更新的欄位。"

        repository.safe_update_company(db, updates, params)
        changed = ", ".join(u.split(" = ")[0] for u in updates)
        return f"公司資訊已更新（{changed}）"


# ---- business_entities ----

def upsert_entity(
    entity_id: str,
    name: str,
    channel_id: str,
    approval_threshold: float,
    notes: str,
) -> str:
    with transaction() as db:
        existing = repository.get_entity(db, entity_id)
        if existing:
            updates: list[str] = []
            params: list = []
            if name:
                updates.append("name = ?"); params.append(name)
            if channel_id:
                updates.append("channel_id = ?"); params.append(channel_id)
            if approval_threshold >= 0:
                updates.append("approval_threshold = ?"); params.append(approval_threshold)
            if notes:
                updates.append("notes = ?"); params.append(notes)
            if not updates:
                return "沒有指定要更新的欄位。"
            repository.safe_update_entity(db, entity_id, updates, params)
            return f"事業體 {entity_id} ({name}) 已更新"

        repository.insert_entity(
            db,
            entity_id=entity_id,
            name=name,
            channel_id=channel_id or None,
            approval_threshold=approval_threshold if approval_threshold >= 0 else None,
            notes=notes or None,
        )
        return f"事業體 {entity_id} ({name}) 已登錄"


def list_entities() -> str:
    db = get_db()
    try:
        rows = repository.list_entities(db)
        if not rows:
            return "目前沒有登錄任何事業體。使用 register_business_entity 登錄。"
        lines = [f"## 事業體（{len(rows)} 個）"]
        for e in rows:
            threshold_str = (
                f"審核門檻 NT${e['approval_threshold']:,.0f}"
                if e["approval_threshold"] else "沿用公司預設"
            )
            channel_str = f"LINE OA: {e['channel_id']}" if e["channel_id"] else "未綁定 LINE OA"
            lines.append(f"- **{e['id']}** — {e['name']} | {channel_str} | {threshold_str}")
        return "\n".join(lines)
    finally:
        db.close()


# ---- session_handoffs ----

def save_handoff(session_id: str, summary: str, pending_items: str) -> str:
    with transaction() as db:
        handoff_id = repository.insert_handoff(db, session_id, summary, pending_items)
    return f"Session 交接 #{handoff_id} 已儲存（{session_id[:8]}...）"


def resolve_handoff(handoff_id: int, note: str) -> str:
    with transaction() as db:
        row = repository.get_handoff_status(db, handoff_id)
        if not row:
            return f"ERROR: 找不到 handoff #{handoff_id}"
        if row["status"] == "resolved":
            return f"handoff #{handoff_id} 已是 resolved 狀態，無需重複"
        repository.mark_handoff_resolved(db, handoff_id, _now(), note or None)
    return f"handoff #{handoff_id} 已標記 resolved" + (f"（{note}）" if note else "")
