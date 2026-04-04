# 訂單管理專業指南

## 觸發情境

「下單」「訂單」「出貨」「收款」「品檢」「客戶要訂」
「查訂單」「訂單進度」「還沒收到貨」「退貨」

---

## 一、訂單生命週期

```
pending → confirmed → (QC passed) → shipped → delivered → paid
  │                      │
  └→ cancelled           └→ QC failed → 通知主管
```

DB 支援的訂單狀態：`pending` | `confirmed` | `shipped` | `delivered` | `paid` | `cancelled`

### 使用的 MCP Tools

| Tool | 功能 | 關鍵行為 |
|------|------|---------|
| `create_order` | 建立訂單 | 需要 customer_id + items_json |
| `get_order` | 查看訂單明細 | 含品項、狀態、物流資訊 |
| `list_orders` | 列出訂單 | 可按 customer_id 或 status 篩選 |
| `update_order` | 更新狀態/物流/備註 | 支援 driver, estimated_delivery |
| `qc_order` | 品質檢查 | result: passed/failed/partial |
| `fulfill_order` | 確認出貨 | ⚠️ **自動扣庫存 + 自動建立應收帳款** |
| `record_payment` | 記錄付款 | 用 transaction_id 銷帳，支援部分付款 |

---

## 一a、中斷恢復（Context Loss Recovery）

如果 session 中斷或 context 壓縮後，用以下方式快速恢復訂單處理進度：

### 恢復步驟

1. `get_context_summary(scope='full')` — 看「進行中訂單」區塊，每筆訂單旁有下一步提示
2. 如需詳情 → `get_order(order_id)` — 取得完整狀態

### 狀態 → 下一步對照表

| status | qc_status | 下一步 |
|--------|-----------|--------|
| pending | * | `update_order(order_id=X, status='confirmed')` 確認訂單 |
| confirmed | pending | `qc_order(order_id=X, result='passed')` 品檢 |
| confirmed | passed | `fulfill_order(order_id=X)` 出貨 |
| confirmed | failed | 通知主管，處理品質問題後重新 QC |
| confirmed | partial | 問主管是否部分出貨 |
| shipped | * | 等待客戶確認送達 → `update_order(order_id=X, status='delivered')` |
| delivered | * | 收款 → `record_payment(transaction_id=Y, amount=Z)` |
| paid | * | ✅ 完成，無需動作 |

### 找到對應的應收帳款

出貨後需要收款時：`list_transactions(type='income', related_order_id=X)` 或 `check_overdue()`

### Tool 回傳值指引

每個訂單操作的 tool（`create_order`、`qc_order`、`fulfill_order`、`record_payment`）回傳值都包含 `👉 下一步` 提示，跟著做即可。不需要背流程。

---

## 二、建立訂單

### 來源

- 客戶透過 LINE 下單（最常見）
- 老闆口述
- 業務建單
- 電話/現場訂單

### 流程

1. **辨識客戶**
   - `find_customer(名稱或關鍵字)` 找到客戶
   - 找不到 → 問：「這是新客戶嗎？」→ 是的話先 `add_customer` 建檔

2. **確認品項和數量**
   - 從對話中提取品項名、SKU、數量
   - 逐項 `check_stock(sku)` 確認庫存
   - 庫存不足 → 回報：「{品名} 目前庫存 {X} 個，訂單需要 {Y} 個，要繼續嗎？」

3. **計算價格**
   - 查客戶 `discount_rate`（`find_customer` 回傳）
   - 查商品 `sell_price`（`check_stock` 回傳）
   - 實際價 = sell_price × (1 - discount_rate)
   - 特殊報價 → `query_knowledge(question='客戶名 商品名 特價')` 查例外
   - items_json 的 `price` 用計算後的實際價

4. **建立訂單**
   ```
   create_order(
     customer_id=客戶ID,
     items_json='[{"sku":"A200","name":"品名","qty":10,"price":150}]',
     notes='備註（如有）',
     created_by=建單人
   )
   ```

