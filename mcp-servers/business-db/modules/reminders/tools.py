"""Reminder tools — @mcp.tool 薄殼，邏輯在 shared.reminders（與 standalone dispatcher 共用）。

floor gate：schedule/cancel/list 對非全權限層移除（見 floor_policy.REMINDER_ADMIN_TOOLS）——
排程＝定時推播任意對象、broadcast-ish，只機密層/operator 可排；機密層 daemon（full access）保留 →
可自助排程，不必每次喊老闆、也不必開 crontab 寫權限（不拆 sandbox 第一道牆）。
"""
from shared.mcp_instance import mcp

from shared import reminders


@mcp.tool()
def schedule_reminder(
    title: str,
    message: str,
    target_id: str,
    recurrence: str = "once",
    fire_at: str = "",
    channel_id: str = "",
    target_type: str = "user",
    business_unit: str = "",
    note: str = "",
    created_by: str = "",
) -> str:
    """排程一則提醒，交由系統定時推播（OS-cron 級可靠、由笨投遞器送；你/系統不碰 crontab）。

    用途：把週期或一次性提醒交給系統定時推送，取代「每次開機才手動帶出來、會漏」。
    例：某筆急單每日盯到出貨 → recurrence='daily'、note='盯到 order #X 出貨'，出貨後呼叫 cancel_reminder。
        每週盯專案進度 → recurrence='weekly'；每月 25 日請款提醒 → recurrence='monthly'；平日提醒 → recurrence='weekdays'。

    Args:
        title: 一行摘要（給 list_reminders / 老闆看）
        message: 實際推播給對象的完整內文（直接照送、不加系統抬頭，請寫成可直接讀的訊息）
        target_id: 收件 LINE userId 或 groupId（push 的 to）
        recurrence: once（一次）| daily（每日）| weekdays（平日一~五）| weekly（每 7 天）| monthly（每月、月底自動夾日）
        fire_at: 觸發時間。'YYYY-MM-DD HH:MM'（明確時點）或 'HH:MM'（時刻、自動取下一個未來時點）
        channel_id: 用哪個 OA 推（空=default OA）
        target_type: user | group（僅標示；push 一律用 target_id）
        business_unit: 所屬事業體（留空=全域）
        note: 完成條件 / 備註（如「盯到 order #123 出貨」），不外送、只供 list 與你自己追蹤
        created_by: 排程者
    """
    return reminders.schedule_reminder(
        title=title, message=message, target_id=target_id, recurrence=recurrence,
        fire_at=fire_at, channel_id=channel_id, target_type=target_type,
        business_unit=business_unit, note=note, created_by=created_by,
    )


@mcp.tool()
def cancel_reminder(reminder_id: int, reason: str = "") -> str:
    """取消一則排程提醒（如盯催的事已完成、不需再提醒）。

    Args:
        reminder_id: 提醒 ID
        reason: 取消原因（選填、留稽核）
    """
    return reminders.cancel_reminder(reminder_id, reason)


@mcp.tool()
def list_reminders(status: str = "active", business_unit: str = "", limit: int = 30) -> str:
    """列出排程提醒。

    Args:
        status: 篩選狀態 active | done | cancelled | failed（留空=全部）
        business_unit: 篩選事業體
        limit: 最多顯示幾筆
    """
    return reminders.list_reminders(status=status, business_unit=business_unit, limit=limit)
