"""
P0 Smoke test — 涵蓋全部 61 個 MCP tool 的 happy path baseline。

目的：重構（Phase 1+）前後行為 diff 必須為 0。每動一刀都要跑這個檔案、全綠才下一步。

使用方式：
    cd mcp-servers/business-db
    python3 tests/test_smoke_all.py

設計：
- 沿用既有 test_bugfixes.py 的 tempfile + _assert pattern（不引入 pytest）
- 每個 tool 至少 1 個 happy path call
- 跨 module dependency 用拓撲順序 setup：company → employees → customers → partners → inventory → orders → transactions
- 跨 module 整合場景（建單→扣 stock→記帳）也涵蓋
"""
import atexit
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta

# Test DB
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
DB_PATH = _tmp.name
_tmp.close()
os.environ["SME_DB_PATH"] = DB_PATH

# 隔離 in-session push（test hygiene）：把 LINE_STATE_DIR 指向 throwaway 暫存目錄。
# enqueue_escalation 的 post-commit drain 會呼叫 inject_to_sessions、它讀 <LINE_STATE_DIR>/inject.token；
# 暫存目錄沒 token → 靜默 no-op，絕不連到 live ~/.claude/channels/line/broadcast.sock 污染真 session。
_TEST_STATE_DIR = tempfile.mkdtemp(prefix="sme-test-state-")
os.environ["LINE_STATE_DIR"] = _TEST_STATE_DIR
atexit.register(lambda: __import__("shutil").rmtree(_TEST_STATE_DIR, ignore_errors=True))


@atexit.register
def _cleanup():
    try:
        os.unlink(DB_PATH)
    except OSError:
        pass


# 從 tests/ 上一層 import server
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server  # noqa: E402

server.DB_PATH = DB_PATH
server.init_db()

# 相對日期（避免測試在不同日子跑會 drift）
TODAY = datetime.now().strftime("%Y-%m-%d")
PAST_DUE_DATE = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")


# === 測試框架 ===

passed = 0
failed = 0
failures: list[str] = []


def _assert(name: str, cond: bool, detail: str = ""):
    global passed, failed
    if cond:
        print(f"OK    {name}")
        passed += 1
    else:
        print(f"FAIL  {name}{('  → ' + detail) if detail else ''}")
        failed += 1
        failures.append(name)


def _has(s: str, *keywords: str) -> bool:
    return all(k in s for k in keywords)


def _section(title: str):
    print(f"\n=== {title} ===")


# === Seed data（拓撲順序 setup）===

_section("Setup seed data")

db = server.get_db()
db.execute("INSERT INTO company (id, name, industry, boss_name, approval_threshold) VALUES (1, 'Test Corp', 'retail', '老闆', 5000)")
db.commit()
row = db.execute("SELECT name FROM company WHERE id = 1").fetchone()
db.close()

_assert("seed: company row created", row and row[0] == "Test Corp")


# === 1. Knowledge module（9 tools）===

_section("Knowledge module")

r = server.store_fact("policy", "出貨流程", "出貨前必須先 QC", source_quote="老闆說 QC 沒過不能出")
_assert("store_fact: returns rule id", "規則" in r or "Rule" in r or "#" in r)

r = server.store_fact("policy", "付款條件", "預設 net30", source_quote="老闆說預設 30 天")
rule_id_2 = 2  # 第二條 rule

r = server.query_knowledge("出貨")
_assert("query_knowledge: finds stored rule", "出貨流程" in r or "QC" in r)

r = server.update_rule(1, "出貨前必須先 QC，且需主管簽核", reason="加簽核")
_assert("update_rule: success", "已更新" in r or "已取代" in r or "#" in r)

r = server.knowledge_changelog(days=1)
_assert("knowledge_changelog: shows recent changes", "更新" in r or "規則" in r or len(r) > 0)

r = server.lint_knowledge()
_assert("lint_knowledge: returns lint report", isinstance(r, str) and len(r) > 0)

r = server.link_rules(rule_id_2, 1, relation_type="related")
_assert("link_rules: success", "關聯" in r or "linked" in r.lower() or "#" in r)

# Codex P1.3 review fix: duplicate rule_relations insert 必須走過 sqlite3.IntegrityError 不爆 NameError
r = server.link_rules(rule_id_2, 1, relation_type="related")  # 重複 link
_assert("link_rules: duplicate relation handled (no NameError)",
        isinstance(r, str) and len(r) > 0,
        detail=r[:100])

r = server.get_rule(1)
_assert("get_rule: returns rule detail", "出貨" in r and "QC" in r)

r = server.get_rule_relations(1)
_assert("get_rule_relations: returns relations", "關聯" in r or "#" in r or "related" in r.lower())

r = server.log_decision("採 net30 為預設付款條件", reason="老闆指定")
_assert("log_decision: success", "已記錄" in r or "決策" in r or "#" in r)


# === 2. Context / interaction（2 tools）===

_section("Context / interaction")

r = server.get_context_summary("compact")
_assert("get_context_summary: returns summary", "Test Corp" in r or len(r) > 30)

r = server.log_interaction("Test User", "test_action", target_type="rule", target_id=1, detail="smoke test")
_assert("log_interaction: success", "已記錄" in r or "logged" in r.lower() or len(r) > 0)


# === 3. Tasks module（5 tools）===

_section("Tasks module")

r = server.create_task("採購咖啡豆", description="本週需 10 公斤", priority="normal")
_assert("create_task: returns task id", "任務" in r and "#" in r, detail=r[:200])

r = server.update_task(1, status="in_progress")
_assert("update_task: success", "已更新" in r or "in_progress" in r)

r = server.list_tasks()
_assert("list_tasks: returns task list", "採購" in r or "任務" in r)

r = server.search_tasks("咖啡")
_assert("search_tasks: finds matching task", "採購" in r or "咖啡" in r)

r = server.get_task(1)
_assert("get_task: returns task detail", "採購" in r and "10 公斤" in r)


# === 4. HR — employees（4 tools）===

_section("HR — employees")

r = server.register_employee("員工A", role="manager", department="業務部",
                              permissions="manager", phone="0912-000-001",
                              line_user_id="U_test_manager",
                              business_units="brand_a")
_assert("register_employee: success", "已建立" in r or "員工" in r and "#" in r)

r = server.register_employee("員工B", role="staff", department="倉管",
                              permissions="basic", phone="0912-000-002")
_assert("register_employee: second employee", "員工" in r and "#" in r)

r = server.update_employee(2, department="客服部")
_assert("update_employee: success", "已更新" in r and "department" in r)

r = server.lookup_employee("U_test_manager")
_assert("lookup_employee: by line_user_id", "員工A" in r)

r = server.list_employees()
_assert("list_employees: returns all", "員工A" in r and "員工B" in r)


# === 5. HR — partners（5 tools）===

_section("HR — partners")

r = server.register_partner("Ray 攝影", role="影片拍攝",
                             phone="0900-100-001", business_units="brand_a",
                             payment_terms="案件計酬")
_assert("register_partner: success", "夥伴" in r or "partner" in r.lower() or "#" in r)

r = server.register_partner("Bonny 剪輯", role="影片剪輯",
                             phone="0900-100-002", business_units="brand_a,brand_c")
_assert("register_partner: second partner", "#" in r)

r = server.update_partner(1, payment_terms="月結30")
_assert("update_partner: success", "已更新" in r or "更新" in r)

r = server.list_partners()
_assert("list_partners: returns all", "Ray" in r and "Bonny" in r)

r = server.find_partner("Ray")
_assert("find_partner: matches name", "Ray" in r and "影片拍攝" in r)

r = server.get_partner(1)
_assert("get_partner: returns detail", "Ray" in r and "0900-100-001" in r)


# === 6. CRM — customers（5 tools）===

_section("CRM — customers")

r = server.add_customer("好好生活", type="distributor",
                         phone="0987-654-321", line_user_id="U_test_cust1",
                         discount_rate=0.15, payment_terms="net30")
_assert("add_customer: success", "客戶" in r or "已建立" in r)

r = server.add_customer("早安咖啡", type="customer",
                         phone="0987-000-002", payment_terms="prepaid")
_assert("add_customer: second customer", "客戶" in r or "已建立" in r)

r = server.find_customer("好好")
_assert("find_customer: matches name", "好好生活" in r)

r = server.get_customer(1)
_assert("get_customer: returns detail",
        "好好生活" in r and ("0.15" in r or "15" in r or "折扣" in r))

r = server.update_customer(1, notes="V.I.P. 客戶")
_assert("update_customer: success", "已更新" in r)

r = server.register_business_entity("brand_a", "Test Brand A")
_assert("register_business_entity: prereq for entity terms", "事業體" in r or "已" in r)

r = server.set_customer_entity_terms(1, "brand_a", discount_rate=0.20, payment_terms="net45")
_assert("set_customer_entity_terms: success", "已設定" in r or "已更新" in r or "客戶" in r)


# === 7. LINE module（3 tools）===

_section("LINE module")

# search_line_messages: empty result OK
r = server.search_line_messages(query="test")
_assert("search_line_messages: empty result handled", "無" in r or "找到" in r or len(r) > 0)

r = server.register_line_group("C_test_group_001", group_name="測試工作群",
                                group_type="work", purpose="測試用")
_assert("register_line_group: success", "登錄" in r or "群組" in r or "#" in r)

r = server.list_line_groups()
_assert("list_line_groups: returns group", "測試工作群" in r or "test_group" in r)


# === 8. Inventory module（3 tools）===

_section("Inventory module")

r = server.update_stock("SKU-001", quantity_change=100, reason="進貨",
                         name="香氛蠟燭", sell_price=500, unit_cost=200,
                         min_stock=20, unit="個")
_assert("update_stock: create new SKU", "庫存" in r or "已" in r)

r = server.update_stock("SKU-002", quantity_change=5, reason="進貨",
                         name="擴香瓶", sell_price=300, unit_cost=100,
                         min_stock=10, unit="個")
_assert("update_stock: low-stock SKU", "庫存" in r or "已" in r)

r = server.check_stock("SKU-001")
_assert("check_stock: by sku", "100" in r and "香氛蠟燭" in r)

r = server.check_stock("擴香瓶")
_assert("check_stock: by name", "擴香瓶" in r)

r = server.low_stock_alerts()
_assert("low_stock_alerts: catches SKU-002 below min",
        "擴香瓶" in r or "SKU-002" in r)


# === 9. Approvals module（2 tools）===

_section("Approvals module")

r = server.create_approval(type="leave_request", summary="員工A 5/24 請特休",
                            detail='{"date":"2026-05-24","employee_id":1}',
                            approver="老闆", requester="員工A")
_assert("create_approval: success", "審核" in r or "approval" in r.lower() or "#" in r)

r = server.resolve_approval(approval_id=1, decision="approved", decided_by="老闆")
_assert("resolve_approval: success", "已" in r or "approved" in r.lower() or "核准" in r)


# === 10. Accounting module（8 tools）===

_section("Accounting module")

r = server.record_transaction(type="income", amount=1500, category="銷售",
                               description="現金銷售 SKU-001 x3",
                               business_unit="brand_a")
_assert("record_transaction: income", "已記錄" in r or "交易" in r or "#" in r)

r = server.record_transaction(type="expense", amount=300, category="進貨",
                               description="補貨")
_assert("record_transaction: expense", "已記錄" in r or "交易" in r or "#" in r)

r = server.record_transaction(type="income", amount=2000, category="銷售",
                               description="信用銷售 net30",
                               related_customer_id=1, payment_status="pending",
                               due_date=PAST_DUE_DATE)  # 相對：60 天前
_assert("record_transaction: pending for overdue test", "帳目" in r or "#" in r)

r = server.list_transactions(limit=10)
_assert("list_transactions: returns recent", "銷售" in r or "進貨" in r)

r = server.monthly_summary()
_assert("monthly_summary: returns numbers", "收入" in r or "支出" in r or "1500" in r)

r = server.get_transaction(1)
_assert("get_transaction: detail", "1500" in r or "銷售" in r)

r = server.update_transaction(1, description="現金銷售 SKU-001 x3（已更新）")
_assert("update_transaction: success", "已更新" in r)

r = server.check_overdue()
_assert("check_overdue: catches overdue txn",
        "逾期" in r or "好好生活" in r or "2000" in r)

r = server.record_payment(3, 2000, notes="入帳")
_assert("record_payment: success", "已" in r or "付款" in r or "收款" in r)

r = server.delete_transaction(2, reason="重複記帳")
_assert("delete_transaction: success", "已" in r or "刪除" in r or "已刪除" in r)


# === 11. Attachments module（2 tools）===

_section("Attachments module")

r = server.add_attachment(target_type="rule", target_id=1,
                           file_path="/tmp/test.pdf", file_name="出貨流程.pdf",
                           description="原文件")
_assert("add_attachment: success", "附件" in r or "#" in r or "已" in r)

r = server.list_attachments("rule", 1)
_assert("list_attachments: returns attachment", "出貨流程" in r or ".pdf" in r)


# === 12. Orders module（7 tools）===

_section("Orders module")

# Create order: customer #1 (好好生活), items: SKU-001 x2, SKU-002 x1
import json
items = json.dumps([
    {"sku": "SKU-001", "name": "香氛蠟燭", "qty": 2, "price": 500},
    {"sku": "SKU-002", "name": "擴香瓶", "qty": 1, "price": 300},
])
r = server.create_order(customer_id=1, items_json=items, business_unit="brand_a",
                         created_by="員工A")
_assert("create_order: success", "訂單" in r and "#" in r)

r = server.get_order(1)
_assert("get_order: returns detail",
        ("香氛蠟燭" in r or "SKU-001" in r) and ("好好生活" in r or "1300" in r or "1105" in r))

r = server.update_order(1, status="confirmed")
_assert("update_order: status confirmed", "已" in r or "confirmed" in r)

r = server.list_orders()
_assert("list_orders: includes new order", "好好生活" in r or "#1" in r or "SKU" in r)

r = server.qc_order(1, result="passed", notes="QC OK", checked_by="員工A")
_assert("qc_order: passed", "QC" in r or "passed" in r or "已" in r)

r = server.fulfill_order(1)
_assert("fulfill_order: ships order", "出貨" in r or "shipped" in r or "已" in r)

# Make a second order to test cancel
r2 = server.create_order(customer_id=2,
                          items_json=json.dumps([{"sku": "SKU-001", "name": "香氛蠟燭", "qty": 1, "price": 500}]),
                          business_unit="brand_a")
_assert("create_order: second for cancel test", "#" in r2)

r = server.cancel_order(2, reason="客戶取消")
_assert("cancel_order: success", "已取消" in r or "cancelled" in r or "取消" in r)


# === 13. Snapshots module（1 tool）===

_section("Snapshots module")

r = server.save_daily_snapshot()
_assert("save_daily_snapshot: success", "快照" in r or "snapshot" in r.lower() or "已" in r)


# === 14. Settings / company（4 tools）===

_section("Settings / company")

# get_setting 讀 settings category rule，不是 company 表
server.store_fact("settings", "primary_color", "#1A1A1A", source_quote="老闆說品牌色")
r = server.get_setting("primary_color")
_assert("get_setting: returns settings rule value", "#1A1A1A" in r)

r = server.update_company(industry="精品零售")
_assert("update_company: success", "已更新" in r or "更新" in r)

r = server.list_business_entities()
_assert("list_business_entities: returns brand_a", "brand_a" in r or "Test Brand A" in r)


# === 15. Session（1 tool）===

_section("Session handoff")

r = server.save_session_handoff("test_session_001",
                                  summary="## 目標\nP0 smoke test",
                                  pending_items='[{"item": "wrap up", "status": "pending"}]')
_assert("save_session_handoff: success", "已" in r or "handoff" in r.lower() or "session" in r.lower())

# resolve_handoff + active filter（避免 stale handoff trap）
import re as _re
_m = _re.search(r'#(\d+)', r)
_handoff_id = int(_m.group(1)) if _m else None
_assert("save_session_handoff: returns handoff_id in message", _handoff_id is not None,
        detail=f"got: {r!r}")

