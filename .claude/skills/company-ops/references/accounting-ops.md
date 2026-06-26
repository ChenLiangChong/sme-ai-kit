# 帳務管理專業指南

## 觸發情境

「記一筆支出」「這個月花了多少」「這張收據」「月報」
「現金流」「應收帳款」「要報稅了」「勞健保」

---

## 一、記帳流程

### 基本記帳

從對話中提取：類型（收入/支出）、金額、分類、描述、日期

1. **一律直接 `record_transaction(...)`（不帶 `approved_id`）**——不要自己預判門檻、**不要自己 `create_approval`**。門檻分流由 record_transaction 內部處理：
   - **門檻內** → 直接記帳、回「帳目 #N」。
   - **超門檻** → 系統自動用完整 `resume_params` 建審核 + 上報簽核人、回「已建審核 #N」（detail 由系統自建、agent 不手寫，確保核准後 gate 一字不差比對得過）。
2. **核准後執行**：簽核人核准後（LINE 回「核准 #N」或全權限層 `resolve_approval`），由**全權限層 session** 從 approval 取鎖定的 `resume_params` 呼叫 `record_transaction(approved_id=N, ...)` 完成記帳（見 `line-comms.md` 執行模型）。
3. 門檻設定：`update_company(approval_threshold=金額)`。
4. 回報：「已記錄 {類型} NT${金額} [{分類}]」。

**注意** 這裡的重點轉變：**絕不要自己 `create_approval` 來記帳**。舊流程要求「主動先建審核」會讓 agent 手寫不完整的 `resume_params`（少了 gate 要的欄位）而被擋——現在一律交給 `record_transaction` 自建、agent 不碰 detail。

> 詳細的 HITL gate 行為（`resume_params` 一字不差驗證、`consumed_at` 單次消費、過期保護、ERROR 判讀）統一寫在 **CLAUDE.md HITL 章節**。本檔只列「記帳場景什麼時候要走 HITL」。
> 重點：核准後**必須**從 approval 取出原始 `resume_params` 再呼叫 `record_transaction(approved_id=N)`，不要從對話脈絡重新推導金額或事業體，否則會被 gate 擋下。

缺少資訊時：
- 沒說金額 → 必問
- 沒說分類 → 根據描述判斷，告知：「我歸類為 {分類}，OK 嗎？」
- 沒說日期 → 預設今天

### 收據照片處理

員工傳 [圖片] → Read tool 看圖 → 辨識金額/商家/日期 → 確認 → 記帳
看不清楚的欄位直接問，不要猜。

收據照片從 LINE 進來時存在 `data/media/line/images/`，歸檔後用 add_attachment 關聯到對應訂單。

記帳完成後，如果有關聯訂單，保存收據附件：
`add_attachment(target_type='order', target_id=訂單ID, file_path=圖片路徑, description='收據', uploaded_by=員工名)`
如果沒有關聯訂單，在 `record_transaction` 的 description 中記錄圖片路徑。

---

## 二、科目分類體系

### 收入科目

| 科目代碼 | 名稱 | 常見情境 |
|---------|------|---------|
| `sales_revenue` | 銷售收入 | 「賣了一批貨」「客戶付款」 |
| `service_revenue` | 服務收入 | 「做完案子」「顧問費」 |
| `other_income` | 其他收入 | 「政府補助」「銀行利息」 |

### 支出科目

| 科目代碼 | 名稱 | 常見情境 |
|---------|------|---------|
| `rent` | 租金 | 「付房租」 |
| `salary` | 薪資 | 「發薪水」「年終」 |
| `supplies` | 辦公用品 | 「買影印紙」「碳粉匣」 |
| `inventory_purchase` | 進貨成本 | 「進了一批貨」 |
| `marketing` | 行銷費用 | 「FB 廣告」「印傳單」 |
| `meals` | 餐飲費 | 「請客戶吃飯」「買便當」 |
| `transportation` | 交通費 | 「加油」「搭高鐵」 |
| `utilities` | 水電瓦斯 | 「繳電費」 |
| `insurance` | 保險費 | 「產險續保」 |
| `repair` | 維修費 | 「修冷氣」 |
| `professional_fee` | 專業服務費 | 「記帳士費用」 |
| `tax_expense` | 稅務費用 | 「繳營業稅」 |
| `other_expense` | 其他支出 | 雜項 |

### 自動分類邏輯

| 關鍵字 | 對應科目 |
|--------|---------|
| 加油/停車/高鐵/計程車 | `transportation` |
| 吃飯/便當/聚餐/請客 | `meals` |
| 電費/水費/網路/電話 | `utilities` |
| 影印/紙/筆/文具 | `supplies` |
| 廣告/FB/Google/傳單 | `marketing` |
| 房租/租金 | `rent` |
| 薪水/工資/獎金 | `salary` |
| 進貨/補貨/叫貨 | `inventory_purchase` |

