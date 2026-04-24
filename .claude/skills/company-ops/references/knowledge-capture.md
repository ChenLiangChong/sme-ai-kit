# 知識萃取專業指南

## 觸發情境

**日常知識萃取**：老闆說「從現在開始...」「我們的規定是...」「以後遇到這種情況...」
**系統導入**：「第一次設定」「幫我建立系統」「導入」「開始使用」

---

## 零、系統導入標準流程（首次部署）

> 每次交付 SME-AI-Kit 給新客戶，依此流程執行。
> 不需要一次做完，可以分 2-3 天。老闆累了就停，下次繼續。

### Step 1：公司基本資料

用 `update_company` 設定公司核心資訊：

```
update_company(
  name='公司名稱',
  industry='產業別',
  boss_name='老闆名',
  approval_threshold=5000   // 審核門檻，預設 NT$5,000
)
```

額外的描述性資訊（規模、痛點、業務描述）仍用 store_fact(category='company') 存入 business_rules：

| 問什麼 | 存什麼 | 範例 |
|--------|--------|------|
| 品牌名稱（如果和公司名不同） | title='品牌名稱' | In Love With My Space |
| 公司規模 | title='公司規模' | 5 人 |
| 主要業務描述 | title='主要業務' | 居家商品設計→工廠生產→全台經銷 |
| 目前最大的營運痛點 | title='核心痛點' | 訂單追蹤混亂、應收帳款催不回來 |

### Step 1a：事業體登錄（多品牌/多部門時）

如果公司有多個事業體或品牌，逐一登錄：

```
register_business_entity(
  entity_id='brand_c',
  name='品牌 C（製造/經銷）',
  channel_id='brand_c',        // 對應的 LINE OA channel_id
  approval_threshold=50000     // 該事業體的審核門檻，-1=沿用公司預設
)
```

問老闆：
- 「你有幾個品牌/事業體？各自叫什麼？」
- 「每個品牌有自己的 LINE 帳號嗎？」
- 「審核門檻各品牌一樣嗎？」

#### 後期新增事業體（非初次導入時）

公司成長後可隨時新增事業體，流程：

1. `register_business_entity(entity_id='new_brand', name='新品牌', channel_id='new_brand', approval_threshold=-1)`
2. 設定 LINE OA：在 `data/line-channels.json` 新增 channel 設定，重啟 LINE server
3. 建立庫存：`update_stock(sku='...', name='...', business_unit='new_brand', quantity=初始數量)`
4. 建立規則：`store_fact(category='...', title='...', business_unit='new_brand', ...)`
5. 確認老闆已加入新 OA 為好友
6. 測試：透過新 OA 發送測試訊息，確認 `business_unit` 正確帶入

### Step 2：員工名冊 + LINE 綁定

逐一 `register_employee` 建入所有員工：

```
register_employee(
  name='[員工姓名]',
  role='boss',              // boss / manager / staff
  department='管理部',
  permissions='admin',      // admin / manager / basic
  phone='[手機號碼]',
  business_units='brand_d,content,distribution'  // 所屬事業體，留空=全部
)
```

多事業體時，用 `business_units` 標注員工歸屬的事業體（逗號分隔）。系統路由通知時會依此判斷「WFA 的業務主管是誰」。留空表示該員工跨所有事業體。

LINE 綁定：請每位員工傳一則訊息到 LINE OA → `lookup_employee` 比對 → 更新 `line_user_id`

⚠️ 老闆（role='boss'）必須第一個綁定，後續所有審核通知都發給他。

⚠️ **多 OA 環境**：確認老闆已加入**所有** LINE OA 為好友。LINE push 只對已加好友的使用者有效，如果老闆沒加某個 OA，來自該 OA 的陌生人/審核通知會靜默失敗。

### Step 3：客戶/供應商/經銷商建檔

問老闆：「你最重要的 5-10 個客戶/經銷商/供應商是誰？」

逐一 `add_customer` 建入：

```
add_customer(
  name='好好生活家居',
  type='distributor',
  phone='02-2345-6789',
  discount_rate=0.15,
  payment_terms='net30',
  notes='聯絡人：李經理'
)
```

不需要一次建完，先建最常往來的，後續邊用邊補。

### Step 4：商品/庫存建檔

問老闆：「你的主力商品有哪些？目前庫存大概多少？」

逐一 `update_stock` 建入：

```
update_stock(
  sku='SKU-A001',
  quantity_change=50,
  reason='初始庫存建檔'
)
```

