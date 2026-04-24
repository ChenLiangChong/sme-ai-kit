# 分析與追蹤
Campaign 分析與 GA4（Google Analytics 4）/ GTM（Google Tag Manager，事件追蹤工具）追蹤設定。

---

> **台灣市場適用指引**
> - GA4/GTM 設定原則為通用框架，全球適用
> - 台灣需注意：貨幣設為 TWD、時區設為 Asia/Taipei、語言設為 zh-TW
> - 完整台灣市場數據見 [taiwan-market.md](taiwan-market.md)

> **工具可用性**：本模組會嘗試呼叫 `query_knowledge`（屬 business-db MCP）載入既有品牌／行銷脈絡。若該工具不可用（例如第一堂課只裝了 Claude Desktop + social-media skill，尚未安裝 SME-AI-Kit），請直接向使用者詢問所需的品牌／行銷資訊，不要因工具缺失而停止。
>
> **最小問題清單（沒 MCP 時先問這些）：**
> - 您的公司／品牌是什麼？主要產品或服務？
> - 目標客戶是誰？（規模、行業、痛點）
> - 目前的行銷／定位狀況？有什麼既有資料可以參考？
> - 目前有沒有 GA4 / GTM？追蹤的是哪些事件或轉換？

---

## campaign-analytics


# Campaign 分析

量產等級的 campaign 成效分析，含多點歸因建模、漏斗轉換分析與 ROI 計算。三支 Python CLI 工具用標準函式庫提供可重複的確定性分析 —— 無外部相依、無 API 呼叫、無機器學習模型。


## 輸入需求

所有分析接受結構化 JSON 輸入。格式範例如下。

### 歸因分析器

```json
{
  "journeys": [
    {
      "journey_id": "j1",
      "touchpoints": [
        {"channel": "organic_search", "timestamp": "2025-10-01T10:00:00", "interaction": "click"},
        {"channel": "email", "timestamp": "2025-10-05T14:30:00", "interaction": "open"},
        {"channel": "paid_search", "timestamp": "2025-10-08T09:15:00", "interaction": "click"}
      ],
      "converted": true,
      "revenue": 500.00
    }
  ]
}
```

### 漏斗分析器

```json
{
  "funnel": {
    "stages": ["Awareness", "Interest", "Consideration", "Intent", "Purchase"],
    "counts": [10000, 5200, 2800, 1400, 420]
  }
}
```

### Campaign ROI 計算器

```json
{
  "campaigns": [
    {
      "name": "Spring Email Campaign",
      "channel": "email",
      "spend": 5000.00,
      "revenue": 25000.00,
      "impressions": 50000,
      "clicks": 2500,
      "leads": 300,
      "customers": 45
    }
  ]
}
```

### 輸入驗證

執行腳本前，請先確認 JSON 有效且符合預期結構。常見錯誤：

- **必填 key 缺失**（例：`journeys`、`funnel.stages`、`campaigns`）→ 腳本會以描述性 `KeyError` 結束
- **漏斗陣列長度不一致**（`stages` 與 `counts` 必須等長）→ 會丟出 `ValueError`
- **ROI 資料中有非數值金額** → 會丟出 `TypeError`

可用 `python -m json.tool your_file.json` 驗證 JSON 語法後再餵給任何腳本。


## 輸出格式

所有腳本透過 `--format` 旗標支援兩種輸出格式：

- `--format text`（預設）：供人閱讀的表格與摘要
- `--format json`：供整合與 pipeline 使用的機器可讀 JSON


## 典型分析工作流

完整 campaign 檢視依三步驟進行：

1. **歸因** — 搞清楚哪些通路帶來轉換（多數情況用 time-decay 或 position-based 模型）
2. **漏斗** — 找出潛客在轉換路徑上從哪裡流失
3. **ROI** — 計算獲利能力，對標業界基準