分類完一律告知讓使用者確認。

---

## 三、查帳與刪帳

> **floor caveat（第一次用到財務工具就提醒）**：本節 `monthly_summary` / `list_transactions` / `update_transaction` / `delete_transaction` / `check_overdue` 全屬財務工具，受 floor gate——floored 非財務 / 非全權限層**呼不到屬正常**，需交有該工具的層 / 全權限層執行（見 CLAUDE.md〈部門安全層（floor）與兩道牆〉、`line-comms.md` 第六節執行模型）。

- 「這個月花了多少」→ `monthly_summary()`
- 「最近的支出」→ `list_transactions(type='expense')`
- 修帳：`update_transaction(transaction_id=帳目ID, category='正確分類', business_unit='正確事業體')` — 第一參數是 `transaction_id`；修正分類、事業體、狀態等欄位（金額不可改，需刪除重建）
- 刪帳：`delete_transaction(transaction_id=帳目ID, reason='原因', actor_user_id='')` — 第一參數是 `transaction_id`，必須有原因。
  - **權限：需 `manager` 以上（已落實）**：floored session 的 `actor_user_id` 由系統取 verified `user_id`（agent 自填無效、非 manager / 未驗證身份擋下），audit log 記真實操作者名（不再 `actor='system'`）；operator（無 `SME_FLOOR`、空 actor）放行＝全權限路徑（設計如此、威脅模型只防 agent 路徑越權）。另有 floor gate 硬牆（財務工具在 floored 非財務層被物理移除）。
  - **刪帳會自動上報主管**（escalation `transaction_deleted` 觸發、系統蓋章通知，見 CLAUDE.md〈上報（escalation）機制〉）；屬不可逆動作。

---

## 四、月結作業

每月 1-5 日處理上月帳務。當使用者說「月結」「結帳」：

**步驟 1：收支核對**
- [ ] `monthly_summary()` 取得上月總覽
- [ ] 確認所有收據都已入帳
- [ ] 檢查有無重複記帳（同金額、同日期、同描述）

**步驟 2：分類檢查**
- [ ] 「其他支出」佔比是否 > 15%（表示分類不夠細）
- [ ] 大筆金額（> NT$10,000）分類是否正確

**步驟 3：產出月報**

```
{YYYY}年{MM}月 財務摘要

收入
  銷售收入    NT$ XXX,XXX
  服務收入    NT$  XX,XXX
  ─────────────────────
  收入合計    NT$ XXX,XXX

支出
  進貨成本    NT$ XXX,XXX （XX%）
  薪資        NT$  XX,XXX （XX%）
  租金        NT$  XX,XXX （XX%）
  ─────────────────────
  支出合計    NT$ XXX,XXX

淨利（虧損）  NT$ ±XX,XXX

與上月比較
  收入：+X% / -X%
  支出：+X% / -X%
```

---

## 五、現金流監控

當使用者問「現金夠嗎」「能撐多久」：

```
月平均支出 = 最近 3 個月支出總和 / 3
可維持月數 = 目前可用現金 / 月平均支出
```

| 可維持月數 | 評價 | 建議 |
|-----------|------|------|
| > 6 個月 | 安全 | 可考慮投資擴張 |
| 3-6 個月 | 正常 | 維持現狀 |
| 1-3 個月 | 警戒 | 控制支出，加速收款 |
| < 1 個月 | 危險 | 催收、延付、借貸 |

### 現金流警訊

以下是 agent 在月結 / 報表 / dashboard 時應自行判斷並提醒的訊號（**系統目前未自動排程或定期檢查現金流**，需 agent 跑 `monthly_summary` 比對近月後人工提醒、必要時建 task 追蹤）：
- 連續 2 個月淨利為負 → 提醒老闆
- 單月支出暴增 > 30% → 提醒老闆
- 應收帳款佔營收 > 40% → 提醒老闆

---

## 六、應收帳款管理

### 檢查逾期

`check_overdue()` — 回傳所有到期日已過且未全額付清的帳目（並把 pending 升為 overdue）。**此工具屬財務工具、受 floor gate**——floored 非財務 / 非全權限層呼不到屬正常，需交有該工具的層 / 全權限層執行（見 CLAUDE.md〈部門安全層（floor）與兩道牆〉、`line-comms.md` 第六節執行模型）。

由 agent 在以下時機主動呼叫（**系統不自動排程**）：
- 每日開工（ops-dashboard 啟動流程，由 agent 判斷處理）
- 月底結帳前
- 客戶要求出貨時（先確認該客戶有無逾期款）

### 帳齡分類與催收