如果商品多，可以讓老闆傳一張 Excel 截圖 → Read tool 辨識 → 逐筆建入。

### Step 5：品牌語氣設定

handoff 到 **brand-voice** 模組。三種方式擇一：

1. **範例分析**（推薦）：請老闆提供 3-5 篇寫得好的文案 → 分析語氣
2. **快速問答**：5 個問題定義品牌個性
3. **兩者結合**：先分析再補充

全部存入 `store_fact(category='brand')`。

### Step 6：深度訪談（用第三節的框架）

按第三節「主動訪談流程」的 8 個領域逐一提問。
每個回答走第二節的被動捕捉流程（確認 → 存入）。

**導入時的額外問題（超出標準 8 領域）：**

| 領域 | 問什麼 |
|------|--------|
| 審核門檻 | 「多少金額以上需要你親自核准？」→ `update_company(approval_threshold=金額)` |
| 訂單流程 | 「客戶下單到收到貨，中間經過哪些步驟？需要品檢嗎？」 |
| 經銷商定價 | 「經銷商折扣怎麼算？不同經銷商不同嗎？」→ 設定每個客戶的 discount_rate |
| 付款條件 | 「客戶付款條件？先付？月結？要收訂金嗎？」→ 設定 payment_terms |
| 帳期 | 「客戶/經銷商的付款條件？月結幾天？」 |
| 催款 | 「逾期多久開始催？怎麼催？」 |
| 報表 | 「你每天/每週/每月想看什麼數字？」→ 設定 ops-dashboard |
| 內容行銷 | 「有在經營社群嗎？哪些平台？更新頻率？」 |
| LINE 訊息路由 | 「陌生人傳訊息要通知��？有業���/客服負責人嗎？���是全部通知你？���→ `store_fact(category='sop', title='LINE 陌生人路由')` |
| 事業體差異 | 「不同品牌/事業體的退貨政策、定價、品牌語氣有沒有不同？」→ 有差異的規則加 `business_unit` 參數存入 |
| 客戶跨事業體 | 「有沒有客戶同時跟多個品牌/事業體合作？折扣和付款條件一樣嗎？」→ 不同的用 `set_customer_entity_terms` ��定 |

### Step 7：業務流程映射

問老闆描述他的核心業務流程（用白話），然後對照系統模組：

```
「你的流程是：{老闆描述}」

這對應到系統的：
1. {步驟} → {模組名}（{tool 名}）
2. {步驟} → {模組名}（{tool 名}）
...

這樣對嗎？有沒有漏掉的步驟？
```

把確認後的流程存入：
```
store_fact(
  category='sop',
  title='核心業務流程',
  content='完整流程描述...',
  source_type='explicit',
  source_quote=老闆原話
)
```

### Step 8：校準測試

用一筆真實業務跑一輪完整流程：

- [ ] 模擬接到一張訂單 → order-ops 建單
- [ ] 確認庫存 → inventory-ops
- [ ] QC → 出貨 → fulfill_order
- [ ] 記帳 → accounting-ops
- [ ] LINE 通知客戶 → line-comms
- [ ] 把結果給老闆看，問：「這樣對嗎？有哪裡需要調整？」

調整的部分 → 回到 Step 6 補充規則。

### Step 9：上線

- 第一週每天跑 ops-dashboard，確認報表數字對不對
- 遇到系統不知道怎麼處理的情況 → 問老闆 → 被動捕捉新規則
- 每天結束前 `save_session_handoff`，確保隔天能接續

### 導入進度追蹤

用 `create_task(category='admin')` 追蹤每個步驟的完成狀態：

```
create_task(title='導入 Step 1：公司基本資料', category='admin', assignee='AI助理')
create_task(title='導入 Step 2：員工名冊+LINE綁定', category='admin', assignee='AI助理')
...
```

每完成一步就 `update_task(status='done')`。

---

## 一、核心哲學

引用 SOP Creator 的原則：**沒人看 50 頁文件。**

好的企業知識：
- **可掃描** — 標題、列點、表格。不要整段文字
- **可執行** — 每一步是具體動作，不是「考慮」「斟酌」
- **夠具體** — 有數字、有名字、有門檻。不要「適當」「視情況」
- **可驗證** — 怎麼知道做對了？有明確的完成標準
- **有人維護** — 知道是誰定的、什麼時候定的、誰可以改

### Be Specific 對照表

