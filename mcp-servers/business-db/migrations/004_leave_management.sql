-- Phase 3b: 請假管理（leave management）
--
-- 三張表：
-- - leave_types：假別定義（特休/事假/病假/喪假/婚假…）+ 配額 + 是否需簽核
-- - leave_balances：員工 × 假別 × 年度 的配額/已用紀錄
-- - leave_requests：請假申請 + 簽核狀態 + 對應的 approvals.id

CREATE TABLE IF NOT EXISTS leave_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    default_quota_days REAL DEFAULT 0,
    requires_approval INTEGER DEFAULT 1,
    is_paid INTEGER DEFAULT 1,
    notes TEXT,
    created_at DATETIME DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS leave_balances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    leave_type_id INTEGER NOT NULL REFERENCES leave_types(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    allocated_days REAL DEFAULT 0,
    used_days REAL DEFAULT 0,
    updated_at DATETIME DEFAULT (datetime('now', 'localtime')),
    UNIQUE(employee_id, leave_type_id, year)
);

CREATE INDEX IF NOT EXISTS idx_leave_balances_emp_year
    ON leave_balances(employee_id, year);

-- leave_requests：employee_id 用 SET NULL 保留稽核紀錄（codex P3b A2 修法）；
-- balance 跟員工 1:1 強耦合所以 CASCADE，但 requests 是歷史紀錄、員工離職後仍應留
CREATE TABLE IF NOT EXISTS leave_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER REFERENCES employees(id) ON DELETE SET NULL,
    leave_type_id INTEGER NOT NULL REFERENCES leave_types(id),
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    days REAL NOT NULL,
    reason TEXT,
    status TEXT DEFAULT 'pending',
    approval_id INTEGER REFERENCES approvals(id),
    decided_by TEXT,
    decided_at DATETIME,
    created_at DATETIME DEFAULT (datetime('now', 'localtime')),
    CHECK (status IN ('pending', 'approved', 'rejected', 'cancelled')),
    CHECK (days > 0),
    CHECK (start_date <= end_date)
);

CREATE INDEX IF NOT EXISTS idx_leave_requests_employee
    ON leave_requests(employee_id);
CREATE INDEX IF NOT EXISTS idx_leave_requests_status
    ON leave_requests(status);
-- approval_id 1:1（codex P3b A1）：每個 approval 至多被一個 request 引用
CREATE UNIQUE INDEX IF NOT EXISTS idx_leave_requests_approval
    ON leave_requests(approval_id) WHERE approval_id IS NOT NULL;