| 帳齡 | 分類 | 催收動作 |
|------|------|---------|
| 1-30 天 | 正常 | 記錄，不催客戶。LINE 通知老闆：「{客戶} 有 NT${金額} 逾期 {天數} 天」 |
| 31-60 天 | 注意 | LINE 友善提醒客戶 + 建立催收任務（agent 動作）：`create_task(title='催收：{客戶} NT${金額}', category='admin')` |
| 61-90 天 | 警告 | 電話催收，建議暫停該客戶出貨，LINE 通知老闆 |
| > 90 天 | 逾期 | 正式催收函，暫停出貨 |

### 催收後續（agent 依 check_overdue 清單處理）

`check_overdue()` 只**回傳逾期清單**（並把 pending 升為 overdue），**不會自己通知老闆或建催收任務**。agent 拿到清單後依上方帳齡表處理（以下皆 agent 動作、非系統自動；通知老闆走上報 / 全權限層）：
- 1-30 天 → 只通知老闆（不打擾客戶）
- 31-60 天 → 通知老闆 + LINE 友善提醒客戶 + 建催收任務
- 61-90 天 → 通知老闆 + 建議暫停出貨
- > 90 天 → 通知老闆 + 建議正式催收

催收範本：
- 31-60 天：「{客戶} 您好，提醒您 {日期} 款項 NT${金額} 尚未收到，方便安排嗎？」
- 61-90 天：「{客戶} 您好，款項已逾期 {X} 天，請盡速處理，謝謝。」

---

## 七、應付帳款管理

### 付款優先排序

| 優先級 | 款項 | 說明 |
|--------|------|------|
| 1 | 薪資、勞健保 | 法定義務 |
| 2 | 稅金 | 逾期有罰則 |
| 3 | 房租、水電 | 影響營運 |
| 4 | 供應商貨款 | 維持供貨 |
| 5 | 其他 | 可彈性調整 |

### 固定支出提醒

系統**有限的**日期提醒由 `_date_reminders()`（純日曆推導、無 DB 機密、各 floor 皆可見）在 `get_context_summary` 啟動 readout 帶出，目前只涵蓋：
- 每月 4-5 日：提醒發薪水
- 每月 23-25 日：提醒繳勞健保
- 單數月 10-15 日：營業稅申報截止
- 5 月：營所稅 + 綜所稅申報

房租等其餘固定支出**系統未排程提醒**，需 agent 在 dashboard / 月結時依公司付款優先序自行提醒、必要時建 task 追蹤。

---

## 八、台灣稅務基礎

### 統一發票

- 銷售開給客戶 → 銷項發票（收入）
- 從供應商取得 → 進項發票（可扣抵）
- 提醒：「進貨有拿到發票嗎？沒有不能扣抵營業稅」
- 發票保存 5 年

### 營業稅

稅率 5%，每 2 個月申報一次（單數月 15 日前）：
- 1-2月 → 3/15
- 3-4月 → 5/15
- 5-6月 → 7/15
- 7-8月 → 9/15
- 9-10月 → 11/15
- 11-12月 → 隔年 1/15

```
應繳營業稅 = 銷項稅額 - 進項稅額
```

`_date_reminders()` 會在單數月 10-15 日的開機 readout 帶出「營業稅申報截止」（系統僅此一處日曆推導提醒、不另外提早一週主動推播）；其餘提早提醒需 agent 自行判斷。

### 勞健保

- 勞保：雇主 70%、勞工 20%、政府 10%（費率約 12%）
- 健保：雇主 60%、勞工 30%、政府 10%（費率約 5.17%）
- 新員工 3 日內加保，離職當日退保

每月記帳（`amount` 為必填、需填實際金額，下方數字僅示意——應取自勞保局 / 健保署當期繳款單，勿沿用範例數字）：
```
record_transaction(type='expense', amount=18500, category='insurance', description='勞保-雇主負擔（{月份} 繳款單）', transaction_date='<繳款日 YYYY-MM-DD>')
record_transaction(type='expense', amount=9200, category='insurance', description='健保-雇主負擔（{月份} 繳款單）', transaction_date='<繳款日 YYYY-MM-DD>')
```
（超門檻時 `record_transaction` 自建審核，不要自己 `create_approval`——見第一節。）

### 重要稅務時程

| 月份 | 事項 |
|------|------|
| 每單數月 15 日 | 營業稅申報 |
| 1 月 | 各類所得扣繳申報 |
| 5 月 | 營所稅 + 綜所稅申報 |
| 9 月 | 營所稅暫繳 |

agent 在啟動 readout / 月結時依上表自行提醒（系統僅 `_date_reminders()` 涵蓋的營業稅、營所稅日期會自動帶出，其餘需 agent 判斷）：「{事項}截止日是 {日期}，建議和記帳士確認。」

---

## 九、財務健康指標

### 毛利率

```
毛利率 = (銷售收入 - 進貨成本) / 銷售收入 × 100%
```

