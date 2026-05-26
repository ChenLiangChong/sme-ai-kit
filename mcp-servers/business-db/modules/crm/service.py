"""CRM service — 客戶/供應商/經銷商業務邏輯（含事業體專屬條件）。

層次邊界：transaction ownership 在這層，repository 不 commit。
"""
from shared.business_units import _validate_business_unit
from shared.db import get_db, transaction

from . import repository

_TYPE_LABEL = {"customer": "客戶", "supplier": "供應商", "distributor": "經銷商"}
_TYPE_ICON = {"customer": "[客戶]", "supplier": "[供應商]", "distributor": "[經銷商]"}
_STAGE_ICON = {
    "prospect": "[潛在]", "contacted": "[已接觸]", "negotiating": "[談判中]",
    "closed_won": "[已成交]", "closed_lost": "[已流失]",
}
_STAGE_ZH = {
    "prospect": "潛在", "contacted": "已接觸", "negotiating": "談判中",
    "closed_won": "已成交", "closed_lost": "已流失", "none": "未設定",
}


def add_customer(
    name: str,
    type_: str,
    phone: str,
    email: str,
    line_user_id: str,
    tags: str,
    notes: str,
    discount_rate: float,
    payment_terms: str,
    primary_business_unit: str,
) -> str:
    if type_ not in ("customer", "supplier", "distributor"):
        return "ERROR: type 必須是 customer, supplier, 或 distributor"

    with transaction() as db:
        bu_warn = (
            _validate_business_unit(db, primary_business_unit)
            if primary_business_unit else ""
        )
        cust_id = repository.insert_customer(
            db,
            name=name,
            type_=type_,
            phone=phone or None,
            email=email or None,
            line_user_id=line_user_id or None,
            tags=tags or None,
            notes=notes or None,
            discount_rate=discount_rate,
            payment_terms=payment_terms,
            primary_business_unit=primary_business_unit or None,
        )
        type_label = _TYPE_LABEL.get(type_, type_)
        repository.insert_interaction_log(
            db,
            actor="system",
            action="customer_added",
            target_type="customer",
            target_id=cust_id,
            detail=f"新增{type_label} {name}",
            business_unit=primary_business_unit or None,
        )
    bu_label = f" [{primary_business_unit}]" if primary_business_unit else ""
    line_label = " LINE已綁定" if line_user_id else ""
    return f"客戶 #{cust_id} {name}{bu_label} 已建立（{payment_terms}）{line_label}{bu_warn}"


def find_customer(query: str, type_: str) -> str:
    db = get_db()
    try:
        rows = repository.search_customers(db, query, type_)
        if not rows:
            return f"找不到與「{query}」相關的{'客戶' if not type_ else type_}。"
        lines = [f"## 搜尋結果：「{query}」"]
        for c in rows:
            icon = _TYPE_ICON.get(c["type"], "[客戶]")
            stage = ""
            if c["pipeline_stage"] and c["pipeline_stage"] != "none":
                stage = f" {_STAGE_ICON.get(c['pipeline_stage'], c['pipeline_stage'])}"
            terms_str = (
                f"{c['payment_terms']}"
                if c["payment_terms"] and c["payment_terms"] != "net30" else ""
            )
            discount_str = (
                f"{c['discount_rate']*100:.0f}%off"
                if c["discount_rate"] and c["discount_rate"] > 0 else ""
            )
            bu_label = f" [{c['primary_business_unit']}]" if c["primary_business_unit"] else ""
            sales_fig = c["total_fulfilled"] or c["total_purchases"] or 0
            sales_label = f"{sales_fig:,.0f}" if sales_fig else ""
            last_date = c["last_fulfilled_date"] or c["last_purchase_date"]
            date_label = f"{last_date}" if last_date else ""
            lines.append(
                f"- {icon} [#{c['id']}] **{c['name']}**{bu_label}{stage} {c['phone'] or ''}"
                f"{sales_label}{date_label}"
                f"{terms_str}{discount_str} "
                f"{c['tags'] or ''}"
            )
        return "\n".join(lines)
    finally:
        db.close()


