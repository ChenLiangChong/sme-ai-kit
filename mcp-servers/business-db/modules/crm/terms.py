"""CRM domain helper — _get_customer_terms（純 helper、no @mcp.tool）。

Phase 1.4.4 抽出。Orders 等 module 跨 module 用、放在 modules/crm/ 內當 sub-module
（不是 sibling tool import、不會觸發 register、避免 cycle）。
"""


def _get_customer_terms(db, customer_id: int, business_unit: str = "") -> dict:
    """取得客戶的折扣率和付款條件。先查 customer_entity_terms（事業體專屬），fallback 到 customers 預設值。"""
    customer = db.execute("SELECT discount_rate, payment_terms FROM customers WHERE id = ?", (customer_id,)).fetchone()
    if not customer:
        return {"discount_rate": 0, "payment_terms": "net30"}
    defaults = {"discount_rate": customer["discount_rate"] or 0, "payment_terms": customer["payment_terms"] or "net30"}
    if not business_unit:
        return defaults
    entity_terms = db.execute(
        "SELECT discount_rate, payment_terms FROM customer_entity_terms WHERE customer_id = ? AND business_unit = ?",
        (customer_id, business_unit),
    ).fetchone()
    if entity_terms:
        return {"discount_rate": entity_terms["discount_rate"] or 0, "payment_terms": entity_terms["payment_terms"] or "net30"}
    return defaults
