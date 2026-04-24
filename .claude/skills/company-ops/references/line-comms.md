# LINE 通訊專業指南

## 觸發情境

收到 `<channel source="line">` 訊息，或使用者要求「通知員工甲」「廣播」「發卡片」

---

## 一、收到 LINE 訊息的處理流程

> 與 CLAUDE.md「⚠️ LINE 訊息處理」完全一致。CLAUDE.md 是權威來源。

### 第一步：辨識身份

從 `<channel>` tag 的 `user_id` 取得 LINE User ID，**依序查以下身份**（找到即停）：

1. 呼叫 `lookup_employee(user_id)` — 是員工嗎？
2. 不是員工 → 呼叫 `find_customer(user_id)` — 是客戶/供應商/經銷商嗎？
3. 都不是 → 呼叫 `find_partner(user_id)` — 是**外包夥伴**嗎？（Bonny/Ray/Ken 等協作者）
4. 都不是 → 嘗試用 LINE 暱稱比對未綁定的員工：
   - `lookup_employee(暱稱)` — 用 `<channel>` tag 的 `user` 欄位
   - 如果找到一位 `line_user_id` 為空的員工 → 回覆對方確認：「你是 {部門} 的 {姓名} 嗎？」
   - 對方確認 → `update_employee(employee_id, line_user_id=user_id)` 完成綁定
   - 找不到或多人同名 → 走陌生人流程（第二節）
5. 也可能是待綁定的外包夥伴（`find_partner(暱稱)` + 回覆確認 + `update_partner(line_user_id=...)`）
6. 陌生人處理 → **不要回覆對方**。改為通知老闆（第二節）
7. 老闆回覆「這是 XXX」→ 綁定到對應的員工、客戶或外包記錄

老闆的 LINE user_id：查 `employees` 表 `role='boss'`。

### 第二步：判斷權限

| 意圖 | 需要的權限 |
|------|-----------|
| 查詢（庫存/任務/規則） | basic |
| 回報進度、建立任務 | basic |
| 記帳/報銷 | basic |
| 修改庫存 | manager |
| 修改規則 | admin |
| 群發訊息 | admin |

權限不足 → 回覆：「這個操作需要主管權限。」

### 第三步：處理並回覆

根據意圖用對應的 business-db tools 處理，然後用 `reply` 回覆。

### 第四步：標記訊息狀態

**每則訊息必須有結局：**
- 有回覆 → `reply` 會自動標記
- 不需回覆（貼圖、「OK」、「收到」、「👍」）→ `mark_read`
- 不確定 → 回覆「收到」

---

## 二、陌生人處理（分層路由）

不在員工名冊也不在客戶名冊的人傳訊息：

### Step 1：不要回覆對方

### Step 2：查路由規則 → 判斷意圖 → 通知對應負責人

先查 DB 有無自訂路由規則：
`query_knowledge(question='LINE 陌生人路由', category='sop')`

**如果有自訂規則** → 按規則路由（導入時由 knowledge-capture 設定）。

**如果沒有自訂規則** → 用預設邏輯：

| 意圖判斷 | 通知誰 | 怎麼找 |
|---------|--------|--------|
| 詢價/業務合作 | 業務負責人 | `list_employees()` 找 department 含「業務/銷售」的 manager，沒有就通知老闆 |
| 客訴/售後問題 | 客服負責人 | `list_employees()` 找 department 含「客服」的人，沒有就通知老闆 |
| 求職/應徵 | 人事或老闆 | `list_employees()` 找 department 含「人事/HR」的人，沒有就通知老闆 |
| 推銷/廣告/垃圾 | 不通知任何人 | 直接 `mark_read`，不浪費老闆時間 |
| 無法判斷 | 老闆 | fallback，永遠通知老闆 |

通知格式：
```
reply(chat_id=負責人的LINE_user_id, text="有陌生人傳了訊息：\n暱稱：{user}\n內容：{content}\n判斷意圖：{意圖}\nUser ID: {user_id}")
```

### Step 3：標記已處理

`mark_read(chat_id=user_id)`

### Step 4：負責人回覆處理

- 負責人回覆「加入客戶」→ `add_customer(name=暱稱, notes='LINE 主動詢問')`
- 負責人回覆「這是 XXX」→ 綁定到對應的員工或客戶記錄
- 負責人回覆「忽略」→ 不做任何事

### 找老闆 + 通知頻道選擇

老闆的 LINE user_id：`list_employees()` 找 `role='boss'` 的員工取 `line_user_id`。

**通知頻道選擇（多 OA 環境重要）：**
1. **優先**：用收到陌生訊息的同一個 `channel_id` 通知（老闆能直接知道來源 OA）
2. **如果推送失敗或不確定老闆是否加了該 OA**：改用 default channel（`list_channels` 查詢）
3. **通知內容要包含來源 OA 資訊**：「[{channel_name}] 有陌生人傳了訊息：...」

