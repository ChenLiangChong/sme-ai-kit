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
    "record_transaction", "update_transaction", "delete_transaction", "record_payment",
}
FINANCIAL_READ_TOOLS = {
    "list_transactions", "get_transaction", "monthly_summary", "check_overdue",
}
FINANCIAL_TOOLS = FINANCIAL_WRITE_TOOLS | FINANCIAL_READ_TOOLS

# HR / 員工 PII / 請假 —— 非全權限層一律移除（v1：hr_visibility 暫不可設定、預設機密）
HR_TOOLS = {
    "register_employee", "update_employee", "list_employees", "lookup_employee",
    "register_leave_type", "set_leave_balance", "get_leave_balance",
    "request_leave", "approve_leave", "reject_leave", "cancel_leave",
    "list_leave_requests", "list_pending_leave_requests", "get_leave_request",
}

# 主管上報管理工具（#9g）—— 非全權限層一律移除：部門層不該讀/標自己被上報的事。
# 只給 claude -p 通報投遞器（全權限、無 SME_FLOOR）+ operator/confidential 用。
ESCALATION_ADMIN_TOOLS = {
    "list_pending_escalations", "mark_escalation_sent",
}

# 全域控制 / 公司核心設定工具（codex 全專案審 B-HIGH）—— 非全權限層一律移除：
# 部門層不該改公司主設定、boss_line_id、審核門檻、事業體 / OA→BU 映射（越權改設定）。
GLOBAL_CONTROL_TOOLS = {
    "update_company", "register_business_entity", "list_business_entities",
}

# 跨 OA LINE 資料工具（codex 全專案審 B-HIGH / E-HIGH）—— 非全權限層一律移除：
# 這些工具無列級 channel/BU 縮限，受限層可橫向讀全公司 LINE 訊息 / 群組、或竄改群組登錄。
LINE_DATA_TOOLS = {
    "search_line_messages", "list_line_groups", "register_line_group",
}

# pleading 整合 token 管理（Task D）—— 非全權限層一律移除：bind/unbind 管的是「律師個人 pleading
# token」＝完整律師身分密鑰，受限層不該綁定/解除/接觸（雙牆第一道；service 另有 is_full_access 第二道）。
# 無 get 工具（密鑰永不經 MCP 回傳）。
INTEGRATION_ADMIN_TOOLS = {
    "bind_pleading_token", "unbind_pleading_token",
}

# legal-admin（律所）案件/時限工具 —— 含當事人名 / calc_trace / 機密案件。
# SPEC §54：小所「預設不分層、全所共用一個視圖」→ MVP 不把整支工具從受限層移除
# （移除整支會連非機密案件都看不到、過度收斂）。機密性走「機密軸」列級過濾：
# matters/deadlines 帶 confidential 欄，read service 在非全權限層過濾 confidential=1
# （與 query_knowledge migration 006 同 pattern、見 modules/deadlines/service.py）。
# 此集合保留為未來「需把整支機密工具從特定受限層硬移除」時的掛點（keystone、預設不啟用）。
LEGAL_CONFIDENTIAL_TOOLS = {
    "create_matter", "get_matter", "list_matters", "find_matter_by_party",
    "create_deadline", "get_deadline", "list_deadlines",
    "list_upcoming_deadlines", "mark_deadline_filed",
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

    決策 #171：財務移除由 floor-map 的 financial_visibility 決定（'none' 預設 / 'own_bu' / 'all'）；
    HR/員工 PII 在非全權限層一律移除（v1）。無 floor-map 條目 → 安全預設（財務 none）＝
    完全等同改版前行為（向後相容）。
    """
    floor = get_floor()
    if floor in FULL_ACCESS_FLOORS:
        return []  # operator / confidential：全權限、不移除

    # lazy import 避免與 floor_map 模組載入時循環
    from shared.floor_map import get_floor_config
    cfg = get_floor_config(floor)

    # 非全權限層：不碰 HR/員工 PII/請假 + 上報管理 + 全域控制設定 + 跨 OA LINE 資料
    to_remove: set[str] = (set(HR_TOOLS) | set(ESCALATION_ADMIN_TOOLS)
                           | set(GLOBAL_CONTROL_TOOLS) | set(LINE_DATA_TOOLS)
                           | set(INTEGRATION_ADMIN_TOOLS))
    fv = (cfg.financial_visibility or "none").strip()
    if fv == "all":
        pass  # 會計層：保留全部財務工具（HR 仍移除）
    elif fv == "own_bu":
        # own_bu 需 #11 對財務「讀」做 BU-scoping 才安全；#11 未落地前 fail-closed＝連讀也移除
        to_remove |= FINANCIAL_TOOLS
    else:  # 'none'（預設）：財務全移除
        to_remove |= FINANCIAL_TOOLS

    removed: list[str] = []
    for name in sorted(to_remove):
        try:
            mcp.remove_tool(name)
            removed.append(name)
        except Exception:
            pass  # 該工具不存在/已移除 → 略過
    return removed
