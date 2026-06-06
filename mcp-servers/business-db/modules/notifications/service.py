"""Notifications service — LINE 訊息查詢 + 群組管理業務邏輯（格式化 + flow）。

層次邊界：transaction ownership 在這層，repository 不 commit。

安全（codex 全專案審 + 修補複審）：受限層的工具移除（search_line_messages / list_line_groups /
register_line_group）由 shared.floor_policy.LINE_DATA_TOOLS 在 MCP 註冊後物理移除負責（第一道）。
本層另加 defense-in-depth（第二道、萬一工具未被移除：floor-map 設定錯 / 名單漏列 / 全權限誤呼）：
- search_messages / list_line_groups（讀）開頭以 is_full_access() 早退、非全權限層回 ERROR；
- register_line_group（寫）走 writer_or_error 做 actor fail-closed + audit 具名。
**列級 channel/BU 縮限尚未實作**——可見度收斂在全權限層內仍是「全公司 LINE 訊息 / 群組」、不分 channel；
受限層由上述兩道整支擋掉。碼或回傳不宣稱「部門層只看自己 channel」。
"""
from shared.auth import writer_or_error
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
    # defense-in-depth（codex 修補複審 B-HIGH/E-HIGH）：本工具已由 floor_policy.LINE_DATA_TOOLS 從受限層
    # 物理移除，但 service 層再加一道——萬一工具未被移除（floor-map 設定錯 / 名單漏列），仍擋下受限層橫向
    # 讀全公司 LINE 訊息（無列級 channel/BU 縮限）。is_full_access()：operator('')/confidential 才放行。
    from shared.floor_policy import is_full_access
    if not is_full_access():
        return "ERROR: 此工具僅全權限層可用"
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
    actor: str = "",
) -> str:
    ch = channel_id or "default"
    with transaction() as db:
        # actor fail-closed（defense-in-depth、對齊 #10）：在任何 line_groups 寫入「之前」解析可信寫入者。
        # floored session 取 line-channel verified 員工名（忽略 agent 自填的 actor）、operator 用傳入值；
        # floored 但查無 verified LINE 脈絡 → __unverified__ → 擋下。防受限層只憑 group_id/channel_id
        # 覆寫任意群組的 group_type/purpose/notes 造成跨部門資料汙染。transaction() 對 return 字串仍會
        # commit、故必須在寫入前擋（writer_or_error 的契約）。
        audit_actor, err = writer_or_error(db, actor)
        if err:
            return err

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
        db.execute(
            "INSERT INTO interaction_log (actor, action, target_type, target_id, detail) "
            "VALUES (?,?,?,?,?)",
            (audit_actor, f"line_group_{verb}", "line_group", 0,
             f"group_id={group_id} channel={ch} type={group_type}"),
        )
    purpose_label = f" — {purpose}" if purpose else ""
    return f"群組{verb}：{group_name or group_id}（{group_type}）{purpose_label}"


def list_line_groups(group_type: str, channel_id: str) -> str:
    # defense-in-depth（codex 修補複審 B-HIGH/E-HIGH）：同 search_messages，已由 floor gate 移除、此為第二道。
    from shared.floor_policy import is_full_access
    if not is_full_access():
        return "ERROR: 此工具僅全權限層可用"
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