if _handoff_id:
    _summary_before = server.get_context_summary(scope='full')
    _assert("context_summary: shows active handoff",
            f"#{_handoff_id}" in _summary_before and "上次 Session 交接" in _summary_before,
            detail=f"handoff_id={_handoff_id} not visible")

    r2 = server.resolve_handoff(_handoff_id, note="smoke test resolve")
    _assert("resolve_handoff: success", "resolved" in r2)

    _summary_after = server.get_context_summary(scope='full')
    _assert("context_summary: hides resolved handoff",
            "上次 Session 交接" not in _summary_after,
            detail=f"resolved handoff still visible")

    r3 = server.resolve_handoff(_handoff_id)
    _assert("resolve_handoff: idempotent on already-resolved", "已是 resolved" in r3)

    r4 = server.resolve_handoff(999999)
    _assert("resolve_handoff: not found error", "ERROR" in r4 or "找不到" in r4)


# === 16. Cross-module integration（critical paths — 直接 query DB 驗副作用）===

_section("Cross-module integration（DB 副作用查驗）")

db = server.get_db()

# Stock：order #1（SKU-001 x2、SKU-002 x1）已 fulfill；order #2（SKU-001 x1）已 cancel
# Order cancel 釋放 reserved，fulfill 扣 current_stock
sku001 = db.execute(
    "SELECT current_stock, reserved FROM inventory WHERE sku = 'SKU-001'"
).fetchone()
_assert("integration: SKU-001 current_stock = 98（100 - 2 fulfilled）",
        sku001 and sku001["current_stock"] == 98,
        detail=f"got current_stock={sku001['current_stock'] if sku001 else None}")
_assert("integration: SKU-001 reserved = 0（cancel 釋放 + fulfill 扣完）",
        sku001 and sku001["reserved"] == 0,
        detail=f"got reserved={sku001['reserved'] if sku001 else None}")

sku002 = db.execute(
    "SELECT current_stock, reserved FROM inventory WHERE sku = 'SKU-002'"
).fetchone()
_assert("integration: SKU-002 current_stock = 4（5 - 1 fulfilled）",
        sku002 and sku002["current_stock"] == 4,
        detail=f"got current_stock={sku002['current_stock'] if sku002 else None}")

# Order #1 fulfilled / Order #2 cancelled
o1_status = db.execute("SELECT status FROM orders WHERE id = 1").fetchone()
_assert("integration: order #1 status fulfilled → 'shipped' or later",
        o1_status and o1_status["status"] in ("shipped", "delivered", "paid"),
        detail=f"got status={o1_status['status'] if o1_status else None}")

o2_status = db.execute("SELECT status FROM orders WHERE id = 2").fetchone()
_assert("integration: order #2 status = cancelled",
        o2_status and o2_status["status"] == "cancelled",
        detail=f"got status={o2_status['status'] if o2_status else None}")

# Customer #1 total_ordered/total_fulfilled 精確值：
# Order #1 SKU-001×2 ($500) + SKU-002×1 ($300) = $1300
# brand_a 折扣 0.20（set_customer_entity_terms 設）→ round(1300 * 0.80) = $1040
# Order #2 cancelled，不計入
EXPECTED_TOTAL = 1040
cust1 = db.execute(
    "SELECT total_ordered, total_fulfilled, primary_business_unit FROM customers WHERE id = 1"
).fetchone()
_assert(f"integration: customer #1 total_ordered == {EXPECTED_TOTAL}",
        cust1 and abs(cust1["total_ordered"] - EXPECTED_TOTAL) < 0.01,
        detail=f"got total_ordered={cust1['total_ordered'] if cust1 else None}")
_assert(f"integration: customer #1 total_fulfilled == {EXPECTED_TOTAL}",
        cust1 and abs(cust1["total_fulfilled"] - EXPECTED_TOTAL) < 0.01,
        detail=f"got total_fulfilled={cust1['total_fulfilled'] if cust1 else None}")

# 應收帳款驗證鏈：record_transaction pending → check_overdue 升 overdue → record_payment 結清
# 結清後 transactions.payment_status = 'paid'、paid_amount = amount
ar_pending = db.execute(
    "SELECT amount, paid_amount, payment_status FROM transactions WHERE related_customer_id = 1 AND amount = 2000"
).fetchone()
_assert("integration: AR transaction now paid after record_payment",
        ar_pending and ar_pending["payment_status"] == "paid"
        and abs(ar_pending["paid_amount"] - ar_pending["amount"]) < 0.01,
        detail=f"got status={ar_pending['payment_status'] if ar_pending else None}, "
               f"paid={ar_pending['paid_amount'] if ar_pending else None}")

db.close()


# === 17. Negative cases（補 codex review 提的負面測試）===

_section("Negative cases")

# 不存在的 id
r = server.get_task(99999)
_assert("negative: get_task non-existent id returns error",
        "找不到" in r or "ERROR" in r or "不存在" in r or "無" in r,
        detail=r[:100])

r = server.get_customer(99999)
_assert("negative: get_customer non-existent id",
        "找不到" in r or "ERROR" in r or "不存在" in r or "無" in r,
        detail=r[:100])

r = server.get_order(99999)
_assert("negative: get_order non-existent id",
        "找不到" in r or "ERROR" in r or "不存在" in r or "無" in r,
        detail=r[:100])

r = server.update_employee(99999, name="ghost")
_assert("negative: update_employee non-existent id",
        "找不到" in r or "ERROR" in r or "不存在" in r or "失敗" in r,
        detail=r[:100])

# Malformed items_json — 應該回 ERROR
r = server.create_order(customer_id=1, items_json="this is not json",
                         business_unit="brand_a")
_assert("negative: create_order malformed items_json returns ERROR",
        "ERROR" in r or "格式" in r,
        detail=r[:100])

# 庫存不足但金額未超門檻：SKU-002 庫存 5、訂 10 個、單價 300、total 3000 < 5000 門檻
# 應該能建單（lazy 驗證、reserved 會 over-allocate），但 fulfill 時應該擋
short_items_json = json.dumps([{"sku": "SKU-002", "name": "擴香瓶", "qty": 10, "price": 300}])
r = server.create_order(customer_id=1, items_json=short_items_json, business_unit="brand_a")
_assert("negative: create_order with short stock creates order (reserves lazy)",
        "#" in r, detail=r[:150])

# Financial tool nonexistent id
r = server.record_payment(99999, 100)
_assert("negative: record_payment non-existent txn",
        "ERROR" in r or "找不到" in r, detail=r[:100])

r = server.update_transaction(99999, description="ghost")
_assert("negative: update_transaction non-existent txn",
        "ERROR" in r or "找不到" in r, detail=r[:100])

r = server.delete_transaction(99999, reason="ghost")
_assert("negative: delete_transaction non-existent txn",
        "ERROR" in r or "找不到" in r, detail=r[:100])

# 非法 approval decision
r = server.resolve_approval(approval_id=1, decision="invalid_decision", decided_by="老闆")
_assert("negative: resolve_approval invalid decision",
        "ERROR" in r or "失敗" in r or "無效" in r or "不允許" in r or "approved" in r or "rejected" in r,
        detail=r[:100])

# update_order 非法 status transition（pending → shipped 應該擋）
db = server.get_db()
o3_pending = db.execute(
    "SELECT id FROM orders WHERE status = 'pending' LIMIT 1"
).fetchone()
db.close()
if o3_pending:
    r = server.update_order(o3_pending["id"], status="shipped")
    _assert("negative: update_order pending → shipped should be blocked",
            "失敗" in r or "ERROR" in r or "不允許" in r or "無法" in r or "pending" in r,
            detail=r[:100])


# === 請假管理（P3b leave management）===

_section("Leave management (P3b)")

# 1. 設定假別 — 需簽核（特休 + 事假）+ 不需簽核（生理假）
r = server.register_leave_type("annual", "特休", default_quota_days=14,
                                requires_approval=True, is_paid=True)
_assert("p3b: register_leave_type 特休", "已建立" in r and "annual" in r, detail=r[:200])

r = server.register_leave_type("personal", "事假", default_quota_days=14,
                                requires_approval=True, is_paid=False)
_assert("p3b: register_leave_type 事假", "已建立" in r, detail=r[:200])

r = server.register_leave_type("menstrual", "生理假", default_quota_days=12,
                                requires_approval=False, is_paid=True)
_assert("p3b: register_leave_type 生理假（不需簽核）",
        "已建立" in r and "不需簽核" in r, detail=r[:200])

# 重複 code 應擋
r = server.register_leave_type("annual", "特休", default_quota_days=10,
                                requires_approval=True, is_paid=True)
_assert("p3b: duplicate code blocked",
        "ERROR" in r and "已存在" in r, detail=r[:200])

# 2. 設定員工餘額（員工 #1 員工A — 在 hr 段建立）
r = server.set_leave_balance(employee_id=1, leave_type_code="annual",
                              year=2026, allocated_days=14)
_assert("p3b: set_leave_balance 特休 14 天",
        "已設為 14" in r, detail=r[:200])

r = server.set_leave_balance(employee_id=1, leave_type_code="personal",
                              year=2026, allocated_days=14)
_assert("p3b: set_leave_balance 事假 14 天", "已設為 14" in r, detail=r[:200])

r = server.set_leave_balance(employee_id=1, leave_type_code="menstrual",
                              year=2026, allocated_days=12)
_assert("p3b: set_leave_balance 生理假 12 天", "已設為 12" in r, detail=r[:200])

# 找不到員工 / 假別
r = server.set_leave_balance(employee_id=99999, leave_type_code="annual",
                              year=2026, allocated_days=5)
_assert("p3b: set_leave_balance non-existent employee blocked",
        "ERROR" in r and "找不到員工" in r, detail=r[:200])

r = server.set_leave_balance(employee_id=1, leave_type_code="not_exist",
                              year=2026, allocated_days=5)
_assert("p3b: set_leave_balance non-existent leave_type blocked",
        "ERROR" in r and "找不到假別" in r, detail=r[:200])

# 3. 請假申請（需簽核） → 建 approval
r = server.request_leave(employee_id=1, leave_type_code="annual",
                          start_date="2026-06-01", end_date="2026-06-03",
                          days=3, reason="家庭出遊")
_assert("p3b: request_leave 特休 3 天（建 approval）",
        "請假申請" in r and "對應簽核" in r, detail=r[:300])

# 抓 leave_request_id + approval_id
db = server.get_db()
lr_row = db.execute(
    "SELECT id, approval_id FROM leave_requests WHERE employee_id = 1 "
    "AND reason = '家庭出遊'"
).fetchone()
lr_id, lr_appr_id = lr_row[0], lr_row[1]
# 確認 leave_request 狀態 pending
status_row = db.execute(
    "SELECT status FROM leave_requests WHERE id = ?", (lr_id,)
).fetchone()
db.close()
_assert("p3b: leave_request status=pending",
        status_row[0] == "pending", detail=f"status={status_row[0]}")
_assert("p3b: leave_request 對應 approval_id 已設",
        lr_appr_id is not None and lr_appr_id > 0,
        detail=f"approval_id={lr_appr_id}")

# 餘額還沒扣（pending 不扣）
db = server.get_db()
bal = db.execute(
    "SELECT allocated_days, used_days FROM leave_balances lb "
    "JOIN leave_types lt ON lb.leave_type_id = lt.id "
    "WHERE lb.employee_id = 1 AND lt.code = 'annual' AND lb.year = 2026"
).fetchone()
db.close()
_assert("p3b: pending 不扣餘額（used_days=0）",
        bal[1] == 0, detail=f"used_days={bal[1]}")

# 4. 主管核准 approval → 然後 approve_leave
server.resolve_approval(approval_id=lr_appr_id, decision="approved", decided_by="老闆")
r = server.approve_leave(leave_request_id=lr_id, approved_id=lr_appr_id,
                          decided_by="老闆")
_assert("p3b: approve_leave 通過 → 扣餘額 + status=approved",
        "已核准" in r and "餘額已扣" in r, detail=r[:300])

# 5. 驗證 balance 已扣（used_days=3）
db = server.get_db()
bal_after = db.execute(
    "SELECT used_days FROM leave_balances lb "
    "JOIN leave_types lt ON lb.leave_type_id = lt.id "
    "WHERE lb.employee_id = 1 AND lt.code = 'annual' AND lb.year = 2026"
).fetchone()
status_after = db.execute(
    "SELECT status FROM leave_requests WHERE id = ?", (lr_id,)
).fetchone()
appr_consumed = db.execute(
    "SELECT consumed_at, consumed_by_type FROM approvals WHERE id = ?",
    (lr_appr_id,),
).fetchone()
db.close()
_assert("p3b: approved 後 used_days = 3", bal_after[0] == 3,
        detail=f"used_days={bal_after[0]}")
_assert("p3b: leave_request status=approved", status_after[0] == "approved")
_assert("p3b: approval consumed_by_type=leave_request",
        appr_consumed[0] is not None and appr_consumed[1] == "leave_request",
        detail=f"({appr_consumed[0]}, {appr_consumed[1]})")

# 6. 不需簽核的假別 — request_leave 一步完成
r = server.request_leave(employee_id=1, leave_type_code="menstrual",
                          start_date="2026-06-10", end_date="2026-06-10",
                          days=1, reason="生理假")
_assert("p3b: 不需簽核的假別 — 一步完成",
        "已核准" in r and "不需簽核" in r, detail=r[:200])

db = server.get_db()
menstr_used = db.execute(
    "SELECT used_days FROM leave_balances lb "
    "JOIN leave_types lt ON lb.leave_type_id = lt.id "
    "WHERE lb.employee_id = 1 AND lt.code = 'menstrual' AND lb.year = 2026"
).fetchone()
db.close()
_assert("p3b: 不需簽核扣餘額 = 1", menstr_used[0] == 1,
        detail=f"used={menstr_used[0]}")

# 7. 餘額不足 → 擋
r = server.request_leave(employee_id=1, leave_type_code="annual",
                          start_date="2026-07-01", end_date="2026-07-20",
                          days=99, reason="超量請假")
_assert("p3b: 餘額不足 blocked",
        "ERROR" in r and "超出可用餘額" in r, detail=r[:300])

# 8. approve_leave 沒給 approved_id → 擋（用新建的 pending leave_request 測）
r = server.request_leave(employee_id=1, leave_type_code="personal",
                          start_date="2026-06-20", end_date="2026-06-20",
                          days=1, reason="缺 approved_id 測試")
db = server.get_db()
no_appr_lr = db.execute(
    "SELECT id FROM leave_requests WHERE reason = '缺 approved_id 測試'"
).fetchone()[0]
db.close()
r = server.approve_leave(leave_request_id=no_appr_lr, approved_id=0, decided_by="老闆")
_assert("p3b: approve_leave 缺 approved_id blocked",
        "ERROR" in r and "必須提供 approved_id" in r, detail=r[:300])

# 9. approve_leave 已 approved 的 leave_request → 擋
r = server.approve_leave(leave_request_id=lr_id, approved_id=lr_appr_id,
                          decided_by="老闆")
_assert("p3b: 重複 approve 已核准的 leave_request blocked",
        "ERROR" in r and ("無法核准" in r or "已使用" in r), detail=r[:200])

# 10. approve_leave verify 不符 — 建 approval 跟 leave 對不上
# 建第二筆請假 + approval
r = server.request_leave(employee_id=1, leave_type_code="personal",
                          start_date="2026-06-15", end_date="2026-06-15",
                          days=1, reason="事假驗錯誤測試")
db = server.get_db()
lr2_id, lr2_appr = db.execute(
    "SELECT id, approval_id FROM leave_requests WHERE reason = '事假驗錯誤測試'"
).fetchone()
db.close()
server.resolve_approval(approval_id=lr2_appr, decision="approved", decided_by="老闆")
# 拿錯的 leave_request_id（lr_id 已 approved）配 lr2_appr → 驗 verify_fields 應擋
r = server.approve_leave(leave_request_id=lr_id, approved_id=lr2_appr,
                          decided_by="老闆")
_assert("p3b: approve_leave verify_fields 不符 blocked",
        "ERROR" in r and ("不符" in r or "已使用" in r or "無法核准" in r), detail=r[:300])

