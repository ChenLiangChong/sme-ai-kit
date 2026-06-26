# 客戶管理專業指南

## 觸發情境

「客戶 XXX 的資料」「哪些客戶最近沒來」「VIP 名單」「新增客戶」
「發行銷訊息」「客戶分群」「流失預警」「客訴處理」

---

## 一、客戶生命週期

每個客戶都在以下階段之一，不同階段用不同策略：

| 階段 | 定義 | 策略 |
|------|------|------|
| 潛在客戶 (Prospect) | 還沒買過 | 提供資訊、建立信任 |
| 新客 (New) | 首次購買 30 天內 | 歡迎、確認滿意度、引導回購 |
| 活躍客 (Active) | 近 60 天有購買 | 維持關係、推薦新品 |
| 沉睡客 (Dormant) | 60-180 天沒購買 | 挽回觸及、特殊優惠 |
| 流失客 (Lost) | 超過 180 天沒購買 | 低成本觸及或放棄 |
| 忠實客 (Loyal) | 累計購買 5 次以上 | VIP 待遇、推薦獎勵 |

### 階段判讀（agent 自己算，系統不自動分類）

CRM 工具只儲存與回傳既有欄位（`pipeline_stage`、`last_purchase_date`、`total_purchases` 等）、**沒有 lifecycle 自動分類器**。查詢客戶（`get_customer` / `find_customer`）時由 **agent 依這些欄位手動判讀**所在階段、在回覆中標注；這只是回覆時的呈現，不會回寫客戶紀錄。要把判讀結果固化到客戶上，需 agent 明確 `update_customer(customer_id=..., pipeline_stage=...)`。

---

## 二、客戶資料管理

### 新增客戶

1. `add_customer(name, type="customer", phone="", email="", line_user_id="", tags="", notes="", discount_rate=0.0, payment_terms="net30", primary_business_unit="")`
   - `type` **只接受 customer / supplier / distributor** 三種；類型在新增時定、之後**不能改**。
2. 如果知道 LINE user_id → 同時綁定（傳 `line_user_id`）
3. 建議至少取得：姓名 + 電話或 LINE

### 更新客戶

- `update_customer(customer_id, name="", phone="", email="", line_user_id="__SKIP__", tags="", notes="", pipeline_stage="", total_purchases=-1, discount_rate=-1.0, payment_terms="", primary_business_unit="__SKIP__")`
- 可更新：基本資料、標籤、累計消費金額、折扣率 / 付款條件、業務（銷售）階段。
- **沒有 `type` 參數**：客戶類型只有 customer / supplier / distributor、且只能在 `add_customer` 時定，`update_customer` 改不了。
- 「潛在 / 跟進中 / 已成交」這類**銷售階段**用 `pipeline_stage` 欄位描述（**不是** type）：值為 `none | prospect | contacted | negotiating | closed_won | closed_lost`。例：`update_customer(customer_id=<客戶 customer_id>, pipeline_stage='negotiating')`（`customer_id` 必填）。

### 查詢

- 用名字/電話/標籤 → `find_customer(query)`
- 列出所有 VIP → `find_customer('vip')`

### 定價等級與付款條件

每個客戶有 `discount_rate`（折扣率）和 `payment_terms`（付款條件）。

| 欄位 | 說明 | 範例 |
|------|------|------|
| discount_rate | 折扣率（0=原價, 0.15=85折） | 8折經銷商: 0.2 |
| payment_terms | 付款條件 | prepaid / cod / deposit_30 / net30 / net60 |

操作：
- 新增時設定：`add_customer(name='<客戶名>', type='distributor', discount_rate=0.15, payment_terms='net30')`（`name` 必填、其餘可省）
- 修改：`update_customer(customer_id=<客戶 customer_id>, discount_rate=0.2, payment_terms='net60')`（`customer_id` 必填）
- 特殊單品報價：`store_fact(category='pricing', title='A經銷商 SKU-A001 特價', content='NT$350', source_quote='<老闆／業務確認的原話>')`（`category`/`title`/`content` 必填；`source_type` 預設 `explicit` 須附 `source_quote`，無原話則改 `source_type='inferred'`——見 CLAUDE.md〈反捏造原則〉）

### 資料衛生

系統**沒有每月自動檢查 / 巡檢 job**。下列由 **agent 在被要求或啟動流程判斷時手動巡檢**（撈客戶清單後逐項比對），需要追蹤可建 task 提醒人工 follow-up：
- 重複客戶（同電話或同名）→ 建議合併
- 無聯繫方式的客戶 → 標記為不完整
- tags 為空的客戶 → 建議補上標籤

