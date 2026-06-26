"""Leave management service — 請假業務邏輯。

層次邊界：transaction ownership 在這層，repository 不 commit。
HITL 簽核走 modules.approvals.service 的 gate_check / gate_consume / create_in_tx。

並發安全（codex P3b 修法）：
- request_leave / approve_leave / reject_leave / cancel_leave 都用 mode='immediate' tx
- 扣餘額用 add_used_days 條件式 UPDATE（WHERE allocated - used >= delta）
- request_leave pending 算入 _calc_remaining（防 pending 總量超額）
- 跨年假禁止（必須單一年度）
"""
import json
from datetime import datetime

from shared.db import _now, get_db, transaction
from shared.utils import _build_guidance

from modules.approvals import repository as approvals_repo
from modules.approvals import service as approvals_service

from . import repository


# ============================================================
# 內部 helper
# ============================================================

def _parse_iso_date(s: str) -> datetime | None:
    """嚴格 YYYY-MM-DD parse；錯誤回 None（codex P3b A3）。"""
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def _employee_business_unit(db, employee_id: int | None) -> str | None:
    """從 employees.business_units（逗號分隔）取第一個當主要 BU。

    employee_id=None（員工已離職、ON DELETE SET NULL）/ 找不到員工 / business_units
    為空 → 回 None（caller 不必再加 `or None`、語意一致）。"""
    if employee_id is None:
        return None
    row = db.execute(
        "SELECT business_units FROM employees WHERE id = ?", (employee_id,)
    ).fetchone()
    if not row or not row[0]:
        return None
    return row[0].split(",")[0].strip() or None


def _calc_remaining(db, employee_id: int, leave_type_id: int, year: int) -> float | None:
    """算員工某假別某年度真實剩餘量 = allocated - used - pending_sum。
    回 None 表示沒有 balance row。"""
    balance = repository.get_balance(db, employee_id, leave_type_id, year)
    if not balance:
        return None
    pending_sum = repository.sum_pending_days(db, employee_id, leave_type_id, year)
    return balance["allocated_days"] - balance["used_days"] - pending_sum


# ============================================================
# 假別設定（register_leave_type）
# ============================================================

def register_leave_type(
    code: str,
    name: str,
    default_quota_days: float,
    requires_approval: bool,
    is_paid: bool,
    notes: str,
) -> str:
    if not code or not name:
        return "ERROR: code 跟 name 必填"
    code = code.strip().lower()

    with transaction() as db:
        existing = repository.get_leave_type_by_code(db, code)
        if existing:
            return (
                f"ERROR: 假別 code={code!r} 已存在（#{existing['id']} {existing['name']}）。"
                "若要修改請刪除重建或直接 update（目前未提供 update_leave_type）。"
            )
        type_id = repository.insert_leave_type(
            db,
            code=code,
            name=name,
            default_quota_days=default_quota_days,
            requires_approval=1 if requires_approval else 0,
            is_paid=1 if is_paid else 0,
            notes=notes or None,
        )

    approval_label = "需簽核" if requires_approval else "不需簽核"
    pay_label = "薪資照給" if is_paid else "扣薪"
    return (
        f"假別 #{type_id} 已建立：{name}（code={code}）"
        f"\n預設配額：{default_quota_days} 天 / {approval_label} / {pay_label}"
    )


# ============================================================
# 設定餘額（set_leave_balance）— 年度初始化
# ============================================================

