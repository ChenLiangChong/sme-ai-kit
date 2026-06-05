"""Leave 模組稽核硬化單元測試（offline、standalone、不連網）。

跑法：
    cd mcp-servers/business-db
    SME_DB_PATH=/tmp/_t_al.db /abs/.venv/bin/python3 tests/test_audit_leave.py

涵蓋（codex 全專案安全稽核 — leave findings）：
HIGH: approve_leave / reject_leave / cancel_leave actor fail-closed
- floored session 查無 verified LINE 脈絡 → approve/reject/cancel 全擋（ERROR、不寫 DB）
- floored basic 員工（非 manager）核准 / 駁回被擋
- 寫進 leave_requests.decided_by / interaction_log.actor 的是 verified 員工名、非 agent 自填
MED: approve_leave approval_id 1:1 綁定
- 另造一張內容相同的 approved approval、用它的 id 核准 → 被擋（approval_id 不符）
MED: cancel pending 請假連帶作廢殭屍 approval
- cancel pending 請假 → 其 waiting/approved-unconsumed 關聯 approval 被標 expired
- 之後 resolve_approval / approve_leave 都無法再消費該孤兒審核
"""
import atexit
import json as _json
import os
import re
import sys
import tempfile
import time as _time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
DB_PATH = _tmp.name
_tmp.close()
os.environ["SME_DB_PATH"] = DB_PATH
os.environ.pop("SME_FLOOR", None)  # 預設全權限（operator）跑種子


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
from modules.leave import service as lsvc  # noqa: E402
from modules.approvals import service as asvc  # noqa: E402

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


def _id(text):
    m = re.search(r"#(\d+)", text or "")
    return int(m.group(1)) if m else None


def _exec(sql, params=()):
    with transaction() as db:
        cur = db.execute(sql, params)
        return cur.lastrowid


def _q1(sql, params=()):
    db = get_db()
    try:
        return db.execute(sql, params).fetchone()
    finally:
        db.close()


# line-channel verified active-request 隔離目錄（floored 寫入需要 verified 脈絡）
_AR_DIR = tempfile.mkdtemp(prefix="leave_ar_")


def _with_floor(floor, fn, user_id):
    """暫設 SME_FLOOR + 寫 verified active-request（模擬受限層 verified 員工）、跑 fn、還原。"""
    old = os.environ.get("SME_FLOOR")
    old_lsd = os.environ.get("LINE_STATE_DIR")
    os.environ["SME_FLOOR"] = floor
    os.environ["LINE_STATE_DIR"] = _AR_DIR
    _arp = os.path.join(_AR_DIR, f"active-request-{floor}.json")
    if user_id is not None:
        with open(_arp, "w", encoding="utf-8") as _f:
            _json.dump({"user_id": user_id, "written_ms": _time.time() * 1000}, _f)
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


# ============================================================
# 種子：員工 + 假別 + 配額
# ============================================================

# 申請人（一般員工）
EMP_ID = _exec(
    "INSERT INTO employees (name, line_user_id, permissions, business_units, active) "
    "VALUES (?,?,?,?,1)",
    ("小員", "Uemp_basic", "basic", "brand_a"),
)
# manager（核准人，floored verified）
MGR_ID = _exec(
    "INSERT INTO employees (name, line_user_id, permissions, business_units, active) "
    "VALUES (?,?,?,?,1)",
    ("陳經理", "Umgr_verified", "manager", "brand_a"),
)

lsvc.register_leave_type(
    code="annual", name="特休", default_quota_days=14,
    requires_approval=True, is_paid=True, notes="",
)
lsvc.set_leave_balance(
    employee_id=EMP_ID, leave_type_code="annual", year=2026, allocated_days=14,
)


def _new_pending():
    """建一筆需簽核的 pending 請假，回 (leave_id, approval_id)。"""
    r = lsvc.request_leave(
        employee_id=EMP_ID, leave_type_code="annual",
        start_date="2026-07-01", end_date="2026-07-02", days=2, reason="休息",
    )
    lid = _id(r.split("\n")[0])
    row = _q1("SELECT approval_id FROM leave_requests WHERE id=?", (lid,))
    return lid, row["approval_id"]


# ============================================================
# HIGH: actor fail-closed
# ============================================================

