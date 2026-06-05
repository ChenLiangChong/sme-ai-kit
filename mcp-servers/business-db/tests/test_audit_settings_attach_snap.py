"""settings / attachments / snapshots 安全稽核單元測試（offline、standalone、不連網）。

跑法：
    cd mcp-servers/business-db
    SME_DB_PATH=/tmp/_t_sas.db /abs/.venv/bin/python3 tests/test_audit_settings_attach_snap.py

涵蓋（codex 全專案安全稽核三 finding）：
settings [HIGH]
- upsert_company / upsert_entity 改公司主設定 = 高權動作，需 admin（defense-in-depth）
  - operator（無 SME_FLOOR、空 actor）放行
  - floored basic 員工被擋（floored 取 verified user_id 驗權、agent 自填無效）
  - floored admin 員工放行
  - floored 無 verified LINE 脈絡 → 擋下（fail-closed）
  - 寫入留 audit（company_updated / business_entity_created）
attachments [MED]
- add_attachment 對不存在的 target_id / 未知 target_type 回 ERROR（防 dangling）
- target 真存在則正常新增
snapshots [MED]
- save_daily 重複呼叫不 raise（INSERT OR IGNORE upsert）、第二次全 skip
- 預存某 BU 快照後，save_daily 該筆 skip、其餘照存（單筆衝突不回滾整批）
"""
import atexit
import json as _j
import os
import re
import sys
import tempfile
import time as _t

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
DB_PATH = _tmp.name
_tmp.close()
os.environ["SME_DB_PATH"] = DB_PATH
os.environ.pop("SME_FLOOR", None)  # 預設 operator（全權限）路徑

_AR_DIR = tempfile.mkdtemp(prefix="sas_ar_")  # 隔離的 line-channel verified active-request 目錄


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
from modules.settings import service as ssvc  # noqa: E402
from modules.attachments import service as asvc  # noqa: E402
from modules.snapshots import service as snsvc  # noqa: E402

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


def _with_floor(floor, fn, user_id="Uadmin_test"):
    """暫時設 SME_FLOOR + 寫 line-channel verified active-request（模擬受限層 verified 員工）、跑 fn、
    用後還原。floored 寫入需 verified LINE 脈絡（真實由 line-channel 驗簽寫）；測試補上、否則撞 actor gate。"""
    old = os.environ.get("SME_FLOOR")
    old_lsd = os.environ.get("LINE_STATE_DIR")
    os.environ["SME_FLOOR"] = floor
    os.environ["LINE_STATE_DIR"] = _AR_DIR
    _arp = os.path.join(_AR_DIR, f"active-request-{floor}.json")
    wrote = False
    if user_id is not None:
        with open(_arp, "w", encoding="utf-8") as _f:
            _j.dump({"user_id": user_id, "written_ms": _t.time() * 1000}, _f)
        wrote = True
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
        if wrote:
            try:
                os.remove(_arp)
            except OSError:
                pass


# ── 種子員工：admin / basic（floored 驗權靠 line_user_id）+ 一個 task / customer ──
_exec("INSERT INTO employees (name, line_user_id, permissions, active) VALUES (?,?,?,1)",
      ("陳老闆", "Uadmin_test", "admin"))
_exec("INSERT INTO employees (name, line_user_id, permissions, active) VALUES (?,?,?,1)",
      ("小李", "Ubasic_test", "basic"))
_TASK_ID = _exec("INSERT INTO tasks (title, status) VALUES (?, 'pending')", ("測試任務",))
_CUST_ID = _exec("INSERT INTO customers (name, type) VALUES (?, 'customer')", ("測試客戶",))


# ============================================================
# settings [HIGH]：upsert_company / upsert_entity 需 admin
# ============================================================

# S1：operator（無 SME_FLOOR、空 actor）放行 → 首次建立公司
_s1 = ssvc.upsert_company(name="測試公司", industry="", boss_name="", boss_title="",
                          boss_line_id="__SKIP__", approval_threshold=-1, actor_user_id="")
_assert("S1: operator 路徑放行（建立公司）", "已建立" in _s1, detail=_s1)
_row_co = _q1("SELECT name FROM company WHERE id=1")
_assert("S1: 公司確實寫入", _row_co and _row_co["name"] == "測試公司")
_log_co = _q1("SELECT actor, action FROM interaction_log WHERE action='company_created' ORDER BY id DESC LIMIT 1")
_assert("S1: 建立留 audit（company_created）", _log_co is not None, detail=str(dict(_log_co)) if _log_co else "none")

