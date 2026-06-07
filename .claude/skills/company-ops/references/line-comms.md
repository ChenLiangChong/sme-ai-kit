# LINE 通訊專業指南（律所所內專用）

## 觸發情境

收到 `<channel source="line">` 訊息，或使用者要求「通知律師甲」「發卡片」

> **本檔定位**：這是**通用的 inbound LINE 處理契約**——辨識身份、判斷權限、處理、結局、floor 路由、執行模型。律所的核心情境（律師/助理傳判決書／裁定／開庭通知要算時限）只是「文件抽取」這一條路徑，**詳細流程見 `.claude/skills/legal-admin/references/deadline-intake.md`**；本檔講的是那條路徑之外、所有 LINE 訊息共通的處理規則。
>
> **所內專用 = 沒有對外通道**：LINE 只給**所內律師／助理／行政**用，不接委任人對話、不做陌生人分層路由、不做對外行銷。下文已據此把通用模板收斂成律所版。

---

## 一、收到 LINE 訊息的處理流程

> 與 CLAUDE.md「⚠️ LINE 訊息處理」完全一致。CLAUDE.md 是權威來源。

### 第一步：辨識身份

> floor 提醒：`lookup_employee` / `list_employees` / 綁定用的 `update_employee` 屬 **HR 工具**、floored 受限層被物理移除。**個人律所通常不設 `SME_FLOOR`（全權限單人）、這些工具都在**；`confidential` 欄 + floor gate 是**保留為 inert** 的升級路（待增助理 / 多人版再啟用，見 CLAUDE.md〈部門安全層（floor）〉、`legal-admin/SKILL.md`〈安全執行模型〉）。若未來分層、辨識不出身份時依第六節交給全權限層、別假設受限層有 `lookup_employee`。

從 `<channel>` tag 的 `user_id` 取得 LINE User ID，**依序查身份**（找到即停）：

1. 呼叫 `lookup_employee(user_id)` — 是所內人員（律師／助理／行政）嗎？
2. 不是 → 嘗試用 LINE 暱稱比對未綁定的所內人員：
   - `lookup_employee(暱稱)` — 用 `<channel>` tag 的 `user` 欄位
   - 如果找到一位 `line_user_id` 為空的人員 → 回覆對方確認：「你是 {姓名} 嗎？」
   - 對方確認 → `update_employee(employee_id, line_user_id=user_id)` 完成綁定
   - 找不到或多人同名 → 走「非名冊用戶」硬規則（見下方第三步前的提示）
3. 主持律師回覆「這是 XXX」→ 綁定到對應的人員記錄

> **律所沒有客戶／供應商／經銷商／外包夥伴的 LINE 身份鏈**（`find_customer` / `find_partner` 不是律所 inbound 的主路徑——委任人不走 LINE、見下方邊界）。辨識只有兩種結果：**所內名冊上的人**、或**非名冊的未識別用戶**。

> **誰能 reply 通知，看你這層的能力**：個人律所全權限單人 session 可直接 reply / push。若未來分層、你是受限部門 session（有 `SME_FLOOR`），「要通知主持律師 / 簽核人」一律走**上報（escalation）機制**或由**全權限層**處理，不要自己撈 `role=boss` 的 user_id 去 `reply`（見 CLAUDE.md〈上報（escalation）機制〉、本檔第六節執行模型）。

### 非名冊用戶 = 硬規則（不回業務內容）

辨識後**不在所內名冊**的 LINE 用戶（含暱稱比對不到、多人同名無法確認）：

1. **不回覆任何業務內容**（律所對內專用、LINE 上沒有對外服務的對象）。
2. `mark_read`（標記已處理，給該則一個結局）。
3. 提示主持律師：「有未識別 LINE 用戶 {暱稱}（User ID: {user_id}）傳訊，請確認是否新進人員需建檔綁定。」——個人律所全權限層直接 reply / push 主持律師；未來分層則走上報機制 / 全權限層。
4. 主持律師確認「這是新來的助理 XXX」→ `register_employee` 建檔後 `update_employee` 綁 `line_user_id`；回「忽略」→ 不做事（已 `mark_read`）。

