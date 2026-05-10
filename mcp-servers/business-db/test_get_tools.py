"""
測試新增的 5 個 get_X 單筆查詢工具：
get_task / get_customer / get_partner / get_transaction / get_rule

跟 list/find 視圖不同、這些 tool 必須回 description / source_quote / 關聯實體等完整欄位。

使用獨立的 tempfile DB、不動正式資料。

執行：cd mcp-servers/business-db && python3 test_get_tools.py
"""
import os
import re
import sys
import sqlite3
import tempfile

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
DB_PATH = _tmp.name
_tmp.close()
os.environ["SME_DB_PATH"] = DB_PATH

sys.path.insert(0, os.path.dirname(__file__))
import server  # noqa: E402
server.DB_PATH = DB_PATH
server.init_db()

passed = 0
failed = 0


def check(name: str, cond: bool, detail: str = ""):
    global passed, failed
    if cond:
        print(f"✅ {name}")
        passed += 1
    else:
        print(f"❌ {name}{('  → ' + detail) if detail else ''}")
        failed += 1


def extract_id(result: str) -> int:
    """從 register/create 工具的回傳訊息抓出 ID（pattern: #123）。"""
    m = re.search(r"#(\d+)", result)
    if not m:
        raise RuntimeError(f"找不到 ID：{result}")
    return int(m.group(1))


def extract_last_id(result: str) -> int:
    """抓回傳訊息中最後一個 #ID（用於 update_rule 這種「#舊 → #新」格式）。"""
    ids = re.findall(r"#(\d+)", result)
    if not ids:
        raise RuntimeError(f"找不到 ID：{result}")
    return int(ids[-1])


# 老闆指示：5 個 get_X 不能含 emoji、用純文字
EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF☀-➿]")


# ============================================================
# get_task
# ============================================================
print("\n=== get_task ===")

# 不存在 → ERROR
r = server.get_task(99999)
check("not_found returns ERROR", r.startswith("ERROR:") and "99999" in r, r)

# 建一個帶完整欄位的 task + 子任務
parent_id = extract_id(server.create_task(
    title="父任務 A",
    description="這是父任務的完整描述、含多行\n第二行內容",
    assignee="charlie",
    priority="urgent",
    category="meeting",
    tags="ig-launch,test",
    business_unit="dreamwalkr",
    due_date="2026-06-01",
    created_by="charlie",
))
child_id = extract_id(server.create_task(
    title="子任務 B",
    parent_task_id=parent_id,
    assignee="york",
    priority="normal",
))

# get_task 應回完整 description
out = server.get_task(parent_id)
check("description 全文出現", "這是父任務的完整描述" in out and "第二行內容" in out, out)
check("title 在 H2", f"任務 #{parent_id}" in out and "父任務 A" in out)
check("tags 顯示", "ig-launch,test" in out)
check("business_unit 顯示", "dreamwalkr" in out)
check("子任務區塊出現", f"#{child_id}" in out and "子任務 B" in out, out)
check("priority=urgent 顯示『急』", "急" in out, out[:300])
check("status 顯示中文+英文", "待處理" in out and "pending" in out, out[:300])

# 子任務應顯示父任務 reference
out_child = server.get_task(child_id)
check("子任務反向顯示父任務", f"父任務：[#{parent_id}]" in out_child and "父任務 A" in out_child, out_child)
check("get_task 不含 emoji", not EMOJI_RE.search(out), out[:400])
check("get_task (子) 不含 emoji", not EMOJI_RE.search(out_child), out_child[:400])


# ============================================================
# get_customer
# ============================================================
print("\n=== get_customer ===")

r = server.get_customer(99999)
check("not_found returns ERROR", r.startswith("ERROR:"))

cust_id = extract_id(server.add_customer(
    name="測試客戶 Alpha",
    type="customer",
    phone="0912000999",
    email="alpha@test.local",
    notes="這是備註全文、要被 get_customer 完整撈出",
    discount_rate=0.1,
    payment_terms="net30",
    primary_business_unit="dreamwalkr",
))

# 加一筆 entity_terms
server.set_customer_entity_terms(
    customer_id=cust_id,
    business_unit="brand_d",
    discount_rate=0.15,
    payment_terms="net60",
)

