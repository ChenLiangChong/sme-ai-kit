"""
Shared permission helpers — actor 權限驗證 + 跨 BU 警告 log。

Phase 1.2 抽出（codex review BLOCKER）：所有 module 都會 call _check_permission，
不能留在 server.py 否則拆 module 時形成 cycle。
"""
import os
import json
import time

_PERM_LEVEL = {"basic": 0, "manager": 1, "admin": 2}


def _read_active_request(floor: str = ""):
    """讀 line-channel 每則驗簽後寫的 active-request（可信操作者來源）。

    per-floor（決策 #164）：line-channel 依 target_floor 寫 active-request-<floor>.json，本 session 只讀
    自己這層的，避免多層同時在線跨層覆蓋誤歸因。先試 per-floor 檔、fallback 舊全域檔（部署順序無關）。
    此檔在 ~/.claude/channels/line 下、被 LINE-runtime 的 sandbox denyRead，agent 的 bash 碰不到、
    也無 Write 權限 → 無法偽造；只有非 sandbox 的 MCP 進程讀得到。超過 10 分鐘視為過期（防 crash 殘留誤歸因）。
    """
    base = os.environ.get("LINE_STATE_DIR") or os.path.expanduser("~/.claude/channels/line")
    candidates = []
    if floor:
        candidates.append(os.path.join(base, f"active-request-{floor}.json"))
    candidates.append(os.path.join(base, "active-request.json"))  # 舊全域、過渡相容
    for path in candidates:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        written_ms = data.get("written_ms", 0)
        if written_ms and (time.time() * 1000 - written_ms) > 600_000:
            continue
        return data
    return None


def _resolve_trusted_actor(actor_user_id: str) -> str:
    """決策 #162/#163：LINE-runtime(有 SME_FLOOR)的操作者一律取 line-channel 驗簽後的 verified
    user_id、忽略 agent 自填（防員工冒名他人 / 防傳空字串走「系統全通」）；operator/setup(無 SME_FLOOR)
    維持用傳入值（全權限路徑）。floored 但查不到當前 LINE 訊息脈絡 → 回非空 sentinel、權限檢查擋下。"""
    try:
        from shared.floor_policy import get_floor
        floor = get_floor()
    except Exception:
        floor = ""
    if not floor:
        return actor_user_id
    ar = _read_active_request(floor)
    if ar and ar.get("user_id"):
        return str(ar["user_id"])
    return "__unverified__"


def _check_permission(db, actor_user_id: str, required: str, business_unit: str = "") -> str:
    """Check actor permission. Returns empty string if OK, error message (starting with 'ERROR:') if denied.
    actor 一律經 _resolve_trusted_actor：LINE-runtime 取 line-channel verified user_id（agent 不可偽造），
    operator/setup(無 SME_FLOOR)才用傳入值；空字串=系統呼叫→放行（僅 operator 路徑可能為空）。
    business_unit: if provided, logs warning when employee is not assigned to that BU (does not block)."""
    actor_user_id = _resolve_trusted_actor(actor_user_id)
    if not actor_user_id:
        return ""
    emp = db.execute(
        "SELECT name, permissions, business_units FROM employees WHERE line_user_id = ? AND active = 1",
        (actor_user_id,),
    ).fetchone()
    if not emp:
        return "ERROR: 找不到該使用者的員工記錄，無法驗證權限"
    if _PERM_LEVEL.get(emp["permissions"], 0) < _PERM_LEVEL.get(required, 0):
        return f"ERROR: 權限不足 — {emp['name']}（{emp['permissions']}）需要 {required} 以上權限"
    # BU 驗證（soft warning — 不阻擋，記錄到 interaction_log 供追蹤）
    if business_unit and emp["business_units"]:
        allowed = [u.strip() for u in emp["business_units"].split(",")]
        if business_unit not in allowed:
            db.execute(
                "INSERT INTO interaction_log (actor, action, target_type, target_id, detail, business_unit) VALUES (?,?,?,?,?,?)",
                (emp["name"], "cross_bu_access", "employee", 0,
                 f"{emp['name']} 操作 {business_unit} 事業體（指派：{emp['business_units']}）", business_unit),
            )
            # REPORT 硬接線（#9/#173）：跨 BU 越權＝部門層唯一 agent 可達的 trigger。預設關
            # （高頻、會洗版、無 dedup）；is_escalation_enabled 預設不含 cross_bu_access → 下面 no-op、
            # 不寫 row。onboarding 想開要進 settings['escalation_triggers'] 並接受洗版（未來補 dedup）。
            # lazy import 避免載入順序脆弱（同 auth 既有 floor_policy lazy import）。
            from shared.escalation import enqueue_escalation
            enqueue_escalation(
                db,
                event_type="cross_bu_access",
                summary=f"{emp['name']} 越權存取 {business_unit} 事業體（指派：{emp['business_units']}）",
                detail={"employee": emp["name"], "accessed_bu": business_unit,
                        "assigned_bu": emp["business_units"]},
                actor_user_id=actor_user_id,
                business_unit=business_unit,
            )
    return ""


def _resolve_actor_label(db, actor_user_id: str) -> str:
    """回傳可信操作者的人類可讀標籤，供不可逆動作的 audit log（interaction_log.actor）具名。

    與 _check_permission 同源（先過 _resolve_trusted_actor）：floored 取 line-channel verified
    user_id 對應的員工名、operator/setup 用傳入值、查無對應員工則回原值、完全無值才回 'system'。
    決策 #10：刪除 / 離職等不可逆動作不可再記 actor='system'，audit 要追得到是誰做的。
    """
    resolved = _resolve_trusted_actor(actor_user_id)
    if not resolved or resolved == "__unverified__":
        return resolved or "system"
    emp = db.execute(
        "SELECT name FROM employees WHERE line_user_id = ? AND active = 1",
        (resolved,),
    ).fetchone()
    return emp["name"] if emp else resolved
