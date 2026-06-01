"""Notifications tools — @mcp.tool 薄殼，業務邏輯在 service.py、SQL 在 repository.py。

Phase 2.4 三層化（套 P2.1 attachments pattern）。
"""
from shared.mcp_instance import mcp
from shared import escalation as _escalation

from . import service


@mcp.tool()
def search_line_messages(
    query: str = "",
    user_id: str = "",
    user_name: str = "",
    direction: str = "",
    channel_id: str = "",
    days: int = 7,
    limit: int = 30,
) -> str:
    """查詢 LINE 訊息歷史紀錄。

    Args:
        query: 搜尋關鍵字（模糊比對訊息內容）
        user_id: 篩選特定用戶的 LINE user ID
        user_name: 篩選特定用戶暱稱（模糊比對）
        direction: 篩選方向 — inbound（收到）| outbound（發出）| 留空=全部
        channel_id: 篩選 LINE OA channel（多品牌模式），留空=全部
        days: 查詢最近幾天（預設 7 天）
        limit: 最多回傳幾則（預設 30）
    """
    return service.search_messages(
        query=query,
        user_id=user_id,
        user_name=user_name,
        direction=direction,
        channel_id=channel_id,
        days=days,
        limit=limit,
    )


@mcp.tool()
def register_line_group(
    group_id: str,
    group_name: str = "",
    group_type: str = "other",
    channel_id: str = "",
    purpose: str = "",
    notes: str = "",
) -> str:
    """註冊 LINE 群組。當 bot 加入新群組或老闆告知群組用途時呼叫。

    Args:
        group_id: LINE 群組 ID（從 channel tag 的 chat_id 取得）
        group_name: 群組名稱（例：公司工作群、經銷商群）
        group_type: 群組類型 — work（工作）| customer（客戶）| supplier（供應商）| marketing（行銷）| other
        channel_id: 來自哪個 LINE OA（多品牌模式），留空=default
        purpose: 一句話描述群組功能（例：品牌 X 內勤訂單協調、ERP 系統供應商交期追蹤）
        notes: 備註（成員、特殊 SOP、限制等自由文字）
    """
    return service.register_line_group(
        group_id=group_id,
        group_name=group_name,
        group_type=group_type,
        channel_id=channel_id,
        purpose=purpose,
        notes=notes,
    )


@mcp.tool()
def list_line_groups(group_type: str = "", channel_id: str = "") -> str:
    """列出所有已註冊的 LINE 群組。

    Args:
        group_type: 篩選類型 — work | customer | supplier | marketing | other | 留空=全部
        channel_id: 篩選 LINE OA channel（多品牌模式），留空=全部
    """
    return service.list_line_groups(group_type=group_type, channel_id=channel_id)


@mcp.tool()
def list_pending_escalations(limit: int = 50) -> str:
    """列出待投遞的主管上報（status=pending、已解析收件人）。全權限層限定（部門層由 floor gate 移除）。

    給 claude -p 通報投遞器用：讀出後逐筆用 mcp__line__reply 推給「該筆的 target_line_user_id」
    （收件人一律照 row、不可自行決定），再呼叫 mark_escalation_sent(id)。
    回 JSON：{"pending":[{id,event_type,summary,actor,business_unit,target_line_user_id,channel_id}],"count"}。

    Args:
        limit: 最多回幾筆（預設 50）
    """
    return _escalation.list_pending_for_notifier(limit=limit)


@mcp.tool()
def mark_escalation_sent(escalation_id: int, sent_text: str = "") -> str:
    """標記某筆主管上報已送達（status pending→sent）+ 落實際送出內容供稽核。投遞器推送成功後呼叫。

    rowcount guard 防重複送（已 sent / 不存在 → 回無法標記、不報錯）。

    Args:
        escalation_id: pending_escalations 的 id
        sent_text: 投遞器真正推給主管的完整文字（系統落 interaction_log 留底「實際送出了什麼」）
    """
    return _escalation.mark_sent_tool(escalation_id, sent_text=sent_text)