out = server.get_customer(cust_id)
check("notes 全文出現", "這是備註全文" in out, out)
check("name + 主事業體", "測試客戶 Alpha" in out and "dreamwalkr" in out)
check("customer H2 顯示『客戶』", f"客戶 #{cust_id}" in out, out[:200])
check("預設折扣 10%", "折扣 10%" in out, out)
check("entity_terms brand_d 折扣 15%", "brand_d" in out and "15%" in out, out)
check("LINE 未綁定提示", "未綁定" in out)

# Supplier H2 應顯示「供應商」、不是「客戶」（type-aware 標題）
sup_id = extract_id(server.add_customer(name="測試供應商 Beta", type="supplier", notes="代工夥伴"))
sup_out = server.get_customer(sup_id)
check("supplier H2 顯示『供應商』", f"供應商 #{sup_id}" in sup_out, sup_out[:200])

# Distributor H2 應顯示「經銷商」
dist_id = extract_id(server.add_customer(name="測試經銷商 Gamma", type="distributor"))
dist_out = server.get_customer(dist_id)
check("distributor H2 顯示『經銷商』", f"經銷商 #{dist_id}" in dist_out, dist_out[:200])

check("get_customer 不含 emoji", not EMOJI_RE.search(out), out[:400])
check("get_customer (supplier) 不含 emoji", not EMOJI_RE.search(sup_out), sup_out[:400])
check("get_customer (distributor) 不含 emoji", not EMOJI_RE.search(dist_out), dist_out[:400])

# discount_rate=NULL 防呆（NULL * 100 應被 `or 0` 防到、不 crash）
null_disc_id = extract_id(server.add_customer(name="無折扣客戶 Delta", type="customer"))
db = server.get_db()
db.execute("UPDATE customers SET discount_rate = NULL WHERE id = ?", (null_disc_id,))
db.commit()
db.close()
null_out = server.get_customer(null_disc_id)
check("discount_rate=NULL 不 crash", "折扣 0%" in null_out, null_out[:300])


# ============================================================
# get_partner
# ============================================================
print("\n=== get_partner ===")

r = server.get_partner(99999)
check("not_found returns ERROR", r.startswith("ERROR:"))

partner_id = extract_id(server.register_partner(
    name="剪輯師 Bob",
    role="影片後製",
    phone="0911000888",
    notes="長期合作、固定報酬",
    business_units="dreamwalkr",
))

out = server.get_partner(partner_id)
check("name + 角色", "剪輯師 Bob" in out and "影片後製" in out)
check("notes 全文", "長期合作、固定報酬" in out)
check("active 顯示啟用", "啟用" in out)
check("get_partner 不含 emoji", not EMOJI_RE.search(out), out[:400])


# ============================================================
# get_transaction
# ============================================================
print("\n=== get_transaction ===")

r = server.get_transaction(99999)
check("not_found returns ERROR", r.startswith("ERROR:"))

# Case 1: pending → record_payment 部分付款（驗 customers.total_paid 與 last_payment_date side effect）
txn_id = extract_id(server.record_transaction(
    type="income",
    amount=3000,
    category="sales_revenue",
    description="客戶 Alpha 訂金、含特殊條款",
    related_customer_id=cust_id,
    business_unit="dreamwalkr",
    payment_status="pending",
    due_date="2026-06-30",
    recorded_by="charlie",
))

# 透過 server.record_payment 走完整 flow（含 customers 累計欄位同步）
pay1 = server.record_payment(transaction_id=txn_id, amount=1500)
check("record_payment 部分付款成功", "ERROR" not in pay1, pay1)

# 驗 customers side effect
db = server.get_db()
cust_after = db.execute(
    "SELECT total_paid, last_payment_date FROM customers WHERE id = ?", (cust_id,)
).fetchone()
db.close()
check("客戶 total_paid 累計 = 1500", cust_after["total_paid"] == 1500, str(dict(cust_after)))
check("客戶 last_payment_date 已更新", bool(cust_after["last_payment_date"]))

