"""Orders service — 訂單建立 / 出貨 / QC / 取消 業務邏輯。

層次邊界：transaction ownership 在這層，repository 不 commit。
Approval gate / payment guidance / LINE wording 全在這層（codex P2.10 警告 #4）。

Codex P2.10 給的 5 條 checklist 全部落實：
1. create_order 全包同一 service transaction（insert order + 預留庫存 + 客戶累計 + audit）
2. fulfill_order 庫存扣減 + 訂單狀態 + 應收帳款 + 客戶累計 同一 tx 避免 oversell
3. 跨 module helper（terms / lookup / items）已接 db 參數、不開 nested transaction
4. orders repository 純 SQL、LINE wording / approval prompt 在這層 service helper
5. 部分出貨用 effective ship_total（按比例分攤）、cancel 用 effective shipped_qty 回補
"""
import json
from datetime import datetime, timedelta

from shared.auth import _check_permission
from shared.business_units import _get_approval_threshold, _validate_business_unit
from shared.db import _now, get_db, transaction
from shared.escalation import enqueue_escalation
from shared.utils import _build_guidance

from modules.approvals import service as approvals_service
from modules.crm.terms import _get_customer_terms
from modules.inventory.lookup import _find_inventory

from . import repository
from .items import _parse_items_json

_ORDER_TRANSITIONS = {
    "pending": {"confirmed"},
    "confirmed": set(),       # → shipped 只能透過 fulfill_order
    "shipped": {"delivered"},
    "delivered": {"paid"},
}

_STATUS_ICON = {
    "pending": "[待處理]", "confirmed": "[已確認]", "shipped": "[已出貨]",
    "delivered": "[已送達]", "paid": "[已付清]", "cancelled": "[已取消]",
    "returned": "[已退貨]",
}
_QC_ICON = {"passed": "[合格]", "failed": "[不合格]", "partial": "[部分合格]"}


# ============================================================
# create_order
# ============================================================

def create_order(
    customer_id: int,
    items_json: str,
    notes: str,
    business_unit: str,
    created_by: str,
    approved_id: int,
) -> str:
    # codex P2.13：gate + verify + insert + consume 全在同一 transaction（鎖定 state、
    # 防 race；approval 必驗 resume_action + 關鍵 params + 單次消耗）。
    # approved_id 提供 → 用 IMMEDIATE 鎖、確保並發兩 client 共用同 approval 時、
    # 輸家不會白做 insert 再 rollback（codex LOW A 修法）。
    tx_mode = "immediate" if approved_id else "deferred"
    with transaction(mode=tx_mode) as db:
        customer = repository.get_customer_for_order(db, customer_id)
        if not customer:
            return f"ERROR: 找不到客戶 #{customer_id}"

        try:
            items = json.loads(items_json) if isinstance(items_json, str) else items_json
        except json.JSONDecodeError:
            return "ERROR: items_json 格式錯誤，需要 JSON 陣列"

        raw_total = sum(item.get("qty", 0) * item.get("price", 0) for item in items)
        terms_info = _get_customer_terms(db, customer_id, business_unit)
        discount = terms_info["discount_rate"]
        total = round(raw_total * (1 - discount)) if discount > 0 else raw_total

        threshold = _get_approval_threshold(db, business_unit)
        gate = approvals_service.gate_check(
            db,
            approved_id=approved_id,
            amount=total,
            threshold=threshold,
            expected_action="create_order",
            verify_fields={
                "customer_id": customer_id,
                "items_json": items_json,
                "business_unit": business_unit or "",
            },
        )
        if gate.error:
            return gate.error
        if gate.needs_approval:
            # 系統自建審核（決策 #183 模式、#26 套到 orders）：超門檻時 create_order 自己用完整
            # resume_params 建審核 + 觸發 approval_pending 上報，不靠 agent 手寫 create_approval。
            # detail 的 resume_params 鍵需涵蓋上方 gate verify_fields（customer_id/items_json/
            # business_unit）→ 核准後依鎖定參數 create_order(approved_id=…) consume 必過。
            discount_note = f"（已含折扣 {discount*100:.0f}%）" if discount > 0 else ""
            approval_id = approvals_service.create_in_tx(
                db,
                type_="purchase",
                summary=f"建立訂單：{customer['name']} NT${total:,.0f}{discount_note}",
                detail=_order_resume_detail(
                    customer_id=customer_id,
                    items_json=items_json,
                    notes=notes,
                    business_unit=business_unit,
                    created_by=created_by,
                ),
                requester=created_by or "system",
                business_unit=business_unit,
                escalate=True,
            )
            return (
                f"訂單金額 NT${total:,.0f}{discount_note} 超過審核門檻 NT${threshold:,.0f}，"
                f"已自動建立審核 #{approval_id} 並上報簽核人。"
                + _build_guidance(next_steps=[
                    f"等簽核人核准（LINE 回「核准 #{approval_id}」或全權限層 resolve_approval）",
                    f"核准後由全權限 / 業務層 session 依審核鎖定的原始參數執行 create_order(approved_id={approval_id})、客戶 / 品項一字不差、無需人工重填",
                ])
            )

        order_id = repository.insert_order(
            db,
            customer_id=customer_id,
            total_amount=total,
            items_json=json.dumps(items, ensure_ascii=False),
            business_unit=business_unit or None,
            notes=notes or None,
            created_by=created_by or None,
            payment_terms=terms_info["payment_terms"],
            discount_applied=discount,
        )

        # 預留庫存（v4 Bug #4：排單時預留、fulfill 才扣 current_stock）
        reservation_notes: list[str] = []
        for item in items:
            sku = (item.get("sku") or "").strip()
            qty = int(item.get("qty") or 0)
            if not sku or qty <= 0:
                continue
            inv = _find_inventory(db, sku, business_unit or "")
            if not inv:
                reservation_notes.append(f"SKU={sku} 不在庫存（跳過預留）")
                continue
            available = (inv["current_stock"] or 0) - (inv["reserved"] or 0)
            if available < qty:
                reservation_notes.append(
                    f"{inv['name']}({sku}) 可用 {available} 不足 {qty}（仍預留，出貨時會再驗）"
                )
            repository.add_inventory_reserved(db, inv["id"], qty)

        # v4 Bug #2：客戶下單累計
        repository.add_customer_ordered(db, customer_id, total, _now()[:10])

        repository.insert_interaction_log(
            db,
            actor=created_by or "system",
            action="order_created",
            target_type="order",
            target_id=order_id,
            detail=f"客戶 {customer['name']}，金額 NT${total:,.0f}，{len(items)} 項品項",
            business_unit=business_unit or None,
        )

        if gate.approval_id:
            approvals_service.gate_consume(
                db,
                approval_id=gate.approval_id,
                consumed_by_type="order",
                consumed_by_id=order_id,
            )

        bu_warn = _validate_business_unit(db, business_unit)

    return _format_create_order_success(
        order_id=order_id,
        customer_name=customer["name"],
        total=total,
        items=items,
        terms=terms_info["payment_terms"],
        discount=discount,
        reservation_notes=reservation_notes,
        bu_warn=bu_warn,
    )