def get_customer(customer_id: int) -> str:
    db = get_db()
    try:
        c = repository.get_customer(db, customer_id)
        if not c:
            return f"ERROR: 找不到客戶 #{customer_id}"

        type_zh = _TYPE_LABEL.get(c["type"], "客戶")
        stage_zh = _STAGE_ZH.get(c["pipeline_stage"], c["pipeline_stage"] or "未設定")
        bu_label = f"（{c['primary_business_unit']}）" if c["primary_business_unit"] else ""

        terms = repository.list_entity_terms(db, customer_id)
        terms_str = ""
        if terms:
            term_lines = [
                f"  - {t['business_unit']}：折扣 {(t['discount_rate'] or 0)*100:.0f}% "
                f"/ 付款條件 {t['payment_terms'] or '預設'}"
                for t in terms
            ]
            terms_str = "\n- 各事業體條件：\n" + "\n".join(term_lines)

        payment_str = f" / 付款條件 {c['payment_terms']}" if c["payment_terms"] else ""

        return (
            f"## {type_zh} #{customer_id}：{c['name']}{bu_label}\n"
            f"- 類型：{type_zh}（{c['type']}）\n"
            f"- 階段：{stage_zh}\n"
            f"- 電話：{c['phone'] or '無'}\n"
            f"- Email：{c['email'] or '無'}\n"
            f"- LINE：{c['line_user_id'] or '未綁定'}\n"
            f"- 標籤：{c['tags'] or '無'}\n"
            f"- 預設條件：折扣 {(c['discount_rate'] or 0)*100:.0f}%{payment_str}"
            f"{terms_str}\n"
            f"- 累計購買：NT${c['total_purchases'] or 0:,.0f} / "
            f"訂購 NT${c['total_ordered'] or 0:,.0f} / "
            f"已付 NT${c['total_paid'] or 0:,.0f}\n"
            f"- 最後購買：{c['last_purchase_date'] or '無'}\n"
            f"- 最後訂單：{c['last_order_date'] or '無'}\n"
            f"- 最後付款：{c['last_payment_date'] or '無'}\n"
            f"- 建立：{c['created_at']}\n"
            f"\n### 備註\n{c['notes'] or '（無）'}"
        )
    finally:
        db.close()


def update_customer(
    customer_id: int,
    name: str,
    phone: str,
    email: str,
    line_user_id: str,
    tags: str,
    notes: str,
    pipeline_stage: str,
    total_purchases: float,
    discount_rate: float,
    payment_terms: str,
    primary_business_unit: str,
) -> str:
    with transaction() as db:
        cust = repository.get_customer(db, customer_id)
        if not cust:
            return f"ERROR: 找不到客戶 #{customer_id}"

        updates: list[str] = []
        params: list = []
        if name:
            updates.append("name = ?"); params.append(name)
        if phone:
            updates.append("phone = ?"); params.append(phone)
        if email:
            updates.append("email = ?"); params.append(email)
        if line_user_id != "__SKIP__":
            updates.append("line_user_id = ?"); params.append(line_user_id or None)
        if tags:
            updates.append("tags = ?"); params.append(tags)
        if notes:
            updates.append("notes = ?"); params.append(notes)
        if pipeline_stage:
            updates.append("pipeline_stage = ?"); params.append(pipeline_stage)
        if total_purchases >= 0:
            updates.append("total_purchases = ?"); params.append(total_purchases)
        if discount_rate >= 0:
            updates.append("discount_rate = ?"); params.append(discount_rate)
        if payment_terms:
            updates.append("payment_terms = ?"); params.append(payment_terms)
        if primary_business_unit != "__SKIP__":
            updates.append("primary_business_unit = ?")
            params.append(primary_business_unit or None)

        if not updates:
            return "沒有指定要更新的欄位。"

        repository.safe_update_customer(db, customer_id, updates, params)
        changed = ", ".join(u.split(" = ")[0] for u in updates)
        repository.insert_interaction_log(
            db,
            actor="system",
            action="customer_updated",
            target_type="customer",
            target_id=customer_id,
            detail=f"更新 {cust['name']}：{changed}",
            business_unit=None,
        )
    return f"客戶 #{customer_id} 已更新"


def set_entity_terms(
    customer_id: int,
    business_unit: str,
    discount_rate: float,
    payment_terms: str,
) -> str:
    with transaction() as db:
        cust = repository.get_customer_name(db, customer_id)
        if not cust:
            return f"ERROR: 找不到客戶 #{customer_id}"

        existing = repository.get_entity_terms(db, customer_id, business_unit)

        if existing:
            updates: list[str] = []
            params: list = []
            if discount_rate >= 0:
                updates.append("discount_rate = ?"); params.append(discount_rate)
            if payment_terms:
                updates.append("payment_terms = ?"); params.append(payment_terms)
            if not updates:
                return "沒有指定要更新的欄位。"
            repository.safe_update_entity_terms(
                db, customer_id, business_unit, updates, params
            )
            detail = (
                f"更新 {cust['name']} 在 {business_unit} 條件："
                f"{', '.join(u.split(' = ')[0] for u in updates)}"
            )
            repository.insert_interaction_log(
                db,
                actor="system",
                action="customer_terms_updated",
                target_type="customer",
                target_id=customer_id,
                detail=detail,
                business_unit=business_unit,
            )
            return f"已更新 {cust['name']} 在 {business_unit} 的條件"

        dr = discount_rate if discount_rate >= 0 else 0
        pt = payment_terms or "net30"
        repository.insert_entity_terms(db, customer_id, business_unit, dr, pt)
        repository.insert_interaction_log(
            db,
            actor="system",
            action="customer_terms_set",
            target_type="customer",
            target_id=customer_id,
            detail=f"設定 {cust['name']} 在 {business_unit} 條件：折扣 {dr*100:.0f}%，付款 {pt}",
            business_unit=business_unit,
        )
    return f"已設定 {cust['name']} 在 {business_unit} 的條件：折扣 {dr*100:.0f}%，付款 {pt}"
