#!/usr/bin/expect -f
# SME-AI-Kit — LINE-runtime 受限啟動（v6：分層 floor，可選 layer 參數）
# 用法：
#   ./start-line.sh                → 預設、floor = data/（向後相容＝原 v5 行為）
#   ./start-line.sh confidential   → 機密層、floor = data/confidential、settings = .claude/line-runtime-confidential.json
#   ./start-line.sh general        → 通用層
#   ./start-line.sh external       → 對外業務層
#
# 四層安全（v2.1.153 / WSL 實測過、見 business-db 決策 #155 / #156 / #158）：
#   1. --permission-mode dontAsk + 只用 allow → 清單外的工具/路徑靜默拒絕（不問不卡）
#   2. Read/Write/Edit 用 allow 圈在「該層 floor」→ 工具層讀寫出不了該層
#   3. CC Bash sandbox：denyRead 家目錄/系統/.mcp.json/.env/business.db ＋「其他層 floor」；
#      failIfUnavailable=true 確保 deps 缺時 fail-CLOSED（不裸跑）
#   4. 啟動 cwd = 該層 floor → 中和 harness 自動把 cwd(".") 注入 allowWrite 的寫入破口
# 威脅模型：防內部員工越權看不該看的（非駭客級 injection）。
#
# 注意：line-channel 目前是「廣播」、尚未做 DB 驅動定向派送（Flow B 下一步）。
#       多開 session 時，同一則 LINE 訊息每個 session 都會收到 → 測「分層隔離」請用終端機直接下指令。
set timeout 15
# base = 這個腳本所在目錄（＝ repo root）：自動推導、不寫死絕對路徑，換機器 / 換資料夾 / 上 NAS 免改。
# （原 v6 寫死絕對路徑；改為 info script 推導後此檔可攜、可進 git 當部署參考。）
set base [file dirname [file normalize [info script]]]
set layer [lindex $argv 0]
if {$layer eq ""} {
    set floor $base/data
    set settings $base/.claude/line-runtime-settings.json
} else {
    set floor $base/data/$layer
    set settings $base/.claude/line-runtime-$layer.json
}
if {![file isdirectory $floor]} {
    puts "錯誤：floor 不存在 → $floor（檢查 layer 名稱、或先建資料夾）"
    exit 1
}
if {![file exists $settings]} {
    puts "錯誤：設定檔不存在 → $settings"
    exit 1
}
puts "啟動 LINE-runtime ── floor   = $floor"
puts "                   settings = $settings"
# 把可信 floor 注入環境 → business-db MCP 進程讀 SME_FLOOR、套每層工具白名單（agent 改不到、非對話參數）
# 決策 #159/#160：external/general 層的 MCP 進程移除財務/HR/員工機密工具，堵住「分層對 DB 0 覆蓋」的洞
set ::env(SME_FLOOR) $layer
cd $floor
# --tools = built-in 工具白名單（決策 #155/#160、5/30 live 實測補上「①工具牆」）：只留
# Bash/Read/Write/Edit/Web*/Skill/ToolSearch，砍 Agent/Workflow/Monitor/Task*/Cron*/ScheduleWakeup
# 等逃逸/編排工具（Monitor 曾實測逃逸）。實測：--tools 只限 built-in、不影響 MCP（business-db/line 照常）。
spawn claude --dangerously-load-development-channels server:line --permission-mode dontAsk --settings $settings --tools Bash Read Write Edit WebSearch WebFetch Skill ToolSearch
# 自動跳過 channel 載入確認 / 資料夾信任
expect {
    "local development" { send "\r" }
    "Enter to confirm" { send "\r" }
    "trust this folder" { send "1\r" }
    "WARNING" { sleep 2; send "\r" }
    timeout { send "\r" }
}
interact
