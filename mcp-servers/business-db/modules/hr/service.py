"""HR service — 員工 + 外包夥伴 業務邏輯。

層次邊界：transaction ownership 在這層，repository 不 commit。
IntegrityError（如 line_user_id 唯一性違反）在這層 catch + format error message。

修順手 fix：原 modules/hr/tools.py:49,131 使用 sqlite3.IntegrityError 但沒 import sqlite3，
P1 拆 module 遺留的 latent bug（smoke 沒覆蓋這條路徑沒爆）。三層化後在 service 層
顯式 import + catch。
"""
import sqlite3

from shared.auth import _check_permission, _resolve_actor_label
from shared.db import get_db, transaction
from shared.escalation import enqueue_escalation

from . import repository


# ---- employees ----

def register_employee(
    name: str,
    role: str,
    department: str,
    line_user_id: str,
    permissions: str,
    phone: str,
    business_units: str,
) -> str:
    try:
        with transaction() as db:
            emp_id = repository.insert_employee(
                db,
                name=name,
                role=role,
                department=department or None,
                line_user_id=line_user_id or None,
                permissions=permissions,
                phone=phone or None,
                business_units=business_units or None,
            )
            repository.insert_interaction_log(
                db,
                actor="system",
                action="employee_registered",
                target_type="employee",
                target_id=emp_id,
                detail=f"註冊 {name}（{role}/{permissions}）",
                business_unit=None,
            )
    except sqlite3.IntegrityError as e:
        if "line_user_id" in str(e):
            return "ERROR: 此 LINE 帳號已被其他員工綁定"
        return f"ERROR: {e}"

    bu_label = f" 事業體:{business_units}" if business_units else ""
    line_label = " LINE已綁定" if line_user_id else ""
    return f"員工 #{emp_id} {name} 已註冊（{role}/{permissions}）{bu_label}{line_label}"


def update_employee(
    employee_id: int,
    name: str,
    role: str,
    department: str,
    line_user_id: str,
    permissions: str,
    phone: str,
    business_units: str,
    active: int,
    notes: str,
    actor_user_id: str = "",
) -> str:
    updates: list[str] = []
    params: list = []
    if name:
        updates.append("name = ?"); params.append(name)
    if role:
        updates.append("role = ?"); params.append(role)
    if department:
        updates.append("department = ?"); params.append(department)
    if line_user_id != "__SKIP__":
        updates.append("line_user_id = ?"); params.append(line_user_id or None)
    if permissions:
        updates.append("permissions = ?"); params.append(permissions)
    if phone:
        updates.append("phone = ?"); params.append(phone)
    if business_units != "__SKIP__":
        updates.append("business_units = ?"); params.append(business_units or None)
    if active >= 0:
        updates.append("active = ?"); params.append(active)
    if notes:
        updates.append("notes = ?"); params.append(notes)

    if not updates:
        return "ERROR: 沒有指定要更新的欄位"

    try:
        with transaction() as db:
            # 決策 #10：改員工資料（permissions 自我提權 / business_units 擴權 / active 離職）
            # 屬不可逆 / 高風險、需 admin。floored 取 line-channel verified user_id（非 admin / 未驗證
            # 擋下、agent 自填無效）；operator（無 SME_FLOOR、空 actor）放行＝全權限路徑（onboarding / CLI）。
            perm_err = _check_permission(db, actor_user_id, "admin")
            if perm_err:
                return perm_err
            # codex-HIGH：在 safe_update_employee「之前」解析操作者名並快取。否則 admin 若在本次
            # 改自己的 line_user_id / active=0，寫入後 _resolve_actor_label / 上報反查會找不到 active
            # 員工 → 退回把內部 user_id 寫進 audit / 通報。audit 與上報都吃這份寫入前快取。
            actor_label = _resolve_actor_label(db, actor_user_id)
            rowcount = repository.safe_update_employee(db, employee_id, updates, params)
            if rowcount == 0:
                return f"ERROR: 找不到員工 #{employee_id}"
            changed = ", ".join(u.split(" = ")[0] for u in updates)
            repository.insert_interaction_log(
                db,
                actor=actor_label,
                action="employee_updated",
                target_type="employee",
                target_id=employee_id,
                detail=f"更新：{changed}",
                business_unit=None,
            )
            # REPORT 硬接線（#9/#173）：改 permissions/business_units/active＝自我提權/擴 BU/離職風險，
            # 主管必知（#162「真漏洞」段）。與 #10 配套：#10 擋「誰能改」(admin-gate)、#9 報「改了什麼」。
            # 改 name/phone/notes 不上報（噪音）。
            if any(u.startswith(("permissions =", "business_units =", "active ="))
                   for u in updates):
                enqueue_escalation(
                    db,
                    event_type="employee_permissions_changed",
                    summary=f"員工 #{employee_id} 敏感欄位被變更：{changed}",
                    detail={
                        "employee_id": employee_id, "changed": changed,
                        "new_permissions": permissions or None,
                        "new_business_units": (
                            business_units if business_units != "__SKIP__" else None
                        ),
                        "new_active": (active if active >= 0 else None),
                    },
                    actor_user_id=actor_user_id,
                    actor_label=actor_label if actor_label not in ("system", "__unverified__") else "",
                    business_unit="",
                )
    except sqlite3.IntegrityError as e:
        return f"ERROR: {e}"

    return f"員工 #{employee_id} 已更新（{changed}）"


