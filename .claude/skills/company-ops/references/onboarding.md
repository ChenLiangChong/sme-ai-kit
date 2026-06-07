# 人員到職 / 離職專業指南（律師事務所版）

## 觸發情境

「新人報到」「加入新進律師 / 助理」「幫 XXX 開帳號」「有人離職」「離所交接」

> 本所為**單一律師事務所、所內專用**。本檔講事務所人員（律師 / 助理 / 行政）的到職、LINE 綁定、離職交接。橫向基建（任務 / 知識 / LINE）沿用本技能包對應模組；案件與時限沿用 legal-admin。

## 角色措辭對照（呈現層 → 底層 enum）

底層 `employees.role` / `permissions` enum **不變**（`staff` / `manager` / `admin`），只在跟人溝通時換律所措辭：

| 律所職稱（呈現） | `role`（底層不變） | 建議 `permissions`（底層不變） |
|------|------|------|
| 律師（attorney）/ 受僱律師 | `manager`（資深、可帶案 / 簽核）或 `staff`（依授權） | `manager` |
| 助理（paralegal）/ 法務助理 | `staff` | `basic` |
| 行政（admin_staff）/ 行政秘書 | `staff` | `basic` |
| 主持律師 / 所長（boss） | `manager` | `admin` |

> 「主持律師 / 所長」是本所最高決策者（對應通用文件的 boss）。`role` / `permissions` 的選擇由主持律師拍板、agent 不替他決定（見下方 Don't）。

## 權限

`update_employee` 需 `admin`（#10 已落實 `_check_permission` admin-gate + audit 具名）；`register_employee`（建新員工）仍未以 `permissions` enforce、靠 floor gate 硬牆（人事 / HR 工具在 floored 層被物理移除）。floored session 的 actor 由系統取 verified `user_id`（agent 自填無效）；operator（無 floor）為全權限路徑。`permissions` 同時也是業務層的軟分流 / 上報判斷用。

人事操作（`register_employee` / `update_employee` / LINE 綁定）屬**員工機密 + HR 工具**：floored 受限業務層被 floor gate 物理移除這組工具（見 CLAUDE.md〈部門安全層（floor）與兩道牆〉），在那層**呼不到屬正常、不是系統壞掉**。新人報到 / 離職 / 綁定一律在全權限層（`SME_FLOOR=''` 或 `confidential`）執行；受限層辨識到「這是人事異動」時，依 line-comms.md 第六節「執行模型」交給全權限層處理，不要自己嘗試 `register_employee` / `update_employee`。

> **個人律所通常不設 `SME_FLOOR`**（全權限單人、看全部、沒有對內隱藏對象）；此時上述 floor gate 機制保留為 inert（全權限下永遠可用、零成本），待增助理 / 多人版再啟用。多人所或需對內隱藏（如行政不看律師人事）時才分層。機制本身領域無關、原樣適用（見 CLAUDE.md〈部門安全層（floor）〉、SKILL〈安全執行模型〉）。

---

## 一、新增人員

### 資訊收集

問清楚：
- 姓名（必填）
- 角色：staff / manager（必填；律師通常 `manager`、助理 / 行政 `staff`，見上方〈角色措辭對照〉）
- 部門 / 組別（建議填；如「訴訟組」「非訟組」「行政」）
- 權限：basic / manager / admin（必填，預設依角色：staff→basic, manager→manager）
- 電話（建議填）
- LINE user ID（稍後綁定）

### 執行

```
register_employee(name=姓名, role='staff', department=組別,
                  line_user_id=LINE用戶ID, permissions='basic',
                  phone=電話, business_units='留空=不分事業體')
```
> 用 keyword 帶參數：tool 的位置順序是 `name, role, department, line_user_id, permissions, phone, business_units`（第 4 個是 `line_user_id`、不是 permissions——位置帶錯會把權限值塞進 LINE ID 欄）。
>
> 單一律所**不分事業體**，`business_units` 一律留空（inert）。

### 假期配額分配（選用 — 律所有正式請假制度時）

`register_employee` 成功後、若 `leave_types` 表已有資料（律所有登記假別）：

1. 詢問主持律師：「{律師 / 助理} 到職日是 {日期}，要怎麼配年度配額？」
2. 常用算法：
   - 1/1 到職 → 給全年配額（如特休 14 天）
   - 年中到職 → 按比例（剩餘月數 / 12 × 全年配額）四捨五入
