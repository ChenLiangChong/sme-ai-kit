"""Accounting service — 收支記帳 + 應收應付 業務邏輯。

層次邊界：transaction ownership 在這層，repository 不 commit。
Approval gate / guidance 在這層（codex 警告：repository 不該知道這些）。

Codex P2 spot-check 三個警告全部落實：
1. record_transaction：approval gate / insert / audit / 訂單付款 guidance 全在 service
   私有 helper、repository 只負責 SQL。
2. check_overdue 雖看似 read 但會 UPDATE pending → overdue，所以用 with transaction()。
3. record_payment 三段（update transactions + update customers + audit）必須同一個
   service transaction，全包在同一個 with transaction() 區塊內。
"""
import json
from datetime import datetime

from shared.auth import _check_permission
from shared.business_units import _get_approval_threshold, _validate_business_unit
from shared.db import _now, get_db, transaction
from shared.escalation import enqueue_escalation
from shared.utils import _build_guidance

from modules.approvals import service as approvals_service

from . import repository

_TYPE_ICON = {"income": "[收入]", "expense": "[支出]"}
_STATUS_LABEL = {"paid": "已付", "pending": "待收付", "overdue": "逾期"}
_TYPE_ZH = {"income": "收入", "expense": "支出"}
_PAYMENT_STATUS_ZH = {"paid": "已付清", "pending": "待付", "overdue": "逾期"}


# ============================================================
# record_transaction（含 approval gate + insert + audit + 訂單付款 guidance）
# ============================================================

