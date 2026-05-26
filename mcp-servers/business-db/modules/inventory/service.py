"""Inventory service — 庫存查/調/警 業務邏輯（含 guidance 提示生成）。

層次邊界：transaction ownership 在這層，repository 不 commit。
"""
from shared.business_units import _validate_business_unit
from shared.db import _now, get_db, transaction
from shared.utils import _build_guidance

from . import repository


def check_stock(sku_or_name: str, business_unit: str) -> str:
    db = get_db()
    try:
        # 1. 先精確查 SKU（優先 SKU+BU、fallback 無歸屬）
        item = repository.find_by_sku(db, sku_or_name, business_unit)
        if item:
            return _format_single_item(item, business_unit)

        # 2. 找不到精確 SKU → LIKE 搜尋
        items = repository.search_by_keyword(db, sku_or_name, business_unit)
        if not items:
            bu_suffix = f"（事業體：{business_unit}）" if business_unit else ""
            return f"找不到庫存品項：{sku_or_name}{bu_suffix}"

        bu_suffix = f"（{business_unit}）" if business_unit else ""
        lines = [f"## 庫存搜尋：「{sku_or_name}」{bu_suffix}"]
        for i in items:
            bu_label = f" [{i['business_unit']}]" if i["business_unit"] else ""
            reserved = i["reserved"] or 0
            available = i["current_stock"] - reserved
            reserved_label = f"（預留 {reserved}，可用 {available}）" if reserved else ""
            lines.append(
                f"- [{i['sku']}] {i['name']}{bu_label}: "
                f"{i['current_stock']}{i['unit']}{reserved_label}"
            )
        return "\n".join(lines)
    finally:
        db.close()


def _format_single_item(item, request_bu: str) -> str:
    bu_label = f" [{item['business_unit']}]" if item["business_unit"] else ""
    reserved = item["reserved"] or 0
    available = item["current_stock"] - reserved
    alert = ""
    if item["current_stock"] <= item["min_stock"] and item["min_stock"] > 0:
        alert = " 注意：實體庫存低於安全庫存！"
    elif available <= item["min_stock"] and item["min_stock"] > 0:
        alert = " 注意：可用量低於安全庫存（已有預留佔用）"
    cross_bu = ""
    if request_bu and item["business_unit"] and item["business_unit"] != request_bu:
        cross_bu = (
            f"\n- 注意：注意：此品項屬於事業體 {item['business_unit']}，"
            f"非 {request_bu}"
        )
    return (
        f"## {item['name']} [{item['sku']}]{bu_label}\n"
        f"- 庫存：{item['current_stock']}{item['unit']}"
        f"（預留 {reserved}，可用 {available}）{alert}\n"
        f"- 安全庫存：{item['min_stock']}{item['unit']}\n"
        f"- 成本：{item['unit_cost'] or '?'} | 售價：{item['sell_price'] or '?'}\n"
        f"- 位置：{item['location'] or '未設定'}\n"
        f"- 最後進貨：{item['last_restock_date'] or '無紀錄'}"
        + cross_bu
    )


def update_stock(
    sku: str,
    quantity_change: int,
    reason: str,
    name: str,
    sell_price: float,
    unit_cost: float,
    min_stock: int,
    unit: str,
    category: str,
    business_unit: str,
) -> str:
    with transaction() as db:
        item = repository.find_by_sku(db, sku, business_unit)
        if not item:
            return _create_new_item(
                db, sku, quantity_change, reason, name, sell_price,
                unit_cost, min_stock, unit, category, business_unit,
            )

        new_stock = item["current_stock"] + quantity_change
        if new_stock < 0:
            return (
                f"ERROR: 庫存不足。目前 {item['current_stock']}{item['unit']}，"
                f"無法扣減 {abs(quantity_change)}"
            )

        stock_updates: list[str] = ["current_stock = ?"]
        stock_params: list = [new_stock]
        if quantity_change > 0:
            stock_updates.append("last_restock_date = ?")
            stock_params.append(_now()[:10])
        if min_stock >= 0:
            stock_updates.append("min_stock = ?"); stock_params.append(min_stock)
        if sell_price >= 0:
            stock_updates.append("sell_price = ?"); stock_params.append(sell_price)
        if unit_cost >= 0:
            stock_updates.append("unit_cost = ?"); stock_params.append(unit_cost)

        repository.safe_update_inventory(db, item["id"], stock_updates, stock_params)

        direction = "進貨" if quantity_change > 0 else "出貨"
        repository.insert_interaction_log(
            db,
            actor="system",
            action="stock_updated",
            target_id=item["id"],
            detail=(
                f"{direction} {abs(quantity_change)}{item['unit']}，"
                f"{reason or '無說明'}。{item['current_stock']}→{new_stock}"
            ),
            business_unit=item["business_unit"],
        )

    alert = ""
    if new_stock <= item["min_stock"] and item["min_stock"] > 0:
        alert = (
            f"\n注意：庫存警報：{item['name']} 剩 {new_stock}{item['unit']}，"
            f"低於安全庫存 {item['min_stock']}"
        )

    guidance = ""
    if quantity_change > 0:
        guidance = _build_purchase_guidance(
            item_name=item["name"],
            item_unit=item["unit"],
            unit_cost=item["unit_cost"],
            quantity=quantity_change,
        )

    return (
        f"[{sku}] {item['name']}: {item['current_stock']} → {new_stock}{item['unit']}"
        + alert
        + guidance
    )


