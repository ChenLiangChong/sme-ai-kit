"""orders 模組 codex 安全稽核回歸測試（offline、standalone、不連網）。

跑法：
    cd mcp-servers/business-db
    SME_DB_PATH=/tmp/_t_ao.db python3 tests/test_audit_orders.py

涵蓋 codex findings：
- [HIGH] fulfill_order 完整出貨後再呼叫 → 不重複扣庫存 / 不重複建應收（已全部出貨守門）
- [MED]  _calc_receivable 訂金/預付多次部分出貨 → 應收加總正確（抵扣只算一次、分攤）
- [MED]  create_order 非全權限層偽造 created_by → actor fail-closed；resolve 後寫可信值
- [MED]  cancel_order 兩筆不可逆 audit log 具名（非 actor='system'）
- [LOW]  create_order 非法 items_json（{}、[1]、{"qty":"2"}、空陣列）→ ERROR 不 raise
"""
import atexit
import json
import os
import re
import sys
import tempfile
import time

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
from modules.orders import service as osvc  # noqa: E402

passed = 0
failed = 0
failures: list[str] = []

_AR_DIR = tempfile.mkdtemp(prefix="orders_ar_")


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


def _q1(sql, params=()):
    db = get_db()
    try:
        return db.execute(sql, params).fetchone()
    finally:
        db.close()


def _exec(sql, params=()):
    with transaction() as db:
        cur = db.execute(sql, params)
        return cur.lastrowid


def _with_floor(floor, fn, user_id):
    """暫設 SME_FLOOR + 寫 line-channel verified active-request、跑 fn、還原。"""
    old = os.environ.get("SME_FLOOR")
    old_lsd = os.environ.get("LINE_STATE_DIR")
    os.environ["SME_FLOOR"] = floor
    os.environ["LINE_STATE_DIR"] = _AR_DIR
    arp = os.path.join(_AR_DIR, f"active-request-{floor}.json")
    with open(arp, "w", encoding="utf-8") as f:
        json.dump({"user_id": user_id, "written_ms": time.time() * 1000}, f)
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


# ---- 種子：客戶 + 庫存 + 一個 manager 員工 ----

CUST = _exec(
    "INSERT INTO customers (name, payment_terms, discount_rate) VALUES (?,?,?)",
    ("測試客戶", "net30", 0),
)
CUST_PREPAID = _exec(
    "INSERT INTO customers (name, payment_terms, discount_rate) VALUES (?,?,?)",
    ("預付客戶", "prepaid", 0),
)
CUST_DEPOSIT = _exec(
    "INSERT INTO customers (name, payment_terms, discount_rate) VALUES (?,?,?)",
    ("訂金客戶", "deposit_30", 0),
)


def _seed_inv(sku, stock):
    return _exec(
        "INSERT INTO inventory (sku, name, current_stock, reserved, min_stock, unit) "
        "VALUES (?,?,?,0,0,'個')",
        (sku, f"品項{sku}", stock),
    )


MGR_UID = "Umanager_test"
_exec(
    "INSERT INTO employees (name, line_user_id, permissions, active) VALUES (?,?,?,1)",
    ("陳經理", MGR_UID, "manager"),
)


# ============================================================
# [HIGH] fulfill_order 完整出貨後不重複出貨
# ============================================================

_seed_inv("H1", 100)
_o1 = _id(osvc.create_order(
    customer_id=CUST, items_json='[{"sku":"H1","name":"品項H1","qty":10,"price":100}]',
    notes="", business_unit="", created_by="", approved_id=0,
))
_assert("HIGH-setup: create_order 成功", _o1 is not None)
# 確認 → QC pass → 完整出貨
osvc.update_order(_o1, status="confirmed", notes="", driver="", estimated_delivery="")
osvc.qc_order(_o1, result="passed", notes="", checked_by="")
_f1 = osvc.fulfill_order(_o1, partial_items_json="")
_assert("HIGH: 首次完整出貨成功（已出貨）", "已出貨" in _f1 and "ERROR" not in _f1, detail=_f1[:120])

