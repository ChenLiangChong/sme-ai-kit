"""pytest 排除設定。

`test_smoke_all.py` 跟 `test_migration_safety.py` 是 standalone Python runner
（自帶 `__main__` 結尾 sys.exit、整個 test body 在 module level 跑），
不是 pytest-style discoverable test。直接執行：

    python tests/test_smoke_all.py
    python tests/test_migration_safety.py

pytest 嘗試 import 收集時會在 module body 跑到 `sys.exit(0)` 直接 abort 整個
collection（pytest INTERNALERROR）。此 conftest 排除這兩檔避免污染 `pytest tests/`。
"""
collect_ignore = [
    "test_smoke_all.py",
    "test_migration_safety.py",
    "test_deadline_engine.py",
    "test_pleading_integration.py",
    "test_office_calendar_import.py",
    "test_health_intake.py",
    "test_audit_accounting.py",
    "test_audit_approvals.py",
    "test_audit_auth.py",
    "test_audit_crm_inv_tasks.py",
    "test_audit_escalation.py",
    "test_audit_knowledge.py",
    "test_audit_leave.py",
    "test_audit_notifications.py",
    "test_audit_orders.py",
    "test_audit_settings_attach_snap.py",
]