> **委任人來電約諮詢的邊界（講死、不可破）**：委任人／民眾在 LINE 傳訊（含「我想約諮詢」「我這個案子……」）一律**走上面非名冊硬規則：不回業務內容 + `mark_read` + 提示主持律師**。**約諮詢只走電話、由行政人工建立**（`create_task` + 行事曆，見 `legal-admin/references/consultation.md`），**不在 LINE 上開委任人對話、不在 LINE 上做法律問答**。理由：LINE 是所內工作介面、不是對外客服窗口；諮詢預約是行政動作、且法律實質問題只能由律師本人面談評估（答錯有執業責任）。

### 第二步：判斷權限

權限有**兩層**、不要搞混：

- **軟層（對話禮貌提示，純 UX）**：依下表的個人身份標記（`permissions` 欄＝這個人在名冊上記的 staff / manager / admin）給出禮貌提示，例如「這個操作通常需要主管確認，我幫你轉給 {主持律師}」。這只是話術、**不是真正的隔離**。
- **硬層（真正的牆）= business-db floor gate**：你這個 session 能呼叫到哪些工具，由 `SME_FLOOR` + floor-map 在 server 啟動時物理決定（見 CLAUDE.md〈部門安全層（floor）與兩道牆〉）。**呼不到某支工具＝這層沒有那個權限、不是系統壞**；能呼叫到的工具就是被允許的。受限層連 `business.db` 都讀不到、唯一入口是這組 floor-gated MCP 工具。
- **個人律所＝全權限單人**：通常不設 `SME_FLOOR`、所有工具都在，硬層不啟用（保留 inert 為升級路）。下表的軟層提示在單人所多半用不到（律師自己就是 admin），但分層後（增助理）仍適用。

| 意圖 | 個人身份標記（提示 / 上報判斷用） |
|------|-----------|
| 查詢（案件／時限／規則） | staff |
| 回報進度、建立任務 | staff |
| 標記書狀已遞交 | staff |
| 異動已入庫時限（改送達日／天數重算） | manager |
| 員工建檔 / 權限變動 | admin |

> `permissions` 欄只是**禮貌提示 + 上報判斷**用的個人身份標記，不是硬隔離。真正能不能做，看你這層 floor gate 有沒有那支工具。
>
> **過時提醒**（別再照舊表回「需要 admin」）：
> - 「修改規則 / 法律見解 / SOP」不再是單純 admin 把關——知識有**機密軸**（confidential），非全權限層的 `query_knowledge` 本來就看不到機密規則（見 CLAUDE.md〈機密軸（confidential）〉）。

**診斷本層能力**：不確定自己這層有沒有某個權限／工具時，用 `floor_status` / `floor_config_status` 查本層實際的可見度與工具範圍，不要靠猜。被 gate 擋下（呼不到工具）→ 照實回報「這層沒有這個權限」，不要當系統錯誤。

### 第三步：處理並回覆

辨識為所內人員後，根據意圖用對應的 business-db tools 處理，然後用 `reply` 回覆。常見路徑：

- **傳判決書／裁定／開庭通知要算時限** → 走 `legal-admin/references/deadline-intake.md`：讀檔抽取 → `stage_deadline_intake` 暫存 → 推回 LINE **一鍵確認** → 確認後 `create_deadline`。**絕不在 LINE 上自己心算天數**——時限天數一律由引擎確定性計算附 `statutory_basis`（反捏造、算錯＝執業過失，見 CLAUDE.md〈反捏造原則〉、`legal-admin/SKILL.md`鐵律）。
- **用人名／案號／當事人查案** → `find_matter_by_party` / `list_matters`（見 `legal-admin/references/matter-query.md`）。
- **回報進度 / 建待辦 / 標書狀已遞交** → `create_task` / `update_task` / `mark_deadline_filed`。

### 第四步：標記訊息狀態

**每則訊息必須有結局：**
- 有回覆 → `reply` 會自動標記
- 不需回覆（貼圖、「OK」、「收到」、「👍」）→ `mark_read`
- 不確定 → 回覆「收到」

