# Client 001：In Love With My Space

> 首家導入客戶，空間設計/居家商品品牌，B2B 經銷模式

## 來源

老闆手寫三張筆記（`/打零工/` 目錄下三張照片）

---

## 老闆的業務流程（從手寫筆記解讀）

### 流程一：B2B 商品 Road Plan

```
市場調查 → 自主發想
    ↓
網路參考 → 簡報設計
    ↓
工廠打版 → 三版確認
    ↓
批量生產 → 全國台灣經銷
    ↓
行銷推播 → 完稿製作
    ↓
LINE Official → 接單、主動型合作開發
    ↓
回款結算 A/C
    ↓
循環

右側備註：創進款、付款
```

**本質**：商品從概念到變現的完整循環。重點在工廠打版管理、經銷商關係、LINE 接單、應收應付。

### 流程二：社群媒體 Funnel

```
內容創作
    ↓
投放內容
    ↓
導入 YouTube（主內容）
    ↓
拆分為：
├── Reels / Shorts / TikTok（短影音）
├── 精緻版 / 三重格 / 貼文（圖文）
└── Threads / YouTube 片段（微動態）
    ↓
目標客經營（每週更新）
```

**本質**：一魚多吃的內容策略。YouTube 是主戰場，拆成各平台格式。每週固定產出。

### 流程三：品牌 WFA「In Love With My Space」

```
概念發想
    ↓
配置設計、設計師
    ↓
去問文稿
    ↓
打版確認
    ↓
設計手稿
    ↓
再次修改
    ↓
最終主題

成長路徑（右側）：
故事起頭 → 練手經驗 → 技術到位 → 花你發想 → 優化產出
```

**本質**：設計案的製作流程 + 品牌成長階段。

---

## 對應 sme-ai-kit 模組

| 老闆的需求 | 對應模組 | 通用化方向 |
|-----------|---------|-----------|
| 產品開發追蹤（打版→確認→量產） | task-ops | → 通用的「多階段專案追蹤」 |
| 經銷商/供應商管理 | crm-ops | → customers 表加 type 欄位（客戶/供應商/經銷商） |
| LINE 接單 | line-comms | → 通用的「LINE 訂單處理流程」 |
| 應收應付追蹤 | accounting-ops | → transactions 加 status（pending/paid）和 due_date |
| 工廠進貨 + 經銷出貨 | inventory-ops | → 已有，location 區分倉庫/門市 |
| 內容行銷排程 | task-ops | → tasks 加 category='content'，當排程表 |
| 品牌語氣 | brand-voice | → 通用的品牌語氣設定流程 |
| 社群 Funnel | task-ops + report-gen | → 每週內容追蹤 + 成效報告 |

## 需要通用化進 sme-ai-kit 的改動

### Schema 層面

1. **customers 表加 type**
   - `type TEXT DEFAULT 'customer'` — customer / supplier / distributor
   - 通用化：所有公司都會有供應商和客戶的區分

2. **transactions 表加應收應付**
   - `payment_status TEXT DEFAULT 'paid'` — paid / pending / overdue
   - `due_date TEXT` — 帳期到期日
   - 通用化：B2B 都有帳期問題

3. **tasks 表加 category**
   - `category TEXT` — general / production / content / design / delivery
   - 通用化：不同類型的任務方便篩選和報表

### Skill 層面

- task-ops 加「多階段專案」流程（概念→設計→打版→確認→量產→出貨）
- crm-ops 加「供應商管理」子流程
- accounting-ops 加「應收帳款追蹤」邏輯
- 加一個 content-calendar 的概念進 task-ops（每週內容排程）

---

## 導入計畫

### 第一次訪談（knowledge-capture）
1. 三張圖的流程完整口述 → 存 business_rules
2. 品牌語氣設定（收集「In Love With My Space」範例文案）
3. 建立員工名冊 + LINE 綁定
4. 建立經銷商 + 供應商清單
5. 建立商品 SKU 清單
6. 設定審核門檻（多少金額需要老闆核准）

### 第一週
- LINE 接單 → Claude 處理 → 庫存確認 → 回覆
- 每日 ops-dashboard
- 任務追蹤（打版進度、內容排程）

### 第二週+
- 收支記帳 → 應收追蹤
- 經銷商 RFM 分析
- 內容排程自動提醒
- 月報