| 不要這樣寫 | 要這樣寫 |
|-----------|---------|
| 「聯繫相關人員」 | 「LINE 通知員工甲」 |
| 「等到準備好」 | 「等狀態顯示『完成』（約 5 分鐘）」 |
| 「仔細檢查」 | 「確認 A、B、C 三個欄位」 |
| 「視情況而定」 | 「金額 > NT$5,000 時」 |
| 「定期」 | 「每週一早上 9 點」 |
| 「盡快」 | 「2 小時內」 |

---

## 二、被動捕捉流程

老闆在對話中提到一條規則時：

1. **辨識** — 這是規則還是閒聊？
   - 規則特徵：「從現在開始」「一律」「不可以」「超過 X 就要」
   - 閒聊特徵：「我覺得」「搞不好」「有一次」

2. **提取原話** — 用老闆的原話當 `source_quote`

3. **確認** — 回覆：
   ```
   我理解的是：

   📋 {整理後的規則，具體化}

   老闆原話：「{source_quote}」
   分類：{category}

   這樣對嗎？確認後我就存進系統。
   ```

4. **存入** — 老闆確認後：
   ```
   store_fact(
     category=分類,
     title=規則標題,
     content=整理後的規則,
     source_type='explicit',
     source_quote=原話,
     set_by=老闆名
   )
   ```

5. **矛盾處理** — 如果 store_fact 回傳矛盾警告：
   - 列出衝突的舊規則
   - 問老闆：「這跟之前的規則 #{id} 有衝突，要取代它嗎？」
   - 確認後用 `update_rule` 取代

---

## 三、主動訪談流程

系統初次導入或老闆說「幫我建立公司規則」時，按領域逐一提問：

### 訪談大綱

| 順序 | 領域 | 核心問題 |
|------|------|---------|
| 1 | 退貨政策 | 「客戶買了不滿意可以退嗎？期限？條件？例外？」 |
| 2 | 定價規則 | 「定價的邏輯？不同客戶不同價？折扣怎麼給？」 |
| 3 | 供應商 | 「供應商怎麼選？付款條件？延遲怎麼處理？」 |
| 4 | 人事 | 「上班時間？請假規定？加班怎麼算？」 |
| 5 | 客戶服務 | 「客訴怎麼處理？特殊客戶注意事項？」 |
| 6 | 庫存 | 「什麼時候補貨？安全庫存怎麼定？盤點頻率？」 |
| 7 | 財務 | 「多少金額需要你核准？記帳有什麼規定？」 |
| 8 | 品牌 | 「對外溝通的語氣？禁用詞？」 |

### 訪談技巧

**追問邊界案例：**
- 「如果客戶說產品壞了但已超過退貨期限呢？」
- 「如果供應商說要漲價 10% 呢？」
- 「如果同一天有 3 個人請假呢？」

**追問數字：**
- 「『太多』是多少？5 個以上？10 個以上？」
- 「『很久沒來』是多久？1 個月？3 個月？」
- 「『大單』是多大？NT$10,000？NT$50,000？」

**追問例外：**
- 「有沒有例外情況？VIP 客戶不同？」
- 「這個規則有沒有例外？什麼情況下不適用？」

每個回答都走被動捕捉流程（確認 → 存入）。
老闆不想回答的就跳過，不強迫。

---

## 四、知識分類體系

### 預設類別

`hr`, `pricing`, `return_policy`, `supplier`, `customer_service`, `inventory`, `finance`, `sop`, `brand`, `general`

不在預設裡的 → Claude 判斷最接近的，或用 `general`。

### 分類決策

| 關鍵字 | 分類 |
|--------|------|
| 上班/請假/加班/薪水/考績 | `hr` |
| 價格/折扣/報價/牌價/定價 | `pricing` |
| 退貨/退款/換貨/保固 | `return_policy` |
| 供應商/進貨/工廠/交期 | `supplier` |
| 客訴/客服/服務/投訴 | `customer_service` |
| 庫存/盤點/補貨/安全量 | `inventory` |
| 記帳/發票/報稅/核准金額 | `finance` |
| 流程/步驟/SOP/標準 | `sop` |
| 品牌/語氣/文案/禁用詞 | `brand` |

---

## 五、知識品質檢查

每條規則存入前，內部驗證：

- [ ] 有具體的觸發條件（什麼情況下用這條規則）
- [ ] 有具體的動作（要做什麼）
- [ ] 有數字或門檻（不是「很多」「很久」）
- [ ] 有明確的負責人或適用對象
- [ ] 邊界案例有涵蓋（例外情況怎麼辦）

