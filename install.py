#!/usr/bin/env python3
"""SME-AI-Kit 核心安裝 — 由 install.sh 呼叫。

從環境變數讀取密鑰（install.sh 已 export），處理：
  venv → bun → .mcp.json → DB → CLAUDE.md → 驗證
"""

import json
import os
import importlib
import platform
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

# ── 顏色 ──────────────────────────────────────────────

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

ROOT = Path(__file__).parent.resolve()


def step(msg: str):
    print(f"\n{BOLD}{CYAN}▶{RESET} {BOLD}{msg}{RESET}")


def ok(msg: str):
    print(f"  {GREEN}✓{RESET} {msg}")


def warn(msg: str):
    print(f"  {YELLOW}⚠{RESET} {msg}")


def err(msg: str):
    print(f"  {RED}✗{RESET} {msg}")


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, check=True, capture_output=True, text=True, **kwargs)
    except subprocess.CalledProcessError as e:
        err(f"指令失敗：{' '.join(cmd)}")
        if e.stderr:
            print(f"    {e.stderr.strip()[:200]}")
        raise


# ── 1. Python venv ────────────────────────────────────

def setup_venv():
    step("建立 Python 虛擬環境")

    venv_path = ROOT / ".venv"
    pip = venv_path / "bin" / "pip"

    if venv_path.exists() and pip.exists():
        ok(".venv 已存在")
    else:
        subprocess.run([sys.executable, "-m", "venv", str(venv_path)], check=True)
        ok(".venv 已建立")

    for req in (ROOT / "mcp-servers").rglob("requirements.txt"):
        run([str(pip), "install", "-q", "-r", str(req)])
        ok(f"已安裝 {req.relative_to(ROOT)}")


# ── 2. Bun 依賴 ──────────────────────────────────────

def setup_bun():
    step("安裝 LINE Channel 依賴（Bun）")

    channel_dir = ROOT / "mcp-servers" / "line-channel"
    if not channel_dir.exists():
        err("mcp-servers/line-channel/ 不存在")
        sys.exit(1)

    run(["bun", "install", "--no-summary"], cwd=str(channel_dir))
    ok("line-channel 依賴已安裝")


# ── 平台偵測 ──────────────────────────────────────────

IS_MAC = platform.system() == "Darwin"
IS_WSL = "microsoft" in platform.uname().release.lower() if platform.system() == "Linux" else False


def _get_desktop_config_path() -> Path | None:
    """取得 Claude Desktop 全局設定檔路徑（只回傳已存在或可建立的路徑）。"""
    if IS_MAC:
        p = Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
        # macOS: 目錄不存在就建（本地檔案系統，安全）
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    if IS_WSL:
        # 掃 /mnt/c/Users/*/AppData/Roaming/Claude/（只找已存在的）
        try:
            for user_dir in Path("/mnt/c/Users").iterdir():
                claude_dir = user_dir / "AppData" / "Roaming" / "Claude"
                if claude_dir.is_dir():
                    return claude_dir / "claude_desktop_config.json"
        except (PermissionError, OSError):
            pass
    return None


# ── 3. 生成 MCP 設定 ─────────────────────────────────

def generate_mcp_json():
    step("生成 MCP 設定")

    line_token = os.environ.get("LINE_TOKEN", "")
    line_secret = os.environ.get("LINE_SECRET", "")
    ngrok_domain = os.environ.get("NGROK_DOMAIN", "")

    python_bin = str(ROOT / ".venv" / "bin" / "python3")
    db_path = str(ROOT / "data" / "business.db")

    # 找 bun 的絕對路徑（Mac 上 Claude Code 的 PATH 可能不含 brew/bun）
    bun_bin = shutil.which("bun") or "bun"

    # ── Claude Code 用的 .mcp.json ──

    code_config = {
        "mcpServers": {
            "business-db": {
                "command": python_bin,
                "args": [str(ROOT / "mcp-servers" / "business-db" / "server.py")],
                "env": {"SME_DB_PATH": db_path},
            },
        }
    }

    if line_token and line_secret:
        line_env = {
            "CHANNEL_ACCESS_TOKEN": line_token,
            "CHANNEL_SECRET": line_secret,
            "LINE_CHANNEL_PORT": "8789",
            "SME_DB_PATH": db_path,
        }
        if ngrok_domain:
            line_env["NGROK_DOMAIN"] = ngrok_domain

        code_config["mcpServers"]["line"] = {
            "type": "channel",
            "command": bun_bin,
            "args": ["run", str(ROOT / "mcp-servers" / "line-channel" / "server.ts")],
            "env": line_env,
        }

    mcp_path = ROOT / ".mcp.json"
    mcp_path.write_text(json.dumps(code_config, indent=2, ensure_ascii=False), encoding="utf-8")
    ok(f".mcp.json → {list(code_config['mcpServers'].keys())}")

    # ── Claude Desktop 用的全局設定 ──

    desktop_path = _get_desktop_config_path()
    if not desktop_path:
        warn("找不到 Claude Desktop 設定檔（未安裝？）— 跳過")
        return

    # 讀取現有設定（可能已有其他 MCP server）
    if desktop_path.exists():
        desktop_config = json.loads(desktop_path.read_text(encoding="utf-8"))
    else:
        desktop_config = {}

    if "mcpServers" not in desktop_config:
        desktop_config["mcpServers"] = {}

    if IS_WSL:
        # WSL: Desktop 在 Windows 端，指令要用 wsl 包裝
        env_exports = f"export SME_DB_PATH='{db_path}'"
        desktop_config["mcpServers"]["sme-business-db"] = {
            "command": "wsl",
            "args": ["bash", "-c", f"{env_exports} && {python_bin} {ROOT / 'mcp-servers' / 'business-db' / 'server.py'}"],
        }
        # LINE channel 不放 Desktop（Desktop 不支援 Channel plugin，由 daemon 處理）
    else:
        # macOS: 直接用一樣的路徑
        desktop_config["mcpServers"]["sme-business-db"] = {
            "command": python_bin,
            "args": [str(ROOT / "mcp-servers" / "business-db" / "server.py")],
            "env": {"SME_DB_PATH": db_path},
        }

    desktop_path.write_text(json.dumps(desktop_config, indent=2, ensure_ascii=False), encoding="utf-8")
    ok(f"Claude Desktop 設定已更新 → {desktop_path}")


