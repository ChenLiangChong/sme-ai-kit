#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════
#  SME-AI-Kit 安裝精靈
#  支援 macOS + Linux (WSL)
#
#  用法：
#    1. cp .env.template .env   ← 填入 4 個設定值
#    2. bash install.sh         ← 全自動
#
#  或不建 .env，直接跑 install.sh 會互動詢問。
# ═══════════════════════════════════════════════════════
set -euo pipefail

GREEN='\033[92m'; YELLOW='\033[93m'; RED='\033[91m'
CYAN='\033[96m'; BOLD='\033[1m'; DIM='\033[2m'; RESET='\033[0m'

ROOT="$(cd "$(dirname "$0")" && pwd)"
OS="$(uname -s)"

ok()   { echo -e "  ${GREEN}✓${RESET} $1"; }
warn() { echo -e "  ${YELLOW}⚠${RESET} $1"; }
err()  { echo -e "  ${RED}✗${RESET} $1"; }
step() { echo -e "\n${BOLD}${CYAN}▶${RESET} ${BOLD}$1${RESET}"; }

# ── 平台偵測 ──────────────────────────────────────────

IS_MAC=false; IS_WSL=false; IS_LINUX=false
if [[ "$OS" == "Darwin" ]]; then
    IS_MAC=true
elif grep -qi microsoft /proc/version 2>/dev/null; then
    IS_WSL=true
    IS_LINUX=true
elif [[ "$OS" == "Linux" ]]; then
    IS_LINUX=true
fi

# ── 讀 .env ──────────────────────────────────────────