> **帶 `message_id` 精準標記**：`reply` / `reply_flex` / `mark_read` 都可帶 `message_id`＝你正在處理的那則訊息（從 `<channel>` tag 的 `message_id` 取得）。帶上後只標記那一則為已處理，**不會誤標同聊天室稍後到、你還沒處理的訊息**（同一人連發多則時尤其重要）。沒帶則退回 FIFO 標記最舊一筆 pending。

---

## 二、訊息類型處理

| 類型 | 處理 |
|------|------|
| 文字 | 正常處理 |
| [圖片] + 路徑 | Read tool 看圖 → 理解內容 → 處理（判決書／裁定照片 → 走 deadline-intake 抽取） |
| [語音] | 「目前僅支援文字訊息，請用打字的方式告訴我」 |
| [貼圖] | `mark_read`，不回覆 |
| [位置] | 記錄，如果跟任務相關就更新 |
| [檔案] | PDF → Read tool / pdf skill 查看（判決書／裁定 PDF → 走 deadline-intake）。其他 → 「已收到檔案」 |

### 圖片/檔案儲存路徑

LINE 用戶傳送的媒體會自動下載到本地：
- 圖片 → `data/media/line/images/{messageId}.jpg`
- 文件（PDF/Word）→ `data/media/line/files/{messageId}.{ext}`
- 影片/語音 → 暫不支援自動處理

收到 `[圖片] {路徑}` 時 → 用 Read tool 查看圖片內容（辨識判決書／裁定／開庭通知）
收到 `[檔案] {路徑}` 時 → 用 Read tool 或 pdf skill 處理

> **判決書／裁定／開庭通知是律所最常見的媒體**：收到後不要只回「已收到檔案」——進 `legal-admin/references/deadline-intake.md` 抽送達日 + 文書類型，推回**一鍵確認**。確認後才 `create_deadline`（人擋在中間、不全自動）。

---

## 三、群組管理

> **權威來源：規則「LINE 群組訊息路由」+「新群組登入 SOP」（導入時由 knowledge-capture 設定）**
> 本節是快速查閱版，完整決策樹與安全邊界請查：
> - `query_knowledge(question='LINE 群組訊息路由')`
> - `query_knowledge(question='新群組登入 SOP')`

### 系統層過濾（已實作）

LINE MCP server（`line-channel/server.ts`）已經：
- **1-on-1 DM**：100% 收進 business-db
- **群組訊息**：只有**被 @mention 的文字訊息**才會進 business-db，沒 @ 直接 `continue` 丟棄
- 被 @ 時自動把 `@AI` 字串從訊息剝掉，留純指令

**所以 business-db 收到的群組訊息 = 保證已經被人 @ 過 AI**

### 群組類型與 AI 行為（律所所內專用）

律所對內專用、沒有對外群（無客戶群 / 供應商群 / 行銷群）。群組僅限**所內工作群**：

| 類型 | 說明 | 回覆策略 |
|------|------|---------|
| `work` | 所內工作群（律師／助理／行政） | 主持律師白名單動作關鍵字觸發；其他所內人員 @AI 觸發；對外動作（對法院遞交確認等）永遠 HITL |
| `other` | 測試群 / 暫不分類 | **完全沉默**（即使被 @ 也不回），僅被動記錄 |

> `customer` / `supplier` / `marketing` 群類型在律所版**不使用**——所內專用無對外群。若某群混入非所內人員、視為非名冊用戶情境（不回業務內容、提示主持律師確認）。

### 主持律師白名單動作關鍵字
主持律師在 `work` 群直接發這些關鍵字不需 @AI 就觸發：
`幫我`、`查`、`找`、`建案`、`算時限`、`記`、`通知`、`建立`、`列出`、`更新`、`已遞交`、`核准`、`駁回`、`提醒`、`彙整`、`寄`、`傳送`

### 群組訊息處理決策樹

```
收到群組訊息（已保證被 @ 過）
  ↓
Step 1: list_line_groups 或查 line_groups 表
  ├─ 未登錄 → 走「新群組登入 SOP」（沉默 + 上報主持律師，見下方 SOP）
  └─ 已登錄 → Step 2

Step 2: 按 group_type
  ├─ other → 完全沉默（連 @ 也不回）
  ├─ work → Step 3

Step 3: 識別發訊者身份（依序查）
  1. lookup_employee(user_id) → 所內人員 → 按 permissions 執行
  2. 沒找到 → 非名冊用戶 → [紅旗] 上報主持律師（個人律所直接 reply；未來分層走 escalation / 全權限層、受限層別自撈 boss user_id）

Step 4: 需審核的動作走 HITL（對法院遞交確認、到期日確認）
```

