# data/ 目錄結構

所有業務資料都在這個目錄下。不進 git（在 .gitignore 中排除），包含憑證與客戶資料。

```
data/
├── business.db                  ← SQLite 企業資料庫（51 tools 操作這一個檔）
├── line-channels.json           ← LINE OA 多事業體設定檔（含 access token，已 gitignore）
├── line-channels.example.json   ← 範例檔（可進 git，供複製用）
└── media/
    ├── line/                    ← LINE 收到的原始媒體
    │   ├── images/              ← 圖片（.jpg）
    │   │   └── {messageId}.jpg
    │   ├── files/               ← 文件（.pdf, .xlsx, .docx 等）
    │   │   └── {messageId}.pdf
    │   ├── videos/              ← 影片（.mp4）暫不處理
    │   └── audio/               ← 語音（.m4a）暫不處理
    ├── orders/                  ← 訂單附件
    │   └── {orderId}/
    ├── customers/               ← 客戶附件
    │   └── {customerId}/
    ├── tasks/                   ← 任務附件
    │   └── {taskId}/
    ├── inventory/               ← 庫存附件
    └── exports/                 ← 系統產出的報表
        └── {日期}_{報表名}.xlsx/pdf/docx
```

---

## line-channels.json（多 LINE OA 設定）

一套 SME-AI-Kit 可同時服務多個 LINE Official Account，每個 OA 對應一個事業體。
`line-channel` MCP server 啟動時會優先讀取這個檔案；若不存在則 fallback 到環境變數
（`CHANNEL_ACCESS_TOKEN` + `CHANNEL_SECRET`）單 OA 模式。

### Schema

```jsonc
{
  "channels": {
    "<channel_id>": {
      "name":          "<這個 OA 的人類可讀名稱>",
      "access_token":  "<LINE Messaging API 的 Channel Access Token (long-lived)>",
      "channel_secret": "<LINE Messaging API 的 Channel Secret>",
      "business_unit": "<對應 business_entities.id，例如 brand_d、content、distribution>"
    },
    ...
  },
  "default_channel": "<省略 channel_id 時使用的 key>"
}
```

### 欄位意義

| 欄位 | 必填 | 作用 |
|------|------|------|
| `channels.<key>` | ✓ | key 就是 `channel_id`；會出現在每則 LINE 訊息的 `<channel channel_id="...">` meta |
| `name` | ✓ | 顯示用名稱，出現在 `list_channels()` 的回傳、回覆成功訊息 |
| `access_token` | ✓ | LINE 對應 OA 的長效 Channel Access Token |
| `channel_secret` | ✓ | 用來驗證 webhook 簽章 (HMAC-SHA256) |
| `business_unit` | 推薦 | 對應 `business_entities` 表的 `id`；如此這個 OA 收到的訊息 meta 會帶上 `business_unit`，後續 `create_order`、`record_transaction`、`create_task` 等建立資料時才能正確歸屬事業體 |
| `default_channel` | ✓ | 當 `reply`／`multicast` 未指定 `channel_id` 時用哪一個 OA；也決定 legacy `/webhook` 路徑的 fallback |

### 連動效應

- Webhook 路徑自動變成 `/webhook/{channel_id}`（例如 `/webhook/brand_d`、`/webhook/content`）
- ngrok 自動設定會對每個 channel 呼叫 LINE `PUT /v2/bot/channel/webhook/endpoint` 設定端點
- 訊息進 Claude 時 meta 為：`<channel source="line" chat_id="..." user="..." user_id="..." channel_id="..." channel_name="..." business_unit="...">`
- 回覆時 **必須傳入同一個 `channel_id`**，否則會透過錯誤的 OA 發送：`reply(channel_id="brand_d", chat_id="U...", text="...")`
- `line_messages` 與 `line_groups` 表會紀錄 `channel_id` 欄位，讀取／標記狀態時按 `channel_id` 隔離

### 新增一個 OA

1. LINE Developers Console 建立 Messaging API Channel → 複製 access token + channel secret
2. 在 business-db 先登錄事業體：`register_business_entity(id='newbrand', name='新品牌')`
3. 編輯 `data/line-channels.json` 新增一個 key
4. 重啟 `line-channel` MCP server（或重啟 Claude CLI）
5. ngrok domain 已設定的話會自動把 webhook endpoint 更新到 LINE

---

## business.db 主要 tables

| Table | 作用 |
|-------|------|
| `company` | 公司基本資料（單列）、審核門檻預設值 |
| `business_entities` | 事業體（品牌／部門）登錄表，可設事業體專屬審核門檻 |
| `employees` | 員工名冊；`business_units` 欄位（逗號分隔）限制能操作的事業體 |
| `customers` | 客戶／供應商／經銷商，含 `discount_rate` 與 `payment_terms` 預設 |
| `customer_entity_terms` | 客戶在特定事業體的折扣／付款條件覆寫（per customer × per business_unit） |
| `business_rules` | 營運規則／SOP／決策，`business_unit` 空值表全域，否則為事業體專屬 |
| `rule_relations` | 規則之間的關係（related／depends_on／conflicts_with） |
| `tasks` | 任務，含 `business_unit` 與父子任務支援 |
| `inventory` | 庫存（SKU 在不同事業體可重複） |
| `transactions` | 收支紀錄，含應收／逾期追蹤 |
| `orders` | 訂單（含 QC、出貨、付款狀態） |
| `approvals` | HITL 核准佇列（跨 session） |
| `attachments` | 附件索引（實體檔放 `media/` 下） |
| `daily_snapshots` | 每日營運快照（可按事業體） |
| `line_messages` | LINE 訊息紀錄，帶 `channel_id` |
| `line_groups` | LINE 群組登錄 |
| `interaction_log` | 操作軌跡 |
| `session_handoffs` | Context 壓縮前的交接摘要 |

完整欄位定義請看 `mcp-servers/business-db/schema.sql`。

---

## 檔案流向

1. **LINE 圖片** → `media/line/images/{messageId}.jpg` → Claude Read tool 辨識
2. **LINE 文件** → `media/line/files/{messageId}.pdf` → Claude Read / office skill 處理
3. **AI 歸類後** → `add_attachment(target_type='order', target_id=123, file_path='...')`
4. **報表產出** → `media/exports/2026-04_月報.xlsx`

## 備份

`business.db` + `line-channels.json` + `media/` 一起備份。
`line-channels.json` 含長效 access token，存放必須加密；若外流須立即在 LINE Developers Console 重發 token。
