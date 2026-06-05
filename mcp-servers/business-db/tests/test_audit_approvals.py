"""approvals 模組安全稽核回歸測試（offline、standalone、不連網）。

跑法：
    cd mcp-servers/business-db
    SME_DB_PATH=/tmp/_t_aa.db /abs/.venv/bin/python3 tests/test_audit_approvals.py

涵蓋（codex 全專案安全稽核 — approvals）：
- [HIGH] gate_check 過期保護：已核准但逾 expires_at 的 approval 不可被消費（同 tx 標 expired、回中文錯誤）；
  expires_at=NULL 視為永不過期、仍可消費
- [HIGH] resolve CAS 防雙簽：第一次核准成功、第二次（仍以為 waiting）回「審核已被處理」、不覆寫前者
- [HIGH] floored 簽核身份用 verified、忽略 caller 傳入的 decided_by（防 manager 冒充老闆）；
  floored 無 verified LINE 脈絡 → fail-closed 擋下
- create_in_tx 接受 actor_user_id 參數（向後相容、預設 ""）
"""
import atexit
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
DB_PATH = _tmp.name
_tmp.close()
os.environ["SME_DB_PATH"] = DB_PATH
os.environ.pop("SME_FLOOR", None)  # 預設全權限（is_full_access）


@atexit.register
def _cleanup():
    try:
        os.unlink(DB_PATH)
    except OSError:
        pass


import server  # noqa: E402

server.DB_PATH = DB_PATH
server.init_db()

from shared.db import get_db, transaction  # noqa: E402
from modules.approvals import repository, service  # noqa: E402

passed = 0
failed = 0
failures: list[str] = []


def _assert(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"OK    {name}")
    else:
        failed += 1
        failures.append(name)
        print(f"FAIL  {name}" + (f"  // {detail}" if detail else ""))


def _exec(sql, params=()):
    with transaction() as db:
        db.execute(sql, params)


def _q1(sql, params=()):
    db = get_db()
    try:
        return db.execute(sql, params).fetchone()
    finally:
        db.close()


# line-channel verified active-request 隔離目錄（模擬受限層 verified 員工）
_AR_DIR = tempfile.mkdtemp(prefix="approvals_ar_")


def _with_floor(floor, fn, user_id=None):
    """暫設 SME_FLOOR + 寫 verified active-request（None=不寫＝模擬無 verified 脈絡）、跑 fn、還原。"""
    import json as _j
    import time as _t
    old = os.environ.get("SME_FLOOR")
    old_lsd = os.environ.get("LINE_STATE_DIR")
    os.environ["SME_FLOOR"] = floor
    os.environ["LINE_STATE_DIR"] = _AR_DIR
    _arp = os.path.join(_AR_DIR, f"active-request-{floor}.json")
    if user_id is not None:
        with open(_arp, "w", encoding="utf-8") as _f:
            _j.dump({"user_id": user_id, "written_ms": _t.time() * 1000}, _f)
    try:
        return fn()
    finally:
        if old is None:
            os.environ.pop("SME_FLOOR", None)
        else:
            os.environ["SME_FLOOR"] = old
        if old_lsd is None:
            os.environ.pop("LINE_STATE_DIR", None)
        else:
            os.environ["LINE_STATE_DIR"] = old_lsd
        try:
            os.remove(_arp)
        except OSError:
            pass