def record_transaction(
    type_: str,
    amount: float,
    category: str,
    description: str,
    transaction_date: str,
    related_customer_id: int,
    related_order_id: int,
    related_invoice: str,
    business_unit: str,
    payment_status: str,
    due_date: str,
    recorded_by: str,
    approved_id: int,
) -> str:
    if type_ not in ("income", "expense"):
        return "ERROR: type 必須是 income 或 expense"
    if amount <= 0:
        return "ERROR: 金額必須是正數"

    if not transaction_date:
        transaction_date = _now()[:10]

    if payment_status not in ("paid", "pending", "overdue"):
        payment_status = "paid"
    paid = amount if payment_status == "paid" else 0.0

    # codex P2.13 + P3a：gate + verify + insert + consume 全在同一 transaction
    # （鎖定 state、防 race；approval 必驗 resume_action + 關鍵 params + 單次消耗）。
    # approved_id 提供 → 用 IMMEDIATE 鎖、確保並發兩 client 共用同 approval 時、
    # 輸家不會白做 insert 再 rollback。
    tx_mode = "immediate" if approved_id else "deferred"
    with transaction(mode=tx_mode) as db:
        threshold = _get_approval_threshold(db, business_unit)
        gate = approvals_service.gate_check(
            db,
            approved_id=approved_id,
            amount=amount,
            threshold=threshold,
            expected_action="record_transaction",
            verify_fields={
                # codex round-2 MED：綁定完整 resume_params（除 recorded_by），防「同金額同類型、
                # 改掛別的客戶/訂單/發票/類別」重用已核准 approval。鍵需與 _txn_resume_detail
                # 的 resume_params 一致（缺鍵會被 verify_resume_params 當「approval 缺此欄位」拒絕）。
                "type": type_,
                "amount": amount,
                "category": category,
                "description": description,
                "transaction_date": transaction_date,
                "related_customer_id": related_customer_id,
                "related_order_id": related_order_id,
                "related_invoice": related_invoice,
                "business_unit": business_unit or "",
                "payment_status": payment_status,
                "due_date": due_date,
            },
        )
        if gate.error:
            return gate.error
        if gate.needs_approval:
            # 系統自建審核（決策 #183）：超門檻時 record_transaction 自己用完整 11 欄
            # resume_params 建審核 + 觸發 approval_pending 上報，不靠 agent 手寫 create_approval。
            # detail 的鍵集合與上方 gate verify_fields 一致 → 核准後 consume 必過。
            approval_id = approvals_service.create_in_tx(
                db,
                type_=type_,
                summary=(
                    f"{_TYPE_ZH.get(type_, type_)} NT${amount:,.0f}（{category}）"
                    f"{description or ''}"
                ).rstrip(),
                detail=_txn_resume_detail(
                    type_=type_, amount=amount, category=category,
                    description=description, transaction_date=transaction_date,
                    related_customer_id=related_customer_id,
                    related_order_id=related_order_id,
                    related_invoice=related_invoice,
                    business_unit=business_unit,
                    payment_status=payment_status, due_date=due_date,
                ),
                requester=recorded_by or "system",
                business_unit=business_unit,
                escalate=True,
            )
            return (
                f"金額 NT${amount:,.0f} 超過審核門檻 NT${threshold:,.0f}，"
                f"已自動建立審核 #{approval_id} 並上報簽核人。"
                + _build_guidance(next_steps=[
                    f"等簽核人核准（LINE 回「核准 #{approval_id}」或全權限層 resolve_approval）",
                    f"核准後由全權限/會計層 session 依審核鎖定的原始參數執行 record_transaction(approved_id={approval_id})、金額/類別一字不差、無需人工重填",
                ])
            )

        txn_id = repository.insert_transaction(
            db,
            type_=type_,
            amount=amount,
            category=category,
            description=description or None,
            transaction_date=transaction_date,
            related_customer_id=related_customer_id or None,
            related_order_id=related_order_id or None,
            related_invoice=related_invoice or None,
            business_unit=business_unit or None,
            payment_status=payment_status,
            due_date=due_date or None,
            paid_amount=paid,
            recorded_by=recorded_by or None,
        )
        repository.insert_interaction_log(
            db,
            actor=recorded_by or "system",
            action="transaction_recorded",
            target_id=txn_id,
            detail=(
                f"{type_} NT${amount:,.0f} [{category}] {payment_status} "
                f"{description or ''}"
            ),
            business_unit=business_unit or None,
        )

        if gate.approval_id:
            approvals_service.gate_consume(
                db,
                approval_id=gate.approval_id,
                consumed_by_type="transaction",
                consumed_by_id=txn_id,
            )
            # REPORT 硬接線（#9/#173）：超門檻帳目核准後執行成功 → 無條件上報主管「已記」。
            # 與 txn 寫入同一 tx＝agent 跳不過；actor/收件人在 enqueue 當下解析寫死、flusher 不重算。
            enqueue_escalation(
                db,
                event_type="transaction_recorded_over_threshold",
                summary=(
                    f"已記一筆超門檻{_TYPE_ZH.get(type_, type_)} "
                    f"NT${amount:,.0f}（{category}）"
                ),
                detail={
                    "txn_id": txn_id, "type": type_, "amount": amount,
                    "category": category, "business_unit": business_unit or None,
                    "approval_id": gate.approval_id, "recorded_by": recorded_by or None,
                },
                actor_user_id=recorded_by or "",
                business_unit=business_unit,
            )

        guidance = ""
        if related_order_id and type_ == "income" and payment_status == "paid":
            guidance = _order_payment_guidance(db, related_order_id)
        bu_warn = _validate_business_unit(db, business_unit)

    icon = _TYPE_ICON.get(type_, "")
    status_label = _STATUS_LABEL.get(payment_status, "")
    base_msg = (
        f"{icon} 帳目 #{txn_id}：{type_} NT${amount:,.0f} "
        f"[{category}] {status_label} {transaction_date}"
    )
    return base_msg + guidance + bu_warn


def _txn_resume_detail(
    *,
    type_: str,
    amount: float,
    category: str,
    description: str,
    transaction_date: str,
    related_customer_id: int,
    related_order_id: int,
    related_invoice: str,
    business_unit: str,
    payment_status: str,
    due_date: str,
) -> str:
    """超門檻記帳 approval 的 detail（完整 11 欄 resume_params）。

    單一真相來源：resume_params 的鍵與值需與 record_transaction 內 gate verify_fields
    完全一致（business_unit 同樣取 `or ""`），核准後 gate_consume 才比對得過。
    系統自建用（決策 #183）、agent 不再手寫。
    """
    return json.dumps({
        "resume_action": "record_transaction",
        "resume_params": {
            "type": type_, "amount": amount, "category": category,
            "description": description, "transaction_date": transaction_date,
            "related_customer_id": related_customer_id,
            "related_order_id": related_order_id,
            "related_invoice": related_invoice,
            "business_unit": business_unit or "",
            "payment_status": payment_status, "due_date": due_date,
        },
        "then": "記帳完成後通知相關人員",
    }, ensure_ascii=False)