_stock_after_first = _q1("SELECT current_stock FROM inventory WHERE sku='H1'")["current_stock"]
_ar_count_first = _q1(
    "SELECT COUNT(*) c FROM transactions WHERE related_order_id=? AND type='income'", (_o1,)
)["c"]
_assert("HIGH: 首次出貨扣 10（剩 90）", _stock_after_first == 90, detail=str(_stock_after_first))
_assert("HIGH: 首次出貨建 1 筆應收", _ar_count_first == 1, detail=str(_ar_count_first))

# 完整出貨後 items 應有 shipped_qty 標記
_items_after = json.loads(_q1("SELECT items FROM orders WHERE id=?", (_o1,))["items"])
_assert("HIGH: 完整出貨已寫 shipped_qty 標記", _items_after[0].get("shipped_qty") == 10,
        detail=str(_items_after))

# 再次呼叫 fulfill（不帶 partial）→ 應回「已全部出貨完畢」、不再扣庫存 / 不再建應收
_f1b = osvc.fulfill_order(_o1, partial_items_json="")
_stock_after_second = _q1("SELECT current_stock FROM inventory WHERE sku='H1'")["current_stock"]
_ar_count_second = _q1(
    "SELECT COUNT(*) c FROM transactions WHERE related_order_id=? AND type='income'", (_o1,)
)["c"]
_assert("HIGH: 再次 fulfill 回『已出貨完畢』提示", "已出貨完畢" in _f1b, detail=_f1b[:120])
_assert("HIGH: 再次 fulfill 不重複扣庫存（仍 90）", _stock_after_second == 90,
        detail=str(_stock_after_second))
_assert("HIGH: 再次 fulfill 不重複建應收（仍 1 筆）", _ar_count_second == 1,
        detail=str(_ar_count_second))

# 再次強塞 partial 指定同 SKU → _validate_partial_ship_items 擋下「無剩餘可補」
_f1c = osvc.fulfill_order(_o1, partial_items_json='[{"sku":"H1","qty":10}]')
_assert("HIGH: 強塞 partial 補出貨被擋（無剩餘可補）",
        "ERROR" in _f1c and ("無剩餘" in _f1c or "出貨完畢" in _f1c), detail=_f1c[:160])
_stock_after_third = _q1("SELECT current_stock FROM inventory WHERE sku='H1'")["current_stock"]
_assert("HIGH: 強塞 partial 後庫存仍 90", _stock_after_third == 90, detail=str(_stock_after_third))


# ============================================================
# [MED] 訂金多次部分出貨 → 應收加總正確
# ============================================================

# 訂單：A×5@100 + B×5@40 = 700；deposit_30 → 訂金 210
_seed_inv("D_A", 100)
_seed_inv("D_B", 100)
_od = _id(osvc.create_order(
    customer_id=CUST_DEPOSIT,
    items_json='[{"sku":"D_A","name":"A","qty":5,"price":100},'
               '{"sku":"D_B","name":"B","qty":5,"price":40}]',
    notes="", business_unit="", created_by="", approved_id=0,
))
_total_d = _q1("SELECT total_amount FROM orders WHERE id=?", (_od,))["total_amount"]
_assert("MED-deposit-setup: 訂單金額 700", _total_d == 700, detail=str(_total_d))

# 收訂金 210（30%）
_exec(
    "INSERT INTO transactions (type, amount, category, related_order_id, payment_status, "
    "paid_amount, transaction_date) VALUES ('income',210,'deposit',?,'paid',210,'2026-01-01')",
    (_od,),
)
osvc.update_order(_od, status="confirmed", notes="", driver="", estimated_delivery="")
# QC partial 讓它走部分出貨路徑
osvc.qc_order(_od, result="partial", notes="分批", checked_by="")

