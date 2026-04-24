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
    ok "已安��� $(basename "$(dirname "$req")")/requirements.txt"
done

# ── 3. Bun 依賴 ──────────────────────────────────────

step "安裝 LINE Channel ���賴"

(cd "$ROOT/mcp-servers/line-channel" && bun install --no-summary)
ok "line-channel 依賴已安裝"

# ── 4. 初始化資料庫 ─────────────��────────────────────

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

# ── 5. 生成最小 .mcp.json ───────────��────────────────

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
[[ -f "$ROOT/.claude/settings.local.json" ]] && ok "settings.local.json" || err "settings.local.json 不存在"

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
