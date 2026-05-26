"""Settings tools — @mcp.tool 薄殼，業務邏輯在 service.py、SQL 在 repository.py。

Phase 2.3 三層化（套 P2.1 attachments pattern）。
"""
from shared.mcp_instance import mcp

from . import service


@mcp.tool()
def get_setting(key: str) -> str:
    """讀取系統設定（從 business_rules category='settings' 讀取）。

    Args:
        key: 設定名稱（如 marketing_frequency_limit, overdue_days_warning）
    """
    return service.read_setting(key)


@mcp.tool()
def update_company(
    name: str = "",
    industry: str = "",
    boss_name: str = "",
    boss_title: str = "",
    boss_line_id: str = "__SKIP__",
    approval_threshold: float = -1,
) -> str:
    """更新公司基本資訊（company 表 id=1）。首次呼叫會自動建立。

    Args:
        name: 公司名稱
        industry: 產業別
        boss_name: 老闆名
        boss_title: 老闆稱謂（如「總經理」「老闆」「執行長」）
        boss_line_id: 老闆的 LINE User ID（用於 LINE 通知路由，傳空字串清除）
        approval_threshold: 審核門檻金額（-1=不更新）
    """
    return service.upsert_company(
        name=name,
        industry=industry,
        boss_name=boss_name,
        boss_title=boss_title,
        boss_line_id=boss_line_id,
        approval_threshold=approval_threshold,
    )


@mcp.tool()
def register_business_entity(
    entity_id: str,
    name: str,
    channel_id: str = "",
    approval_threshold: float = -1,
    notes: str = "",
) -> str:
    """登錄或更新事業體。用於多事業體/多品牌場景。

    Args:
        entity_id: 事業體 ID（如 brand_c, brand_d），也作為 business_unit 值
        name: 事業體名稱
        channel_id: 對應的 LINE OA channel_id
        approval_threshold: 該事業體的審核門檻（-1=沿用公司預設）
        notes: 備註
    """
    return service.upsert_entity(
        entity_id=entity_id,
        name=name,
        channel_id=channel_id,
        approval_threshold=approval_threshold,
        notes=notes,
    )


@mcp.tool()
def list_business_entities() -> str:
    """列出所有已登錄的事業體。"""
    return service.list_entities()


@mcp.tool()
def save_session_handoff(session_id: str, summary: str, pending_items: str = "[]") -> str:
    """儲存 session 交接資訊。在關閉 session 或定期保存時呼叫。

    新建的 handoff 預設 status='active'。新 session 接手後請呼叫 resolve_handoff 標記完成，
    否則下次 get_context_summary 還會撈到（變成過期 handoff trap）。

    Args:
        session_id: 當前 session ID
        summary: 交接摘要（目前在做什麼、等待什麼）
        pending_items: JSON 格式的待處理項目清單
    """
    return service.save_handoff(session_id, summary, pending_items)


@mcp.tool()
def resolve_handoff(handoff_id: int, note: str = "") -> str:
    """標記 session_handoff 為已接手。新 session 讀到 handoff 並完成承接後呼叫。

    標記後 get_context_summary 就不會再撈到這筆（但 audit log 保留）。

    Args:
        handoff_id: 要標記的 handoff id（從 get_context_summary 或 save_session_handoff 回傳）
        note: 可選備註（如「接手完成、已切到 P2.1」）
    """
    return service.resolve_handoff(handoff_id, note)
