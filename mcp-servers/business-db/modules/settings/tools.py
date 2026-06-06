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
    actor_user_id: str = "",
) -> str:
    """更新公司基本資訊（company 表 id=1）。首次呼叫會自動建立。

    需 admin 權限（改通知路由 boss_line_id / 審核門檻 = 高權動作）。floored session 由系統取
    verified user_id 驗權、agent 自填的 actor_user_id 無效；operator（無 SME_FLOOR）才採傳入值。

    Args:
        name: 公司名稱
        industry: 產業別
        boss_name: 老闆名
        boss_title: 老闆稱謂（如「總經理」「老闆」「執行長」）
        boss_line_id: 老闆的 LINE User ID（用於 LINE 通知路由，傳空字串清除）
        approval_threshold: 審核門檻金額（-1=不更新）
        actor_user_id: 操作者 LINE user_id（floored 由系統覆寫；operator 可省略）
    """
    return service.upsert_company(
        name=name,
        industry=industry,
        boss_name=boss_name,
        boss_title=boss_title,
        boss_line_id=boss_line_id,
        approval_threshold=approval_threshold,
        actor_user_id=actor_user_id,
    )


@mcp.tool()
def register_business_entity(
    entity_id: str,
    name: str,
    channel_id: str = "",
    approval_threshold: float = -1,
    notes: str = "",
    actor_user_id: str = "",
) -> str:
    """登錄或更新事業體。用於多事業體/多品牌場景。

    需 admin 權限（設定 OA→BU 映射 / 該事業體審核門檻 = 高權動作）。floored session 由系統取
    verified user_id 驗權、agent 自填無效；operator（無 SME_FLOOR）才採傳入值。

    Args:
        entity_id: 事業體 ID（如 brand_c, brand_d），也作為 business_unit 值
        name: 事業體名稱
        channel_id: 對應的 LINE OA channel_id
        approval_threshold: 該事業體的審核門檻（-1=沿用公司預設）
        notes: 備註
        actor_user_id: 操作者 LINE user_id（floored 由系統覆寫；operator 可省略）
    """
    return service.upsert_entity(
        entity_id=entity_id,
        name=name,
        channel_id=channel_id,
        approval_threshold=approval_threshold,
        notes=notes,
        actor_user_id=actor_user_id,
    )


@mcp.tool()
def list_business_entities() -> str:
    """列出所有已登錄的事業體。"""
    return service.list_entities()


@mcp.tool()
def save_session_handoff(
    session_id: str, summary: str, pending_items: str = "[]", actor_user_id: str = ""
) -> str:
    """儲存 session 交接資訊。在關閉 session 或定期保存時呼叫。

    新建的 handoff 預設 status='active'。新 session 接手後請呼叫 resolve_handoff 標記完成，
    否則下次 get_context_summary 還會撈到（變成過期 handoff trap）。

    handoff = 跨 session 控制面，寫入前 actor fail-closed：floored session 由系統取 verified
    user_id、查無 verified LINE 脈絡擋下；operator（無 SME_FLOOR）放行。

    Args:
        session_id: 當前 session ID
        summary: 交接摘要（目前在做什麼、等待什麼）
        pending_items: JSON 格式的待處理項目清單
        actor_user_id: 操作者 LINE user_id（floored 由系統覆寫；operator 可省略）
    """
    return service.save_handoff(session_id, summary, pending_items, actor_user_id)


@mcp.tool()
def resolve_handoff(handoff_id: int, note: str = "", actor_user_id: str = "") -> str:
    """標記 session_handoff 為已接手。新 session 讀到 handoff 並完成承接後呼叫。

    標記後 get_context_summary 就不會再撈到這筆（但 audit log 保留）。

    寫入前 actor fail-closed（同 save_session_handoff）：floored 取 verified user_id、
    查無 verified LINE 脈絡擋下；operator 放行。

    Args:
        handoff_id: 要標記的 handoff id（從 get_context_summary 或 save_session_handoff 回傳）
        note: 可選備註（如「接手完成、已切到 P2.1」）
        actor_user_id: 操作者 LINE user_id（floored 由系統覆寫；operator 可省略）
    """
    return service.resolve_handoff(handoff_id, note, actor_user_id)