3. 逐一 `set_leave_balance(employee_id, leave_type_code, year, allocated_days)` 配每一種假別

> **注意（反捏造·法律版）**：此處 `leave_types` / `leave_balances` 的 `days` 是**事務所內部請假天數**，與任何**法定時限天數零關係**。法定時限（上訴 / 抗告 / 答辯…）一律由 legal-admin 引擎 `create_deadline` 確定性計算並附 `statutory_basis`，**不在這裡、絕不心算**。

若 `leave_types` 表是空的（律所還沒走 knowledge-capture Step 2a），跳過此步、提示主持律師「之後若要管請假、可走 leave-ops 設定」。

> 詳細請假流程見 **`leave-ops.md`**。

---

## 二、LINE 綁定

### 自動綁定流程

人員加入所內 LINE OA 後傳「我是 XXX」：

1. Channel 收到訊息 → Claude 觸發 line-comms 流程
2. `lookup_employee(訊息中的名字)` 搜尋
3. 找到且 line_user_id 為空 → 詢問確認：「你是 {組別} 的 {名字} 嗎？」
4. 對方確認 → 用 `update_employee` 綁定 LINE ID：
   `update_employee(employee_id=員工ID, line_user_id='Uxxxx')`
5. 回覆：「綁定成功！」→ 發送歡迎訊息

> 本所 LINE OA 僅供所內律師 / 助理 / 行政使用（內部專用、不接委任人對話）。

### 同名處理

如果有多人同名：
- 列出所有同名人員（含組別）
- 讓對方選：「請問你是哪一位？1. 訴訟組的 王曉明 2. 非訟組的 王曉明」

### 綁定失敗處理

- 名字不在人員名冊 → 走 line-comms 的未知來源流程（通知主持律師）
- 已經被別人綁過 → 「這個帳號已綁定到 {其他人}，請聯繫主持律師」

---

## 三、歡迎訊息

綁定成功後由 agent 立即發送（onboarding 流程當下的 agent 動作、非背景排程）：

```
歡迎加入 {事務所名稱}！

你可以在這裡：
查案件 → 傳「{當事人名 / 案號}的案子」
查時限 → 傳「最近有哪些時限到期」
回報書狀 → 傳「#時限編號 已遞交」
看狀態 → 傳「今天有什麼事」

要算上訴 / 抗告 / 答辯期限時，把判決書 / 裁定 / 開庭通知拍照或 PDF 傳進來，我會算出法定期限 + 內部期限（一律附法條依據、不心算）。有問題隨時問我！
```

> 算時限的完整流程見 legal-admin 的 `deadline-intake.md`；查案件見 `matter-query.md`。

---

## 四、首週訓練任務

由 agent 建立（onboarding 流程當下、非系統背景排程）：
```
create_task(
  title='新人訓練 - {姓名}',
  description='完成以下項目：
1. 了解事務所基本規則 / SOP（問 AI「事務所規定」）
2. 熟悉 LINE 常用指令
3. 完成第一次案件查詢（人名 / 案號查案）
4. 完成第一次時限收件（傳一份裁定 / 通知試算期限並一鍵確認）
5. 完成第一次書狀進度回報',
  assignee=姓名,
  priority='normal',
  due_date='<一週後 YYYY-MM-DD>'
)
```

> 此 `create_task` 的 `due_date` 是**內部待辦到期日**，與法定時限無關（法定時限走 `create_deadline`）。

---

## 五、分階段引導

### Day 1：基礎

- [x] 帳號建立 + LINE 綁定
- [ ] （選用）分配年度假期配額（`leave_types` 已登記時）
- [ ] 發送歡迎訊息
- [ ] 建立訓練任務
- [ ] 介紹基本 LINE 指令（查案件 / 查時限 / 回報書狀）

### Day 2-3：熟悉

人員第一次用 LINE 問問題時，耐心引導：
- 如果問的東西在知識庫有答案 → 回答 + 「以後你可以直接問我這類問題」
- 如果問的東西沒有 → 「這個我不確定，建議問 {主持律師 / 帶案律師}」
- **法律實質問題不臆測**：涉及法律見解 / 答辯策略的，引導去問主持律師 / 帶案律師，agent 只做行政（不做法律問答、不代寫實質內容）。

