#!/usr/bin/expect -f
# SME-AI-Kit 啟動腳本 — 自動跳過 Channel 確認
set timeout 15
spawn claude --dangerously-load-development-channels server:line
# 等任何輸出出現後送 Enter
expect {
    "local development" { send "\r" }
    "Enter to confirm" { send "\r" }
    "WARNING" { sleep 2; send "\r" }
    timeout { send "\r" }
}
interact
