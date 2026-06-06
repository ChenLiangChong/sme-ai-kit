"""auth active-request target_floor 一致性稽核測試（codex 修補複審 A-HIGH、offline、standalone、不連網）。

跑法：
    cd mcp-servers/business-db
    SME_DB_PATH=/tmp/_t_audit_auth.db /abs/.venv/bin/python3 tests/test_audit_auth.py

背景：line-channel 依 target_floor 寫 active-request-<floor>.json（檔名綁層）、檔內並蓋 target_floor 欄。
business-db floored session 只讀「自己這層」的檔當可信操作者來源（_read_active_request(floor)）。

修補複審 A-HIGH（第一輪只砍全域 fallback + 強制 written_ms、沒驗檔內層標）：
- 檔內 target_floor 必須等於本次請求的 floor，否則（被錯寫 / 殘留 / 跨層複製到本層檔名）視為非本層脈絡、
  fail-closed 回 None → _resolve_trusted_actor 回 __unverified__、寫入閘擋下。
- 向後相容：舊 line-channel 寫的檔可能無 target_floor 欄 → 不擋（但 written_ms 仍必須）。

涵蓋：
- target_floor 與請求 floor 相符 → 回 data（user_id 取得）。
- target_floor != 請求 floor → 回 None（fail-closed），即使 user_id / written_ms 都齊。
- 無 target_floor 欄（legacy）→ 不擋、回 data（written_ms 在效期內）。
- 缺 written_ms → 仍回 None（既有 fail-closed 行為不被新邏輯破壞）。
- 端到端：target_floor 不符時 _resolve_trusted_actor 回 __unverified__、writer_or_error 擋下寫入。
"""
import atexit
import json
import os
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

# 隔離的 line-channel state dir（active-request 檔放這、不碰真實 ~/.claude）
_STATE_DIR = tempfile.mkdtemp(prefix="auth_ar_")
os.environ["LINE_STATE_DIR"] = _STATE_DIR
os.environ.pop("SME_FLOOR", None)


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
from shared.auth import (  # noqa: E402
    _read_active_request,
    _resolve_trusted_actor,
    writer_or_error,
)

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


