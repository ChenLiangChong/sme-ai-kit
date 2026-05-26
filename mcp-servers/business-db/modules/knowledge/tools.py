"""Knowledge tools — @mcp.tool 薄殼，業務邏輯 + SQL 在 service.py。

Phase 2.12 partial split（codex 建議路線、不強拆三層）：
knowledge 是 cross-cutting read model（rule_relations + superseded_by + cross-entity
refs），強拆 tools/service/repository 會產生大量薄 SQL wrapper。改採：
- tools.py 薄殼（11 個 @mcp.tool 純 docstring + 透傳）
- service.py 含業務邏輯 + SQL（不抽 repository）
- 寫入流程升級到 with transaction()，與 P2.1-P2.11 一致
"""
from shared.mcp_instance import mcp

from . import service


@mcp.tool()
def store_fact(
    category: str,
    title: str,
    content: str,
    source_type: str = "explicit",
    source_quote: str = "",
    set_by: str = "",
    business_unit: str = "",
    related_rule_ids: list[int] = [],
) -> str:
    """儲存企業規則或知識。反捏造機制：source_type='explicit' 時必須附上 source_quote（老闆原話）。

    Args:
        category: 規則類別（如 return_policy, pricing, hr, supplier, sop）
        title: 規則標題
        content: 規則內容詳述
        source_type: 來源類型 — explicit（老闆明確指示）| observed（觀察到的慣例）| inferred（AI推斷）
        source_quote: 老闆原話引用（source_type=explicit 時必填）
        set_by: 誰設定的（如老闆姓名）
        business_unit: 所屬事業體（如 brand_c, brand_d），留空=全域規則
        related_rule_ids: 跟此規則相關的既有 rule id（list of int、可空）— 寫進 rule_relations as 'related'
    """
    return service.store_fact(
        category=category,
        title=title,
        content=content,
        source_type=source_type,
        source_quote=source_quote,
        set_by=set_by,
        business_unit=business_unit,
        related_rule_ids=related_rule_ids,
    )


@mcp.tool()
def query_knowledge(question: str, category: str = "", business_unit: str = "") -> str:
    """搜尋企業知識庫（規則、任務、客戶、庫存）。使用 LIKE 模糊比對（CJK 友好）。

    Args:
        question: 搜尋關鍵字或問題
        category: 可選，限定搜尋特定的規則類別
        business_unit: 可選，限定搜尋特定事業體的規則（同時包含全域規則）
    """
    return service.query_knowledge(
        question=question, category=category, business_unit=business_unit
    )


@mcp.tool()
def update_rule(
    rule_id: int, new_content: str, reason: str, actor_user_id: str = ""
) -> str:
    """更新企業規則。舊規則標記為已取代，建立新規則。

    Args:
        rule_id: 要更新的規則 ID
        new_content: 新的規則內容
        reason: 更新原因
        actor_user_id: 操作者 LINE user_id（用於權限驗證，留空=系統呼叫，不驗證）
    """
    return service.update_rule(
        rule_id=rule_id,
        new_content=new_content,
        reason=reason,
        actor_user_id=actor_user_id,
    )


@mcp.tool()
def knowledge_changelog(days: int = 7) -> str:
    """知識變更日誌：顯示指定天數內的規則新增、更新記錄。

    Args:
        days: 回溯天數（預設 7 天）
    """
    return service.knowledge_changelog(days)


@mcp.tool()
def lint_knowledge(checks: str = "all") -> str:
    """知識庫健檢：偵測矛盾、過期、覆蓋缺口、孤立鏈。

    Args:
        checks: 要執行的檢查，逗號分隔。可選值：contradictions, stale, coverage, orphaned, all（預設）
    """
    return service.lint_knowledge(checks)


@mcp.tool()
def link_rules(rule_id_a: int, rule_id_b: int, relation_type: str = "related") -> str:
    """建立規則之間的關聯（交叉引用）。

    Args:
        rule_id_a: 第一條規則 ID
        rule_id_b: 第二條規則 ID
        relation_type: 關聯類型 — related（相關）| depends_on（A 依賴 B）| conflicts_with（潛在衝突）
    """
    return service.link_rules(
        rule_id_a=rule_id_a, rule_id_b=rule_id_b, relation_type=relation_type
    )


@mcp.tool()
def get_rule(rule_id: int) -> str:
    """查看單筆規則完整內容（含 source_quote、被誰取代／取代了誰）。

    Args:
        rule_id: 規則 ID
    """
    return service.get_rule(rule_id)


@mcp.tool()
def get_rule_relations(rule_id: int) -> str:
    """查詢規則的所有關聯（交叉引用）。

    Args:
        rule_id: 規則 ID
    """
    return service.get_rule_relations(rule_id)


@mcp.tool()
def get_context_summary(scope: str = "full") -> str:
    """取得當前系統狀態摘要。壓縮恢復或新 session 啟動時必須呼叫。

    Args:
        scope: 'full'（完整狀態）或 'compact'（精簡版）
    """
    return service.get_context_summary(scope)


@mcp.tool()
def log_interaction(
    actor: str,
    action: str,
    target_type: str = "",
    target_id: int = 0,
    detail: str = "",
    business_unit: str = "",
) -> str:
    """記錄操作日誌（審計追蹤）。

    Args:
        actor: 操作者（員工姓名或 'system'）
        action: 動作（如 rule_created, task_completed, stock_updated）
        target_type: 對象類型（task, rule, inventory, customer, approval）
        target_id: 對象 ID
        detail: 詳細說明
        business_unit: 所屬事業體（如 brand_d, content），留空=不分
    """
    return service.log_interaction(
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail,
        business_unit=business_unit,
    )


@mcp.tool()
def log_decision(
    title: str,
    reason: str,
    supersedes_rule_ids: list[int] = [],
    related_rule_ids: list[int] = [],
    source_quote: str = "",
    set_by: str = "",
    business_unit: str = "",
) -> str:
    """記錄決策（為什麼這樣決定）。寫進 business_rules with category='decision_record'。
    可選擇同時把舊規則標為 superseded（透過 supersedes_rule_ids）。
    可選擇 link 到相關規則（透過 related_rule_ids）。
    查詢決策用 query_knowledge(category='decision_record')。

    Args:
        title: 決策摘要（一句話、不超過 60 字）
        reason: 為什麼這樣決定（rationale、含背景）
        supersedes_rule_ids: 此決策廢棄哪些舊 rule id（list of int、可空）
        related_rule_ids: 跟此決策相關的既有 rule id（不廢棄、只是 cross-ref）
        source_quote: 老闆原話（recommended）
        set_by: 誰做的決定（如老闆姓名）
        business_unit: 所屬事業體（如 brand_x），留空=全域
    """
    return service.log_decision(
        title=title,
        reason=reason,
        supersedes_rule_ids=supersedes_rule_ids,
        related_rule_ids=related_rule_ids,
        source_quote=source_quote,
        set_by=set_by,
        business_unit=business_unit,
    )