> **「上報主持律師」的執行方式統一**：個人律所全權限單人 session 直接 reply 主持律師；未來分層時受限部門 session 走上報（escalation）機制 / 由全權限層處理，**不要自己撈 `role=boss` user_id 去 push**（與本檔第六節執行模型一致、見 CLAUDE.md〈上報（escalation）機制〉）。
>
> **Step 4 HITL**：「對法院遞交」「到期日確認」可走 `create_approval`；建立審核**當下**就會通知簽核人（escalation `approval_pending`）。gate 行為（`resume_params` 鎖定 / `consumed_at` 單次 / 過期）見 CLAUDE.md〈HITL gate 行為〉。核准後的執行流程見第六節。

### 新群組登入 SOP

> 以下「通知主持律師」的送達方式與決策樹、第六節一致：個人律所直接 DM 主持律師；未來分層時受限部門 session 走上報（escalation）/ 全權限層，不自撈 boss user_id（見 CLAUDE.md〈上報（escalation）機制〉）。

#### 情境 A：Bot 被加入新群組
LINE MCP 發 `event.type='join'` → AI 應：
1. 通知主持律師「Bot 被加入新群組 ...，要登錄嗎？」（個人律所直接 DM；未來分層走上報）
2. 主持律師回覆「登錄：類型 / 名稱 / 成員」→ `register_line_group()`
3. 主持律師回「忽略」→ 不登錄（下次該群組 @AI 走情境 B）

#### 情境 B：未登錄群組有人 @AI
1. **沉默不回**（絕對不在陌生群組發話）
2. 通知主持律師「未登錄群組有人 @AI，要登錄嗎？」（送達方式同情境 A）

#### 情境 C：主持律師主動預先登錄
主持律師在對話說「幫我登錄這個群組...」→ `register_line_group()`

### 群組工具速查
- `list_line_groups()` — 列出所有群組（顯示功能 + 備註）
- `list_line_groups(group_type='work')` — 只看工作群
- `register_line_group(group_id, group_name, group_type, channel_id, purpose, notes)` — 新增/更新群組
- `search_line_messages(query='關鍵字')` — 搜尋訊息（含 [群組] 標記）

### 群組欄位語意
- `group_type` — 分類（律所僅用 work / other）決定 AI 行為策略
- **`purpose`** — 一句話功能描述（例：「所內案件協調群」「庭期提醒群」）
- `notes` — 成員列表、特殊規則、備註等自由文字
- AI 處理群組訊息時應**讀 purpose + notes** 做為上下文補充

### 查詢群組

- `list_line_groups()` — 列出所有群組
- `list_line_groups(group_type='work')` — 只看工作群
- `search_line_messages(query='關鍵字')` — 搜尋群組訊息（結果含 [群組] 標記）

---

## 四、回覆語氣

| 對象 | 稱呼 | 語氣 |
|------|------|------|
| 主持律師 / 主管 (boss/manager) | 您 | 專業 |
| 律師 / 助理 / 行政 (staff) | 你 | 親切直接 |
| 非名冊用戶 | — | 不回業務內容（mark_read + 提示主持律師） |

---

## 五、LINE 訊息格式

### 文字訊息原則

- 一則不超過 200 字
- 重點放前面（手機螢幕小）
- 適當換行
- emoji 1-2 個就好

### Flex Message 使用場景

| 場景 | 用 Flex 的好處 |
|------|--------------|
| 任務指派 | 任務標題 + 截止日 + 負責人，一目了然 |
| 時限確認卡 | 送達日 + 文書類型 + 法定/內部雙期限，請律師一鍵確認 |
| 今日工作事項 | 當日到期時限 + 庭期，卡片格式 |
| 審核請求 | 內容摘要 + 「核准」/「駁回」提示 |