def set_leave_balance(
    employee_id: int,
    leave_type_code: str,
    year: int,
    allocated_days: float,
) -> str:
    if allocated_days < 0:
        return "ERROR: allocated_days 不可為負數"
    if year < 2000 or year > 2100:
        return f"ERROR: year={year!r} 不合理（應在 2000-2100）"

    with transaction() as db:
        employee = db.execute(
            "SELECT id, name FROM employees WHERE id = ?", (employee_id,)
        ).fetchone()
        if not employee:
            return f"ERROR: 找不到員工 #{employee_id}"

        leave_type = repository.get_leave_type_by_code(db, leave_type_code.strip().lower())
        if not leave_type:
            return f"ERROR: 找不到假別 code={leave_type_code!r}"

        repository.upsert_balance(
            db,
            employee_id=employee_id,
            leave_type_id=leave_type["id"],
            year=year,
            allocated_days=allocated_days,
            now=_now(),
        )

    return (
        f"員工 #{employee_id} {employee['name']} 的 {leave_type['name']}"
        f"（{year}年）配額已設為 {allocated_days} 天"
    )


# ============================================================
# 請假申請（request_leave）— IMMEDIATE tx + pending-aware remaining
# ============================================================

def request_leave(
    employee_id: int,
    leave_type_code: str,
    start_date: str,
    end_date: str,
    days: float,
    reason: str,
) -> str:
    # 基本驗證
    if days <= 0:
        return "ERROR: days 必須 > 0"
    if not start_date or not end_date:
        return "ERROR: start_date 跟 end_date 必填（YYYY-MM-DD）"
    start_dt = _parse_iso_date(start_date)
    end_dt = _parse_iso_date(end_date)
    if not start_dt or not end_dt:
        return f"ERROR: 日期格式必須是 YYYY-MM-DD（got start={start_date!r}, end={end_date!r}）"
    if start_dt > end_dt:
        return f"ERROR: start_date ({start_date}) 不能晚於 end_date ({end_date})"
    if start_dt.year != end_dt.year:
        return (
            f"ERROR: 暫不支援跨年度請假（start={start_date} year={start_dt.year}、"
            f"end={end_date} year={end_dt.year}）。請分兩次申請。"
        )
    year = start_dt.year

    # 寫入用 IMMEDIATE tx（防並發 pending overdraw、codex P3b C1）
    with transaction(mode="immediate") as db:
        employee = db.execute(
            "SELECT id, name FROM employees WHERE id = ?", (employee_id,)
        ).fetchone()
        if not employee:
            return f"ERROR: 找不到員工 #{employee_id}"

        leave_type = repository.get_leave_type_by_code(db, leave_type_code.strip().lower())
        if not leave_type:
            return f"ERROR: 找不到假別 code={leave_type_code!r}"

        remaining = _calc_remaining(db, employee_id, leave_type["id"], year)
        if remaining is None:
            return (
                f"ERROR: 員工 #{employee_id} 的 {leave_type['name']}"
                f"（{year}年）尚未設定配額。請先 set_leave_balance"
                f"(employee_id={employee_id}, leave_type_code={leave_type_code!r}, "
                f"year={year}, allocated_days=N)"
            )
        if remaining < days:
            return (
                f"ERROR: {employee['name']} 的 {leave_type['name']}"
                f"（{year}年）剩 {remaining:g} 天（含 pending 申請）、"
                f"申請 {days:g} 天超出可用餘額"
            )

        requires_approval = bool(leave_type["requires_approval"])
        emp_bu = _employee_business_unit(db, employee_id)

        leave_request_id = repository.insert_leave_request(
            db,
            employee_id=employee_id,
            leave_type_id=leave_type["id"],
            start_date=start_date,
            end_date=end_date,
            days=days,
            reason=reason or None,
            status="pending" if requires_approval else "approved",
            approval_id=None,
        )

        if requires_approval:
            detail_obj = {
                "resume_action": "approve_leave",
                "resume_params": {
                    "leave_request_id": leave_request_id,
                    "employee_id": employee_id,
                    "leave_type_id": leave_type["id"],
                    "start_date": start_date,
                    "end_date": end_date,
                    "days": days,
                },
                "then": "請假核准後通知 HR 跟員工",
            }
            approval_id = approvals_service.create_in_tx(
                db,
                type_="leave_request",
                summary=(
                    f"{employee['name']} 請 {leave_type['name']} {days:g} 天"
                    f"（{start_date}~{end_date}）"
                    + (f"｜原因：{reason}" if reason else "")
                ),
                detail=json.dumps(detail_obj, ensure_ascii=False),
                requester=employee["name"],
                approver="",
                business_unit=emp_bu or "",
            )
            repository.set_request_approval_id(db, leave_request_id, approval_id)
        else:
            # 不需簽核：直接扣 balance（codex P3b C4 — 原子條件 UPDATE 防超扣）
            rowcount = repository.add_used_days(
                db,
                employee_id=employee_id,
                leave_type_id=leave_type["id"],
                year=year,
                delta_days=days,
                now=_now(),
            )
            if rowcount != 1:
                # rollback to safe state
                raise RuntimeError(
                    f"請假扣餘額失敗（balance 不夠或 row 不存在，rowcount={rowcount}）"
                )
            approval_id = 0

        repository.insert_interaction_log(
            db,
            actor=employee["name"],
            action="leave_requested",
            target_id=leave_request_id,
            detail=(
                f"{leave_type['name']} {days:g} 天（{start_date}~{end_date}）"
                + (f" 原因：{reason}" if reason else "")
            ),
            business_unit=emp_bu,
        )

    if requires_approval:
        return (
            f"請假申請 #{leave_request_id} 已建立（pending）\n"
            f"{employee['name']} 請 {leave_type['name']} {days:g} 天"
            f"（{start_date}~{end_date}）"
            f"\n對應簽核 #{approval_id}"
            + _build_guidance(next_steps=[
                f"請主管／老闆 LINE 回覆「核准 #{approval_id}」或執行 "
                f"resolve_approval(approval_id={approval_id}, decision='approved', "
                f"decided_by='主管')",
                f"核准後執行 approve_leave(leave_request_id={leave_request_id}, "
                f"approved_id={approval_id}, decided_by='主管')",
            ])
        )
    return (
        f"請假申請 #{leave_request_id} 已核准（{leave_type['name']}不需簽核）\n"
        f"{employee['name']} 請 {days:g} 天（{start_date}~{end_date}）、餘額已扣"
    )