# 11. get_leave_balance — 列員工 #1 在 2026 的所有 balance
r = server.get_leave_balance(employee_id=1, year=2026)
_assert("p3b: get_leave_balance 列所有假別",
        "特休" in r and "事假" in r and "生理假" in r,
        detail=r[:400])

r = server.get_leave_balance(employee_id=1, year=2026, leave_type_code="annual")
_assert("p3b: get_leave_balance 指定假別",
        "特休" in r and "可用 11" in r, detail=r[:300])

r = server.get_leave_balance(employee_id=99999, year=2026)
_assert("p3b: get_leave_balance non-existent employee blocked",
        "ERROR" in r and "找不到員工" in r, detail=r[:200])

# F2 verification: get_leave_balance 顯示 pending days（避免高估可用餘額）
# 此時 personal 有 pending 申請（"事假驗錯誤測試" + "缺 approved_id 測試" 各 1 天）
r = server.get_leave_balance(employee_id=1, year=2026, leave_type_code="personal")
_assert("p3b: F2 — get_leave_balance 顯示 pending days",
        "pending" in r, detail=r[:300])

# F3 verification 移到 P3b 最末（在 reject/cancel 都跑完之後）

# 12. 半天請假（codex F3）
r = server.request_leave(employee_id=1, leave_type_code="annual",
                          start_date="2026-06-25", end_date="2026-06-25",
                          days=0.5, reason="半天看醫生")
_assert("p3b: 半天 request 通過",
        "請假申請" in r and "0.5 天" in r, detail=r[:200])
db = server.get_db()
half_lr_id, half_appr_id = db.execute(
    "SELECT id, approval_id FROM leave_requests WHERE reason = '半天看醫生'"
).fetchone()
db.close()
server.resolve_approval(approval_id=half_appr_id, decision="approved", decided_by="老闆")
r = server.approve_leave(leave_request_id=half_lr_id, approved_id=half_appr_id,
                          decided_by="老闆")
_assert("p3b: 半天 approve 通過 → 扣 0.5",
        "已核准" in r and "0.5 天" in r, detail=r[:300])

# 13. 跨年假禁止（codex F4）
r = server.request_leave(employee_id=1, leave_type_code="annual",
                          start_date="2026-12-31", end_date="2027-01-02",
                          days=3, reason="跨年假")
_assert("p3b: 跨年假 blocked",
        "ERROR" in r and "跨年度" in r, detail=r[:300])

# 14. 日期格式錯誤（codex A3 / F6）
r = server.request_leave(employee_id=1, leave_type_code="annual",
                          start_date="2026/06/01", end_date="2026/06/02",
                          days=1, reason="格式錯誤日期")
_assert("p3b: malformed date blocked",
        "ERROR" in r and "YYYY-MM-DD" in r, detail=r[:300])

# 15. balance 不存在（codex F6）—  Year 2027 沒設過 balance
r = server.request_leave(employee_id=1, leave_type_code="annual",
                          start_date="2027-03-01", end_date="2027-03-02",
                          days=2, reason="2027 沒 balance")
_assert("p3b: 沒設過 balance 的年度 blocked",
        "ERROR" in r and "尚未設定配額" in r, detail=r[:300])

# 16. reject_leave（codex E1 + F1）
r = server.request_leave(employee_id=1, leave_type_code="personal",
                          start_date="2026-06-28", end_date="2026-06-28",
                          days=1, reason="reject 測試")
db = server.get_db()
reject_lr_id, reject_appr_id = db.execute(
    "SELECT id, approval_id FROM leave_requests WHERE reason = 'reject 測試'"
).fetchone()
db.close()
server.resolve_approval(approval_id=reject_appr_id, decision="rejected", decided_by="老闆")
r = server.reject_leave(leave_request_id=reject_lr_id,
                         rejected_approval_id=reject_appr_id,
                         decided_by="老闆", reason="人手不夠")
_assert("p3b: reject_leave 通過",
        "已駁回" in r and "人手不夠" in r, detail=r[:300])
db = server.get_db()
rej_status = db.execute(
    "SELECT status FROM leave_requests WHERE id = ?", (reject_lr_id,)
).fetchone()[0]
db.close()
_assert("p3b: rejected leave_request status=rejected",
        rej_status == "rejected", detail=f"status={rej_status}")

# 16b. reject_leave 配 approval 還 waiting（沒 rejected）→ 擋
r = server.request_leave(employee_id=1, leave_type_code="personal",
                          start_date="2026-06-29", end_date="2026-06-29",
                          days=1, reason="reject 沒先 rejected")
db = server.get_db()
bad_reject_lr, bad_reject_appr = db.execute(
    "SELECT id, approval_id FROM leave_requests WHERE reason = 'reject 沒先 rejected'"
).fetchone()
db.close()
r = server.reject_leave(leave_request_id=bad_reject_lr,
                         rejected_approval_id=bad_reject_appr,
                         decided_by="老闆", reason="")
_assert("p3b: reject_leave 配 waiting approval blocked",
        "ERROR" in r and "必須是 rejected" in r, detail=r[:300])

# 17. cancel_leave — pending（先用上面建的 bad_reject_lr 來測）
r = server.cancel_leave(leave_request_id=bad_reject_lr, reason="員工撤回",
                          actor="員工A")
_assert("p3b: cancel_leave pending 通過",
        "已取消" in r, detail=r[:300])
db = server.get_db()
cancelled_status = db.execute(
    "SELECT status FROM leave_requests WHERE id = ?", (bad_reject_lr,)
).fetchone()[0]
db.close()
_assert("p3b: cancelled leave_request status=cancelled",
        cancelled_status == "cancelled", detail=f"status={cancelled_status}")

# 18. cancel_leave approved → 回補 balance（用先前 approved 的 half_lr_id 測：0.5 天）
db_before = server.get_db()
used_before = db_before.execute(
    "SELECT used_days FROM leave_balances lb "
    "JOIN leave_types lt ON lb.leave_type_id = lt.id "
    "WHERE lb.employee_id = 1 AND lt.code = 'annual' AND lb.year = 2026"
).fetchone()[0]
db_before.close()
r = server.cancel_leave(leave_request_id=half_lr_id, reason="醫院臨時取消",
                         actor="員工A")
_assert("p3b: cancel_leave approved 通過 + 回補",
        "已取消" in r and "已回補" in r, detail=r[:300])
db_after = server.get_db()
used_after = db_after.execute(
    "SELECT used_days FROM leave_balances lb "
    "JOIN leave_types lt ON lb.leave_type_id = lt.id "
    "WHERE lb.employee_id = 1 AND lt.code = 'annual' AND lb.year = 2026"
).fetchone()[0]
db_after.close()
_assert("p3b: cancel_leave approved 回補 0.5 天 → used_days 減 0.5",
        abs((used_before - used_after) - 0.5) < 0.001,
        detail=f"used_before={used_before}, used_after={used_after}")

# 18b. cancel_leave restore anomaly 測試獨立用 anomaly_test 假別、不污染其他 case
# （codex round-2 MED：restore_used_days 不再靜默截斷、改條件式 + ERROR）
server.register_leave_type("anomaly_test", "異常測試假",
                            default_quota_days=1, requires_approval=False, is_paid=False)
server.set_leave_balance(employee_id=1, leave_type_code="anomaly_test",
                         year=2026, allocated_days=1)
# requires_approval=False、request 一步完成 → used_days = 1
server.request_leave(employee_id=1, leave_type_code="anomaly_test",
                      start_date="2026-09-15", end_date="2026-09-15",
                      days=1, reason="anomaly test")
db = server.get_db()
anom_lr = db.execute(
    "SELECT id FROM leave_requests WHERE reason = 'anomaly test'"
).fetchone()[0]
# 手動把 used_days 設為 0（模擬資料異常：approved 但 balance 顯示 used=0）
db.execute(
    "UPDATE leave_balances SET used_days = 0 "
    "WHERE employee_id = 1 AND leave_type_id = "
    "(SELECT id FROM leave_types WHERE code='anomaly_test') AND year = 2026"
)
db.commit()
db.close()
r = server.cancel_leave(leave_request_id=anom_lr, reason="anomaly cancel",
                         actor="員工A")
_assert("p3b: MED — cancel_leave restore anomaly → ERROR、不靜默",
        "ERROR" in r and "無法回補" in r, detail=r[:300])

# 19. cancel_leave 已 cancelled / rejected → 擋
r = server.cancel_leave(leave_request_id=bad_reject_lr, reason="再取消",
                         actor="員工A")
_assert("p3b: cancel_leave 已 cancelled 擋",
        "ERROR" in r and "無法取消" in r, detail=r[:300])
r = server.cancel_leave(leave_request_id=reject_lr_id, reason="rejected 再取消",
                         actor="員工A")
_assert("p3b: cancel_leave 已 rejected 擋",
        "ERROR" in r and "無法取消" in r, detail=r[:300])

# 20. pending overdraw 防御（codex C1）— balance 剩餘 + pending 加總 < 申請
# 員工 #1 特休 used=3 + 0.5(half) - 0.5(cancel) = 3、allocated=14、pending sum = 0
# 申請大量 pending 直到接近上限、再申請應擋
db = server.get_db()
remaining_check = db.execute(
    "SELECT allocated_days, used_days FROM leave_balances lb "
    "JOIN leave_types lt ON lb.leave_type_id = lt.id "
    "WHERE lb.employee_id = 1 AND lt.code = 'annual' AND lb.year = 2026"
).fetchone()
db.close()
# remaining = 14 - 3 = 11；之後申請 10 + 5 應第二筆擋（因 pending 10 算入）
r1 = server.request_leave(employee_id=1, leave_type_code="annual",
                           start_date="2026-08-01", end_date="2026-08-10",
                           days=10, reason="C1 overdraw 1")
_assert("p3b: pending overdraw test 第一筆 pending 通過",
        "請假申請" in r1, detail=r1[:200])
r2 = server.request_leave(employee_id=1, leave_type_code="annual",
                           start_date="2026-09-01", end_date="2026-09-05",
                           days=5, reason="C1 overdraw 2")
_assert("p3b: C1 — pending overdraw 第二筆 blocked",
        "ERROR" in r2 and "超出可用餘額" in r2, detail=r2[:300])

# F3 verification（codex round-2）: approved/reject/cancel audit log 各別都應有 business_unit
db = server.get_db()
audit_by_action = {
    r[0]: r[1] for r in db.execute(
        "SELECT action, business_unit FROM interaction_log "
        "WHERE target_type = 'leave_request' AND action IN "
        "('leave_approved', 'leave_rejected', 'leave_cancelled') "
        "AND business_unit IS NOT NULL "
        "GROUP BY action"
    ).fetchall()
}
db.close()
_assert("p3b: F3 — leave_approved audit log 有 business_unit",
        audit_by_action.get("leave_approved") is not None,
        detail=f"audit_by_action={audit_by_action}")
_assert("p3b: F3 — leave_rejected audit log 有 business_unit",
        audit_by_action.get("leave_rejected") is not None,
        detail=f"audit_by_action={audit_by_action}")
_assert("p3b: F3 — leave_cancelled audit log 有 business_unit",
        audit_by_action.get("leave_cancelled") is not None,
        detail=f"audit_by_action={audit_by_action}")

# 21. approve_leave 用 expired approval → 擋（codex F2）
r = server.request_leave(employee_id=1, leave_type_code="personal",
                          start_date="2026-06-30", end_date="2026-06-30",
                          days=1, reason="expired approval 測試")
db = server.get_db()
exp_lr_id, exp_appr_id = db.execute(
    "SELECT id, approval_id FROM leave_requests WHERE reason = 'expired approval 測試'"
).fetchone()
# 手動把 approval 設 expired
db.execute("UPDATE approvals SET status = 'expired' WHERE id = ?", (exp_appr_id,))
db.commit()
db.close()
r = server.approve_leave(leave_request_id=exp_lr_id, approved_id=exp_appr_id,
                          decided_by="老闆")
_assert("p3b: expired approval blocked",
        "ERROR" in r and ("不存在" in r or "已使用" in r), detail=r[:300])


# === list_pending_leave_requests（P3d — 給啟動儀表板用）===

_section("list_pending_leave_requests (P3d)")

# 共用 setup：獨立員工 + 假別 + balance + pending 一筆
server.register_employee(name="P3d測試員", role="staff", department="測試組",
                          permissions="basic", phone="0900111222",
                          business_units="brand_p3d")
db = server.get_db()
p3d_emp = db.execute(
    "SELECT id FROM employees WHERE name = 'P3d測試員'"
).fetchone()[0]
exists = db.execute(
    "SELECT id FROM leave_types WHERE code = 'p3d_test_leave'"
).fetchone()
db.close()
if not exists:
    server.register_leave_type(code="p3d_test_leave", name="P3d 測試假",
                                default_quota_days=5, requires_approval=True,
                                is_paid=True, notes="P3d 測試專用")
server.set_leave_balance(employee_id=p3d_emp, leave_type_code="p3d_test_leave",
                          year=2026, allocated_days=10)
server.request_leave(employee_id=p3d_emp, leave_type_code="p3d_test_leave",
                     start_date="2026-10-01", end_date="2026-10-01",
                     days=1, reason="P3d list 測試")
db = server.get_db()
p3d_lr = db.execute(
    "SELECT id FROM leave_requests WHERE reason = 'P3d list 測試'"
).fetchone()[0]
db.close()

# P3d-1: 全 list 含 P3d 員工的 pending
r = server.list_pending_leave_requests()
_assert("p3d-1: 全 list 含 P3d 員工 pending",
        f"#{p3d_lr}" in r and "P3d測試員" in r and "待簽請假" in r,
        detail=r[:400])

# P3d-2: 不存在 BU 顯示 empty
r = server.list_pending_leave_requests(business_unit="totally_fake_bu_xyz")
_assert("p3d-2: 不存在 BU 顯示 empty",
        "目前無待簽請假申請" in r and "totally_fake_bu_xyz" in r,
        detail=r[:200])

# P3d-3: BU=brand_p3d 含 P3d 員工 pending
r = server.list_pending_leave_requests(business_unit="brand_p3d")
_assert("p3d-3: BU=brand_p3d 含 P3d 員工 pending",
        f"#{p3d_lr}" in r and "P3d測試員" in r,
        detail=r[:300])

# P3d-4: BU=brand_a 不含 brand_p3d 員工 pending（防 BU 漏匹配）
r = server.list_pending_leave_requests(business_unit="brand_a")
_assert("p3d-4: BU=brand_a 不含 brand_p3d 員工 pending",
        f"#{p3d_lr}" not in r,
        detail=r[:300])

# P3d-5: approved leaves 不出現在 pending list
db = server.get_db()
approved_ids = [str(row[0]) for row in db.execute(
    "SELECT id FROM leave_requests WHERE status = 'approved'"
).fetchall()]
db.close()
r = server.list_pending_leave_requests()
import re as _re_p3d
ids_in_list = _re_p3d.findall(r"^- 請假 #(\d+)\s", r, flags=_re_p3d.MULTILINE)
approved_leaked = [i for i in approved_ids if i in ids_in_list]
_assert(f"p3d-5: approved leaves 不出現於 pending list (approved={len(approved_ids)} 件)",
        len(approved_leaked) == 0,
        detail=f"leaked: {approved_leaked}, ids_in_list: {ids_in_list[:10]}")

# P3d-6/7: business_units=NULL/'' 視為「全公司」，BU 篩選時應出現
# 建一位 business_units 留空 (NULL) 的員工
server.register_employee(name="P3d全公司員", role="staff", department="跨部門",
                          permissions="basic", phone="0900333444",
                          business_units="")
db = server.get_db()
p3d_all_emp = db.execute(
    "SELECT id FROM employees WHERE name = 'P3d全公司員'"
).fetchone()[0]
db.close()
server.set_leave_balance(employee_id=p3d_all_emp, leave_type_code="p3d_test_leave",
                          year=2026, allocated_days=10)
server.request_leave(employee_id=p3d_all_emp, leave_type_code="p3d_test_leave",
                     start_date="2026-11-01", end_date="2026-11-01",
                     days=1, reason="P3d 全公司員 NULL BU 測試")
