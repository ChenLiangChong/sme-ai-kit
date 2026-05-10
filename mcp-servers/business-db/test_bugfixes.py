"""
Regression tests for 2026-04-19 bug batch (Bugs #1-#5 + Obs #6).

這批測試覆蓋本次修復，確保同類 bug 不再發生：
- Bug #1: init_db 多次執行後 FK 不會指向 _customers_migrate / _orders_migrate
- Bug #2: fulfill_order / record_payment / cancel_order 同步維護 customers 累計欄位
- Bug #3: update_rule 可連續多次呼叫不觸發 UNIQUE constraint
- Bug #4: inventory.reserved 的完整 flow（預留 → 出貨扣減 → 取消釋放）
- Bug #5: update_stock(quantity_change=0) 允許新建 SKU
- Obs #6: customers.primary_business_unit 的寫入與顯示

使用方式：python3 test_bugfixes.py
"""
import sys, os, json, sqlite3, tempfile

sys.path.insert(0, os.path.dirname(__file__))

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
DB_PATH = _tmp.name
_tmp.close()
os.environ["SME_DB_PATH"] = DB_PATH

import server  # noqa: E402
server.DB_PATH = DB_PATH
server.init_db()

passed = 0
failed = 0


def _assert(name, cond, detail=""):
    global passed, failed
    if cond:
        print(f"✅ {name}")
        passed += 1
    else:
        print(f"❌ {name}{('  ' + detail) if detail else ''}")
        failed += 1


def _reset_db():
    """重置成乾淨狀態，方便各 test 獨立運作。"""
    global DB_PATH
    os.remove(DB_PATH)
    _t = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    DB_PATH = _t.name
    _t.close()
    os.environ["SME_DB_PATH"] = DB_PATH
    server.DB_PATH = DB_PATH
    server.init_db()


# ============================================================
# Bug #1: FK 不應指向 _customers_migrate / _orders_migrate
# ============================================================

print("\n=== Bug #1: FK survives init_db (rename dance) ===")

# 跑兩次 init_db 模擬 server restart 情境
server.init_db()
server.init_db()

db = server.get_db()
for tbl in ("orders", "transactions", "customer_entity_terms"):
    row = db.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (tbl,)
    ).fetchone()
    sql = row["sql"] if row else ""
    _assert(
        f"Bug #1: {tbl} FK not pointing to _customers_migrate",
        "_customers_migrate" not in sql,
        f"sql: {sql[:200]}",
    )
    _assert(
        f"Bug #1: {tbl} FK not pointing to _orders_migrate",
        "_orders_migrate" not in sql,
        f"sql: {sql[:200]}",
    )
db.close()

# One-shot repair：手動建一個「壞」的 orders schema，模擬舊 DB
_reset_db()
db = server.get_db()
db.execute("PRAGMA foreign_keys=OFF")
db.execute("DROP TABLE orders")
db.execute("""CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER REFERENCES _customers_migrate(id),
    status TEXT DEFAULT 'pending',
    total_amount REAL DEFAULT 0,
    items TEXT,
    business_unit TEXT,
    notes TEXT,
    payment_terms TEXT,
    discount_applied REAL DEFAULT 0,
    qc_status TEXT DEFAULT 'pending',
    qc_notes TEXT,
    qc_checked_by TEXT,
    qc_checked_at DATETIME,
    driver TEXT,
    estimated_delivery TEXT,
    delivered_at DATETIME,
    created_by TEXT,
    created_at DATETIME DEFAULT (datetime('now','localtime')),
    updated_at DATETIME DEFAULT (datetime('now','localtime'))
)""")
db.commit()
db.close()

# 再跑 init_db 應自動修復
server.init_db()

db = server.get_db()
sql = db.execute(
    "SELECT sql FROM sqlite_master WHERE type='table' AND name='orders'"
).fetchone()["sql"]
db.close()
_assert(
    "Bug #1: one-shot repair fixed stale FK",
    "_customers_migrate" not in sql and "customers(id)" in sql,
    f"post-repair sql: {sql[:300]}",
)

# 修完後 create_order 應可成功
_reset_db()
server.add_customer(name="Test Co", type="customer")
# 先建 SKU
server.update_stock(sku="T-001", quantity_change=10, name="Test", sell_price=100, unit_cost=50)
r = server.create_order(
    customer_id=1,
    items_json='[{"sku":"T-001","name":"Test","qty":1,"price":100}]',
    business_unit="",
)
_assert("Bug #1: create_order works after init_db", "訂單 #" in r, r[:200])