# ============================================================
# 核准請假（approve_leave）— HITL gate (require_approval) + 原子扣餘額
# ============================================================

def approve_leave(
    leave_request_id: int,
    approved_id: int,
    decided_by: str,
) -> str:
    if not decided_by:
        return "ERROR: decided_by 必填（誰核准）"

    with transaction(mode="immediate") as db:
        leave_req = repository.get_leave_request(db, leave_request_id)
        if not leave_req:
            return f"ERROR: 找不到請假申請 #{leave_request_id}"
        if leave_req["status"] != "pending":
            return (
                f"ERROR: 請假申請 #{leave_request_id} 狀態是 {leave_req['status']!r}、"
                "無法核准（必須是 pending）"
            )

        gate = approvals_service.gate_check(
            db,
            approved_id=approved_id,
            expected_action="approve_leave",
            verify_fields={
                "leave_request_id": leave_request_id,
                "employee_id": leave_req["employee_id"],
                "leave_type_id": leave_req["leave_type_id"],
                "start_date": leave_req["start_date"],
                "end_date": leave_req["end_date"],
                "days": leave_req["days"],
            },
            require_approval=True,
        )
        if gate.error:
            return gate.error

        # 原子條件式扣 balance（codex P3b C3）
        year = int(leave_req["start_date"][:4])
        rowcount = repository.add_used_days(
            db,
            employee_id=leave_req["employee_id"],
            leave_type_id=leave_req["leave_type_id"],
            year=year,
            delta_days=leave_req["days"],
            now=_now(),
        )
        if rowcount != 1:
            return (
                f"ERROR: 員工 #{leave_req['employee_id']} 的 {leave_req['type_name']}"
                f"（{year}年）餘額不足或無 balance row、無法扣減。請查 get_leave_balance"
            )

        repository.update_request_status(
            db,
            leave_request_id=leave_request_id,
            status="approved",
            decided_by=decided_by,
            decided_at=_now(),
        )

        approvals_service.gate_consume(
            db,
            approval_id=gate.approval_id,
            consumed_by_type="leave_request",
            consumed_by_id=leave_request_id,
        )

        emp_label = _format_employee_label(leave_req)
        emp_bu = _employee_business_unit(db, leave_req["employee_id"])
        repository.insert_interaction_log(
            db,
            actor=decided_by,
            action="leave_approved",
            target_id=leave_request_id,
            detail=(
                f"{emp_label} {leave_req['type_name']} "
                f"{leave_req['days']:g} 天（{leave_req['start_date']}~"
                f"{leave_req['end_date']}）已核准"
            ),
            business_unit=emp_bu,
        )
        # 在 with 內完成 message 字串、出 with 直接 return（避免 caller scope 依賴
        # with 內 variable、防 future re-fetch 造成 stale）
        result_msg = (
            f"請假申請 #{leave_request_id} 已核准（{decided_by}）"
            f"\n{emp_label} {leave_req['type_name']} "
            f"{leave_req['days']:g} 天（{leave_req['start_date']}~{leave_req['end_date']}）"
            f"\n餘額已扣"
            + _build_guidance(next_steps=[
                f"LINE 通知 {emp_label}：請假申請已核准",
            ])
        )

    return result_msg


