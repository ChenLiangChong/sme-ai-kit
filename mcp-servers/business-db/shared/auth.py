"""
Shared permission helpers — actor 權限驗證 + 跨 BU 警告 log。

Phase 1.2 抽出（codex review BLOCKER）：所有 module 都會 call _check_permission，
不能留在 server.py 否則拆 module 時形成 cycle。
"""
_PERM_LEVEL = {"basic": 0, "manager": 1, "admin": 2}


def _check_permission(db, actor_user_id: str, required: str, business_unit: str = "") -> str:
    """Check actor permission. Returns empty string if OK, error message (starting with 'ERROR:') if denied.
    actor_user_id='' means system/Cowork call → always allowed.
    business_unit: if provided, logs warning when employee is not assigned to that BU (does not block)."""
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
    return ""