先用歸因結果找出表現最好的通路，再把漏斗分析聚焦在那些通路的區段，最後用 ROI 指標驗證以決定預算重新分配的優先序。


## 分析元件

### 1. 歸因分析

五種業界標準歸因模型，把轉換功勞分配到各行銷通路：

| 模型 | 說明 | 最適用 |
|-------|-------------|----------|
| First-Touch（首次觸及） | 100% 功勞給第一次互動 | 品牌知名度 campaign |
| Last-Touch（末次觸及） | 100% 功勞給最後一次互動 | 直效回應 campaign |
| Linear（線性） | 所有觸點平均分配 | 平衡的多通路評估 |
| Time-Decay（時間衰減） | 越近的觸點分得越多 | 短銷售週期 |
| Position-Based（位置式） | 40/20/40 分配（首/中/末） | 全漏斗行銷 |

> Attribution（歸因）指將轉換功勞分配給銷售漏斗中的各行銷觸點，以判斷哪些通路實際帶動成果。

### 2. 漏斗分析

分析轉換漏斗以找出瓶頸與優化機會：

- 階段之間的轉換率與流失比例
- 自動找出瓶頸（絕對值最大與相對值最大的流失點）
- 整體漏斗轉換率
- 若提供多個區段則做區段比較

### 3. Campaign ROI 計算

計算完整 ROI 指標並與業界基準比對：

- **ROI**（Return On Investment，投資報酬率）：投資報酬率百分比
- **ROAS**（Return On Ad Spend）：廣告花費回報率
- **CPA**（Cost Per Acquisition）：每次獲客成本
- **CPL**（Cost Per Lead）：每次線索成本
- **CAC**（Customer Acquisition Cost）：客戶獲取成本
- **CTR**（Click-Through Rate）：點擊率
- **CVR**（Conversion Rate）：轉換率（從線索到客戶）
- 對照業界基準標出表現不佳的 campaign


## 最佳實務

1. **用多個歸因模型** — 至少比較 3 個模型三角驗證通路價值；沒有單一模型能講完全故事。
2. **設合適的回顧窗口** — time-decay 的半衰期要對齊您的平均銷售週期。
3. **區段化漏斗** — 比較不同區段（通路、cohort（同期群，依加入時間分組）、地區）找出成效驅動因素。
4. **先和自己的歷史比** — 業界基準提供 context，但歷史資料才是最相關的比較對象。
5. **定期跑 ROI 分析** — 活躍 campaign 每週、策略檢視每月。
6. **把所有成本納入** — 媒體花費之外，也要考慮創意、工具與人力成本，ROI 才準確。
7. **嚴謹記錄 A/B test（分組對照測試）** — 使用提供的模板確保統計有效性與清楚的決策標準。


## 限制

- **不做統計顯著性測試** — 腳本只提供描述性指標；p 值計算需要外部工具。
- **僅使用標準函式庫** — 無進階統計函式庫。適合多數 campaign 規模但不適用於超過 10 萬個 journey 的資料集。
- **離線分析** — 腳本分析靜態 JSON 快照；無即時資料連線或 API 整合。
- **單一幣別** — 所有金額假設為同一幣別；不支援幣別換算。
- **簡化的時間衰減** — 依可設定的半衰期做指數衰減；不考慮平假日或季節性。
- **無跨裝置追蹤** — 歸因以提供的 journey 資料為準；跨裝置身份解析需在上游處理。

## Related Skills

- 見本檔案下方的 analytics-tracking 區段 — 用於設定追蹤。不適合用來分析資料（那是本區段的工作）。
- **marketing-ops.md** — 行銷路由與上下文建構。用於把洞察路由到正確的執行模組。
- **paid-acquisition.md** — 付費廣告策略與創意。用於根據分析結果優化廣告花費。

---

## analytics-tracking


# 分析追蹤設定

本模組負責分析實作。目標是確保客戶旅程中每個有意義的行為都被正確、一致、且可用於決策地捕捉 —— 不是為了有資料而有資料。

