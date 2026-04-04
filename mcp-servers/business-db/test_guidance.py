"""Test tool return guidance for three-layer defense architecture."""
import sys, os, json, sqlite3

sys.path.insert(0, os.path.dirname(__file__))

# Patch DB path to use temp DB
import tempfile
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
DB_PATH = _tmp.name
_tmp.close()

os.environ["SME_DB_PATH"] = DB_PATH

import server  # noqa: E402

# Re-init with temp DB
server.DB_PATH = DB_PATH
server.init_db()

# === Setup test data ===
db = server.get_db()
db.execute("INSERT INTO company (id, name, industry, boss_name, approval_threshold) VALUES (1, 'Test Corp', 'retail', 'Boss', 5000)")
db.execute("INSERT INTO customers (id, name, type, payment_terms, discount_rate) VALUES (1, '好好生活', 'distributor', 'net30', 0.15)")
db.execute("INSERT INTO customers (id, name, type, payment_terms, discount_rate) VALUES (2, '預付客戶', 'customer', 'prepaid', 0)")
db.execute("INSERT INTO inventory (sku, name, current_stock, min_stock, unit, unit_cost, sell_price) VALUES ('WIA-001', '香氛蠟燭', 50, 20, '個', 200, 500)")
db.execute("INSERT INTO inventory (sku, name, current_stock, min_stock, unit, unit_cost, sell_price) VALUES ('WIA-002', '擴香瓶', 5, 10, '個', 100, 300)")
db.commit()
db.close()

passed = 0
failed = 0

def check(name, result, *keywords):
    global passed, failed
    ok = all(kw in result for kw in keywords)
    status = "✅" if ok else "❌"
    print(f"{status} {name}")
    if not ok:
        for kw in keywords:
            if kw not in result:
                print(f"   Missing: '{kw}'")
        print(f"   Result:\n{result[:500]}\n")
        failed += 1
    else:
        passed += 1


# === Test 1: create_order with payment terms guidance ===
print("\n=== Test 1: create_order guidance ===")
items = json.dumps([{"sku": "WIA-001", "name": "香氛蠟燭", "qty": 10, "price": 425}])
result = server.create_order(customer_id=1, items_json=items, created_by="test")
check("create_order has next_steps", result, "👉 下一步")
check("create_order mentions payment terms", result, "net30")
check("create_order mentions update_order confirmed", result, "update_order", "confirmed")
check("create_order mentions LINE notify", result, "LINE 通知")
check("create_order warns about discount", result, "15%", "折扣")

# Threshold test
items_big = json.dumps([{"sku": "WIA-001", "name": "香氛蠟燭", "qty": 20, "price": 500}])
result2 = server.create_order(customer_id=1, items_json=items_big, created_by="test")
check("create_order threshold warning", result2, "審核門檻", "create_approval")


# === Test 2: qc_order guidance ===
print("\n=== Test 2: qc_order guidance ===")
# Get the first order ID
db = server.get_db()
order = db.execute("SELECT id FROM orders ORDER BY id LIMIT 1").fetchone()
db.close()
order_id = order["id"]

result = server.qc_order(order_id=order_id, result="passed", checked_by="QC員")
check("qc_order passed has fulfill_order call", result, f"fulfill_order(order_id={order_id})")

result = server.qc_order(order_id=order_id, result="failed", notes="外觀瑕疵", checked_by="QC員")
check("qc_order failed has next_steps", result, "通知主管", "LINE")


# === Test 3: fulfill_order guidance ===
print("\n=== Test 3: fulfill_order guidance ===")
# Reset QC to passed for fulfill
db = server.get_db()
db.execute("UPDATE orders SET qc_status = 'passed', status = 'confirmed' WHERE id = ?", (order_id,))
db.commit()
db.close()

