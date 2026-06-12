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
    # bubblewrap = Claude Code 在 Linux 的 sandbox 後端：floored 層的 line-runtime-*.json 設
    # sandbox.enabled + failIfUnavailable=true，缺 bwrap → 受限層 session fail-closed 起不來
    # （macOS 用內建 sandbox-exec、不需此套件，故只在 Linux 段裝）。
    command -v bwrap &>/dev/null || sudo apt-get install -y -qq bubblewrap
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

# ── 8. cron：上報保證層 + 律所時限「漏不掉」三支（缺一支都留靜默失敗破口）──────
# 上報「品質層」是 business-db commit 後即時起的 claude -p；以下 cron 是「保證層 / 時間驅動」：
#   - flush_escalations：每 2 分確定性掃 pending_escalations 補送 claude -p 漏的/掛的。
#   - scan_deadlines：每日掃 pending 時限 → 命中提醒節點/逾期即上報（同時落 heartbeat 證明在跑）。
#   - scan_heartbeat（#H1 watchdog）：每 2h 自證活著 + 偵測 scan_deadlines 失聯 → scan_stalled 上報。
#   - scan_unconfirmed_intake（#H2）：每 4h 跟催「抽出但人忘了確認入庫」的待確認暫存。
# 後三支是「漏期=執業過失」的核心防線；以前只在 privacy-deploy.md 當手動 crontab、操作者易漏 → 改自動裝。

step "安裝 cron（上報保證層 + 時限掃描/哨兵/跟催）"

# 冪等安裝一行 cron（marker 出現在註解行、用來去重；重跑不重複加）。
add_cron() {
    local marker="$1" line="$2" desc="$3"
    if crontab -l 2>/dev/null | grep -qF "$marker"; then
        ok "$desc 已存在、不重複加"
    elif ( crontab -l 2>/dev/null; echo "# === $marker ==="; echo "$line" ) | crontab -; then
        ok "$desc 已安裝"
    else
        err "crontab 寫入失敗、請手動加一行：$line"
    fi
}

if command -v crontab >/dev/null 2>&1; then
    add_cron "SME-AI-Kit escalation flusher" \
        "*/2 * * * * SME_DB_PATH=$DB $VENV/bin/python3 $ROOT/mcp-servers/business-db/flush_escalations.py >> $ROOT/data/flush.log 2>&1" \
        "上報投遞保證層 flusher（每 2 分、log: data/flush.log）"
    add_cron "SME-AI-Kit deadline scanner" \
        "0 7 * * * SME_DB_PATH=$DB $VENV/bin/python3 $ROOT/mcp-servers/business-db/scan_deadlines.py >> $ROOT/data/scan.log 2>&1" \
        "時限掃描 scan_deadlines（每日 07:00、落 heartbeat、log: data/scan.log）"
    add_cron "SME-AI-Kit deadline heartbeat watchdog" \
        "17 */2 * * * SME_DB_PATH=$DB $VENV/bin/python3 $ROOT/mcp-servers/business-db/scan_heartbeat.py >> $ROOT/data/heartbeat.log 2>&1" \
        "健康哨兵 watchdog scan_heartbeat（每 2 小時、#H1、log: data/heartbeat.log）"
    add_cron "SME-AI-Kit unconfirmed intake reminder" \
        "37 */4 * * * SME_DB_PATH=$DB $VENV/bin/python3 $ROOT/mcp-servers/business-db/scan_unconfirmed_intake.py >> $ROOT/data/intake.log 2>&1" \
        "待確認跟催 scan_unconfirmed_intake（每 4 小時、#H2、log: data/intake.log）"
    if [[ "$IS_LINUX" == true ]] && ! pgrep -x cron >/dev/null 2>&1 && ! pgrep -x crond >/dev/null 2>&1; then
        err "cron daemon 沒在跑 → 上述 cron 全不會觸發（時限不會自動倒數、哨兵也不會報）。啟動：sudo service cron start（WSL 建議 systemctl enable --now cron）"
    fi
else
    err "找不到 crontab → 上報保證層 + 時限掃描/哨兵/跟催都不會自動跑；請手動定時跑 mcp-servers/business-db/{flush_escalations,scan_deadlines,scan_heartbeat,scan_unconfirmed_intake}.py"
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