def _order_resume_detail(
    customer_id: int,
    items_json: str,
    notes: str,
    business_unit: str,
    created_by: str,
) -> str:
    """訂單審核的 resume detail JSON（決策 #183/#26）。resume_params 的鍵需涵蓋 create_order
    gate verify_fields（customer_id / items_json / business_unit），核准後依此鎖定參數
    create_order(approved_id=…) 的 consume 才會一字不差通過。"""
    return json.dumps({
        "resume_action": "create_order",
        "resume_params": {
            "customer_id": customer_id,
            "items_json": items_json,
            "notes": notes,
            "business_unit": business_unit,
            "created_by": created_by,
        },
        "then": "訂單建立後通知客戶和倉管",
    }, ensure_ascii=False)


def _format_create_order_success(
    order_id: int,
    customer_name: str,
    total: float,
    items: list,
    terms: str,
    discount: float,
    reservation_notes: list[str],
    bu_warn: str,
) -> str:
    items_str = "\n".join(
        f"  - {i.get('name', i.get('sku', '?'))} × {i.get('qty', 0)} "
        f"@ NT${i.get('price', 0):,.0f}" for i in items
    )
    base_msg = (
        f"訂單 #{order_id} 已建立\n客戶：{customer_name}\n"
        f"金額：NT${total:,.0f}\n品項：\n{items_str}"
    )

    # 付款條件 next step
    next_steps: list[str] = []
    deposit_pct = 0.0
    if terms.startswith("deposit_"):
        try:
            deposit_pct = int(terms.split("_")[1]) / 100.0
        except (IndexError, ValueError):
            deposit_pct = 0.3
    terms_actions = {
        "prepaid": (
            f"通知客戶匯款 NT${total:,.0f}，收到後 "
            f"record_transaction(type='income', amount={total}, "
            f"category='sales_revenue', related_order_id={order_id}, payment_status='paid')"
        ),
        "net30": f"update_order(order_id={order_id}, status='confirmed') → 進入品檢流程",
        "net60": f"update_order(order_id={order_id}, status='confirmed') → 進入品檢流程",
        "cod": f"update_order(order_id={order_id}, status='confirmed') → 進入品檢流程",
    }
    if deposit_pct > 0:
        deposit_amt = round(total * deposit_pct)
        terms_actions[terms] = (
            f"通知客戶付 {int(deposit_pct*100)}% 訂金 NT${deposit_amt:,.0f}，"
            f"收到後 record_transaction(type='income', amount={deposit_amt}, "
            f"related_order_id={order_id}, payment_status='paid')"
        )
    default_action = f"update_order(order_id={order_id}, status='confirmed')"
    next_steps.append(f"付款條件 {terms}：{terms_actions.get(terms, default_action)}")
    next_steps.append(f"LINE 通知客戶：訂單 #{order_id} 已建立，金額 NT${total:,.0f}")
    next_steps.append(f"LINE 通知倉管/業務：新訂單 #{order_id}，請準備備貨")

    warnings: list[str] = []
    if bu_warn:
        warnings.append(bu_warn.strip())
    if discount > 0:
        warnings.append(f"已套用客戶折扣率 {discount*100:.0f}%")
    reserved_qty = sum(int(i.get("qty") or 0) for i in items if i.get("sku"))
    if reserved_qty > 0:
        warnings.append(f"已為訂單預留 {reserved_qty} 單位庫存（出貨時才扣 current_stock）")
    if reservation_notes:
        warnings.extend(reservation_notes)
    guidance = _build_guidance(next_steps=next_steps, warnings=warnings)
    return base_msg + guidance


