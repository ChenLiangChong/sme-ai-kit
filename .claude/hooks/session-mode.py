#!/usr/bin/env python3
"""Session 模式分流 hook（為什麼需要：.claude/playbooks/00-diagnosis.md 第一名「角色混線」）。

模式判定（優先序）：
1. `SME_SESSION_MODE` 顯式指定（`dev` / `ops`）→ 照指定
2. `SME_FLOOR` 有值（floored / confidential 產品 runtime）→ ops
3. 都沒有（repo root 互動 session）→ dev（本 repo 是開發 repo；正式部署有自己的專案資料夾與 settings）

用法：session-mode.py <session-start|prompt-submit> [dev|ops]
- 第二參數＝顯式模式覆寫（優先序最高；給部署環境在 hook command 直接寫死用、
  不依賴 SME_SESSION_MODE 環境變數是否傳進 hook 進程——Windows e2e 實測的可攜性課題）
- ops：注入律所版營運指令（2026-07-07 全律所化：開機清單對齊 ops-dashboard.md、
  寫入檢查對齊律所領域；最初的 SME 原文保存在 git 歷史 9beffcd 之前的 settings.json）
- dev + session-start：注入幾行開發紀律；dev + prompt-submit：靜默（不注入）

自測（不用開 session）：
  python3 .claude/hooks/session-mode.py session-start            # 應輸出 dev 紀律
  SME_FLOOR=x python3 .claude/hooks/session-mode.py prompt-submit  # 應輸出 ops DB 寫入檢查
  SME_SESSION_MODE=ops python3 .claude/hooks/session-mode.py session-start  # 應輸出 ops 啟動流程
"""
import json
import os
import sys


def resolve_mode() -> str:
    argv_mode = (sys.argv[2] if len(sys.argv) > 2 else "").strip().lower()
    if argv_mode in ("dev", "ops"):
        return argv_mode
    explicit = os.environ.get("SME_SESSION_MODE", "").strip().lower()
    if explicit in ("dev", "ops"):
        return explicit
    if os.environ.get("SME_FLOOR", "").strip():
        return "ops"
    return "dev"


# 律所版 ops 文字（2026-07-07 全律所化，老闆核准「全改」）：
# 開機清單對齊 CLAUDE.md〈啟動流程〉與 ops-dashboard.md 步驟 3-7 的真實工具；
# 寫入檢查對齊律所領域（時限走收件抽取、絕不心算——反捏造一級鐵則）。
OPS_SESSION_START = (
    "SESSION START / COMPACT 恢復：請立即跑啟動流程（完整步驟見 ops-dashboard.md、CLAUDE.md〈啟動流程〉為主控）。\n"
    "1. mcp__business-db__get_context_summary(scope=full) — 若回傳含「上次 Session 交接 #N」：\n"
    "   • 24h 內 → 按 handoff 下一步繼續、不要重新規劃\n"
    "   • 標 ⚠️ 過時 → 顯示給使用者並問「這個交接還有效嗎？」確認後再動\n"
    "   • 接手完成後務必跑 mcp__business-db__resolve_handoff(handoff_id, note) 標記，否則下次又會撈到\n"
    "2. 掃描器 heartbeat 哨兵列 readout 最前（看 get_context_summary 的哨兵狀態；"
    "失聯=時限恐停止倒數、執業過失高風險）；再補：\n"
    "   • mcp__business-db__list_pending_intakes — 待確認到期日（等律師一鍵確認、不端權威日期）\n"
    "   • mcp__business-db__list_upcoming_deadlines(within_days=7) — 即將到期/逾期法定時限"
    "（只搬引擎算好的日期與 statutory_basis、絕不自行心算天數）\n"
    "   • mcp__business-db__list_pending_leave_requests — 待簽請假（空表自然回 empty、不影響流程）\n"
    "3. 再回答使用者的問題"
)

OPS_PROMPT_SUBMIT = (
    "⚠️ DB 寫入檢查（每則訊息必過一次）：\n"
    "• 寫前必查：query_knowledge(關鍵字) / get_rule(id) 找同主題；命中 → 跟使用者討論 → "
    "補充走 update_rule、不要 silently 再開新規則\n"
    "• 所務規則/SOP/收發文慣例 → mcp__business-db__store_fact (必帶 source_quote=所長/律師原話；"
    "可選 related_rule_ids 關聯既有規則)\n"
    "• 設定值（行事曆代號/範本路徑/文案）→ mcp__business-db__store_fact (category='settings', title=key)；"
    "查用 get_setting(key)\n"
    "• 交辦/承諾/「明天」「下週」「記得做」→ mcp__business-db__create_task\n"
    "• 為什麼這樣做的決策 → mcp__business-db__log_decision (附 reason；可選 supersedes_rule_ids / related_rule_ids)\n"
    "• 判決書/裁定/開庭通知的送達日與期限 → 一律走 legal-admin 收件抽取"
    "（stage_deadline_intake → HITL 一鍵確認 → create_deadline 確定性計算），"
    "絕不心算天數、絕不直接 store_fact 存期限日期\n"
    "• 當事人/委任人聯絡方式與特殊注意事項 → mcp__business-db__update_customer\n"
    "回「好的我會記住」「我知道了」不算寫入。必須真的呼叫對應 tool。"
    "不確定要不要存就主動問使用者，不要私下省略。"
)

DEV_SESSION_START = (
    "本 session 模式 = dev（開發）：你是本專案的開發者，不是律所行政助理。\n"
    "• 不跑營運啟動流程、不做營運 readout、不寫營運/dogfood DB（驗證產品行為用本 repo dev DB data/business.db、.mcp.json 已指）\n"
    "• 開工前讀 .claude/playbooks/README.md（模型調度 / 判斷 rubric / 派工模板 / 維護協議）\n"
    "• 一律繁體中文；commit 可以、push 前先問；master ⊥ legal-admin 兩產品線永不 merge\n"
    "若這其實是營運 session（回 LINE / 所務 readout），請告知使用者以 SME_SESSION_MODE=ops 重啟。"
)


def emit(event_name: str, text: str) -> None:
    print(json.dumps(
        {"hookSpecificOutput": {"hookEventName": event_name, "additionalContext": text}},
        ensure_ascii=False,
    ))


def main() -> None:
    # Windows 主控台預設 cp950 會炸在 ⚠/emoji（e2e 實測 UnicodeEncodeError）——強制 UTF-8 輸出
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    event = sys.argv[1] if len(sys.argv) > 1 else ""
    mode = resolve_mode()
    if event == "session-start":
        emit("SessionStart", OPS_SESSION_START if mode == "ops" else DEV_SESSION_START)
    elif event == "prompt-submit":
        if mode == "ops":
            emit("UserPromptSubmit", OPS_PROMPT_SUBMIT)
        # dev：靜默，不注入任何 context
    # 未知 event：靜默 exit 0（fail-open 成「不注入」、絕不擋 prompt）


if __name__ == "__main__":
    main()
