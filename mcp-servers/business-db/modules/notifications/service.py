"""Notifications service — LINE 訊息查詢 + 群組管理業務邏輯（格式化 + flow）。

層次邊界：transaction ownership 在這層，repository 不 commit。
"""
from shared.db import get_db, transaction

from . import repository

_GROUP_TYPE_ICON = {
    "work": "[工作]",
    "customer": "[客戶]",
    "supplier": "[供應商]",
    "marketing": "[行銷]",
    "other": "[其他]",
}


def search_messages(
    query: str,
    user_id: str,
    user_name: str,
    direction: str,
    channel_id: str,
    days: int,
    limit: int,
) -> str:
    db = get_db()
    try:
        rows = repository.search_messages(
            db,
            query=query,
            user_id=user_id,
            user_name=user_name,
            direction=direction,
            channel_id=channel_id,
            days=days,
            limit=limit,
        )
        if not rows:
            return "沒有找到符合條件的 LINE 訊息。"
        lines = [f"## LINE 訊息（{len(rows)} 則）\n"]
        for m in rows:
            arrow = "→" if m["direction"] == "outbound" else "←"
            src = ""
            if m["source_type"] == "group" and m["group_id"]:
                src = f" [群組 {m['group_id']}]"
            name = m["user_name"] or m["user_id"][:8]
            chat_id = m["group_id"] if m["source_type"] == "group" and m["group_id"] else m["user_id"]
            ch_label = (
                f" [{m['channel_id']}]"
                if m["channel_id"] and m["channel_id"] != "default" else ""
            )
            lines.append(
                f"- {arrow} [{m['created_at']}]{ch_label} **{name}** "
                f"(user_id={m['user_id']}){src} (chat_id={chat_id}): {m['content'][:200]}"
            )
        return "\n".join(lines)
    finally:
        db.close()


def register_line_group(
    group_id: str,
    group_name: str,
    group_type: str,
    channel_id: str,
    purpose: str,
    notes: str,
) -> str:
    ch = channel_id or "default"
    with transaction() as db:
        existing = repository.get_line_group(db, group_id, ch)
        if existing:
            repository.update_line_group(
                db,
                group_id=group_id,
                channel_id=ch,
                group_name=group_name,
                group_type=group_type,
                purpose=purpose,
                notes=notes,
            )
            verb = "已更新"
        else:
            repository.insert_line_group(
                db,
                group_id=group_id,
                group_name=group_name,
                group_type=group_type,
                channel_id=ch,
                purpose=purpose or None,
                notes=notes or None,
            )
            verb = "已註冊"
    purpose_label = f" — {purpose}" if purpose else ""
    return f"群組{verb}：{group_name or group_id}（{group_type}）{purpose_label}"


def list_line_groups(group_type: str, channel_id: str) -> str:
    db = get_db()
    try:
        rows = repository.list_line_groups(db, group_type, channel_id)
        if not rows:
            return "目前沒有已註冊的 LINE 群組。"
        lines = [f"## LINE 群組（{len(rows)} 個）\n"]
        for g in rows:
            icon = _GROUP_TYPE_ICON.get(g["group_type"], "[其他]")
            name = g["group_name"] or g["group_id"][:12]
            lines.append(f"- {icon} **{name}** ({g['group_type']}) — chat_id={g['group_id']}")
            if g["purpose"]:
                lines.append(f"  功能：{g['purpose']}")
            if g["notes"]:
                lines.append(f"  備註：{g['notes']}")
        return "\n".join(lines)
    finally:
        db.close()