# ============================================================
# get / list / update / qc
# ============================================================

def get_order(order_id: int) -> str:
    db = get_db()
    try:
        order = repository.get_order(db, order_id)
        if not order:
            return f"ERROR: 找不到訂單 #{order_id}"

        customer = repository.get_customer_name(db, order["customer_id"])
        customer_name = customer["name"] if customer else "未知"

        status_icon = _STATUS_ICON.get(order["status"], "")
        items = _parse_items_json(order["items"])
        items_str = "\n".join(
            f"  - {i.get('name', i.get('sku', '?'))} × {i.get('qty', 0)} "
            f"@ NT${i.get('price', 0):,.0f}" for i in items
        )

        qc_info = ""
        if order["qc_status"] != "pending":
            qc_icon = _QC_ICON.get(order["qc_status"], "")
            qc_info = (
                f"\n- QC：{qc_icon} {order['qc_status']}"
                f"{' — ' + order['qc_notes'] if order['qc_notes'] else ''}"
                f"{' by ' + order['qc_checked_by'] if order['qc_checked_by'] else ''}"
            )

        logistics = ""
        if order["driver"] or order["estimated_delivery"] or order["delivered_at"]:
            logistics = (
                f"\n- 物流：\n"
                f"  - 司機：{order['driver'] or '未指派'}\n"
                f"  - 預計送達：{order['estimated_delivery'] or '未設定'}\n"
                f"  - 實際送達：{order['delivered_at'] or '尚未送達'}"
            )

        terms_str = ""
        if order["payment_terms"]:
            discount_str = (
                f" 折扣 {order['discount_applied']*100:.0f}%"
                if order["discount_applied"] else ""
            )
            terms_str = f"\n- 付款條件：{order['payment_terms']}{discount_str}"

        return (
            f"## 訂單 #{order_id} {status_icon}\n"
            f"- 客戶：{customer_name}\n"
            f"- 狀態：{order['status']}\n"
            f"- 金額：NT${order['total_amount']:,.0f}"
            f"{terms_str}\n"
            f"- 品項：\n{items_str}"
            f"{qc_info}"
            f"{logistics}\n"
            f"- 備註：{order['notes'] or '無'}\n"
            f"- 建立：{order['created_at']}\n"
            f"- 更新：{order['updated_at']}"
        )
    finally:
        db.close()


def list_orders(
    customer_id: int, status: str, business_unit: str, limit: int
) -> str:
    db = get_db()
    try:
        orders = repository.list_orders(db, customer_id, status, business_unit, limit)
        if not orders:
            return "沒有符合條件的訂單。"
        lines = [f"## 訂單列表（{len(orders)} 筆）"]
        for o in orders:
            icon = _STATUS_ICON.get(o["status"], "")
            lines.append(
                f"- {icon} [#{o['id']}] {o['customer_name'] or '?'} | "
                f"NT${o['total_amount']:,.0f} | {o['status']} | {o['created_at'][:10]}"
            )
        return "\n".join(lines)
    finally:
        db.close()


def update_order(
    order_id: int,
    status: str,
    notes: str,
    driver: str,
    estimated_delivery: str,
) -> str:
    with transaction() as db:
        order = repository.get_order(db, order_id)
        if not order:
            return f"ERROR: 找不到訂單 #{order_id}"

        updates: list[str] = ["updated_at = ?"]
        params: list = [_now()]

        if status:
            cur = order["status"]
            if status in ("cancelled", "returned"):
                return (
                    f"ERROR: 請使用 cancel_order(order_id={order_id}, reason='...'"
                    + (", cancel_type='returned'" if status == "returned" else "")
                    + ") 來處理取消/退貨（會自動回補庫存、作廢帳款）"
                )
            if status == "shipped":
                return (
                    f"ERROR: 請使用 fulfill_order(order_id={order_id}) "
                    f"來出貨（會自動扣庫存、建立應收帳款）"
                )
            allowed = _ORDER_TRANSITIONS.get(cur, set())
            if status not in allowed:
                hint = (
                    f"目前狀態 {cur} 可轉換為：{', '.join(allowed)}"
                    if allowed else f"目前狀態 {cur} 無法透過 update_order 轉換"
                )
                return f"ERROR: 訂單 #{order_id} 無法從 {cur} 轉為 {status}。{hint}"
            updates.append("status = ?"); params.append(status)
            if status == "delivered":
                updates.append("delivered_at = ?"); params.append(_now())
        if notes:
            updates.append("notes = ?"); params.append(notes)
        if driver:
            updates.append("driver = ?"); params.append(driver)
        if estimated_delivery:
            updates.append("estimated_delivery = ?"); params.append(estimated_delivery)

        repository.safe_update_order(db, order_id, updates, params)

        detail_parts: list[str] = []
        if status:
            detail_parts.append(f"狀態: {order['status']}→{status}")
        if driver:
            detail_parts.append(f"司機: {driver}")
        if estimated_delivery:
            detail_parts.append(f"預計送達: {estimated_delivery}")

        repository.insert_interaction_log(
            db,
            actor="system",
            action="order_updated",
            target_type="order",
            target_id=order_id,
            detail=" | ".join(detail_parts) or "備註更新",
            business_unit=order["business_unit"],
        )
    return (
        f"訂單 #{order_id} 已更新"
        + (f"（{', '.join(detail_parts)}）" if detail_parts else "")
    )


