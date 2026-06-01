"""Approvals service — HITL 審核業務流程（建立 / 核准駁回 / 過期判定 / JSON detail 解析 / gate helper）。

層次邊界：transaction ownership 在這層，repository 不 commit。

P3a HITL gate helper（gate_check + gate_consume + GateResult）抽出了 accounting /
orders 重複的 verify→insert→consume 邏輯；新模組要 HITL 直接套同 pattern。
"""
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from shared.business_units import _validate_business_unit
from shared.db import _now, get_db, transaction
from shared.escalation import enqueue_escalation
from shared.utils import _build_guidance

from . import repository

_APPROVAL_TTL_HOURS = 72
RAW_DETAIL_MAX = 2000  # get_approval 顯示 raw detail 字數上限、防巨型 JSON 吃 token

# Markdown section headers — test 跟 caller 都應引用這兩個 constant、不要重複字面
RAW_DETAIL_HEADER = "### detail (原始)"
NEXT_STEP_HEADER = "### 下一步說明"


def create_in_tx(
    db,
    *,
    type_: str,
    summary: str,
    detail: str,
    requester: str,
    approver: str = "",
    business_unit: str = "",
    ttl_hours: int = _APPROVAL_TTL_HOURS,
    escalate: bool = True,
) -> int:
    """Caller-managed-tx 版的 create approval。回傳 approval_id。

    供其他 service（如 leave/request_leave）在自己的 with transaction() 內呼叫、
    避免「nested transaction」問題。new connection 版的 create() 是這個的 wrapper。

    escalate=True（預設）：審核請求一建立就走 enqueue_escalation 上報「待核准」給簽核人
    （老闆 / 主管）。與 approval 寫入同一 caller-managed tx＝agent 跳不過、不靠 agent 再記得
    「請透過 LINE 通知主管」。actor / 收件人在 enqueue 當下解析寫死（floored 取 verified
    user_id），event_type='approval_pending' 預設開、onboarding 可在 settings 關。
    """
    expires = (datetime.now() + timedelta(hours=ttl_hours)).strftime("%Y-%m-%d %H:%M:%S")
    approval_id = repository.insert_approval(
        db,
        type_=type_,
        summary=summary,
        detail=detail or None,
        requester=requester or "system",
        approver=approver or None,
        business_unit=business_unit or None,
        expires_at=expires,
    )
    if escalate:
        enqueue_escalation(
            db,
            event_type="approval_pending",
            summary=f"#{approval_id}（{type_}）：{summary}",
            detail={
                "approval_id": approval_id, "type": type_,
                "requester": requester or "system",
                "business_unit": business_unit or None,
            },
            actor_user_id="",
            business_unit=business_unit,
        )
    return approval_id


def create(
    type_: str,
    summary: str,
    detail: str,
    approver: str,
    requester: str,
    business_unit: str,
) -> str:
    with transaction() as db:
        approval_id = create_in_tx(
            db,
            type_=type_,
            summary=summary,
            detail=detail,
            requester=requester,
            approver=approver,
            business_unit=business_unit,
        )
        bu_warn = _validate_business_unit(db, business_unit)
    bu_label = f"\n事業體：{business_unit}" if business_unit else ""
    return (
        f"審核請求 #{approval_id} 已建立\n類型：{type_}{bu_label}\n摘要：{summary}\n"
        f"等待審核中（{_APPROVAL_TTL_HOURS} 小時內有效）。系統已自動上報簽核人（老闆/主管）。"
        + bu_warn
    )


# ============================================================
# HITL gate helper（P3a）— accounting / orders / 任何新 HITL caller 統一套 pattern
# ============================================================

@dataclass
class GateResult:
    """HITL approval gate 檢查結果，4 種狀態靠 3 個欄位辨識：

    - error 非 None         → caller 應 return error（approval 無效/不符）
    - needs_approval=True   → caller 應自建審核（create_in_tx）並回提示（金額超門檻、決策 #183）
    - approval_id 非 None    → caller 通過、寫入後須 gate_consume(approval_id)
    - 三者皆預設值          → caller 通過、無需 consume（amount < threshold）
    """
    error: str | None = None
    needs_approval: bool = False
    approval_id: int | None = None