> **時限相關的 Flex 卡呈現**：抽取結果（送達日 / 文書類型 / **法定期限 + 內部期限雙日期**）+ 一鍵確認。**內部期限是用來盯的、法定期限是底線**——兩個都要顯示（見 `legal-admin/SKILL.md` 鐵律）。卡片上呈現的天數一律來自引擎 `calc_trace`、不可自行心算。

### 審核回覆機制

Phase 1 用文字回覆（不用 Postback 按鈕）：
- 主持律師收到審核通知 → 回覆「核准 #123」或「駁回 #123」
- Claude 解析 → `resolve_approval(approval_id=123, decision='approved', decided_by='主持律師')`
- **接續執行真正的 action**：從 approval.detail 取出 `resume_action` 與 `resume_params`，呼叫對應 tool（gate-backed：`approve_leave`；或 manual_ prefix 走人工多步驟），完成後 approval 才會被 consume（HITL gate 強制）
- **裸「核准」沒帶編號**：不要猜、不要隨便撈一筆 pending approval 套上去。先 `get_context_summary` / 查 waiting approvals：剛好一筆 → 回報「您是要核准 #N（內容…）嗎？」確認後再核；多筆 → 列出來問哪一筆；零筆 → 告知沒有待核項目。
- **簽核身份驗證（#24）**：`resolve_approval` 在非全權限層會驗操作者（須 verified manager 以上、且本人 LINE 操作）。被回「無權簽核」**不是系統錯誤**——是該操作者權限不足或非本人，照實回報、不要繞。（個人律所全權限單人不觸發此驗證。）
- **執行接續可能要換層（分層部署才相關）**：若你這層沒有該 `resume_action` 的工具，`resolve_approval` 仍會成功（核准是決策、不需執行工具），但「真正執行」要由**有該工具的層**或**原本建立審核的 session** 接手。此時回報「審核 #N 已核准，將由 {對應層} 執行」，不要假裝自己執行了。
- 詳細的 gate 行為、`resume_params` 一致性驗證、單次消費規則見 **CLAUDE.md HITL 章節**

### 執行模型：核准後一條龍（兩 session 拓樸）

上一段講「同一 session 收到回覆怎麼接續」。本段講**跨 session 分工**：發起 session 建審核、全權限層執行。**個人律所全權限單人時，發起與執行是同一個 session，下文兩 session 拓樸是分層 / 多人版的升級路；機制原樣保留。**

#### 1. in-session 上報通知的辨識（不要 reply）

當這個 session 收到的 channel 通知帶 `meta.event_type='escalation'`（如 `escalation_event='approval_pending'`）＝這是 **DB 主動推進來的「內部上報」**，不是 LINE 使用者傳來的訊息：

- 它**沒有要回覆的 `chat_id`**（不是某個聊天視窗）⇒ **不要對它做 `reply` / `reply_flex`**。
- 把它當成「已知有一筆待核准 #N、等主持律師核准」的通知，記在心裡、等下一步指示即可。
- 對比一般 LINE 訊息（有 `chat_id` / `user_id`、要走第一節辨識身份 + 結局）：上報通知是**系統事件**、不套那套流程。

> 律所最常見的上報來源是**時限提醒**（cron `scan_deadlines.py` 掃 pending 時限 → 命中提醒節點 / 逾期即 enqueue_escalation、全所一份，見 `legal-admin/SKILL.md`〈安全執行模型〉、`legal-admin/references/daily-digest.md`）與**建立審核當下**（`approval_pending`）。提醒只通知、不擋動作。

#### 2. 兩 session 拓樸

- **發起/建審核的 session**：依情境用 `create_approval`（如「對法院遞交確認」「到期日確認」走 HITL）。
- **執行的 session**：真正執行 `resume_action` 的地方**必須有對應工具**——一個 floor 有沒有某工具取決於 floor-map（見 CLAUDE.md〈部門安全層（floor）〉）。個人律所全權限單人＝同一 session 全有；分層部署則需路由到有該工具的層。
- ⇒ 核准後的執行要落在「有對應工具」的 session。最穩的是 `confidential` 全權限層（主持律師所在、見第 4 點路由）。

