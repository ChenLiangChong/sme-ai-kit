"""codex 安全稽核回歸：crm / inventory / tasks 三模組（offline、standalone、不連網）。

跑法：
    cd mcp-servers/business-db
    SME_DB_PATH=/tmp/_t_audit.db /abs/.venv/bin/python3 tests/test_audit_crm_inv_tasks.py

涵蓋（對應 codex findings）：
crm.set_entity_terms
- 空 business_unit → ERROR（不寫懸空覆寫規則）
- 不存在的 business_unit → ERROR
- 合法 BU 重複呼叫（先 set 再 update）不 raise（原子 upsert），結果是 UPDATE 非新增列
inventory.update_stock
- BU 打錯（該 BU 無此 SKU、但全域有同 SKU）→ ERROR，不誤改全域庫存列
- BU 正確 → 正常扣減
- 無 BU 時動到全域庫存（行為不變）
tasks.list_tasks
- parent_task_id=0 → 只回頂層任務（不含子任務）
- parent_task_id>0 → 只回該父的子任務
- parent_task_id=-1 → 不過濾（含子任務）
"""
import atexit
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
DB_PATH = _tmp.name
_tmp.close()
os.environ["SME_DB_PATH"] = DB_PATH
os.environ.pop("SME_FLOOR", None)  # 全權限（is_full_access）跑 service


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
from modules.crm import service as crm  # noqa: E402
from modules.inventory import service as inv  # noqa: E402
from modules.tasks import repository as trepo  # noqa: E402
from modules.tasks import service as tsvc  # noqa: E402

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
        return db.execute(sql, params)


def _q1(sql, params=()):
    db = get_db()
    try:
        return db.execute(sql, params).fetchone()
    finally:
        db.close()


# ---- 種子 ----
_exec(
    "INSERT INTO business_entities (id, name, approval_threshold) VALUES (?,?,?)",
    ("brand_a", "品牌A", 5000),
)
_exec(
    "INSERT INTO customers (name, type, discount_rate, payment_terms) VALUES (?,?,?,?)",
    ("測試客戶", "customer", 0, "net30"),
)
_CID = _q1("SELECT id FROM customers WHERE name='測試客戶'")["id"]


# ============================================================
# crm.set_entity_terms
# ============================================================

# T1：空 BU → ERROR、且未寫入任何 entity_terms 列
_r1 = crm.set_entity_terms(_CID, "", 0.1, "net60")
_cnt1 = _q1("SELECT COUNT(*) c FROM customer_entity_terms WHERE customer_id=?", (_CID,))
_assert("CRM-T1: 空 BU → ERROR", _r1.startswith("ERROR"), detail=_r1)
_assert("CRM-T1: 空 BU 未寫懸空條件列", _cnt1["c"] == 0)

# T1b：純空白 BU 也擋
_r1b = crm.set_entity_terms(_CID, "   ", 0.1, "net60")
_assert("CRM-T1b: 純空白 BU → ERROR", _r1b.startswith("ERROR"), detail=_r1b)

# T2：不存在的 BU → ERROR、未寫入
_r2 = crm.set_entity_terms(_CID, "no_such_bu", 0.1, "net60")
_cnt2 = _q1(
    "SELECT COUNT(*) c FROM customer_entity_terms WHERE customer_id=? AND business_unit=?",
    (_CID, "no_such_bu"),
)
_assert("CRM-T2: 不存在 BU → ERROR", _r2.startswith("ERROR"), detail=_r2)
_assert("CRM-T2: 不存在 BU 未寫入", _cnt2["c"] == 0)

# T3：合法 BU 首次設定 → 成功、寫一筆
_r3 = crm.set_entity_terms(_CID, "brand_a", 0.15, "net60")
_row3 = _q1(
    "SELECT * FROM customer_entity_terms WHERE customer_id=? AND business_unit=?",
    (_CID, "brand_a"),
)
_assert("CRM-T3: 合法 BU set 成功", (not _r3.startswith("ERROR")) and _row3 is not None, detail=_r3)
_assert("CRM-T3: discount_rate 寫入正確", _row3 and abs(_row3["discount_rate"] - 0.15) < 1e-9)

# T4：同 BU 重複呼叫（update）→ 不 raise、結果是 UPDATE（仍只一列）、值更新
_r4 = crm.set_entity_terms(_CID, "brand_a", 0.2, "net90")
_cnt4 = _q1(
    "SELECT COUNT(*) c FROM customer_entity_terms WHERE customer_id=? AND business_unit=?",
    (_CID, "brand_a"),
)
_row4 = _q1(
    "SELECT * FROM customer_entity_terms WHERE customer_id=? AND business_unit=?",
    (_CID, "brand_a"),
)
_assert("CRM-T4: 重複呼叫不 raise（回字串非例外）", isinstance(_r4, str) and not _r4.startswith("ERROR"), detail=_r4)
_assert("CRM-T4: upsert 後仍只有一列（UNIQUE 未撞 raise）", _cnt4["c"] == 1)
_assert("CRM-T4: 值已更新為 0.2 / net90", _row4 and abs(_row4["discount_rate"] - 0.2) < 1e-9 and _row4["payment_terms"] == "net90")


# ============================================================
# inventory.update_stock — BU 嚴格、不誤改全域
# ============================================================