def gate_check(
    db,
    *,
    approved_id: int,
    amount: float = 0,
    threshold: float = 0,
    expected_action: str,
    verify_fields: dict,
    require_approval: bool = False,
) -> GateResult:
    """HITL approval gate（含找 unused approval + verify_resume_params 比對）。

    caller 拿 GateResult、按欄位順序處理：
        gate = approvals_service.gate_check(db, approved_id=..., amount=...,
            threshold=..., expected_action='record_transaction',
            verify_fields={...})
        if gate.error: return gate.error
        if gate.needs_approval: ...自建審核 create_in_tx(db, ...)、回「已建審核 #N」（決策 #183）
        # ... 業務寫入 ...
        if gate.approval_id:
            approvals_service.gate_consume(db, approval_id=gate.approval_id,
                consumed_by_type='transaction', consumed_by_id=txn_id)

    Args:
        db: sqlite3.Connection（caller-managed tx，approved_id 場景應已用 IMMEDIATE 開）
        approved_id: caller 傳入的 approval id（0 = 沒提供 = 純走門檻檢查）
        amount: 業務金額（>= threshold 才會觸發 approval 需求；非金額場景填 0）
        threshold: 該 business_unit 的審核門檻（非金額場景填 0）
        expected_action: detail.resume_action 必須等於此值（防 approval 挪用）
        verify_fields: detail.resume_params 必須包含的 key/value 子集（防改參數重用）
        require_approval: True=不靠 amount/threshold 機制、必須有 approval（如請假
            必須先送簽核才能 approve_leave）。codex P3b D1 修法。

    Returns:
        GateResult — caller 按欄位順序判斷
    """
    if approved_id:
        approval = repository.get_approved_unused(db, approved_id)
        if not approval:
            return GateResult(
                error=f"ERROR: 審核 #{approved_id} 不存在、未核准或已使用"
            )
        mismatch = verify_resume_params(approval, expected_action, verify_fields)
        if mismatch:
            return GateResult(error=mismatch)
        return GateResult(approval_id=approval["id"])
    if require_approval:
        return GateResult(
            error="ERROR: 此操作必須提供 approved_id（先 resolve_approval 後再呼叫）"
        )
    if amount >= threshold:
        return GateResult(needs_approval=True)
    return GateResult()


def gate_consume(
    db,
    *,
    approval_id: int,
    consumed_by_type: str,
    consumed_by_id: int,
) -> None:
    """Approval 單次消耗（含 rowcount=1 race guard、rollback-on-fail）。

    caller-managed tx，helper 不開 tx。WHERE consumed_at IS NULL 防同 tx 雙寫；
    rowcount != 1 raise RuntimeError 觸發 with transaction() 的 rollback。
    """
    rowcount = repository.mark_consumed(
        db, approval_id, _now(), consumed_by_type, consumed_by_id
    )
    if rowcount != 1:
        raise RuntimeError(
            f"審核 #{approval_id} 消耗失敗（rowcount={rowcount}）"
        )


def expire_stale_approvals(db) -> int:
    """過期 waiting approvals：超過 expires_at 仍 waiting → 改 status='expired'。

    供 maintenance flow（如 get_context_summary 啟動掃描）呼叫。caller 必須用
    `with transaction()` 包；helper 自己不開 tx、不 commit。回傳影響行數。

    Args:
        db: sqlite3.Connection（caller-managed tx）

    Returns:
        受影響行數（過期了幾筆）
    """
    cursor = db.execute(
        "UPDATE approvals SET status = 'expired' "
        "WHERE status = 'waiting' AND expires_at IS NOT NULL AND expires_at < ?",
        (_now(),),
    )
    return cursor.rowcount