壞追蹤比沒追蹤更糟。重複事件、參數缺失、未同意收集、轉換追蹤壞掉，都會讓決策建立在壞資料上。本模組專注於第一次就做對，或找出壞掉的地方並修好。

## 開始前

**先檢查既有品牌/行銷 context：**
使用 `query_knowledge(category='brand')` 和 `query_knowledge(category='marketing')` 檢查既有脈絡，避免重複詢問。

蒐集以下 context：

### 1. 目前狀況
- 已有 GA4 和／或 GTM 嗎？若有，哪裡壞掉或缺什麼？
- 技術堆疊是什麼？（React SPA、Next.js、WordPress、自刻等）
- 有 consent management platform（CMP）嗎？是哪個？
- 目前在追蹤哪些事件（如果有）？

### 2. 商業 Context
- 您的主要轉換行為是什麼？（註冊、購買、填表、開始免費試用）
- 關鍵微轉換是什麼？（瀏覽定價頁、發現功能、申請 demo）
- 有跑付費 campaign 嗎？（Google Ads、Meta、LinkedIn — 會影響轉換追蹤需求）

### 3. 目標
- 從零建置、稽核既有、或是除錯特定問題？
- 需要跨網域追蹤嗎？多個 property 或子網域？
- 有 server-side tagging 需求嗎？（GDPR 敏感市場、效能考量）

## 本模組的三種模式

### 模式 1：從零建置
沒有任何分析 — 會建立追蹤計畫、實作 GA4 與 GTM、定義事件分類、設定轉換。

### 模式 2：稽核既有追蹤
有追蹤但資料不可信、覆蓋不完整、或要加新目標。會稽核現況、補齊缺口、清理。

### 模式 3：除錯追蹤問題
特定事件缺失、轉換數字對不上、或 GTM Preview 顯示事件有觸發但 GA4 沒記錄。用結構化的除錯工作流處理。


## 事件分類設計

在動 GA4 或 GTM 之前先搞定這一塊。事後重構分類體系很痛苦。

### 命名慣例

**格式：** `object_action`（snake_case，動詞在後）

| ✅ 好 | ❌ 不好 |
|--------|--------|
| `form_submit` | `submitForm`、`FormSubmitted`、`form-submit` |
| `plan_selected` | `clickPricingPlan`、`selected_plan`、`PlanClick` |
| `video_started` | `videoPlay`、`StartVideo`、`VideoStart` |
| `checkout_completed` | `purchase`、`buy_complete`、`checkoutDone` |

**規則：**
- 一律 `noun_verb` 而非 `verb_noun`
- 只用小寫 + 底線 — 不用 camelCase、不用連字號
- 具體到可辨識但不要長到像一句話
- 時態一致：`_started`、`_completed`、`_failed`（不要混用過去／現在）

### 標準參數

每個事件在適用時都應包含：

| 參數 | 型別 | 範例 | 用途 |
|-----------|------|---------|---------|
| `page_location` | string | `https://app.co/pricing` | GA4 自動捕捉 |
| `page_title` | string | `Pricing - Acme` | GA4 自動捕捉 |
| `user_id` | string | `usr_abc123` | 連到您的 CRM/DB |
| `plan_name` | string | `Professional` | 依方案區段 |
| `value` | number | `99` | 營收／訂單金額 |
| `currency` | string | `USD` | 有 value 時必填 |
| `content_group` | string | `onboarding` | 頁面／流程分組 |
| `method` | string | `google_oauth` | 方法（註冊方式等） |

### 事件分類（SaaS／電商範例）

**核心漏斗事件：**
```
visitor_arrived         (page view — GA4 自動)
signup_started          (使用者點「註冊」)
signup_completed        (帳號建立成功)
trial_started           (免費試用開始)
onboarding_step_completed (參數：step_name, step_number)
feature_activated       (參數：feature_name)
plan_selected           (參數：plan_name, billing_period)
checkout_started        (參數：value, currency, plan_name)
checkout_completed      (參數：value, currency, transaction_id)
subscription_cancelled  (參數：cancel_reason, plan_name)
```