result = server.fulfill_order(order_id=order_id)
check("fulfill_order has auto_completed", result, "📋 已自動完成")
check("fulfill_order mentions stock deducted", result, "庫存已扣減")
check("fulfill_order mentions receivable", result, "應收帳款")
check("fulfill_order has next_steps", result, "👉 下一步")
check("fulfill_order mentions update_order shipped", result, "update_order", "driver")
check("fulfill_order mentions LINE notify", result, "LINE 通知")
check("fulfill_order has warnings", result, "不要再手動 update_stock", "不要再手動 record_transaction")
# WIA-002 had 5 stock, min_stock 10, but was not in this order. WIA-001 had 50-10=40, min_stock 20, should be ok.
# Actually WIA-001 50-10=40 > 20, no alert expected for it.


# === Test 4: update_stock incoming guidance ===
print("\n=== Test 4: update_stock guidance ===")
result = server.update_stock(sku="WIA-001", quantity_change=20, reason="進貨")
check("update_stock incoming has next_steps", result, "👉 下一步")
check("update_stock incoming mentions record_transaction", result, "record_transaction", "inventory_purchase")
check("update_stock incoming mentions amount", result, "4000")  # 20 * 200

# New item creation
result = server.update_stock(sku="NEW-001", quantity_change=10, reason="新品", name="新商品", unit_cost=150, unit="組")
check("update_stock new item has guidance", result, "👉 下一步", "record_transaction")
check("update_stock new item mentions cost", result, "1500")  # 10 * 150


# === Test 5: record_transaction threshold block guidance ===
print("\n=== Test 5: record_transaction threshold guidance ===")
result = server.record_transaction(type="expense", amount=8000, category="inventory_purchase", description="大筆進貨")
check("record_transaction blocked has guidance", result, "👉 下一步", "create_approval")
check("record_transaction blocked has structured detail", result, "resume_action")

# Success with related order
result = server.record_transaction(type="income", amount=500, category="sales_revenue", related_order_id=order_id, payment_status="paid")
# Order already shipped, this is a partial payment
check("record_transaction success with order", result, "✅")


# === Test 6: resolve_approval with structured detail ===
print("\n=== Test 6: resolve_approval guidance ===")
detail = json.dumps({
    "resume_action": "record_transaction",
    "resume_params": {"type": "expense", "amount": 8000, "category": "inventory_purchase"},
    "then": "記帳完成後通知採購人員",
}, ensure_ascii=False)
# Create approval
result = server.create_approval(type="expense", summary="進貨 NT$8,000", detail=detail)
# Extract approval ID
import re
match = re.search(r"#(\d+)", result)
approval_id = int(match.group(1))

result = server.resolve_approval(approval_id=approval_id, decision="approved", decided_by="Boss")
check("resolve_approval has original summary", result, "進貨 NT$8,000")
check("resolve_approval has resume action", result, "record_transaction")
check("resolve_approval has next_steps", result, "👉 下一步")
check("resolve_approval has then step", result, "記帳完成後通知採購人員")


# === Test 7: record_payment guidance ===
print("\n=== Test 7: record_payment guidance ===")
# Find the receivable from fulfill_order
db = server.get_db()
txn = db.execute("SELECT id, amount FROM transactions WHERE related_order_id = ? AND payment_status = 'pending' LIMIT 1", (order_id,)).fetchone()
db.close()
if txn:
    # Full payment
    result = server.record_payment(transaction_id=txn["id"], amount=txn["amount"])
    check("record_payment full has guidance", result, "👉 下一步")
    check("record_payment full mentions update_order paid", result, "update_order", "paid")


# === Test 8: get_context_summary with order hints ===
print("\n=== Test 8: get_context_summary order hints ===")
# Create an order stuck in confirmed + qc pending
items = json.dumps([{"sku": "WIA-001", "name": "香氛蠟燭", "qty": 2, "price": 425}])
server.create_order(customer_id=1, items_json=items, created_by="test")
db = server.get_db()
new_order = db.execute("SELECT id FROM orders ORDER BY id DESC LIMIT 1").fetchone()
db.execute("UPDATE orders SET status = 'confirmed' WHERE id = ?", (new_order["id"],))
db.commit()
db.close()

result = server.get_context_summary(scope="full")
check("context_summary has order hints", result, "qc_order")
check("context_summary shows pending orders", result, "進行中訂單")