⚠️ LINE push 靜默失敗無錯誤回傳。預防方式：導入時確認老闆已加入所有 OA 為好友。

### 導入時需設定

在 knowledge-capture 導入 Step 6 時問老闆：
- 「不同類型的陌生訊息要通知誰？有沒有業務/客服負責人？」
- 如果只有老闆一人 → 全部通知老闆（退化為舊邏輯）
- 如果有分工 → 按上表路由

### ⚠️ 通知頻道注意事項

通知員工/老闆時，LINE push 只對「已加入該 OA 好友」的使用者有效。

- 導入時確認老闆已加入所有 LINE OA 為好友
- **啟動流程驗證**（多 OA 環境）：用 `list_channels()` 取得所有 OA，對每個 OA 嘗試 `reply` 測試推送給老闆。如果老闆尚未加入某 OA，在 dashboard 報告中提醒：「⚠️ 老闆尚未加入 {channel_name} 為好友，該 OA 的審核/路由通知將無法送達」
- 通知老闆時優先用老闆最常用的 OA channel_id
- 如果不確定老闆加了哪些 OA → 用 `list_channels` 查已設定的 OA，選 default channel
- 員工通知同理：確認員工已加入要通知的 OA

通知失敗（LINE push 靜默失敗）時不會有錯誤訊息，所以**預防比修復重要**。

---

## 三、訊息類型處理

| 類型 | 處理 |
|------|------|
| 文字 | 正常處理 |
| [圖片] + 路徑 | Read tool 看圖 → 理解內容 → 處理（收據→記帳、商品→查庫存） |
| [語音] | 「目前僅支援文字訊息，請用打字的方式告訴我」 |
| [貼圖] | `mark_read`，不回覆 |
| [位置] | 記錄，如果跟任務相關就更新 |
| [檔案] | PDF → Read tool 查看。其他 → 「已收到檔案」 |

### 圖片/檔案儲存路徑

LINE 用戶傳送的媒體會自動下載到本地：
- 圖片 → `data/media/line/images/{messageId}.jpg`
- 文件（PDF/Excel/Word）→ `data/media/line/files/{messageId}.{ext}`
- 影片/語音 → 暫不支援自動處理

收到 `[圖片] {路徑}` 時 → 用 Read tool 查看圖片內容（辨識收據、商品照等）
收到 `[檔案] {路徑}` 時 → 用 Read tool 或 office skill 處理

---

## 四、群組管理

> **權威來源：規則 #32「LINE 群組訊息路由」+ 規則 #33「新群組登入 SOP」**
> 本節是快速查閱版，完整決策樹與安全邊界請查：
> - `query_knowledge(question='LINE 群組訊息路由')`
> - `query_knowledge(question='新群組登入 SOP')`

### 系統層過濾（已實作）

LINE MCP server（`line-channel/server.ts` L662-675）已經：
- **1-on-1 DM**：100% 收進 business-db
- **群組訊息**：只有**被 @mention 的文字訊息**才會進 business-db，沒 @ 直接 `continue` 丟棄
- 被 @ 時自動把 `@AI` 字串從訊息剝掉，留純指令

**所以 business-db 收到的群組訊息 = 保證已經被人 @ 過 AI**

### 群組類型與 AI 行為

| 類型 | 說明 | 回覆策略 |
|------|------|---------|
| `work` | 公司內部工作群 | Boss 白名單動作關鍵字觸發；其他人 @AI 觸發；對外永遠 HITL |
| `customer` | 客戶/經銷商群 | 套品牌語氣（規則 #11-#13）；詢價/客訴立即通知內勤 |
| `supplier` | 供應商群 | 進貨/交期追蹤；不主動 |
| `marketing` | 行銷推廣群 | 全 HITL，草擬後等核准再發 |
| `other` | 測試群 / 暫不分類 | **完全沉默**（即使被 @ 也不回），僅被動記錄 |

### Boss 白名單動作關鍵字
老闆 或高明傳在 `work` 群直接發這些關鍵字不需 @AI 就觸發：
`幫我`、`查`、`找`、`排單`、`出貨`、`記`、`通知`、`建立`、`列出`、`更新`、`取消`、`核准`、`駁回`、`盤點`、`補貨`、`提醒`、`匯出`、`寄`、`傳送`

### 群組訊息處理決策樹