def qc_order(order_id: int, result: str, notes: str, checked_by: str) -> str:
    if result not in ("passed", "failed", "partial"):
        return "ERROR: result 必須是 passed, failed, 或 partial"

    with transaction() as db:
        order = repository.get_order(db, order_id)
        if not order:
            return f"ERROR: 找不到訂單 #{order_id}"
        if order["status"] not in ("confirmed", "shipped"):
            if order["status"] == "pending":
                return (
                    f"ERROR: 訂單 #{order_id} 尚未確認，"
                    f"請先 update_order(order_id={order_id}, status='confirmed') 後再品檢。"
                )
            return (
                f"ERROR: 訂單 #{order_id} 狀態是 {order['status']}，"
                f"無法進行品檢（需要 confirmed 或 shipped 狀態）"
            )

        now = _now()
        repository.update_qc(
            db,
            order_id=order_id,
            result=result,
            notes=notes or None,
            checked_by=checked_by or None,
            checked_at=now,
            updated_at=now,
        )
        repository.insert_interaction_log(
            db,
            actor=checked_by or "system",
            action="qc_completed",
            target_type="order",
            target_id=order_id,
            detail=f"QC {result}: {notes or '無備註'}",
            business_unit=order["business_unit"],
        )
        if result == "failed":
            # REPORT 硬接線（#9/#173）：QC 不合格主管必知（硬接線、取代下方 _build_guidance 可跳過的軟提示）。
            enqueue_escalation(
                db,
                event_type="qc_failed",
                summary=f"訂單 #{order_id} QC 不合格（{notes or '無備註'}）",
                detail={"order_id": order_id, "result": result, "notes": notes or None,
                        "checked_by": checked_by or None,
                        "business_unit": order["business_unit"]},
                actor_user_id=checked_by or "",
                business_unit=order["business_unit"] or "",
            )
        prev_qc_status = order["qc_status"]
        prev_qc_notes = order["qc_notes"]
        prev_qc_by = order["qc_checked_by"]

    icon = _QC_ICON[result]
    prev_qc = ""
    if prev_qc_status != "pending":
        prev_icon = _QC_ICON.get(prev_qc_status, "")
        prev_qc = f"\n前次 QC：{prev_icon} {prev_qc_status}"
        if prev_qc_notes:
            prev_qc += f"（{prev_qc_notes}）"
        if prev_qc_by:
            prev_qc += f" by {prev_qc_by}"
    msg = f"{icon} 訂單 #{order_id} QC {result}{prev_qc}"
    if result == "passed":
        msg += _build_guidance(next_steps=[f"fulfill_order(order_id={order_id})"])
    elif result == "failed":
        msg += _build_guidance(next_steps=[
            "通知主管處理品質問題",
            f"LINE 通知相關人員：訂單 #{order_id} QC 不合格"
            + (f"，原因：{notes}" if notes else ""),
        ])
    elif result == "partial":
        msg += _build_guidance(next_steps=[
            "列出合格/不合格品項，詢問主管是否部分出貨",
            f"主管核准部分出貨 → fulfill_order(order_id={order_id})",
        ])
    return msg


# ============================================================
# fulfill_order — 出貨：扣庫存 + 訂單狀態 + 應收帳款 + 客戶累計（同一 tx）
# ============================================================