# T1：floored session 查無 verified 脈絡（user_id=None）→ approve 被擋、不寫 DB
_lid1, _aid1 = _new_pending()
asvc.resolve(_aid1, "approved", "陳經理")  # operator 全權限 resolve
_r1 = _with_floor("general", lambda: lsvc.approve_leave(_lid1, _aid1, "我是老闆"), user_id=None)
_row1 = _q1("SELECT status, decided_by FROM leave_requests WHERE id=?", (_lid1,))
_assert("HIGH-T1: floored 無 verified → approve 擋下（ERROR）", _r1.startswith("ERROR"), detail=_r1[:100])
_assert("HIGH-T1: 請假仍 pending、未寫 decided_by", _row1["status"] == "pending" and _row1["decided_by"] is None,
        detail=str(dict(_row1)))

# T2：floored basic 員工（已 verified 但非 manager）→ approve 被擋（權限不足）
_r2 = _with_floor("general", lambda: lsvc.approve_leave(_lid1, _aid1, "小員"), user_id="Uemp_basic")
_assert("HIGH-T2: floored basic 員工核准被擋（manager gate）", _r2.startswith("ERROR") and "manager" in _r2,
        detail=_r2[:120])
_assert("HIGH-T2: 請假仍 pending", _q1("SELECT status FROM leave_requests WHERE id=?", (_lid1,))["status"] == "pending")

# T3：floored verified manager → approve 成功，decided_by/audit 記 verified 員工名（非 agent 自填）
_r3 = _with_floor("general", lambda: lsvc.approve_leave(_lid1, _aid1, "假冒的名字"), user_id="Umgr_verified")
_row3 = _q1("SELECT status, decided_by FROM leave_requests WHERE id=?", (_lid1,))
_log3 = _q1("SELECT actor FROM interaction_log WHERE action='leave_approved' AND target_id=? "
            "ORDER BY id DESC LIMIT 1", (_lid1,))
_assert("HIGH-T3: floored verified manager 核准成功", not _r3.startswith("ERROR"), detail=_r3[:100])
_assert("HIGH-T3: decided_by 記 verified 員工名（非 agent 自填的『假冒的名字』）",
        _row3["decided_by"] == "陳經理", detail=str(dict(_row3)))
_assert("HIGH-T3: interaction_log.actor 記 verified 員工名", _log3 and _log3["actor"] == "陳經理",
        detail=str(dict(_log3)) if _log3 else "no log")

# T4：reject_leave floored 無 verified → 擋下
_lid4, _aid4 = _new_pending()
asvc.resolve(_aid4, "rejected", "陳經理")
_r4 = _with_floor("general", lambda: lsvc.reject_leave(_lid4, _aid4, "我是老闆", "不准"), user_id=None)
_assert("HIGH-T4: reject_leave floored 無 verified → 擋下", _r4.startswith("ERROR"), detail=_r4[:100])
_assert("HIGH-T4: 請假仍 pending", _q1("SELECT status FROM leave_requests WHERE id=?", (_lid4,))["status"] == "pending")

# T5：cancel_leave floored 無 verified → 擋下、不寫 DB
_lid5, _aid5 = _new_pending()
_r5 = _with_floor("general", lambda: lsvc.cancel_leave(_lid5, "不想請了", "我是老闆"), user_id=None)
_assert("HIGH-T5: cancel_leave floored 無 verified → 擋下", _r5.startswith("ERROR"), detail=_r5[:100])
_assert("HIGH-T5: 請假仍 pending", _q1("SELECT status FROM leave_requests WHERE id=?", (_lid5,))["status"] == "pending")


# ============================================================
# MED: approve_leave approval_id 1:1 綁定
# ============================================================

# T6：另造一張內容相同的 approved approval、拿它的 id 核准 → 被擋（approval_id 不符）
_lid6, _aid6 = _new_pending()
# 偽造另一張 approval：detail 跟真的那筆一模一樣（resume_params 全對），只差 id
_real_detail = _q1("SELECT detail FROM approvals WHERE id=?", (_aid6,))["detail"]
_fake_aid = _exec(
    "INSERT INTO approvals (type, summary, detail, requester, status, expires_at) "
    "VALUES ('leave_request','偽造','" + _real_detail.replace("'", "''") +
    "','x','approved','2099-01-01 00:00:00')"
)
_r6 = lsvc.approve_leave(_lid6, _fake_aid, "陳經理")  # operator 全權限、撞 1:1 gate
_assert("MED-T6: 用不匹配的 approval_id（內容相同但非綁定那張）核准被擋",
        _r6.startswith("ERROR") and "不符" in _r6, detail=_r6[:140])
