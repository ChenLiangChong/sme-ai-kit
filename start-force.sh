#!/bin/bash
# SME-AI-Kit 啟動腳本 — 3 秒後自動送 Enter
cd "$(dirname "$0")"
(sleep 3 && xdotool key Return 2>/dev/null || python3 -c "
import subprocess, time
time.sleep(0.1)
subprocess.run(['xdotool', 'key', 'Return'], capture_output=True)
" 2>/dev/null) &
claude --dangerously-load-development-channels server:line
