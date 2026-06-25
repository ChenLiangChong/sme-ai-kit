#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════
#  SME-AI-Kit 安裝腳本
#  只裝軟體和環境，不問密鑰。所有設定由 Claude 互動完成。
#  支援 macOS + Linux (WSL)
# ═══════════════════════════════════════════════════════
set -euo pipefail

GREEN='\033[92m'; RED='\033[91m'; CYAN='\033[96m'
BOLD='\033[1m'; DIM='\033[2m'; RESET='\033[0m'

ROOT="$(cd "$(dirname "$0")" && pwd)"
OS="$(uname -s)"

ok()   { echo -e "  ${GREEN}✓${RESET} $1"; }
err()  { echo -e "  ${RED}✗${RESET} $1"; }
step() { echo -e "\n${BOLD}${CYAN}▶${RESET} ${BOLD}$1${RESET}"; }

IS_MAC=false; IS_LINUX=false
[[ "$OS" == "Darwin" ]] && IS_MAC=true
[[ "$OS" == "Linux" ]] && IS_LINUX=true

# ── 1. 系統依賴 ──────────────────────────────────────

step "安裝系統依賴"

if $IS_MAC; then
    if ! command -v brew &>/dev/null; then
        echo -e "  ${DIM}安裝 Homebrew...${RESET}"
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        [[ -f /opt/homebrew/bin/brew ]] && eval "$(/opt/homebrew/bin/brew shellenv)"
    fi
    ok "Homebrew"

    for pkg in python@3.12 node; do
        command -v "${pkg%%@*}" &>/dev/null || brew install "$pkg"
    done
    command -v bun &>/dev/null || brew install oven-sh/bun/bun
    command -v ngrok &>/dev/null || brew install ngrok/ngrok/ngrok
    command -v claude &>/dev/null || npm install -g @anthropic-ai/claude-code

