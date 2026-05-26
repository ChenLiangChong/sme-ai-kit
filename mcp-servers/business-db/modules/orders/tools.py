"""Orders tools — @mcp.tool 薄殼，業務邏輯在 service.py、SQL 在 repository.py。

Phase 2.11 三層化（套 P2.1 attachments pattern、含 codex P2.10 給的 5 條 checklist）。
注意：orders/items.py、modules/crm/terms.py、modules/inventory/lookup.py（P1 cross-module
helper）保留不動、service 直接 import 使用（已接 db 參數、不開 nested transaction）。
"""
from shared.mcp_instance import mcp

from . import service


@mcp.tool()
def create_order(
    customer_id: int,
    items_json: str,
    notes: str = "",
    business_unit: str = "",
    created_by: str = "",
    approved_id: int = 0,
) -> str:
    """建立訂單。

    Args:
        customer_id: 客戶 ID
        items_json: 訂單品項 JSON，格式：[{"sku":"A200","name":"特殊零件","qty":10,"price":350}]
        notes: 備註
        business_unit: 所屬事業體（如 product, design, content），留空=不分
        created_by: 建立者
        approved_id: 已核准的審核 ID（繞過門檻檢查）
    """
    return service.create_order(
        customer_id=customer_id,
        items_json=items_json,
        notes=notes,
        business_unit=business_unit,
        created_by=created_by,
        approved_id=approved_id,
    )


@mcp.tool()
def get_order(order_id: int) -> str:
    """查看單筆訂單完整資訊。

    Args:
        order_id: 訂單 ID
    """
    return service.get_order(order_id)


@mcp.tool()
def update_order(
    order_id: int,
    status: str = "",
    notes: str = "",
    driver: str = "",
    estimated_delivery: str = "",
) -> str:
    """更新訂單狀態、物流資訊或備註。狀態轉換受限：取消/退貨用 cancel_order，出貨用 fulfill_order。

    Args:
        order_id: 訂單 ID
        status: 新狀態 — confirmed | delivered | paid（其他轉換請用專門工具）
        notes: 更新備註
        driver: 配送司機/物流人員
        estimated_delivery: 預計送達日期（YYYY-MM-DD）
    """
    return service.update_order(
        order_id=order_id,
        status=status,
        notes=notes,
        driver=driver,
        estimated_delivery=estimated_delivery,
    )


@mcp.tool()
def list_orders(
    customer_id: int = 0,
    status: str = "",
    business_unit: str = "",
    limit: int = 20,
) -> str:
    """列出訂單。

    Args:
        customer_id: 篩選客戶（0=全部）
        status: 篩選狀態（空白=全部）
        business_unit: 篩選事業體（留空=全部）
        limit: 最多顯示幾筆
    """
    return service.list_orders(
        customer_id=customer_id,
        status=status,
        business_unit=business_unit,
        limit=limit,
    )


@mcp.tool()
def qc_order(order_id: int, result: str, notes: str = "", checked_by: str = "") -> str:
    """品質檢查（QC）。出貨前必須通過 QC。

    Args:
        order_id: 訂單 ID
        result: 檢查結果 — passed（通過）| failed（不合格）| partial（部分合格）
        notes: QC 備註（瑕疵描述、檢查項目等）
        checked_by: 檢查人員
    """
    return service.qc_order(
        order_id=order_id, result=result, notes=notes, checked_by=checked_by
    )


@mcp.tool()
def fulfill_order(order_id: int, partial_items_json: str = "") -> str:
    """確認訂單出貨：自動扣庫存 + 建立應收帳款。

    Args:
        order_id: 訂單 ID
        partial_items_json: 部分出貨品項 JSON（僅 QC partial 時使用）。格式：[{"sku":"A001","qty":5}, ...]。留空=出貨全部品項。
    """
    return service.fulfill_order(
        order_id=order_id, partial_items_json=partial_items_json
    )


@mcp.tool()
def cancel_order(
    order_id: int,
    reason: str,
    cancel_type: str = "cancelled",
    actor_user_id: str = "",
) -> str:
    """取消或退貨訂單。自動回補庫存（若已出貨）並作廢應收帳款。

    Args:
        order_id: 訂單 ID
        reason: 取消/退貨原因（必填）
        cancel_type: cancelled（取消）| returned（退貨）
        actor_user_id: 操作者 LINE user_id（用於權限驗證，留空=系統呼叫，不驗證）
    """
    return service.cancel_order(
        order_id=order_id,
        reason=reason,
        cancel_type=cancel_type,
        actor_user_id=actor_user_id,
    )
