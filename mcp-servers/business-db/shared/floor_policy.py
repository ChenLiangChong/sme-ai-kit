"""
Floor-based tool gating（決策 #159 / #160）— per-floor 工具白名單。

問題：LINE-runtime 分層後，floor 物理隔離(sandbox)只擋 bash/檔案存取；business-db MCP 是
獨立進程、sandbox 管不到它，所以外部/通用層 session 仍可透過 MCP 工具讀全部薪資/帳務/員工
（決策 #159 的 Critical 洞）。

解法：啟動端(start-line.sh)用 env 注入「可信 floor」(agent 改不到、非對話參數)；server 在所有
tool 註冊完後讀 SME_FLOOR + floor-map 能力設定(決策#171)，把該層不該有的工具從 mcp 移除。
- SME_FLOOR='' → operator/Cowork、全權限（不移除）
- SME_FLOOR='confidential' → 機密層、全權限（不移除）
- 其他層 → 移除 HR_TOOLS（一律）+ 依 floor-map 的 financial_visibility 決定財務工具去留
  （none 預設=全移除＝向後相容 / all=會計層保留 / own_bu=待 #11、暫 fail-closed 全移除）

範圍：這是 floor 級「工具白名單」(整支工具有/無)。資料級 scoping（同一支工具按 floor
過濾欄位/列）分兩批：
- 開機讀取（決策 #166、已做）：get_context_summary / low_stock_alerts 在非全權限層回
  安全子集（見各自 service 的 is_full_access() 早退），堵住「開機 hook 自動跑就洩漏」。
- on-demand 讀取（task #11、待 #6 floor-map）：list_orders/get_order/list_tasks/check_stock/
  find_customer 等仍照 agent 傳入的 business_unit，非全權限層可省略 → 撈全 BU；須等 floor→BU
  map 落地、由 gate 自動注入該層 BU 才能根治（目前 fail-open，屬 on-demand 主動越權、
  非開機自動洩漏，嚴重度較低）。
"""
import os

# 財務工具拆 寫/讀 兩類（決策 #171：financial_visibility 能獨立控制財務、own_bu 只留讀）
FINANCIAL_WRITE_TOOLS = {
    "record_transaction", "update_transaction", "record_payment",
}
FINANCIAL_READ_TOOLS = {
    "list_transactions", "get_transaction", "monthly_summary", "check_overdue",
}
FINANCIAL_TOOLS = FINANCIAL_WRITE_TOOLS | FINANCIAL_READ_TOOLS

# 危險財務操作（需要 manager 權限）—— 非全權限層一律移除
FINANCIAL_DANGER_TOOLS = {
    "delete_transaction",
}

# HR 管理工具 —— 非全權限層一律移除（需 admin 權限或配額設定職責）
# lookup_employee / list_employees 保留（LINE 路由辨識 + 員工通訊錄）
# 員工自助請假 + 看誰請假保留（request_leave / cancel_leave / get_leave_request / list_leave_requests）
# 但 list_pending_leave_requests（主管簽核佇列、含全員事由）＝管理工具、移除（#171 審）
HR_ADMIN_TOOLS = {
    "register_employee", "update_employee",       # 寫入 HR，需 admin
    "register_leave_type", "set_leave_balance",   # 配額設定，HR 管理員
    "approve_leave", "reject_leave",              # 請假簽核，老闆/HR 才做
    "list_pending_leave_requests",                # 主管簽核佇列（含全員事由）＝管理用、非員工自助
}

# 向後相容引用（外部若有 import HR_TOOLS / CONFIDENTIAL_ONLY_TOOLS）
HR_TOOLS = HR_ADMIN_TOOLS | {
    "list_employees", "lookup_employee",
    "get_leave_balance", "request_leave", "cancel_leave",
    "list_leave_requests", "get_leave_request",
}

# 主管上報管理工具（#9g）—— 非全權限層一律移除：部門層不該讀/標自己被上報的事。
# 只給 claude -p 通報投遞器（全權限、無 SME_FLOOR）+ operator/confidential 用。
ESCALATION_ADMIN_TOOLS = {
    "list_pending_escalations", "mark_escalation_sent",
}

# 知識敏感度重分級工具（#168 後續）—— 非全權限層一律移除：翻 confidential 旗標是
# 敏感度管理、只該機密層/operator 做（比照 HR_ADMIN 寫入）。受限層仍可 query_knowledge
# /get_rule（讀），只是讀不到 confidential=1 的列、也改不了任何規則的機密等級。
KNOWLEDGE_ADMIN_TOOLS = {
    "set_rule_confidential",
}