# 第一次出 A×5（ship_total = 700 * 500/700 = 500）；credit = 210*500/700 = 150；應收 350
_fd1 = osvc.fulfill_order(_od, partial_items_json='[{"sku":"D_A","qty":5}]')
_assert("MED-deposit: 第一次部分出貨成功", "ERROR" not in _fd1, detail=_fd1[:160])
# 第二次出 B×5（ship_total = 700 * 200/700 = 200）；credit = 210*200/700 = 60；應收 140
_fd2 = osvc.fulfill_order(_od, partial_items_json='[{"sku":"D_B","qty":5}]')
_assert("MED-deposit: 第二次部分出貨成功", "ERROR" not in _fd2, detail=_fd2[:160])

# 應收加總 = 700 - 210 = 490（不是舊 bug 的 280）
_recv_rows = _q1(
    "SELECT COALESCE(SUM(amount),0) s FROM transactions "
    "WHERE related_order_id=? AND type='income' AND payment_status='pending'", (_od,)
)["s"]
_assert("MED-deposit: 兩次部分出貨應收加總 = 490（訂金只抵一次）",
        abs(_recv_rows - 490) < 1.0, detail=str(_recv_rows))

# prepaid 完整出貨應收 = 0（退化驗證）
_seed_inv("P1", 100)
_op = _id(osvc.create_order(
    customer_id=CUST_PREPAID, items_json='[{"sku":"P1","name":"P1","qty":2,"price":300}]',
    notes="", business_unit="", created_by="", approved_id=0,
))
_exec(
    "INSERT INTO transactions (type, amount, category, related_order_id, payment_status, "
    "paid_amount, transaction_date) VALUES ('income',600,'prepay',?,'paid',600,'2026-01-01')",
    (_op,),
)
osvc.update_order(_op, status="confirmed", notes="", driver="", estimated_delivery="")
osvc.qc_order(_op, result="passed", notes="", checked_by="")
_fp = osvc.fulfill_order(_op, partial_items_json="")
_recv_p = _q1(
    "SELECT COUNT(*) c FROM transactions WHERE related_order_id=? AND type='income' "
    "AND payment_status='pending'", (_op,)
)["c"]
_assert("MED-prepaid: 全額預付完整出貨不建應收（應收 0 筆）", _recv_p == 0, detail=str(_recv_p))


# ============================================================
# [MED] create_order actor fail-closed
# ============================================================

# 受限層（floored）且無 verified 脈絡 → 寫入被擋
def _floored_no_ctx():
    # 不寫 active-request → __unverified__
    old = os.environ.get("SME_FLOOR")
    old_lsd = os.environ.get("LINE_STATE_DIR")
    os.environ["SME_FLOOR"] = "general"
    os.environ["LINE_STATE_DIR"] = _AR_DIR  # 此目錄無 general 的 active-request
    try:
        return osvc.create_order(
            customer_id=CUST, items_json='[{"sku":"X","name":"X","qty":1,"price":50}]',
            notes="", business_unit="", created_by="偽造老闆", approved_id=0,
        )
    finally:
        if old is None:
            os.environ.pop("SME_FLOOR", None)
        else:
            os.environ["SME_FLOOR"] = old
        if old_lsd is None:
            os.environ.pop("LINE_STATE_DIR", None)
        else:
            os.environ["LINE_STATE_DIR"] = old_lsd


_orders_before = _q1("SELECT COUNT(*) c FROM orders")["c"]
_r_fc = _floored_no_ctx()
_orders_after = _q1("SELECT COUNT(*) c FROM orders")["c"]
_assert("MED-actor: floored 無 verified 脈絡 → create_order 擋下", _r_fc.startswith("ERROR"),
        detail=_r_fc[:120])
_assert("MED-actor: 擋下後未寫入任何訂單", _orders_after == _orders_before,
        detail=f"{_orders_before}->{_orders_after}")

