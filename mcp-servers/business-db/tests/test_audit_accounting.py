"""accounting 模組 codex 安全稽核回歸（offline、standalone、不連網）。

跑法：
    cd mcp-servers/business-db
    /abs/.venv/bin/python3 tests/test_audit_accounting.py
（會自動用 temp DB；不要併進 test_smoke_all.py）

涵蓋 codex findings：
- [HIGH] update_transaction() 無 _check_permission → 補 manager-gate、無權限被擋
- [HIGH] record_transaction() income+paid+customer 未同步 customers.total_paid → 補同步
- [MED]  delete_transaction() 刪已付收入未回沖 / update_transaction() 改付款狀態·客戶掛載未重算
- [MED]  recorded_by 直寫 → floored session 改用 verified actor（writer_or_error）
"""
import atexit
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
DB_PATH = _tmp.name
_tmp.close()
os.environ["SME_DB_PATH"] = DB_PATH
os.environ.pop("SME_FLOOR", None)  # 全權限/operator 路徑跑種子與多數場景


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
from modules.accounting import service as acct  # noqa: E402

passed = 0
failed = 0
failures: list[str] = []

# verified active-request 目錄（floored 場景模擬 line-channel 驗簽）
_AR_DIR = tempfile.mkdtemp(prefix="acct_ar_")


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
        db.execute(sql, params)


def _q1(sql, params=()):
    db = get_db()
    try:
        return db.execute(sql, params).fetchone()
    finally:
        db.close()


def _with_floor(floor, user_id, fn):
    """暫設 SME_FLOOR + 寫 line-channel verified active-request、跑 fn、還原。

    floored 寫入需 verified LINE 脈絡（真實由 line-channel 驗簽寫），測試補上、
    否則被當 __unverified__ 擋下（撞到 actor gate 而非要測的權限 gate）。
    """
    import json as _j
    import time as _t
    old = os.environ.get("SME_FLOOR")
    old_lsd = os.environ.get("LINE_STATE_DIR")
    os.environ["SME_FLOOR"] = floor
    os.environ["LINE_STATE_DIR"] = _AR_DIR
    arp = os.path.join(_AR_DIR, f"active-request-{floor}.json")
    with open(arp, "w", encoding="utf-8") as f:
        _j.dump({"user_id": user_id, "written_ms": _t.time() * 1000}, f)
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
            os.remove(arp)
        except OSError:
            pass


# ============================================================
# 種子：一個 manager 員工、一個 basic 員工、兩個客戶
# ============================================================
_exec(
    "INSERT INTO employees (name, line_user_id, permissions, business_units, active) "
    "VALUES (?,?,?,?,1)",
    ("王經理", "Umgr_acct", "manager", "brand_a"),
)
_exec(
    "INSERT INTO employees (name, line_user_id, permissions, business_units, active) "
    "VALUES (?,?,?,?,1)",
    ("小職員", "Ubasic_acct", "basic", "brand_a"),
)
_exec("INSERT INTO customers (name, type) VALUES (?, 'customer')", ("甲客戶",))
_exec("INSERT INTO customers (name, type) VALUES (?, 'customer')", ("乙客戶",))
CUST_A = _q1("SELECT id FROM customers WHERE name='甲客戶'")["id"]
CUST_B = _q1("SELECT id FROM customers WHERE name='乙客戶'")["id"]


def _total_paid(cid):
    r = _q1("SELECT total_paid FROM customers WHERE id=?", (cid,))
    return r["total_paid"] or 0


def _kw(type_="income", amount=1000.0, status="paid", cust=0, **kw):
    """operator 路徑（無 floor）建一筆帳，回 txn_id。"""
    params = dict(
        type_=type_, amount=amount, category="sales_revenue", description="t",
        transaction_date="2026-06-01", related_customer_id=cust, related_order_id=0,
        related_invoice="", business_unit="", payment_status=status, due_date="",
        recorded_by="", approved_id=0,
    )
    params.update(kw)
    return _id(acct.record_transaction(**params))


# ============================================================
# Finding [HIGH] record_transaction：income+paid+customer 同步 total_paid
# ============================================================
# 金額均 < 預設審核門檻 5000，避免走超門檻 auto-approval 路徑（那會回審核而非記帳）
_before = _total_paid(CUST_A)
_t1 = _kw(amount=2500.0, status="paid", cust=CUST_A)
_assert("REC-1: record_transaction income+paid+客戶 → total_paid +2500",
        _total_paid(CUST_A) == _before + 2500.0,
        detail=f"{_before}→{_total_paid(CUST_A)}")