# ============================================================
# 駁回請假（reject_leave）— 主管 resolve_approval rejected 後呼叫
# ============================================================

def reject_leave(
    leave_request_id: int,
    rejected_approval_id: int,
    decided_by: str,
    reason: str,
) -> str:
    if not decided_by:
        return "ERROR: decided_by 必填"

    with transaction(mode="immediate") as db:
        leave_req = repository.get_leave_request(db, leave_request_id)
        if not leave_req:
            return f"ERROR: 找不到請假申請 #{leave_request_id}"
        if leave_req["status"] != "pending":
            return (
                f"ERROR: 請假申請 #{leave_request_id} 狀態是 {leave_req['status']!r}、"
                "無法駁回（必須是 pending）"
            )
        if leave_req["approval_id"] != rejected_approval_id:
            return (
                f"ERROR: rejected_approval_id #{rejected_approval_id} 跟 "
                f"leave_request #{leave_request_id} 對應的 approval_id "
                f"#{leave_req['approval_id']} 不符"
            )

        approval = approvals_repo.get(db, rejected_approval_id)
        if not approval:
            return f"ERROR: 找不到審核 #{rejected_approval_id}"
        if approval["status"] != "rejected":
            return (
                f"ERROR: 審核 #{rejected_approval_id} 狀態是 {approval['status']!r}、"
                "必須是 rejected 才能 reject_leave。請先 "
                f"resolve_approval(approval_id={rejected_approval_id}, "
                "decision='rejected', decided_by='主管')"
            )

        repository.update_request_status(
            db,
            leave_request_id=leave_request_id,
            status="rejected",
            decided_by=decided_by,
            decided_at=_now(),
        )

        emp_label = _format_employee_label(leave_req)
        emp_bu = _employee_business_unit(db, leave_req["employee_id"])
        repository.insert_interaction_log(
            db,
            actor=decided_by,
            action="leave_rejected",
            target_id=leave_request_id,
            detail=(
                f"{emp_label} {leave_req['type_name']} "
                f"{leave_req['days']:g} 天已駁回"
                + (f"｜原因：{reason}" if reason else "")
            ),
            business_unit=emp_bu,
        )
        result_msg = (
            f"請假申請 #{leave_request_id} 已駁回（{decided_by}）"
            f"\n{emp_label} {leave_req['type_name']} "
            f"{leave_req['days']:g} 天"
            + (f"\n駁回原因：{reason}" if reason else "")
        )

    return result_msg


# ============================================================
# 取消請假（cancel_leave）— pending 直接取消、approved 回補餘額
# ============================================================