db = server.get_db()
p3d_all_lr = db.execute(
    "SELECT id FROM leave_requests WHERE reason = 'P3d 全公司員 NULL BU 測試'"
).fetchone()[0]
db.close()

r = server.list_pending_leave_requests(business_unit="brand_p3d")
_assert("p3d-6: BU 篩選時 business_units='' 員工的 pending 仍出現（全公司視角）",
        f"請假 #{p3d_all_lr}" in r and "P3d全公司員" in r,
        detail=r[:400])

r = server.list_pending_leave_requests(business_unit="brand_a")
_assert("p3d-7: 不同 BU 篩選也要含 business_units='' 員工",
        f"請假 #{p3d_all_lr}" in r,
        detail=r[:400])

# P3d-8: leave_requests.employee_id=NULL（員工已被 DELETE，ON DELETE SET NULL）
# 不會 crash 且顯示「員工已離職」、不會出現「#None」
db = server.get_db()
db.execute("UPDATE leave_requests SET employee_id = NULL WHERE id = ?",
           (p3d_all_lr,))
db.commit()
db.close()
r = server.list_pending_leave_requests()
_assert("p3d-8: employee_id=NULL 不 crash + 顯示「員工已離職」+ 無 #None",
        "員工已離職" in r and "#None" not in r,
        detail=r[:500])

# P3d-8 cleanup：把 employee_id 改回去、避免污染後續測試
db = server.get_db()
db.execute("UPDATE leave_requests SET employee_id = ? WHERE id = ?",
           (p3d_all_emp, p3d_all_lr))
db.commit()
db.close()


# === Read-only 查詢工具（P3e — get_approval / get_leave_request / list_leave_requests）===

_section("read-only queries (P3e)")

# P3e-1: get_approval 不存在 → ERROR
r = server.get_approval(approval_id=999999)
_assert("p3e-1: get_approval 不存在回 ERROR",
        r.startswith("ERROR") and "999999" in r,
        detail=r[:200])

# P3e-2: get_approval 對應實際 approval → 包含 # / 狀態 / detail
db = server.get_db()
some_appr_id = db.execute(
    "SELECT id FROM approvals ORDER BY id LIMIT 1"
).fetchone()[0]
db.close()
r = server.get_approval(approval_id=some_appr_id)
_assert(f"p3e-2: get_approval(#{some_appr_id}) 含基本欄位",
        f"審核 #{some_appr_id}" in r and "類型：" in r and "狀態：" in r,
        detail=r[:400])

# P3e-3: get_approval 對應已 consumed 的 → 顯示「已消費」
db = server.get_db()
consumed_row = db.execute(
    "SELECT id FROM approvals WHERE consumed_at IS NOT NULL LIMIT 1"
).fetchone()
db.close()
if consumed_row:
    r = server.get_approval(approval_id=consumed_row[0])
    _assert(f"p3e-3: get_approval(#{consumed_row[0]}) 顯示「已消費」",
            "已消費" in r,
            detail=r[:500])
else:
    # 沒 consumed approval、skip 但不 fail
    _assert("p3e-3: (skip) 無 consumed approval 可測", True)

# P3e-4: get_leave_request 不存在 → ERROR
r = server.get_leave_request(leave_request_id=999999)
_assert("p3e-4: get_leave_request 不存在回 ERROR",
        r.startswith("ERROR") and "999999" in r,
        detail=r[:200])

# P3e-5: get_leave_request 存在 → 含完整欄位
db = server.get_db()
some_lr_id = db.execute(
    "SELECT id FROM leave_requests ORDER BY id LIMIT 1"
).fetchone()[0]
db.close()
r = server.get_leave_request(leave_request_id=some_lr_id)
_assert(f"p3e-5: get_leave_request(#{some_lr_id}) 含完整欄位",
        f"請假 #{some_lr_id}" in r and "員工：" in r and "假別：" in r and "狀態：" in r,
        detail=r[:500])

# P3e-6: list_leave_requests 無 filter → 多筆
r = server.list_leave_requests()
_assert("p3e-6: list_leave_requests() 無 filter 回多筆",
        "請假紀錄" in r and "最新" in r and "請假 #" in r,
        detail=r[:400])

# P3e-7: list_leave_requests filter by employee
r = server.list_leave_requests(employee_id=p3d_emp)
_assert(f"p3e-7: list_leave_requests(employee_id={p3d_emp}) 篩特定員工",
        f"員工 #{p3d_emp}" in r and "P3d測試員" in r,
        detail=r[:400])

# P3e-8: list_leave_requests filter by status approved
r = server.list_leave_requests(status="approved", limit=5)
_assert("p3e-8: list_leave_requests(status='approved') 只回 approved",
        r.startswith("ERROR") is False and ("approved" in r.lower() or "查無" in r),
        detail=r[:400])

# P3e-9: list_leave_requests 不存在條件 → empty msg
r = server.list_leave_requests(employee_id=999999)
_assert("p3e-9: list_leave_requests 不存在員工回「查無」",
        "查無" in r,
        detail=r[:200])

# P3e-10: limit 邊界（防 LIMIT -1 / OOM）
r = server.list_leave_requests(limit=0)
_assert("p3e-10: limit=0 擋下", r.startswith("ERROR") and "limit" in r, detail=r[:200])
r = server.list_leave_requests(limit=200)
_assert("p3e-11: limit=200 擋下（超過 100）",
        r.startswith("ERROR") and "100" in r, detail=r[:200])
r = server.list_leave_requests(limit=-1)
_assert("p3e-12: limit=-1 擋下（防 SQLite LIMIT -1 = 不限）",
        r.startswith("ERROR") and "limit" in r, detail=r[:200])

# P3e-13: status 必須是合法 enum
r = server.list_leave_requests(status="invalid_status_xyz")
_assert("p3e-13: status 非法值擋下",
        r.startswith("ERROR") and "status" in r, detail=r[:300])

# P3e-18~22: get_approval / resolve_approval 對 detail 非標準 JSON 形狀的容錯
# （codex round 9 audit MEDIUM：_format_resume_detail 對 list / null / resume_params 非 dict 會 crash）
import json as _json_p3e
db = server.get_db()
# 建一筆 approval、各種畸形 detail 都 in-place UPDATE 然後 get_approval 不 crash
edge_appr_id = db.execute(
    "INSERT INTO approvals (type, summary, detail, status) "
    "VALUES ('test', 'edge-case', '{}', 'waiting')"
).lastrowid
db.commit()
db.close()

for case_name, detail_value in [
    ("純文字 detail", "this is plain text, not JSON"),
    ("JSON null", "null"),
    ("JSON list", '["a", "b"]'),
    ("JSON 數字", "42"),
    ("resume_params 是 null", '{"resume_action": "manual_x", "resume_params": null}'),
    ("resume_params 是 list", '{"resume_action": "record_transaction", "resume_params": ["bad"]}'),
]:
    db = server.get_db()
    db.execute("UPDATE approvals SET detail = ? WHERE id = ?",
               (detail_value, edge_appr_id))
    db.commit()
    db.close()
    r = server.get_approval(approval_id=edge_appr_id)
    _assert(f"p3e-edge: get_approval 容錯 ({case_name})",
            not r.startswith("ERROR") and f"審核 #{edge_appr_id}" in r,
            detail=r[:300])

# P3e-edge: 非空 list 的 resume_params 應走 raw fallback、不應產出 record_transaction() 空呼叫
db = server.get_db()
db.execute(
    "UPDATE approvals SET detail = ? WHERE id = ?",
    ('{"resume_action": "record_transaction", "resume_params": [1, 2, 3]}',
     edge_appr_id),
)
db.commit()
db.close()
r = server.get_approval(approval_id=edge_appr_id)
# 用 service constant 而非字面 markdown header、避免 header 改名 test 假紅
from modules.approvals.service import RAW_DETAIL_HEADER, NEXT_STEP_HEADER
_assert("p3e-edge: 非空 list resume_params 走 raw fallback、不產 record_transaction() 空呼叫",
        "record_transaction()" not in r and RAW_DETAIL_HEADER in r,
        detail=r[:400])

# P3e-edge: 原始 detail JSON 保留可見（agent 可自行 parse resume_params）
db = server.get_db()
db.execute(
    "UPDATE approvals SET detail = ? WHERE id = ?",
    ('{"resume_action": "record_transaction", "resume_params": {"amount": 12345, "category": "supplies"}}',
     edge_appr_id),
)
db.commit()
db.close()
r = server.get_approval(approval_id=edge_appr_id)
_assert("p3e-edge: get_approval 保留 raw detail JSON 可見 + 附『下一步說明』",
        "12345" in r and "supplies" in r and RAW_DETAIL_HEADER in r and NEXT_STEP_HEADER in r,
        detail=r[:500])

# P3e-edge: resume_action 是 non-string（list / int）不應 crash
for case_name, detail_value in [
    ("resume_action 是 list", '{"resume_action": ["a","b"], "resume_params": {}}'),
    ("resume_action 是 int", '{"resume_action": 42, "resume_params": {}}'),
]:
    db = server.get_db()
    db.execute("UPDATE approvals SET detail = ? WHERE id = ?",
               (detail_value, edge_appr_id))
    db.commit()
    db.close()
    r = server.get_approval(approval_id=edge_appr_id)
    _assert(f"p3e-edge: get_approval 容錯 ({case_name})、無 startswith crash",
            not r.startswith("ERROR") and f"審核 #{edge_appr_id}" in r,
            detail=r[:300])

# P3e-14 ~ P3e-17：service 層 isinstance guard 防線測試（直呼測試）
# 註：實際 MCP transport 下 fastmcp Pydantic 會先 coerce / 擋下這些情境，
# 不會打到 service。這幾個 case 驗的是 service 層的「縱深防禦」、不是 transport 行為。

# P3e-14: limit=True / False（bool 是 int 子類、要排除）
r = server.list_leave_requests(limit=True)
_assert("p3e-14: limit=True 擋下（service guard 直呼驗證）",
        r.startswith("ERROR") and ("整數" in r or "int" in r.lower()),
        detail=r[:300])

# P3e-15: limit=float
r = server.list_leave_requests(limit=1.5)
_assert("p3e-15: limit=1.5 擋下（非 int）",
        r.startswith("ERROR") and ("整數" in r or "int" in r.lower()),
        detail=r[:300])

# P3e-16: limit=string
r = server.list_leave_requests(limit="abc")
_assert("p3e-16: limit='abc' 擋下（非 int）",
        r.startswith("ERROR") and ("整數" in r or "int" in r.lower()),
        detail=r[:300])

# P3e-17: limit=None
r = server.list_leave_requests(limit=None)
_assert("p3e-17: limit=None 擋下（非 int）",
        r.startswith("ERROR") and ("整數" in r or "int" in r.lower()),
        detail=r[:300])


# === HITL gate helper（P3a）===

_section("HITL gate helper unit-style (P3a)")

# gate_check 4-state 單測（直接呼叫 helper、不經 record_transaction）
from modules.approvals import service as _appr_svc
from shared.db import transaction as _tx

# Setup: 一個 approved unused approval
server.create_approval(
    type="expense",
    summary="P3a gate test approval",
    detail=json.dumps({
        "resume_action": "test_action",
        "resume_params": {"amount": 10000, "business_unit": ""},
    }, ensure_ascii=False),
    approver="老闆",
    requester="test",
)
db = server.get_db()
p3a_appr_id = db.execute(
    "SELECT id FROM approvals WHERE summary = 'P3a gate test approval' AND status = 'waiting'"
).fetchone()[0]
db.close()
server.resolve_approval(approval_id=p3a_appr_id, decision="approved", decided_by="老闆")

# State 1: pass_no_approval（amount < threshold、無 approved_id）
with _tx() as db:
    g = _appr_svc.gate_check(
        db, approved_id=0, amount=100, threshold=5000,
        expected_action="test_action", verify_fields={"amount": 100},
    )
_assert("p3a: state pass_no_approval — 全預設",
        g.error is None and not g.needs_approval and g.approval_id is None,
        detail=f"{g}")

# State 2: needs_approval（amount >= threshold、無 approved_id）
with _tx() as db:
    g = _appr_svc.gate_check(
        db, approved_id=0, amount=10000, threshold=5000,
        expected_action="test_action", verify_fields={"amount": 10000},
    )
_assert("p3a: state needs_approval — needs_approval=True",
        g.needs_approval and g.error is None and g.approval_id is None,
        detail=f"{g}")

# State 3: pass_with_approval（valid approved_id）
with _tx() as db:
    g = _appr_svc.gate_check(
        db, approved_id=p3a_appr_id, amount=10000, threshold=5000,
        expected_action="test_action",
        verify_fields={"amount": 10000, "business_unit": ""},
    )
_assert("p3a: state pass_with_approval — 拿到 approval_id",
        g.approval_id == p3a_appr_id and g.error is None and not g.needs_approval,
        detail=f"{g}")

# State 4a: error — 不存在的 approved_id
with _tx() as db:
    g = _appr_svc.gate_check(
        db, approved_id=99999, amount=10000, threshold=5000,
        expected_action="test_action", verify_fields={"amount": 10000},
    )
_assert("p3a: state error — 不存在 approved_id 回 error",
        g.error and "不存在、未核准或已使用" in g.error,
        detail=f"{g}")

# State 4b: error — resume_action 不符
with _tx() as db:
    g = _appr_svc.gate_check(
        db, approved_id=p3a_appr_id, amount=10000, threshold=5000,
        expected_action="wrong_action",  # 注意：跟 approval detail 不同
        verify_fields={"amount": 10000},
    )
_assert("p3a: state error — action 不符回 error",
        g.error and "不能用於" in g.error, detail=f"{g}")

# State 4c: error — verify_fields 不符
with _tx() as db:
    g = _appr_svc.gate_check(
        db, approved_id=p3a_appr_id, amount=10000, threshold=5000,
        expected_action="test_action",
        verify_fields={"amount": 99999},  # 不符
    )
_assert("p3a: state error — fields 不符回 error",
        g.error and "不符" in g.error, detail=f"{g}")

# gate_consume 單測：消耗成功 → rowcount=1、再消耗 → rowcount=0 → RuntimeError
# 先消耗 p3a_appr_id（這次 consume 應成功）
with _tx() as db:
    _appr_svc.gate_consume(db, approval_id=p3a_appr_id,
                            consumed_by_type="test", consumed_by_id=12345)

db = server.get_db()
consumed_row = db.execute(
    "SELECT consumed_at, consumed_by_type, consumed_by_id FROM approvals WHERE id = ?",
    (p3a_appr_id,),
).fetchone()
db.close()
_assert("p3a: gate_consume 寫入 consumed_at",
        consumed_row[0] is not None, detail=f"consumed_at={consumed_row[0]}")
_assert("p3a: gate_consume 寫入 consumed_by_type/id",
        consumed_row[1] == "test" and consumed_row[2] == 12345,
        detail=f"({consumed_row[1]}, {consumed_row[2]})")

# 再次 consume 同一 approval → 應 raise（rowcount=0）
raised = False
try:
    with _tx() as db:
        _appr_svc.gate_consume(db, approval_id=p3a_appr_id,
                                consumed_by_type="test", consumed_by_id=99999)
except RuntimeError:
    raised = True
_assert("p3a: gate_consume 重複消耗 raise RuntimeError",
        raised)

# 不存在 approval → 也 raise
raised2 = False
try:
    with _tx() as db:
        _appr_svc.gate_consume(db, approval_id=99999,
                                consumed_by_type="test", consumed_by_id=1)
except RuntimeError:
    raised2 = True
_assert("p3a: gate_consume 不存在 approval raise",
        raised2)


# === record_payment 全額付清明確 error（P2.16）===

_section("record_payment fully-paid blocked (P2.16)")

# 建一筆 pending 帳目、付清、再付一次 → 應 ERROR、不該 silently no-op
r = server.record_transaction(type="income", amount=1500, category="銷售",
                               description="P2.16 fully-paid test",
                               related_customer_id=2, payment_status="pending",
                               due_date=PAST_DUE_DATE)