def fulfill_order(order_id: int, partial_items_json: str) -> str:
    with transaction() as db:
        order = repository.get_order(db, order_id)
        if not order:
            return f"ERROR: 找不到訂單 #{order_id}"
        status_check = _validate_fulfill_status(order_id, order)
        if status_check:
            return status_check

        is_followup = order["status"] == "shipped"
        is_partial = False

        if is_followup:
            partial_check = _handle_followup_partial(order, order_id, partial_items_json)
            if partial_check:
                return partial_check
            is_partial = True
        elif order["qc_status"] == "partial":
            partial_check = _handle_qc_partial(order, order_id, partial_items_json)
            if partial_check:
                return partial_check
            is_partial = True
        elif order["qc_status"] != "passed":
            return (
                f"ERROR: 訂單 #{order_id} 尚未通過品質檢查"
                f"（目前 QC 狀態: {order['qc_status']}）。"
                f"請先用 qc_order 工具完成 QC。"
            )

        # 拿 customer（fulfill 顯示用）+ payment terms（凍結用）
        customer = repository.get_customer_full(db, order["customer_id"])
        terms = order["payment_terms"]
        if not terms:
            terms_info = _get_customer_terms(
                db, order["customer_id"], order["business_unit"] or ""
            )
            terms = terms_info["payment_terms"]

        # 決定出貨品項
        if is_partial:
            try:
                ship_items = (
                    json.loads(partial_items_json)
                    if isinstance(partial_items_json, str) else partial_items_json
                )
            except json.JSONDecodeError:
                return "ERROR: partial_items_json 格式錯誤，需要 JSON 陣列"
            # codex P2.14: partial follow-up 出貨量驗證（防過出貨／重複 SKU／未知 SKU）
            ship_validation_error = _validate_partial_ship_items(order, ship_items)
            if ship_validation_error:
                return ship_validation_error
        else:
            ship_items = _parse_items_json(order["items"])

        # 計算出貨金額（部分出貨按比例分攤）
        ship_total = _calc_ship_total(
            order=order, ship_items=ship_items, is_partial=is_partial
        )

        # prepaid / deposit 收款檢查
        prepayment_error = _check_prepayment(db, order_id, terms, ship_total)
        if prepayment_error:
            return prepayment_error

        # 庫存檢查
        errors: list[str] = []
        deductions: list[tuple] = []  # (inventory_id, sku, qty, name)
        order_bu = order["business_unit"] or ""
        for item in ship_items:
            sku = item.get("sku", "")
            qty = item.get("qty", 0)
            if not sku or qty <= 0:
                continue
            inv = _find_inventory(db, sku, order_bu)
            if not inv:
                errors.append(f"找不到 SKU={sku}")
            elif inv["current_stock"] < qty:
                errors.append(
                    f"{inv['name']}({sku}) 庫存 {inv['current_stock']} 不足，需要 {qty}"
                )
            else:
                deductions.append((inv["id"], sku, qty, inv["name"]))
        if errors:
            return "無法出貨，庫存不足：\n" + "\n".join(f"- {e}" for e in errors)

        # 扣庫存（同時釋放 reserved）+ 更新訂單狀態 + 部分出貨更新 items
        for inv_id, sku, qty, _ in deductions:
            repository.deduct_inventory_stock_and_release(db, inv_id, qty)

        now = _now()
        repository.update_status(db, order_id, "shipped", now)

        if is_partial:
            all_items = _parse_items_json(order["items"])
            shipped_skus = {si.get("sku"): si.get("qty", 0) for si in ship_items}
            for ai in all_items:
                sku = ai.get("sku", "")
                if sku in shipped_skus:
                    ai["shipped_qty"] = ai.get("shipped_qty", 0) + shipped_skus[sku]
            note_label = "[補出貨]" if is_followup else "[部分出貨] 僅出貨合格品項"
            repository.update_items_with_note(
                db, order_id, json.dumps(all_items, ensure_ascii=False), note_label
            )

        # 建立應收帳款（根據付款條件設 due_date）
        due_date = _calc_due_date(terms, order)
        receivable = _calc_receivable(db, order_id, terms, ship_total)
        if receivable > 0:
            desc_suffix = "（部分出貨）" if is_partial else ""
            repository.insert_receivable(
                db,
                amount=receivable,
                description=(
                    f"訂單 #{order_id} {customer['name'] if customer else ''}"
                    f"{desc_suffix}"
                ),
                transaction_date=now[:10],
                customer_id=order["customer_id"],
                order_id=order_id,
                due_date=due_date,
                business_unit=order["business_unit"],
            )

        action_label = "order_partial_fulfilled" if is_partial else "order_fulfilled"
        repository.insert_interaction_log(
            db,
            actor="system",
            action=action_label,
            target_type="order",
            target_id=order_id,
            detail=f"出貨 {len(deductions)} 項品項，應收 NT${ship_total:,.0f}",
            business_unit=order["business_unit"],
        )

        # v4 Bug #2：客戶已出貨累計
        if order["customer_id"]:
            repository.add_customer_fulfilled(
                db, order["customer_id"], ship_total, now[:10]
            )

        # 查扣庫存後低庫存警報（同 tx 內讀、保證一致）
        low_stock_items: list[str] = []
        for inv_id, sku, qty, name in deductions:
            inv_after = repository.get_inventory_status(db, inv_id)
            if (inv_after and inv_after["min_stock"] > 0
                    and inv_after["current_stock"] <= inv_after["min_stock"]):
                low_stock_items.append(
                    f"{name}({sku}) 剩 {inv_after['current_stock']}{inv_after['unit']}，"
                    f"安全庫存 {inv_after['min_stock']}"
                )

        customer_name = customer["name"] if customer else ""

    return _format_fulfill_success(
        order_id=order_id,
        is_partial=is_partial,
        deductions=deductions,
        receivable=receivable,
        terms=terms,
        customer_name=customer_name,
        low_stock_items=low_stock_items,
    )


def _validate_fulfill_status(order_id: int, order) -> str | None:
    if order["status"] in ("confirmed", "shipped"):
        return None
    if order["status"] == "pending":
        return (
            f"ERROR: 訂單 #{order_id} 尚未確認，請先 "
            f"update_order(order_id={order_id}, status='confirmed') 確認訂單，"
            f"再進行品檢和出貨。"
        )
    return f"ERROR: 訂單 #{order_id} 狀態是 {order['status']}，無法出貨"


