# LINE 通訊專業指南

## 觸發情境

收到 `<channel source="line">` 訊息，或使用者要求「通知小王」「廣播」「發卡片」

---

## 一、收到 LINE 訊息的處理流程

### 第一步：辨識發送者

從 `<channel>` tag 的 `user_id` 取得 LINE User ID：

1. `lookup_employee(user_id)` → 是員工？查到角色和權限
2. 不是員工 → `find_customer(user_id)` → 是客戶？
3. 都不是 → 陌生人處理（見下方）

### 第二步：判斷意圖與權限

| 意圖 | 需要的權限 | 對應模組 |
|------|-----------|---------|
| 查詢（庫存/任務/規則） | basic | 對應模組 |
| 回報進度 | basic | task-ops |
| 建立任務 | basic | task-ops |
| 記帳/報銷 | basic | accounting-ops |
| 修改庫存 | manager | inventory-ops |
| 修改規則 | admin | knowledge-capture |
| 群發訊息 | admin | line-comms |

權限不足 → 回覆：「這個操作需要主管權限，請聯繫 {boss_title}。」

### 第三步：處理並回覆

根據意圖調用對應模組，然後 `reply` 回覆。

### 第四步：標記訊息狀態

**每則訊息必須有結局，不能停在 queued：**

- 有回覆 → `reply` 自動標記 replied
- 不需要回覆（貼圖、「OK」、「收到」、「👍」）→ `mark_read`
- 不確定 → 回覆「收到」

---

## 二、陌生人處理

不在員工名冊也不在客戶名冊的人傳訊息：

1. **不要回覆對方**
2. 通知老闆：
   ```
   reply(chat_id=老闆LINE_ID,
     text="有人傳了訊息：\n暱稱：{user}\n內容：{content}\n\nUser ID: {user_id}")
   ```
3. `mark_read`
4. 老闆決定是否回覆

老闆的 LINE user_id：查 `employees` 表 `role='boss'`。

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

### 群組類型

| 類型 | 說明 | 回覆策略 |
|------|------|---------|
| `work` | 公司內部工作群 | 被 @ 時處理任務、查詢、回報 |
| `customer` | 客戶/經銷商群 | 被 @ 時用品牌語氣回覆，謹慎 |
| `supplier` | 供應商群 | 被 @ 時處理訂單、交期查詢 |
| `marketing` | 行銷推廣群 | 被 @ 時提供產品資訊 |
| `other` | 其他 | 被 @ 時先辨識身份再處理 |

### 群組註冊

群組需要註冊後 Claude 才知道它的用途：

1. Bot 被加入群組 → 收到 join event 或第一則群組訊息
2. Claude 通知老闆：「我被加入了一個群組（group_id=XXX），這是什麼群？」
3. 老闆說「這是工作群」→ `register_line_group(group_id, '公司工作群', 'work')`

### 群組訊息處理

1. 群組中只回應 **被 @ 的訊息**（line-channel 自動過濾）
2. 收到群組訊息時，先查 `list_line_groups()` 確認群組類型
3. 根據群組類型調整回覆策略：
   - `work` 群 → 可以直接處理任務、查詢、回報
   - `customer` 群 → 先過 brand-voice，語氣要正式
   - 未註冊群組 → 通知老闆確認
4. 回覆時用 `reply(chat_id=群組的group_id, text=...)` 送進群組

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

## 十、注意事項

- LINE 是員工最常用的介面，回覆要快、要準、要簡短
- 不確定的事不要回，轉給老闆
- 每則訊息處理完都要標記狀態
- 所有對外發送（非回覆員工問題的）都 log_interaction
