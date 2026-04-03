# SME-AI-Kit

台灣中小企業（20-30 人）的「開箱即用」AI 營運中樞。

Claude 當你的數位管家 — 管任務、管庫存、管帳、管客戶、管 LINE，全部用講的。

## 成本

- Claude Max $100/月（老闆 + 全公司共用）
- LINE Official Account（免費方案即可）
- ngrok 免費帳號

## 安裝

```bash
git clone https://github.com/charlo0414/sme-ai-kit.git
cd sme-ai-kit
bash install.sh
```

### 前置作業（顧問事先準備）

1. **LINE Messaging API** — 到 [LINE Developers Console](https://developers.line.biz/console/) 建立 Channel，取得 Access Token 和 Secret
2. **ngrok** — 到 [ngrok](https://dashboard.ngrok.com/) 註冊，取得 Authtoken 和固定域名

### install.sh 會做的事

| 步驟 | macOS | WSL / Linux |
|------|-------|-------------|
| 安裝依賴 | `brew install` | `apt install` + `curl` |
| 收集密鑰 | 原生對話框 | Terminal 輸入 |
| Python venv | 自動建立 | 自動建立 |
| Bun 依賴 | 自動安裝 | 自動安裝 |
| .mcp.json | Claude Code + Desktop 都寫入 | Claude Code + Desktop 都寫入 |
| 資料庫 | 空白 14 張表 | 空白 14 張表 |
| 開機自啟 | LaunchAgent | crontab @reboot |

## 架構

```
┌─────────────────────────────────────────────┐
│                  Claude Max                  │
├──────────────────┬──────────────────────────┤
│   Claude Code    │    Claude Desktop        │
│   (背景 daemon)  │    (老闆直接用)          │
│   + LINE Channel │    + Cowork / Dispatch   │
├──────────────────┴──────────────────────────┤
│              共用 SQLite DB                  │
│    business-db MCP (38 tools)               │
├─────────────────────────────────────────────┤
│   Skills: company-ops + social-media        │
│   (10 + 23 個 reference modules)            │
└─────────────────────────────────────────────┘
```

- **Claude Code daemon**：背景常駐，即時處理 LINE 訊息
- **Claude Desktop / Cowork**：老闆的工作台，直接下指令
- **共用 SQLite**：WAL mode + busy_timeout，兩邊同時讀寫不衝突

## MCP Servers

| Server | 語言 | 功能 |
|--------|------|------|
| business-db | Python (FastMCP) | 38 tools — 知識/任務/員工/客戶/庫存/帳務/訂單/審核/附件/快照 |
| line-channel | TypeScript (Bun) | LINE 即時收發 — Channel plugin + ngrok + webhook |
| social | Python (FastMCP) | FB/IG/Threads 讀取（20 tools） |

## Skills

### company-ops（公司營運）

營運儀表板 · 任務管理 · 知識萃取 · 客戶管理 · 庫存管理 · 帳務管理 · LINE 通訊 · 品牌語氣 · 報表生成 · 新人導引 · 訂單管理

### social-media（社群行銷）

社群經營 · 社群分析 · 文案撰寫 · 內容生產 · 編輯校對 · Email 觸及 · 行銷營運 · 數據分析 · 競品心理 · 付費獲客 · 成長飛輪 · 留客防流失 · LINE 行銷 · 台灣市場 + PMM 策略模組 ×8

## 導入流程

```
bash install.sh          # 環境 + 設定（約 10 分鐘）
↓
claude                   # 啟動 Claude Code
↓
首次訪談                  # Claude 自動引導：
  → 公司名稱、產業        #   存入 DB，不用改 config
  → 員工名冊 + LINE 綁定
  → 商品 / 客戶 / 供應商
  → 品牌語氣
  → 審核門檻
↓
正式營運                  # LINE 訊息即時處理
```

## 目錄結構

```
sme-ai-kit/
├── install.sh              # 安裝入口（macOS + Linux）
├── install.py              # 核心安裝邏輯
├── start.sh                # daemon 啟動腳本（expect）
├── CLAUDE.md               # AI 助理的操作手冊
├── CLAUDE.md.template      # 客製化模板
├── mcp-servers/
│   ├── business-db/        # 企業資料庫 MCP
│   ├── line-channel/       # LINE Channel MCP
│   └── social/             # 社群媒體 MCP
├── .claude/
│   ├── skills/
│   │   ├── company-ops/    # 公司營運技能包
│   │   └── social-media/   # 社群行銷技能包
│   ├── agents/             # PMM 專家 agents
│   ├── commands/           # 快捷指令
│   └── settings.local.json # MCP 權限
├── data/                   # 資料庫 + 媒體（gitignored）
└── docs/                   # 文件
```

## License

Private — 僅供授權客戶使用。
