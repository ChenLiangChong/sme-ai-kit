"""Inventory tools — @mcp.tool 薄殼，業務邏輯在 service.py、SQL 在 repository.py。

Phase 2.9 三層化（套 P2.1 attachments pattern）。
注意：inventory/lookup.py（P1 抽出的 cross-module helper，orders 用）保留不動。
"""
from shared.mcp_instance import mcp

from . import service


@mcp.tool()
def check_stock(sku_or_name: str, business_unit: str = "") -> str:
    """查詢庫存。可用 SKU 或品名搜尋。

    Args:
        sku_or_name: SKU 編號或品名關鍵字
        business_unit: 篩選特定事業體（如 brand_c, brand_d），留空=全部
    """
    return service.check_stock(sku_or_name=sku_or_name, business_unit=business_unit)


@mcp.tool()
def update_stock(
    sku: str,
    quantity_change: int,
    reason: str = "",
    name: str = "",
    sell_price: float = -1,
    unit_cost: float = -1,
    min_stock: int = -1,
    unit: str = "",
    category: str = "",
    business_unit: str = "",
) -> str:
    """調整庫存數量（正數=進貨，負數=出貨/損耗）。SKU 不存在時自動建立新品項。

    Args:
        sku: SKU 編號
        quantity_change: 數量變動（正=進貨，負=出貨）
        reason: 調整原因
        name: 品項名稱（新建 SKU 時使用）
        sell_price: 售價（-1=不設定）
        unit_cost: 成本（-1=不設定）
        min_stock: 安全庫存（-1=不設定）
        unit: 單位（如「個」「箱」「組」）
        category: 品項分類
        business_unit: 所屬事業體（如 brand_c, brand_d），留空=不分
    """
    return service.update_stock(
        sku=sku,
        quantity_change=quantity_change,
        reason=reason,
        name=name,
        sell_price=sell_price,
        unit_cost=unit_cost,
        min_stock=min_stock,
        unit=unit,
        category=category,
        business_unit=business_unit,
    )


@mcp.tool()
def low_stock_alerts(business_unit: str = "") -> str:
    """列出所有低於安全庫存的品項。

    Args:
        business_unit: 篩選特定事業體（如 brand_c, brand_d），留空=全部
    """
    return service.low_stock_alerts(business_unit)