**微轉換事件：**
```
pricing_viewed
demo_requested          (參數：source)
form_submitted          (參數：form_name, form_location)
content_downloaded      (參數：content_name, content_type)
video_started           (參數：video_title)
video_completed         (參數：video_title, percent_watched)
chat_opened
help_article_viewed     (參數：article_name)
```


## GA4 設定

### Data Stream 設定

1. **建立 property**：GA4 → Admin → Properties → Create
2. **新增 web data stream**，填入網域
3. **Enhanced Measurement** — 全部啟用，然後檢視：
   - ✅ Page views（保留）
   - ✅ Scrolls（保留）
   - ✅ Outbound clicks（保留）
   - ✅ Site search（若有站內搜尋則保留）
   - ⚠️ Video engagement（若會手動追蹤影片則停用 — 避免重複）
   - ⚠️ File downloads（若會在 GTM 追蹤以取得更好參數則停用）
4. **設定網域** — 加入所有漏斗使用的子網域

### GA4 中的自訂事件

任何非自動收集的事件，建議在 GTM 建立（首選）或直接用 gtag：

**透過 gtag：**
```javascript
gtag('event', 'signup_completed', {
  method: 'email',
  user_id: 'usr_abc123',
  plan_name: "trial"
});
```

**透過 GTM data layer（首選 — 見 GTM 段落）：**
```javascript
window.dataLayer.push({
  event: 'signup_completed',
  signup_method: 'email',
  user_id: 'usr_abc123'
});
```

### 轉換設定

在 GA4 → Admin → Conversions 把下列事件標為轉換：
- `signup_completed`
- `checkout_completed`
- `demo_requested`
- `trial_started`（若與 signup 分開）

**規則：**
- 每個 property 最多 30 個轉換事件 — 精挑，不是全勾
- GA4 的轉換是回溯性的 — 打開後會套用到過去 6 個月歷史
- 除非要針對微轉換優化廣告 campaign，否則不要把它們標為轉換


## Google Tag Manager 設定

### Container 結構

```
GTM Container
├── Tags
│   ├── GA4 Configuration（在所有頁面觸發）
│   ├── GA4 Event — [event_name]（每個事件一個 tag）
│   ├── Google Ads Conversion（每個轉換行為一個）
│   └── Meta Pixel（若有跑 Meta 廣告）
├── Triggers
│   ├── All Pages
│   ├── DOM Ready
│   ├── Data Layer Event — [event_name]
│   └── Custom Element Click — [selector]
└── Variables
    ├── Data Layer Variables（dlv — 每個 dL key 一個）
    ├── Constant — GA4 Measurement ID
    └── JavaScript Variables（計算值）
```

### Tag 模式（常見範例）

**模式 1：Data Layer Push（最可靠）**

您的 app 推資料到 dataLayer → GTM 接到 → 送到 GA4。

```javascript
// 在 app 程式碼（事件發生時）：
window.dataLayer = window.dataLayer || [];
window.dataLayer.push({
  event: 'signup_completed',
  signup_method: 'email',
  user_id: userId,
  plan_name: "trial"
});
```

```
GTM Tag: GA4 Event
  Event Name: {{DLV - event}} 或寫死 "signup_completed"
  Parameters:
    signup_method: {{DLV - signup_method}}
    user_id: {{DLV - user_id}}
    plan_name: "dlv-plan-name"
Trigger: Custom Event - "signup_completed"
```

**模式 2：CSS Selector 點擊**

用於由 UI 元素觸發、但沒有 app 層級 hook 的事件。

```
GTM Trigger:
  Type: Click - All Elements
  Conditions: Click Element matches CSS selector [data-track="demo-cta"]

GTM Tag: GA4 Event
  Event Name: demo_requested
  Parameters:
    page_location: {{Page URL}}
```