# 種子：一筆無歸屬（全域）SKU=WIDGET 100、一筆 brand_a 的 WIDGET 50
_exec(
    "INSERT INTO inventory (sku, name, current_stock, business_unit, min_stock, unit) "
    "VALUES (?,?,?,?,?,?)",
    ("WIDGET", "小工具(全域)", 100, None, 0, "個"),
)
_exec(
    "INSERT INTO inventory (sku, name, current_stock, business_unit, min_stock, unit) "
    "VALUES (?,?,?,?,?,?)",
    ("WIDGET", "小工具(brand_a)", 50, "brand_a", 0, "個"),
)


def _stock(sku, bu):
    if bu is None:
        r = _q1(
            "SELECT current_stock FROM inventory WHERE sku=? AND (business_unit IS NULL OR business_unit='')",
            (sku,),
        )
    else:
        r = _q1(
            "SELECT current_stock FROM inventory WHERE sku=? AND business_unit=?",
            (sku, bu),
        )
    return r["current_stock"] if r else None


# T5：BU 正確（brand_a）→ 扣 brand_a 那列、不動全域
_r5 = inv.update_stock(
    sku="WIDGET", quantity_change=-10, reason="出貨", name="", sell_price=-1,
    unit_cost=-1, min_stock=-1, unit="", category="", business_unit="brand_a",
)
_assert("INV-T5: brand_a 扣減成功（非 ERROR）", not _r5.startswith("ERROR"), detail=_r5)
_assert("INV-T5: brand_a 庫存 50→40", _stock("WIDGET", "brand_a") == 40)
_assert("INV-T5: 全域庫存未被動（仍 100）", _stock("WIDGET", None) == 100)

# T6：BU 打錯（brand_x 無此 SKU、但全域有同 SKU）→ ERROR、全域與 brand_a 都不動
_r6 = inv.update_stock(
    sku="WIDGET", quantity_change=-30, reason="出貨", name="", sell_price=-1,
    unit_cost=-1, min_stock=-1, unit="", category="", business_unit="brand_x",
)
_assert("INV-T6: BU 打錯 → ERROR（不靜默 fallback 改全域）", _r6.startswith("ERROR"), detail=_r6)
_assert("INV-T6: 全域庫存未被誤扣（仍 100）", _stock("WIDGET", None) == 100)
_assert("INV-T6: brand_a 庫存未被動（仍 40）", _stock("WIDGET", "brand_a") == 40)

# T7：無 BU → 動全域庫存（既有行為不變）
_r7 = inv.update_stock(
    sku="WIDGET", quantity_change=-5, reason="出貨", name="", sell_price=-1,
    unit_cost=-1, min_stock=-1, unit="", category="", business_unit="",
)
_assert("INV-T7: 無 BU 扣全域成功", not _r7.startswith("ERROR"), detail=_r7)
_assert("INV-T7: 全域庫存 100→95", _stock("WIDGET", None) == 95)
_assert("INV-T7: brand_a 庫存未被動（仍 40）", _stock("WIDGET", "brand_a") == 40)


# ============================================================
# tasks.list_tasks — parent_task_id sentinel
# ============================================================

# 種子：兩個頂層任務 + 一個子任務（掛在第一個頂層下）
_p1 = _exec(
    "INSERT INTO tasks (title, priority, category) VALUES (?,?,?)",
    ("頂層任務1", "normal", "general"),
).lastrowid
_p2 = _exec(
    "INSERT INTO tasks (title, priority, category) VALUES (?,?,?)",
    ("頂層任務2", "normal", "general"),
).lastrowid
_sub = _exec(
    "INSERT INTO tasks (title, priority, category, parent_task_id) VALUES (?,?,?,?)",
    ("子任務A", "normal", "general", _p1),
).lastrowid


def _ids(rows):
    return {r["id"] for r in rows}


db = get_db()
try:
    # T8：parent_task_id=0 → 只回頂層（不含子任務）
    top = _ids(trepo.list_tasks(db, parent_task_id=0, limit=50))
    _assert("TASK-T8: parent=0 含兩個頂層任務", _p1 in top and _p2 in top, detail=str(top))
    _assert("TASK-T8: parent=0 不含子任務（語義修正核心）", _sub not in top, detail=str(top))

    # T9：parent_task_id=>0 → 只回該父的子任務
    children = _ids(trepo.list_tasks(db, parent_task_id=_p1, limit=50))
    _assert("TASK-T9: parent=p1 只回子任務A", children == {_sub}, detail=str(children))

    # T10：parent_task_id=-1 → 不過濾（頂層 + 子任務都在）
    all_t = _ids(trepo.list_tasks(db, parent_task_id=-1, limit=50))
    _assert("TASK-T10: parent=-1 不過濾（含頂層與子任務）",
            {_p1, _p2, _sub} <= all_t, detail=str(all_t))
finally:
    db.close()

# T11：透過 service 層（對外語義）確認 parent=0 不端出子任務字串
_out = tsvc.list_tasks(status="", assignee="", category="", business_unit="",
                       parent_task_id=0, limit=50)
_assert("TASK-T11: service parent=0 輸出含頂層1", "頂層任務1" in _out, detail=_out[:120])
_assert("TASK-T11: service parent=0 輸出不含子任務A 作為頂層列",
        "[#%d] 子任務A" % _sub not in _out, detail=_out[:200])


print(f"\n{'='*50}\n{passed} passed, {failed} failed")
if failures:
    print("FAILURES:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
sys.exit(0)