db = server.get_db()
p216_txn_id = db.execute(
    "SELECT id FROM transactions WHERE description = 'P2.16 fully-paid test'"
).fetchone()[0]
db.close()
server.record_payment(p216_txn_id, 1500, notes="付清")

# 再付一次 → 應 ERROR
r = server.record_payment(p216_txn_id, 100, notes="重複付款")
_assert("p2.16: LOW — fully-paid record_payment 明確擋",
        "ERROR" in r and ("已全額付清" in r and "無需再記款" in r),
        detail=r[:200])

# 確認 paid_amount 沒被誤增
db = server.get_db()
paid_amt = db.execute(
    "SELECT paid_amount FROM transactions WHERE id = ?", (p216_txn_id,)
).fetchone()[0]
db.close()
_assert("p2.16: paid_amount 沒被多加",
        paid_amt == 1500, detail=f"paid_amount={paid_amt}")

# 驗證錯誤訊息引導到 delete_transaction、不引導到 update_transaction（codex round-2 LOW）
_assert("p2.16: error message 引導到 delete_transaction（不是 update_transaction）",
        "delete_transaction" in r and "update_transaction" not in r,
        detail=r[:300])

# 過付情境（paid > amount，理論上 clamp 不該出現、但若 DB 資料異常）→ 也應擋
db = server.get_db()
db.execute(
    "INSERT INTO transactions (type, amount, paid_amount, category, payment_status, "
    "transaction_date) VALUES ('income', 1000, 1500, 'test', 'paid', date('now'))"
)
overpaid_id = db.execute(
    "SELECT id FROM transactions WHERE amount = 1000 AND paid_amount = 1500"
).fetchone()[0]
db.commit()
db.close()
r = server.record_payment(overpaid_id, 100, notes="嘗試付給 overpaid")
_assert("p2.16: overpaid (paid>amount) 也擋",
        "ERROR" in r and "已全額付清" in r, detail=r[:200])


# === expire_stale_approvals helper（P2.15）===

_section("expire_stale_approvals helper (P2.15)")

# 直接呼叫 helper：建一個 waiting 但 expires_at 過期的 approval、跑 helper、
# status 應變 expired；同時驗證 helper 不會碰非過期 / 非 waiting 的 approval
from modules.approvals import service as _appr_svc

db = server.get_db()
db.execute(
    "INSERT INTO approvals (type, summary, status, expires_at) "
    "VALUES ('test', 'stale waiting', 'waiting', '2000-01-01 00:00:00')"
)
db.execute(
    "INSERT INTO approvals (type, summary, status, expires_at) "
    "VALUES ('test', 'fresh waiting', 'waiting', '2099-12-31 23:59:59')"
)
db.execute(
    "INSERT INTO approvals (type, summary, status, expires_at) "
    "VALUES ('test', 'already approved', 'approved', '2000-01-01 00:00:00')"
)
# 永不過期的 waiting（expires_at = NULL）— 不應被 helper 改動
db.execute(
    "INSERT INTO approvals (type, summary, status, expires_at) "
    "VALUES ('test', 'no expiry waiting', 'waiting', NULL)"
)
db.commit()
db.close()

# 呼叫 helper（service-level、caller 包 transaction）
from shared.db import transaction as _tx
with _tx() as db:
    expired_count = _appr_svc.expire_stale_approvals(db)
_assert("p2.15: expire_stale_approvals 至少過期 1 筆",
        expired_count >= 1, detail=f"rowcount={expired_count}")

db = server.get_db()
stale_row = db.execute(
    "SELECT status FROM approvals WHERE summary = 'stale waiting'"
).fetchone()
fresh_row = db.execute(
    "SELECT status FROM approvals WHERE summary = 'fresh waiting'"
).fetchone()
approved_row = db.execute(
    "SELECT status FROM approvals WHERE summary = 'already approved'"
).fetchone()
db.close()
_assert("p2.15: stale waiting → expired", stale_row[0] == "expired")
_assert("p2.15: fresh waiting 不受影響 → 仍 waiting", fresh_row[0] == "waiting")
_assert("p2.15: 已 approved 不受影響 → 仍 approved", approved_row[0] == "approved")
no_expiry_row = server.get_db().execute(
    "SELECT status FROM approvals WHERE summary = 'no expiry waiting'"
).fetchone()
_assert("p2.15: expires_at=NULL waiting 不受影響 → 仍 waiting",
        no_expiry_row[0] == "waiting", detail=f"status={no_expiry_row[0]}")

# get_context_summary 呼叫應隱含跑 helper
db = server.get_db()
db.execute(
    "INSERT INTO approvals (type, summary, status, expires_at) "
    "VALUES ('test', 'context stale', 'waiting', '2000-01-01 00:00:00')"
)
db.commit()
db.close()
server.get_context_summary("full")
db = server.get_db()
ctx_row = db.execute(
    "SELECT status FROM approvals WHERE summary = 'context stale'"
).fetchone()
db.close()
_assert("p2.15: get_context_summary 觸發 expire_stale_approvals",
        ctx_row[0] == "expired", detail=f"status={ctx_row[0]}")


# === fulfill_order partial follow-up 出貨量驗證（P2.14）===
# 放最後（migration runner 前）：這段會建新訂單、改 status、跑 partial fulfill，
# 不污染 cross-module integration 假設。

_section("fulfill_order partial overship validation (P2.14)")

# 補貨庫存以利測試
db = server.get_db()
db.execute("UPDATE inventory SET current_stock = 100 WHERE sku IN ('SKU-001', 'SKU-002')")
db.commit()
db.close()

# 建新訂單（multi-SKU、控總金額 < 5000 threshold 避開 approval 門檻）並 QC partial
# raw: 4*500 + 4*300 = 3200，distributor 15% off → 2720
p214_items = json.dumps([
    {"sku": "SKU-001", "name": "香氛蠟燭", "qty": 4, "price": 500},
    {"sku": "SKU-002", "name": "擴香瓶", "qty": 4, "price": 300},
])
server.create_order(customer_id=1, items_json=p214_items,
                    business_unit="brand_a", created_by="test", notes="P2.14 test")
db = server.get_db()
p214_order_id = db.execute(
    "SELECT id FROM orders WHERE notes = 'P2.14 test' ORDER BY id DESC LIMIT 1"
).fetchone()[0]
db.close()
server.update_order(p214_order_id, status="confirmed")
server.qc_order(p214_order_id, result="partial", notes="SKU-002 一半瑕疵")

# qty <= 0 → 擋
r = server.fulfill_order(p214_order_id,
                          partial_items_json='[{"sku":"SKU-001","qty":0}]')
_assert("p2.14: qty=0 blocked",
        "ERROR" in r and "無效" in r, detail=r[:200])

r = server.fulfill_order(p214_order_id,
                          partial_items_json='[{"sku":"SKU-001","qty":-5}]')
_assert("p2.14: qty<0 blocked",
        "ERROR" in r and "無效" in r, detail=r[:200])

# 空 list（E1 HIGH）→ 擋
r = server.fulfill_order(p214_order_id, partial_items_json='[]')
_assert("p2.14: HIGH E1 — empty list blocked",
        "ERROR" in r and "不可為空" in r, detail=r[:200])

# 非 list（dict）→ 擋
r = server.fulfill_order(p214_order_id,
                          partial_items_json='{"sku":"SKU-001","qty":1}')
_assert("p2.14: dict (not list) blocked",
        "ERROR" in r and "陣列" in r, detail=r[:200])

# list item 是 string、非 dict → 擋
r = server.fulfill_order(p214_order_id, partial_items_json='["SKU-001"]')
_assert("p2.14: string item (not dict) blocked",
        "ERROR" in r and "格式不是 object" in r, detail=r[:200])

# qty 是 string 不是 int → 擋（E2 MED）
r = server.fulfill_order(p214_order_id,
                          partial_items_json='[{"sku":"SKU-001","qty":"5"}]')
_assert("p2.14: MEDIUM E2 — string qty blocked",
        "ERROR" in r and "無效" in r, detail=r[:200])

# qty 是 float → 擋（E2 MED）
r = server.fulfill_order(p214_order_id,
                          partial_items_json='[{"sku":"SKU-001","qty":2.5}]')
_assert("p2.14: MEDIUM E2 — float qty blocked",
        "ERROR" in r and "無效" in r, detail=r[:200])

# 未知 SKU → 擋
r = server.fulfill_order(p214_order_id,
                          partial_items_json='[{"sku":"SKU-NOT-IN-ORDER","qty":1}]')
_assert("p2.14: unknown SKU blocked",
        "ERROR" in r and "不在原訂單" in r, detail=r[:200])

# 重複 SKU → 擋
r = server.fulfill_order(p214_order_id,
                          partial_items_json='[{"sku":"SKU-001","qty":2},{"sku":"SKU-001","qty":3}]')
_assert("p2.14: duplicate SKU blocked",
        "ERROR" in r and "重複出現" in r, detail=r[:200])

# 超過 qty 上限 → 擋
r = server.fulfill_order(p214_order_id,
                          partial_items_json='[{"sku":"SKU-001","qty":99}]')
_assert("p2.14: MEDIUM — qty > remaining blocked",
        "ERROR" in r and "超過剩餘未出量" in r, detail=r[:200])

# 第一次 partial fulfill：SKU-001 全 4、SKU-002 出 2（保留 2 個瑕疵）
r = server.fulfill_order(p214_order_id,
                          partial_items_json='[{"sku":"SKU-001","qty":4},{"sku":"SKU-002","qty":2}]')
_assert("p2.14: valid first partial succeeds",
        "出貨" in r or "shipped" in r, detail=r[:200])

# 補出貨：剩餘 SKU-001=0 / SKU-002=2
# 試圖補 SKU-001 → 應擋（已全數出完）
r = server.fulfill_order(p214_order_id,
                          partial_items_json='[{"sku":"SKU-001","qty":1}]')
_assert("p2.14: followup over-ship of fully-shipped SKU blocked",
        "ERROR" in r and "無剩餘可補" in r, detail=r[:200])

# 試圖補 SKU-002 超量（剩 2、要 5）→ 應擋
r = server.fulfill_order(p214_order_id,
                          partial_items_json='[{"sku":"SKU-002","qty":5}]')
_assert("p2.14: followup over-ship of partially-shipped SKU blocked",
        "ERROR" in r and "超過剩餘未出量" in r, detail=r[:200])

# 合法補出 SKU-002 剩餘 2 個 → 通過
r = server.fulfill_order(p214_order_id,
                          partial_items_json='[{"sku":"SKU-002","qty":2}]')
_assert("p2.14: valid followup partial succeeds",
        "出貨" in r or "shipped" in r, detail=r[:200])

# 再試補出貨：所有都出完了 → _handle_followup_partial 應回 "都已出貨完畢"
r = server.fulfill_order(p214_order_id)
_assert("p2.14: 補出貨 after all-shipped returns clear msg",
        "ERROR" in r and ("出貨完畢" in r or "都已出貨" in r), detail=r[:200])

# D4: prepaid 訂單 + overship → validator 先攔（不會看到 prepayment error）
# 注意：customer #1 在 brand_a 有 entity terms 覆寫（net45），entity 優先於 customer
# 預設，所以必須同時把 entity terms 改 prepaid（不然 prepaid 路徑不會被觸發）
db = server.get_db()
db.execute("UPDATE customers SET payment_terms = 'prepaid' WHERE id = 1")
db.execute(
    "UPDATE customer_entity_terms SET payment_terms = 'prepaid' "
    "WHERE customer_id = 1 AND business_unit = 'brand_a'"
)
db.commit()
db.close()
prepaid_items = json.dumps([
    {"sku": "SKU-001", "name": "香氛蠟燭", "qty": 3, "price": 400},  # 1200 raw
])
server.create_order(customer_id=1, items_json=prepaid_items,
                    business_unit="brand_a", created_by="test", notes="P2.14 prepaid")
db = server.get_db()
prep_order_id = db.execute(
    "SELECT id FROM orders WHERE notes = 'P2.14 prepaid' ORDER BY id DESC LIMIT 1"
).fetchone()[0]
# 確認該訂單的付款條件是 prepaid（證明 entity terms 切換有效）
prep_terms = db.execute(
    "SELECT payment_terms FROM orders WHERE id = ?", (prep_order_id,)
).fetchone()[0]
db.close()
_assert("p2.14: D4 setup — prepaid entity terms 確實有套用到新訂單",
        prep_terms == "prepaid", detail=f"payment_terms={prep_terms}")

server.update_order(prep_order_id, status="confirmed")
server.qc_order(prep_order_id, result="partial", notes="prepaid overship test")
r = server.fulfill_order(prep_order_id,
                          partial_items_json='[{"sku":"SKU-001","qty":99}]')
_assert("p2.14: LOW D4 — overship validator runs before prepayment check",
        "ERROR" in r and "超過剩餘未出量" in r and "prepaid" not in r,
        detail=r[:200])
# 還原 customer + entity 付款條件（避免後續 P2.13 等測試受影響）
db = server.get_db()
db.execute("UPDATE customers SET payment_terms = NULL WHERE id = 1")
db.execute(
    "UPDATE customer_entity_terms SET payment_terms = 'net45' "
    "WHERE customer_id = 1 AND business_unit = 'brand_a'"
)
db.commit()
db.close()


# === HITL approval consume + verify（P2.13）===
# 必須放最後（migration runner 前）：這段會建大筆訂單 + 多筆 transaction，
# 若放前面會污染 cross-module integration 假設的 stock/customer 累計。

_section("HITL approval consume + verify (P2.13)")

# Setup: 建立可消耗的 record_transaction approval（amount=12000、超 threshold 5000）
detail_record_txn = json.dumps({
    "resume_action": "record_transaction",
    "resume_params": {
        "type": "expense", "amount": 12000, "category": "設備",
        "description": "電腦", "transaction_date": "2026-01-15",
        "related_customer_id": 0, "related_order_id": 0, "related_invoice": "",
        "business_unit": "", "payment_status": "paid", "due_date": "",
    },
    "then": "記帳完成後通知主管",
}, ensure_ascii=False)
r = server.create_approval(type="expense", summary="購買電腦 NT$12000",
                            detail=detail_record_txn, approver="老闆", requester="員工A")
_assert("p2.13: create_approval for record_transaction", "#" in r)

db = server.get_db()
record_appr_id = db.execute(
    "SELECT id FROM approvals WHERE summary = '購買電腦 NT$12000' AND status = 'waiting'"
).fetchone()[0]
db.close()

r = server.resolve_approval(approval_id=record_appr_id, decision="approved", decided_by="老闆")
_assert("p2.13: resolve approval to approved", "已" in r or "核准" in r)

# 用 approval 真正記帳 → 應成功
r = server.record_transaction(type="expense", amount=12000, category="設備",
                               description="電腦", transaction_date="2026-01-15",
                               payment_status="paid", approved_id=record_appr_id)
_assert("p2.13: first use of approval succeeds",
        "帳目" in r and "#" in r, detail=r[:150])

# 確認 consumed_at + consumed_by_type/id 已寫入
db = server.get_db()
row = db.execute(
    "SELECT consumed_at, consumed_by_type, consumed_by_id FROM approvals WHERE id = ?",
    (record_appr_id,),
).fetchone()
db.close()
_assert("p2.13: approval marked consumed", row[0] is not None,
        detail=f"consumed_at={row[0]}")
_assert("p2.13: approval consumed_by_type=transaction",
        row[1] == "transaction", detail=f"consumed_by_type={row[1]}")
_assert("p2.13: approval consumed_by_id is set",
        row[2] is not None and row[2] > 0, detail=f"consumed_by_id={row[2]}")

# 嘗試重用同一 approval → 應被擋（HIGH finding fix）
r = server.record_transaction(type="expense", amount=12000, category="設備",
                               description="重複用 approval", payment_status="paid",
                               approved_id=record_appr_id)
_assert("p2.13: HIGH — reuse of consumed approval blocked",
        "ERROR" in r and ("已使用" in r or "不存在" in r), detail=r[:150])

