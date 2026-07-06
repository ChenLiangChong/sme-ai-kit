#!/usr/bin/env python3
"""Session 模式分流 hook（為什麼需要：.claude/playbooks/00-diagnosis.md 第一名「角色混線」）。

模式判定（優先序）：
1. `SME_SESSION_MODE` 顯式指定（`dev` / `ops`）→ 照指定
2. `SME_FLOOR` 有值（floored / confidential 產品 runtime）→ ops
3. 都沒有（repo root 互動 session）→ dev（本 repo 同時是開發 repo；dogfood 營運 session 請帶 SME_SESSION_MODE=ops）

用法：session-mode.py <session-start|prompt-submit>
- ops：注入原本的營運指令（文字與 2026-07-07 之前的 settings.json 完全一致、營運行為零改變）
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
    explicit = os.environ.get("SME_SESSION_MODE", "").strip().lower()
    if explicit in ("dev", "ops"):
        return explicit
    if os.environ.get("SME_FLOOR", "").strip():
        return "ops"
    return "dev"


OPS_SESSION_START = (
    "SESSION START / COMPACT 恢復：請立即跑啟動流程。\n"
    "1. mcp__business-db__get_context_summary(scope=full) — 若回傳含「上次 Session 交接 #N」：\n"
    "   • 24h 內 → 按 handoff 下一步繼續、不要重新規劃\n"
    "   • 標 ⚠️ 過時 → 顯示給使用者並問「這個交接還有效嗎？」確認後再動\n"
    "   • 接手完成後務必跑 mcp__business-db__resolve_handoff(handoff_id, note) 標記，否則下次又會撈到\n"
    "2. mcp__business-db__low_stock_alerts、mcp__business-db__check_overdue、"
    "mcp__business-db__list_pending_leave_requests 補充狀態（請假表為空時自然回 empty、不影響流程）\n"
    "3. 再回答使用者的問題"
)

OPS_PROMPT_SUBMIT = (
    "⚠️ DB 寫入檢查（每則訊息必過一次）：\n"
    "• 寫前必查：query_knowledge(關鍵字) / get_rule(id) 找同主題；命中 → 跟使用者討論 → "
    "補充走 update_rule、不要 silently 再開新規則\n"
    "• 規則/SOP/政策/限制 → mcp__business-db__store_fact (必帶 source_quote=老闆原話；"
    "可選 related_rule_ids 關聯既有規則)\n"
    "• 設定值（顏色/字體/URL/文案）→ mcp__business-db__store_fact (category='settings', title=key)；"
    "查用 get_setting(key)\n"
    "• 交辦/承諾/截止日/「明天」「下週」「記得做」→ mcp__business-db__create_task\n"
    "• 為什麼這樣做的決策 → mcp__business-db__log_decision (附 reason；可選 supersedes_rule_ids / related_rule_ids)\n"
    "• 客戶聯絡/偏好/特殊條件 → mcp__business-db__update_customer 或 set_customer_entity_terms\n"
    "• 庫存異動 → mcp__business-db__update_stock\n"
    "• 收支金額 → mcp__business-db__record_transaction\n"
    "回「好的我會記住」「我知道了」不算寫入。必須真的呼叫對應 tool。"
    "不確定要不要存就主動問使用者，不要私下省略。"
)

DEV_SESSION_START = (
    "本 session 模式 = dev（開發）：你是本專案的開發者，不是營運助理。\n"
    "• 不跑營運啟動流程、不做營運 readout、不寫 dogfood DB（data/business.db 是真實營運資料；"
    "驗證產品行為用 scratch DB + SME_DB_PATH 另指）\n"
    "• 開工前讀 .claude/playbooks/README.md（模型調度 / 判斷 rubric / 派工模板 / 維護協議）\n"
    "• 一律繁體中文；commit 可以、push 前先問；master ⊥ legal-admin 兩產品線永不 merge\n"
    "若這其實是營運 session（dogfood readout / LINE / Cowork 老闆互動），請告知使用者以 SME_SESSION_MODE=ops 重啟。"
)


def emit(event_name: str, text: str) -> None:
    print(json.dumps(
        {"hookSpecificOutput": {"hookEventName": event_name, "additionalContext": text}},
        ensure_ascii=False,
    ))


def main() -> None:
    # Windows 主控台預設 cp950 會炸在 ⚠/emoji（legal-admin 線 e2e 實測 UnicodeEncodeError）——強制 UTF-8 輸出
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