def lookup_employee(name_or_line_id: str) -> str:
    db = get_db()
    try:
        emp = repository.get_employee_by_name_or_line(db, name_or_line_id)
        if not emp:
            return f"找不到員工：{name_or_line_id}"
        bu = emp["business_units"] if emp["business_units"] else "全部"
        return (
            f"## {emp['name']}\n"
            f"- 角色：{emp['role']} | 權限：{emp['permissions']}\n"
            f"- 部門：{emp['department'] or '未設定'}\n"
            f"- 事業體：{bu}\n"
            f"- LINE：{'已綁定' if emp['line_user_id'] else '未綁定'}\n"
            f"- 電話：{emp['phone'] or '未設定'}\n"
            f"- 備註：{emp['notes'] or '無'}"
        )
    finally:
        db.close()


def list_employees(active_only: bool) -> str:
    db = get_db()
    try:
        emps = repository.list_employees(db, active_only)
        if not emps:
            return "目前沒有員工資料。"
        lines = [f"## 員工名冊（{len(emps)} 人）"]
        for e in emps:
            line_status = "[已綁定]" if e["line_user_id"] else "[未綁定]"
            bu = f" [{e['business_units']}]" if e["business_units"] else ""
            lines.append(
                f"- [#{e['id']}] **{e['name']}** ({e['role']}/{e['permissions']}) "
                f"{e['department'] or ''}{bu} {line_status}"
            )
        return "\n".join(lines)
    finally:
        db.close()


# ---- external_partners ----

def register_partner(
    name: str,
    role: str,
    line_user_id: str,
    phone: str,
    email: str,
    business_units: str,
    payment_terms: str,
    notes: str,
) -> str:
    with transaction() as db:
        pid = repository.insert_partner(
            db,
            name=name,
            role=role or None,
            line_user_id=line_user_id or None,
            phone=phone or None,
            email=email or None,
            business_units=business_units or None,
            payment_terms=payment_terms or None,
            notes=notes or None,
        )
        repository.insert_interaction_log(
            db,
            actor="system",
            action="partner_registered",
            target_type="external_partner",
            target_id=pid,
            detail=f"註冊外包 {name} ({role or '未指定職責'})",
            business_unit=None,
        )
    bu_label = f" [BU: {business_units}]" if business_units else ""
    return f"外包夥伴 #{pid} {name}{bu_label} 已註冊（{role or '未指定職責'}）"