# S2：floored basic 員工 → 權限不足擋下、且不寫入
_before = _q1("SELECT approval_threshold FROM company WHERE id=1")["approval_threshold"]
_s2 = _with_floor("general", lambda: ssvc.upsert_company(
    name="", industry="", boss_name="", boss_title="", boss_line_id="__SKIP__",
    approval_threshold=99999, actor_user_id="自填無效"), user_id="Ubasic_test")
_after = _q1("SELECT approval_threshold FROM company WHERE id=1")["approval_threshold"]
_assert("S2: floored basic 改門檻被擋（ERROR 權限不足）", _s2.startswith("ERROR") and "權限" in _s2, detail=_s2)
_assert("S2: 被擋後門檻未變（fail-closed 在寫入前）", _before == _after, detail=f"{_before}->{_after}")

# S3：floored admin 員工 → 放行 + audit actor 具名（verified 員工名、非自填）
_s3 = _with_floor("confidential_does_not_matter_uses_verified", lambda: ssvc.upsert_company(
    name="", industry="", boss_name="", boss_title="", boss_line_id="__SKIP__",
    approval_threshold=12000, actor_user_id="agent亂填"), user_id="Uadmin_test")
_assert("S3: floored admin 改門檻放行", "已更新" in _s3, detail=_s3)
_assert("S3: 門檻確實改成 12000", _q1("SELECT approval_threshold FROM company WHERE id=1")["approval_threshold"] == 12000)
_log_upd = _q1("SELECT actor FROM interaction_log WHERE action='company_updated' ORDER BY id DESC LIMIT 1")
_assert("S3: audit actor 為 verified 員工名（陳老闆）、非 agent 自填", _log_upd and _log_upd["actor"] == "陳老闆",
        detail=str(dict(_log_upd)) if _log_upd else "none")

# S4：floored 但無 verified LINE 脈絡（沒寫 active-request）→ fail-closed 擋下
_s4 = _with_floor("general", lambda: ssvc.upsert_company(
    name="", industry="", boss_name="", boss_title="", boss_line_id="__SKIP__",
    approval_threshold=55555, actor_user_id=""), user_id=None)
_assert("S4: floored 無 verified 脈絡 → 擋下（ERROR）", _s4.startswith("ERROR"), detail=_s4)
_assert("S4: 被擋後門檻仍 12000（未洩寫）", _q1("SELECT approval_threshold FROM company WHERE id=1")["approval_threshold"] == 12000)

# S5：upsert_entity 同樣需 admin — basic 擋、admin 放行 + audit
_s5a = _with_floor("general", lambda: ssvc.upsert_entity(
    entity_id="brand_x", name="X品牌", channel_id="", approval_threshold=-1, notes="",
    actor_user_id=""), user_id="Ubasic_test")
_assert("S5: floored basic 登錄事業體被擋", _s5a.startswith("ERROR") and "權限" in _s5a, detail=_s5a)
_assert("S5: 被擋後事業體未建立", _q1("SELECT id FROM business_entities WHERE id='brand_x'") is None)
_s5b = _with_floor("confidential", lambda: ssvc.upsert_entity(
    entity_id="brand_x", name="X品牌", channel_id="", approval_threshold=8000, notes="",
    actor_user_id=""), user_id="Uadmin_test")
_assert("S5: floored admin 登錄事業體放行", "已登錄" in _s5b, detail=_s5b)
_assert("S5: 事業體確實寫入", _q1("SELECT name FROM business_entities WHERE id='brand_x'") is not None)
_log_be = _q1("SELECT actor, business_unit FROM interaction_log WHERE action='business_entity_created' ORDER BY id DESC LIMIT 1")
_assert("S5: 事業體建立留 audit（actor=陳老闆、bu=brand_x）",
        _log_be and _log_be["actor"] == "陳老闆" and _log_be["business_unit"] == "brand_x",
        detail=str(dict(_log_be)) if _log_be else "none")


# ============================================================
# attachments [MED]：add_attachment 驗證 target 存在
# ============================================================

# A1：target 存在 → 正常新增
_a1 = asvc.add(target_type="task", target_id=_TASK_ID, file_path="/x/a.pdf", file_name="", description="", uploaded_by="")
_assert("A1: 對存在的 task 加附件成功", _id(_a1) is not None and "已新增" in _a1, detail=_a1)

