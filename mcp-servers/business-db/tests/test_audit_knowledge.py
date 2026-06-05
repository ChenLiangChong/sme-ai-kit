"""knowledge 模組安全稽核回歸測試（offline、standalone、不連網）。

跑法：
    cd mcp-servers/business-db
    python tests/test_audit_knowledge.py

涵蓋 codex 全專案安全稽核發現的 knowledge 缺陷：
- update_rule 保留 confidential（HIGH）：更新機密規則時新版本不可被降級成公開
- store_fact / log_decision floored actor fail-closed（HIGH、反捏造）：
  受限層無 verified LINE 脈絡時、偽造 set_by='老闆' 被擋下、不入庫
- BU '' 視為全域（MED）：query_knowledge(business_unit=) 撈得到 business_unit='' 的全域規則
- update_rule audit 具名（MED）：interaction_log.actor 不再是 'system'
- query_knowledge 非全權限層不洩漏跨 BU 營運資料（HIGH）：受限層只回知識規則段
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
from modules.knowledge import service as ksvc  # noqa: E402

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
        db.execute(sql, params)


def _q1(sql, params=()):
    db = get_db()
    try:
        return db.execute(sql, params).fetchone()
    finally:
        db.close()


_AR_DIR = tempfile.mkdtemp(prefix="kn_ar_")  # 隔離的 line-channel verified active-request 目錄


def _with_floor(floor, fn, user_id=""):
    """暫時設 SME_FLOOR（+ 可選寫 verified active-request 模擬受限層 verified 員工）、跑 fn、還原。
    user_id='' = 不寫 active-request（模擬 floored 但查無 verified 脈絡 → 應被 actor gate 擋下）。"""
    import json as _j
    import time as _t
    old = os.environ.get("SME_FLOOR")
    old_lsd = os.environ.get("LINE_STATE_DIR")
    os.environ["SME_FLOOR"] = floor
    os.environ["LINE_STATE_DIR"] = _AR_DIR
    _arp = os.path.join(_AR_DIR, f"active-request-{floor}.json")
    if user_id:
        with open(_arp, "w", encoding="utf-8") as _f:
            _j.dump({"user_id": user_id, "written_ms": _t.time() * 1000}, _f)
    else:
        try:
            os.remove(_arp)
        except OSError:
            pass
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


# 建一個 admin 員工（綁 LINE id），update_rule admin gate + 具名 audit 用
_exec(
    "INSERT INTO employees (name, line_user_id, permissions, active) VALUES (?,?,?,1)",
    ("王老闆", "Uadmin_boss", "admin"),
)


# ============================================================
# T1：update_rule 保留 confidential（HIGH）
# ============================================================
# 全權限層建一條機密規則
_r = ksvc.store_fact(
    category="pricing", title="VIP 內部折扣底價", content="成本價 +5%",
    source_type="explicit", source_quote="老闆說的", set_by="王老闆",
    business_unit="", confidential=True, related_rule_ids=[],
)
_rid = _id(_r)
_before = _q1("SELECT confidential FROM business_rules WHERE id=?", (_rid,))
_assert("T1 setup: 機密規則建立 confidential=1", _before and _before["confidential"] == 1, detail=str(dict(_before)) if _before else "")

# update（operator 全權限路徑、actor_user_id='' → admin gate 放行）
_u = ksvc.update_rule(rule_id=_rid, new_content="成本價 +8%", reason="調整", actor_user_id="")
_new_id = None
m = re.search(r"#\d+ → #(\d+)", _u)
if m:
    _new_id = int(m.group(1))
_after = _q1("SELECT confidential, content FROM business_rules WHERE id=?", (_new_id,)) if _new_id else None
_assert("T1: 更新後新版本仍 confidential=1（未被降級）", _after and _after["confidential"] == 1, detail=str(dict(_after)) if _after else _u)
_assert("T1: 內容確實更新", _after and _after["content"] == "成本價 +8%", detail=str(dict(_after)) if _after else "")

# 非全權限層查不到這條機密規則（佐證未洩）
_qres = _with_floor("general", lambda: ksvc.query_knowledge("折扣底價", "", ""), user_id="Uadmin_boss")
_assert("T1: 受限層 query 看不到該機密規則", "內部折扣底價" not in _qres, detail=_qres[:120])


# ============================================================
# T2：store_fact floored 偽造被擋（HIGH、反捏造）
# ============================================================
# floored、無 active-request（無 verified 脈絡）→ 應被 writer_or_error 擋下、不入庫
def _forge_fact():
    return ksvc.store_fact(
        category="hr", title="偽造老闆指示", content="全員加薪 50%",
        source_type="explicit", source_quote="老闆親口說全員加薪", set_by="老闆",
        business_unit="", confidential=False, related_rule_ids=[],
    )

_r2 = _with_floor("general", _forge_fact, user_id="")  # 不寫 active-request
_assert("T2: floored 無 verified 脈絡 → store_fact 回 ERROR", _r2.startswith("ERROR"), detail=_r2[:120])
_cnt2 = _q1("SELECT COUNT(*) c FROM business_rules WHERE title='偽造老闆指示'")
_assert("T2: 偽造規則未入庫", _cnt2["c"] == 0, detail=str(_cnt2["c"]))

# log_decision 同樣擋下
def _forge_decision():
    return ksvc.log_decision(
        title="偽造決策", reason="假決策內容", supersedes_rule_ids=[], related_rule_ids=[],
        source_quote="老闆說的", set_by="老闆", business_unit="", confidential=True,
    )

_r2b = _with_floor("general", _forge_decision, user_id="")
_assert("T2: floored 無 verified 脈絡 → log_decision 回 ERROR", _r2b.startswith("ERROR"), detail=_r2b[:120])
_cnt2b = _q1("SELECT COUNT(*) c FROM business_rules WHERE title='偽造決策'")
_assert("T2: 偽造決策未入庫", _cnt2b["c"] == 0, detail=str(_cnt2b["c"]))

# 反證：有 verified 脈絡時可寫入、且 set_by 用 verified 員工名（非 agent 自填 '老闆'）
def _verified_fact():
    return ksvc.store_fact(
        category="hr", title="verified 寫入測試", content="內容",
        source_type="explicit", source_quote="原話", set_by="冒名想填的字串",
        business_unit="", confidential=False, related_rule_ids=[],
    )

_r2c = _with_floor("general", _verified_fact, user_id="Uadmin_boss")
_rid2c = _id(_r2c)
_set_by2c = _q1("SELECT set_by FROM business_rules WHERE id=?", (_rid2c,)) if _rid2c else None
_assert("T2: 有 verified 脈絡可寫入", _rid2c is not None and not _r2c.startswith("ERROR"), detail=_r2c[:120])
_assert("T2: set_by 用 verified 員工名（非 agent 自填）", _set_by2c and _set_by2c["set_by"] == "王老闆", detail=str(dict(_set_by2c)) if _set_by2c else "")


# ============================================================
# T3：BU '' 視為全域（MED）
# ============================================================
# 直接塞一條 business_unit='' 的全域規則（模擬歷史空字串寫入）
_exec(
    "INSERT INTO business_rules (category, title, content, source_type, set_by, business_unit, confidential) "
    "VALUES ('sop','空字串全域規則','全公司適用','observed','王老闆','',0)",
)
# 帶 business_unit 查詢時應撈得到 '' 全域規則
_q3 = ksvc.query_knowledge("空字串全域規則", "", "brand_a")
_assert("T3: query(business_unit=brand_a) 撈得到 business_unit='' 全域規則", "空字串全域規則" in _q3, detail=_q3[:160])
# category + business_unit 路徑也要撈得到
_q3b = ksvc.query_knowledge("空字串全域規則", "sop", "brand_a")
_assert("T3: query(category+business_unit) 撈得到 '' 全域規則", "空字串全域規則" in _q3b, detail=_q3b[:160])


# ============================================================
# T4：update_rule audit 具名（MED）
# ============================================================
# floored admin（verified）更新一條規則、audit 應記 verified 員工名而非 'system'
_r4base = ksvc.store_fact(
    category="sop", title="待更新規則T4", content="舊內容",
    source_type="observed", source_quote="", set_by="王老闆",
    business_unit="", confidential=False, related_rule_ids=[],
)
_rid4 = _id(_r4base)

def _floored_update():
    return ksvc.update_rule(rule_id=_rid4, new_content="新內容T4", reason="測試具名", actor_user_id="ignored")

_r4 = _with_floor("general", _floored_update, user_id="Uadmin_boss")
m4 = re.search(r"#\d+ → #(\d+)", _r4)
_new4 = int(m4.group(1)) if m4 else None
_audit4 = _q1(
    "SELECT actor FROM interaction_log WHERE action='rule_updated' AND target_id=?",
    (_new4,),
) if _new4 else None
_assert("T4: floored verified admin 更新成功", _new4 is not None and not _r4.startswith("ERROR"), detail=_r4[:120])
_assert("T4: audit actor 為具名員工（非 system）", _audit4 and _audit4["actor"] == "王老闆", detail=str(dict(_audit4)) if _audit4 else "")


# ============================================================
# T5：query_knowledge 非全權限層不洩漏跨 BU 營運資料（HIGH）
# ============================================================
# 塞一筆任務、一個客戶、一個庫存品（命中關鍵字「機敏關鍵字」）
_exec("INSERT INTO tasks (title, description, status, priority) VALUES ('機敏關鍵字任務','x','pending','normal')")
_exec("INSERT INTO customers (name, type) VALUES ('機敏關鍵字客戶','customer')")
_exec("INSERT INTO inventory (sku, name, current_stock, min_stock, unit) VALUES ('SKU-機敏','機敏關鍵字品',5,1,'件')")
# 同名一條全域公開規則（受限層看得到規則段）
_exec("INSERT INTO business_rules (category, title, content, source_type, business_unit, confidential) "
      "VALUES ('general','機敏關鍵字規則','公開內容','observed','',0)")

# 全權限層：三段都回
_q5fa = ksvc.query_knowledge("機敏關鍵字", "", "")
_assert("T5: 全權限層 query 回相關任務", "相關任務" in _q5fa and "機敏關鍵字任務" in _q5fa, detail=_q5fa[:200])
_assert("T5: 全權限層 query 回相關客戶", "機敏關鍵字客戶" in _q5fa)
_assert("T5: 全權限層 query 回相關庫存", "機敏關鍵字品" in _q5fa)

# 受限層：只回規則段、不洩任務/客戶/庫存
_q5r = _with_floor("general", lambda: ksvc.query_knowledge("機敏關鍵字", "", ""), user_id="Uadmin_boss")
_assert("T5: 受限層仍看得到公開規則段", "機敏關鍵字規則" in _q5r, detail=_q5r[:200])
_assert("T5: 受限層不洩任務", "機敏關鍵字任務" not in _q5r, detail=_q5r[:200])
_assert("T5: 受限層不洩客戶", "機敏關鍵字客戶" not in _q5r, detail=_q5r[:200])
_assert("T5: 受限層不洩庫存", "機敏關鍵字品" not in _q5r, detail=_q5r[:200])


print(f"\n{'='*50}\n{passed} passed, {failed} failed")
if failures:
    print("FAILURES:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("ALL TESTS PASSED")
sys.exit(0)