def update_partner(
    partner_id: int,
    name: str,
    role: str,
    line_user_id: str,
    phone: str,
    email: str,
    business_units: str,
    payment_terms: str,
    notes: str,
    active: int,
) -> str:
    with transaction() as db:
        p = repository.get_partner(db, partner_id)
        if not p:
            return f"ERROR: 找不到外包夥伴 #{partner_id}"

        updates: list[str] = []
        params: list = []
        if name:
            updates.append("name = ?"); params.append(name)
        if role:
            updates.append("role = ?"); params.append(role)
        if line_user_id != "__SKIP__":
            updates.append("line_user_id = ?"); params.append(line_user_id or None)
        if phone:
            updates.append("phone = ?"); params.append(phone)
        if email:
            updates.append("email = ?"); params.append(email)
        if business_units != "__SKIP__":
            updates.append("business_units = ?"); params.append(business_units or None)
        if payment_terms:
            updates.append("payment_terms = ?"); params.append(payment_terms)
        if notes:
            updates.append("notes = ?"); params.append(notes)
        if active in (0, 1):
            updates.append("active = ?"); params.append(active)

        if not updates:
            return "沒有指定要更新的欄位。"

        repository.safe_update_partner(db, partner_id, updates, params)
        changed = ", ".join(u.split(" = ")[0] for u in updates)
        repository.insert_interaction_log(
            db,
            actor="system",
            action="partner_updated",
            target_type="external_partner",
            target_id=partner_id,
            detail=f"更新 {p['name']}：{changed}",
            business_unit=None,
        )
    return f"外包夥伴 #{partner_id} 已更新（{changed}）"


def list_partners(active_only: bool, role: str, business_unit: str) -> str:
    db = get_db()
    try:
        rows = repository.list_partners(db, active_only, role, business_unit)
        if not rows:
            return "目前沒有符合條件的外包夥伴。"
        lines = [f"## 外包夥伴（{len(rows)} 位）"]
        for p in rows:
            status = "" if p["active"] else " 注意：停用"
            line_label = "" if p["line_user_id"] else " [未綁定]"
            bu_label = f" [{p['business_units']}]" if p["business_units"] else ""
            terms_label = f" | {p['payment_terms']}" if p["payment_terms"] else ""
            lines.append(
                f"- [#{p['id']}] **{p['name']}** ({p['role'] or '未指定'}){bu_label}"
                f"{line_label} {p['phone'] or ''}{terms_label}{status}"
            )
        return "\n".join(lines)
    finally:
        db.close()


def find_partner(query: str) -> str:
    db = get_db()
    try:
        rows = repository.search_partners(db, query)
        if not rows:
            return f"找不到符合「{query}」的外包夥伴。"
        lines = [f"## 外包夥伴搜尋：「{query}」"]
        for p in rows:
            status = "" if p["active"] else " 注意：停用"
            line_label = f" LINE:{p['line_user_id'][:8]}..." if p["line_user_id"] else ""
            bu_label = f" [{p['business_units']}]" if p["business_units"] else ""
            lines.append(
                f"- [#{p['id']}] **{p['name']}** ({p['role'] or '未指定'}){bu_label}"
                f" {p['phone'] or ''}{line_label}{status}"
            )
            if p["notes"]:
                lines.append(f"  備註：{p['notes'][:100]}")
        return "\n".join(lines)
    finally:
        db.close()


def get_partner(partner_id: int) -> str:
    db = get_db()
    try:
        p = repository.get_partner(db, partner_id)
        if not p:
            return f"ERROR: 找不到夥伴 #{partner_id}"
        active_str = "啟用" if p["active"] else "停用"
        return (
            f"## 夥伴 #{partner_id}：{p['name']}\n"
            f"- 角色：{p['role'] or '未設定'}\n"
            f"- 狀態：{active_str}\n"
            f"- 電話：{p['phone'] or '無'}\n"
            f"- Email：{p['email'] or '無'}\n"
            f"- LINE：{p['line_user_id'] or '未綁定'}\n"
            f"- 服務事業體：{p['business_units'] or '全部'}\n"
            f"- 付款條件：{p['payment_terms'] or '無'}\n"
            f"- 建立：{p['created_at']}\n"
            f"\n### 備註\n{p['notes'] or '（無）'}"
        )
    finally:
        db.close()