# 建立新 approval 但拿來挪用到 create_order（resume_action 不符）
r = server.create_approval(type="expense", summary="購買印表機 NT$8000",
                            detail=json.dumps({
                                "resume_action": "record_transaction",
                                "resume_params": {
                                    "type": "expense", "amount": 8000, "category": "設備",
                                    "description": "印表機", "transaction_date": "2026-01-15",
                                    "related_customer_id": 0, "related_order_id": 0,
                                    "related_invoice": "", "business_unit": "",
                                    "payment_status": "paid", "due_date": "",
                                },
                            }, ensure_ascii=False),
                            approver="老闆", requester="員工A")
_assert("p2.13: create_approval for printer", "#" in r)
db = server.get_db()
printer_appr_id = db.execute(
    "SELECT id FROM approvals WHERE summary = '購買印表機 NT$8000' AND status = 'waiting'"
).fetchone()[0]
db.close()
server.resolve_approval(approval_id=printer_appr_id, decision="approved", decided_by="老闆")

items_high = json.dumps([{"sku": "SKU-001", "name": "香氛蠟燭", "qty": 1, "price": 500}])
r = server.create_order(customer_id=1, items_json=items_high,
                         business_unit="brand_a", approved_id=printer_appr_id)
_assert("p2.13: HIGH — approval cross-action blocked (record_transaction → create_order)",
        "ERROR" in r and ("不能用於" in r or "create_order" in r),
        detail=r[:200])

# 拿同一 approval 但改 amount → params mismatch
r = server.record_transaction(type="expense", amount=50000, category="設備",
                               description="改大金額重用", payment_status="paid",
                               approved_id=printer_appr_id)
_assert("p2.13: MEDIUM — approval amount mismatch blocked",
        "ERROR" in r and ("不符" in r or "amount" in r), detail=r[:200])

# 改 type 也擋
r = server.record_transaction(type="income", amount=8000, category="設備",
                               description="改 type", payment_status="paid",
                               approved_id=printer_appr_id)
_assert("p2.13: MEDIUM — approval type mismatch blocked",
        "ERROR" in r and ("不符" in r or "type" in r), detail=r[:200])

# 用對的 params → 應成功
r = server.record_transaction(type="expense", amount=8000, category="設備",
                               description="印表機", transaction_date="2026-01-15",
                               payment_status="paid", approved_id=printer_appr_id)
_assert("p2.13: matching params succeeds",
        "帳目" in r and "#" in r, detail=r[:150])

# 不存在的 approval id → 擋
r = server.record_transaction(type="expense", amount=20000, category="設備",
                               description="ghost approval", approved_id=99999)
_assert("p2.13: non-existent approval blocked",
        "ERROR" in r and ("不存在" in r or "未核准" in r), detail=r[:150])

# === 決策 #183：record_transaction 超門檻「系統自建審核」+ 自建 approval 可乾淨 consume ===
# 這是 #25 live 測暴露 bug 的回歸測試：舊流程 agent 手寫 4 欄 approval、被 11 欄 gate 擋。
# 系統自建必產完整 11 欄 → 核准後原樣 replay → consume 必過（#10 失敗的那一步）。
r = server.record_transaction(type="expense", amount=18000, category="設備",
                               description="伺服器", transaction_date="2026-01-20",
                               business_unit="brand_a", payment_status="paid")
_assert("p2.13: #183 超門檻無 approved_id → 系統自建審核（非舊字串、不叫 agent create_approval）",
        "已自動建立審核" in r and "#" in r and "create_approval" not in r, detail=r[:200])

db = server.get_db()
_auto_row = db.execute(
    "SELECT id, detail, status FROM approvals WHERE summary LIKE '%伺服器%' "
    "ORDER BY id DESC LIMIT 1"
).fetchone()
db.close()
auto_appr_id = _auto_row[0]
_auto_detail = json.loads(_auto_row[1])
_auto_rp = _auto_detail.get("resume_params", {})
_REQ_11 = {"type", "amount", "category", "description", "transaction_date",
           "related_customer_id", "related_order_id", "related_invoice",
           "business_unit", "payment_status", "due_date"}
_assert("p2.13: #183 自建審核 status=waiting", _auto_row[2] == "waiting")
_assert("p2.13: #183 自建 resume_params 完整 11 欄（非 4 欄）",
        set(_auto_rp.keys()) == _REQ_11, detail=f"keys={sorted(_auto_rp.keys())}")
_assert("p2.13: #183 resume_action=record_transaction",
        _auto_detail.get("resume_action") == "record_transaction")

# 自建審核同時觸發 approval_pending 上報（#23、簽核人會被通知）
db = server.get_db()
_esc_cnt = db.execute(
    "SELECT COUNT(*) FROM pending_escalations WHERE event_type='approval_pending' "
    "AND summary LIKE ?", (f"%#{auto_appr_id}（%",)
).fetchone()[0]
db.close()
_assert("p2.13: #183 自建審核觸發 approval_pending 上報", _esc_cnt >= 1,
        detail=f"escalations={_esc_cnt}")

# 核准 → 原樣 replay 鎖定的 resume_params → consume 必成功（#10 回歸：4 欄會在這步被擋）
server.resolve_approval(approval_id=auto_appr_id, decision="approved", decided_by="老闆")
r = server.record_transaction(approved_id=auto_appr_id, **_auto_rp)
_assert("p2.13: #183 自建審核 replay resume_params → consume 成功（#10 回歸）",
        "帳目" in r and "#" in r, detail=r[:200])

# round-2 MED：完整 resume_params 綁定 — 同金額同類型但改 category / related_invoice 也要擋
# （防「拿同一張已核准 approval 改掛別的發票/類別後執行」）
_bind_rp = {
    "type": "expense", "amount": 7700, "category": "設備",
    "description": "綁定測試", "transaction_date": "2026-01-15",
    "related_customer_id": 0, "related_order_id": 0, "related_invoice": "INV-AAA",
    "business_unit": "", "payment_status": "paid", "due_date": "",
}
def _mk_bind_appr(summary):
    server.create_approval(type="expense", summary=summary,
                           detail=json.dumps({"resume_action": "record_transaction",
                                              "resume_params": _bind_rp}, ensure_ascii=False),
                           approver="老闆", requester="員工A")
    _bdb = server.get_db()
    _bid = _bdb.execute("SELECT id FROM approvals WHERE summary = ? AND status = 'waiting'",
                        (summary,)).fetchone()[0]
    _bdb.close()
    server.resolve_approval(approval_id=_bid, decision="approved", decided_by="老闆")
    return _bid

r = server.record_transaction(type="expense", amount=7700, category="餐飲",
                               description="綁定測試", transaction_date="2026-01-15",
                               related_invoice="INV-AAA", payment_status="paid",
                               approved_id=_mk_bind_appr("綁定測試-改類別"))
_assert("p2.13: full-bind — tampered category blocked",
        "ERROR" in r and "不符" in r and "category" in r, detail=r[:160])

r = server.record_transaction(type="expense", amount=7700, category="設備",
                               description="綁定測試", transaction_date="2026-01-15",
                               related_invoice="INV-EVIL", payment_status="paid",
                               approved_id=_mk_bind_appr("綁定測試-改發票"))
_assert("p2.13: full-bind — tampered related_invoice blocked",
        "ERROR" in r and "不符" in r and "related_invoice" in r, detail=r[:160])

# create_order 也跑 happy path + reuse 擋
order_items = json.dumps([{"sku": "SKU-001", "name": "香氛蠟燭", "qty": 1, "price": 500}])
order_appr_detail = json.dumps({
    "resume_action": "create_order",
    "resume_params": {
        "customer_id": 1, "items_json": order_items,
        "notes": "", "business_unit": "brand_a", "created_by": "test",
    },
}, ensure_ascii=False)
server.create_approval(type="purchase", summary="approval 訂單測試",
                       detail=order_appr_detail, approver="老闆", requester="test")
db = server.get_db()
order_appr_id = db.execute(
    "SELECT id FROM approvals WHERE summary = 'approval 訂單測試' AND status = 'waiting'"
).fetchone()[0]
db.close()
server.resolve_approval(approval_id=order_appr_id, decision="approved", decided_by="老闆")

r = server.create_order(customer_id=1, items_json=order_items,
                         business_unit="brand_a", created_by="test",
                         approved_id=order_appr_id)
_assert("p2.13: create_order with valid approval succeeds",
        "訂單" in r and "#" in r, detail=r[:200])

# 同一 order approval 重用 → 擋
r = server.create_order(customer_id=1, items_json=order_items,
                         business_unit="brand_a", created_by="test",
                         approved_id=order_appr_id)
_assert("p2.13: HIGH — create_order approval reuse blocked",
        "ERROR" in r and ("已使用" in r or "不存在" in r), detail=r[:200])

db = server.get_db()
row = db.execute(
    "SELECT consumed_by_type FROM approvals WHERE id = ?", (order_appr_id,)
).fetchone()
db.close()
_assert("p2.13: order approval consumed_by_type=order",
        row[0] == "order", detail=f"consumed_by_type={row[0]}")


# --- Codex audit round 2 補測：reject / expired / malformed / rollback / 邊界值 ---

# rejected approval 拿 approved_id 用 → 擋
server.create_approval(type="expense", summary="會被駁回的請款",
                       detail=json.dumps({
                           "resume_action": "record_transaction",
                           "resume_params": {
                               "type": "expense", "amount": 9000,
                               "business_unit": "",
                           },
                       }, ensure_ascii=False),
                       approver="老闆", requester="test")
db = server.get_db()
rej_appr_id = db.execute(
    "SELECT id FROM approvals WHERE summary = '會被駁回的請款' AND status = 'waiting'"
).fetchone()[0]
db.close()
server.resolve_approval(approval_id=rej_appr_id, decision="rejected", decided_by="老闆")
r = server.record_transaction(type="expense", amount=9000, category="設備",
                               description="拿 rejected approval", payment_status="paid",
                               approved_id=rej_appr_id)
_assert("p2.13: rejected approval blocked",
        "ERROR" in r and ("不存在" in r or "未核准" in r), detail=r[:200])

# expired approval：直接 DB UPDATE 模擬 expired
server.create_approval(type="expense", summary="即將過期的請款",
                       detail=json.dumps({
                           "resume_action": "record_transaction",
                           "resume_params": {
                               "type": "expense", "amount": 9500,
                               "business_unit": "",
                           },
                       }, ensure_ascii=False),
                       approver="老闆", requester="test")
db = server.get_db()
exp_appr_id = db.execute(
    "SELECT id FROM approvals WHERE summary = '即將過期的請款' AND status = 'waiting'"
).fetchone()[0]
db.execute("UPDATE approvals SET status = 'expired' WHERE id = ?", (exp_appr_id,))
db.commit()
db.close()
r = server.record_transaction(type="expense", amount=9500, category="設備",
                               description="拿 expired approval", payment_status="paid",
                               approved_id=exp_appr_id)
_assert("p2.13: expired approval blocked",
        "ERROR" in r and ("不存在" in r or "未核准" in r), detail=r[:200])

# malformed detail (非 JSON 字串) → 擋
server.create_approval(type="expense", summary="壞 JSON",
                       detail="this is NOT json",
                       approver="老闆", requester="test")
db = server.get_db()
bad_appr_id = db.execute(
    "SELECT id FROM approvals WHERE summary = '壞 JSON' AND status = 'waiting'"
).fetchone()[0]
db.close()
server.resolve_approval(approval_id=bad_appr_id, decision="approved", decided_by="老闆")
r = server.record_transaction(type="expense", amount=7000, category="設備",
                               description="拿 malformed approval", payment_status="paid",
                               approved_id=bad_appr_id)
_assert("p2.13: malformed detail JSON blocked",
        "ERROR" in r and "格式錯誤" in r, detail=r[:200])

# round-4 MED：detail 是合法 JSON 但形狀錯（list / resume_params 非 dict）→ 乾淨 ERROR、不可拋例外
server.create_approval(type="expense", summary="detail 是 list",
                       detail='["x"]', approver="老闆", requester="test")
db = server.get_db()
list_detail_id = db.execute(
    "SELECT id FROM approvals WHERE summary = 'detail 是 list' AND status = 'waiting'"
).fetchone()[0]
db.close()
server.resolve_approval(approval_id=list_detail_id, decision="approved", decided_by="老闆")
r = server.record_transaction(type="expense", amount=5500, category="設備",
                               description="拿 list detail", payment_status="paid",
                               approved_id=list_detail_id)
_assert("p2.13: detail 是 list → 乾淨 ERROR（不拋例外）",
        "ERROR" in r and "格式錯誤" in r, detail=r[:200])

server.create_approval(type="expense", summary="resume_params 是 list",
                       detail='{"resume_action": "record_transaction", "resume_params": ["type"]}',
                       approver="老闆", requester="test")
db = server.get_db()
list_rp_id = db.execute(
    "SELECT id FROM approvals WHERE summary = 'resume_params 是 list' AND status = 'waiting'"
).fetchone()[0]
db.close()
server.resolve_approval(approval_id=list_rp_id, decision="approved", decided_by="老闆")
r = server.record_transaction(type="expense", amount=5600, category="設備",
                               description="拿 list resume_params", payment_status="paid",
                               approved_id=list_rp_id)
_assert("p2.13: resume_params 是 list → 乾淨 ERROR（不拋例外）",
        "ERROR" in r and "格式錯誤" in r, detail=r[:200])

# round-5 LOW：falsy 非 dict resume_params（[] / null）也要走「格式錯誤」、不可被 or {} 靜默吞
for _bad_label, _bad_detail, _bad_amt in [
    ("resume_params 空 list", '{"resume_action": "record_transaction", "resume_params": []}', 5700),
    ("resume_params 是 null", '{"resume_action": "record_transaction", "resume_params": null}', 5800),
]:
    server.create_approval(type="expense", summary=_bad_label, detail=_bad_detail,
                           approver="老闆", requester="test")
    _bdb = server.get_db()
    _bad_id = _bdb.execute("SELECT id FROM approvals WHERE summary = ? AND status = 'waiting'",
                           (_bad_label,)).fetchone()[0]
    _bdb.close()
    server.resolve_approval(approval_id=_bad_id, decision="approved", decided_by="老闆")
    r = server.record_transaction(type="expense", amount=_bad_amt, category="設備",
                                   description="拿 " + _bad_label, payment_status="paid",
                                   approved_id=_bad_id)
    _assert("p2.13: " + _bad_label + " → 乾淨 ERROR（格式錯誤、不拋例外）",
            "ERROR" in r and "格式錯誤" in r, detail=r[:200])

# missing detail 整段 → 擋（detail=None / 空）
db = server.get_db()
db.execute("INSERT INTO approvals (type, summary, detail, status) "
           "VALUES ('expense', 'no detail', NULL, 'approved')")
db.commit()
no_detail_id = db.execute(
    "SELECT id FROM approvals WHERE summary = 'no detail'"
).fetchone()[0]
db.close()
r = server.record_transaction(type="expense", amount=6000, category="設備",
                               description="拿 no-detail approval", payment_status="paid",
                               approved_id=no_detail_id)
_assert("p2.13: missing detail blocked",
        "ERROR" in r and "resume detail" in r, detail=r[:200])

# resume_params 缺欄位 → 擋（這次 detail JSON 缺 business_unit key）
server.create_approval(type="expense", summary="缺 business_unit",
                       detail=json.dumps({
                           "resume_action": "record_transaction",
                           "resume_params": {"type": "expense", "amount": 6500},
                       }, ensure_ascii=False),
                       approver="老闆", requester="test")
db = server.get_db()
no_bu_id = db.execute(
    "SELECT id FROM approvals WHERE summary = '缺 business_unit' AND status = 'waiting'"
).fetchone()[0]
db.close()
server.resolve_approval(approval_id=no_bu_id, decision="approved", decided_by="老闆")
r = server.record_transaction(type="expense", amount=6500, category="設備",
                               description="缺 key approval", payment_status="paid",
                               approved_id=no_bu_id)
_assert("p2.13: missing resume_params key blocked",
        "ERROR" in r and "approval 缺此欄位" in r, detail=r[:200])