# === Test 9: find_customer shows payment_terms ===
print("\n=== Test 9: find_customer display ===")
result = server.find_customer(query="預付")
check("find_customer shows prepaid", result, "📄prepaid")

result = server.find_customer(query="好好")
check("find_customer shows discount", result, "🏷️15%off")


# === Test 10: fulfill_order with low stock alert ===
print("\n=== Test 10: fulfill_order low stock alert ===")
# WIA-002 has 5 stock, min_stock 10 — ordering 3 should trigger alert (5-3=2 < 10)
items = json.dumps([{"sku": "WIA-002", "name": "擴香瓶", "qty": 3, "price": 300}])
server.create_order(customer_id=1, items_json=items, created_by="test")
db = server.get_db()
low_order = db.execute("SELECT id FROM orders ORDER BY id DESC LIMIT 1").fetchone()
db.execute("UPDATE orders SET status = 'confirmed', qc_status = 'passed' WHERE id = ?", (low_order["id"],))
db.commit()
db.close()
result = server.fulfill_order(order_id=low_order["id"])
check("fulfill_order low stock alert", result, "庫存警報", "擴香瓶")


# === Test 11: resolve_approval rejected path ===
print("\n=== Test 11: resolve_approval rejected ===")
detail = json.dumps({"resume_action": "record_transaction", "resume_params": {"amount": 5000}}, ensure_ascii=False)
result = server.create_approval(type="expense", summary="測試駁回", detail=detail)
match = re.search(r"#(\d+)", result)
rej_id = int(match.group(1))
result = server.resolve_approval(approval_id=rej_id, decision="rejected", decided_by="Boss")
check("resolve_approval rejected has icon", result, "❌")
check("resolve_approval rejected has summary", result, "測試駁回")
check("resolve_approval rejected has original detail", result, "原始請求")


# === Test 12: resolve_approval with plain text detail ===
print("\n=== Test 12: resolve_approval plain text detail ===")
result = server.create_approval(type="purchase", summary="普通採購", detail="這是純文字備註不是JSON")
match = re.search(r"#(\d+)", result)
plain_id = int(match.group(1))
result = server.resolve_approval(approval_id=plain_id, decision="approved", decided_by="Boss")
check("resolve_approval plain text has summary", result, "普通採購")
check("resolve_approval plain text shows detail", result, "這是純文字備註")


# === Test 13: update_stock new item without unit_cost ===
print("\n=== Test 13: update_stock no unit_cost ===")
result = server.update_stock(sku="NOUC-001", quantity_change=30, reason="無成本新品", name="試用品")
check("update_stock no cost has guidance", result, "下一步", "record_transaction")
check("update_stock no cost mentions confirm amount", result, "需確認進貨金額")


# === Test 14: create_order with prepaid customer ===
print("\n=== Test 14: create_order prepaid customer ===")
items = json.dumps([{"sku": "WIA-001", "name": "香氛蠟燭", "qty": 2, "price": 500}])
result = server.create_order(customer_id=2, items_json=items, created_by="test")
check("create_order prepaid has payment guidance", result, "prepaid")
check("create_order prepaid mentions 匯款", result, "匯款")


# === Test 15: record_payment partial ===
print("\n=== Test 15: record_payment partial ===")
# Find an unpaid transaction
db = server.get_db()
unpaid = db.execute(
    "SELECT id, amount, related_order_id FROM transactions WHERE payment_status = 'pending' AND amount > 100 LIMIT 1"
).fetchone()
db.close()
if unpaid:
    partial_amount = unpaid["amount"] * 0.5
    result = server.record_payment(transaction_id=unpaid["id"], amount=partial_amount)
    check("record_payment partial shows remaining", result, "剩餘")
    if unpaid["related_order_id"]:
        check("record_payment partial shows order remaining", result, "尚欠")


# === Summary ===
print(f"\n{'='*50}")
print(f"Results: {passed} passed, {failed} failed out of {passed + failed}")
if failed:
    print("SOME TESTS FAILED")
    sys.exit(1)
else:
    print("ALL TESTS PASSED ✅")

# Cleanup
os.unlink(DB_PATH)