def _make_approval(*, status="approved", expires_at="__future__", detail=None,
                   consumed=False, business_unit=None):
    """直接插一筆 approval 到指定狀態，回 id。expires_at='__future__' = 明天、
    '__past__' = 昨天、None = NULL（永不過期）、其他字串原樣。"""
    if expires_at == "__future__":
        expires_at = (datetime.now() + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    elif expires_at == "__past__":
        expires_at = (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    with transaction() as db:
        aid = repository.insert_approval(
            db, type_="purchase", summary="測試審核", detail=detail,
            requester="申請人", approver=None, business_unit=business_unit,
            expires_at=expires_at,
        )
        # insert_approval 固定寫 waiting；要 approved/其他狀態時改之
        if status != "waiting":
            db.execute("UPDATE approvals SET status=? WHERE id=?", (status, aid))
        if consumed:
            db.execute(
                "UPDATE approvals SET consumed_at=?, consumed_by_type='transaction', "
                "consumed_by_id=1 WHERE id=?", (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), aid))
    return aid


_DETAIL = '{"resume_action": "record_transaction", "resume_params": {"amount": 10000}}'


# ============================================================
# [HIGH] gate_check 過期保護
# ============================================================

# T1：已核准但過期 → gate_check 回 error、且同 tx 標成 expired
_a1 = _make_approval(status="approved", expires_at="__past__", detail=_DETAIL)
with transaction(mode="immediate") as _db:
    _g1 = service.gate_check(
        _db, approved_id=_a1, amount=10000, threshold=5000,
        expected_action="record_transaction", verify_fields={"amount": 10000},
    )
_assert("T1: 過期 approval gate_check 回 error", _g1.error is not None and "過期" in _g1.error, detail=str(_g1.error))
_assert("T1: 過期 approval 不放行（approval_id 為 None）", _g1.approval_id is None)
_row1 = _q1("SELECT status FROM approvals WHERE id=?", (_a1,))
_assert("T1: 過期 approval 同 tx 被標 expired", _row1["status"] == "expired", detail=_row1["status"])

# T2：未過期（future）→ gate_check 放行
_a2 = _make_approval(status="approved", expires_at="__future__", detail=_DETAIL)
with transaction(mode="immediate") as _db:
    _g2 = service.gate_check(
        _db, approved_id=_a2, amount=10000, threshold=5000,
        expected_action="record_transaction", verify_fields={"amount": 10000},
    )
_assert("T2: 未過期 approval gate_check 放行", _g2.error is None and _g2.approval_id == _a2, detail=str(_g2.error))

# T3：expires_at=NULL（永不過期）→ 仍放行（NULL 不視為過期）
_a3 = _make_approval(status="approved", expires_at=None, detail=_DETAIL)
with transaction(mode="immediate") as _db:
    _g3 = service.gate_check(
        _db, approved_id=_a3, amount=10000, threshold=5000,
        expected_action="record_transaction", verify_fields={"amount": 10000},
    )
_assert("T3: expires_at=NULL 視為永不過期、放行", _g3.error is None and _g3.approval_id == _a3, detail=str(_g3.error))
_row3 = _q1("SELECT status FROM approvals WHERE id=?", (_a3,))
_assert("T3: NULL expires 不被誤標 expired", _row3["status"] == "approved", detail=_row3["status"])

# T4：過期判定不破壞既有 consumed_at 單次語義（已消費的本就抓不到、回 not-found error）
_a4 = _make_approval(status="approved", expires_at="__future__", detail=_DETAIL, consumed=True)
with transaction(mode="immediate") as _db:
    _g4 = service.gate_check(
        _db, approved_id=_a4, amount=10000, threshold=5000,
        expected_action="record_transaction", verify_fields={"amount": 10000},
    )
_assert("T4: 已消費 approval 仍擋下（未核准或已使用）", _g4.error is not None and _g4.approval_id is None, detail=str(_g4.error))


# ============================================================
# [HIGH] resolve CAS 防雙簽
# ============================================================

# T5：第一次核准成功、第二次 fail-closed 不重複落定（序列下狀態已非 waiting）
_a5 = _make_approval(status="waiting", expires_at="__future__", detail=_DETAIL)
_r5a = service.resolve(_a5, "approved", "老闆")
_r5b = service.resolve(_a5, "rejected", "另一人")
_assert("T5: 第一次核准成功", _r5a.startswith("[核准]"), detail=_r5a[:80])
_assert("T5: 第二次 fail-closed（ERROR、不重決）", _r5b.startswith("ERROR"), detail=_r5b[:80])
_row5 = _q1("SELECT status, approver FROM approvals WHERE id=?", (_a5,))
_assert("T5: 狀態維持第一次的 approved（後者未覆寫）", _row5["status"] == "approved", detail=_row5["status"])
_assert("T5: approver 維持第一決定者（未被後者覆寫）", _row5["approver"] == "老闆", detail=_row5["approver"])
# interaction_log 只應有第一次那筆 approval_* 稽核
_log5 = _q1("SELECT COUNT(*) c FROM interaction_log WHERE target_type='approval' AND target_id=?", (_a5,))
_assert("T5: 稽核 log 只一筆（後者不留痕）", _log5["c"] == 1, detail=str(_log5["c"]))

# T5b：CAS race 收口——模擬「兩簽核人同讀到 waiting」。直接造一個 status='waiting' 但
# decided_at 已被另一路寫入的 row（get_waiting 仍撈得到），service 應在 mark_decided CAS
# rowcount=0 時回『審核已被處理』、不二次落定（這是 deferred→immediate + CAS 真正擋的 case）。
_a5b = _make_approval(status="waiting", expires_at="__future__", detail=_DETAIL)
_exec("UPDATE approvals SET decided_at=? WHERE id=?", ("2026-06-05 09:00:00", _a5b))
_r5c = service.resolve(_a5b, "approved", "後到的人")
_assert("T5b: CAS rowcount=0 → 回『已被處理』", "已被處理" in _r5c, detail=_r5c[:80])
_log5b = _q1("SELECT COUNT(*) c FROM interaction_log WHERE target_type='approval' AND target_id=?", (_a5b,))
_assert("T5b: 被 CAS 擋下者不留稽核痕", _log5b["c"] == 0, detail=str(_log5b["c"]))

# T6：repository.mark_decided CAS 直接驗 rowcount（第二次 rowcount=0）
_a6 = _make_approval(status="waiting", expires_at="__future__", detail=_DETAIL)
with transaction(mode="immediate") as _db:
    _rc6a = repository.mark_decided(_db, _a6, "approved", "甲", "2026-06-05 10:00:00")
with transaction(mode="immediate") as _db:
    _rc6b = repository.mark_decided(_db, _a6, "rejected", "乙", "2026-06-05 10:01:00")
_assert("T6: 首次 mark_decided rowcount=1", _rc6a == 1, detail=str(_rc6a))
_assert("T6: 二次 mark_decided rowcount=0（CAS 擋下）", _rc6b == 0, detail=str(_rc6b))


# ============================================================
# [HIGH] floored 簽核身份用 verified、非 caller 傳入
# ============================================================

# 建一個 manager 員工 + verified user_id，模擬部門層本人操作
_MGR_UID = "Umanager_test_001"
_exec("INSERT INTO employees (name, line_user_id, permissions, active) VALUES (?,?,?,1)",
      ("林經理", _MGR_UID, "manager"))

# T7：floored manager 核准 → approver / 稽核 actor 用 verified 員工名、忽略 caller 傳入的「老闆」
_a7 = _make_approval(status="waiting", expires_at="__future__", detail=_DETAIL)
_r7 = _with_floor("general", lambda: service.resolve(_a7, "approved", "老闆"), user_id=_MGR_UID)
_row7 = _q1("SELECT status, approver FROM approvals WHERE id=?", (_a7,))
_log7 = _q1("SELECT actor FROM interaction_log WHERE target_type='approval' AND target_id=? ORDER BY id DESC LIMIT 1", (_a7,))
_assert("T7: floored 核准成功", _row7["status"] == "approved", detail=str(dict(_row7)))
_assert("T7: approver 用 verified 員工名（非 caller 傳入的『老闆』）", _row7["approver"] == "林經理", detail=_row7["approver"])
_assert("T7: 稽核 actor 用 verified 員工名（防冒充）", _log7 and _log7["actor"] == "林經理", detail=str(_log7 and _log7["actor"]))
_assert("T7: 回覆顯示 verified 決定者", "林經理" in _r7 and "老闆" not in _r7, detail=_r7[:80])

# T8：floored 但無 verified LINE 脈絡 → fail-closed 擋下、不落定
_a8 = _make_approval(status="waiting", expires_at="__future__", detail=_DETAIL)
_r8 = _with_floor("general", lambda: service.resolve(_a8, "approved", "老闆"), user_id=None)
_row8 = _q1("SELECT status FROM approvals WHERE id=?", (_a8,))
_assert("T8: 無 verified 脈絡 → ERROR 擋下", _r8.startswith("ERROR") and "無權簽核" in _r8, detail=_r8[:80])
_assert("T8: 被擋下的審核維持 waiting（未落定）", _row8["status"] == "waiting", detail=_row8["status"])

# T9：floored 但 verified 員工權限不足（basic）→ 擋下
_BASIC_UID = "Ubasic_test_001"
_exec("INSERT INTO employees (name, line_user_id, permissions, active) VALUES (?,?,?,1)",
      ("陳助理", _BASIC_UID, "basic"))
_a9 = _make_approval(status="waiting", expires_at="__future__", detail=_DETAIL)
_r9 = _with_floor("general", lambda: service.resolve(_a9, "approved", "老闆"), user_id=_BASIC_UID)
_row9 = _q1("SELECT status FROM approvals WHERE id=?", (_a9,))
_assert("T9: basic 權限被擋下", _r9.startswith("ERROR") and "無權簽核" in _r9, detail=_r9[:80])
_assert("T9: 被擋下維持 waiting", _row9["status"] == "waiting", detail=_row9["status"])


# ============================================================
# create_in_tx actor_user_id 參數（向後相容）
# ============================================================

# T10：不傳 actor_user_id 仍可建（向後相容、預設 ""）
with transaction() as _db:
    _a10 = service.create_in_tx(
        _db, type_="purchase", summary="相容測試", detail=_DETAIL,
        requester="申請人", escalate=False,
    )
_assert("T10: create_in_tx 不傳 actor_user_id 仍建立成功", _a10 is not None and _a10 > 0, detail=str(_a10))

# T11：傳 actor_user_id 不報錯（escalate=True 走 enqueue、actor 蓋章）
with transaction() as _db:
    _a11 = service.create_in_tx(
        _db, type_="purchase", summary="蓋章測試", detail=_DETAIL,
        requester="申請人", actor_user_id="Urequester_999", escalate=True,
    )
_esc11 = _q1("SELECT actor FROM pending_escalations WHERE event_type='approval_pending' ORDER BY id DESC LIMIT 1")
_assert("T11: create_in_tx 傳 actor_user_id 建立成功", _a11 is not None and _a11 > 0, detail=str(_a11))
_assert("T11: enqueue 的上報 row actor 蓋章為傳入申請人（非空、非 system）",
        _esc11 is not None and _esc11["actor"] == "Urequester_999", detail=str(_esc11 and dict(_esc11)))


print(f"\n{'='*50}\n{passed} passed, {failed} failed")
if failures:
    print("FAILURES:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
sys.exit(0)