def _order_payment_guidance(db, order_id: int) -> str:
    """訂單全額收齊 → 提示 update_order；部分收 → 提示剩餘金額。"""
    order = repository.get_order_status_total(db, order_id)
    if not order or order["status"] in ("paid", "cancelled"):
        return ""
    total_paid = repository.sum_paid_income_for_order(db, order_id)
    if total_paid >= order["total_amount"]:
        return _build_guidance(next_steps=[
            f"update_order(order_id={order_id}, status='paid') — 訂單已全額收款",
            "LINE 通知客戶：已收到款項，感謝！",
        ])
    remaining = order["total_amount"] - total_paid
    return _build_guidance(next_steps=[
        f"訂單 #{order_id} 尚欠 NT${remaining:,.0f}，等待後續付款",
    ])


# ============================================================
# list / monthly_summary / get / delete / update（read + write 各自場景）
# ============================================================

def list_transactions(
    start_date: str,
    end_date: str,
    type_: str,
    category: str,
    business_unit: str,
    related_order_id: int,
    limit: int,
) -> str:
    has_date_filter = bool(start_date or end_date) or not related_order_id
    if has_date_filter:
        if not start_date:
            start_date = _now()[:8] + "01"
        if not end_date:
            end_date = _now()[:10]

    db = get_db()
    try:
        rows = repository.list_transactions(
            db,
            start_date=start_date,
            end_date=end_date,
            has_date_filter=has_date_filter,
            type_=type_,
            category=category,
            business_unit=business_unit,
            related_order_id=related_order_id,
            limit=limit,
        )
        if not rows:
            if related_order_id:
                return f"找不到訂單 #{related_order_id} 的相關帳目。"
            return f"在 {start_date} ~ {end_date} 期間沒有收支記錄。"

        total_income = sum(r["amount"] for r in rows if r["type"] == "income")
        total_expense = sum(r["amount"] for r in rows if r["type"] == "expense")

        date_label = f"{start_date} ~ {end_date}" if has_date_filter else "全部"
        lines = [f"## 收支記錄（{date_label}，共 {len(rows)} 筆）"]
        lines.append(
            f"收入合計: NT${total_income:,.0f} | 支出合計: NT${total_expense:,.0f} "
            f"| 淨額: NT${total_income - total_expense:,.0f}\n"
        )

        for r in rows:
            icon = _TYPE_ICON.get(r["type"], "")
            status_tag = ""
            if r["payment_status"] == "pending":
                status_tag = f" [待收付](已收{r['paid_amount']:,.0f})"
            elif r["payment_status"] == "overdue":
                status_tag = f" [逾期](已收{r['paid_amount']:,.0f})"
            order_tag = f" 訂單#{r['related_order_id']}" if r["related_order_id"] else ""
            bu_tag = (
                f" [{r['business_unit']}]"
                if r["business_unit"] and not business_unit else ""
            )
            lines.append(
                f"- {icon} [#{r['id']}] {r['transaction_date']} NT${r['amount']:,.0f} "
                f"[{r['category'] or '?'}]{bu_tag}{status_tag}{order_tag} "
                f"{r['description'] or ''}"
            )
        return "\n".join(lines)
    finally:
        db.close()


def monthly_summary(year_month: str, business_unit: str) -> str:
    if not year_month:
        year_month = _now()[:7]

    db = get_db()
    try:
        rows = repository.monthly_by_type_category(db, year_month, business_unit)
        if not rows:
            bu_label = f"（{business_unit}）" if business_unit else ""
            return f"{year_month}{bu_label} 沒有收支記錄。"

        income_rows = [r for r in rows if r["type"] == "income"]
        expense_rows = [r for r in rows if r["type"] == "expense"]
        total_income = sum(r["total"] for r in income_rows)
        total_expense = sum(r["total"] for r in expense_rows)

        bu_label = f"（{business_unit}）" if business_unit else ""
        lines = [f"## {year_month} 月度收支彙總{bu_label}"]
        lines.append(
            f"**收入**: NT${total_income:,.0f} | **支出**: NT${total_expense:,.0f} "
            f"| **淨額**: NT${total_income - total_expense:,.0f}\n"
        )

        if income_rows:
            lines.append("### 收入明細")
            for r in income_rows:
                lines.append(
                    f"- [{r['category'] or '未分類'}] NT${r['total']:,.0f}（{r['count']} 筆）"
                )

        if expense_rows:
            lines.append("\n### 支出明細")
            for r in expense_rows:
                lines.append(
                    f"- [{r['category'] or '未分類'}] NT${r['total']:,.0f}（{r['count']} 筆）"
                )

        if not business_unit:
            bu_rows = repository.monthly_by_business_unit(db, year_month)
            if bu_rows:
                lines.append("\n### 事業體分類")
                bus: dict = {}
                for r in bu_rows:
                    bu = r["business_unit"]
                    if bu not in bus:
                        bus[bu] = {"income": 0, "expense": 0}
                    bus[bu][r["type"]] = r["total"]
                for bu, vals in bus.items():
                    net = vals["income"] - vals["expense"]
                    lines.append(
                        f"- **{bu}**: 收入 NT${vals['income']:,.0f} / "
                        f"支出 NT${vals['expense']:,.0f} / 淨額 NT${net:,.0f}"
                    )
                unassigned = repository.monthly_unassigned(db, year_month)
                if unassigned:
                    ua = {r["type"]: r["total"] for r in unassigned}
                    ua_income = ua.get("income", 0)
                    ua_expense = ua.get("expense", 0)
                    lines.append(
                        f"- **未歸類**: 收入 NT${ua_income:,.0f} / "
                        f"支出 NT${ua_expense:,.0f} / "
                        f"淨額 NT${ua_income - ua_expense:,.0f}"
                    )

        return "\n".join(lines)
    finally:
        db.close()