def _validate_partial_ship_items(order, ship_items) -> str | None:
    """驗證 partial fulfillment 的 ship_items（codex P2 終審 MEDIUM）。

    防禦：
    - 未知 SKU（不在原訂單 items）
    - qty <= 0
    - 重複 SKU
    - qty > (原訂單該 SKU.qty - 已出貨 shipped_qty)

    QC partial 首出時 shipped_qty = 0（即 qty <= 原訂單 qty）；補出貨時則扣已出量。
    """
    if not isinstance(ship_items, list):
        return "ERROR: partial_items_json 必須是 JSON 陣列"
    # codex P2.14 round-2 E1 HIGH: 空 list 會讓 _calc_ship_total fallback 到 total_amount
    # → 零庫存扣減 + 完整 AR、後果嚴重。直接擋。
    if not ship_items:
        return "ERROR: partial_items_json 不可為空 list"

    all_items = _parse_items_json(order["items"])
    remaining_by_sku = {}
    for ai in all_items:
        sku = (ai.get("sku") or "").strip()
        if not sku:
            continue
        remaining_by_sku[sku] = ai.get("qty", 0) - ai.get("shipped_qty", 0)

    seen: set[str] = set()
    errors: list[str] = []
    for idx, si in enumerate(ship_items):
        if not isinstance(si, dict):
            errors.append(f"第 {idx + 1} 項格式不是 object")
            continue
        sku = (si.get("sku") or "").strip()
        qty = si.get("qty", 0)
        if not sku:
            errors.append(f"第 {idx + 1} 項缺 sku")
            continue
        # qty 必須是正整數：庫存是整件計算、不允許 float qty（codex P2.14 round-2 E2 MED）；
        # bool 是 int subclass、明確擋避免 True == 1 通過
        if not isinstance(qty, int) or isinstance(qty, bool) or qty <= 0:
            errors.append(f"SKU={sku} qty={qty!r} 無效（必須是正整數）")
            continue
        if sku in seen:
            errors.append(f"SKU={sku} 在 partial_items_json 重複出現")
            continue
        seen.add(sku)
        if sku not in remaining_by_sku:
            errors.append(f"SKU={sku} 不在原訂單品項清單")
            continue
        remaining = remaining_by_sku[sku]
        if remaining <= 0:
            errors.append(f"SKU={sku} 已全數出貨完畢、無剩餘可補")
            continue
        if qty > remaining:
            errors.append(
                f"SKU={sku} 本次要出 {qty}、超過剩餘未出量 {remaining}"
            )
    if errors:
        return "ERROR: partial 出貨驗證失敗：\n" + "\n".join(f"- {e}" for e in errors)
    return None


def _handle_followup_partial(order, order_id: int, partial_items_json: str) -> str | None:
    if partial_items_json:
        return None
    items_list = _parse_items_json(order["items"])
    unshipped = [
        {"sku": i.get("sku", ""), "qty": i.get("qty", 0) - i.get("shipped_qty", 0)}
        for i in items_list if i.get("qty", 0) - i.get("shipped_qty", 0) > 0
    ]
    if not unshipped:
        return f"ERROR: 訂單 #{order_id} 所有品項都已出貨完畢。"
    items_hint = json.dumps(unshipped, ensure_ascii=False)
    return (
        f"注意：訂單 #{order_id} 已部分出貨，需指定本次要補出的品項。\n"
        f"fulfill_order(order_id={order_id}, partial_items_json='...')\n"
        f"未出貨品項：{items_hint}"
    )


def _handle_qc_partial(order, order_id: int, partial_items_json: str) -> str | None:
    if partial_items_json:
        return None
    items_list = _parse_items_json(order["items"])
    items_hint = json.dumps(
        [{"sku": i.get("sku", ""), "qty": i.get("qty", 0)} for i in items_list],
        ensure_ascii=False,
    )
    return (
        f"注意：訂單 #{order_id} QC 狀態為部分合格（partial）。\n"
        f"請指定要出貨的品項：fulfill_order(order_id={order_id}, "
        f"partial_items_json='[{{\"sku\":\"...\",\"qty\":...}}, ...]')\n"
        f"原始品項參考：{items_hint}\n"
        f"QC 備註：{order['qc_notes'] or '無'}"
    )


def _calc_ship_total(order, ship_items: list, is_partial: bool) -> float:
    """部分出貨：按比例分攤 order.total_amount（已含折扣），確保部分出貨金額正確。"""
    if not is_partial:
        return order["total_amount"]
    all_items = _parse_items_json(order["items"])
    all_items_map = {i.get("sku", ""): i for i in all_items}
    full_raw_total = sum(i.get("price", 0) * i.get("qty", 0) for i in all_items) or 1
    ship_raw_total = 0.0
    for si in ship_items:
        orig = all_items_map.get(si.get("sku", ""))
        if orig and orig.get("price"):
            ship_raw_total += orig["price"] * si.get("qty", 0)
    if ship_raw_total > 0:
        return round(order["total_amount"] * (ship_raw_total / full_raw_total))
    return order["total_amount"]


def _check_prepayment(db, order_id: int, terms: str, ship_total: float) -> str | None:
    if terms == "prepaid":
        paid = repository.sum_paid_income_for_order(db, order_id)
        if paid < ship_total:
            return (
                f"ERROR: 訂單 #{order_id} 客戶付款條件是 prepaid，"
                f"需先收到全額 NT${ship_total:,.0f}（目前已收 NT${paid:,.0f}）"
            )
    elif terms.startswith("deposit_"):
        try:
            deposit_pct = int(terms.split("_")[1]) / 100.0
        except (IndexError, ValueError):
            deposit_pct = 0.3
        paid = repository.sum_paid_income_for_order(db, order_id)
        required = ship_total * deposit_pct
        if paid < required:
            return (
                f"ERROR: 訂單 #{order_id} 客戶付款條件是 {terms}，"
                f"需先收到 {int(deposit_pct*100)}% 訂金 NT${required:,.0f}"
                f"（目前已收 NT${paid:,.0f}）"
            )
    return None