# A2：target_id 不存在 → ERROR、不寫入
_n_before = _q1("SELECT COUNT(*) c FROM attachments")["c"]
_a2 = asvc.add(target_type="task", target_id=999999, file_path="/x/b.pdf", file_name="", description="", uploaded_by="")
_n_after = _q1("SELECT COUNT(*) c FROM attachments")["c"]
_assert("A2: 不存在的 task → ERROR", _a2.startswith("ERROR"), detail=_a2)
_assert("A2: 不寫 dangling 附件（count 不變）", _n_before == _n_after, detail=f"{_n_before}->{_n_after}")

# A3：customer 存在 → 成功
_a3 = asvc.add(target_type="customer", target_id=_CUST_ID, file_path="/x/c.png", file_name="", description="", uploaded_by="")
_assert("A3: 對存在的 customer 加附件成功", _id(_a3) is not None, detail=_a3)

# A4：未知 target_type → ERROR（白名單外一律擋）
_a4 = asvc.add(target_type="employee", target_id=1, file_path="/x/d.pdf", file_name="", description="", uploaded_by="")
_assert("A4: 未知 target_type → ERROR", _a4.startswith("ERROR") and "不支援" in _a4, detail=_a4)

# A5：order 不存在 → ERROR
_a5 = asvc.add(target_type="order", target_id=12345, file_path="/x/e.pdf", file_name="", description="", uploaded_by="")
_assert("A5: 不存在的 order → ERROR", _a5.startswith("ERROR"), detail=_a5)


# ============================================================
# snapshots [MED]：save_daily 原子 upsert、不 raise、單筆衝突不回滾整批
# ============================================================

# 先確保至少一個事業體存在（brand_x 已於 S5 建立）→ save_daily 會存「全域 + brand_x」
# Sn1：第一次 save_daily 成功
_sn1 = snsvc.save_daily()
_assert("Sn1: 首次 save_daily 成功（含全域）", "快照已儲存" in _sn1, detail=_sn1)
_today = _q1("SELECT snapshot_date FROM daily_snapshots ORDER BY id DESC LIMIT 1")["snapshot_date"]
_n_snap1 = _q1("SELECT COUNT(*) c FROM daily_snapshots")["c"]
_assert("Sn1: 全域 + brand_x 各一筆（共 2）", _n_snap1 == 2, detail=str(_n_snap1))

# Sn2：重複呼叫不 raise、全部 skip、不新增重複列
_sn2 = snsvc.save_daily()
_n_snap2 = _q1("SELECT COUNT(*) c FROM daily_snapshots")["c"]
_assert("Sn2: 第二次 save_daily 不 raise、回『已全部存在』", "已全部存在" in _sn2, detail=_sn2)
_assert("Sn2: 快照列數不變（無重複）", _n_snap2 == _n_snap1, detail=f"{_n_snap1}->{_n_snap2}")

# Sn3：單筆衝突不回滾整批 —— 刪掉全域快照、保留 brand_x，再 save_daily：全域應補回、brand_x skip
_exec("DELETE FROM daily_snapshots WHERE COALESCE(business_unit,'')=''")  # 刪全域
_n_before3 = _q1("SELECT COUNT(*) c FROM daily_snapshots")["c"]
_assert("Sn3 setup: 只剩 brand_x 一筆", _n_before3 == 1, detail=str(_n_before3))
_sn3 = snsvc.save_daily()
_has_global = _q1("SELECT COUNT(*) c FROM daily_snapshots WHERE COALESCE(business_unit,'')=''")["c"]
_n_brandx = _q1("SELECT COUNT(*) c FROM daily_snapshots WHERE business_unit='brand_x'")["c"]
_assert("Sn3: 不 raise、全域補回（brand_x 衝突未回滾全域）", "快照已儲存" in _sn3, detail=_sn3)
_assert("Sn3: 全域快照已補回（1 筆）", _has_global == 1, detail=str(_has_global))
_assert("Sn3: brand_x 仍只有 1 筆（衝突 skip、未重複）", _n_brandx == 1, detail=str(_n_brandx))


print(f"\n{'='*50}\n{passed} passed, {failed} failed")
if failures:
    print("FAILURES:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
sys.exit(0)