#### 3. LINE 回「核准 #N」→ 全權限 session 一條龍

主持律師在 LINE 回「核准 #N」會被路由進**全權限 session**（因 sender 是全權限主體、見第 4 點）。全權限 session 收到後依序執行：

1. `resolve_approval(approval_id=N, decision='approved', decided_by='主持律師')` — 先把審核設成核准。
2. `get_approval(approval_id=N)` — 從輸出的 `detail` 取出 `resume_params`（**照抄原始值、不要重打**）。
3. 呼叫對應 gate-backed 工具，**帶 approval 的原始 `resume_params` + `approved_id=N`**（approval 綁定參數名 = `approved_id`，整數、就是 N）。
4. 成功後 `reply` 主持律師 LINE：「已核准 #N 並完成 {動作}」。

**先後順序（必守）**：一定要**先 `resolve_approval(approved)`、後帶 `approved_id` 呼叫工具**。gate 只認「已核准且未使用」的 approval；順序顛倒或漏 resolve 會被回 `ERROR: 審核 #N 不存在、未核准或已使用`。

**務必用原始 `resume_params`**：執行時欄位值照 `get_approval` 取出的填，**不可從對話脈絡重新推導金額 / ID**——HITL gate 會一字不差比對關鍵欄位（型別敏感），對不上直接擋下。此為交叉引用，演算法細節見 **CLAUDE.md「HITL gate 行為」**。

#### 4. 身份路由：主持律師 / admin 訊息落進全權限 session

主持律師 / admin 的 LINE 訊息會落進**全權限 session**——line-channel 依 sender 身份把 `target_floor` 設為 `confidential`。因此要讓主持律師收到 in-session 上報推送、並完成「核准 → 執行 → 回覆」閉環，分層部署下**必須有一個 `SME_FLOOR=confidential` 的 session 在跑**；沒有這層，核准訊息無處落地、閉環斷裂。**個人律所不設 `SME_FLOOR`、單一全權限 session 即包辦發起 + 執行 + 回覆，本點為升級路。**

---

## 六、防騷擾規則

- 同一人 1 小時內不主動推超過 5 則
- 所內人員問問題的回覆不算限制
- 晚上 10 點到早上 8 點不主動推送（除非緊急——逾期時限提醒屬緊急）

> 律所對內專用、**無對外行銷 / 廣播**（已移出產品，見 SPEC.md〈不做〉）。不存在「對外文案要核准才發」這條路徑。

---

## 七、LINE 訊息歷史查詢

所有 LINE 收發訊息都自動存入 `line_messages` 表。用 `search_line_messages` 查詢：

### 常見查詢

| 使用者說 | 怎麼查 |
|---------|--------|
| 「林律師上週傳了什麼」 | `search_line_messages(user_name='林', days=7)` |
| 「最近有誰提到上訴」 | `search_line_messages(query='上訴')` |
| 「今天收到幾則 LINE」 | `search_line_messages(direction='inbound', days=1)` |
| 「我們回了什麼給陳助理」 | `search_line_messages(user_name='陳', direction='outbound')` |
| 「群組裡最近的討論」 | `search_line_messages(days=3)` 然後過濾 [群組] 標記 |

### 參數

- `query` — 關鍵字（模糊搜尋訊息內容）
- `user_id` — 精確比對 LINE user ID
- `user_name` — 模糊比對暱稱
- `direction` — `inbound`（收到）/ `outbound`（發出）/ 留空=全部
- `days` — 最近幾天（預設 7）
- `limit` — 最多幾則（預設 30）

---

## 八、LINE OA 額度管理

免費方案每月 200 則 push message。

| 額度使用率 | 建議 |
|-----------|------|
| < 50% | 正常使用 |
| 50-80% | 減少非必要推送 |
| > 80% | 警告主持律師，建議升級 |

額度追蹤方式：
- 系統目前無法自動查詢 LINE 額度（LINE MCP 尚未支援 quota API）
- `get_context_summary` 有推送用量摘要可參考；**系統目前未自動排程「月初額度檢查」提醒**。需檢查時由 agent 在啟動流程 / 對話中提醒主持律師「建議到 LINE Official Account Manager 後台檢查本月訊息額度」，或建一筆 task 做人工 follow-up（待實作自動月檢）
- 日常優先使用 `reply`（回覆訊息不計入 push 額度），減少主動 push