def cancel_leave(leave_request_id: int, reason: str, actor: str) -> str:
    if not actor:
        return "ERROR: actor 必填（誰取消）"

    with transaction(mode="immediate") as db:
        leave_req = repository.get_leave_request(db, leave_request_id)
        if not leave_req:
            return f"ERROR: 找不到請假申請 #{leave_request_id}"
        if leave_req["status"] not in ("pending", "approved"):
            return (
                f"ERROR: 請假申請 #{leave_request_id} 狀態是 {leave_req['status']!r}、"
                "無法取消（必須是 pending 或 approved）"
            )

        restore_msg = ""
        if leave_req["status"] == "approved":
            year = int(leave_req["start_date"][:4])
            rowcount = repository.restore_used_days(
                db,
                employee_id=leave_req["employee_id"],
                leave_type_id=leave_req["leave_type_id"],
                year=year,
                delta_days=leave_req["days"],
                now=_now(),
            )
            if rowcount != 1:
                # row 不存在或 used_days < delta（資料異常）— 不靜默截斷、明確報錯
                return (
                    f"ERROR: 員工 #{leave_req['employee_id']} 的 {leave_req['type_name']}"
                    f"（{year}年）balance 無法回補 {leave_req['days']:g} 天"
                    f"（row 不存在或 used_days 不足）。請先確認 balance 狀態。"
                )
            restore_msg = f"（已回補 {leave_req['days']:g} 天）"

        repository.update_request_status(
            db,
            leave_request_id=leave_request_id,
            status="cancelled",
            decided_by=actor,
            decided_at=_now(),
        )

        emp_label = _format_employee_label(leave_req)
        # _employee_business_unit 內已處理 employee_id=None 情境（回 None）、不需 caller 再守
        emp_bu = _employee_business_unit(db, leave_req["employee_id"])
        repository.insert_interaction_log(
            db,
            actor=actor,
            action="leave_cancelled",
            target_id=leave_request_id,
            detail=(
                f"{emp_label} {leave_req['type_name']} "
                f"{leave_req['days']:g} 天已取消"
                + (f"｜原因：{reason}" if reason else "")
            ),
            business_unit=emp_bu,
        )
        result_msg = (
            f"請假申請 #{leave_request_id} 已取消（{actor}）"
            f"\n{emp_label} {leave_req['type_name']} "
            f"{leave_req['days']:g} 天 {restore_msg}"
            + (f"\n取消原因：{reason}" if reason else "")
        )

    return result_msg


# ============================================================
# 查餘額（get_leave_balance）
# ============================================================

def _format_employee_label(row) -> str:
    """共用：員工 row 顯示處理 NULL employee_id / name。

    三分支：(1) employee_name 存在 → 用姓名；(2) employee_id 存在但 name 是 NULL
    （資料異常防禦碼、employees.name 是 NOT NULL、理論不可達、但留以防 schema 異動 /
    手動修改）；(3) employee_id IS NULL（ON DELETE SET NULL 路徑）→ 員工已離職。"""
    if row["employee_name"]:
        return row["employee_name"]
    if row["employee_id"] is not None:
        return f"員工 #{row['employee_id']}（已離職）"
    return "員工已離職"