```
收到群組訊息（已保證被 @ 過）
  ↓
Step 1: list_line_groups 或查 line_groups 表
  ├─ 未登錄 → 走規則 #33（沉默 + 通知 老闆）
  └─ 已登錄 → Step 2

Step 2: 按 group_type
  ├─ other → 完全沉默（連 @ 也不回）
  ├─ work → Step 3
  ├─ customer/supplier/marketing → Step 3（套對應品牌語氣）

Step 3: 識別發訊者身份（依序查）
  1. lookup_employee(user_id) → 員工 → 按 permissions 執行
  2. find_customer(user_id) → 客戶/供應商 → 套品牌語氣
  3. find_partner(user_id) → 外包夥伴 → 協作身份，可查詢不可執行
  4. 都沒找到 → 陌生人 → 🔴 紅旗通知 老闆

Step 4: 對外動作（發 LINE/記帳/下單）永遠走 HITL
```

### 新群組登入 SOP（規則 #33 摘要）

#### 情境 A：Bot 被加入新群組
LINE MCP 發 `event.type='join'` → AI 應：
1. 對 老闆 發 LINE DM：「🆕 Bot 被加入新群組 C...，要登錄嗎？」
2. 老闆 回覆「登錄：類型 / 名稱 / 成員」→ `register_line_group()`
3. 老闆 回「忽略」→ 不登錄（下次該群組 @AI 走情境 B）

#### 情境 B：未登錄群組有人 @AI
1. **沉默不回**（絕對不在陌生群組發話）
2. 對 老闆 發 LINE DM 通知「未登錄群組有人 @AI，要登錄嗎？」

#### 情境 C：老闆 主動預先登錄
老闆 在對話說「幫我登錄這個群組...」→ `register_line_group()`

### 群組工具速查
- `list_line_groups()` — 列出所有群組（顯示 🎯 功能 + 📝 備註）
- `list_line_groups(group_type='work')` — 只看工作群
- `register_line_group(group_id, group_name, group_type, channel_id, purpose, notes)` — 新增/更新群組
- `search_line_messages(query='關鍵字')` — 搜尋訊息（含 [群組] 標記）

### 群組欄位語意
- `group_type` — 分類（work/customer/supplier/marketing/other）決定 AI 行為策略
- **`purpose`** — 一句話功能描述（例：「品牌 C內勤訂單協調」「鼎新供應商交期追蹤」）
- `notes` — 成員列表、特殊規則、備註等自由文字
- AI 處理群組訊息時應**讀 purpose + notes** 做為上下文補充

### 查詢群組

- `list_line_groups()` — 列出所有群組
- `list_line_groups(group_type='work')` — 只看工作群
- `search_line_messages(query='關鍵字')` — 搜尋群組訊息（結果含 [群組] 標記）

---

## 五、回覆語氣

| 對象 | 稱呼 | 語氣 |
|------|------|------|
| 主管 (boss/manager) | 您 | 專業 |
| 員工 (staff) | 你 | 親切直接 |
| 客戶 | 您 | 禮貌 |
| 陌生人 | — | 不回覆 |

---

## 六、LINE 訊息格式

### 文字訊息原則

- 一則不超過 200 字
- 重點放前面（手機螢幕小）
- 適當換行
- emoji 1-2 個就好

### Flex Message 使用場景

| 場景 | 用 Flex 的好處 |
|------|--------------|
| 任務指派 | 任務標題 + 截止日 + 負責人，一目了然 |
| 庫存警報 | 品名 + 數量 + 建議動作 |
| 收支摘要 | 金額 + 分類 + 日期，格式整齊 |
| 審核請求 | 內容摘要 + 「核准」/「駁回」提示 |
| 日報 | 5 個核心數字，卡片格式 |

### 審核回覆機制

Phase 1 用文字回覆（不用 Postback 按鈕）：
- 主管收到審核通知 → 回覆「核准 #123」或「駁回 #123」
- Claude 解析 → `resolve_approval(123, 'approved', 主管名)`

---

## 七、防騷擾規則

- 同一人 1 小時內不主動推超過 5 則
- 員工問問題的回覆不算限制
- 廣播一律需 admin 核准
- 晚上 10 點到早上 8 點不主動推送（除非緊急）

---

## 八、LINE 訊息歷史查詢

所有 LINE 收發訊息都自動存入 `line_messages` 表。用 `search_line_messages` 查詢：

### 常見查詢

| 使用者說 | 怎麼查 |
|---------|--------|
| 「王經理上週傳了什麼」 | `search_line_messages(user_name='王', days=7)` |
| 「最近有誰提到退貨」 | `search_line_messages(query='退貨')` |
| 「今天收到幾則 LINE」 | `search_line_messages(direction='inbound', days=1)` |
| 「我們回了什麼給張小姐」 | `search_line_messages(user_name='張', direction='outbound')` |
| 「群組裡最近的討論」 | `search_line_messages(days=3)` 然後過濾 [群組] 標記 |

### 參數