## 轉換追蹤：各平台

### Google Ads

1. 在 Google Ads → Tools → Conversions 建立轉換行為
2. 匯入 GA4 轉換（建議 — 單一資料來源）或用 Google Ads tag
3. 設定歸因模型：**Data-driven**（若每月 >50 次轉換），否則用 **Last click**
4. 轉換窗口：lead gen 30 天，高考量型購買 90 天

### Meta（Facebook/Instagram）Pixel

1. 透過 GTM 安裝 Meta Pixel 基礎碼
2. 標準事件：`PageView`、`Lead`、`CompleteRegistration`、`Purchase`
3. 強烈建議搭配 Conversions API（CAPI）— 客戶端 pixel 因廣告阻擋器與 iOS 會流失約 30% 轉換
4. CAPI 需要 server-side 實作（看 Meta 文件或 GTM server-side）


## 跨平台追蹤

### UTM 策略

UTM（Urchin Tracking Module，網址參數，用於追蹤流量來源）：嚴格執行 UTM 慣例，否則通路資料會變成噪音。

| 參數 | 慣例 | 範例 |
|-----------|-----------|---------|
| `utm_source` | 平台名稱（小寫） | `google`、`linkedin`、`newsletter` |
| `utm_medium` | 流量類型 | `cpc`、`email`、`social`、`organic` |
| `utm_campaign` | Campaign ID 或名稱 | `q1-trial-push`、`brand-awareness` |
| `utm_content` | 廣告／素材變體 | `hero-cta-blue`、`text-link` |
| `utm_term` | 付費關鍵字 | `saas-analytics` |

**規則：** 絕對不要在自然或直接流量上加 UTM。UTM 會覆蓋 GA4 自動的 source/medium 歸因。

### 歸因窗口

| 平台 | 預設窗口 | 建議 |
|---------|---------------|---------------------|
| GA4 | 30 天 | 依銷售週期 30-90 天 |
| Google Ads | 30 天 | 30 天（試用）、90 天（企業） |
| Meta | 7 天點擊、1 天瀏覽 | 只用 7 天點擊 |
| LinkedIn | 30 天 | 30 天 |

### 跨網域追蹤

若漏斗橫跨網域（例：`acme.com` → `app.acme.com`）：

1. GA4 → Admin → Data Streams → Configure tag settings → List unwanted referrals → 加兩個網域
2. GTM → GA4 Configuration tag → Cross-domain measurement → 加兩個網域
3. 測試：造訪網域 A、點連結到網域 B、在 GA4 DebugView 檢查 — session 不應重新開始


## 資料品質

### 去重

**事件觸發兩次？** 常見原因：
- GTM tag + 寫死的 gtag 同時觸發
- Enhanced Measurement + 自訂 GTM tag 追同一事件
- SPA router 每次路由切換都觸發 pageview，而 GTM 的 page view tag 也觸發

修正：在 GTM Preview 稽核雙重觸發。用 DevTools Network tab 檢查是否有重複請求。

### Bot 過濾

GA4 自動過濾已知 bot。內部流量：
1. GA4 → Admin → Data Filters → Internal Traffic
2. 加入辦公室 IP 與開發者 IP
3. 啟用過濾器（預設為測試模式 — 要啟用）

### 同意管理影響

在 GDPR/ePrivacy 下，分析可能需要同意。要規劃：

| Consent Mode 設定 | 影響 |
|---------------------|--------|
| **無 consent mode** | 拒絕 cookie 的訪客 → 零資料 |
| **Basic consent mode** | 拒絕者 → 零資料 |
| **Advanced consent mode** | 拒絕者 → 模型估算資料（GA4 用同意的使用者推估） |

**建議：** 透過 GTM 實作 Advanced Consent Mode。需要整合 CMP（Cookiebot、OneTrust、Usercentrics 等）。