# ============================================================
# Bug #2: customers 累計欄位維護
# ============================================================

print("\n=== Bug #2: customers sales aggregates ===")

_reset_db()
server.add_customer(name="Acme Co", type="customer", payment_terms="net30")
server.update_stock(sku="A-001", quantity_change=100, name="Widget", sell_price=1000, unit_cost=500)

# create_order → total_ordered += 3000, last_order_date 設
items_json = '[{"sku":"A-001","name":"Widget","qty":3,"price":1000}]'
r = server.create_order(customer_id=1, items_json=items_json, created_by="test")

db = server.get_db()
c = db.execute("SELECT * FROM customers WHERE id=1").fetchone()
db.close()
_assert("Bug #2 create_order: total_ordered updated", c["total_ordered"] == 3000, f"got {c['total_ordered']}")
_assert("Bug #2 create_order: last_order_date set", bool(c["last_order_date"]), f"got {c['last_order_date']}")
_assert("Bug #2 create_order: total_fulfilled still 0", (c["total_fulfilled"] or 0) == 0)

# confirm → qc pass → fulfill
order_id = db.execute("SELECT id FROM orders ORDER BY id LIMIT 1").fetchone() if False else 1
import sqlite3 as _sq
# Refetch order_id
with server.get_db() as _d:
    order_id = _d.execute("SELECT id FROM orders ORDER BY id LIMIT 1").fetchone()["id"]

server.update_order(order_id=order_id, status="confirmed")
server.qc_order(order_id=order_id, result="passed", checked_by="QC")
server.fulfill_order(order_id=order_id)

db = server.get_db()
c = db.execute("SELECT * FROM customers WHERE id=1").fetchone()
db.close()
_assert("Bug #2 fulfill_order: total_fulfilled updated", c["total_fulfilled"] == 3000, f"got {c['total_fulfilled']}")
_assert("Bug #2 fulfill_order: total_purchases updated (backward-compat)", c["total_purchases"] == 3000, f"got {c['total_purchases']}")
_assert("Bug #2 fulfill_order: last_fulfilled_date set", bool(c["last_fulfilled_date"]))
_assert("Bug #2 fulfill_order: last_purchase_date set (backward-compat)", bool(c["last_purchase_date"]))

# record_payment → total_paid 累加
db = server.get_db()
txn = db.execute("SELECT id FROM transactions WHERE related_order_id=? AND type='income'", (order_id,)).fetchone()
db.close()
server.record_payment(transaction_id=txn["id"], amount=3000, notes="")

db = server.get_db()
c = db.execute("SELECT * FROM customers WHERE id=1").fetchone()
db.close()
_assert("Bug #2 record_payment: total_paid updated", c["total_paid"] == 3000, f"got {c['total_paid']}")
_assert("Bug #2 record_payment: last_payment_date set", bool(c["last_payment_date"]))

# cancel_order (已出貨) → 反扣 total_fulfilled + total_ordered
server.cancel_order(order_id=order_id, reason="test cancel")

db = server.get_db()
c = db.execute("SELECT * FROM customers WHERE id=1").fetchone()
db.close()
_assert("Bug #2 cancel_order: total_fulfilled reversed", c["total_fulfilled"] == 0, f"got {c['total_fulfilled']}")
_assert("Bug #2 cancel_order: total_purchases reversed", c["total_purchases"] == 0, f"got {c['total_purchases']}")
_assert("Bug #2 cancel_order: total_ordered reversed", c["total_ordered"] == 0, f"got {c['total_ordered']}")


# ============================================================
# Bug #3: update_rule UNIQUE constraint
# ============================================================

print("\n=== Bug #3: update_rule repeatable ===")

_reset_db()
server.store_fact(
    category="hr",
    title="test rule",
    content="version 1",
    source_type="explicit",
    source_quote="原話 1",
    set_by="老闆",
)

# 應該可以連續呼叫 update_rule 多次不撞 UNIQUE
r1 = server.update_rule(rule_id=1, new_content="version 2", reason="第一次更新")
_assert("Bug #3: first update_rule success", "已更新" in r1, r1[:200])

# 找到剛新建的 rule id（#1 已 superseded）
db = server.get_db()
latest = db.execute(
    "SELECT id FROM business_rules WHERE category='hr' AND title='test rule' "
    "AND superseded_by IS NULL"
).fetchone()
db.close()
_assert("Bug #3: new active rule exists after first update", latest is not None)