def resolve(approval_id: int, decision: str, decided_by: str) -> str:
    if decision not in ("approved", "rejected"):
        return "ERROR: decision 必須是 approved 或 rejected"

    with transaction() as db:
        # 簽核權限（#24）：非全權限層（部門 session）必須由 line-channel 驗證過的 manager 以上
        # 操作者執行——防部門基層員工冒名核准財務/敏感審核。actor 走 active-request（agent 不可
        # 偽造）、查不到當前 LINE 脈絡 → __unverified__ → _check_permission 擋下。全權限層
        # （confidential / operator＝老闆自己的可信 session）放行、不卡終端機直打的核准。
        from shared.floor_policy import is_full_access
        if not is_full_access():
            from shared.auth import _check_permission
            perm_err = _check_permission(db, "", "manager")
            if perm_err:
                return (
                    f"ERROR: 無權簽核審核 #{approval_id}"
                    f"（{perm_err.removeprefix('ERROR: ')}）。"
                    "簽核需 manager 以上、且須由本人 LINE 操作。"
                )
        approval = repository.get_waiting(db, approval_id)
        if not approval:
            expired = repository.get_expired(db, approval_id)
            if expired:
                return f"ERROR: 審核 #{approval_id} 已過期，請重新建立審核請求"
            return f"ERROR: 找不到待審核項目 #{approval_id}"

        if approval["expires_at"]:
            try:
                expires_dt = datetime.strptime(approval["expires_at"], "%Y-%m-%d %H:%M:%S")
                if datetime.now() > expires_dt:
                    repository.mark_expired(db, approval_id)
                    return (
                        f"ERROR: 審核 #{approval_id} 已過期（{approval['expires_at']}），"
                        f"請重新建立審核請求"
                    )
            except (ValueError, TypeError):
                pass

        repository.mark_decided(db, approval_id, decision, decided_by, _now())
        repository.insert_interaction_log(
            db,
            actor=decided_by,
            action=f"approval_{decision}",
            target_type="approval",
            target_id=approval_id,
            detail=approval["summary"],
            business_unit=approval["business_unit"],
        )

    return _format_decision(approval, approval_id, decision, decided_by)


def get_approval(approval_id: int) -> str:
    """查單筆 approval 全部欄位（含 detail / consumed_at / decided_by 等）。
    給 leave-ops / accounting-ops 失敗情境判讀用：被 gate 擋下時、agent 可以查
    approval 現況決定如何回報老闆，不必繞 sqlite。"""
    db = get_db()
    try:
        approval = repository.get(db, approval_id)
        if not approval:
            return f"ERROR: 找不到審核 #{approval_id}"

        lines = [f"## 審核 #{approval_id}"]
        lines.append(f"- 類型：{approval['type']}")
        lines.append(f"- 摘要：{approval['summary']}")
        lines.append(f"- 狀態：{approval['status']}")
        if approval["business_unit"]:
            lines.append(f"- 事業體：{approval['business_unit']}")
        lines.append(f"- 申請人：{approval['requester'] or 'system'}")
        lines.append(f"- 建立：{approval['created_at']}")
        if approval["expires_at"]:
            lines.append(f"- 過期：{approval['expires_at']}")
        # approver 欄位儲存兩種語意：建立時 = 指定審核人；resolve 後 = 實際決定者
        if approval["decided_at"]:
            lines.append(
                f"- 決定者：{approval['approver'] or '（未記名）'}"
                f"（{approval['decided_at']}）"
            )
        elif approval["approver"]:
            lines.append(f"- 指定審核人：{approval['approver']}")
        if approval["consumed_at"]:
            consumed_target = (
                f"{approval['consumed_by_type']} #{approval['consumed_by_id']}"
                if approval["consumed_by_id"] else approval["consumed_by_type"]
            )
            lines.append(f"- 已消費：{approval['consumed_at']}（by {consumed_target}）")
        if approval["detail"]:
            # 原始 detail（agent 可解析 resume_params）— cap 防巨型 JSON 吃 token
            raw = approval["detail"]
            truncated = len(raw) > RAW_DETAIL_MAX
            shown = raw[:RAW_DETAIL_MAX] + (
                f"\n[截斷、原始長度 {len(raw)} 字]" if truncated else ""
            )
            lines.append(f"\n{RAW_DETAIL_HEADER}")
            lines.append(shown)
            # 可格式化才附「下一步說明」（純文字 / non-dict detail 直接 skip 不重複輸出）
            formatted = _format_resume_detail(approval["detail"])
            if formatted:
                lines.append(f"\n{NEXT_STEP_HEADER}")
                lines.append(formatted.lstrip("\n"))
        return "\n".join(lines)
    finally:
        db.close()