def get_transaction(transaction_id: int) -> str:
    db = get_db()
    try:
        t = repository.get_transaction(db, transaction_id)
        if not t:
            return f"ERROR: 找不到帳目 #{transaction_id}"

        type_zh = _TYPE_ZH.get(t["type"], "帳目")
        if t["description"]:
            summary = t["description"][:30] + ("…" if len(t["description"]) > 30 else "")
        else:
            summary = f"{type_zh} NT${t['amount'] or 0:,.0f} [{t['category'] or '未分類'}]"

        related_customer = ""
        if t["related_customer_id"]:
            cust = repository.get_customer_name(db, t["related_customer_id"])
            related_customer = (
                f"\n- 關聯客戶：[#{t['related_customer_id']}] "
                f"{cust['name'] if cust else '（已刪除）'}"
            )

        related_order = (
            f"\n- 關聯訂單：#{t['related_order_id']}" if t["related_order_id"] else ""
        )
        related_invoice = (
            f"\n- 關聯發票：{t['related_invoice']}" if t["related_invoice"] else ""
        )

        outstanding = (t["amount"] or 0) - (t["paid_amount"] or 0)
        payment_str = ""
        if t["payment_status"]:
            status_zh = _PAYMENT_STATUS_ZH.get(t["payment_status"], t["payment_status"])
            due_str = f" / 到期：{t['due_date']}" if t["due_date"] else ""
            payment_str = (
                f"\n- 付款狀態：{status_zh}（{t['payment_status']}）"
                f"\n- 已付：NT${t['paid_amount'] or 0:,.0f} / "
                f"未付：NT${outstanding:,.0f}{due_str}"
            )

        return (
            f"## 帳目 #{transaction_id}：{summary}\n"
            f"- 類型：{type_zh}（{t['type']}）\n"
            f"- 金額：NT${t['amount'] or 0:,.0f}\n"
            f"- 分類：{t['category'] or '未分類'}\n"
            f"- 事業體：{t['business_unit'] or '全域'}\n"
            f"- 交易日：{t['transaction_date'] or '未設定'}"
            f"{payment_str}"
            f"{related_customer}"
            f"{related_order}"
            f"{related_invoice}\n"
            f"- 記錄人：{t['recorded_by'] or '未知'}\n"
            f"- 建立：{t['created_at']}\n"
            f"\n### 描述\n{t['description'] or '（無）'}"
        )
    finally:
        db.close()


