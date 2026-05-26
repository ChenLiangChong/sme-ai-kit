"""Leave tools — @mcp.tool 薄殼，業務邏輯在 service.py、SQL 在 repository.py。"""
from shared.mcp_instance import mcp

from . import service


@mcp.tool()
def register_leave_type(
    code: str,
    name: str,
    default_quota_days: float = 0,
    requires_approval: bool = True,
    is_paid: bool = True,
    notes: str = "",
) -> str:
    """登記新假別（如 annual/personal/sick/bereavement/marriage/menstrual…）。

    Args:
        code: 假別代號（英文小寫，全域唯一，如 'annual', 'personal', 'sick'）
        name: 中文名稱（如 '特休', '事假', '病假', '喪假', '婚假', '生理假'）
        default_quota_days: 預設年度配額（新進員工初始值；可後續 set_leave_balance 覆寫）
        requires_approval: 是否需要簽核（True=要走 approval flow；False=request_leave 一步完成）
        is_paid: 是否照給薪資（紀錄用、不影響 balance 計算）
        notes: 備註（如「年資對照表詳見 …」）
    """
    return service.register_leave_type(
        code=code,
        name=name,
        default_quota_days=default_quota_days,
        requires_approval=requires_approval,
        is_paid=is_paid,
        notes=notes,
    )


@mcp.tool()
def set_leave_balance(
    employee_id: int,
    leave_type_code: str,
    year: int,
    allocated_days: float,
) -> str:
    """設定／覆寫員工某假別某年度的配額。used_days 保留既有值。

    Args:
        employee_id: 員工 ID
        leave_type_code: 假別代號（須先 register_leave_type）
        year: 年度（如 2026）
        allocated_days: 該年度配額（如特休 14 天）
    """
    return service.set_leave_balance(
        employee_id=employee_id,
        leave_type_code=leave_type_code,
        year=year,
        allocated_days=allocated_days,
    )


@mcp.tool()
def request_leave(
    employee_id: int,
    leave_type_code: str,
    start_date: str,
    end_date: str,
    days: float,
    reason: str = "",
) -> str:
    """員工請假申請。

    流程：
    1. 驗證員工、假別、日期、餘額
    2. 建 leave_requests（status=pending 或 approved）
    3. 若 requires_approval=True：自動 create approval（resume_action='approve_leave'）
    4. 主管 resolve_approval(approval_id=M, decision='approved', decided_by='主管')
       後執行 approve_leave(leave_request_id=N, approved_id=M, decided_by='主管')

    Args:
        employee_id: 員工 ID
        leave_type_code: 假別代號（如 annual / personal / sick）
        start_date: 開始日期（YYYY-MM-DD）
        end_date: 結束日期（YYYY-MM-DD，含當日）
        days: 請假天數（可為小數，如 0.5 半天）
        reason: 請假原因（選填）
    """
    return service.request_leave(
        employee_id=employee_id,
        leave_type_code=leave_type_code,
        start_date=start_date,
        end_date=end_date,
        days=days,
        reason=reason,
    )


@mcp.tool()
def approve_leave(
    leave_request_id: int,
    approved_id: int,
    decided_by: str,
) -> str:
    """核准請假申請（走 HITL gate）。

    必須先 resolve_approval(approval_id=M, decision='approved', decided_by='主管')
    後拿 M 當 approved_id 來這。
    gate_check 會驗 resume_action='approve_leave' + leave_request_id/employee_id/days 一致。
    通過後：扣 leave_balance、leave_request.status='approved'、consume approval。

    Args:
        leave_request_id: 請假申請 ID
        approved_id: 對應的 approval ID（已被 resolve 為 approved 的）
        decided_by: 核准人姓名（記錄到 leave_request.decided_by）
    """
    return service.approve_leave(
        leave_request_id=leave_request_id,
        approved_id=approved_id,
        decided_by=decided_by,
    )


@mcp.tool()
def reject_leave(
    leave_request_id: int,
    rejected_approval_id: int,
    decided_by: str,
    reason: str = "",
) -> str:
    """駁回請假申請。先 resolve_approval(approval_id=M, decision='rejected',
    decided_by='主管') 才能呼叫。

    不動 leave_balances（pending 不算扣餘額）。

    Args:
        leave_request_id: 請假申請 ID
        rejected_approval_id: 對應的已被 rejected 的 approval ID
        decided_by: 駁回人姓名
        reason: 駁回原因（選填）
    """
    return service.reject_leave(
        leave_request_id=leave_request_id,
        rejected_approval_id=rejected_approval_id,
        decided_by=decided_by,
        reason=reason,
    )


@mcp.tool()
def cancel_leave(
    leave_request_id: int,
    reason: str = "",
    actor: str = "",
) -> str:
    """取消請假申請（pending 或 approved 都可）。
    approved 狀態取消會回補 leave_balances 餘額（原子條件式扣回、失敗則 rollback）；
    pending 不需回補（pending 不扣）。

    Args:
        leave_request_id: 請假申請 ID
        reason: 取消原因
        actor: 取消人姓名
    """
    return service.cancel_leave(
        leave_request_id=leave_request_id, reason=reason, actor=actor
    )


@mcp.tool()
def get_leave_request(leave_request_id: int) -> str:
    """查單筆請假申請完整內容（含員工、假別、起訖、狀態、對應審核 ID、決定者）。

    給失敗情境判讀使用：approve_leave / cancel_leave 被擋下時、用此查現況。

    Args:
        leave_request_id: 請假申請 ID
    """
    return service.get_leave_request(leave_request_id=leave_request_id)


@mcp.tool()
def list_leave_requests(
    employee_id: int = 0,
    status: str = "",
    year: int = 0,
    leave_type_code: str = "",
    limit: int = 30,
) -> str:
    """通用查詢請假紀錄（按 員工 / 狀態 / 年度 / 假別 filter）。

    Args:
        employee_id: 篩特定員工 ID（0=全部）
        status: 篩狀態 pending / approved / rejected / cancelled（空=全部）
        year: 篩年度（按 start_date 年；0=全部）
        leave_type_code: 篩假別代號（如 annual / sick；空=全部）
        limit: 最多回幾筆（預設 30、按 created_at DESC）
    """
    return service.list_leave_requests(
        employee_id=employee_id,
        status=status,
        year=year,
        leave_type_code=leave_type_code,
        limit=limit,
    )


@mcp.tool()
def list_pending_leave_requests(business_unit: str = "") -> str:
    """列出所有 pending 請假申請（含員工 / 假別 / 天數 / 起訖 / 對應簽核 ID / 等待天數）。

    給啟動儀表板使用：老闆早上一啟動就看到待簽事項、避免遺漏。

    Args:
        business_unit: 篩選特定事業體 ID（須先 register_business_entity）。空字串=全部。
    """
    return service.list_pending_leave_requests(business_unit=business_unit)


@mcp.tool()
def get_leave_balance(
    employee_id: int,
    year: int = 0,
    leave_type_code: str = "",
) -> str:
    """查詢員工假別餘額（配額/已用/剩餘）。

    Args:
        employee_id: 員工 ID
        year: 指定年度（0=所有年度）
        leave_type_code: 指定假別代號（空白=所有假別）
    """
    return service.get_leave_balance(
        employee_id=employee_id,
        year=year,
        leave_type_code=leave_type_code,
    )