# 浮點容差邊界：12000 vs 12000.009 → 擋（NT$ 整數場景嚴格、tolerance < 0.01）
server.create_approval(type="expense", summary="整數金額",
                       detail=json.dumps({
                           "resume_action": "record_transaction",
                           "resume_params": {
                               "type": "expense", "amount": 12000, "category": "設備",
                               "description": "整數浮點等價", "transaction_date": "2026-01-15",
                               "related_customer_id": 0, "related_order_id": 0,
                               "related_invoice": "", "business_unit": "",
                               "payment_status": "paid", "due_date": "",
                           },
                       }, ensure_ascii=False),
                       approver="老闆", requester="test")
db = server.get_db()
int_amt_id = db.execute(
    "SELECT id FROM approvals WHERE summary = '整數金額' AND status = 'waiting'"
).fetchone()[0]
db.close()
server.resolve_approval(approval_id=int_amt_id, decision="approved", decided_by="老闆")
r = server.record_transaction(type="expense", amount=12000.009, category="設備",
                               description="非整數塞入", payment_status="paid",
                               approved_id=int_amt_id)
_assert("p2.13: float tolerance — int 12000 vs 12000.009 blocked",
        "ERROR" in r and ("不符" in r or "amount" in r), detail=r[:200])

# 整數與整數浮點等價：12000 vs 12000.0 → 應通過
r = server.record_transaction(type="expense", amount=12000.0, category="設備",
                               description="整數浮點等價", transaction_date="2026-01-15",
                               payment_status="paid", approved_id=int_amt_id)
_assert("p2.13: int 12000 vs 12000.0 passes (whole numbers)",
        "帳目" in r and "#" in r, detail=r[:200])

# items_json 結構性比對：approval 存 compact JSON，caller 傳 spaces 多的 → 應通過
spaced_items = '[ {"sku": "SKU-001", "name": "香氛蠟燭",  "qty": 1, "price": 500} ]'
compact_items = json.dumps([{"sku": "SKU-001", "name": "香氛蠟燭", "qty": 1, "price": 500}])
server.create_approval(type="purchase", summary="結構性比對 — compact 存",
                       detail=json.dumps({
                           "resume_action": "create_order",
                           "resume_params": {
                               "customer_id": 1, "items_json": compact_items,
                               "business_unit": "brand_a",
                           },
                       }, ensure_ascii=False),
                       approver="老闆", requester="test")
db = server.get_db()
struct_appr_id = db.execute(
    "SELECT id FROM approvals WHERE summary = '結構性比對 — compact 存' AND status = 'waiting'"
).fetchone()[0]
db.close()
server.resolve_approval(approval_id=struct_appr_id, decision="approved", decided_by="老闆")
r = server.create_order(customer_id=1, items_json=spaced_items,
                         business_unit="brand_a", created_by="test",
                         approved_id=struct_appr_id)
_assert("p2.13: MEDIUM B — items_json structural compare (whitespace ignored)",
        "訂單" in r and "#" in r, detail=r[:250])

# items_json 真正不同（qty 不同）→ 擋
diff_qty_items = '[{"sku": "SKU-001", "name": "香氛蠟燭", "qty": 99, "price": 500}]'
server.create_approval(type="purchase", summary="結構性比對 — qty 不同",
                       detail=json.dumps({
                           "resume_action": "create_order",
                           "resume_params": {
                               "customer_id": 1, "items_json": compact_items,
                               "business_unit": "brand_a",
                           },
                       }, ensure_ascii=False),
                       approver="老闆", requester="test")
db = server.get_db()
diff_qty_id = db.execute(
    "SELECT id FROM approvals WHERE summary = '結構性比對 — qty 不同' AND status = 'waiting'"
).fetchone()[0]
db.close()
server.resolve_approval(approval_id=diff_qty_id, decision="approved", decided_by="老闆")
r = server.create_order(customer_id=1, items_json=diff_qty_items,
                         business_unit="brand_a", created_by="test",
                         approved_id=diff_qty_id)
_assert("p2.13: items_json different qty blocked",
        "ERROR" in r and ("不符" in r or "items_json" in r), detail=r[:250])

# _values_equivalent unit-style edge cases（codex round-3 補 MED + LOW）
from modules.approvals.service import _values_equivalent
# bool vs int 不等價（防 True==1 通過數值門檻）
_assert("p2.13: bool True vs int 1 → not equivalent",
        not _values_equivalent(True, 1))
_assert("p2.13: bool False vs int 0 → not equivalent",
        not _values_equivalent(False, 0))
_assert("p2.13: bool True vs bool True → equivalent",
        _values_equivalent(True, True))
# 超 float 精度大整數：2^53+1 跟 2^53+1 應等價（int 路徑）
big = (2 ** 53) + 1
_assert("p2.13: int 2^53+1 == 2^53+1 (int-int exact)",
        _values_equivalent(big, big))
# 2^53+1 vs 2^53+2 應不等（差異只在第一個無法被 float 表示的整數）
_assert("p2.13: int 2^53+1 != 2^53+2 (int-int exact)",
        not _values_equivalent(big, big + 1))
# int 跨型 vs float、float 為超界整數值會丟精度 → 應正確判不等
_assert("p2.13: int 2^53+1 vs float(2^53+1) → not equivalent (float loses precision)",
        not _values_equivalent(big, float(big)))
# nan != nan
_assert("p2.13: float nan vs nan → not equivalent",
        not _values_equivalent(float("nan"), float("nan")))
# inf == inf
_assert("p2.13: float inf vs inf → equivalent",
        _values_equivalent(float("inf"), float("inf")))
# Cross-type OverflowError 防護：huge int vs non-integer float（codex round-4 MED）
_assert("p2.13: int 10**400 vs float 1.5 → not equivalent (no OverflowError)",
        not _values_equivalent(10 ** 400, 1.5))
_assert("p2.13: float 1.5 vs int 10**400 → not equivalent (no OverflowError)",
        not _values_equivalent(1.5, 10 ** 400))

# 極大整數 amount（OverflowError 防護、codex round-2 LOW A2）→ 應乾淨 ERROR、不 crash
huge = 10 ** 400  # python int 無上限、轉 float 會 OverflowError
huge_detail = '{"resume_action": "record_transaction", "resume_params": {"type": "expense", "amount": ' + str(huge) + ', "business_unit": ""}}'
server.create_approval(type="expense", summary="超大整數金額",
                       detail=huge_detail, approver="老闆", requester="test")
db = server.get_db()
huge_appr_id = db.execute(
    "SELECT id FROM approvals WHERE summary = '超大整數金額' AND status = 'waiting'"
).fetchone()[0]
db.close()
server.resolve_approval(approval_id=huge_appr_id, decision="approved", decided_by="老闆")
r = server.record_transaction(type="expense", amount=12345, category="設備",
                               description="huge approval", payment_status="paid",
                               approved_id=huge_appr_id)
_assert("p2.13: LOW A2 — overflow-large amount returns clean ERROR (no crash)",
        "ERROR" in r and ("不符" in r or "amount" in r), detail=r[:200])

# mark_consumed rowcount=0 → RuntimeError 觸發 rollback（monkeypatch 模擬 race）
from modules.approvals import repository as _appr_repo
server.create_approval(type="expense", summary="rollback 路徑",
                       detail=json.dumps({
                           "resume_action": "record_transaction",
                           "resume_params": {
                               "type": "expense", "amount": 11000, "category": "設備",
                               "description": "rollback marker", "transaction_date": "2026-01-15",
                               "related_customer_id": 0, "related_order_id": 0,
                               "related_invoice": "", "business_unit": "",
                               "payment_status": "paid", "due_date": "",
                           },
                       }, ensure_ascii=False),
                       approver="老闆", requester="test")
db = server.get_db()
rollback_appr_id = db.execute(
    "SELECT id FROM approvals WHERE summary = 'rollback 路徑' AND status = 'waiting'"
).fetchone()[0]
db.close()
server.resolve_approval(approval_id=rollback_appr_id, decision="approved", decided_by="老闆")

orig_mark = _appr_repo.mark_consumed
_appr_repo.mark_consumed = lambda *a, **kw: 0  # 模擬 race：consume 落空
try:
    raised = False
    try:
        server.record_transaction(type="expense", amount=11000, category="設備",
                                   description="rollback marker", transaction_date="2026-01-15",
                                   payment_status="paid", approved_id=rollback_appr_id)
    except RuntimeError:
        raised = True
    _assert("p2.13: MEDIUM F — mark_consumed rowcount=0 raises RuntimeError",
            raised)
    db = server.get_db()
    bad_cnt = db.execute(
        "SELECT COUNT(*) FROM transactions WHERE description = 'rollback marker'"
    ).fetchone()[0]
    db.close()
    _assert("p2.13: MEDIUM F — RuntimeError rolls back transaction insert",
            bad_cnt == 0, detail=f"transactions with 'rollback marker' = {bad_cnt}")
finally:
    _appr_repo.mark_consumed = orig_mark


# === notifier 控制檔受保護路徑不變量（round-5/6：lock / 暫存 mcp-config 不可落 floor-writable /tmp）===

_section("notifier 控制檔受保護路徑")
from shared.escalation import _notifier_state_dir, _notifier_lock_path
import os as _os_ni
_old_lsd = _os_ni.environ.get("LINE_STATE_DIR")
try:
    _os_ni.environ["LINE_STATE_DIR"] = "/srv/protected/state"
    _assert("notifier: state dir 尊重 LINE_STATE_DIR",
            _notifier_state_dir() == "/srv/protected/state")
    _assert("notifier: lock 在 state dir 下、非 /tmp",
            _notifier_lock_path() == "/srv/protected/state/sme-notifier.lock"
            and not _notifier_lock_path().startswith("/tmp"))
    _os_ni.environ.pop("LINE_STATE_DIR", None)
    _assert("notifier: 無 LINE_STATE_DIR 時 fallback ~/.claude（非 /tmp）",
            _notifier_state_dir().endswith("/.claude/channels/line")
            and not _notifier_state_dir().startswith("/tmp"))
finally:
    if _old_lsd is None:
        _os_ni.environ.pop("LINE_STATE_DIR", None)
    else:
        _os_ni.environ["LINE_STATE_DIR"] = _old_lsd


# === #27 escalation 稽核硬化：來源層蓋章（系統讀 SME_FLOOR、非 LLM）+ 通報落 log + 永不匿名 ===

_section("#27 escalation 來源層蓋章 + 落 log")
from shared.escalation import (
    enqueue_escalation as _enq27, format_escalation_message as _fmt27,
    _floor_display as _fd27, _actor_text as _at27,
    flush_pending_escalations as _flush27, mark_sent_tool as _mark27,
)
from shared.db import transaction as _tx27, get_db as _getdb27
import os as _os27

# helper 單元（確定性人話、皆由 (source_floor, actor) 推導）
_assert("#27: _floor_display 空=全權限層（operator/cowork）",
        _fd27("") == "全權限層（operator/cowork）")
_assert("#27: _floor_display confidential=機密層", _fd27("confidential") == "機密層")
_assert("#27: _floor_display accounting=accounting 層", _fd27("accounting") == "accounting 層")
_assert("#27: _actor_text 空 actor 永不匿名（改標來源層、非「未具名」）",
        "全權限層" in _at27(None, "") and "未具名" not in _at27(None, ""))
_assert("#27: _actor_text __unverified__ 標未驗證+來源層",
        _at27("__unverified__", "accounting") == "未驗證身份（accounting 層）")
_assert("#27: _actor_text 具名+來源層", _at27("王小明", "accounting") == "王小明（accounting 層）")

# 來源層蓋章：operator 路徑（無 SME_FLOOR）→ source_floor 空/NULL，訊息標「全權限層」、不匿名
_saved_floor_27 = _os27.environ.pop("SME_FLOOR", None)
try:
    with _tx27() as _d27:
        _eid_op = _enq27(_d27, event_type="transaction_deleted",
                         summary="測試刪帳 #999（operator）", detail={"txn_id": 999},
                         actor_user_id="", business_unit="")
    _db_op = _getdb27()
    _row_op = _db_op.execute("SELECT * FROM pending_escalations WHERE id=?", (_eid_op,)).fetchone()
    _db_op.close()
    _assert("#27: enqueue 寫入 source_floor 欄（operator→空/NULL）",
            "source_floor" in _row_op.keys() and _row_op["source_floor"] in (None, ""))
    _msg_op = _fmt27(_row_op)
    _assert("#27: cron 訊息含【系統通報】抬頭", "【系統通報】" in _msg_op)
    _assert("#27: cron 訊息含來源層（operator→全權限層）",
            "來源層：" in _msg_op and "全權限層" in _msg_op)
    _assert("#27: operator 空 actor 訊息不出現「未具名」", "未具名" not in _msg_op)

    # 落 log（notifier 路徑）：mark_sent_tool(sent_text=...) 落「實際送出內容」到 interaction_log
    _res_mark = _mark27(_eid_op, sent_text="【系統通報】帳目被刪除 #999（這是我送出的文字）")
    _db_m = _getdb27()
    _log_m = _db_m.execute(
        "SELECT detail FROM interaction_log WHERE action='escalation_sent' AND target_id=?",
        (_eid_op,)).fetchone()
    _db_m.close()
    _assert("#27(a): mark_sent_tool 落 notifier 送出內容到 interaction_log",
            _log_m is not None and "我送出的文字" in _log_m["detail"]
            and "[notifier→" in _log_m["detail"])
finally:
    if _saved_floor_27 is not None:
        _os27.environ["SME_FLOOR"] = _saved_floor_27

# 來源層蓋章：floored 路徑（SME_FLOOR=accounting）→ source_floor=accounting，訊息標「accounting 層」
_os27.environ["SME_FLOOR"] = "accounting"
try:
    with _tx27() as _d27b:
        _eid_fl = _enq27(_d27b, event_type="transaction_deleted",
                         summary="測試刪帳 #998（accounting 層）", actor_user_id="", business_unit="")
    _db_fl = _getdb27()
    _row_fl = _db_fl.execute("SELECT * FROM pending_escalations WHERE id=?", (_eid_fl,)).fetchone()
    _db_fl.close()
    _assert("#27: floored enqueue 蓋章 source_floor=accounting（系統讀 SME_FLOOR）",
            _row_fl["source_floor"] == "accounting")
    _assert("#27: floored 訊息來源層=accounting 層", "accounting 層" in _fmt27(_row_fl))
finally:
    _os27.environ.pop("SME_FLOOR", None)

# 落 log（cron 保證層）：flush 成功 → status=sent + 確定性送出內容入 interaction_log
with _tx27() as _d27c:
    _d27c.execute(
        "INSERT INTO pending_escalations (event_type, summary, actor, status, "
        "target_line_user_id, source_floor) "
        "VALUES ('transaction_deleted','測試刪帳 #996（cron）','王小明','pending','Ucron27','accounting')")
    _eid_cron = _d27c.execute("SELECT last_insert_rowid()").fetchone()[0]
_sent_27 = []
def _fake_push_27(ch, to, text):
    _sent_27.append((to, text)); return True
_flush27(_fake_push_27)
_db_c = _getdb27()
_log_c = _db_c.execute(
    "SELECT detail FROM interaction_log WHERE action='escalation_sent' AND target_id=?",
    (_eid_cron,)).fetchone()
_row_c = _db_c.execute("SELECT status FROM pending_escalations WHERE id=?", (_eid_cron,)).fetchone()
_db_c.close()
_assert("#27(a): cron flush 成功 → status=sent", _row_c["status"] == "sent")
_assert("#27(a): cron flush 落確定性送出內容到 interaction_log（含收件人 + 系統通報抬頭）",
        _log_c is not None and "[cron→Ucron27]" in _log_c["detail"]
        and "【系統通報】" in _log_c["detail"])
_assert("#27(a): cron 實際送出文字含來源層 accounting",
        any(_to == "Ucron27" and "accounting 層" in _t for _to, _t in _sent_27))

# --- codex#2：_actor_text 三類分明（空 actor=系統操作、非「未驗證的人」）---
_assert("#27(codex2): 空 actor + floored → 來源層系統操作（非未驗證身份）",
        _at27("", "accounting") == "accounting 層系統操作（無個別登入身份）"
        and "未驗證" not in _at27("", "accounting"))