r2 = server.update_rule(rule_id=latest["id"], new_content="version 3", reason="第二次更新")
_assert("Bug #3: second update_rule success", "已更新" in r2, r2[:200])

db = server.get_db()
latest2 = db.execute(
    "SELECT id FROM business_rules WHERE category='hr' AND title='test rule' "
    "AND superseded_by IS NULL"
).fetchone()
active_count = db.execute(
    "SELECT COUNT(*) c FROM business_rules WHERE category='hr' AND title='test rule' "
    "AND superseded_by IS NULL"
).fetchone()["c"]
db.close()
_assert("Bug #3: only one active rule at a time", active_count == 1, f"got {active_count}")
_assert(
    "Bug #3: latest rule has version 3 content",
    db.execute("SELECT content FROM business_rules WHERE id=?", (latest2["id"],)) if False
    else True,  # placeholder
)
# Re-check content (with new connection since closed above)
db = server.get_db()
content = db.execute("SELECT content FROM business_rules WHERE id=?", (latest2["id"],)).fetchone()["content"]
db.close()
_assert("Bug #3: latest content is version 3", content == "version 3", f"got: {content[:50]}")


# ============================================================
# Bug #4: inventory.reserved flow
# ============================================================

print("\n=== Bug #4: inventory.reserved ===")

_reset_db()
server.add_customer(name="Buyer", type="customer", payment_terms="net30")
server.update_stock(sku="R-001", quantity_change=10, name="Reservable", sell_price=500, unit_cost=200, business_unit="test-bu")

# create_order → reserved +3
server.create_order(
    customer_id=1,
    items_json='[{"sku":"R-001","name":"Reservable","qty":3,"price":500}]',
    business_unit="test-bu",
    created_by="tester",
)

db = server.get_db()
inv = db.execute("SELECT * FROM inventory WHERE sku='R-001'").fetchone()
db.close()
_assert("Bug #4 create_order: current_stock unchanged", inv["current_stock"] == 10, f"got {inv['current_stock']}")
_assert("Bug #4 create_order: reserved = 3", inv["reserved"] == 3, f"got {inv['reserved']}")

# fulfill → current_stock -3, reserved -3
with server.get_db() as _d:
    order_id = _d.execute("SELECT id FROM orders ORDER BY id LIMIT 1").fetchone()["id"]
server.update_order(order_id=order_id, status="confirmed")
server.qc_order(order_id=order_id, result="passed", checked_by="QC")
server.fulfill_order(order_id=order_id)

db = server.get_db()
inv = db.execute("SELECT * FROM inventory WHERE sku='R-001'").fetchone()
db.close()
_assert("Bug #4 fulfill_order: current_stock -3 → 7", inv["current_stock"] == 7, f"got {inv['current_stock']}")
_assert("Bug #4 fulfill_order: reserved released to 0", inv["reserved"] == 0, f"got {inv['reserved']}")

# 再下單、但不 fulfill 就 cancel → reserved 必須釋放
server.create_order(
    customer_id=1,
    items_json='[{"sku":"R-001","name":"Reservable","qty":2,"price":500}]',
    business_unit="test-bu",
)
db = server.get_db()
inv = db.execute("SELECT * FROM inventory WHERE sku='R-001'").fetchone()
order2_id = db.execute("SELECT id FROM orders ORDER BY id DESC LIMIT 1").fetchone()["id"]
db.close()
_assert("Bug #4 second order: reserved = 2", inv["reserved"] == 2, f"got {inv['reserved']}")

server.cancel_order(order_id=order2_id, reason="test cancel pending order")

db = server.get_db()
inv = db.execute("SELECT * FROM inventory WHERE sku='R-001'").fetchone()
db.close()
_assert("Bug #4 cancel pending: reserved released to 0", inv["reserved"] == 0, f"got {inv['reserved']}")
_assert("Bug #4 cancel pending: current_stock unchanged (7)", inv["current_stock"] == 7, f"got {inv['current_stock']}")


# ============================================================
# Bug #5: update_stock quantity_change=0 允許建 SKU
# ============================================================

print("\n=== Bug #5: update_stock quantity_change=0 ===")