# income + pending（未收）→ 不動 total_paid
_before = _total_paid(CUST_A)
_t_pending = _kw(amount=3000.0, status="pending", cust=CUST_A)
_assert("REC-2: income+pending（未收）→ total_paid 不變", _total_paid(CUST_A) == _before)

# expense + paid + customer → 不動 total_paid（只有 income 計入客戶實收）
_before = _total_paid(CUST_A)
_kw(type_="expense", amount=999.0, status="paid", cust=CUST_A)
_assert("REC-3: expense+paid → total_paid 不變", _total_paid(CUST_A) == _before)


# ============================================================
# Finding [MED] delete_transaction：刪已付收入 → 回沖 total_paid
# ============================================================
_before = _total_paid(CUST_A)
_d = acct.delete_transaction(transaction_id=_t1, reason="誤記", actor_user_id="")
_assert("DEL-1: 刪已付 income → total_paid 回沖 -2500",
        _total_paid(CUST_A) == _before - 2500.0, detail=str(_d)[:80])

# 刪 pending（未收）income → total_paid 不變（本來就沒進帳）
_before = _total_paid(CUST_A)
acct.delete_transaction(transaction_id=_t_pending, reason="清理", actor_user_id="")
_assert("DEL-2: 刪 pending income → total_paid 不變", _total_paid(CUST_A) == _before)


# ============================================================
# Finding [HIGH] update_transaction：manager 權限關卡
# ============================================================
_t_upd = _kw(amount=2000.0, status="pending", cust=CUST_A)

# basic 員工（floored、verified）→ 被擋
_r_basic = _with_floor("general", "Ubasic_acct", lambda: acct.update_transaction(
    transaction_id=_t_upd, category="adjusted", description="",
    business_unit="__SKIP__", payment_status="", due_date="",
    related_order_id=-1, related_customer_id=-1, actor_user_id="Ubasic_acct",
))
_assert("UPD-PERM-1: basic 員工改帳被擋（權限不足）",
        _r_basic.startswith("ERROR") and "權限不足" in _r_basic, detail=_r_basic[:100])
# 確認真的沒改到
_row = _q1("SELECT category FROM transactions WHERE id=?", (_t_upd,))
_assert("UPD-PERM-1b: 被擋後欄位未變", _row["category"] == "sales_revenue", detail=_row["category"])

# floored 但查無 verified 脈絡（不寫 active-request）→ __unverified__ 被擋
_old_floor = os.environ.get("SME_FLOOR")
os.environ["SME_FLOOR"] = "general"
os.environ["LINE_STATE_DIR"] = _AR_DIR  # 此目錄無 active-request → 查無脈絡
_r_unv = acct.update_transaction(
    transaction_id=_t_upd, category="x", description="",
    business_unit="__SKIP__", payment_status="", due_date="",
    related_order_id=-1, related_customer_id=-1, actor_user_id="Ubasic_acct",
)
if _old_floor is None:
    os.environ.pop("SME_FLOOR", None)
else:
    os.environ["SME_FLOOR"] = _old_floor
os.environ.pop("LINE_STATE_DIR", None)
_assert("UPD-PERM-2: floored 無 verified 脈絡 → 擋下", _r_unv.startswith("ERROR"), detail=_r_unv[:100])

# manager（floored、verified）→ 放行
_r_mgr = _with_floor("confidential", "Umgr_acct", lambda: acct.update_transaction(
    transaction_id=_t_upd, category="adjusted", description="",
    business_unit="__SKIP__", payment_status="", due_date="",
    related_order_id=-1, related_customer_id=-1, actor_user_id="Umgr_acct",
))
_assert("UPD-PERM-3: manager 改帳放行", not _r_mgr.startswith("ERROR"), detail=_r_mgr[:100])
# audit 記具名 manager（非 system）
_log = _q1("SELECT actor FROM interaction_log WHERE action='transaction_updated' "
           "AND target_id=? ORDER BY id DESC LIMIT 1", (_t_upd,))
_assert("UPD-PERM-3b: audit 記具名 verified 操作者（非 system）",
        _log and _log["actor"] == "王經理", detail=str(dict(_log)) if _log else "no log")

