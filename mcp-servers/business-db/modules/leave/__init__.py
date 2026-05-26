"""Leave management module（P3b）— 請假管理。

3 表 7 工具：
- leave_types：假別定義（特休/事假/病假/喪假/婚假…）
- leave_balances：員工×假別×年度 餘額（allocated/used）
- leave_requests：請假申請 + 簽核狀態 + approvals.id 連動

簽核流程：
1. request_leave → 建 pending leave_request + 走 approvals.create_in_tx
2. 主管 resolve_approval(approval_id=M, decision='approved', decided_by='主管')
3. AI/系統 approve_leave(leave_request_id=N, approved_id=M, decided_by='主管') →
   gate_check 驗證 → 扣 balance → mark approved → gate_consume

不需簽核的假別（requires_approval=0）：request_leave 一步完成、不建 approval。
"""
from . import tools  # noqa: F401