- `query` — 關鍵字（模糊搜尋訊息內容）
- `user_id` — 精確比對 LINE user ID
- `user_name` — 模糊比對暱稱
- `direction` — `inbound`（收到）/ `outbound`（發出）/ 留空=全部
- `days` — 最近幾天（預設 7）
- `limit` — 最多幾則（預設 30）

---

## 九、LINE OA 額度管理

免費方案每月 200 則 push message。

| 額度使用率 | 建議 |
|-----------|------|
| < 50% | 正常使用 |
| 50-80% | 減少非必要推送 |
| > 80% | 警告老闆，建議升級或減少廣播 |

額度追蹤方式：
- 系統目前無法自動查詢 LINE 額度（LINE MCP 尚未支援 quota API）
- 每月 1 日提醒老闆：「建議到 LINE Official Account Manager 後台檢查本月訊息額度」
- 日常優先使用 `reply`（回覆訊息不計入 push 額度），減少主動 push
- 群發前先估算：本月已發 N 則 + 這次要發 M 則，是否超過方案上限

---

## Do's and Don'ts

### Do
- 每則 LINE 訊息處理完都要有結局：`reply` 或 `mark_read`
- 回覆前先辨識身份：`lookup_employee` → `find_customer` → 陌生人流程
- 回覆時傳入正確的 `channel_id`（從哪個 OA 收到就用哪個 OA 回）
- 所有對外發送都 `log_interaction`
- LINE 訊息不超過 200 字，重點放前面

### Don't
- 不要回覆陌生人（通知老闆或對應負責人）
- 不要對同一人 1 小時內推超過 5 則
- 不要在晚上 10 點到早上 8 點主動推送（除非緊急）
- 不要未經 admin 核准就廣播
- 不要在未辨識身份的情況下執行操作

## 快速參考

### 辨識身份 + 回覆
1. `lookup_employee(name_or_line_id=user_id)` — 是員工？
2. 不是 → `find_customer(query=user_id)` — 是客戶？
3. 都不是 → 陌生人路由（見下方）
4. 是員工/客戶 → 處理請求 → `reply(channel_id=channel_id, chat_id=chat_id, text='回覆內容')`

### 陌生人路由
1. `query_knowledge(question='LINE 陌生人路由', category='sop')` — 查路由規��
2. 判斷意圖（詢價/客訴/求職/推銷）
3. 推銷 → `mark_read(channel_id=channel_id, chat_id=chat_id)` 直接結束
4. 其他 → `reply(channel_id=channel_id, chat_id=負責人LINE_user_id, text='[{channel_name}] 有陌生人傳了訊息：...')` 通知對應負責人
   - 多 OA 環境：優先用收到訊息的 channel_id，不確定負責人是否加了該 OA 時改用 default channel
5. `mark_read(channel_id=channel_id, chat_id=原始chat_id)`

---

## 十、注意事項

- LINE 是員工最常用的介面，回覆要快、要準、要簡短
- 不確定的事不要回，轉給老闆
- 每則訊息處理完都要標記狀態
- 所有對外發送（非回覆員工問題的）都 log_interaction

---

## 多 LINE OA 注意事項

系統支援多個 LINE OA（品牌帳號）同時運作。

### 識別來源

每則 LINE 訊息的 meta 帶有 `channel_id`、`channel_name` 和 `business_unit`：
- `channel_id` = 設定檔中的 key（如 `brand_a`、`brand_b`）
- `channel_name` = OA 顯示名稱
- `business_unit` = 該 OA 所屬事業體（如 `brand_c`、`brand_d`）

### 事業體感知

收到 LINE 訊息後，從 `business_unit` meta 判斷所屬事業體：
- 建立訂單 → `create_order(..., business_unit=business_unit)`
- 查庫存 → `check_stock(sku, business_unit=business_unit)`
- 記帳 → `record_transaction(..., business_unit=business_unit)`
- 查規則 → `query_knowledge(..., business_unit=business_unit)`
- 存規則 → `store_fact(..., business_unit=business_unit)`（如果是事業體特定規則）

### 回覆規則

- **回覆時必須傳入正確的 `channel_id`**：`reply(channel_id='brand_a', chat_id='U...', text='...')`
- 從哪個 OA 收到訊息，就用哪個 OA 回覆
- 省略 `channel_id` 時使用預設 channel

### 查詢 OA 清單

`list_channels` 列出所有已設定的 LINE OA 及其 channel_id。

### 跨 OA 通知

如果需要用特定 OA 通知某人（如用 品牌 A 帳號通知客戶）：
1. 確認該人是該 OA 的好友
2. 用對應的 channel_id 發送：`reply(channel_id='brand_a', chat_id='U...', text='...')`

### 搜尋歷史訊息

`search_line_messages(channel_id='brand_a')` 可按 OA 篩選訊息歷史。