### Day 4-7：獨立

- 追蹤訓練任務進度
- Day 5（靠 task 提醒 / agent 在啟動流程追蹤、**非系統自動**）：主動問「新人訓練還順利嗎？有沒有什麼不清楚的？」
- 訓練任務到期前：agent 在啟動流程看到該 task 到期提示時提醒主持律師「{姓名} 的新人訓練任務即將到期」

> 系統**無 Day-N 排程器**會自己在第 5 / 7 天觸發——以上靠 `create_task` 排提醒 + agent 在啟動流程 / 收到到期提示時人工 follow-up。（注意：legal-admin 的 `scan_deadlines.py` 等 cron 只盯**法定時限**、不盯這種訓練待辦。）

---

## 六、離職處理（在手案件 + 未結時限交接）

當主持律師說「XXX 離職了」「XXX 不做了」：

> **離所交接是本所最高風險的人事動作**：離職律師 / 助理名下的**在手案件**與**未結時限**若沒轉給接手的人，會變成**沒人盯的時限 → 時限失聯 → 執業過失**。停用帳號**之前**，必須先把案件與時限交接完。

### 步驟

1. **確認身份和權限**（流程上由 admin / manager 操作；系統目前未以 employee `permissions` enforce、真正硬牆是 floor gate——見開頭〈權限〉）
2. **列出該人員的在手案件**（交接給接手律師）：
   ```
   list_matters(status='open', lead_attorney=姓名)
   ```
   > ⚠️ **系統目前無 `update_matter` 工具改主辦律師欄**（matters 模組只有 `create_matter` / `list_matters` / `get_matter` / `find_matter_by_party`）。所以「改主辦」**無法靠單一 tool 完成**：逐案以 `store_fact(category='hr', title='案件交接-{案號}', content='{案號} 由 {離職者} 轉 {接手律師}', confidential=True)` 記錄 + `create_task(assignee=接手律師, title='承接案件 {案號}')` 讓接手律師逐案承接 + **在事務所實體案件管理（或 pleading-manager）改主辦**。**絕不可宣稱系統已自動改主辦。**
3. **列出該人員名下未結的時限**（最關鍵、漏一筆＝執業過失）：
   ```
   list_deadlines(assignee=姓名, status='pending')   # 該人員承辦、未結
   list_upcoming_deadlines(within_days=60)            # 對照近期到期、確認沒漏
   ```
   把每一筆未結時限明確交給接手律師承接、並在 LINE 跟接手律師確認收到。> ⚠️ **時限同樣無「重指派承辦人」的單一 tool**：以 `store_fact` 記錄交接 + `create_task(assignee=接手律師)` 逐筆承接 + LINE 確認收到。**時限日期本身不要重算、不要動**（日期填錯才走 legal-admin 的 `amend_deadline` 確定性重算，絕不在這裡心算）。
4. **列出未完成的內部任務**並轉移：
   ```
   list_tasks(assignee=姓名, status='pending')
   list_tasks(assignee=姓名, status='in_progress')
   ```
   問主持律師：「{姓名} 還有 {N} 項未完成任務 + {M} 件在手案件 + {K} 筆未結時限，分別轉移給誰？」→ **任務可逐一 `update_task(task_id, assignee=新負責人)` 重指派**；案件 / 時限無重指派 tool、走上面 step 2/3 的 `store_fact` 記錄 + `create_task` + 人工。
5. **停用帳號 + 解綁 LINE**（**不可逆 / 敏感動作、務必在案件與時限都交接完之後**：清權限 + 標離職；`permissions` / `active` 變更會觸發上報 `employee_permissions_changed`，見 CLAUDE.md〈上報（escalation）機制〉）：
   ```
   update_employee(
     employee_id=員工ID,
     line_user_id='',       // 清除 LINE 綁定
     permissions='none',    // 移除所有權限
     active=0,              // 標記為離職
     notes='離職日期：{日期}，原因：{原因}'
   )
   ```
   > **actor 與硬牆**：人事 / HR 工具（含 `update_employee`）本就只在全權限層可用（見上方〈權限〉）＝這裡的硬牆。`update_employee` 現需 `admin`（#10 已落實 admin-gate）且 audit log 記 verified 操作者名（不再 `actor='system'`）；floored 非 admin / 未驗證身份會被擋、operator（無 floor）為全權限路徑。可信身份機制見 CLAUDE.md〈actor 身份信任〉。