# ── 4. 初始化資料庫 ──────────────────────────────────

def init_database():
    step("初始化資料庫")

    data_dir = ROOT / "data"
    data_dir.mkdir(exist_ok=True)

    for subdir in ["line", "orders", "customers", "tasks", "inventory", "exports"]:
        (data_dir / "media" / subdir).mkdir(parents=True, exist_ok=True)

    db_path = data_dir / "business.db"
    schema_path = ROOT / "mcp-servers" / "business-db" / "schema.sql"

    if db_path.exists():
        warn(f"business.db 已存在（{db_path.stat().st_size / 1024:.0f} KB）— 跳過")
        return

    if not schema_path.exists():
        err(f"schema.sql 不存在：{schema_path}")
        sys.exit(1)

    db = sqlite3.connect(str(db_path))
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=5000")
    db.executescript(schema_path.read_text(encoding="utf-8"))
    db.close()
    ok(f"空白資料庫已建立 → {db_path}")


# ── 5. CLAUDE.md ─────────────────────────────────────

def ensure_claude_md():
    step("檢查 CLAUDE.md")

    claude_md = ROOT / "CLAUDE.md"
    if claude_md.exists():
        ok("CLAUDE.md 已存在")
        return

    template = ROOT / "CLAUDE.md.template"
    if not template.exists():
        err("CLAUDE.md 和 CLAUDE.md.template 都不存在！")
        sys.exit(1)

    content = template.read_text(encoding="utf-8")
    for key, val in {
        "company_name": "本公司",
        "boss_title": "老闆",
        "boss_name": "（待設定）",
        "industry": "（待設定）",
        "employee_count": "（待設定）",
        "business_hours": "（待設定）",
        "approval_threshold": "5000",
        "stock_threshold": "10",
    }.items():
        content = content.replace(f"{{{{{key}}}}}", val)

    claude_md.write_text(content, encoding="utf-8")
    ok("已從 template 生成 CLAUDE.md（首次訪談時更新）")


# ── 6. 驗證 ──────────────────────────────────────────

def verify() -> int:
    step("驗證安裝結果")

    errors = 0

    # DB
    db_path = ROOT / "data" / "business.db"
    if db_path.exists():
        db = sqlite3.connect(str(db_path))
        tables = [r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()]
        db.close()
        ok(f"資料庫：{len(tables)} 張表")
    else:
        err("資料庫不存在"); errors += 1

    # .mcp.json
    mcp_path = ROOT / ".mcp.json"
    if mcp_path.exists():
        config = json.loads(mcp_path.read_text())
        servers = list(config.get("mcpServers", {}).keys())
        ok(f".mcp.json：{servers}")
    else:
        err(".mcp.json 不存在"); errors += 1

    # CLAUDE.md
    if (ROOT / "CLAUDE.md").exists():
        ok("CLAUDE.md")
    else:
        err("CLAUDE.md 不存在"); errors += 1

    # Skills
    skills_dir = ROOT / ".claude" / "skills"
    if skills_dir.exists():
        skills = sorted(
            d.name for d in skills_dir.iterdir()
            if d.is_dir() and (d / "SKILL.md").exists()
        )
        ok(f"Skills：{', '.join(skills)}")

    # settings.local.json
    if (ROOT / ".claude" / "settings.local.json").exists():
        ok("settings.local.json")

    # business-db server（用 venv Python 驗證）
    try:
        venv_python = str(ROOT / ".venv" / "bin" / "python3")
        test_script = (
            "import sys; sys.path.insert(0, 'mcp-servers/business-db'); "
            "import server; "
            "print(len(server.mcp._tool_manager._tools))"
        )
        result = subprocess.run(
            [venv_python, "-c", test_script],
            capture_output=True, text=True, cwd=str(ROOT),
            env={**os.environ, "SME_DB_PATH": str(db_path)},
        )
        if result.returncode == 0:
            tool_count = result.stdout.strip()
            ok(f"business-db：{tool_count} 個 MCP tools")
        else:
            err(f"business-db 載入失敗：{result.stderr.strip()[:200]}")
            errors += 1
    except Exception as e:
        err(f"business-db 驗證失敗：{e}"); errors += 1

    return errors


# ── main ──────────────────────────────────────────────

def main():
    setup_venv()
    setup_bun()
    generate_mcp_json()
    init_database()
    ensure_claude_md()
    errors = verify()

    if errors:
        err(f"{errors} 個項目有問題")
        sys.exit(1)
    else:
        ok("核心安裝驗證通過")


if __name__ == "__main__":
    main()