不完整的 → 追問補充後再存。

---

## 六、反捏造原則

- `source_type='explicit'` → **必須**有 source_quote（老闆原話）
- 你觀察到的慣例 → `source_type='observed'`，告知老闆
- 你推斷的 → `source_type='inferred'`，明確標注待確認
- **絕不可把 inferred 偽裝成 explicit**
- 引用規則時，優先引用 explicit，其次 observed，最後 inferred

---

## 七、知識更新與退役

### 更新流程

老闆說「從現在開始改成...」：
1. `query_knowledge` 找到舊規則
2. 確認要取代哪條
3. `update_rule(old_id, new_content, reason)`
4. 舊規則自動標記 superseded_by

### 退役信號

以下情況建議老闆檢討規則：
- 規則超過 6 個月沒被引用
- 同類別有 3 條以上互相矛盾
- 員工反映「系統說的跟實際做法不一樣」

### 知識健檢（Lint）

定期（建議每月一次）執行 `lint_knowledge()` 進行知識庫健檢：
- **矛盾**：偵測同類別中可能矛盾的規則對
- **過期**：標記超過 6 個月未更新的規則
- **覆蓋**：找出覆蓋不足的類別（空白或偏少）
- **孤立鏈**：檢查 superseded_by 指向不存在的 ID

可指定檢查：`lint_knowledge(checks='stale,coverage')`

建議月報時一併執行，結果納入「企業規則變更」區塊。

### 知識變更日誌

`knowledge_changelog(days=7)` — 查看最近 N 天的知識變更：
- 新增了哪些規則（按日期分組）
- 更新了哪些規則（含原因）
- 月報時用 `knowledge_changelog(days=30)`

### 交叉引用

規則之間可建立關聯（rule_relations 表）：
- `store_fact` 偵測到相似規則時**自動建立** 'related' 關聯
- 手動建立：`link_rules(rule_id_a=12, rule_id_b=45, relation_type='depends_on')`
- 查詢關聯：`get_rule_relations(rule_id=12)`
- `query_knowledge` 結果會附帶相關規則的交叉引用
- `update_rule` 更新時會自動遷移關聯並提醒檢查連動規則
- 關聯類型：`related`（相關）、`depends_on`（依賴）、`conflicts_with`（衝突）

---

## Do's and Don'ts

### Do
- 存入前一定要先回覆確認，等老闆說「對」才存
- `source_type='explicit'` 必須附上 `source_quote`（老闆原話）
- 每條規則確保有觸發條件、具體動作、數字門檻
- 老闆改主意時用 `update_rule`，不要直接覆蓋
- 所有規則變更都 `log_interaction`

### Don't
- 不要自作主張存入規則（一定要確認）
- 不要把 `inferred` 偽裝成 `explicit`
- 不要一次問老闆太多問題（每次 3-5 個領域）
- 不要存入模糊規則（「適當」「視情況」→ 追問具體數字）
- 不要用 `delete_fact` 取代更新 — 用 `update_rule` 保留歷史

## 快速參考

### 被動捕捉規則
1. 辨識老闆話中的規則特徵（「從現在開始」「一律」「不可以」「超過 X 就要」）
2. 回覆確認：「我理解的是：{規則}。這樣對嗎？」
3. `store_fact(category='pricing', title='經銷商折扣', content='規則內容', source_type='explicit', source_quote='老闆原話', set_by='老闆名')`

### 更新既有規則
1. `query_knowledge(question='退貨政策', category='return_policy')` — 找到舊規則
2. `update_rule(rule_id=舊ID, new_content='新規則內容', reason='老闆更新')`

### 知識健檢與變更日誌
1. `lint_knowledge()` — 全面健檢（矛盾、過期、覆蓋、孤立鏈）
2. `lint_knowledge(checks='stale')` — 只查過期規則
3. `knowledge_changelog(days=30)` — 查看最近 30 天的變更

### 交叉引用
1. `link_rules(rule_id_a=12, rule_id_b=45, relation_type='related')` — 手動建立關聯
2. `get_rule_relations(rule_id=12)` — 查看規則的所有關聯

---

## 八、注意事項

- 存入前一定要確認，不要自作主張
- 矛盾偵測靠 store_fact 內建的檢查
- 老闆改主意時用 update_rule，不要直接覆蓋
- 訪談時不要一次問太多（每次 3-5 個領域，老闆累了就停）
- 所有規則變更都記 interaction_log