_assert("MED-T6: 請假仍 pending、偽造審核未被消費",
        _q1("SELECT status FROM leave_requests WHERE id=?", (_lid6,))["status"] == "pending"
        and _q1("SELECT consumed_at FROM approvals WHERE id=?", (_fake_aid,))["consumed_at"] is None,
        detail="leave still pending & fake unused")
# 用正確綁定的 approval_id 仍可正常核准（gate 不誤殺）
asvc.resolve(_aid6, "approved", "陳經理")
_r6b = lsvc.approve_leave(_lid6, _aid6, "陳經理")
_assert("MED-T6: 用正確綁定 approval_id 核准成功（gate 不誤殺）", not _r6b.startswith("ERROR"), detail=_r6b[:100])


# ============================================================
# MED: cancel pending 請假連帶作廢殭屍 approval
# ============================================================

# T7：cancel pending 請假（approval 仍 waiting）→ approval 標 expired、resolve 無法再用
_lid7, _aid7 = _new_pending()
_st7 = _q1("SELECT status FROM approvals WHERE id=?", (_aid7,))["status"]
_assert("MED-T7 setup: 新 pending 請假的 approval 為 waiting", _st7 == "waiting", detail=_st7)
_r7 = lsvc.cancel_leave(_lid7, "不請了", "陳經理")
_st7b = _q1("SELECT status FROM approvals WHERE id=?", (_aid7,))["status"]
_assert("MED-T7: cancel pending → 請假 cancelled", _q1(
    "SELECT status FROM leave_requests WHERE id=?", (_lid7,))["status"] == "cancelled", detail=_r7[:100])
_assert("MED-T7: 關聯 waiting approval 被標 expired（非殭屍）", _st7b == "expired", detail=_st7b)
_assert("MED-T7: 回覆註記關聯審核已作廢", "作廢" in _r7, detail=_r7[:140])
# 殭屍審核不可再被 resolve（resolve 需 waiting）
_r7c = asvc.resolve(_aid7, "approved", "陳經理")
_assert("MED-T7: 已作廢審核無法再 resolve_approval", _r7c.startswith("ERROR"), detail=_r7c[:100])
# 留了 audit
_log7 = _q1("SELECT COUNT(*) c FROM interaction_log WHERE action='leave_approval_voided' AND target_id=?", (_lid7,))
_assert("MED-T7: 作廢有留 audit（leave_approval_voided）", _log7["c"] == 1, detail=str(_log7["c"]))

# T8：cancel pending 請假（approval 已 resolve=approved 但還沒 approve_leave 消費）→ approval 標 expired、
#      approve_leave 無法再消費該孤兒
_lid8, _aid8 = _new_pending()
asvc.resolve(_aid8, "approved", "陳經理")  # resolve 但不 approve_leave
_st8 = _q1("SELECT status, consumed_at FROM approvals WHERE id=?", (_aid8,))
_assert("MED-T8 setup: approval approved 且未消費", _st8["status"] == "approved" and _st8["consumed_at"] is None)
_r8 = lsvc.cancel_leave(_lid8, "改變主意", "陳經理")
_st8b = _q1("SELECT status FROM approvals WHERE id=?", (_aid8,))["status"]
_assert("MED-T8: cancel → 請假 cancelled", _q1(
    "SELECT status FROM leave_requests WHERE id=?", (_lid8,))["status"] == "cancelled")
_assert("MED-T8: approved-but-unconsumed 孤兒 approval 被標 expired", _st8b == "expired", detail=_st8b)
# 孤兒審核不可再被 approve_leave 消費（請假已 cancelled、gate 也找不到 approved-unused）
_r8c = lsvc.approve_leave(_lid8, _aid8, "陳經理")
_assert("MED-T8: 已作廢審核無法再 approve_leave 消費", _r8c.startswith("ERROR"), detail=_r8c[:120])


print(f"\n{'='*50}\n{passed} passed, {failed} failed")
if failures:
    print("FAILURES:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
sys.exit(0)