> 律所主動推送主要是**每日「今日工作事項」彙整**（全所一份）+ **時限提醒**，量小；不存在對外群發。

---

## Do's and Don'ts

### Do
- 每則 LINE 訊息處理完都要有結局：`reply` 或 `mark_read`
- 回覆前先辨識身份：`lookup_employee`（員工 → 處理；非名冊 → mark_read + 提示主持律師）
- 回覆時傳入正確的 `channel_id`（從哪個 OA 收到就用哪個 OA 回）
- 所有對外發送都 `log_interaction`
- 判決書／裁定／開庭通知 → 走 deadline-intake 抽取、推一鍵確認（**絕不心算時限天數**）
- LINE 訊息不超過 200 字，重點放前面

### Don't
- 不要回覆非名冊用戶的業務內容（mark_read + 提示主持律師確認是否新進需建檔）
- **不要在 LINE 上跟委任人開對話 / 做法律問答 / 約諮詢**（約諮詢只走電話由行政人工建，見 consultation.md）
- 不要對同一人 1 小時內推超過 5 則
- 不要在晚上 10 點到早上 8 點主動推送（除非緊急）
- 不要在未辨識身份的情況下執行操作
- **不要自己心算法定時限天數**——一律由引擎 `create_deadline` 確定性計算附 `statutory_basis`（反捏造、算錯＝執業過失）

## 快速參考

### 辨識身份 + 回覆
1. `lookup_employee(name_or_line_id=user_id)` — 是所內人員？
2. 是 → 處理請求 → `reply(channel_id=channel_id, chat_id=chat_id, text='回覆內容')`
3. 不是（非名冊）→ `mark_read(channel_id=channel_id, chat_id=chat_id)` + reply / 上報主持律師「有未識別 LINE 用戶，請確認是否新進需建檔綁定」

### 收到判決書／裁定／開庭通知
1. Read / pdf skill 看檔 → 走 `legal-admin/references/deadline-intake.md` 抽送達日 + 文書類型
2. `stage_deadline_intake` 暫存（只存事實、不算天數）→ 推回 LINE **一鍵確認卡**
3. 人確認後 → `create_deadline(confirm_intake_id=N)` 確定性算雙日期 + `statutory_basis`
4. `mark_read` / `reply` 給結局

---

## 九、注意事項

- LINE 是所內人員最常用的介面，回覆要快、要準、要簡短
- 不確定的事不要回，轉給主持律師
- 每則訊息處理完都要標記狀態
- 所有對外發送（非回覆所內人員問題的）都 log_interaction

---

## 多 LINE OA 注意事項

> **單一律所通常只有一個 LINE OA**；`business_unit` 多事業體機制在律所版**退化、留空 inert**（見 CLAUDE.md〈多事業體支援〉、SPEC.md〈退化〉）。下文是 OA 識別 / 回覆的通用契約，律所單 OA 時 `business_unit` 一律留空。

### 識別來源

每則 LINE 訊息的 meta 帶有 `channel_id`、`channel_name`（律所單所時 `business_unit` 留空）：
- `channel_id` = 設定檔中的 key
- `channel_name` = OA 顯示名稱

### 回覆規則

- **回覆時必須傳入正確的 `channel_id`**：`reply(channel_id='...', chat_id='U...', text='...')`
- 從哪個 OA 收到訊息，就用哪個 OA 回覆
- 省略 `channel_id` 時使用預設 channel

### 查詢 OA 清單

`list_channels` 列出所有已設定的 LINE OA 及其 channel_id。

### 搜尋歷史訊息

`search_line_messages(channel_id='...')` 可按 OA 篩選訊息歷史。

### 通知頻道注意事項

通知主持律師時，LINE push 只對「已加入該 OA 好友」的使用者有效。LINE push 靜默失敗無錯誤回傳——**預防比修復重要**：導入時確認主持律師已加入 LINE OA 為好友。多 OA 環境（少見）可用 `list_channels()` 對每個 OA 測試推送、未加入則在 dashboard 提醒。
