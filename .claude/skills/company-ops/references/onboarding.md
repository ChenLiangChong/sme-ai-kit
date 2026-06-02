# 新人導引專業指南

## 觸發情境

「新人報到」「加入新員工」「幫 XXX 開帳號」「有人離職」

## 權限

`update_employee` 需 `admin`（#10 已落實 `_check_permission` admin-gate + audit 具名）；`register_employee`（建新員工）仍未以 `permissions` enforce、靠 floor gate 硬牆（人事 / HR 工具在 floored 層被物理移除）。floored session 的 actor 由系統取 verified `user_id`（agent 自填無效）；operator（無 floor）為全權限路徑。`permissions` 同時也是業務層的軟分流 / 上報判斷用。

人事操作（`register_employee` / `update_employee` / LINE 綁定）屬**員工機密 + HR 工具**：floored 受限業務層被 floor gate 物理移除這組工具（見 CLAUDE.md〈部門安全層（floor）與兩道牆〉），在那層**呼不到屬正常、不是系統壞掉**。新人報到 / 離職 / 綁定一律在全權限層（`SME_FLOOR=''` 或 `confidential`）執行；受限層辨識到「這是人事異動」時，依 line-comms.md 第六節「執行模型」交給全權限層處理，不要自己嘗試 `register_employee` / `update_employee`。

---

## 一、新增員工

### 資訊收集

問清楚：
- 姓名（必填）
- 角色：staff / manager（必填）
- 部門（建議填）
- 權限：basic / manager / admin（必填，預設依角色：staff→basic, manager→manager）
- 電話（建議填）
- LINE user ID（稍後綁定）

### 執行

```
register_employee(name=姓名, role='staff', department=部門,
                  line_user_id=LINE用戶ID, permissions='basic',
                  phone=電話, business_units='留空=全部事業體')
```
> 用 keyword 帶參數：tool 的位置順序是 `name, role, department, line_user_id, permissions, phone, business_units`（第 4 個是 `line_user_id`、不是 permissions——位置帶錯會把權限值塞進 LINE ID 欄）。

### 假期配額分配（選用 — 公司有正式請假制度時）

`register_employee` 成功後、若 `leave_types` 表已有資料（公司有登記假別）：

1. 詢問老闆：「{員工} 到職日是 {日期}，要怎麼配年度配額？」
2. 常用算法：
   - 1/1 到職 → 給全年配額（如特休 14 天）
   - 年中到職 → 按比例（剩餘月數 / 12 × 全年配額）四捨五入
3. 逐一 `set_leave_balance(employee_id, leave_type_code, year, allocated_days)` 配每一種假別

若 `leave_types` 表是空的（公司還沒走 knowledge-capture Step 2a），跳過此步、提示老闆「之後若要管請假、可走 leave-ops 設定」。

> 詳細請假流程見 **`leave-ops.md`**。

---

## 二、LINE 綁定

### 自動綁定流程

員工加入 LINE OA 後傳「我是 XXX」：

1. Channel 收到訊息 → Claude 觸發 line-comms 流程
2. `lookup_employee(訊息中的名字)` 搜尋
3. 找到且 line_user_id 為空 → 詢問確認：「你是 {部門} 的 {名字} 嗎？」
4. 員工確認 → 用 `update_employee` 綁定 LINE ID：
   `update_employee(employee_id=員工ID, line_user_id='Uxxxx')`
5. 回覆：「綁定成功！」→ 發送歡迎訊息

### 同名處理

如果有多人同名：
- 列出所有同名員工（含部門）
- 讓員工選：「請問你是哪一位？1. 倉庫的員工甲 2. 門市的員工甲」

### 綁定失敗處理

- 名字不在員工名冊 → 走陌生人流程（通知老闆）
- 已經被別人綁過 → 「這個帳號已綁定到 {其他人}，請聯繫主管」

---

## 三、歡迎訊息

綁定成功後由 agent 立即發送（onboarding 流程當下的 agent 動作、非背景排程）：

```
歡迎加入 {公司名稱}！🎉

你可以在這裡：
📝 查待辦 → 傳「我的任務」
📦 查庫存 → 傳「查庫存 + 品名」
✅ 回報進度 → 傳「#任務編號 做完了」
📊 看狀態 → 傳「今天有什麼事」

有問題隨時問我！
```

---

## 四、首週訓練任務

由 agent 建立（onboarding 流程當下、非系統背景排程）：
```
create_task(
  title='新人訓練 - {姓名}',
  description='完成以下項目：
1. 了解公司基本規則（問 AI「公司規定」）
2. 熟悉 LINE 常用指令
3. 完成第一次庫存查詢
4. 完成第一次任務回報
5. 閱讀部門相關 SOP',
  assignee=姓名,
  priority='normal',
  due_date='<一週後 YYYY-MM-DD>'
)
```

---

## 五、分階段引導

