"""
條件式 hook：當 user prompt 含 <channel source="line"> 時、
注入 LINE 訊息路由檢查提醒（律所版）；其他情況不輸出（hook 安靜通過）。

stdin 是 Claude Code 傳的 JSON 物件、形如：
  {"session_id":"...","prompt":"<channel source=\\"line\\" ...>內容</channel>"}
所以要先 parse JSON、再從 prompt 欄位抓字串。

路由文字與 CLAUDE.md〈LINE 訊息處理〉、line-comms.md（律所收斂版）一致：
所內專用、沒有對外通道——身份只有「所內名冊上的人」或「非名冊用戶」兩種結果。
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
                '1. lookup_employee(user_id) — 是所內人員嗎（律師 / 助理 / 行政）？\n'
                '2. 不是 → 暱稱比對 lookup_employee；仍沒命中（含多人同名無法確認）= 非所內名冊\n'
                '3. 非所內名冊一律不回覆業務內容：mark_read + 提示主持律師確認是否新進人員待建檔綁定\n'
                '   （委任人／民眾來訊同此硬規則；約諮詢只走電話由行政人工建、不在 LINE 開委任人對話）\n'
                '4. 判決書 / 裁定 / 開庭通知（附件或文字）→ 走 legal-admin 收件抽取：'
                '讀檔 → 抽送達日 → 一鍵確認才入 → 引擎確定性算時限，絕不心算天數\n'
                '5. 不做對外行銷、不做陌生人意圖分層路由（律師倫理限制廣告招攬）\n'
                '6. 每則訊息必有結局：reply / reply_flex / mark_read\n'
                '完整流程：.claude/skills/company-ops/references/line-comms.md'
            )
        }
    }, ensure_ascii=False))