| 毛利率 | 零售業 | 服務業 |
|--------|--------|--------|
| 優秀 | > 40% | > 60% |
| 正常 | 25-40% | 40-60% |
| 偏低 | < 25% | < 40% |

### 淨利率

| 淨利率 | 評價 |
|--------|------|
| > 15% | 獲利能力強 |
| 5-15% | 正常 |
| 0-5% | 偏薄 |
| < 0% | 虧損 |

### 人事費用率

| 比率 | 評價 |
|------|------|
| < 30% | 偏低（可能人力不足） |
| 30-50% | 正常 |
| > 50% | 偏高 |

---

## 十、何時找專業會計

| 情境 | 建議 |
|------|------|
| 月營業額 > NT$200 萬 | 找記帳士 |
| 員工超過 10 人 | 找記帳士 |
| 營業稅申報 | 交給專業 |
| 年度所得稅 | 強烈建議找專業 |
| 要申請貸款 | 需要正式財報 |

### 系統 vs 記帳士分工

| 項目 | 系統 | 記帳士 |
|------|------|--------|
| 日常收支記錄 | 主責 | |
| 收據歸檔 | 主責 | |
| 月度報表 | 主責 | 複核 |
| 營業稅申報 | 提供資料 | 主責 |
| 所得稅申報 | 提供資料 | 主責 |
| 稅務規劃 | | 主責 |

---

## 十一、常見記帳錯誤

| 錯誤 | 預防 |
|------|------|
| 收據不留 | 拍照後立即記帳 |
| 公私帳混一起 | 提醒老闆分開 |
| 只記大筆不記小筆 | 所有支出都記 |
| 重複記帳 | 月結時檢查 |
| 分類全丟「其他」 | 用自動分類 |
| 不做月結 | 每月 1-5 日固定 |
| 進貨沒拿發票 | 每次提醒 |

---

## Do's and Don'ts

### Do
- 金額超過 `approval_threshold` 時，一律直接 `record_transaction`、由它自建審核——**不要自己 `create_approval`**
- 收據看不清楚的欄位直接問，不要猜
- 金額一律用 NT$ + 千位逗號（如 NT$12,345）
- 分類完一律告知讓使用者確認
- 稅務建議附加：「詳細請諮詢記帳士」
- 每次帳務操作都 `log_interaction`

### Don't
- 不要在沒確認金額的情況下記帳
- 刪帳需 `manager` 以上（已落實：floored 取 verified actor 驗權 + audit 具名；operator 全權限路徑放行；另有 floor gate 硬牆）；agent 不應替 basic 權限者執行刪帳
- 不要猜測收據上看不清楚的數字
- 不要做複式簿記或電子發票（Phase 1 不支援）
- 不要給確定性的稅務建議

## 快速參考

> 本節 `record_transaction` / `monthly_summary` / `list_transactions` / `check_overdue` 皆屬財務工具、受 floor gate——floored 非財務 / 非全權限層呼不到屬正常，需交有該工具的層 / 全權限層執行（見 CLAUDE.md〈部門安全層（floor）與兩道牆〉、`line-comms.md` 第六節）。

### 記一筆支出
1. `record_transaction(type='expense', amount=850, category='supplies', description='買影印紙', transaction_date='<收據日 YYYY-MM-DD>')`（`type` / `amount` / `category` 為必填；`amount` 填收據實際金額、留空 `transaction_date` 視為今天）
→ 超過門檻系統會自動建審核並上報簽核人，不需自己 `create_approval`

### 月結作業
1. `monthly_summary(year_month='2026-03')`
2. `list_transactions(type='expense', start_date='2026-03-01', end_date='2026-03-31')`
3. 確認無重複帳目 → 產出月報格式

### 催收檢查
1. `check_overdue()`
2. 依帳齡分類（1-30天/31-60天/61-90天/>90天）決定催收動作（**以下皆 agent 動作、系統不自動建任務或通知**）
3. 31-60天 → `create_task(title='催收：{客戶} NT${金額}', category='admin')`
4. LINE 友善提醒客戶

## 中斷恢復

如果 context 被壓縮：
1. `get_context_summary(scope='full')` — 查看「逾期帳款」區塊
2. `check_overdue()` — 取得所有未付清帳款的完整列表
3. 從帳齡判斷下一步催收動作

---

## 十二、注意事項

- 帳務極敏感，每次操作都 log_interaction
- 刪帳需 `manager` 以上（已落實：floored verified actor 驗權 + audit 具名；operator 放行；另有 floor gate 硬牆，詳見第三節刪帳說明）
- Phase 1 簡單收支，不做複式簿記
- 電子發票 Phase 1 不做
- 稅務建議附加：「詳細請諮詢記帳士」
- 金額用 NT$，千位逗號分隔
- 科目分類可透過 knowledge-capture 自訂