def _create_new_item(
    db,
    sku: str,
    quantity_change: int,
    reason: str,
    name: str,
    sell_price: float,
    unit_cost: float,
    min_stock: int,
    unit: str,
    category: str,
    business_unit: str,
) -> str:
    """SKU 不存在 → 新建品項。quantity_change<0 不允許（負庫存初始狀態無意義）。"""
    if quantity_change < 0:
        return f"ERROR: 找不到 SKU={sku}（新增品項請用 0 或正數）"

    initial_stock = max(quantity_change, 0)
    inv_id = repository.insert_inventory(
        db,
        sku=sku,
        name=name or sku,
        current_stock=initial_stock,
        business_unit=business_unit or None,
        sell_price=sell_price,
        unit_cost=unit_cost,
        min_stock=min_stock,
        unit=unit,
        category=category,
    )
    repository.insert_interaction_log(
        db,
        actor="system",
        action="stock_created",
        target_id=inv_id,
        detail=(
            f"新建品項 [{sku}] {name or sku}，"
            f"初始庫存 {quantity_change}。{reason or ''}"
        ),
        business_unit=business_unit or None,
    )

    item_unit = unit or "個"
    item_name = name or sku
    guidance = _build_purchase_guidance(
        item_name=item_name,
        item_unit=item_unit,
        unit_cost=unit_cost if unit_cost >= 0 else None,
        quantity=quantity_change,
    )
    bu_warn = _validate_business_unit(db, business_unit)
    return (
        f"新建品項 [{sku}] {name or sku}，"
        f"初始庫存 {quantity_change}{unit or '個'}"
        + guidance
        + bu_warn
    )


def _build_purchase_guidance(
    item_name: str, item_unit: str, unit_cost, quantity: int
) -> str:
    """為進貨流程生成 record_transaction 提示。unit_cost 已知 → 帶 amount；未知 → 提示確認。"""
    if quantity <= 0:
        return ""
    if unit_cost:
        cost = quantity * unit_cost
        return _build_guidance(next_steps=[
            f"record_transaction(type='expense', amount={cost}, category='inventory_purchase', "
            f"description='進貨 {item_name} {quantity}{item_unit} @ NT${unit_cost:,.0f}')",
            "問使用者：已付款(payment_status='paid')還是賒帳(payment_status='pending')？",
        ])
    return _build_guidance(next_steps=[
        f"record_transaction(type='expense', category='inventory_purchase', "
        f"description='進貨 {item_name} {quantity}{item_unit}') — 需確認進貨金額",
    ])


def low_stock_alerts(business_unit: str) -> str:
    db = get_db()
    try:
        items = repository.list_low_stock(db, business_unit)
        if not items:
            bu_suffix = f"（{business_unit}）" if business_unit else ""
            return f"所有品項庫存正常，無警報。{bu_suffix}"
        bu_suffix = f"（{business_unit}）" if business_unit else ""
        lines = [f"## 庫存警報（{len(items)} 項）{bu_suffix}"]
        for i in items:
            pct = round(i["current_stock"] / i["min_stock"] * 100) if i["min_stock"] else 0
            bu_label = (
                f" [{i['business_unit']}]"
                if i["business_unit"] and not business_unit else ""
            )
            lines.append(
                f"- [{i['sku']}] {i['name']}{bu_label}: "
                f"{i['current_stock']}/{i['min_stock']}{i['unit']} ({pct}%) "
                f"{i['location'] or ''}"
            )
        return "\n".join(lines)
    finally:
        db.close()