def get_leave_request(leave_request_id: int) -> str:
    """查單筆請假申請（含員工、假別、簽核 id、狀態、決定者等）。

    給失敗情境判讀使用：approve_leave / cancel_leave 被擋時、agent 用此 tool 看
    這筆 leave_request 現況，不要繞 sqlite。"""
    from shared.floor_policy import is_full_access
    db = get_db()
    try:
        lr = repository.get_leave_request(db, leave_request_id)
        if not lr:
            return f"ERROR: 找不到請假申請 #{leave_request_id}"

        lines = [f"## 請假 #{leave_request_id}"]
        lines.append(f"- 員工：{_format_employee_label(lr)}")
        lines.append(f"- 假別：{lr['type_name']}（{lr['type_code']}）")
        lines.append(f"- 期間：{lr['start_date']} ~ {lr['end_date']}（{lr['days']:g} 天）")
        lines.append(f"- 狀態：{lr['status']}")
        # 原因屬個人隱私 → 只給全權限層（#171 審）；受限層看得到誰/何時/狀態即可
        if lr["reason"] and is_full_access():
            lines.append(f"- 原因：{lr['reason']}")
        if lr["approval_id"]:
            lines.append(f"- 對應審核：#{lr['approval_id']}")
        if lr["decided_by"]:
            lines.append(
                f"- 決定者：{lr['decided_by']}（{lr['decided_at']}）"
            )
        lines.append(f"- 建立：{lr['created_at']}")
        return "\n".join(lines)
    finally:
        db.close()


def list_leave_requests(
    employee_id: int = 0,
    status: str = "",
    year: int = 0,
    leave_type_code: str = "",
    limit: int = 30,
) -> str:
    """通用查詢請假紀錄（依員工 / 狀態 / 年度 / 假別 filter）。

    注意：實際 MCP transport 下 fastmcp 用 Pydantic 強制 type 驗證
    （True→1 / 1.5→validation error / "abc"→validation error / None→validation error；
    Pydantic 2.x 對 int field 預設 strict mode、float 不會 silently 截斷），
    這些非 int 情境 transport 層先擋下、不會打到 service。
    這層 isinstance guard 主要防：(a) 內部模組直呼測試 (b) fastmcp 規則變動。
    """
    # 邊界驗證 — limit 必須是非布林整數、且在 [1, 100]
    if not isinstance(limit, int) or isinstance(limit, bool):
        return f"ERROR: limit 必須是整數（got {type(limit).__name__}: {limit!r}）"
    if limit < 1 or limit > 100:
        return f"ERROR: limit 必須在 1-100（got {limit}）"
    if status and status not in ("pending", "approved", "rejected", "cancelled"):
        return (
            f"ERROR: status 必須是 pending / approved / rejected / cancelled"
            f"（got {status!r}）"
        )

    from shared.floor_policy import is_full_access
    db = get_db()
    try:
        rows = repository.list_requests(
            db,
            employee_id=employee_id,
            status=status,
            year=year,
            leave_type_code=leave_type_code,
            limit=limit,
        )
        if not rows:
            return "查無符合條件的請假紀錄"

        # 標題顯示套用了哪些 filter
        title_parts = []
        if employee_id:
            title_parts.append(f"員工 #{employee_id}")
        if status:
            title_parts.append(f"狀態={status}")
        if year:
            title_parts.append(f"{year} 年")
        if leave_type_code:
            title_parts.append(leave_type_code)
        title_label = (
            "（" + " / ".join(title_parts) + "）" if title_parts else ""
        )

        # 原因屬個人隱私 → 只給全權限層（#171 審）；受限層保留誰/何時/狀態供排班協調
        fa = is_full_access()
        lines = [f"## 請假紀錄{title_label}（最新 {len(rows)} 筆）"]
        for r in rows:
            approval_label = (
                f"｜審核 #{r['approval_id']}" if r["approval_id"] else ""
            )
            reason_label = f"｜原因：{r['reason']}" if (r["reason"] and fa) else ""
            lines.append(
                f"- 請假 #{r['id']} {_format_employee_label(r)} "
                f"{r['type_name']} {r['days']:g} 天"
                f"（{r['start_date']}~{r['end_date']}）"
                f"｜{r['status']}{approval_label}{reason_label}"
            )
        return "\n".join(lines)
    finally:
        db.close()