# 受限層 + verified 員工 → 寫入用可信員工名（非 agent 自填的「偽造老闆」）
_seed_inv("FC1", 100)
_r_ok = _with_floor(
    "general",
    lambda: osvc.create_order(
        customer_id=CUST, items_json='[{"sku":"FC1","name":"FC1","qty":1,"price":50}]',
        notes="", business_unit="", created_by="偽造老闆", approved_id=0,
    ),
    user_id=MGR_UID,
)
_o_fc = _id(_r_ok)
_assert("MED-actor: floored + verified → create_order 成功", _o_fc is not None, detail=_r_ok[:120])
_created_by = _q1("SELECT created_by FROM orders WHERE id=?", (_o_fc,))["created_by"]
_log_actor = _q1(
    "SELECT actor FROM interaction_log WHERE action='order_created' AND target_id=?", (_o_fc,)
)["actor"]
_assert("MED-actor: created_by 寫 verified 員工名（非偽造老闆）",
        _created_by == "陳經理", detail=str(_created_by))
_assert("MED-actor: interaction_log.actor 寫 verified 員工名", _log_actor == "陳經理",
        detail=str(_log_actor))


# ============================================================
# [MED] cancel_order audit 具名
# ============================================================

_seed_inv("C1", 100)
_oc = _id(osvc.create_order(
    customer_id=CUST, items_json='[{"sku":"C1","name":"C1","qty":3,"price":100}]',
    notes="", business_unit="", created_by="", approved_id=0,
))
osvc.update_order(_oc, status="confirmed", notes="", driver="", estimated_delivery="")
osvc.qc_order(_oc, result="passed", notes="", checked_by="")
osvc.fulfill_order(_oc, partial_items_json="")  # 建一筆 pending 應收
# manager 在 floored session 取消（verified）→ audit 應記「陳經理」
_r_cancel = _with_floor(
    "general",
    lambda: osvc.cancel_order(
        order_id=_oc, reason="客戶取消", cancel_type="cancelled", actor_user_id="忽略此值",
    ),
    user_id=MGR_UID,
)
_assert("MED-cancel: 取消成功", "已取消" in _r_cancel and "ERROR" not in _r_cancel,
        detail=_r_cancel[:160])
_cancel_log = _q1(
    "SELECT actor FROM interaction_log WHERE action='order_cancelled' AND target_id=?", (_oc,)
)
_assert("MED-cancel: order_cancelled audit 具名（陳經理、非 system）",
        _cancel_log and _cancel_log["actor"] == "陳經理", detail=str(dict(_cancel_log) if _cancel_log else None))
_void_log = _q1(
    "SELECT actor FROM interaction_log WHERE action='transaction_voided' "
    "ORDER BY id DESC LIMIT 1"
)
_assert("MED-cancel: transaction_voided audit 具名（陳經理、非 system）",
        _void_log and _void_log["actor"] == "陳經理", detail=str(dict(_void_log) if _void_log else None))


# ============================================================
# [LOW] create_order 非法 items_json → ERROR 不 raise
# ============================================================

def _try_create(items_json):
    try:
        return osvc.create_order(
            customer_id=CUST, items_json=items_json, notes="", business_unit="",
            created_by="", approved_id=0,
        )
    except Exception as e:  # noqa: BLE001
        return f"__RAISED__ {type(e).__name__}: {e}"


for label, payload in [
    ("空物件 {}", "{}"),
    ("非物件元素 [1]", "[1]"),
    ("qty 非數字 {\"qty\":\"2\"}", '[{"sku":"Z","qty":"2","price":10}]'),
    ("price 非數字", '[{"sku":"Z","qty":2,"price":"x"}]'),
    ("空陣列 []", "[]"),
    ("壞 JSON", "{not json"),
    ("qty 為 bool", '[{"sku":"Z","qty":true,"price":10}]'),
]:
    _r = _try_create(payload)
    _assert(f"LOW-items: {label} → ERROR 不 raise",
            _r.startswith("ERROR"), detail=_r[:120])


print(f"\n{'='*50}\n{passed} passed, {failed} failed")
if failures:
    print("FAILURES:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
sys.exit(0)
