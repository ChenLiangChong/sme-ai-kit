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
│   (多 OA 單 port)│                          │
├──────────────────┴──────────────────────────┤
│              共用 SQLite DB                  │
│     business-db MCP (80+ tools)             │
│   + 多事業體（business_entities）支援        │
├─────────────────────────────────────────────┤
│   Skills: company-ops + social-media (+更多) │
└─────────────────────────────────────────────┘
```

## 核心特色

- **AI 營運中樞**：Claude 作為背景 daemon，24 小時監看 LINE 並代替人處理常規請求
- **雙 Session 架構**：CLI（自動化）+ Cowork（老闆主動查詢），共用同一個 SQLite DB
- **多事業體支援**：一套部署可同時服務多個品牌／部門，資料按 `business_unit` 區隔
- **多 LINE OA**：單一 process 透過路徑路由處理多個 LINE Official Account，每個 OA 對應一個事業體
- **反捏造原則**：老闆的規則必須附上原話 (`source_quote`)，AI 推斷的規則標記為 `inferred`
- **HITL 審核**：超過審核門檻的金額、對外行銷廣播、跨多步驟的批次資料變動、請假簽核都會先進核准流程；gate 比對 `resume_params`、單次消費（`consumed_at`）、逾 72h 自動過期，老闆可在 LINE 直接回「核准 #N / 駁回 #N」跨 session 放行
- **部門安全層（floor）**：每個 LINE / CLI session 可帶 `SME_FLOOR` 標示部門身份，兩道獨立的牆（檔案 sandbox + business-db MCP 工具白名單）依 `data/floor-map.json` 自動移除該層不該用的工具（HR 管理、刪帳、上報管理、機密規則切換、排程提醒等），財務工具去留由各層 `financial_visibility` 控制；敏感欄位（員工備註、請假原因）對受限層做欄位級遮蔽。未設層＝全權限（開發 / 老闆層）。威脅模型是防內部員工越權、非防駭客級注入
- **主動上報（escalation）**：高風險或越權動作（記帳超門檻、刪帳、員工權限變動、訂單已出貨被取消、品檢未過、審核待簽）在執行那支工具的同一交易內硬接線寫入待投遞佇列（AI agent 跳不過），由 cron 保證層 / `claude -p` 品質層 / in-session 即時層三路投遞主動通知老闆。只通知、不擋動作
- **排程提醒**：`schedule_reminder` 排定一次性或週期性（daily / weekdays / weekly / monthly）提醒，由 OS cron 派工器以 at-most-once 投遞到指定 LINE 對象（錯過時點不補發、不洗版）；`list_reminders` / `cancel_reminder` 管理。屬全權限層工具（受限部門層不可排）
- **請假管理**：假別配額、員工自助請假、HITL 簽核（假別 `requires_approval=true` 時 `request_leave` 自動建 approval）、餘額查詢與待簽佇列
- **知識機密軸**：規則 / 決策可標記 `confidential`，非全權限部門層的 `query_knowledge` 自動過濾機密內容；`set_rule_confidential` 可事後調整可見度（僅全權限層）

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

#### 單 OA vs 多 OA

- **單 OA 模式**：只需 `CHANNEL_ACCESS_TOKEN` + `CHANNEL_SECRET` 兩個 env var
- **多 OA 模式**：建立 `data/line-channels.json`（可參考 `data/line-channels.example.json`），
  為每個 LINE Official Account 指定 `access_token`、`channel_secret`、`business_unit`，
  Webhook 路徑自動變成 `/webhook/{channel_id}`，訊息 meta 會帶上 `business_unit`，
  Claude 據此判斷該訊息屬於哪個事業體並正確歸屬訂單／帳務／任務。

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
7. 假別與年度配額（特休 / 病假 / 事假，是否需簽核）
8. LINE 綁定（員工掃 QR code 加好友）

---

## 目錄結構

```
sme-ai-kit/
├── install.sh              # 安裝腳本
├── start.sh                # daemon 啟動（expect 自動確認）
├── CLAUDE.md               # AI 助理操作手冊
├── AGENTS.md               # 同 CLAUDE.md（Codex / Cursor / Gemini 讀，.githooks 自動同步）
├── mcp-servers/
│   ├── business-db/        # 企業資料庫 MCP（工具清單見 modules/*/tools.py）
│   ├── line-channel/       # LINE Channel MCP（reply / mark_read，支援多 OA）
│   └── social/             # 社群媒體 MCP（FB / IG / Threads，工具見 server）
├── .claude/
│   ├── skills/
│   │   ├── company-ops/    # 公司營運（多模組，見 SKILL.md）
│   │   ├── social-media/   # 社群行銷（多模組，見 SKILL.md）
│   │   ├── sme-design/     # 報告 / 簡報 / battlecard 設計（HTML→PPT）
│   │   └── docx/ pdf/ pptx/ xlsx/   # 文件處理通用 skill
│   └── settings.local.json
├── data/                   # DB + 媒體（gitignored）
│   ├── business.db
│   ├── line-channels.json       # 多 OA 設定（多事業體時使用）
│   └── line-channels.example.json
└── docs/                   # 文件
```

## 多事業體（multi-business-unit）

如果一間公司同時經營多個品牌／部門／事業單位（例如：內容產品、經銷物流、實體空間），SME-AI-Kit 用 `business_unit` 欄位把資料貫穿整個系統：

| 層級 | 行為 |
|------|------|
| LINE OA | 每個 OA 在 `line-channels.json` 綁定一個 `business_unit`，訊息自動帶此 meta |
| 訂單／帳務／任務／庫存／規則 | 建立時都要帶 `business_unit`，查詢時可按事業體篩選 |
| 客戶條件 | `set_customer_entity_terms` 設定客戶對某事業體的折扣率與付款條件，覆寫客戶預設值 |
| 審核門檻 | 每個事業體可在 `business_entities` 表設定自己的 `approval_threshold`，優先於公司預設 |
| 規則 | 全域規則（公司層級）+ 事業體專屬規則，`query_knowledge` 會自動合併 |
| 員工 | `employees.business_units` 欄位（逗號分隔）限制操作範圍 |

相關 MCP tools：`register_business_entity`、`list_business_entities`、`set_customer_entity_terms`。建立資料時支援 `business_unit` 參數的 tools 包括 `create_order`、`record_transaction`、`create_task`、`update_stock`、`store_fact` 等，查詢時則有 `check_stock`、`low_stock_alerts`、`check_overdue`、`monthly_summary`、`query_knowledge`、`list_orders`、`list_tasks` 等。

## 日常營運

| 時間 | 做什麼 |
|------|--------|
| 早上 | Claude 自動跑營運摘要 + 庫存警報 + 逾期帳款 |
| 白天 | LINE 訊息即時處理、任務追蹤、記帳 |
| 傍晚 | 自動保存每日快照 |
| 月底 | 「出月報」→ 收支彙總 + 庫存盤點 |

## License

Private — 僅供授權客戶使用。
