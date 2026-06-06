#!/usr/bin/env bash
# 一鍵跑全部 standalone test runner（codex 全專案審 MED：audit 測試要有自動回歸入口、
# 不能只靠手動逐檔跑）。任一檔非零退出 → 整體失敗（CI / pre-push 可直接用）。
#
#   bash tests/run_all.sh
#
# 注意：這些是 standalone runner（自帶 __main__ + sys.exit），不是 pytest-discoverable，
# 故逐檔 `python <file>` 跑、不走 pytest（見 conftest.py collect_ignore 說明）。
set -uo pipefail
cd "$(dirname "$0")/.." || exit 2

FILES=(
  tests/test_smoke_all.py
  tests/test_deadline_engine.py
  tests/test_migration_safety.py
  tests/test_health_intake.py
  tests/test_office_calendar_import.py
  tests/test_audit_accounting.py
  tests/test_audit_approvals.py
  tests/test_audit_auth.py
  tests/test_audit_crm_inv_tasks.py
  tests/test_audit_escalation.py
  tests/test_audit_knowledge.py
  tests/test_audit_leave.py
  tests/test_audit_notifications.py
  tests/test_audit_orders.py
  tests/test_audit_settings_attach_snap.py
)

fail=0
for f in "${FILES[@]}"; do
  if [[ ! -f "$f" ]]; then
    echo "SKIP（不存在）: $f"; continue
  fi
  if python "$f" >/tmp/_runall_$$.log 2>&1; then
    echo "PASS: $f"
  else
    echo "FAIL: $f"
    tail -8 /tmp/_runall_$$.log
    fail=1
  fi
done
rm -f /tmp/_runall_$$.log
if [[ $fail -ne 0 ]]; then
  echo "=== 有測試失敗 ==="; exit 1
fi
echo "=== 全部測試通過 ==="