5. **審核門檻檢查**
   - 計算訂單總金額
   - 查門檻（`company` 表的 `approval_threshold`）
   - 超過門檻 → `create_approval(type='purchase', summary='訂單 #{id} 金額 NT${total}')` → 等主管核准
   - 門檻內 → 直接進入確認

6. **通知**
   - LINE 通知客戶：「訂單 #{id} 已建立，{品項明細}，總金額 NT${total}」
   - LINE 通知相關員工（倉管/業務）：「新訂單 #{id}，請準備備貨」

---

## 二a、付款條件判斷

建單後查客戶的 `payment_terms`（`find_customer` 回傳）：

| payment_terms | 流程 |
|--------------|------|
| **prepaid** | 通知客戶匯款 → 等 `record_transaction(type='income', related_order_id=訂單ID)` → 付清後才 → confirmed → QC → fulfill |
| **deposit_30** | 通知客戶付 30% 訂金 → `record_transaction(amount=總額×0.3)` → confirmed → QC → fulfill → 出貨後收尾款 |
| **net30 / net60** | 直接 → confirmed → QC → fulfill_order（自動建應收帳款，due_date = 出貨日+30/60天） |
| **cod** | 直接 → QC → fulfill → 送達時收款 |

⚠️ `fulfill_order` 有內建付款條件檢查：
- prepaid 客戶未付全額 → 拒絕出貨
- deposit_30 客戶未付 30% → 拒絕出貨
- net30/net60 → 自動帶 due_date

---

## 三、訂單確認

主管或業務確認後：

1. `update_order(order_id, status='confirmed')`
2. LINE 通知客戶：「訂單 #{id} 已確認，預計 {日期} 出貨」
3. 如果需要備貨時間較長 → 建立任務：
   `create_task(title='備貨 訂單#{id}', assignee=倉管, due_date=出貨日前一天, category='delivery')`

---

## 四、品質檢查（出貨前必須步驟）

⚠️ **出貨前必須通過 QC，不可跳過。**

1. 員工完成備貨後回報
2. 執行品檢：
   ```
   qc_order(
     order_id=訂單ID,
     result='passed',  // passed | failed | partial
     notes='檢查備註',
     checked_by=檢查人
   )
   ```

3. 根據結果處理：

| QC 結果 | 處理 |
|---------|------|
| `passed` | 進入出貨流程（第五節） |
| `failed` | 通知主管 + 記錄不良原因 + 不出貨 |
| `partial` | 列出合格/不合格品項 → 問主管：「部分品項不合格，是否部分出貨？」 |

---

## 五、出貨

### 前置條件
- QC result = `passed`（或主管核准的 `partial`）

### 流程

1. **出貨確認**
   ```
   fulfill_order(order_id)
   ```
   ⚠️ 這個操作會**自動執行**：
   - 扣減對應品項的庫存
   - 在 transactions 表建立應收帳款紀錄

   **不要再手動 `update_stock` 或 `record_transaction`**，否則會重複。

2. **更新物流資訊**
   ```
   update_order(
     order_id,
     status='shipped',
     driver='司機名或物流單號',
     estimated_delivery='預計到貨日',
     notes='物流備註'
   )
   ```

3. **通知**
   - LINE 通知客戶：「訂單 #{id} 已出貨，預計 {日期} 到達。物流：{driver}」
   - 如果有出貨單/簽收單 → `add_attachment(target_type='order', target_id=訂單ID, file_path='data/media/orders/{orderId}/出貨單.jpg', description='出貨單')`

4. **庫存檢查**
   - 出貨後自動扣庫存，檢查是否觸發 `low_stock_alerts()`
   - 低於安全庫存 → 通知相關人員

---

## 六、到貨確認

客戶確認收到貨時：

