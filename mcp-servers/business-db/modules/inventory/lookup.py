"""Inventory lookup helper — _find_inventory（pure helper、no @mcp.tool）。

Phase 1.4.3 拆出。Orders module 之後也 import 這個 helper（不是 sibling tool import）。
"""


def _find_inventory(db, sku: str, business_unit: str):
    """查找庫存紀錄。先精確匹配 SKU+BU，再 fallback 到無歸屬（共用）庫存，絕不跨 BU。"""
    if business_unit:
        inv = db.execute(
            "SELECT * FROM inventory WHERE sku = ? AND business_unit = ?",
            (sku, business_unit),
        ).fetchone()
        if inv:
            return inv
    # Fallback：只查無歸屬（共用）庫存，避免跨 BU 誤扣
    return db.execute(
        "SELECT * FROM inventory WHERE sku = ? AND (business_unit IS NULL OR business_unit = '')",
        (sku,),
    ).fetchone()