def _write_ar(floor: str, payload: dict):
    """寫 active-request-<floor>.json（模擬 line-channel writeActiveRequest 落檔）。"""
    p = os.path.join(_STATE_DIR, f"active-request-{floor}.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(payload, f)


def _clear_ar(floor: str):
    try:
        os.remove(os.path.join(_STATE_DIR, f"active-request-{floor}.json"))
    except OSError:
        pass


_NOW_MS = time.time() * 1000


# ============================================================
# T1：target_floor 與請求 floor 相符 → 回 data（正路）
# ============================================================
_write_ar("general", {"user_id": "Umatch_floor", "target_floor": "general", "written_ms": _NOW_MS})
_d1 = _read_active_request("general")
_assert("T1: target_floor 與請求 floor 相符 → 回 data", _d1 is not None and _d1.get("user_id") == "Umatch_floor",
        detail=str(_d1))
_clear_ar("general")


# ============================================================
# T2：target_floor != 請求 floor → fail-closed 回 None（即使 user_id / written_ms 齊）
#     模擬：別層脈絡（target_floor='accounting'）被錯寫 / 殘留 / 複製到本層檔名 active-request-general.json
# ============================================================
_write_ar("general", {"user_id": "Uother_floor_user", "target_floor": "accounting", "written_ms": _NOW_MS})
_d2 = _read_active_request("general")
_assert("T2: 檔內 target_floor=accounting 但讀 general → fail-closed 回 None（不信他層脈絡）",
        _d2 is None, detail=str(_d2))
_clear_ar("general")


# ============================================================
# T3：無 target_floor 欄（legacy 舊 line-channel）→ 不擋、回 data（向後相容、written_ms 在效期內）
# ============================================================
_write_ar("general", {"user_id": "Ulegacy_no_tf", "written_ms": _NOW_MS})
_d3 = _read_active_request("general")
_assert("T3: 無 target_floor 欄（legacy）→ 不擋、回 data（向後相容）",
        _d3 is not None and _d3.get("user_id") == "Ulegacy_no_tf", detail=str(_d3))
_clear_ar("general")


# ============================================================
# T4：缺 written_ms → 仍回 None（既有 fail-closed 不被新 target_floor 邏輯破壞；即使 target_floor 相符）
# ============================================================
_write_ar("general", {"user_id": "Uno_written_ms", "target_floor": "general"})
_d4 = _read_active_request("general")
_assert("T4: 缺 written_ms → 回 None（即使 target_floor 相符、時戳必填的 fail-closed 仍在）",
        _d4 is None, detail=str(_d4))
_clear_ar("general")


# ============================================================
# T5：逾 10 分鐘過期 → 回 None（target_floor 相符也擋）
# ============================================================
_write_ar("general", {"user_id": "Ustale", "target_floor": "general", "written_ms": _NOW_MS - 600_001})
_d5 = _read_active_request("general")
_assert("T5: written_ms 逾 10 分鐘 → 回 None（過期 fail-closed）", _d5 is None, detail=str(_d5))
_clear_ar("general")


# ============================================================
# T6：端到端 — target_floor 不符時 _resolve_trusted_actor 回 __unverified__、writer_or_error 擋下寫入
# ============================================================
# 建一個綁定 LINE user_id 的員工（若 verified 通過、應解析得到名字；本案應被 target_floor 擋下）
with transaction() as db:
    db.execute("INSERT INTO employees (name, line_user_id, permissions, active) VALUES (?,?,?,1)",
               ("陳會計", "Uother_floor_user", "manager"))

_saved_floor = os.environ.get("SME_FLOOR")
os.environ["SME_FLOOR"] = "general"
try:
    # 檔內 target_floor=accounting（他層）寫進 general 檔名 → 本層 general session 不該採信
    _write_ar("general", {"user_id": "Uother_floor_user", "target_floor": "accounting", "written_ms": _NOW_MS})
    _resolved = _resolve_trusted_actor("agent_自填_someone")  # floored 忽略 agent 自填
    _assert("T6: 端到端 — target_floor 不符 → _resolve_trusted_actor 回 __unverified__（非他層員工名）",
            _resolved == "__unverified__", detail=_resolved)
    _db_w = get_db()
    try:
        _label, _err = writer_or_error(_db_w, "agent_自填_someone")
    finally:
        _db_w.close()
    _assert("T6: 端到端 — writer_or_error 因 __unverified__ 擋下寫入（fail-closed）",
            _label is None and _err is not None and _err.startswith("ERROR"),
            detail=f"label={_label} err={_err}")
    _clear_ar("general")

    # 對照：target_floor 相符（general）→ _resolve_trusted_actor 解析得到 user_id、writer_or_error 通過具名
    _write_ar("general", {"user_id": "Uother_floor_user", "target_floor": "general", "written_ms": _NOW_MS})
    _resolved_ok = _resolve_trusted_actor("agent_自填_someone")
    _assert("T6: 對照 — target_floor 相符 → _resolve_trusted_actor 取 verified user_id",
            _resolved_ok == "Uother_floor_user", detail=_resolved_ok)
    _db_w2 = get_db()
    try:
        _label2, _err2 = writer_or_error(_db_w2, "agent_自填_someone")
    finally:
        _db_w2.close()
    _assert("T6: 對照 — target_floor 相符 → writer_or_error 通過、具名 verified 員工（陳會計）",
            _err2 is None and _label2 == "陳會計", detail=f"label={_label2} err={_err2}")
    _clear_ar("general")
finally:
    if _saved_floor is None:
        os.environ.pop("SME_FLOOR", None)
    else:
        os.environ["SME_FLOOR"] = _saved_floor


# === 收尾 ===
print(f"\n{'='*50}")
print(f"PASSED {passed}  FAILED {failed}")
if failures:
    print("FAILURES:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("ALL GREEN")
