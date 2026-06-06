"""notifications 模組安全稽核單元測試（offline、standalone、不連網）。

跑法：
    cd mcp-servers/business-db
    SME_DB_PATH=/tmp/_t_notif.db /abs/.venv/bin/python3 tests/test_audit_notifications.py

涵蓋（defense-in-depth：受限層工具移除由 floor_policy.LINE_DATA_TOOLS 負責、本層 service 為第二道）：
- register_line_group：operator（無 SME_FLOOR）可寫 + audit 具名（傳入 actor）
- register_line_group：floored 但「無 verified LINE 脈絡」→ ERROR 擋下（不寫 row、不 raise）
- register_line_group：floored 有 verified 員工 → 用 verified 員工名寫入 + audit（忽略 agent 自填 actor）
- register_line_group：受限層覆寫既有群組（update 路徑）同樣需 verified、未驗證擋下（防跨部門汙染）
- [修補複審 B-HIGH/E-HIGH] search_messages / list_line_groups（讀）受限層第二道防線：
  is_full_access() 早退、非全權限層回 ERROR（萬一工具未被 floor gate 移除仍擋）；全權限層正常可讀。
- 結構性：service / tools 模組可 import（無語法/相依錯）
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
os.environ.pop("SME_FLOOR", None)  # 起始為 operator（全權限）


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
from modules.notifications import service as nsvc  # noqa: E402

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


def _q1(sql, params=()):
    db = get_db()
    try:
        return db.execute(sql, params).fetchone()
    finally:
        db.close()


def _exec(sql, params=()):
    with transaction() as db:
        db.execute(sql, params)


_AR_DIR = tempfile.mkdtemp(prefix="notif_ar_")  # 隔離的 line-channel verified active-request 目錄


def _with_floor(floor, fn, user_id=None):
    """暫時設 SME_FLOOR；user_id 給定時寫 line-channel verified active-request（模擬受限層 verified 員工），
    None 時不寫（模擬 floored 但無 verified 脈絡）。跑 fn、用後還原。"""
    import json as _j
    import time as _t
    old = os.environ.get("SME_FLOOR")
    old_lsd = os.environ.get("LINE_STATE_DIR")
    os.environ["SME_FLOOR"] = floor
    os.environ["LINE_STATE_DIR"] = _AR_DIR
    _arp = os.path.join(_AR_DIR, f"active-request-{floor}.json")
    if user_id is not None:
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


# ============================================================
# T0：模組可 import（無語法/相依錯）
# ============================================================
import modules.notifications.service  # noqa: E402,F401
import modules.notifications.tools  # noqa: E402,F401
_assert("T0: notifications service / tools 可 import", True)


# ============================================================
# T1：operator（無 SME_FLOOR）可寫 + audit 具名
# ============================================================
_r1 = nsvc.register_line_group(
    group_id="Gop001", group_name="總公司工作群", group_type="work",
    channel_id="", purpose="內勤協調", notes="", actor="老闆",
)
_assert("T1: operator 註冊成功（已註冊）", "已註冊" in _r1, detail=_r1)
_row1 = _q1("SELECT group_type, purpose FROM line_groups WHERE group_id=? AND channel_id='default'", ("Gop001",))
_assert("T1: 群組真的寫入 DB", _row1 is not None and _row1["group_type"] == "work", detail=str(dict(_row1)) if _row1 else "None")
_aud1 = _q1("SELECT actor, action FROM interaction_log WHERE target_type='line_group' AND detail LIKE '%Gop001%' ORDER BY id DESC LIMIT 1")
_assert("T1: audit 具名（actor=老闆、非 system）", _aud1 is not None and _aud1["actor"] == "老闆", detail=str(dict(_aud1)) if _aud1 else "None")


# ============================================================
# T2：floored 但「無 verified LINE 脈絡」→ ERROR 擋下（不寫 row、不 raise）
# ============================================================
def _restricted_no_verify():
    return nsvc.register_line_group(
        group_id="Gevil001", group_name="冒名群", group_type="customer",
        channel_id="", purpose="跨部門汙染嘗試", notes="", actor="老闆",  # agent 自填 actor 無效
    )


_r2 = _with_floor("general", _restricted_no_verify, user_id=None)
_assert("T2: floored 無 verified → ERROR 擋下", _r2.startswith("ERROR"), detail=_r2[:120])
_row2 = _q1("SELECT id FROM line_groups WHERE group_id=?", ("Gevil001",))
_assert("T2: 被擋下時未寫入任何群組 row（fail-closed 在寫入前）", _row2 is None)


# ============================================================
# T3：floored 有 verified 員工 → 用 verified 員工名寫入 + audit（忽略 agent 自填 actor）
# ============================================================
# 先建一個綁定 LINE user_id 的員工（verified 解析得到名字）
_exec("INSERT INTO employees (name, line_user_id, permissions, active) VALUES (?,?,?,1)",
      ("林助理", "Uverified_notif_test", "basic"))


def _restricted_verified():
    return nsvc.register_line_group(
        group_id="Gok001", group_name="部門群", group_type="work",
        channel_id="", purpose="部門協調", notes="", actor="老闆",  # agent 自填、應被忽略
    )


_r3 = _with_floor("general", _restricted_verified, user_id="Uverified_notif_test")
_assert("T3: floored 有 verified → 註冊成功", "已註冊" in _r3, detail=_r3)
_aud3 = _q1("SELECT actor FROM interaction_log WHERE target_type='line_group' AND detail LIKE '%Gok001%' ORDER BY id DESC LIMIT 1")
_assert("T3: audit 用 verified 員工名（林助理）、非 agent 自填（老闆）",
        _aud3 is not None and _aud3["actor"] == "林助理", detail=str(dict(_aud3)) if _aud3 else "None")


# ============================================================
# T4：受限層覆寫既有群組（update 路徑）同樣需 verified —— 未驗證擋下（防跨部門汙染）
# ============================================================
# operator 先建一個既有群組
nsvc.register_line_group(
    group_id="Gshared001", group_name="共用群", group_type="work",
    channel_id="", purpose="原始用途", notes="", actor="老闆",
)


def _restricted_overwrite_no_verify():
    return nsvc.register_line_group(
        group_id="Gshared001", group_name="", group_type="marketing",  # 想竄改 type
        channel_id="", purpose="竄改用途", notes="", actor="老闆",
    )


_r4 = _with_floor("general", _restricted_overwrite_no_verify, user_id=None)
_assert("T4: floored 無 verified 覆寫 → ERROR 擋下", _r4.startswith("ERROR"), detail=_r4[:120])
_row4 = _q1("SELECT group_type, purpose FROM line_groups WHERE group_id=? AND channel_id='default'", ("Gshared001",))
_assert("T4: 既有群組未被竄改（仍 work / 原始用途）",
        _row4 is not None and _row4["group_type"] == "work" and _row4["purpose"] == "原始用途",
        detail=str(dict(_row4)) if _row4 else "None")


# ============================================================
# T5：[修補複審 B-HIGH/E-HIGH] search_messages / list_line_groups 受限層第二道防線（is_full_access 早退）
#     工具已由 floor_policy.LINE_DATA_TOOLS 物理移除（第一道），這裡測 service 層 defense-in-depth：
#     萬一工具未被移除（floor-map 設定錯 / 名單漏列），受限層仍被擋下、不洩漏全公司 LINE 訊息 / 群組。
# ============================================================
# operator（全權限）先確認讀路徑正常（非全擋）：search 無資料回「沒有找到」、list 有 T1~T4 寫入的群組
_r5_op_search = nsvc.search_messages(
    query="", user_id="", user_name="", direction="", channel_id="", days=7, limit=30)
_assert("T5: operator search_messages 可讀（非 ERROR、走正常查詢路徑）",
        not _r5_op_search.startswith("ERROR"), detail=_r5_op_search[:120])
_r5_op_list = nsvc.list_line_groups(group_type="", channel_id="")
_assert("T5: operator list_line_groups 可讀（非 ERROR、列出既有群組）",
        not _r5_op_list.startswith("ERROR") and "LINE 群組" in _r5_op_list, detail=_r5_op_list[:120])

# 受限層（general）→ search / list 被 is_full_access() 早退擋下（回 ERROR、不查 DB、不洩漏）
_r5_r_search = _with_floor(
    "general",
    lambda: nsvc.search_messages(query="機密", user_id="", user_name="", direction="",
                                 channel_id="", days=30, limit=50),
    user_id="Uverified_notif_test")
_assert("T5: 受限層 search_messages → ERROR 擋下（第二道防線、僅全權限可用）",
        _r5_r_search.startswith("ERROR") and "全權限層" in _r5_r_search, detail=_r5_r_search[:120])

_r5_r_list = _with_floor(
    "general",
    lambda: nsvc.list_line_groups(group_type="", channel_id=""),
    user_id="Uverified_notif_test")
_assert("T5: 受限層 list_line_groups → ERROR 擋下（第二道防線、僅全權限可用）",
        _r5_r_list.startswith("ERROR") and "全權限層" in _r5_r_list, detail=_r5_r_list[:120])

# __unexpanded__（fail-closed 受限未知層）→ 同樣擋下（is_full_access 對 __unexpanded__ 回 False）
_r5_unexp = _with_floor(
    "${SME_FLOOR}",
    lambda: nsvc.list_line_groups(group_type="", channel_id=""),
    user_id=None)
_assert("T5: __unexpanded__ fail-closed 層 list_line_groups → ERROR 擋下",
        _r5_unexp.startswith("ERROR"), detail=_r5_unexp[:120])


print(f"\n{'='*50}\n{passed} passed, {failed} failed")
if failures:
    print("FAILURES:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
sys.exit(0)