---

## 三、RFM 分群分析

### 用現有欄位的簡化版

| 維度 | 衡量 | 資料來源 |
|------|------|---------|
| R (Recency) | 多久沒來 | `last_purchase_date` 距今天數 |
| F (Frequency) | 來多少次 | `list_orders(customer_id=<客戶 customer_id>)` 的訂單筆數（需啟用 order-ops 模組）。若未啟用，暫用 total_purchases / 平均客單價 估算 |
| M (Monetary) | 花多少錢 | `total_purchases` |

> Phase 1 以 R + M 為主要維度。F 在 order-ops 模組完善後可加入進階分群。

### 分群邏輯

| 分群 | R 條件 | M 條件 | 建議動作 |
|------|--------|--------|---------|
| 冠軍客戶 | 近 30 天有消費 | 總額前 20% | 維護、專屬服務、推薦計畫 |
| 忠實客戶 | 近 60 天有消費 | 總額中上 | 感謝回饋、新品預覽 |
| 有潛力 | 近 30 天有消費 | 總額一般 | 提升客單價、交叉銷售 |
| 需要關注 | 60-120 天沒消費 | 總額前 20% | 立即挽回！發關懷訊息 |
| 沉睡中 | 120-180 天沒消費 | 任何 | 喚醒優惠、問卷調查 |
| 已流失 | 超過 180 天 | 任何 | 低成本觸及或放棄 |

### 執行方式

當使用者問「客戶分群」「RFM」「誰最有價值」：
1. 從 DB 撈所有客戶的 last_purchase_date 和 total_purchases
2. 按上表分群
3. 每群列出人數和代表客戶
4. 附帶建議動作

---

## 四、客戶觸及策略

### 頻率限制

| 客群 | 最高頻率 | 管道 |
|------|---------|------|
| 冠軍/忠實 | 每月 2 次 | LINE + 專屬 |
| 有潛力 | 每月 1 次 | LINE |
| 需要關注 | 每 2 週 1 次（限時） | LINE + 電話 |
| 沉睡 | 每月 1 次 | LINE |
| 已流失 | 每季 1 次 | LINE |

### 觸及內容建議

| 場景 | 內容 | 範本 |
|------|------|------|
| 新品上市 | 「嗨 {name}，我們有新品 {product}，以你喜歡的 {category} 風格，覺得你會有興趣！」 | 套 brand-voice |
| 節日問候 | 簡短祝福 + 不要硬推銷 | 套 brand-voice |
| 沉睡喚醒 | 「好久不見！最近有新的 {category}，想來看看嗎？」 | 套 brand-voice |
| 生日 | 專屬優惠或祝福 | 套 brand-voice |
| 售後關懷 | 購買後 7 天：「{product} 用得還好嗎？有任何問題隨時找我」 | 直接發 |

### 行銷訊息審核流程

1. 選定目標客群
2. 草擬訊息 → 參考 brand-voice 模組
3. **對外行銷/廣播須送審**（`type` / `summary` 為必填）：`create_approval(type='announcement', summary='<訊息摘要>', detail='{"resume_action": "manual_broadcast", "resume_params": {"audience": "<客群描述>", "channel": "line", "text": "<完整訊息內容>"}, "note": "核准後人工執行：先撈客群 LINE user_id 清單、逐一 reply、最後 log_interaction（非單一 tool call）", "then": "發送後逐一 log_interaction"}')`
   - 行銷廣播走 `manual_broadcast`、是 **B 類 manual approval**（resume_action 開頭 `manual_`、resolve 後人工多步驟、不適用 resume_params 一字不差；別寫死「需 admin 核准」——見 CLAUDE.md〈HITL 審核〉B 類）。一般客服 / 交易性回覆依本檔對應流程、非全部送審。
   - **建審核當下即上報簽核人**（escalation `approval_pending` 觸發）：不必自己撈老闆 user_id 去通知，系統會上報。
4. 主管核准後**人工執行**：逐一 `reply` 客群 + `log_interaction`。這步要在**有對外 reply 能力的層**執行（floored 業務層未必能 push 到客群、跨層分工見 line-comms 第六節〈執行模型〉）。
5. 發送的事實靠每筆 `log_interaction` 留底。CRM **沒有「最後聯繫日」欄位、也沒有自動更新它的排程**；要追蹤觸及頻率改翻 `log_interaction` 紀錄、或 agent 自行於下次操作判讀，不要寫成系統會回寫聯繫日。