# operator 路徑（無 floor、空 actor）→ 放行（受信任開發/老闆層）
_r_op = acct.update_transaction(
    transaction_id=_t_upd, category="op_edit", description="",
    business_unit="__SKIP__", payment_status="", due_date="",
    related_order_id=-1, related_customer_id=-1, actor_user_id="",
)
_assert("UPD-PERM-4: operator（空 actor）放行", not _r_op.startswith("ERROR"), detail=_r_op[:80])


# ============================================================
# Finding [MED] update_transaction：付款狀態 / 客戶掛載重算 total_paid
# ============================================================
# (a) pending→paid：補進 total_paid
_t_a = _kw(amount=4000.0, status="pending", cust=CUST_A)
_before = _total_paid(CUST_A)
acct.update_transaction(
    transaction_id=_t_a, category="", description="", business_unit="__SKIP__",
    payment_status="paid", due_date="", related_order_id=-1, related_customer_id=-1,
    actor_user_id="",
)
_assert("UPD-RECALC-a: pending→paid → total_paid +4000",
        _total_paid(CUST_A) == _before + 4000.0, detail=f"{_before}→{_total_paid(CUST_A)}")

# (b) 改客戶掛載（已 paid）：從甲移到乙
_before_a = _total_paid(CUST_A)
_before_b = _total_paid(CUST_B)
acct.update_transaction(
    transaction_id=_t_a, category="", description="", business_unit="__SKIP__",
    payment_status="", due_date="", related_order_id=-1, related_customer_id=CUST_B,
    actor_user_id="",
)
_assert("UPD-RECALC-b1: 改客戶後甲 -4000", _total_paid(CUST_A) == _before_a - 4000.0,
        detail=f"{_before_a}→{_total_paid(CUST_A)}")
_assert("UPD-RECALC-b2: 改客戶後乙 +4000", _total_paid(CUST_B) == _before_b + 4000.0,
        detail=f"{_before_b}→{_total_paid(CUST_B)}")

# (c) 清除客戶掛載（已 paid）：乙退回
_before_b = _total_paid(CUST_B)
acct.update_transaction(
    transaction_id=_t_a, category="", description="", business_unit="__SKIP__",
    payment_status="", due_date="", related_order_id=-1, related_customer_id=0,
    actor_user_id="",
)
_assert("UPD-RECALC-c: 清除客戶 → 乙 -4000", _total_paid(CUST_B) == _before_b - 4000.0,
        detail=f"{_before_b}→{_total_paid(CUST_B)}")


# ============================================================
# Finding [MED] update_transaction 逆向路徑：paid → pending/overdue 回沖客戶累計
# （codex 複審第二輪：第一輪只補正向 pending→paid、反向轉未付沒回沖、paid_amount 也沒歸零）
# ============================================================
# (d) paid → pending：客戶累計負向回沖 + paid_amount 歸零
_t_rev = _kw(amount=3500.0, status="paid", cust=CUST_A)  # 建一筆已付、計入甲
_before_rev = _total_paid(CUST_A)
_paid_before = _q1("SELECT paid_amount FROM transactions WHERE id=?", (_t_rev,))["paid_amount"]
_assert("UPD-REV-d setup: 已付帳 paid_amount=3500", _paid_before == 3500.0, detail=str(_paid_before))
acct.update_transaction(
    transaction_id=_t_rev, category="", description="", business_unit="__SKIP__",
    payment_status="pending", due_date="", related_order_id=-1, related_customer_id=-1,
    actor_user_id="",
)
_assert("UPD-REV-d: paid→pending → 甲 total_paid -3500（負向回沖）",
        _total_paid(CUST_A) == _before_rev - 3500.0, detail=f"{_before_rev}→{_total_paid(CUST_A)}")
_paid_after = _q1("SELECT paid_amount, payment_status FROM transactions WHERE id=?", (_t_rev,))
_assert("UPD-REV-d: paid_amount 歸零（轉未付）", _paid_after["paid_amount"] == 0,
        detail=str(dict(_paid_after)))
_assert("UPD-REV-d: payment_status 確實改成 pending", _paid_after["payment_status"] == "pending",
        detail=str(dict(_paid_after)))

# (e) paid → overdue：同樣回沖 + 歸零（涵蓋另一個未付狀態）
_t_rev2 = _kw(amount=2200.0, status="paid", cust=CUST_B)
_before_rev2 = _total_paid(CUST_B)
acct.update_transaction(
    transaction_id=_t_rev2, category="", description="", business_unit="__SKIP__",
    payment_status="overdue", due_date="", related_order_id=-1, related_customer_id=-1,
    actor_user_id="",
)
_assert("UPD-REV-e: paid→overdue → 乙 total_paid -2200", _total_paid(CUST_B) == _before_rev2 - 2200.0,
        detail=f"{_before_rev2}→{_total_paid(CUST_B)}")
