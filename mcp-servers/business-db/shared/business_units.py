"""
Shared business-unit helpers — BU 存在驗證 + 審核門檻取得（先查 BU、fallback 到 company 預設）。

Phase 1.2 抽出（codex review BLOCKER）：accounting、orders、approvals 等多 module 共用。
"""


def _validate_business_unit(db, business_unit: str) -> str:
    """驗證 business_unit 是否存在於 business_entities 表。
    Returns: 空字串=OK，非空=警告訊息（不阻擋操作）。"""
    if not business_unit:
        return ""
    entity = db.execute("SELECT id FROM business_entities WHERE id = ?", (business_unit,)).fetchone()
    if not entity:
        return f"\n注意：事業體 '{business_unit}' 未登錄（register_business_entity），資料已存入但無法按事業體篩選彙總。"
    return ""


def _get_approval_threshold(db, business_unit: str = "") -> float:
    """取得審核門檻。先查事業體設定（必須 >= 0 才有效），否則 fallback 到公司預設。
    注意：事業體的 approval_threshold 若為負值（常見 -1 sentinel）視為未設定，需 fallback。"""
    if business_unit:
        entity = db.execute("SELECT approval_threshold FROM business_entities WHERE id = ?", (business_unit,)).fetchone()
        if entity and entity["approval_threshold"] is not None and entity["approval_threshold"] >= 0:
            return entity["approval_threshold"]
    company = db.execute("SELECT approval_threshold FROM company WHERE id = 1").fetchone()
    return company["approval_threshold"] if company else 5000