---

## 五、客訴處理流程

當收到客訴（LINE 或口述）：

### 處理步驟

1. **立即回覆**（5 分鐘內）：「收到您的反映，我們非常重視，正在處理中。」
2. **記錄**：`log_interaction(actor='AI助理', action='complaint', target_type='customer', target_id=<客戶 customer_id>, detail='<客訴內容原文>')`（`actor`/`action` 為必填）
3. **分級**：

| 嚴重度 | 定義 | 處理時限 | 通知 |
|--------|------|---------|------|
| 高 | 安全疑慮、法律風險、大額退款 | 2 小時 | 老闆 + 負責人 |
| 中 | 品質不佳、缺貨、延遲 | 24 小時 | 負責人 |
| 低 | 小瑕疵、誤解、建議 | 48 小時 | 負責人 |

> **「通知老闆」怎麼通知**：不要這層自己撈老闆 user_id 直接 `reply`（floored 業務層未必撈得到、也未必 push 得到老闆）。走 escalation 機制 / 由全權限層處理，與其他上報走一致路徑——跨層通知與簽核見 line-comms 第六節〈執行模型〉。建審核（如大額退款 / 超權限賠償）時系統會自動上報簽核人。

4. **查詢相關規則**：`query_knowledge(question='<問題描述>', category='customer_service')`
5. **依規則處理或建審核**
6. **回覆客戶處理結果**
7. **追蹤**：系統不會自動排程回訪。要事後確認客戶是否滿意，請 `create_task`（標題如「客訴 #X 後續滿意度確認」、可在 description 註記建議幾天後做），交由人工 follow-up——**沒有 N 天後自動追蹤的 scheduler**。

### 客訴禁忌

- 不要辯解或推責
- 不要承諾做不到的事
- 不要洩漏其他客戶資訊
- 超出權限的賠償 → 一律建審核

---

## 六、B2B 經銷商/供應商管理

### 與一般客戶的差異

| 面向 | 一般客戶 | 經銷商/供應商 |
|------|---------|-------------|
| 聯繫頻率 | 每月 1-2 次 | 每週或按需 |
| 溝通語氣 | 親切 | 專業正式 |
| 關注指標 | 回購率、客單價 | 採購量、準時付款、配合度 |
| 特殊處理 | 退貨/客訴 | 帳期、批量折扣、獨家條款 |

### 經銷商健康評分（簡化版）

| 維度 | 權重 | 指標 |
|------|------|------|
| 採購量 | 40% | 月採購金額 vs 目標 |
| 付款紀律 | 30% | 平均付款天數、逾期次數 |
| 配合度 | 20% | 回覆速度、配合促銷活動 |
| 成長性 | 10% | 採購量趨勢（上升/持平/下降） |

紅黃綠分級：
- 綠（75+ 分）：健康
- 黃（50-74 分）：需關注
- 紅（50 分以下）：需介入

---

## 七、客戶滿意度追蹤

### 簡化版 NPS

在關鍵時刻問一個問題：
「從 0 到 10，你有多大可能推薦我們給朋友？」

| 分數 | 分類 | 佔比 |
|------|------|------|
| 9-10 | 推薦者 | 越高越好 |
| 7-8 | 被動者 | 不好不壞 |
| 0-6 | 批評者 | 越低越危險 |

```
NPS = 推薦者% - 批評者%
```

| NPS | 評價 |
|-----|------|
| > 50 | 優秀 |
| 30-50 | 良好 |
| 0-30 | 需改善 |
| < 0 | 嚴重問題 |

### 何時問

下列是建議時機、**不是系統自動排程**（CRM 沒有 NPS scheduler、也沒有觸發送問卷的機制）。要落實得靠人工 follow-up，可 `create_task` 排提醒：
- 購買後約 7 天（產品滿意度）
- 客訴處理後約 3 天（服務滿意度）
- 每季一次（整體滿意度）

---

## 八、KPI 指標

| 指標 | 計算 | 健康值 |
|------|------|--------|
| 客戶留存率 | 期末有購買客戶 / 期初客戶 | > 70% |
| 回購率 | 重複購買客戶 / 總客戶 | > 30% |
| 平均客單價 | 總收入 / 總交易次數 | 持續上升 |
| 客戶獲取成本 | 行銷費用 / 新客數 | 越低越好 |
| 客訴解決率 | 已解決客訴 / 總客訴 | > 90% |

