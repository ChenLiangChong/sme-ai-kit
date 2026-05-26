"""Approvals tools — @mcp.tool 薄殼，業務邏輯在 service.py、SQL 在 repository.py。

Phase 2.5 三層化（套 P2.1 attachments pattern）。
"""
from shared.mcp_instance import mcp

from . import service


@mcp.tool()
def create_approval(
    type: str,
    summary: str,
    detail: str = "",
    approver: str = "",
    requester: str = "",
    business_unit: str = "",
) -> str:
    """建立審核請求（HITL 人機協作）。

    Args:
        type: 審核類型（email, purchase, refund, announcement, other）
        summary: 摘要
        detail: 詳細內容（JSON 或純文字）
        approver: 指定審核人
        requester: 申請人名稱（留空=system）
        business_unit: 所屬事業體（如 brand_d, content），留空=不分
    """
    return service.create(
        type_=type,
        summary=summary,
        detail=detail,
        approver=approver,
        requester=requester,
        business_unit=business_unit,
    )


@mcp.tool()
def get_approval(approval_id: int) -> str:
    """查單筆 approval 完整內容（含 detail JSON / status / consumed_at / decided_by 等）。

    給失敗情境判讀使用：當 record_transaction / approve_leave 等被 gate 擋下時，
    agent 用此 tool 查 approval 現況決定如何回報老闆，不要繞 sqlite。

    Args:
        approval_id: 審核 ID
    """
    return service.get_approval(approval_id=approval_id)


@mcp.tool()
def resolve_approval(approval_id: int, decision: str, decided_by: str) -> str:
    """處理審核結果。

    Args:
        approval_id: 審核請求 ID
        decision: 決定 — approved | rejected
        decided_by: 審核人姓名
    """
    return service.resolve(approval_id=approval_id, decision=decision, decided_by=decided_by)