_reset_db()
r = server.update_stock(sku="ZERO-001", quantity_change=0, name="Zero Stock SKU", sell_price=1200)
_assert("Bug #5: quantity_change=0 creates SKU", "新建品項" in r and "ZERO-001" in r, r[:200])

db = server.get_db()
inv = db.execute("SELECT * FROM inventory WHERE sku='ZERO-001'").fetchone()
db.close()
_assert("Bug #5: created SKU has current_stock=0", inv is not None and inv["current_stock"] == 0, f"got {inv}")
_assert("Bug #5: created SKU has sell_price=1200", inv is not None and inv["sell_price"] == 1200)

# 負數仍應報錯
r = server.update_stock(sku="NEG-001", quantity_change=-5, name="Negative test")
_assert("Bug #5: quantity_change=-5 still rejected for new SKU", "ERROR" in r, r[:200])


# ============================================================
# Obs #6: customers.primary_business_unit
# ============================================================

print("\n=== Obs #6: primary_business_unit ===")

_reset_db()
server.register_business_entity(entity_id="brand_a", name="品牌 A 我要生活")
server.register_business_entity(entity_id="brand_c", name="品牌 C 家具")

# add_customer 帶 primary_business_unit
server.add_customer(name="D2C Xiaoming", type="customer", primary_business_unit="brand_a")
server.add_customer(name="B2B 傢具行", type="customer", primary_business_unit="brand_c")

# find_customer 應該在輸出顯示 [brand_a] / [brand_c]
r = server.find_customer(query="D2C")
_assert("Obs #6: find_customer shows [brand_a] label", "[brand_a]" in r, r[:300])

r = server.find_customer(query="傢具行")
_assert("Obs #6: find_customer shows [brand_c] label", "[brand_c]" in r, r[:300])

# update_customer 切換 BU
server.update_customer(customer_id=1, primary_business_unit="brand_c")
db = server.get_db()
c = db.execute("SELECT primary_business_unit FROM customers WHERE id=1").fetchone()
db.close()
_assert("Obs #6: update_customer switches BU", c["primary_business_unit"] == "brand_c", f"got {c['primary_business_unit']}")

# 清除 BU（傳空字串）
server.update_customer(customer_id=1, primary_business_unit="")
db = server.get_db()
c = db.execute("SELECT primary_business_unit FROM customers WHERE id=1").fetchone()
db.close()
_assert("Obs #6: update_customer clears BU with empty string", c["primary_business_unit"] is None, f"got {c['primary_business_unit']}")


# ============================================================
# Bug #8: _get_approval_threshold handles negative sentinel
# ============================================================

print("\n=== Bug #8: approval_threshold=-1 fallback to company ===")

_reset_db()
# 公司門檻 = 9999999（視為無門檻）
db = server.get_db()
db.execute("INSERT INTO company (id, name, industry, boss_name, approval_threshold) VALUES (1, 'Test', 'retail', '老闆', 9999999)")
db.commit()
db.close()

server.register_business_entity(entity_id="brand_c", name="BRAND_C")
# 直接把 threshold 寫成 -1，模擬舊 DB
db = server.get_db()
db.execute("UPDATE business_entities SET approval_threshold=-1 WHERE id='brand_c'")
db.commit()
db.close()

# 重跑 init_db，one-shot 應該把 -1 清成 NULL
server.init_db()

db = server.get_db()
t = db.execute("SELECT approval_threshold FROM business_entities WHERE id='brand_c'").fetchone()
db.close()
_assert("Bug #8: one-shot cleaned negative threshold to NULL",
        t["approval_threshold"] is None, f"got {t['approval_threshold']}")

# record_transaction 不應觸發審核（因為 fallback 到 company=9999999）
server.add_customer(name="Test C", type="customer")
r = server.record_transaction(
    type="expense", amount=10000, category="inventory_purchase",
    description="test expense", business_unit="brand_c",
)
_assert("Bug #8: record_transaction NT$10,000 passes threshold (company fallback)",
        "帳目 #" in r and "超過審核門檻" not in r, r[:200])


# ============================================================
# Obs #7: update_stock modifies metadata for existing SKUs
# ============================================================

print("\n=== Obs #7: update_stock updates metadata ===")

_reset_db()
# 建一個 SKU
server.update_stock(sku="META-001", quantity_change=10, name="Meta Test", sell_price=100, unit_cost=50, min_stock=2)

# 用 update_stock 修改既有 SKU 的 metadata
server.update_stock(sku="META-001", quantity_change=0, sell_price=150, unit_cost=80, min_stock=5, reason="調價調安全庫存")