elif $IS_LINUX; then
    command -v python3 &>/dev/null || { sudo apt-get update -qq && sudo apt-get install -y -qq python3 python3-venv; }
    command -v bun &>/dev/null || { curl -fsSL https://bun.sh/install | bash; export PATH="$HOME/.bun/bin:$PATH"; }
    command -v ngrok &>/dev/null || {
        curl -fsSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null
        echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | sudo tee /etc/apt/sources.list.d/ngrok.list
        sudo apt-get update -qq && sudo apt-get install -y -qq ngrok
    }
    command -v expect &>/dev/null || sudo apt-get install -y -qq expect
    if command -v npm &>/dev/null && ! command -v claude &>/dev/null; then
        npm install -g @anthropic-ai/claude-code
    fi
fi

for cmd in python3 bun ngrok; do
    command -v "$cmd" &>/dev/null && ok "$cmd → $(which $cmd)" || err "$cmd 未安裝"
done
command -v claude &>/dev/null && ok "Claude Code → $(which claude)" || err "Claude Code 未安裝"

# ── 2. Python venv ────────────────────────────────────

step "建立 Python 虛擬環境"

VENV="$ROOT/.venv"
if [[ ! -f "$VENV/bin/pip" ]]; then
    python3 -m venv "$VENV"
    ok "venv 已建立"
else
    ok "venv 已存在"
fi

for req in "$ROOT"/mcp-servers/*/requirements.txt; do
    "$VENV/bin/pip" install -q -r "$req"
    ok "已安裝 $(basename "$(dirname "$req")")/requirements.txt"
done

# ── 3. Bun 依賴 ──────────────────────────────────────

step "安裝 LINE Channel 依賴"

(cd "$ROOT/mcp-servers/line-channel" && bun install --no-summary)
ok "line-channel 依賴已安裝"

# ── 4. 初始化資料庫 ──────────────────────────────────

step "初始化資料庫"

mkdir -p "$ROOT/data"
for sub in line orders customers tasks inventory exports; do
    mkdir -p "$ROOT/data/media/$sub"
done

DB="$ROOT/data/business.db"
if [[ -f "$DB" ]]; then
    ok "business.db 已存在"
else
    SME_DB_PATH="$DB" "$VENV/bin/python3" -c "
import sqlite3; from pathlib import Path
db = sqlite3.connect('$DB')
db.execute('PRAGMA journal_mode=WAL')
db.execute('PRAGMA foreign_keys=ON')
db.executescript(Path('$ROOT/mcp-servers/business-db/schema.sql').read_text())
db.close()
print('OK')
"
    ok "空白資料庫已建立"
fi

# ── 5. 生成最小 .mcp.json ────────────────────────────

step "生成 MCP 設定"

MCP="$ROOT/.mcp.json"
if [[ -f "$MCP" ]]; then
    ok ".mcp.json 已存在（保留現有設定）"
else
    cat > "$MCP" <<MCPJSON
{
  "mcpServers": {
    "business-db": {
      "command": "$VENV/bin/python3",
      "args": ["$ROOT/mcp-servers/business-db/server.py"],
      "env": {
        "SME_DB_PATH": "$DB"
      }
    }
  }
}
MCPJSON
    ok ".mcp.json → business-db（LINE 稍後由 Claude 設定）"
fi

# ── 6. 驗證 ──────────────────────────────────────────

step "驗證"

TOOLS=$(SME_DB_PATH="$DB" "$VENV/bin/python3" -c "
import sys; sys.path.insert(0, '$ROOT/mcp-servers/business-db')
import server; print(len(server.mcp._tool_manager._tools))
" 2>/dev/null)
ok "business-db：$TOOLS 個 MCP tools"
[[ -f "$ROOT/CLAUDE.md" ]] && ok "CLAUDE.md" || err "CLAUDE.md 不存在"

LOCAL_SETTINGS="$ROOT/.claude/settings.local.json"
if [[ ! -f "$LOCAL_SETTINGS" ]]; then
    mkdir -p "$ROOT/.claude"
    cat > "$LOCAL_SETTINGS" <<'LOCALJSON'
{
  "permissions": {
    "allow": [
      "Bash(bash install.sh)",
      "Bash(bash start.sh)",
      "Bash(bash start-force.sh)",
      "Bash(./.venv/bin/python3:*)",
      "Bash(./.venv/bin/pip:*)",
      "Read(./data/**)",
      "Read(./mcp-servers/**)"
    ],
    "deny": []
  }
}
LOCALJSON
    ok "settings.local.json 已建立（基本權限白名單）"
else
    ok "settings.local.json 已存在"
fi

# ── 7. Git hooks ─────────────────────────────────────

step "啟用 Git hooks"

if [[ -d "$ROOT/.git" && -d "$ROOT/.githooks" ]]; then
    git -C "$ROOT" config core.hooksPath .githooks
    ok "core.hooksPath = .githooks（CLAUDE.md ↔ AGENTS.md 自動同步啟用）"
else
    ok "非 git repo 或 .githooks 目錄不存在、跳過"
fi

# ── 8. 上報投遞保證層（cron flusher、決策 #177）───────────
# 主管上報「品質層」是 business-db commit 後即時起的 claude -p；此 cron 是「保證層」：
# 每 2 分確定性掃 pending_escalations 補送 claude -p 漏的/掛的（status 協調、retry/failed 終態）。

step "安裝 cron 投遞器（上報保證層 + 排程提醒派工器）"

# 兩支 OS-cron 笨投遞器：flush_escalations（上報保證層 #177）+ reminder_dispatcher（排程提醒派工器 #237）。
# 冪等以「腳本路徑」判重（非 marker）→ 與 tools/cron/install-cron.sh 共存、重跑都不會雙裝。
FLUSH_LINE="*/2 * * * * SME_DB_PATH=$DB $VENV/bin/python3 $ROOT/mcp-servers/business-db/flush_escalations.py >> $ROOT/data/flush.log 2>&1"
REMINDER_LINE="*/2 * * * * SME_DB_PATH=$DB $VENV/bin/python3 $ROOT/mcp-servers/business-db/reminder_dispatcher.py >> $ROOT/data/reminder.log 2>&1"
if command -v crontab >/dev/null 2>&1; then
    _cron_added=0
    if ! crontab -l 2>/dev/null | grep -qF 'flush_escalations.py'; then
        ( crontab -l 2>/dev/null; echo "# === SME-AI-Kit 上報保證層：每 2 分確定性投遞 pending_escalations ==="; echo "$FLUSH_LINE" ) | crontab - && _cron_added=1
    fi
    if ! crontab -l 2>/dev/null | grep -qF 'reminder_dispatcher.py'; then
        ( crontab -l 2>/dev/null; echo "# === SME-AI-Kit 排程提醒派工器：每 2 分投遞到期 scheduled_reminders ==="; echo "$REMINDER_LINE" ) | crontab - && _cron_added=1
    fi
    if [[ "$_cron_added" == 1 ]]; then
        ok "cron 投遞器已安裝/補齊（flush + reminder，每 2 分；log: data/flush.log、data/reminder.log）"
    else
        ok "cron 投遞器已存在（flush + reminder）、不重複加"
    fi
    if [[ "$IS_LINUX" == true ]] && ! pgrep -x cron >/dev/null 2>&1 && ! pgrep -x crond >/dev/null 2>&1; then
        err "cron daemon 沒在跑 → 投遞器不會觸發。啟動：sudo service cron start（WSL 建議 systemctl enable --now cron）"
    fi
else
    err "找不到 crontab → 上報/提醒無確定性保證層；請手動定時跑 flush_escalations.py 與 reminder_dispatcher.py"
fi

# ── 完成 ──────────────────────────────────────────────

echo ""
echo -e "  ${BOLD}${GREEN}✓ 安裝完成！${RESET}"
echo ""
echo -e "  ${BOLD}下一步：${RESET}"
echo -e "  ${CYAN}cd $ROOT && claude${RESET}"
echo ""
echo -e "  Claude 會引導你完成："
echo -e "  1. LINE Channel 設定（Token / Secret / ngrok）"
echo -e "  2. 首次訪談（公司資訊、員工、客戶、庫存）"
echo ""