def delete_transaction(transaction_id: int, reason: str, actor_user_id: str) -> str:
    if not reason.strip():
        return "ERROR: 刪除帳目必須填寫原因"

    with transaction() as db:
        perm_err = _check_permission(db, actor_user_id, "manager")
        if perm_err:
            return perm_err
        txn = repository.get_transaction(db, transaction_id)
        if not txn:
            return f"ERROR: 找不到帳目 #{transaction_id}"

        repository.delete_transaction(db, transaction_id)
        repository.insert_interaction_log(
            db,
            actor="system",
            action="transaction_deleted",
            target_id=transaction_id,
            detail=(
                f"刪除 {txn['type']} NT${txn['amount']:,.0f} "
                f"[{txn['category']}]，原因：{reason}"
            ),
            business_unit=txn["business_unit"],
        )
        # REPORT 硬接線（#9/#173）：刪財務紀錄不可逆、主管必知。與刪除同一 tx。
        enqueue_escalation(
            db,
            event_type="transaction_deleted",
            summary=(
                f"刪除帳目 #{transaction_id}：{_TYPE_ZH.get(txn['type'], txn['type'])} "
                f"NT${txn['amount']:,.0f}（{txn['category']}），原因：{reason}"
            ),
            detail={
                "txn_id": transaction_id, "type": txn["type"], "amount": txn["amount"],
                "category": txn["category"], "business_unit": txn["business_unit"],
                "reason": reason,
            },
            actor_user_id=actor_user_id,
            business_unit=txn["business_unit"] or "",
        )
    return f"帳目 #{transaction_id} 已刪除（原因：{reason}）"


def update_transaction(
    transaction_id: int,
    category: str,
    description: str,
    business_unit: str,
    payment_status: str,
    due_date: str,
    related_order_id: int,
    related_customer_id: int,
) -> str:
    with transaction() as db:
        txn = repository.get_transaction(db, transaction_id)
        if not txn:
            return f"ERROR: 找不到帳目 #{transaction_id}"

        updates: list[str] = []
        params: list = []
        detail_parts: list[str] = []

        if category:
            updates.append("category = ?"); params.append(category)
            detail_parts.append(f"分類→{category}")
        if description:
            updates.append("description = ?"); params.append(description)
            detail_parts.append("說明已更新")
        if business_unit != "__SKIP__":
            updates.append("business_unit = ?"); params.append(business_unit or None)
            detail_parts.append(f"事業體→{business_unit or '(清除)'}")
        if payment_status:
            if payment_status not in ("paid", "pending", "overdue"):
                return "ERROR: payment_status 必須是 paid, pending, overdue"
            updates.append("payment_status = ?"); params.append(payment_status)
            if payment_status == "paid":
                updates.append("paid_amount = amount")
            detail_parts.append(f"狀態→{payment_status}")
        if due_date:
            updates.append("due_date = ?"); params.append(due_date)
            detail_parts.append(f"到期日→{due_date}")
        if related_order_id != -1:
            updates.append("related_order_id = ?"); params.append(related_order_id or None)
            detail_parts.append(
                f"訂單→#{related_order_id}" if related_order_id else "訂單→(清除)"
            )
        if related_customer_id != -1:
            updates.append("related_customer_id = ?")
            params.append(related_customer_id or None)
            detail_parts.append(
                f"客戶→#{related_customer_id}" if related_customer_id else "客戶→(清除)"
            )

        if not updates:
            return "沒有要更新的欄位。"

        repository.safe_update_transaction(db, transaction_id, updates, params)
        repository.insert_interaction_log(
            db,
            actor="system",
            action="transaction_updated",
            target_id=transaction_id,
            detail=" | ".join(detail_parts),
            business_unit=txn["business_unit"],
        )
    return f"帳目 #{transaction_id} 已更新（{', '.join(detail_parts)}）"


# ============================================================
# 應收應付（check_overdue + record_payment）
# ============================================================

def check_overdue(business_unit: str) -> str:
    """注意：看似 read 但會自動 promote pending → overdue（codex 警告）。
    全程 with transaction() 保證 promote + list 在同一 tx。"""
    today = _now()[:10]
    with transaction() as db:
        repository.mark_overdue_by_due_date(db, today)
        overdue = repository.list_overdue(db, business_unit)

    if not overdue:
        bu_suffix = f"（{business_unit}）" if business_unit else ""
        return f"目前沒有逾期帳款。{bu_suffix}"

    total_receivable = sum(
        r["amount"] - r["paid_amount"] for r in overdue if r["type"] == "income"
    )
    total_payable = sum(
        r["amount"] - r["paid_amount"] for r in overdue if r["type"] == "expense"
    )

    bu_suffix = f"（{business_unit}）" if business_unit else ""
    lines = [f"## 逾期帳款（{len(overdue)} 筆）{bu_suffix}"]
    today_dt = datetime.strptime(today, "%Y-%m-%d")

    if total_receivable > 0:
        lines.append(f"\n### 應收未收：NT${total_receivable:,.0f}")
        for r in overdue:
            if r["type"] == "income":
                lines.append(_format_overdue_row(r, today_dt, business_unit))

    if total_payable > 0:
        lines.append(f"\n### 應付未付：NT${total_payable:,.0f}")
        for r in overdue:
            if r["type"] == "expense":
                lines.append(_format_overdue_row(r, today_dt, business_unit))

    return "\n".join(lines)