_assert("#27(codex2): None actor + operator → 全權限層系統操作",
        _at27(None, "").startswith("全權限層 operator/cowork") and "系統操作" in _at27(None, ""))
_assert("#27(codex2): __unverified__ + floored → 未驗證身份（層）",
        _at27("__unverified__", "accounting") == "未驗證身份（accounting 層）")

# --- codex#4：__unexpanded__ sentinel 不漏給主管 ---
_assert("#27(codex4): _floor_display 特判 __unexpanded__（不漏 sentinel）",
        _fd27("__unexpanded__") == "未知受限層（SME_FLOOR 未展開）")

# --- codex#1：投遞租約 claim — fresh-claimed 不重送、stale-claimed reclaim、notifier lease 後 cron 不重送 ---
from shared.escalation import list_pending_for_notifier as _lst27
import json as _json27

# (1) fresh-claimed（剛被別路徑 claim）→ cron SELECT 排除、不重送
with _tx27() as _d27d:
    _d27d.execute(
        "INSERT INTO pending_escalations (event_type, summary, actor, status, "
        "target_line_user_id, source_floor, claimed_at) "
        "VALUES ('transaction_deleted','claim·fresh','王小明','pending','Ufresh27','accounting',"
        "datetime('now','localtime'))")
    _eid_fresh = _d27d.execute("SELECT last_insert_rowid()").fetchone()[0]
_sent_fresh = []
_flush27(lambda ch, to, t: (_sent_fresh.append(to) or True))
_db_f = _getdb27()
_st_fresh = _db_f.execute("SELECT status FROM pending_escalations WHERE id=?", (_eid_fresh,)).fetchone()["status"]
_db_f.close()
_assert("#27(codex1): fresh-claimed row 不被 cron 重送（仍 pending）",
        _st_fresh == "pending" and "Ufresh27" not in _sent_fresh)

# (1b) claimed 5 分前（< TTL 10 分）→ 即使比舊 3 分 TTL 久，仍不被 cron 提前 reclaim 重送（codex r2#1）
with _tx27() as _d27g:
    _d27g.execute(
        "INSERT INTO pending_escalations (event_type, summary, actor, status, "
        "target_line_user_id, source_floor, claimed_at) "
        "VALUES ('transaction_deleted','claim·within-ttl','王小明','pending','Uwithin27','accounting',"
        "datetime('now','localtime','-5 minutes'))")
    _eid_within = _d27g.execute("SELECT last_insert_rowid()").fetchone()[0]
_sent_within = []
_flush27(lambda ch, to, t: (_sent_within.append(to) or True))
_db_w = _getdb27()
_st_within = _db_w.execute("SELECT status FROM pending_escalations WHERE id=?", (_eid_within,)).fetchone()["status"]
_db_w.close()
_assert("#27(codex1·r2): claimed 5 分前（<TTL）不被 cron 提前 reclaim（慢 notifier 不重送）",
        _st_within == "pending" and "Uwithin27" not in _sent_within)

# (2) stale-claimed（>TTL 未完成）→ cron reclaim 並送出
with _tx27() as _d27e:
    _d27e.execute(
        "INSERT INTO pending_escalations (event_type, summary, actor, status, "
        "target_line_user_id, source_floor, claimed_at) "
        "VALUES ('transaction_deleted','claim·stale','王小明','pending','Ustale27','accounting',"
        "datetime('now','localtime','-15 minutes'))")
    _eid_stale = _d27e.execute("SELECT last_insert_rowid()").fetchone()[0]
_sent_stale = []
_flush27(lambda ch, to, t: (_sent_stale.append(to) or True))
_db_s = _getdb27()
_st_stale = _db_s.execute("SELECT status FROM pending_escalations WHERE id=?", (_eid_stale,)).fetchone()["status"]
_db_s.close()
_assert("#27(codex1): stale-claimed row（>TTL）被 cron reclaim 並送出",
        _st_stale == "sent" and "Ustale27" in _sent_stale)

# (3) notifier claim-on-read lease 後、同窗 cron flush 不重送；mark_sent 才標 sent + 落 log
with _tx27() as _d27f:
    _d27f.execute(
        "INSERT INTO pending_escalations (event_type, summary, actor, status, "
        "target_line_user_id, source_floor) "
        "VALUES ('transaction_deleted','claim·lease','王小明','pending','Ulease27','accounting')")
    _eid_lease = _d27f.execute("SELECT last_insert_rowid()").fetchone()[0]
_listed = _json27.loads(_lst27(limit=50))
_leased = any(_it["id"] == _eid_lease for _it in _listed["pending"])
_sent_lease = []
_flush27(lambda ch, to, t: (_sent_lease.append(to) or True))
_db_l = _getdb27()
_row_l = _db_l.execute("SELECT status, claimed_at FROM pending_escalations WHERE id=?", (_eid_lease,)).fetchone()
_db_l.close()
_assert("#27(codex1): list_pending_for_notifier claim-on-read（lease 該筆）",
        _leased and _row_l["claimed_at"] is not None)
_assert("#27(codex1): notifier 已 lease 的 row、同窗 cron flush 不重送（仍 pending）",
        "Ulease27" not in _sent_lease and _row_l["status"] == "pending")
_mark27(_eid_lease, sent_text="【系統通報】帳目被刪除（notifier lease 後送出）")
_db_l2 = _getdb27()
_st_lease2 = _db_l2.execute("SELECT status FROM pending_escalations WHERE id=?", (_eid_lease,)).fetchone()["status"]
_log_lease = _db_l2.execute(
    "SELECT detail FROM interaction_log WHERE action='escalation_sent' AND target_id=?",
    (_eid_lease,)).fetchone()
_db_l2.close()
_assert("#27(codex1): lease 後 mark_escalation_sent → sent + 落 notifier log",
        _st_lease2 == "sent" and _log_lease is not None and "lease 後送出" in _log_lease["detail"])

# (4) flush 失敗釋租後 backoff 未到：notifier list 與 cron flush 都看不到該 row（codex r2#2）
with _tx27() as _d27h:
    # retry_count=1 + last_attempt_at=now → backoff = 1*3 = 3 分未到；claimed_at=NULL（已釋租）
    _d27h.execute(
        "INSERT INTO pending_escalations (event_type, summary, actor, status, "
        "target_line_user_id, source_floor, retry_count, last_attempt_at, claimed_at) "
        "VALUES ('transaction_deleted','claim·backoff','王小明','pending','Ubackoff27','accounting',"
        "1, datetime('now','localtime'), NULL)")
    _eid_bo = _d27h.execute("SELECT last_insert_rowid()").fetchone()[0]
_listed_bo = _json27.loads(_lst27(limit=50))
_in_list_bo = any(_it["id"] == _eid_bo for _it in _listed_bo["pending"])
_sent_bo = []
_flush27(lambda ch, to, t: (_sent_bo.append(to) or True))
_db_bo = _getdb27()
_st_bo = _db_bo.execute("SELECT status, claimed_at FROM pending_escalations WHERE id=?", (_eid_bo,)).fetchone()
_db_bo.close()
_assert("#27(codex2·r2): backoff 未到 → notifier list 不 claim 該 row",
        not _in_list_bo and _st_bo["claimed_at"] is None)
_assert("#27(codex2·r2): backoff 未到 → cron flush 也不送該 row（仍 pending）",
        "Ubackoff27" not in _sent_bo and _st_bo["status"] == "pending")

# (5) cross-file 不變量 guard（codex r3）：把「投遞租約安全」綁到實際逾時常數、非註解假設。
#     notifier 單筆 push 上限由 line-channel/server.ts 的 LINE_PUSH_TIMEOUT_MS 綁死；
#     必須滿足 _NOTIFIER_CLAIM_BATCH × push 上限 << _CLAIM_TTL_MIN，否則慢批次會被 cron 提前 reclaim 重送。
import re as _re27
from shared.escalation import (
    _CLAIM_TTL_MIN as _ttl27, _NOTIFIER_CLAIM_BATCH as _batch27,
    _ASSUMED_MAX_PUSH_SEC as _push27,
)
_server_ts = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "line-channel", "server.ts"))
try:
    with open(_server_ts, encoding="utf-8") as _f27:
        _ts_src = _f27.read()
except OSError:
    _ts_src = ""
_m27 = _re27.search(r"LINE_PUSH_TIMEOUT_MS\s*=\s*([0-9_]+)", _ts_src)
_ts_timeout_sec = int(_m27.group(1).replace("_", "")) / 1000 if _m27 else None
_assert("#27(codex3): server.ts 有 LINE_PUSH_TIMEOUT_MS 且與 _ASSUMED_MAX_PUSH_SEC 對齊",
        _ts_timeout_sec is not None and _ts_timeout_sec == _push27)
_assert("#27(codex3): linePush + linePushFlex 都套 AbortSignal.timeout（單筆 push 有界）",
        _ts_src.count("AbortSignal.timeout(LINE_PUSH_TIMEOUT_MS)") >= 2)
# 安全餘裕：批量×單筆上限 < TTL 的一半（留 LLM 逐筆思考時間）
_assert("#27(codex3): 租約不變量 batch×push << TTL（含 LLM 思考餘裕）",
        _batch27 * _push27 < _ttl27 * 60 * 0.5)


# === #26 create_order 超門檻系統自建審核（比照 #183） ===

_section("#26 create_order 超門檻自建審核")

# company.approval_threshold=5000；金額拉到 100,000（客戶 #1 即使有折扣、打折後仍遠超門檻）
# → 應系統自建審核、不再印「create_approval(...)」要 agent 自己開（舊模式）。
_o26_items = json.dumps([{"sku": "SKU-001", "name": "香氛蠟燭", "qty": 100, "price": 1000}])
_r26 = server.create_order(customer_id=1, items_json=_o26_items,
                           business_unit="brand_a", created_by="員工A")
_assert("#26: 超門檻 create_order 系統自建審核（不再印 create_approval 指令給 agent）",
        "已自動建立審核" in _r26 and "create_approval(" not in _r26)

import re as _re26
_m26 = _re26.search(r"審核 #(\d+)", _r26)
_appr26 = int(_m26.group(1)) if _m26 else 0
_db26 = server.get_db()
_row26 = _db26.execute("SELECT type, detail FROM approvals WHERE id=?", (_appr26,)).fetchone()
_esc26 = _db26.execute(
    "SELECT COUNT(*) FROM pending_escalations WHERE event_type='approval_pending' AND summary LIKE ?",
    (f"#{_appr26}%",)).fetchone()[0]
_db26.close()
_assert("#26: 自建 approval 帶 resume_action=create_order（核准後 consume 對得上 gate verify_fields）",
        _row26 is not None and "resume_action" in (_row26["detail"] or "")
        and "create_order" in (_row26["detail"] or ""))
_assert("#26: 自建審核同時上報簽核人（approval_pending escalation 入列、與審核同 tx）",
        _esc26 >= 1)

# 核准後依鎖定參數執行 create_order(approved_id=…) consume 必過（一字不差、無需重填）
server.resolve_approval(approval_id=_appr26, decision="approved", decided_by="老闆")
_r26ok = server.create_order(customer_id=1, items_json=_o26_items,
                             business_unit="brand_a", created_by="員工A",
                             approved_id=_appr26)
_assert("#26: 核准後依鎖定參數 create_order(approved_id) consume 通過、訂單建立",
        "訂單" in _r26ok and "#" in _r26ok and "ERROR" not in _r26ok)


# === #10 update_employee admin-gate + 不可逆動作 audit 具名 ===

_section("#10 update_employee admin-gate + audit 具名")

# 種兩個測試員工：非 admin（basic）+ admin
server.register_employee(name="測試員工_basic10", role="staff",
                         line_user_id="Ustaff_t10", permissions="basic")
server.register_employee(name="測試主管_admin10", role="manager",
                         line_user_id="Uadmin_t10", permissions="admin")
server.register_employee(name="測試自改_admin10", role="manager",
                         line_user_id="Uself_t10", permissions="admin")
_dbid10 = server.get_db()
_selfid10 = _dbid10.execute(
    "SELECT id FROM employees WHERE line_user_id='Uself_t10'").fetchone()[0]
_dbid10.close()

import time as _time10
_sd10 = os.environ["LINE_STATE_DIR"]


def _set_active_request_10(user_id):
    """模擬 floored session 的 line-channel verified active-request（floor=hr）。"""
    with open(os.path.join(_sd10, "active-request-hr.json"), "w", encoding="utf-8") as _f:
        json.dump({"user_id": user_id, "written_ms": _time10.time() * 1000}, _f)


# floored（SME_FLOOR=hr）+ verified 非 admin → update_employee 被 admin-gate 擋下
os.environ["SME_FLOOR"] = "hr"
try:
    _set_active_request_10("Ustaff_t10")
    _r10block = server.update_employee(2, notes="不該成功_basic10")
    _assert("#10: floored 非 admin 改員工資料被擋（admin-gate、忽略 agent 自填 actor）",
            "ERROR" in _r10block and "權限不足" in _r10block)

    # floored + verified admin → 通過，且 audit log 記真實操作者（非 'system'）
    _set_active_request_10("Uadmin_t10")
    _r10ok = server.update_employee(2, notes="admin10_ok")
    _assert("#10: floored admin 改員工資料通過", "已更新" in _r10ok)
    _db10 = server.get_db()
    _log10 = _db10.execute(
        "SELECT actor FROM interaction_log WHERE action='employee_updated' "
        "ORDER BY id DESC LIMIT 1").fetchone()
    _db10.close()
    _assert("#10: update_employee audit 具名（記 verified 操作者名、非 'system'）",
            _log10 is not None and _log10["actor"] == "測試主管_admin10")

    # codex-HIGH 回歸：admin 改「自己」的 active=0（自我離職）→ 寫入後反查會找不到 active 員工，
    # audit / 上報的操作者名須靠「寫入前快取」、不可退回顯示內部 user_id。
    _set_active_request_10("Uself_t10")
    _r10self = server.update_employee(_selfid10, active=0)
    _assert("#10(codex-HIGH): admin 自我離職（active=0）仍成功", "已更新" in _r10self)
    _db10s = server.get_db()
    _log10s = _db10s.execute(
        "SELECT actor FROM interaction_log WHERE action='employee_updated' AND target_id=? "
        "ORDER BY id DESC LIMIT 1", (_selfid10,)).fetchone()
    _esc10s = _db10s.execute(
        "SELECT actor FROM pending_escalations WHERE event_type='employee_permissions_changed' "
        "AND summary LIKE ? ORDER BY id DESC LIMIT 1", (f"員工 #{_selfid10}%",)).fetchone()
    _db10s.close()
    _assert("#10(codex-HIGH): 自我離職 audit 記操作者名（寫入前快取、非退回 user_id）",
            _log10s is not None and _log10s["actor"] == "測試自改_admin10")
    _assert("#10(codex-HIGH): 自我離職 上報也記操作者名（actor_label 寫入前快取、非 user_id）",
            _esc10s is not None and _esc10s["actor"] == "測試自改_admin10")
finally:
    os.environ.pop("SME_FLOOR", None)
    try:
        os.remove(os.path.join(_sd10, "active-request-hr.json"))
    except OSError:
        pass

# operator 路徑（無 SME_FLOOR、空 actor）仍放行（全權限 / onboarding / CLI 不被擋）
_r10op = server.update_employee(2, notes="operator10_ok")
_assert("#10: operator（無 floor、空 actor）改員工資料仍放行（全權限路徑不被 admin-gate 擋）",
        "已更新" in _r10op)


# === Schema version check ===

_section("Migration runner")

db = server.get_db()
versions = db.execute("SELECT version, notes FROM schema_version ORDER BY version").fetchall()
db.close()
_assert("migration: schema_version table populated",
        len(versions) >= 1 and versions[0][0] == 1)


# === Summary ===

print("\n" + "=" * 60)
total = passed + failed
print(f"Results: {passed} passed, {failed} failed out of {total}")
if failed:
    print(f"\nFailures:")
    for name in failures:
        print(f"  - {name}")
    print(f"\nSOME TESTS FAILED")
    sys.exit(1)
else:
    print(f"\nALL TESTS PASSED")
    sys.exit(0)