地區預期同意率：EU 60-75%、US 85-95%。


## Proactive Triggers（主動觸發）

不等被問就主動提出：

- **事件在每個頁面載入時都觸發** → Trigger 設錯的症狀。標記：資料會被重複灌水。
- **沒有傳 user_id** → 無法和 CRM 連起來或分析 cohort。標記待修。
- **GA4 與 Ads 的轉換對不上** → 歸因窗口不一致或 pixel 重複。標記要稽核。
- **EU 市場沒設 consent mode** → 有法律風險且資料嚴重低估。立即標記。
- **所有頁面顯示為 "/(not set)" 或通用路徑** → SPA routing 沒處理。GA4 記錯頁面。
- **付費 campaign 的 UTM source 顯示為 "direct"** → UTM 缺失或被吃掉。流量歸因壞了。


## Output Artifacts（產出物）

| 使用者要什麼 | Claude 給什麼 |
|--------------------|-----------|
| 「建立追蹤計畫」 | 事件分類表（事件 + 參數 + trigger）、GA4 設定清單、GTM container 結構 |
| 「稽核我的追蹤」 | 對照標準轉換漏斗的缺口分析、資料品質計分（0-100）、優先修正清單 |
| 「設定 GTM」 | 每個事件的 tag/trigger/variable 設定、container 建置清單 |
| 「除錯缺失事件」 | 用 GTM Preview + GA4 DebugView + Network tab 的結構化除錯步驟 |
| 「設定轉換追蹤」 | GA4 + Google Ads + Meta 的轉換行為設定 |
| 「產出追蹤計畫」 | 事件分類表、GA4 設定清單、GTM container 結構 |


## Communication（溝通原則）

所有輸出遵守結構化溝通標準：
- **先結論** — 在談方法論之前先說什麼壞了或什麼要建立
- **What + Why + How** — 每個發現都含這三項
- **行動有負責人與期限** — 不要含糊的「考慮實作」
- **信心標註** — 🟢 已驗證 / 🟡 估算 / 🔴 假設


## Do's and Don'ts

### Do
- 先建好追蹤再開始優化——沒有數據的優化是猜測
- Event 命名用 `noun_verb` snake_case 格式（如 `form_submit`、`plan_selected`）
- 台灣市場設定：貨幣 TWD、時區 Asia/Taipei、語言 zh-TW

### Don't
- 不要 Enhanced Measurement 和 GTM 同時追蹤同一事件——會造成數據重複
- 不要在 organic 流量加 UTM——UTM 會覆蓋 GA4 自動的 source/medium 歸因
- 不要沒有 consent mode 就在歐洲市場上線——有法律風險且數據會嚴重低估
- 不要把所有事件都標為 conversion——每個 property 最多 30 個，精挑細選

## 快速參考

### GA4 + GTM 從零建置
1. GA4 建立 property → 新增 web data stream → 開啟 Enhanced Measurement
2. GTM 建立 container → 加入 GA4 Configuration tag（All Pages trigger）
3. 為每個自訂事件建立 Data Layer Push + GTM Event Tag + GA4 Event
4. 在 GA4 標記重要事件為 conversion（signup_completed、checkout_completed 等）

### 追蹤除錯流程
1. 開啟 GTM Preview Mode 確認 tag 是否 fire
2. 開啟 GA4 DebugView 確認事件是否到達
3. 檢查 DevTools Network tab 確認沒有重複 hit

### 跨平台轉換追蹤
1. Google Ads：從 GA4 匯入 conversion（單一數據來源）
2. Meta Pixel：透過 GTM 安裝 + 搭配 Conversions API（CAPI）提升準確度
3. 所有付費流量統一 UTM 命名規範

## Related Skills

- 見本檔案上方的 campaign-analytics 區段 — 用於分析行銷成效與通路 ROI。不適合用於實作 — 本區段負責追蹤設定。本區段只涵蓋設定；儀表板與報表請見 campaign-analytics。