def _format_overdue_row(r, today_dt: datetime, request_bu: str) -> str:
    remaining = r["amount"] - r["paid_amount"]
    days = (today_dt - datetime.strptime(r["due_date"], "%Y-%m-%d")).days
    bu_label = (
        f" [{r['business_unit']}]"
        if r["business_unit"] and not request_bu else ""
    )
    order_tag = f" 訂單#{r['related_order_id']}" if r["related_order_id"] else ""
    return (
        f"- [#{r['id']}]{bu_label}{order_tag} NT${remaining:,.0f} 逾期 "
        f"{days} 天 | {r['description'] or r['category']}"
    )


def record_payment(
    transaction_id: int, amount: float, notes: str, actor_user_id: str
) -> str:
    """三段（update txn + update customer + audit）必須同一 transaction（codex 警告）。"""
    if amount <= 0:
        return "ERROR: 金額必須是正數"

    with transaction() as db:
        perm_err = _check_permission(db, actor_user_id, "manager")
        if perm_err:
            return perm_err
        txn = repository.get_transaction(db, transaction_id)
        if not txn:
            return f"ERROR: 找不到帳目 #{transaction_id}"

        # codex P2.16: 已全額付清明確擋；舊行為會 silently log 一筆 effective=0
        # 的付款 + 回「已全額付清」，操作者看不出是 no-op 還是重複付款。
        # 註：update_transaction 不能調 paid_amount，所以退款管道指向 delete + 重建。
        if txn["paid_amount"] >= txn["amount"]:
            return (
                f"ERROR: 帳目 #{transaction_id} 已全額付清"
                f"（{txn['paid_amount']:,.0f}/{txn['amount']:,.0f}）、"
                f"無需再記款。若為誤記請用 delete_transaction 刪除後重建；"
                f"若需退款請聯絡管理員另行處理。"
            )

        new_paid = txn["paid_amount"] + amount
        remaining = txn["amount"] - new_paid

        if new_paid >= txn["amount"]:
            new_status = "paid"
            new_paid = txn["amount"]  # 不超付
            remaining = 0
        else:
            new_status = "pending"

        # effective delta：超額時用 clamp 後的實際增量，避免 customer total_paid overcount
        # （codex P2.10 spot-check 找到的 pre-existing bug — 原 code 用 raw amount）
        effective_amount = new_paid - txn["paid_amount"]

        repository.update_paid_amount(db, transaction_id, new_paid, new_status)

        # v4 Bug #2：客戶累計（同一 tx，用 effective_amount 避免 overcount）
        if txn["type"] == "income" and txn["related_customer_id"]:
            repository.update_customer_payment_totals(
                db, txn["related_customer_id"], effective_amount, _now()[:10]
            )

        repository.insert_interaction_log(
            db,
            actor="system",
            action="payment_recorded",
            target_id=transaction_id,
            detail=(
                f"付款 NT${amount:,.0f}，累計 NT${new_paid:,.0f}/{txn['amount']:,.0f}。"
                f"{notes}"
            ),
            business_unit=txn["business_unit"],
        )

        # 訂單付款 guidance（讀 orders、同 db）
        guidance = ""
        if txn["related_order_id"]:
            order = repository.get_order_status(db, txn["related_order_id"])
            if new_status == "paid" and order and order["status"] not in ("paid", "cancelled"):
                guidance = _build_guidance(next_steps=[
                    f"update_order(order_id={txn['related_order_id']}, status='paid') "
                    f"— 訂單全額收款完成",
                    "LINE 通知客戶：已收到款項，感謝！",
                ])
            elif new_status != "paid":
                guidance = _build_guidance(next_steps=[
                    f"訂單 #{txn['related_order_id']} 尚欠 NT${remaining:,.0f}",
                ])

    if new_status == "paid":
        return f"帳目 #{transaction_id} 已全額付清（NT${txn['amount']:,.0f}）" + guidance
    return f"帳目 #{transaction_id} 已收到 NT${amount:,.0f}，剩餘 NT${remaining:,.0f}" + guidance