# 排程提醒工具（派工器模式）—— 非全權限層一律移除：schedule_reminder 會定時推播到任意 LINE
# 對象（broadcast-ish），只該機密層/operator 排。confidential（full access）保留 → daemon 自助排程，
# 不必每次喊老闆、也不必開 crontab 寫權限（不拆 sandbox 第一道牆）。
REMINDER_ADMIN_TOOLS = {
    "schedule_reminder", "cancel_reminder", "list_reminders",
}

# 向後相容引用 + 「financial_visibility=none（預設）」的完整移除集（= 改版前的清單）
CONFIDENTIAL_ONLY_TOOLS = FINANCIAL_TOOLS | HR_TOOLS

# 全權限 floor（不移除任何工具）。空字串 = operator/Cowork。
FULL_ACCESS_FLOORS = {"", "confidential"}


def get_floor() -> str:
    """讀啟動端注入的可信 floor。三態：

    - genuinely 空（env unset）→ '' = operator/全權限（合法、不砍工具）
    - 未展開的 ${...} 模板（CC 沒展開）→ '__unexpanded__' = 受限未知層、**fail-CLOSED**
      （apply_floor_policy 會砍機密工具、_resolve_trusted_actor 會擋下、line-channel 收不到訊息），
      絕不誤當 operator 放行
    - 其餘 → 該 floor
    """
    v = os.environ.get("SME_FLOOR", "").strip()
    if not v:
        return ""
    if "$" in v or "{" in v:
        return "__unexpanded__"
    return v


def is_full_access() -> bool:
    """True = operator('')/confidential（全權限、看全部）；False = 部門/受限層
    （含 __unexpanded__ fail-closed）。供 service 層（get_context_summary /
    low_stock_alerts 等開機讀取）判斷是否回安全子集、避免跨部門/跨 BU 洩漏。"""
    return get_floor() in FULL_ACCESS_FLOORS


def apply_floor_policy(mcp) -> list[str]:
    """依 SME_FLOOR + floor-map 能力設定從 mcp 移除該層不該有的工具。回傳被移除的工具名 list。

    決策 #171（修訂）：最大化保留原則。
    - 非全權限層一律移除：HR_ADMIN_TOOLS（寫入/簽核）+ ESCALATION_ADMIN_TOOLS + FINANCIAL_DANGER_TOOLS
      + KNOWLEDGE_ADMIN_TOOLS（set_rule_confidential 敏感度重分級）+ REMINDER_ADMIN_TOOLS（排程推播）
    - 財務移除由 floor-map 的 financial_visibility 決定（'all'=全保留 / 'none'=移除讀寫 / 'own_bu'=fail-closed）
    - 保留：lookup_employee / list_employees（路由必要）/ 員工自助請假（走 HITL）/ 財務讀寫（HITL gate 控大額）
    - 無 floor-map 條目 → 安全預設（財務 none）= 向後相容
    """
    floor = get_floor()
    if floor in FULL_ACCESS_FLOORS:
        return []  # operator / confidential：全權限、不移除

    # lazy import 避免與 floor_map 模組載入時循環
    from shared.floor_map import get_floor_config
    cfg = get_floor_config(floor)

    # 基礎移除：HR 管理寫入 + 危險財務 + 上報管理（一律）
    to_remove: set[str] = (
        set(HR_ADMIN_TOOLS) | set(FINANCIAL_DANGER_TOOLS)
        | set(ESCALATION_ADMIN_TOOLS) | set(KNOWLEDGE_ADMIN_TOOLS)
        | set(REMINDER_ADMIN_TOOLS)
    )

    fv = (cfg.financial_visibility or "none").strip()
    if fv == "all":
        pass  # 財務全保留（HITL gate 控大額）
    elif fv == "own_bu":
        # own_bu 需 #11 對財務「讀」做 BU-scoping 才安全；#11 未落地前 fail-closed＝連讀也移除
        to_remove |= FINANCIAL_TOOLS
    else:  # 'none'（預設）：財務讀寫全移除
        to_remove |= FINANCIAL_TOOLS

    removed: list[str] = []
    for name in sorted(to_remove):
        try:
            mcp.remove_tool(name)
            removed.append(name)
        except Exception:
            pass  # 該工具不存在/已移除 → 略過
    return removed