6. **記錄** → `store_fact(category='hr', title='離職記錄-{姓名}', content='離職日期：{日期}，原因：{原因}，在手案件已轉 {接手律師}、未結時限已交接、任務已轉移、已解綁 LINE、已停用帳號')`
7. **leave_balances 保留**：不要刪該人員的 `leave_balances` row（用於離職結算 / 補薪計算）。`leave_requests` 在員工被刪時透過 `ON DELETE SET NULL` 保留紀錄，所以離職用 `active=0` 而非 DELETE 就足夠
8. **回報完成**（明確列出：轉了哪幾件案、哪幾筆時限、給了誰）

### 知識轉移

如果離職的是資深律師 / 帶案多年的助理：
- 提醒主持律師：「{姓名} 可能有一些未文件化的見解 / 案件脈絡 / 慣用流程，要不要在他離開前做一次訪談？」
- 如果要 → 啟動 knowledge-capture 的主動訪談流程（見 `knowledge-capture.md`）
- 機密見解 / 策略類 `store_fact(confidential=True)`（見 CLAUDE.md〈機密軸（confidential）〉）

---

## Do's and Don'ts

### Do
- 確認操作者有 admin 或 manager 權限才執行
- **離職前先交接在手案件 + 未結時限**，確認接手律師收到，再停用帳號
- 離職用 `update_employee(active=0)` 停用，不要刪除紀錄
- 所有操作記 `log_interaction`
- 新人第一週回覆更詳細耐心
- 資深律師離職前提醒主持律師做知識轉移訪談

### Don't
- 不要代替主持律師決定新人的角色和權限（問清楚）
- 不要刪除離職人員紀錄（用 active=0）
- 不要讓 basic 權限的人操作人事異動
- 不要跳過 LINE 綁定確認步驟
- **不要在離職交接時心算或變更法定時限日期**（只調承辦；日期錯誤走 legal-admin `amend_deadline`）
- 不要在案件 / 時限尚未交接完就停用離職人員帳號（會造成時限失聯）

## 快速參考

### 新人報到完整流程
1. `register_employee(name='[姓名]', role='staff', department='訴訟組', permissions='basic', phone='[手機號碼]')`（律師通常 `role='manager'` / `permissions='manager'`）
2. 請新人傳訊息到所內 LINE OA → `lookup_employee(name_or_line_id='[姓名]')` → `update_employee(employee_id=ID, line_user_id='Uxxxx')`
3. `reply(channel_id=新人傳綁定訊息進來的 channel_id, chat_id='Uxxxx', text='歡迎加入！')`（回同一個收到訊息的 OA、不要寫死 `default`、見 line-comms 通知頻道選擇）
4. `create_task(title='新人訓練 - [姓名]', assignee='[姓名]', due_date='<一週後 YYYY-MM-DD>', category='admin')`（日期傳實際 `YYYY-MM-DD`、工具不解析「一週後」）

### 離職處理
1. `list_matters(status='open', lead_attorney='離職人員')` — 查在手案件（轉接手律師）
2. `list_deadlines(...)` / `list_upcoming_deadlines(within_days=60)` — 查未結時限（逐筆交接、不動日期）
3. `list_tasks(assignee='離職人員', status='pending')` — 查未完成任務
4. 問主持律師案件 / 時限 / 任務各轉給誰 → 任務 `update_task(task_id=ID, assignee='新負責人')`；**案件 / 時限無重指派 tool**＝`store_fact` 記錄交接 + `create_task` 給接手律師 + 人工（實體案件管理 / pleading-manager）改主辦
5. `update_employee(employee_id=ID, line_user_id='', permissions='none', active=0, notes='離職日期...')`（**在 1-4 都交接完之後**）

---

## 七、注意事項

- 離職不刪除紀錄，用 `update_employee(active=0)` 停用，`list_employees(active_only=True)` 會自動過濾
- 離職務必先轉移**在手案件 + 未結時限**再停用帳號（漏轉移＝時限失聯＝執業過失）
- LINE 綁定用自然語言比對，不用綁定碼
- 所有操作記 interaction_log
- 新人第一週多包容，回覆更詳細
- 法定時限一律由 legal-admin 引擎確定性計算附法條依據，本檔的 task / leave `days` 與法定時限天數無關