db = server.get_db()
inv = db.execute("SELECT sell_price, unit_cost, min_stock FROM inventory WHERE sku='META-001'").fetchone()
db.close()
_assert("Obs #7: sell_price updated 100 → 150", inv["sell_price"] == 150, f"got {inv['sell_price']}")
_assert("Obs #7: unit_cost updated 50 → 80", inv["unit_cost"] == 80, f"got {inv['unit_cost']}")
_assert("Obs #7: min_stock updated 2 → 5", inv["min_stock"] == 5, f"got {inv['min_stock']}")


# ============================================================
# line_groups.purpose: 群組功能描述欄位
# ============================================================

print("\n=== line_groups.purpose ===")

_reset_db()

r = server.register_line_group(
    group_id="CTEST123",
    group_name="品牌 C內勤",
    group_type="work",
    channel_id="brand_c",
    purpose="協調訂單/庫存/客訴的日常工作",
    notes="成員：老闆、戴戴、陳春妙",
)
_assert("purpose: register with purpose includes purpose in return",
        "協調訂單" in r, r[:300])

r = server.list_line_groups(channel_id="brand_c")
_assert("purpose: list_line_groups shows purpose", "功能：協調訂單" in r, r[:300])
_assert("purpose: list_line_groups shows notes separately", "備註：成員：老闆" in r, r[:300])

# update purpose via re-register
server.register_line_group(
    group_id="CTEST123",
    group_type="work",
    channel_id="brand_c",
    purpose="改為專責庫存警報和補貨排程",
)
r = server.list_line_groups(channel_id="brand_c")
_assert("purpose: update via re-register", "庫存警報" in r, r[:300])

# 沒給 purpose 時應保留既有值（COALESCE(NULLIF(?, ''), purpose)）
server.register_line_group(
    group_id="CTEST123",
    group_type="work",
    channel_id="brand_c",
)  # 空 purpose
r = server.list_line_groups(channel_id="brand_c")
_assert("purpose: empty string in update preserves existing value",
        "庫存警報" in r, r[:300])


# ============================================================
# external_partners: register / update / list / find
# ============================================================

print("\n=== external_partners CRUD ===")

_reset_db()
# Register
r = server.register_partner(
    name="Test 外包夥伴",
    role="影片剪輯",
    phone="0900-000-001",
    business_units="brand_e,brand_a,brand_c",
    payment_terms="案件計酬",
)
_assert("partners: register success", "已註冊" in r and "#1" in r, r[:200])

# 再 register 一個
server.register_partner(name="Bonny 社群", role="社群發布", business_units="brand_e,brand_a")
server.register_partner(name="Ken 攝影師", role="外景拍攝")

# list active only
r = server.list_partners(active_only=True)
_assert("partners: list active", "3 位" in r or "3位" in r, r[:300])

# 依 role 篩選
r = server.list_partners(role="剪輯")
_assert("partners: filter by role", "Ray" in r and "Bonny" not in r, r[:200])

# find by name
r = server.find_partner("Bonny")
_assert("partners: find by name", "Bonny" in r and "社群" in r, r[:200])

# update — 綁 LINE user_id + 停用
server.update_partner(partner_id=3, line_user_id="U" + "k" * 32, phone="0923-000-000")
server.update_partner(partner_id=2, active=0)

r = server.list_partners(active_only=True)
_assert("partners: inactive hidden when active_only=True", "Bonny" not in r, r[:200])

r = server.list_partners(active_only=False)
_assert("partners: inactive shown when active_only=False", "Bonny" in r, r[:200])

r = server.find_partner("U" + "k" * 32)
_assert("partners: find by line_user_id", "Ken" in r, r[:200])

# sanity: Ken's line_user_id 正確寫入
db = server.get_db()
p = db.execute("SELECT line_user_id FROM external_partners WHERE name='Ken 攝影師'").fetchone()
db.close()
_assert("partners: line_user_id saved correctly",
        p["line_user_id"] == "U" + "k" * 32, f"got {p['line_user_id']}")


# ============================================================
# Summary
# ============================================================

print("\n" + "=" * 50)
print(f"Results: {passed} passed, {failed} failed out of {passed + failed}")
if failed:
    print("SOME TESTS FAILED ❌")
    sys.exit(1)
else:
    print("ALL TESTS PASSED ✅")
    sys.exit(0)