def list_pending_leave_requests(business_unit: str = "") -> str:
    """列出 pending 請假申請（給啟動儀表板用）。"""
    db = get_db()
    try:
        rows = repository.list_pending_requests(db, business_unit=business_unit)
        if not rows:
            bu_label = f"（事業體：{business_unit}）" if business_unit else ""
            return f"目前無待簽請假申請{bu_label}"

        title_bu = f"（事業體：{business_unit}）" if business_unit else ""
        lines = [f"## 待簽請假申請{title_bu}"]
        now = datetime.now()
        for r in rows:
            emp_label = _format_employee_label(r)

            wait_label = ""
            try:
                created = datetime.strptime(r["created_at"], "%Y-%m-%d %H:%M:%S")
                wait_days = (now - created).days
                if wait_days >= 3:
                    wait_label = f"｜已等 {wait_days} 天"
            except (ValueError, TypeError, KeyError):
                pass

            approval_label = (
                f"｜審核 #{r['approval_id']}" if r["approval_id"] else "（無對應審核）"
            )
            reason_label = f"｜原因：{r['reason']}" if r["reason"] else ""
            # 明確標「請假 #N」跟「審核 #M」，避免 agent 拿錯 id 呼叫 resolve_approval
            lines.append(
                f"- 請假 #{r['id']} {emp_label} {r['type_name']} {r['days']:g} 天"
                f"（{r['start_date']}~{r['end_date']}）"
                f"{approval_label}{wait_label}{reason_label}"
            )

        lines.append(
            f"\n共 {len(rows)} 件待處理。簽核流程（N=請假 ID、M=審核 ID）："
            "\n1. resolve_approval(approval_id=M, decision='approved' / 'rejected', "
            "decided_by='主管')"
            "\n2. approve_leave(leave_request_id=N, approved_id=M, decided_by='主管')"
            "\n   或 reject_leave(leave_request_id=N, rejected_approval_id=M, "
            "decided_by='主管', reason='...')"
        )
        return "\n".join(lines)
    finally:
        db.close()


def get_leave_balance(
    employee_id: int,
    year: int,
    leave_type_code: str,
) -> str:
    db = get_db()
    try:
        employee = db.execute(
            "SELECT id, name FROM employees WHERE id = ?", (employee_id,)
        ).fetchone()
        if not employee:
            return f"ERROR: 找不到員工 #{employee_id}"

        if leave_type_code:
            leave_type = repository.get_leave_type_by_code(
                db, leave_type_code.strip().lower()
            )
            if not leave_type:
                return f"ERROR: 找不到假別 code={leave_type_code!r}"
            # 指定假別 + 指定年 → 用 get_balance 單筆查；指定假別 + 不限年 → fetch all 再 filter
            if year:
                row = repository.get_balance(
                    db, employee_id, leave_type["id"], year
                )
                # 需要 type_code / type_name 才能跟 list_balances_by_employee 同型
                if row:
                    row = dict(row)
                    row["type_code"] = leave_type["code"]
                    row["type_name"] = leave_type["name"]
                    balances = [row]
                else:
                    balances = []
            else:
                balances = [b for b in repository.list_balances_by_employee(
                    db, employee_id, year=year
                ) if b["leave_type_id"] == leave_type["id"]]
        else:
            balances = repository.list_balances_by_employee(
                db, employee_id, year=year
            )

        if not balances:
            year_label = f"{year}年" if year else "所有年度"
            type_label = f" {leave_type_code}" if leave_type_code else ""
            return (
                f"員工 #{employee_id} {employee['name']} "
                f"在 {year_label}{type_label} 無 balance 紀錄"
            )

        lines = [f"## {employee['name']} 假別餘額"]
        for b in balances:
            allocated = b["allocated_days"]
            used = b["used_days"]
            pending = repository.sum_pending_days(
                db, employee_id, b["leave_type_id"], b["year"]
            )
            available = allocated - used - pending
            pending_label = f" / pending {pending:g}" if pending > 0 else ""
            lines.append(
                f"- [{b['year']}] {b['type_name']}：配額 {allocated:g} / "
                f"已用 {used:g}{pending_label} / 可用 {available:g} 天"
            )
        return "\n".join(lines)
    finally:
        db.close()