load_env() {
    if [[ -f "$ROOT/.env" ]]; then
        step "讀取 .env"
        # 只讀非註解、非空白的行
        while IFS='=' read -r key val; do
            key="$(echo "$key" | xargs)"
            val="$(echo "$val" | xargs)"
            [[ -z "$key" || "$key" == \#* ]] && continue
            export "$key=$val"
            ok "$key = ...${val: -8}"
        done < "$ROOT/.env"
        return 0
    fi
    return 1
}

# ── 輸入函式 ─────────────────────────────────────────

ask_text() {
    local prompt="$1" default="${2:-}"
    if $IS_MAC; then
        osascript -e "text returned of (display dialog \"$prompt\" default answer \"$default\" with title \"SME-AI-Kit\")" 2>/dev/null || echo "$default"
    else
        local result
        if [[ -n "$default" ]]; then
            read -rp "  $prompt [$default]: " result
            echo "${result:-$default}"
        else
            read -rp "  $prompt: " result
            echo "$result"
        fi
    fi
}

ask_secret() {
    local prompt="$1"
    if $IS_MAC; then
        osascript -e "text returned of (display dialog \"$prompt\" default answer \"\" with hidden answer with title \"SME-AI-Kit\")" 2>/dev/null || echo ""
    else
        local result
        read -rsp "  $prompt: " result
        echo "$result"
        echo >&2
    fi
}

notify() {
    local msg="$1"
    if $IS_MAC; then
        osascript -e "display notification \"$msg\" with title \"SME-AI-Kit\"" 2>/dev/null || true
    fi
    echo -e "\n  ${GREEN}${BOLD}$msg${RESET}"
}

# ── 1. 系統依賴安裝 ──────────────────────────────────

install_dependencies() {
    step "安裝系統依賴"

    if $IS_MAC; then
        # Homebrew
        if ! command -v brew &>/dev/null; then
            warn "正在安裝 Homebrew..."
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
            # Apple Silicon path
            if [[ -f /opt/homebrew/bin/brew ]]; then
                eval "$(/opt/homebrew/bin/brew shellenv)"
            fi
        fi
        ok "Homebrew"

        # Python
        if ! command -v python3 &>/dev/null || [[ "$(python3 -c 'import sys;print(sys.version_info >= (3,10))')" != "True" ]]; then
            warn "正在安裝 Python..."
            brew install python@3.12
        fi
        ok "Python $(python3 --version | cut -d' ' -f2)"

        # Bun
        if ! command -v bun &>/dev/null; then
            warn "正在安裝 Bun..."
            brew install oven-sh/bun/bun
        fi
        ok "Bun → $(which bun)"

        # ngrok
        if ! command -v ngrok &>/dev/null; then
            warn "正在安裝 ngrok..."
            brew install ngrok/ngrok/ngrok
        fi
        ok "ngrok"

        # Node/npm
        if ! command -v npm &>/dev/null; then
            warn "正在安裝 Node.js..."
            brew install node
        fi
        ok "Node.js"

        # Claude Code
        if ! command -v claude &>/dev/null; then
            warn "正在安裝 Claude Code..."
            npm install -g @anthropic-ai/claude-code
        fi
        if command -v claude &>/dev/null; then
            ok "Claude Code"
        fi

        ok "expect（macOS 內建）"

    elif $IS_LINUX; then
        if ! command -v python3 &>/dev/null; then
            warn "正在安裝 Python..."
            sudo apt-get update -qq && sudo apt-get install -y -qq python3 python3-venv
        fi
        ok "Python $(python3 --version | cut -d' ' -f2)"

        if ! command -v bun &>/dev/null; then
            warn "正在安裝 Bun..."
            curl -fsSL https://bun.sh/install | bash
            export PATH="$HOME/.bun/bin:$PATH"
        fi
        ok "Bun"

        if ! command -v ngrok &>/dev/null; then
            warn "正在安裝 ngrok..."
            curl -fsSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null
            echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | sudo tee /etc/apt/sources.list.d/ngrok.list
            sudo apt-get update -qq && sudo apt-get install -y -qq ngrok
        fi
        ok "ngrok"

        if ! command -v expect &>/dev/null; then
            warn "正在安裝 expect..."
            sudo apt-get install -y -qq expect
        fi
        ok "expect"

        if ! command -v claude &>/dev/null; then
            if command -v npm &>/dev/null; then
                warn "正在安裝 Claude Code..."
                npm install -g @anthropic-ai/claude-code
            fi
        fi
        if command -v claude &>/dev/null; then
            ok "Claude Code"
        fi
    fi
}

# ── 2. 收集密鑰 ──────────────────────────────────────

collect_credentials() {
    # 已從 .env 載入就跳過
    if [[ -n "${LINE_TOKEN:-}" && -n "${LINE_SECRET:-}" && -n "${NGROK_AUTHTOKEN:-}" && -n "${NGROK_DOMAIN:-}" ]]; then
        step "密鑰已從 .env 載入"
        return
    fi

    step "收集設定資訊"
    echo -e "  ${DIM}提示：也可以先填 .env 檔再跑 install.sh，就不用在這裡輸入${RESET}"
    echo -e "  ${DIM}  cp .env.template .env && nano .env${RESET}"
    echo ""

    if [[ -z "${LINE_TOKEN:-}" ]]; then
        export LINE_TOKEN
        LINE_TOKEN="$(ask_secret "LINE Channel Access Token")"
        [[ -z "$LINE_TOKEN" ]] && { err "LINE Token 為必填"; exit 1; }
        ok "LINE Token: ...${LINE_TOKEN: -8}"
    fi

    if [[ -z "${LINE_SECRET:-}" ]]; then
        export LINE_SECRET
        LINE_SECRET="$(ask_secret "LINE Channel Secret")"
        [[ -z "$LINE_SECRET" ]] && { err "LINE Secret 為必填"; exit 1; }
        ok "LINE Secret: ...${LINE_SECRET: -6}"
    fi

    if [[ -z "${NGROK_AUTHTOKEN:-}" ]]; then
        export NGROK_AUTHTOKEN
        NGROK_AUTHTOKEN="$(ask_secret "ngrok Authtoken")"
        [[ -z "$NGROK_AUTHTOKEN" ]] && { err "ngrok Authtoken 為必填"; exit 1; }
    fi

    if [[ -z "${NGROK_DOMAIN:-}" ]]; then
        export NGROK_DOMAIN
        NGROK_DOMAIN="$(ask_text "ngrok 固定域名（例：xxx-yyy.ngrok-free.dev）")"
        [[ -z "$NGROK_DOMAIN" ]] && { err "ngrok 域名為必填"; exit 1; }
    fi

    # 清理域名格式
    NGROK_DOMAIN="${NGROK_DOMAIN#https://}"
    NGROK_DOMAIN="${NGROK_DOMAIN#http://}"
    NGROK_DOMAIN="${NGROK_DOMAIN%/}"
    export NGROK_DOMAIN

    # 設定 ngrok authtoken
    ngrok config add-authtoken "$NGROK_AUTHTOKEN" 2>/dev/null
    ok "ngrok Authtoken 已設定"
    ok "ngrok 域名：$NGROK_DOMAIN"
}

# ── 3. 呼叫 install.py ──────────────────────────────

run_install_py() {
    step "執行核心安裝（install.py）"
    cd "$ROOT"
    python3 install.py
}

# ── 4. 開機自啟 ──────────────────────────────────────

setup_autostart() {
    step "設定開機自動啟動"

    if $IS_MAC; then
        local label="com.sme-ai-kit.daemon"
        local plist_dir="$HOME/Library/LaunchAgents"
        local plist_path="$plist_dir/$label.plist"

        # 組合 PATH（確保 brew/bun/node 都找得到）
        local extra_path="/usr/local/bin:/opt/homebrew/bin:$HOME/.bun/bin"
        if command -v bun &>/dev/null; then
            extra_path="$(dirname "$(which bun)"):$extra_path"
        fi
        if command -v node &>/dev/null; then
            extra_path="$(dirname "$(which node)"):$extra_path"
        fi

        mkdir -p "$plist_dir"

        cat > "$plist_path" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$label</string>
    <key>ProgramArguments</key>
    <array>
        <string>$ROOT/start.sh</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$ROOT</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$ROOT/data/daemon.log</string>
    <key>StandardErrorPath</key>
    <string>$ROOT/data/daemon-error.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>$extra_path:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
PLIST

        launchctl unload "$plist_path" 2>/dev/null || true
        launchctl load "$plist_path"
        ok "LaunchAgent 已設定（開機自動啟動）"
        warn "建議：系統設定 → 電池 → 永不休眠"

    elif $IS_WSL; then
        local cron_line="@reboot cd $ROOT && ./start.sh >> $ROOT/data/daemon.log 2>&1"
        (crontab -l 2>/dev/null | grep -v "sme-ai-kit"; echo "$cron_line") | crontab -
        ok "crontab @reboot 已設定"

    elif $IS_LINUX; then
        local service_dir="$HOME/.config/systemd/user"
        mkdir -p "$service_dir"

        cat > "$service_dir/sme-ai-kit.service" <<SERVICE
[Unit]
Description=SME-AI-Kit Daemon
After=network.target

[Service]
Type=simple
WorkingDirectory=$ROOT
ExecStart=$ROOT/start.sh
Restart=always
RestartSec=10
Environment=PATH=/usr/local/bin:/usr/bin:/bin:$HOME/.bun/bin

[Install]
WantedBy=default.target
SERVICE

        systemctl --user daemon-reload
        systemctl --user enable sme-ai-kit.service
        ok "systemd user service 已設定"
    fi
}

# ── main ──────────────────────────────────────────────

main() {
    echo ""
    echo -e "  ${BOLD}╔═══════════════════════════════════╗${RESET}"
    echo -e "  ${BOLD}║     SME-AI-Kit 安裝精靈     ║${RESET}"
    echo -e "  ${BOLD}╚═══════════════════════════════════╝${RESET}"
    echo -e "  ${DIM}路徑：$ROOT${RESET}"
    if $IS_MAC; then
        echo -e "  ${DIM}系統：macOS${RESET}"
    elif $IS_WSL; then
        echo -e "  ${DIM}系統：Windows (WSL)${RESET}"
    else
        echo -e "  ${DIM}系統：Linux${RESET}"
    fi

    load_env || true          # 1. 嘗試讀 .env
    install_dependencies      # 2. 系統依賴
    collect_credentials       # 3. 密鑰（.env 有就跳過）
    run_install_py            # 4. 核心安裝
    setup_autostart           # 5. 開機自啟

    notify "安裝完成！"

    echo ""
    echo -e "  ${BOLD}下一步：${RESET}"
    echo -e "  1. cd $ROOT && claude"
    echo -e "  2. Claude 啟動後自動執行開機流程"
    echo -e "  3. 跟 Claude 進行首次訪談"
    echo ""
}

main "$@"