# get_transaction 應顯示 pending + 部分付款數字 + H2 含 description summary
out = server.get_transaction(txn_id)
check("H2 含 description summary", f"帳目 #{txn_id}：客戶 Alpha 訂金" in out, out[:200])
check("description 全文", "客戶 Alpha 訂金、含特殊條款" in out)
check("關聯客戶名出現", "測試客戶 Alpha" in out, out)
check("pending 付款狀態 + 中文『待付』", "pending" in out and "待付" in out, out[:400])
check("已付 / 未付數字", "已付：NT$1,500" in out and "未付：NT$1,500" in out, out)
check("到期日", "2026-06-30" in out)
check("type 顯示『收入』", "收入" in out, out[:400])
check("get_transaction 不含 emoji", not EMOJI_RE.search(out), out[:400])

# Case 2: 結清 → record_payment 補完、status 應自動轉 paid
pay2 = server.record_payment(transaction_id=txn_id, amount=1500)
check("record_payment 結清成功", "ERROR" not in pay2, pay2)

out_paid = server.get_transaction(txn_id)
check("paid 付款狀態 + 中文『已付清』", "paid" in out_paid and "已付清" in out_paid, out_paid[:300])
check("結清後已付=全額/未付=0", "已付：NT$3,000" in out_paid and "未付：NT$0" in out_paid, out_paid[:300])

# 驗 customers.total_paid 累計到 3000
db = server.get_db()
final_total = db.execute("SELECT total_paid FROM customers WHERE id = ?", (cust_id,)).fetchone()["total_paid"]
db.close()
check("客戶 total_paid 結清後 = 3000", final_total == 3000, f"actual={final_total}")

# Case 3: overdue（建 pending、SQL update 改 overdue 模擬時間到期後的標記）
txn_overdue_id = extract_id(server.record_transaction(
    type="expense",
    amount=2000,
    category="rent",
    description="某月房租、未付",
    payment_status="pending",
    due_date="2026-01-01",
    recorded_by="charlie",
))
db = server.get_db()
db.execute("UPDATE transactions SET payment_status = 'overdue' WHERE id = ?", (txn_overdue_id,))
db.commit()
db.close()

out_overdue = server.get_transaction(txn_overdue_id)
check("overdue 付款狀態 + 中文『逾期』", "overdue" in out_overdue and "逾期" in out_overdue, out_overdue[:300])
check("type 顯示『支出』", "支出" in out_overdue, out_overdue[:400])
check("get_transaction (overdue) 不含 emoji", not EMOJI_RE.search(out_overdue), out_overdue[:400])


# ============================================================
# get_rule
# ============================================================
print("\n=== get_rule ===")

r = server.get_rule(99999)
check("not_found returns ERROR", r.startswith("ERROR:"))

rule_id = extract_id(server.store_fact(
    category="testing",
    title="測試規則 Foo",
    content="規則的完整內文、含 source_quote 引號「老闆原話」這種字。",
    source_type="explicit",
    source_quote="這是老闆原話、要被引號顯示",
    set_by="charlie",
))

out = server.get_rule(rule_id)
check("title 顯示", "測試規則 Foo" in out)
check("category 在標題", "[testing]" in out)
check("content 全文", "規則的完整內文" in out)
check("source_quote 引號顯示", "「這是老闆原話、要被引號顯示」" in out, out)
check("source_type explicit", "explicit" in out)
check("set_by 顯示", "charlie" in out)

# 取代鏈：用 update_rule 升版（回傳「#舊 → #新」、所以抓最後一個 ID）
new_id = extract_last_id(server.update_rule(
    rule_id=rule_id,
    new_content="升版後的內容",
    reason="測試取代鏈顯示",
))
old_out = server.get_rule(rule_id)
check("舊規則顯示『已被取代』", "已被取代" in old_out and f"#{new_id}" in old_out, old_out)

new_out = server.get_rule(new_id)
check("新規則顯示『取代了』", "取代了" in new_out and f"#{rule_id}" in new_out, new_out)
check("get_rule 不含 emoji", not EMOJI_RE.search(new_out), new_out[:400])
check("get_rule (舊) 不含 emoji", not EMOJI_RE.search(old_out), old_out[:400])


# ============================================================
# 收尾
# ============================================================
print(f"\n=== 結果：{passed} 通過 / {failed} 失敗 ===")
try:
    os.remove(DB_PATH)
except OSError:
    pass
sys.exit(0 if failed == 0 else 1)