def _calc_due_date(terms: str, order) -> str | None:
    today = datetime.now()
    if terms == "net30":
        return (today + timedelta(days=30)).strftime("%Y-%m-%d")
    if terms == "net60":
        return (today + timedelta(days=60)).strftime("%Y-%m-%d")
    if terms == "cod":
        return order["estimated_delivery"] or (today + timedelta(days=7)).strftime("%Y-%m-%d")
    return None  # prepaid / deposit


def _calc_receivable(db, order_id: int, terms: str, ship_total: float) -> float:
    """prepaid/deposit 已收全額/部分，應收 = 剩餘金額；其他 = ship_total。"""
    if terms == "prepaid" or terms.startswith("deposit_"):
        already_paid = repository.sum_paid_income_for_order(db, order_id)
        return ship_total - already_paid
    return ship_total


def _format_fulfill_success(
    order_id: int,
    is_partial: bool,
    deductions: list[tuple],
    receivable: float,
    terms: str,
    customer_name: str,
    low_stock_items: list[str],
) -> str:
    partial_label = "（部分出貨）" if is_partial else ""
    auto_done = [
        f"庫存已扣減（{len(deductions)} 項品項）{partial_label}",
        "訂單狀態 → shipped",
    ]
    if receivable > 0:
        auto_done.append(f"應收帳款 NT${receivable:,.0f} 已建立（{terms}）")

    next_steps = [
        f"update_order(order_id={order_id}, driver='司機名或物流單號', "
        f"estimated_delivery='YYYY-MM-DD')",
        f"LINE 通知客戶 {customer_name}：訂單 #{order_id} 已出貨{partial_label}",
    ]
    if is_partial:
        next_steps.append("處理不合格品項：退回供應商 / 報廢 / 重新品檢")
    if low_stock_items:
        next_steps.append("庫存警報需處理：\n   " + "\n   ".join(low_stock_items))

    warnings = [
        "不要再手動 update_stock（已自動扣庫存）",
        "不要再手動 record_transaction（已自動建應收帳款）",
    ]
    guidance = _build_guidance(
        auto_done=auto_done, next_steps=next_steps, warnings=warnings
    )

    deduct_str = "\n".join(
        f"  - {name}({sku}) -{qty}" for _, sku, qty, name in deductions
    )
    return (
        f"訂單 #{order_id} 已出貨{partial_label}\n"
        f"庫存扣減：\n{deduct_str}\n"
        f"應收帳款：NT${receivable:,.0f}（{terms}）"
        + guidance
    )


# ============================================================
# cancel_order — 取消/退貨：回補庫存 + 客戶累計反扣 + 待收帳款作廢
# ============================================================

def cancel_order(
    order_id: int, reason: str, cancel_type: str, actor_user_id: str
) -> str:
    if not reason.strip():
        return "ERROR: 必須提供取消/退貨原因"
    if cancel_type not in ("cancelled", "returned"):
        return "ERROR: cancel_type 必須是 cancelled 或 returned"

    with transaction() as db:
        perm_err = _check_permission(db, actor_user_id, "manager")
        if perm_err:
            return perm_err
        order = repository.get_order(db, order_id)
        if not order:
            return f"ERROR: 找不到訂單 #{order_id}"
        if order["status"] in ("cancelled", "returned"):
            return f"ERROR: 訂單 #{order_id} 已經是 {order['status']} 狀態"

        auto_done: list[str] = []
        warnings: list[str] = []
        was_fulfilled = order["status"] in ("shipped", "delivered", "paid")

        items = _parse_items_json(order["items"])
        order_bu = order["business_unit"] or ""

        # 庫存處理：已出貨 → 回補 current_stock（用 effective shipped_qty）；
        #          未出貨 → 釋放 reserved
        if was_fulfilled:
            stock_restored = _restore_shipped_inventory(db, items, order_bu, warnings)
            if stock_restored:
                auto_done.append(f"庫存已回補：{', '.join(stock_restored)}")
        else:
            reserved_released = _release_unshipped_reserved(db, items, order_bu)
            if reserved_released:
                auto_done.append(f"預留已釋放：{', '.join(reserved_released)}")

        # v4 Bug #2：客戶累計反扣
        # total_ordered 用整張 total_amount（下單時就是整張累計）
        # total_fulfilled 用 effective_fulfilled_total — 部分出貨時不能用整張
        # （codex P2.11 找到的 bug：fulfill 用 ship_total 但 cancel 用 total_amount，
        # 部分出貨後取消會 over-reverse）
        if order["customer_id"]:
            repository.reduce_customer_ordered(
                db, order["customer_id"], order["total_amount"]
            )
            if was_fulfilled:
                effective_fulfilled = _calc_fulfilled_total(order)
                repository.reduce_customer_fulfilled(
                    db, order["customer_id"], effective_fulfilled
                )

        # 統計已收 + 作廢待收
        all_income_txns = repository.list_income_txns_for_order(db, order_id)
        total_paid = sum(t["paid_amount"] for t in all_income_txns)
        voided_txns = [
            t for t in all_income_txns if t["payment_status"] in ("pending", "overdue")
        ]
        for txn in voided_txns:
            repository.delete_transaction(db, txn["id"])
            repository.insert_interaction_log(
                db,
                actor="system",
                action="transaction_voided",
                target_type="transaction",
                target_id=txn["id"],
                detail=(
                    f"訂單 #{order_id} {cancel_type}，"
                    f"作廢應收帳款 NT${txn['amount']:,.0f}"
                    f"（已收 NT${txn['paid_amount']:,.0f}）"
                ),
                business_unit=order["business_unit"],
            )
        if voided_txns:
            voided_total = sum(t["amount"] - t["paid_amount"] for t in voided_txns)
            auto_done.append(
                f"已作廢 {len(voided_txns)} 筆待收帳款（未收 NT${voided_total:,.0f}）"
            )

        repository.update_cancel(
            db,
            order_id=order_id,
            cancel_type=cancel_type,
            cancel_note=f"[{cancel_type}] {reason}",
            updated_at=_now(),
        )
        repository.insert_interaction_log(
            db,
            actor="system",
            action=f"order_{cancel_type}",
            target_type="order",
            target_id=order_id,
            detail=reason,
            business_unit=order["business_unit"],
        )
        if was_fulfilled:
            # REPORT 硬接線（#9/#173）：已出貨/已收款訂單被取消退貨＝不可逆高風險，主管必知。
            enqueue_escalation(
                db,
                event_type="order_cancelled_shipped",
                summary=(
                    f"已出貨訂單 #{order_id} 被"
                    f"{'退貨' if cancel_type == 'returned' else '取消'}"
                    f"（原因：{reason}）"
                ),
                detail={"order_id": order_id, "cancel_type": cancel_type,
                        "reason": reason, "prev_status": order["status"],
                        "total_amount": order["total_amount"],
                        "total_paid": total_paid,
                        "business_unit": order["business_unit"]},
                actor_user_id=actor_user_id,
                business_unit=order["business_unit"] or "",
            )

    auto_done.append(f"訂單狀態 → {cancel_type}")
    next_steps: list[str] = []
    if total_paid > 0:
        next_steps.append(
            f"客戶已付 NT${total_paid:,.0f} 需退款 → "
            f"record_transaction(type='expense', category='refund', amount={total_paid}, "
            f"description='退款 訂單#{order_id}', related_order_id={order_id})"
        )
        next_steps.append("LINE 通知客戶退款事宜")
    else:
        next_steps.append("LINE 通知客戶訂單已取消")

    guidance = _build_guidance(
        auto_done=auto_done, next_steps=next_steps, warnings=warnings or None
    )
    label = "退貨" if cancel_type == "returned" else "取消"
    return f"訂單 #{order_id} 已{label}\n原因：{reason}" + guidance


