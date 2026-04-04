# SME-AI-Kit

台灣中小企業的 AI 營運中樞 — Claude 當你的數位管家。

## 架構

```
┌─────────────────────────────────────────────┐
│                Claude Max ($100/月)           │
├──────────────────┬──────────────────────────┤
│   Claude Code    │    Claude Desktop        │
│   (背景 daemon)  │    (老闆直接用)          │
│   + LINE Channel │    + Cowork / Dispatch   │
├──────────────────┴──────────────────────────┤
│              共用 SQLite DB                  │
│     business-db MCP (42 tools)              │
├─────────────────────────────────────────────┤
│   Skills: company-ops (12) + social-media   │
└─────────────────────────────────────────────┘
```

## 成本

| 項目 | 費用 |
|------|------|
| Claude Max | NT$3,200/月 |
| LINE Official Account | 免費 |
| ngrok | 免費 |

---

## 顧問安裝指南

### 事前準備

開始安裝前，顧問需先完成：

1. **ngrok 帳號**
   - 到 [ngrok.com](https://ngrok.com) 註冊
   - Dashboard → Your Authtoken → 複製
   - Dashboard → Domains → 建立固定域名

2. **LINE Messaging API**
   - [LINE Developers Console](https://developers.line.biz/console/) 建立 Provider + Messaging API Channel
   - Channel → Messaging API → Issue Channel Access Token（長效）→ 複製
   - Channel → Basic settings → Channel Secret → 複製
   - Messaging API → Allow bot to join groups → Enabled

3. **LINE Official Account**
   - [LINE Official Account Manager](https://manager.line.biz/) 確認帳號已開通

### 安裝

```bash
git clone https://github.com/ChenLiangChong/sme-ai-kit.git
cd sme-ai-kit
bash install.sh
```

install.sh 會自動安裝：Python、Bun、ngrok、Claude Code、所有依賴、空白資料庫。

**不需要輸入任何密鑰** — 所有設定由 Claude 互動完成。

### 設定 LINE

```bash
claude
```

Claude 啟動後偵測到 LINE 未設定，會引導你：
1. 貼上 LINE Channel Access Token
2. 貼上 LINE Channel Secret
3. 貼上 ngrok Authtoken + 固定域名
4. Claude 自動生成設定、提示重啟

重啟後 Claude 會自動驗證 LINE 連線。

### 常見問題

| 問題 | 解法 |
|------|------|
| MCP tools 找不到 | 檢查 .mcp.json 的路徑是否正確（用絕對路徑） |
| Claude Desktop 找不到 MCP | 需另外設定 Desktop config（Claude 會引導） |
| LINE 收不到訊息 | 確認 ngrok domain 正確、LINE webhook URL 是 `https://domain/webhook` |
| ngrok 連不上 | 確認 authtoken 正確：`ngrok config check` |

---

## 首次訪談

LINE 設定完成後，Claude 偵測到空 DB，自動進入首次訪談：

1. 公司基本資料（名稱、產業、審核門檻）
2. 員工名冊（姓名、職位、權限）
3. 客戶 / 供應商 / 經銷商
4. 商品庫存 SKU
5. 品牌語氣
6. 營運規則 / SOP
7. LINE 綁定（員工掃 QR code 加好友）

---

## 目錄結構

```
sme-ai-kit/
├── install.sh              # 安裝腳本
├── start.sh                # daemon 啟動（expect 自動確認）
├── CLAUDE.md               # AI 助理操作手冊
├── mcp-servers/
│   ├── business-db/        # 企業資料庫 MCP (42 tools)
│   ├── line-channel/       # LINE Channel MCP (6 tools)
│   └── social/             # 社群媒體 MCP
├── .claude/
│   ├── skills/
│   │   ├── company-ops/    # 公司營運（12 模組）
│   │   └── social-media/   # 社群行銷（23 模組）
│   └── settings.local.json
├── data/                   # DB + 媒體（gitignored）
└── docs/                   # 文件
```

## 日常營運

| 時間 | 做什麼 |
|------|--------|
| 早上 | Claude 自動跑營運摘要 + 庫存警報 + 逾期帳款 |
| 白天 | LINE 訊息即時處理、任務追蹤、記帳 |
| 傍晚 | 自動保存每日快照 |
| 月底 | 「出月報」→ 收支彙總 + 庫存盤點 |

## License

Private — 僅供授權客戶使用。
