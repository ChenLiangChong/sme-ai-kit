"""Inventory repository — inventory SQL + interaction_log。

層次邊界（同 P2.1 pattern）：
- 進 sqlite3.Connection + primitive、出 Row / id
- 不 commit / rollback

注意：lookup.py 是 P1 抽出的 cross-module helper（orders 用），這裡薄包重用、避免重複。
"""
import sqlite3

from shared.utils import _like_param, _safe_update

from .lookup import _find_inventory

_INVENTORY_COLUMNS = {
    "current_stock", "last_restock_date", "min_stock", "sell_price", "unit_cost",
}


def find_by_sku(
    db: sqlite3.Connection, sku: str, business_unit: str
) -> sqlite3.Row | None:
    """SKU + BU 精確匹配、fallback 到無歸屬庫存。重用 lookup._find_inventory。"""
    return _find_inventory(db, sku, business_unit)


def find_by_sku_exact(
    db: sqlite3.Connection, sku: str, business_unit: str
) -> sqlite3.Row | None:
    """嚴格按 SKU + BU 精確匹配，找不到「不」fallback 到全域（避免 BU 打錯誤改共用庫存）。"""
    return db.execute(
        "SELECT * FROM inventory WHERE sku = ? AND business_unit = ?",
        (sku, business_unit),
    ).fetchone()


def find_global_by_sku(db: sqlite3.Connection, sku: str) -> sqlite3.Row | None:
    """只查無歸屬（共用）庫存的同 SKU，用於 BU 不符時的明確提示。"""
    return db.execute(
        "SELECT * FROM inventory WHERE sku = ? AND (business_unit IS NULL OR business_unit = '')",
        (sku,),
    ).fetchone()


def business_unit_exists(db: sqlite3.Connection, business_unit: str) -> bool:
    """指定 BU 是否登錄於 business_entities（update_stock 新建前驗證、防誤建懸空 BU 庫存列）。"""
    row = db.execute(
        "SELECT 1 FROM business_entities WHERE id = ? LIMIT 1", (business_unit,)
    ).fetchone()
    return row is not None


def search_by_keyword(
    db: sqlite3.Connection, query: str, business_unit: str
) -> list[sqlite3.Row]:
    like = _like_param(query)
    if business_unit:
        return db.execute(
            "SELECT * FROM inventory "
            "WHERE (name LIKE ? OR sku LIKE ? OR category LIKE ?) AND business_unit = ? "
            "LIMIT 5",
            (like, like, like, business_unit),
        ).fetchall()
    return db.execute(
        "SELECT * FROM inventory "
        "WHERE name LIKE ? OR sku LIKE ? OR category LIKE ? LIMIT 5",
        (like, like, like),
    ).fetchall()


def insert_inventory(
    db: sqlite3.Connection,
    sku: str,
    name: str,
    current_stock: int,
    business_unit: str | None,
    sell_price: float,
    unit_cost: float,
    min_stock: int,
    unit: str,
    category: str,
) -> int:
    """動態欄位 INSERT（依非預設值決定 INSERT 哪些 col、其他走 schema default）。"""
    cols = ["sku", "name", "current_stock"]
    vals: list = [sku, name, current_stock]
    if business_unit:
        cols.append("business_unit"); vals.append(business_unit)
    if sell_price >= 0:
        cols.append("sell_price"); vals.append(sell_price)
    if unit_cost >= 0:
        cols.append("unit_cost"); vals.append(unit_cost)
    if min_stock >= 0:
        cols.append("min_stock"); vals.append(min_stock)
    if unit:
        cols.append("unit"); vals.append(unit)
    if category:
        cols.append("category"); vals.append(category)
    placeholders = ",".join("?" for _ in cols)
    cursor = db.execute(
        f"INSERT INTO inventory ({','.join(cols)}) VALUES ({placeholders})", vals
    )
    return cursor.lastrowid


def safe_update_inventory(
    db: sqlite3.Connection, item_id: int, updates: list[str], params: list
) -> None:
    _safe_update(
        db, "inventory", _INVENTORY_COLUMNS, updates, params, "id = ?", [item_id]
    )


def list_low_stock(
    db: sqlite3.Connection, business_unit: str
) -> list[sqlite3.Row]:
    cols = "sku, name, current_stock, min_stock, unit, location, business_unit"
    base = (
        f"SELECT {cols} FROM inventory "
        f"WHERE current_stock <= min_stock AND min_stock > 0"
    )
    order = " ORDER BY (current_stock * 1.0 / min_stock)"
    if business_unit:
        return db.execute(
            base + " AND business_unit = ?" + order, (business_unit,)
        ).fetchall()
    return db.execute(base + order).fetchall()


def insert_interaction_log(
    db: sqlite3.Connection,
    actor: str,
    action: str,
    target_id: int,
    detail: str,
    business_unit: str | None,
) -> None:
    db.execute(
        "INSERT INTO interaction_log "
        "(actor, action, target_type, target_id, detail, business_unit) "
        "VALUES (?,?,'inventory',?,?,?)",
        (actor, action, target_id, detail, business_unit),
    )