def _calc_fulfilled_total(order) -> float:
    """算 order 已 fulfilled 的 effective total（用於 cancel 反扣 customer.total_fulfilled）。

    - 完整出貨（items 內無 shipped_qty 欄位）→ 整張 total_amount
    - 部分出貨（fulfill 寫了 shipped_qty 進 items）→ 按比例分攤 total_amount

    codex P2.11 找到 first bug：原本 cancel 用 total_amount 反扣 fulfilled，但
    fulfill 部分出貨用的是 ship_total（按比例），部分出貨後取消會 over-reverse。

    codex P2 終審找到 second bug：fulfill_order 完整出貨時不會把 shipped_qty 寫回
    items（is_partial 才寫），原本判斷式 `shipped_qty < qty` 對完整出貨會 True、
    錯誤走 partial 分支、shipped_raw_total = 0 → 反扣金額變 0、完全沒反扣到。
    改用「items 內是否有 shipped_qty 欄位」當判斷 — 沒欄位 = 完整出貨；
    有欄位 = 部分出貨（fulfill 走 is_partial 路徑時才寫）。
    """
    all_items = _parse_items_json(order["items"])
    has_partial_marker = any("shipped_qty" in i for i in all_items)
    if not has_partial_marker:
        return order["total_amount"]
    full_raw_total = sum(i.get("price", 0) * i.get("qty", 0) for i in all_items) or 1
    shipped_raw_total = sum(
        i.get("price", 0) * i.get("shipped_qty", 0) for i in all_items
    )
    return round(order["total_amount"] * (shipped_raw_total / full_raw_total))


def _restore_shipped_inventory(
    db, items: list, order_bu: str, warnings: list[str]
) -> list[str]:
    """用 shipped_qty（effective delta）回補，避免部分出貨時多補。"""
    stock_restored: list[str] = []
    for item in items:
        sku = item.get("sku", "")
        qty = item.get("shipped_qty", item.get("qty", 0))
        if not sku or qty <= 0:
            continue
        inv = _find_inventory(db, sku, order_bu)
        if inv:
            repository.restore_inventory_stock(db, inv["id"], qty)
            stock_restored.append(f"{inv['name']}({sku}) +{qty}")
        else:
            warnings.append(f"找不到 SKU={sku} 的庫存紀錄，無法回補")
    return stock_restored


def _release_unshipped_reserved(
    db, items: list, order_bu: str
) -> list[str]:
    """未出貨訂單取消：釋放 create_order 當時的 reserved。"""
    reserved_released: list[str] = []
    for item in items:
        sku = (item.get("sku") or "").strip()
        qty = int(item.get("qty") or 0)
        if not sku or qty <= 0:
            continue
        inv = _find_inventory(db, sku, order_bu)
        if inv:
            repository.release_inventory_reserved(db, inv["id"], qty)
            reserved_released.append(f"{inv['name']}({sku}) -{qty}")
    return reserved_released