1. `update_order(order_id, status='delivered')`
2. `log_interaction(actor='AI助理', action='delivery', target_type='order', target_id=訂單ID, detail='訂單 #{id} 已送達')`
3. 排程售後關懷（7 天後，參考 crm-ops）：
   - 「{客戶} 您好，上次的訂單使用還順利嗎？有任何問題歡迎告訴我們。」

---

## 七、收款

### 檢查逾期帳款

`check_overdue()` — 自動回傳所有到期日已過且未全額付清的帳目。

### 收款流程

1. 客戶付款後（匯款通知、LINE 傳截圖等）
2. 查詢對應帳目：`list_orders(customer_id=客戶ID, status='delivered')` 或 `check_overdue()`
3. 記錄收款：
   ```
   record_payment(
     transaction_id=應收帳款的交易ID,
     amount=收到的金額,
     notes='匯款/現金/刷卡'
   )
   ```
4. 支援**部分付款**：可多次 `record_payment`，每次記錄實收金額
5. 全額付清 → `update_order(order_id, status='paid')`
6. LINE 通知客戶：「已收到款項 NT${金額}，感謝！」

### 催收邏輯

催收規則統一由 **accounting-ops 第六節**定義（帳齡分類、催收動作、自動通知）。
order-ops 只負責收款操作（`record_payment`），不重複定義催收時機。

---

## 八、取消 / 退貨

### 取消訂單

| 階段 | 處理方式 |
|------|---------|
| pending/confirmed（未出貨） | 直接 `update_order(order_id, status='cancelled', notes=取消原因)` |
| shipped（已出貨未到貨） | 通知物流攔截 → 攔截成功才取消 |
| delivered（已到貨） | 走退貨流程 |

### 退貨流程

1. 記錄退貨原因：`update_order(order_id, notes='退貨原因：{原因}')`
2. 收到退回商品後：
   - 品質OK → `update_stock(sku, +數量, '退貨入庫')` 回補庫存
   - 品質不OK → 記為損耗，不回補
3. 退款處理：
   - 尚未收款 → `update_order(status='cancelled')`
   - 已收款 → `record_transaction(type='expense', category='refund', amount=退款金額, description='退貨退款 訂單#{id}')` → 安排退款

---

## 九、訂單查詢

| 需求 | 操作 |
|------|------|
| 查單筆訂單 | `get_order(order_id)` |
| 查某客戶的訂單 | `list_orders(customer_id=客戶ID)` |
| 查待出貨的訂單 | `list_orders(status='confirmed')` |
| 查已出貨未收款 | `list_orders(status='delivered')` |
| 查逾期帳款 | `check_overdue()` |

---

## 十、跨模組交互

| 步驟 | 交互模組 | Tool / 說明 |
|------|---------|------------|
| 建單 | crm-ops | `find_customer` 查客戶 → `add_customer` 建新客戶 |
| 建單 | inventory-ops | `check_stock` 確認庫存 |
| QC | — | `qc_order` 獨立操作 |
| 出貨 | inventory-ops | `fulfill_order` **自動扣庫存** |
| 出貨 | accounting-ops | `fulfill_order` **自動建應收帳款** |
| 收款 | accounting-ops | `record_payment` 銷帳 |
| 催收 | accounting-ops | `check_overdue` + 帳齡催收 |
| 通知 | line-comms | 各階段 `reply` 通知客戶/員工 |
| 附件 | — | `add_attachment` 保存出貨單/簽收單 |
| 售後 | crm-ops | `log_interaction` 記錄 + 售後關懷 |

---

## 十一、注意事項

- **fulfill_order 會自動扣庫存**，不要另外手動 `update_stock`
- **出貨前必須過 QC**，不可跳過
- **大額訂單需 HITL 審核**（`create_approval`）
- 所有訂單操作建議 `log_interaction` 記錄
- 退貨入庫**需要手動** `update_stock` 回補（fulfill_order 的反向操作不自動）
- 客戶合約、PO 等文件用 `add_attachment(target_type='order')` 保存
- 訂單附件統一存放在 `data/media/orders/{orderId}/` 目錄下
