"""CRM tools — @mcp.tool 薄殼，業務邏輯在 service.py、SQL 在 repository.py。

Phase 2.8 三層化（套 P2.1 attachments pattern）。
注意：crm/terms.py（P1 抽出的 cross-module helper）保留不動。
"""
from shared.mcp_instance import mcp

from . import service


@mcp.tool()
def add_customer(
    name: str,
    type: str = "customer",
    phone: str = "",
    email: str = "",
    line_user_id: str = "",
    tags: str = "",
    notes: str = "",
    discount_rate: float = 0.0,
    payment_terms: str = "net30",
    primary_business_unit: str = "",
) -> str:
    """新增客戶、供應商或經銷商。

    Args:
        name: 名稱（公司名或個人名）
        type: 類型 — customer（客戶）| supplier（供應商）| distributor（經銷商）
        phone: 電話
        email: Email
        line_user_id: LINE User ID（用於 LINE 身份辨識）
        tags: 標籤（逗號分隔，如 vip,wholesale）
        notes: 備註
        discount_rate: 折扣率（0=原價, 0.15=85折, 0.2=8折）
        payment_terms: 付款條件 — prepaid | cod | deposit_30 | net30 | net60
        primary_business_unit: 主要歸屬事業體（如 brand_c, brand_a），留空=無特定歸屬
    """
    return service.add_customer(
        name=name,
        type_=type,
        phone=phone,
        email=email,
        line_user_id=line_user_id,
        tags=tags,
        notes=notes,
        discount_rate=discount_rate,
        payment_terms=payment_terms,
        primary_business_unit=primary_business_unit,
    )


@mcp.tool()
def find_customer(query: str, type: str = "") -> str:
    """搜尋客戶、供應商或經銷商。

    Args:
        query: 搜尋關鍵字
        type: 篩選類型（customer/supplier/distributor），空白=全部
    """
    return service.find_customer(query=query, type_=type)


@mcp.tool()
def get_customer(customer_id: int) -> str:
    """查看單筆客戶／供應商／經銷商完整資訊（含各事業體條件、累計銷售）。

    Args:
        customer_id: 客戶 ID
    """
    return service.get_customer(customer_id)


@mcp.tool()
def update_customer(
    customer_id: int,
    name: str = "",
    phone: str = "",
    email: str = "",
    line_user_id: str = "__SKIP__",
    tags: str = "",
    notes: str = "",
    pipeline_stage: str = "",
    total_purchases: float = -1,
    discount_rate: float = -1.0,
    payment_terms: str = "",
    primary_business_unit: str = "__SKIP__",
) -> str:
    """更新客戶/供應商/經銷商資訊。

    Args:
        customer_id: 客戶 ID
        name: 新姓名（空白=不更新）
        phone: 新電話
        email: 新 Email
        line_user_id: LINE User ID（傳空字串清除綁定）
        tags: 新標籤
        notes: 新備註
        pipeline_stage: 業務階段 — none | prospect | contacted | negotiating | closed_won | closed_lost
        total_purchases: 累計消費金額（-1=不更新）
        discount_rate: 折扣率（-1=不更新，0=原價，0.15=85折）
        payment_terms: 付款條件 — prepaid | cod | deposit_30 | net30 | net60（空白=不更新）
        primary_business_unit: 主要歸屬事業體（傳空字串清除歸屬）
    """
    return service.update_customer(
        customer_id=customer_id,
        name=name,
        phone=phone,
        email=email,
        line_user_id=line_user_id,
        tags=tags,
        notes=notes,
        pipeline_stage=pipeline_stage,
        total_purchases=total_purchases,
        discount_rate=discount_rate,
        payment_terms=payment_terms,
        primary_business_unit=primary_business_unit,
    )


@mcp.tool()
def set_customer_entity_terms(
    customer_id: int,
    business_unit: str,
    discount_rate: float = -1.0,
    payment_terms: str = "",
) -> str:
    """設定客戶在特定事業體的折扣率和付款條件。覆寫 customers 表的預設值。

    Args:
        customer_id: 客戶 ID
        business_unit: 事業體（如 brand_c, brand_d）
        discount_rate: 折扣率（-1=不設定，0=原價，0.15=85折）
        payment_terms: 付款條件 — prepaid | cod | deposit_30 | net30 | net60（空白=不設定）
    """
    return service.set_entity_terms(
        customer_id=customer_id,
        business_unit=business_unit,
        discount_rate=discount_rate,
        payment_terms=payment_terms,
    )