def verify_resume_params(
    approval, expected_action: str, fields_to_match: dict
) -> str | None:
    """驗證 approval.detail 的 resume_action / resume_params 是否符合 caller 預期。

    供 record_transaction / create_order 等 HITL gate caller 在 write transaction 內
    呼叫。回傳 None=OK、否則回傳 ERROR 訊息（供 caller 直接 return）。

    Args:
        approval: sqlite3.Row（從 get_approved_unused 取得）
        expected_action: 預期的 resume_action（如 'record_transaction'、'create_order'）
        fields_to_match: 必須比對的 resume_params 子集；比對規則見 _values_equivalent

    Behavior:
        - 沒有 detail → 拒絕（無法驗證使用意圖）
        - detail 不是合法 JSON → 拒絕
        - resume_action 不符 → 拒絕（防止挪用其他用途的 approval）
        - fields_to_match key 不存在於 resume_params → 拒絕（缺資訊不放行）
        - fields_to_match 中任一欄位值不符 → 拒絕（防止改參數後重用）
    """
    if not approval["detail"]:
        return (
            f"ERROR: 審核 #{approval['id']} 沒有 resume detail、無法驗證使用意圖。"
            "建立 approval 時請帶 detail JSON、包含 resume_action 與 resume_params。"
        )
    try:
        detail_obj = json.loads(approval["detail"])
    except (json.JSONDecodeError, TypeError):
        return f"ERROR: 審核 #{approval['id']} detail 格式錯誤（非合法 JSON）"
    if not isinstance(detail_obj, dict):
        return f"ERROR: 審核 #{approval['id']} detail 格式錯誤（resume detail 應為物件）"

    actual_action = detail_obj.get("resume_action", "")
    if actual_action != expected_action:
        return (
            f"ERROR: 審核 #{approval['id']} 是 {actual_action!r} 用、"
            f"不能用於 {expected_action!r}（防止 approval 挪作他用）"
        )

    # 不用 `or {}`：falsy 非 dict（[] / "" / 0 / false / null）要走下面「格式錯誤」分支、不可被
    # 靜默轉成 {}（否則退化成「缺欄位」訊息、型別錯誤被吞）。只有 key 缺失才用預設 {}。
    actual_params = detail_obj.get("resume_params", {})
    if not isinstance(actual_params, dict):
        return f"ERROR: 審核 #{approval['id']} resume_params 格式錯誤（應為物件）"
    mismatches: list[str] = []
    for field, expected_value in fields_to_match.items():
        if field not in actual_params:
            mismatches.append(f"{field}: approval 缺此欄位")
            continue
        actual_value = actual_params[field]
        if not _values_equivalent(actual_value, expected_value):
            mismatches.append(f"{field}={actual_value!r}≠{expected_value!r}")
    if mismatches:
        return (
            f"ERROR: 審核 #{approval['id']} 參數不符（"
            + "、".join(mismatches)
            + "），請重新建立 approval"
        )
    return None


def _values_equivalent(a, b) -> bool:
    """強相等比對，型別容差：
    - bool：兩邊都是 bool 才比（防 `True == 1` 通過數值門檻、codex round-3 LOW）
    - int vs int：直接 == （任意精度、無 OverflowError 風險）
    - float vs float：non-finite 用 ==、整數對整數轉 int 比、其他 0.001 tolerance
    - int vs float（跨型）：先 finite 守護；float 是整數時拿 int 比、否則 tolerance
      （不無腦 float(a) 轉、防 2^53+1 之類超 float 精度的整數誤判等價、codex round-3 MED）
    - JSON 字串：若雙邊都是 array/object JSON 字面、parse 後 structural 比對
    - 其他：原生 == 比對
    """
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, int) and isinstance(b, int):
        return a == b
    if isinstance(a, float) and isinstance(b, float):
        if not (math.isfinite(a) and math.isfinite(b)):
            return a == b  # inf==inf 成立；nan!=nan 也對
        if a.is_integer() and b.is_integer():
            return int(a) == int(b)
        return abs(a - b) < 0.001
    if isinstance(a, int) and isinstance(b, float):
        if not math.isfinite(b):
            return False
        if b.is_integer():
            return a == int(b)
        try:
            return abs(float(a) - b) < 0.001
        except OverflowError:
            return False
    if isinstance(a, float) and isinstance(b, int):
        if not math.isfinite(a):
            return False
        if a.is_integer():
            return int(a) == b
        try:
            return abs(a - float(b)) < 0.001
        except OverflowError:
            return False
    if isinstance(a, str) and isinstance(b, str):
        if a == b:
            return True
        a_stripped = a.strip()
        b_stripped = b.strip()
        if a_stripped[:1] in ("[", "{") and b_stripped[:1] in ("[", "{"):
            try:
                return json.loads(a) == json.loads(b)
            except (json.JSONDecodeError, ValueError):
                return False
        return False
    return a == b


