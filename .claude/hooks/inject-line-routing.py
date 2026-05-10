"""
條件式 hook：當 user prompt 含 <channel source="line"> 時、
注入 LINE 訊息路由檢查提醒；其他情況不輸出（hook 安靜通過）。

stdin 是 Claude Code 傳的 JSON 物件、形如：
  {"session_id":"...","prompt":"<channel source=\\"line\\" ...>內容</channel>"}
所以要先 parse JSON、再從 prompt 欄位抓字串。
"""
import json
import sys

raw = sys.stdin.read()

try:
    payload = json.loads(raw)
    prompt = payload.get('prompt', '') if isinstance(payload, dict) else raw
    if not isinstance(prompt, str):
        prompt = str(prompt)
except (json.JSONDecodeError, ValueError):
    prompt = raw  # fallback：直接當字串處理

if '<channel source="line"' in prompt:
    sys.stdout.reconfigure(encoding='utf-8')
    print(json.dumps({
        'hookSpecificOutput': {
            'hookEventName': 'UserPromptSubmit',
            'additionalContext': (
                '🚨 LINE 訊息進來、回覆前必走完整路由（不准跳）：\n'
                '1. lookup_employee(user_id) — 是員工嗎？\n'
                '2. find_customer(user_id) — 是客戶 / 供應商 / 經銷商嗎？\n'
                '3. 都不是 → 暱稱比對；仍沒命中 = 陌生人\n'
                '4. 陌生人原則：不直接回覆、依意圖路由通知對應負責人\n'
                '5. 對外行銷訊息 → 必先 create_approval HITL 審核\n'
                '6. 每則訊息必有結局：reply / reply_flex / mark_read\n'
                '完整流程：.claude/skills/company-ops/references/line-comms.md'
            )
        }
    }, ensure_ascii=False))