### Day 1：基礎

- [x] 帳號建立 + LINE 綁定
- [ ] （選用）分配年度假期配額（`leave_types` 已登記時）
- [ ] 發送歡迎訊息
- [ ] 建立訓練任務
- [ ] 介紹基本 LINE 指令

### Day 2-3：熟悉

員工第一次用 LINE 問問題時，耐心引導：
- 如果問的東西在知識庫有答案 → 回答 + 「以後你可以直接問我這類問題」
- 如果問的東西沒有 → 「這個我不確定，建議問 {主管名}」

### Day 4-7：獨立

- 追蹤訓練任務進度
- Day 5（靠 task 提醒 / agent 在啟動流程追蹤、**非系統自動**）：主動問「新人訓練還順利嗎？有沒有什麼不清楚的？」
- 訓練任務到期前：agent 在啟動流程看到該 task 到期提示時提醒主管「{姓名} 的新人訓練任務即將到期」

> 系統**無 Day-N 排程器**會自己在第 5 / 7 天觸發——以上靠 `create_task` 排提醒 + agent 在啟動流程 / 收到到期提示時人工 follow-up（同 order-ops 售後關懷模式）。

---

## 六、離職處理

當老闆說「XXX 離職了」「XXX 不做了」：

### 步驟

1. **確認身份和權限**（流程上由 admin / manager 操作；系統目前未以 employee `permissions` enforce、真正硬牆是 floor gate——見開頭〈權限〉）
2. **列出該員工的未完成任務**：
   ```
   list_tasks(assignee=姓名, status='pending')
   list_tasks(assignee=姓名, status='in_progress')
   ```
3. **問老闆**：「{姓名} 還有 {N} 項未完成任務，要轉移給誰？」
4. **轉移任務** → 逐一 `update_task(task_id, assignee=新負責人)`
5. **停用帳號 + 解綁 LINE**（**不可逆 / 敏感動作**：清權限 + 標離職；`permissions` / `active` 變更會觸發上報 `employee_permissions_changed`，見 CLAUDE.md〈上報（escalation）機制〉）：
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
6. **記錄** → `store_fact(category='hr', title='離職記錄-{姓名}', content='離職日期：{日期}，原因：{原因}，已轉移任務、解綁LINE、停用帳號')`
7. **leave_balances 保留**：不要刪該員工的 `leave_balances` row（用於離職結算 / 補薪計算）。`leave_requests` 在員工被刪時透過 `ON DELETE SET NULL` 保留紀錄，所以離職用 `active=0` 而非 DELETE 就足夠
8. **回報完成**

### 知識轉移

如果離職的是資深員工：
- 提醒老闆：「{姓名} 可能有一些未文件化的知識，要不要在他離開前做一次訪談？」
- 如果要 → 啟動 knowledge-capture 的主動訪談流程

---

## Do's and Don'ts

### Do
- 確認操作者有 admin 或 manager 權限才執行
- 離職用 `update_employee(active=0)` 停用，不要刪除紀錄
- 所有操作記 `log_interaction`
- 新人第一週回覆更詳細耐心
- 資深員工離職前提醒老闆做知識轉移訪談

### Don't
- 不要代替老闆決定新人的角色和權限（問清楚）
- 不要刪除離職員工紀錄（用 active=0）
- 不要讓 basic 權限的人操作人事異動
- 不要跳過 LINE 綁定確認步驟

## 快速參考

### 新人報到完整流程
1. `register_employee(name='[員工姓名]', role='staff', department='倉庫', permissions='basic', phone='[手機號碼]')`
2. 請新人傳訊息到 LINE OA → `lookup_employee(name_or_line_id='[員工姓名]')` → `update_employee(employee_id=ID, line_user_id='Uxxxx')`
3. `reply(channel_id=新人傳綁定訊息進來的 channel_id, chat_id='Uxxxx', text='歡迎加入！')`（回同一個收到訊息的 OA、不要寫死 `default`、見 line-comms 通知頻道選擇）
4. `create_task(title='新人訓練 - [員工姓名]', assignee='[員工姓名]', due_date='<一週後 YYYY-MM-DD>', category='admin')`（日期傳實際 `YYYY-MM-DD`、工具不解析「一週後」）

### 離職處理
1. `list_tasks(assignee='離職員工', status='pending')` — 查未完成任務
2. 問老闆任務轉移給誰 → 逐一 `update_task(task_id=ID, assignee='新負責人')`
3. `update_employee(employee_id=ID, line_user_id='', permissions='none', active=0, notes='離職日期...')`

---

## 七、注意事項

- 離職不刪除紀錄，用 `update_employee(active=0)` 停用，`list_employees(active_only=True)` 會自動過濾
- LINE 綁定用自然語言比對，不用綁定碼
- 所有操作記 interaction_log
- 新人第一週多包容，回覆更詳細