---

## 九、客戶附件

客戶相關的重要文件（合約、名片、報價單等）：
`add_attachment(target_type='customer', target_id=<客戶 customer_id>, file_path='data/media/customers/<customer_id>/<檔名>', description='<描述>')`（`target_type`/`target_id`/`file_path` 為必填）

---

## Do's and Don'ts

### Do
- 客戶資料異動都 `log_interaction`
- 行銷訊息先過 brand-voice 再發
- 對外行銷/群發前 `create_approval(type='announcement', summary='<訊息摘要>', detail='{"resume_action": "manual_broadcast", "resume_params": {"audience": "<客群描述>", "channel": "line", "text": "<完整訊息內容>"}, "note": "核准後人工執行：先撈客群 LINE user_id 清單、逐一 reply、最後 log_interaction（非單一 tool call）", "then": "發送後逐一 log_interaction"}')` 送審（`type`/`summary` 必填；B 類 manual；建審核即上報簽核人；核准後人工執行落在有對外 reply 能力的層——見第四節）
- 遵守頻率限制：同一客戶每月推送不超過 2 次
- 客訴立即回覆（5 分鐘內），先同理再處理

### Don't
- 不要硬推銷（節日問候不夾帶促銷）
- 不要洩漏其他客戶的資訊
- 不要承諾做不到的賠償（超出權限 → `create_approval`）
- 不要辯解或推責（客訴處理）
- 不要刪除客訴紀錄（永久保留）

## 快速參考

### 新增客戶
1. `add_customer(name='好好生活', phone='02-1234-5678', type='customer', tags='vip')`
2. `log_interaction(actor='AI助理', action='customer_created', detail='新增客戶 好好生活')`

### 查客戶 + RFM 分群
1. `find_customer(query='好好生活')` — 取得 customer_id、last_purchase_date、total_purchases
2. 根據 R（距今天數）+ F（`list_orders` 計算）+ M（total_purchases）判斷分群

### 客訴處理
1. `reply(channel_id='<收到客訴訊息的 channel_id>', chat_id='<客戶 chat_id>', text='收到您的反映，我們非常重視，正在處理中。')`（回同一個收到客訴的 OA、不要寫死 `default`、見 line-comms 通知頻道選擇）
2. `log_interaction(actor='AI助理', action='complaint', target_type='customer', target_id=<客戶 customer_id>, detail='<客訴內容原文>')`（`actor`/`action` 為必填）
3. `query_knowledge(question='<問題描述>', category='customer_service')` — 查處理規則
4. 退款：直接 `record_transaction(type='expense', amount=<退款金額，取原訂單/原收款 transaction 的實付額、勿自行推算>, category='refund', description='退款給<客戶名>（原訂單 #<order_id>）')`——`type`/`amount`/`category` 為必填；超門檻它會用完整 `resume_params` 自動建審核並上報、**勿自行 `create_approval`**；記帳完成後 LINE 通知客戶
   - **退款記帳受 floor `financial_visibility` 限制**：`general` / `external` 業務層**沒有 `record_transaction`**、記不了帳。此時不要自己想辦法繞，把退款交給**有財務工具的層**（會計層 / 全權限層）執行。跨層誰執行、核准後一條龍見 line-comms 第六節〈執行模型〉。

## 中斷恢復

如果 context 被壓縮：
1. `get_context_summary(scope='full')` — 查看客戶數、進行中訂單
2. `find_customer(query='<正在處理的客戶名>')` — 恢復客戶資訊和 pipeline_stage
3. `list_orders(customer_id=<客戶 customer_id>)` — 查看該客戶的訂單狀態

---

## 十、注意事項

- 群發行銷一律走 HITL 審核（`create_approval` B 類 manual broadcast、見第四節）；建審核當下即上報簽核人。
  - **流程上**核准者應為 admin / 主管；但**系統未對「誰能 resolve」全面 enforce**——`resolve_approval` 在非全權限（floored）層才要求 verified manager 以上身份，operator / 全權限層的脈絡不強制 admin。真正擋越權看不該看的是 **floor gate**（HR / 財務工具在 floored 層被物理移除）、不是這條注意事項。
- 單筆查詢不需要核准
- 客戶資料修改建議 `log_interaction` 留痕（非系統強制 enforce）
- 所有行銷訊息先過 brand-voice 模組
- 同一客戶每月推送不超過 2 次
- 客訴紀錄永久保留，不可刪除