_assert("UPD-REV-e: paid_amount 歸零",
        _q1("SELECT paid_amount FROM transactions WHERE id=?", (_t_rev2,))["paid_amount"] == 0)

# (f) 反向回復 overdue → paid：再補回客戶累計（正反向對稱、無漏算）
_before_rev3 = _total_paid(CUST_B)
acct.update_transaction(
    transaction_id=_t_rev2, category="", description="", business_unit="__SKIP__",
    payment_status="paid", due_date="", related_order_id=-1, related_customer_id=-1,
    actor_user_id="",
)
_assert("UPD-REV-f: overdue→paid 再補回 → 乙 total_paid +2200",
        _total_paid(CUST_B) == _before_rev3 + 2200.0, detail=f"{_before_rev3}→{_total_paid(CUST_B)}")
_assert("UPD-REV-f: paid_amount 補滿 = amount",
        _q1("SELECT paid_amount FROM transactions WHERE id=?", (_t_rev2,))["paid_amount"] == 2200.0)


# ============================================================
# Finding [MED] recorded_by：floored session 用 verified actor（非 agent 自填）
# ============================================================
# floored、verified=王經理，但 agent 自填 recorded_by='偽造者' → 應記成王經理
def _floored_record():
    return acct.record_transaction(
        type_="income", amount=100.0, category="sales_revenue", description="floored",
        transaction_date="2026-06-02", related_customer_id=0, related_order_id=0,
        related_invoice="", business_unit="brand_a", payment_status="paid", due_date="",
        recorded_by="偽造者", approved_id=0,
    )

_rf = _with_floor("confidential", "Umgr_acct", _floored_record)
_tf = _id(_rf)
_logf = _q1("SELECT recorded_by FROM transactions WHERE id=?", (_tf,))
_assert("ACTOR-1: floored recorded_by 用 verified 員工名（忽略 agent 自填）",
        _logf and _logf["recorded_by"] == "王經理", detail=str(dict(_logf)) if _logf else "no row")
_ilogf = _q1("SELECT actor FROM interaction_log WHERE action='transaction_recorded' "
             "AND target_id=? ORDER BY id DESC LIMIT 1", (_tf,))
_assert("ACTOR-1b: interaction_log.actor 同為 verified 員工名",
        _ilogf and _ilogf["actor"] == "王經理", detail=str(dict(_ilogf)) if _ilogf else "no log")

# floored 無 verified 脈絡 → 拒絕寫入（actor fail-closed）
_old_floor = os.environ.get("SME_FLOOR")
os.environ["SME_FLOOR"] = "general"
os.environ["LINE_STATE_DIR"] = _AR_DIR
_r_block = acct.record_transaction(
    type_="income", amount=100.0, category="sales_revenue", description="",
    transaction_date="2026-06-02", related_customer_id=0, related_order_id=0,
    related_invoice="", business_unit="brand_a", payment_status="paid", due_date="",
    recorded_by="anything", approved_id=0,
)
if _old_floor is None:
    os.environ.pop("SME_FLOOR", None)
else:
    os.environ["SME_FLOOR"] = _old_floor
os.environ.pop("LINE_STATE_DIR", None)
_assert("ACTOR-2: floored 無 verified 脈絡 → record_transaction 拒絕寫入",
        _r_block.startswith("ERROR"), detail=_r_block[:100])

# operator 路徑（無 floor）recorded_by 照用傳入值
_r_op = acct.record_transaction(
    type_="income", amount=100.0, category="sales_revenue", description="",
    transaction_date="2026-06-02", related_customer_id=0, related_order_id=0,
    related_invoice="", business_unit="", payment_status="paid", due_date="",
    recorded_by="老闆", approved_id=0,
)
_top = _id(_r_op)
_logop = _q1("SELECT recorded_by FROM transactions WHERE id=?", (_top,))
_assert("ACTOR-3: operator 路徑 recorded_by 用傳入值", _logop["recorded_by"] == "老闆",
        detail=str(dict(_logop)))


print(f"\n{'='*50}\n{passed} passed, {failed} failed")
if failures:
    print("FAILURES:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
sys.exit(0)