def _extract_resume_action(detail_str: str) -> str | None:
    """純取 resume_action 字串、不格式化、安全 fallback。

    給 get_context_summary 等短訊息場景用、不需要完整 next_steps。
    detail 不是 dict / 沒 resume_action / resume_action 非字串 / 解析失敗都回 None。"""
    try:
        obj = json.loads(detail_str)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(obj, dict):
        return None
    value = obj.get("resume_action")
    if not isinstance(value, str) or not value:
        return None
    return value


def _format_resume_detail(detail_str: str, approval_id: int | None = None) -> str:
    """解析 approval.detail JSON、格式化成 guidance steps（only 可格式化時才回非空）。

    resume_action 開頭 'manual_' 視為人工多步驟、輸出 `[人工執行 X] note` 而非 callable
    樣式（防 agent 試呼叫不存在的 tool）；其他視為可 call tool name、輸出 `func(args)`。

    approval_id=None（查詢顯示用、不注入 approved_id）；非 None（resolve 後下一步指引、
    注入 approved_id）。

    無從格式化（detail 非 dict、缺 resume_action、resume_params 非 dict）一律回空字串、
    讓 caller 透過 `if formatted:` 跳過、不重複輸出 raw detail。"""
    try:
        detail_obj = json.loads(detail_str)
    except (json.JSONDecodeError, TypeError):
        return ""

    if not isinstance(detail_obj, dict):
        return ""

    resume_action = detail_obj.get("resume_action")
    if not isinstance(resume_action, str) or not resume_action:
        return ""

    raw_params = detail_obj.get("resume_params", {})
    if not isinstance(raw_params, dict):
        return ""

    resume_params = dict(raw_params)
    then_desc = detail_obj.get("then") or ""
    note = detail_obj.get("note") or ""

    steps = []
    if resume_action.startswith("manual_"):
        # 多步驟人工流程、不包成 callable
        descr = note or ", ".join(f"{k}={v!r}" for k, v in resume_params.items())
        steps.append(f"[人工執行 {resume_action}] {descr}")
    else:
        if approval_id is not None:
            resume_params["approved_id"] = approval_id
        params_str = ", ".join(f"{k}={v!r}" for k, v in resume_params.items())
        steps.append(f"{resume_action}({params_str})")

    if then_desc:
        steps.append(then_desc)
    return _build_guidance(next_steps=steps)


def _format_decision(
    approval, approval_id: int, decision: str, decided_by: str
) -> str:
    icon = "[核准]" if decision == "approved" else "[駁回]"
    decision_label = "核准" if decision == "approved" else "駁回"
    msg = f"{icon} 審核 #{approval_id} 已{decision_label}（{decided_by}）"
    msg += f"\n類型：{approval['type']}\n摘要：{approval['summary']}"

    if not approval["detail"]:
        return msg

    if decision == "approved":
        formatted = _format_resume_detail(approval["detail"], approval_id=approval_id)
        if formatted:
            msg += formatted
        else:
            # detail 不是可格式化的 JSON（純文字 / 非 dict / 缺 resume_action）→
            # 印 raw 供 caller 自行判讀、避免靜默吞掉資訊
            msg += f"\n詳情：{approval['detail'][:200]}"
    else:
        msg += f"\n原始請求：{approval['detail'][:200]}"

    return msg
