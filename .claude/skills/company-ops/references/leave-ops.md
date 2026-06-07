# 請假管理專業指南（律師事務所 — 所內人事）

> **適用範圍**：本檔處理**事務所內部人事請假**（律師 / 助理 / 行政人員的特休、病假、事假等）。這是「人事休假」、**不是**任何法定 / 訴訟期間。

## ⚠️ 硬邊界（與 task-ops 對稱、務必先讀）

**`leave_requests.days` ＝人事休假天數（一個人請幾天假）、與任何法定 / 訴訟期間天數零關係。**

- 本檔的「天數」永遠是「員工請幾天假」的人事概念。**本檔不得出現上訴期 / 抗告期 / 答辯 / 補正 / 在途期間 / 末日順延 / 送達日 等字眼**——那些是 legal-admin 時限引擎的事、與請假無關。
- 法定時限永遠由 **legal-admin** 的 `create_deadline` 確定性計算、附 `statutory_basis`（見 `.claude/skills/legal-admin/SKILL.md`、`.claude/skills/legal-admin/references/deadline-intake.md`）。**請假天數絕不可拿去算或對照任何法定期間**，反之亦然。
- 同理 `task` 的 `due_date` / `leave` 的 `days` 都是行政內部期日 / 天數，**和訴訟時限是兩套互不相干的東西**（與 task-ops 的硬邊界對稱）。若有人在 LINE 把「我下週請特休 3 天」和「這件上訴剩幾天」混在一句話講，請**分流**：請假走本檔、時限走 legal-admin、兩者天數不互相代入。

## 觸發情境

律師 / 助理 / 行政人員或主持律師（所長）說：「我下週要請特休」「想請病假」「特休還剩幾天」「{某律師} 申請的假准了沒」「核准 / 駁回 #M」（所長簽核審核 ID）「取消我的請假」「年初幫大家配特休」「事務所要登記新假別」

## ID 命名約定（重要、整份文件通用）

請假管理流程中有**兩種不同 ID**、不要混用：

| 變數 | 意義 | DB 欄位 | 用在哪 |
|------|------|---------|--------|
| **N** | 請假申請 ID（leave_request_id） | `leave_requests.id` | `approve_leave(leave_request_id=N, ...)` / `reject_leave(N, ...)` / `cancel_leave(N, ...)` / `get_leave_request(N)` |
| **M** | 審核 ID（approval_id） | `approvals.id` | `resolve_approval(approval_id=M, ...)` / `approve_leave(..., approved_id=M)` / `get_approval(M)` |

所長 LINE 回覆「核准 #M」時、**M 是審核 ID 不是請假 ID**。系統輸出 `list_pending_leave_requests` 時明確標兩種 ID 就是為了避免拿錯。

---

## 一、整體流程概觀

請假管理是三張表的合作：

| 層 | 表名 | 一句話 | 何時改 |
|----|------|--------|--------|
| 假別定義 | `leave_types` | 事務所有哪些假（特休 / 病假 / 事假...） | 一次性、首次導入 |
| 員工配額 | `leave_balances` | 王律師 2026 年特休 14 天、已用 3 天 | 每年初設定一次 |
| 請假紀錄 | `leave_requests` | 王律師申請 6/1 特休 1 天、狀態 pending | 每次請假 |

簽核流程示意（**重要：N = 請假申請 ID、M = 審核 ID，兩者不同、不要混用**）：

```
律師 LINE 說「下週一二請特休」
   ↓
AI 算 2 天 → request_leave(...)
   ↓
若 leave_type.requires_approval=True：
   - 系統建 leave_request 取得「請假 #N」（status=pending）
   - 系統建 approval 取得「審核 #M」（resume_action='approve_leave'、鎖定 params）
   - LINE 通知所長「請假 #N 待簽 / 對應審核 #M」
   ↓
所長 LINE 回「核准 #M」（注意是「審核 ID」、不是「請假 ID」）
   ↓
resolve_approval(approval_id=M, decision='approved', decided_by='所長')
   ↓
approve_leave(leave_request_id=N, approved_id=M, decided_by='所長')
   ↓
gate 驗 resume_params 一致 → 原子扣 balance → leave_request.status='approved' → consume approval
```

若 `leave_type.requires_approval=False`（如生理假），`request_leave` 一步完成、直接扣餘額。

詳細的 gate 行為（params 鎖定、單次消費、過期保護）見 CLAUDE.md HITL 章節。

---

## 二、首次設定（一次性）

### 1. 登記事務所有哪些假別

> ⚠️ 寫前必查：先 `query_knowledge('假別 leave_types')` 看所長有沒有講過要哪幾種。

```
register_leave_type(
    code='annual', name='特休',
    default_quota_days=14, requires_approval=True,
    is_paid=True, notes='年資對照表詳見事務所人事規章'
)
```

律師事務所常見配置（**僅作參考、應依所長實際說明與勞動基準法調整、不要自行發明天數**）：

| 代號 | 中文名 | 預設天數 | 需簽核 | 有薪 |
|------|--------|---------|--------|------|
| `annual` | 特休 | 依年資 | 是 | 是 |
| `personal` | 事假 | 依規章 | 是 | 否 |
| `sick` | 病假 | 依規章 | 是 | 依規章 |
| `bereavement` | 喪假 | 依親等 | 是 | 是 |
| `marriage` | 婚假 | 依規章 | 是 | 是 |
| `menstrual` | 生理假 | 依規章 | 否 | 依規章 |
| `official` | 公假（如出庭作證 / 受傳喚） | 依事由 | 是 | 是 |

> 天數 / 給薪比例**依勞動基準法及事務所人事規章**、由所長確認後填入。AI **不發明法定數字**——拿不準就問所長、或請所長提供規章。（這跟 legal-admin 的「不發明法律細節」一致，但請注意：此處是**勞動法 / 人事規章**的休假，與訴訟時限毫不相干。）

### 2. 為每位人員分配年度配額

新年度（或新人到職）時：

```
set_leave_balance(
    employee_id=1, leave_type_code='annual',
    year=2026, allocated_days=14
)
```

`used_days` 自動保留（不會被歸零）。如要批次處理多位人員，逐一呼叫即可。

---

## 三、人員申請請假（最常見場景）

> floor 提醒：`request_leave` 屬 HR 工具。**單一律師事務所為全權限單人運作（不設 `SME_FLOOR`）、此工具一律可用**；`general` / `external` 等受限部門層的 floor gate（會把 HR 工具物理移除）是保留給日後擴編的升級路（見 CLAUDE.md〈部門安全層（floor）與兩道牆〉）。若日後分層、floored 受限 session 連「建立請假申請」都呼不到此工具屬**正常、非系統錯誤**——請假申請的建立通常落在全權限層 / 由 line-channel 身份路由處理；該層呼不到 `request_leave` 時據實回報、別當壞掉（與第四節 `approve_leave` 的 floor 註記對齊）。

### 流程

律師說「6/1 請特休 1 天」，AI 應該：

1. 從對話算出 `start_date` / `end_date` / `days`（注意：含「當日」、6/1 一天即 start=end='2026-06-01'）
2. 確認人員 ID（從 LINE meta 或 `lookup_employee`）
3. 呼叫 `request_leave(...)`
4. 系統自動建 leave_request + approval、回傳 approval ID
5. **通知所長不是本 session 自己去撈所長 user_id 推播**：approval 一建立、系統就在同一 tx 內 enqueue 上報、確定性蓋章「來源層 + 申請人」通知簽核人（觸發 `approval_pending`，見 CLAUDE.md〈上報（escalation）機制〉、決策 #178 / #23）。AI 在當前對話據實回報「請假申請 #N 待簽 / 對應簽核 #M」即可，不用、也不該自己挑簽核人 reply。日後若分層、floored 部門層未必撈得到所長、也未必 push 得到——簽核通知統一走 escalation、由 line-channel 路由到對的人（執行模型細節交叉引用 line-comms 第六節）。

### 完整呼叫範例

```
request_leave(
    employee_id=1,
    leave_type_code='annual',
    start_date='2026-06-01',
    end_date='2026-06-01',
    days=1,
    reason='陪小孩看醫生'
)
```

### 半天怎麼處理

`days=0.5` 直接傳。系統會接受小數天數。`start_date` 與 `end_date` 同一天即可，可在 `reason` 註明「上午 / 下午」。

### 跨年禁止（系統會擋）

`start_date.year != end_date.year` 直接回 `ERROR: 暫不支援跨年度請假`。
正確做法：拆成兩張、各自申請。

```
# 錯：請 12/30~1/2 跨年
# 對：先請 12/30~12/31（2 天），再請 1/1~1/2（2 天）
```

> 注意：這裡「拆兩張」純粹是因為 `leave_balances` 按年度結算（跨年要分開扣餘額）的**人事系統限制**，**與任何訴訟期間 / 末日順延無關**。不要把這個拆法跟 legal-admin 的時限計算混為一談。

### 不需簽核的假別

`requires_approval=False` 的假別（如生理假），`request_leave` 一步完成、回傳「已核准」+ 餘額已扣。**不**會建立 approval。

---

## 四、簽核（所長視角）

### 核准

所長 LINE 回「核准 #M」（M = approval id），執行：

```
resolve_approval(approval_id=M, decision='approved', decided_by='所長')
approve_leave(
    leave_request_id=N,
    approved_id=M,
    decided_by='所長'
)
```

`approve_leave` 會：
- gate 驗 `approved_id` 對應的 approval `resume_params` 與當前傳入一致
- 原子扣 `leave_balances.used_days`（防超扣）
- 更新 `leave_requests.status='approved'`
- consume approval（單次使用、之後不能再用）

成功後 LINE 通知申請人「請假已核准」。

> **floor 提醒**：`approve_leave` 同時是 **HR 工具 + gate-backed 工具**。**單一律師事務所為全權限單人運作（不設 `SME_FLOOR`）、此工具一律可用**。以下是保留給日後擴編、分層後的升級路行為（機制原樣保留）：非全權限層一律被移除 HR 工具（見 CLAUDE.md〈部門安全層（floor）與兩道牆〉），所以 `general` / `external` 等部門層**多半沒有 `approve_leave`**。屆時本層沒有此工具＝**正常、不是系統錯誤**：`resolve_approval` 可能能做（核准是決策），但「真正扣餘額 + 標 approved」的 `approve_leave` 要由**有 HR 工具的層 / 全權限層**接手。比照 line-comms 第六節「執行接續可能要換層」——此時回報「請假 #N 已核准、扣假將由 HR 層執行」、不要假裝自己扣了。

### 駁回

所長 LINE 回「駁回 #M 原因 ...」，執行：

```
resolve_approval(approval_id=M, decision='rejected', decided_by='所長')
reject_leave(
    leave_request_id=N,
    rejected_approval_id=M,
    decided_by='所長',
    reason='本週有開庭、人力吃緊、改下週'
)
```

駁回**不**扣餘額（pending 本來就沒扣）。LINE 回申請人駁回原因。

---

## 五、取消請假

申請人或所長臨時不請了：

```
cancel_leave(
    leave_request_id=N,
    reason='會議改期、不請假了',
    actor='王律師'
)
```

- `pending` 狀態：直接標 `cancelled`、不影響餘額（本來就沒扣）
- `approved` 狀態：原子回補餘額（內含 `WHERE used_days >= delta` 保護、防 row 異常）

---

## 六、查餘額

人員說「我特休還剩幾天」：

```
get_leave_balance(employee_id=1, year=2026, leave_type_code='annual')
```

回傳格式：

```
## {人員名} 假別餘額
- [2026] 特休：配額 14 / 已用 3 / pending 1 / 可用 10 天
```

**重點：`可用 = 配額 - 已用 - pending`**。pending 也算「不可用」，防止同一人同時申請多張結果加總超過配額（pre-overdraw）。

留空 `year=0` 看所有年度；留空 `leave_type_code=''` 看所有假別。

---

## 七、待簽事項暴露（啟動儀表板自動跑）

`list_pending_leave_requests()` 在啟動流程被呼叫，輸出格式：

```
## 待簽請假申請
- 請假 #45 王律師 特休 1 天（2026-06-01~2026-06-01）｜審核 #88｜已等 5 天｜原因：陪小孩看醫生
- 請假 #46 林助理 病假 2 天（2026-06-03~2026-06-04）｜審核 #89
共 2 件待處理。簽核流程：
1. resolve_approval(approval_id=M, decision='approved' / 'rejected', decided_by='所長')
2. approve_leave(leave_request_id=N, approved_id=M, decided_by='所長')
   或 reject_leave(leave_request_id=N, rejected_approval_id=M, decided_by='所長', reason='...')
```

⚠️ **不要把「請假 #N」拿去呼叫 resolve_approval()**。resolve_approval 只認「審核 #M」。輸出明確標兩種 id、就是為了避免拿錯。

當 `list_pending_leave_requests` 偵測到等待 >= 3 天的請假、會在 label 自動附加「已等 N 天」、提醒所長優先處理。實際標紅 / 警示優先級由 ops-dashboard 整合時加（如 wait_days >= 7 視為緊急）。

> 此處「已等 N 天」是「申請放了幾天沒人簽」的**人事提醒**、與訴訟時限的逾期警示完全無關（時限逾期由 legal-admin 的 `list_upcoming_deadlines` 管）。

> 單一律所為單一所運作、不分事業體：`list_pending_leave_requests()` 不帶 `business_unit`（該參數為日後擴編成多所 / 多部門時保留的升級路、目前留空）。

---

## 八、失敗情境（重要 — 遇到 ERROR 時這樣判讀）

### A. `approval 不存在 / 未核准 / 已使用`

`approve_leave` gate 擋下、回「審核 #M 不存在、未核准或已使用」（這是合併 error、原因有三種）。

**判讀（三選一）：**
- approved_id 根本不存在 → 申請人或所長報錯 id
- 此 approval 尚未 resolve_approval(approval_id, decision='approved', decided_by='...') → 還在 pending
- 此 approval 曾被 consume 過（`consumed_at IS NOT NULL`） → 已執行過

**處理：**
```
get_approval(M)             # 看 approval 現況（含 consumed_at / consumed_by_id）
get_leave_request(N)        # 反查對應 leave_request 狀態
list_leave_requests(status='approved')   # 看是哪筆已處理過了
```

不要當系統錯誤回報、不要繞 sqlite。

### B. `審核 #M 的 resume_action 不是 approve_leave`

caller 拿錯了 approval（也許那筆 approval 是別的動作用的、被誤套到 approve_leave）。

**處理：** 重新查正確的 approval id、或請所長重發核准訊息。

### C. `params 不一致`

approval 的 `resume_params.days=1`、但呼叫 `approve_leave` 傳了不一樣的 `days`。

**處理：** **必須從 approval.detail 取出原始 resume_params**，不要從對話脈絡推算。例如：

```
# 錯：從對話再算一次 days
# 對：approval = approvals.get(M)；detail = json.loads(approval['detail'])；
#     params = detail['resume_params']；按 params 呼叫
```

### D. `餘額不足（含 pending）`

`request_leave` 回「剩 X 天（含 pending 申請）、申請 Y 天超出」。

**處理：**
- 跟申請人確認天數有沒有算錯（半天 vs 整天）
- 或回報所長「{人員} 的 {假別} 已不夠、要不要增配額」 → `set_leave_balance(employee_id=人員ID, leave_type_code='annual', year=2026, allocated_days=N)`（四個全必填）

### E. `跨年度禁止`

`start_date.year != end_date.year` 直接擋。

**處理：** 拆兩張申請（見第三節「跨年禁止」）。

### F. `Balance row 不存在`

`request_leave` 回「{年度} 尚未設定配額」。

**處理：** 先 `set_leave_balance(...)` 配額，再請申請人重申。可能是人員到職時忘了配。

### G. `cancel approved 但 balance 無法回補`

`cancel_leave` 回「row 不存在或 used_days 不足」。

**判讀：** 資料異常（可能有人手動改過 `leave_balances`、或舊資料）。

**處理：** **不直接 SQL 改資料**。報告原狀讓所長判斷，例如：

> 「{人員}{假別}{年度} 取消請假 {天數} 天時無法回補 balance：目前 `used_days={X}`、但 row 不存在 / 不足以扣 {天數}。可能是：
> 1. balance row 已被刪 → 走 `set_leave_balance(employee_id, leave_type_code, year, allocated_days=正確配額)` 重設配額（會新建 row）
> 2. 資料異常 → 走 `set_leave_balance` 重設配額並覆寫 allocated；used 保留既有值（系統不允許在 set_leave_balance 改 used）」

絕對不要繞過工具直接 SQL 改 `leave_balances.used_days`（會違反 Do/Don't）。如果舊資料確實有問題、改走 `set_leave_balance` + 後續以 `request_leave` / `approve_leave` 的正常路徑慢慢校正。

### H. `本層沒有 approve_leave 工具`（floor 升級路、單一律所目前不會遇到）

單一律師事務所為全權限單人運作、`approve_leave` 一律可用、**不會**遇到本情境。以下保留給日後擴編、分層後：在 `general` / `external` 等部門層、`approve_leave`（HR + gate-backed）已被 floor 移除（見 CLAUDE.md〈部門安全層（floor）與兩道牆〉），呼叫不到此工具。

**判讀：** 屆時這是**設計上的正常結果、不是系統錯誤**——本層沒有 HR 權限、扣不了假。

**處理：** 比照 line-comms 第六節「執行接續可能要換層」。`resolve_approval` 可能仍能做（核准本身是決策），但「真正扣餘額」要由**有 HR 工具的層 / 全權限層 / 原本建審核的 session** 接手。回報所長「請假 #N 已核准、扣假將由 HR 層執行」、不要假裝自己扣了。**不要繞 sqlite 自己改 `leave_requests.status` / `leave_balances`。**

### I. `resolve_approval 回「無權簽核」`（#24 簽核身份驗證；floor 升級路）

單一律師事務所為全權限單人運作、**不會**遇到本情境。以下保留給日後擴編、分層後：非全權限層 `resolve_approval` 會驗操作者（須 verified manager 以上、且本人 LINE 操作；actor 由系統取 line-channel 驗過的身份、不信任 agent 自填，見 CLAUDE.md〈actor 身份信任〉）。

**判讀：** 屆時該操作者**權限不足或非本人**——**不是系統錯誤**（對齊 line-comms 第六節已有寫法）。

**處理：** 照實回報「此筆需 manager 以上本人簽核」、請有權限的主管在自己的 LINE 重發「核准 #M」、不要繞、不要拿 agent 自填的名字硬簽。

---

## Do's and Don'ts

### Do
- 跨年度自動拆兩張（並告知申請人拆法）
- 半天用 `days=0.5`
- 失敗時 query approval 取原始 `resume_params`、不要再從對話推導
- 人員每次請假都 `insert_interaction_log`（系統自動做）
- 所長核准 / 駁回都記錄 `decided_by`

### Don't
- 不要繞過 `request_leave` 直接 `INSERT INTO leave_balances` 或 SQL 改 `used_days`
- 不要 mock approval id 給 `approve_leave`（gate 會驗）
- 不要把跨年請假合併成一張塞給系統
- 不要 silently 取消 approved 而不回補餘額
- 不要在 `set_leave_balance` 時把 `used_days` 歸零（系統不允許、保留既有值）
- 不要把請假的「天數」拿去算 / 對照任何訴訟時限（見檔首硬邊界）；法定期間一律走 legal-admin 的 `create_deadline`

---

## 快速參考

### 人員請假完整流程
```
1. request_leave(employee_id=1, leave_type_code='annual',
                start_date='2026-06-01', end_date='2026-06-01',
                days=1, reason='陪小孩看醫生')
2. （若 requires_approval=True）→ 系統建 approval + 通知所長
3. 所長：resolve_approval(approval_id=M, decision='approved', decided_by='所長') → approve_leave(leave_request_id=N, approved_id=M, decided_by='所長')
4. LINE 通知申請人：已核准
```

### 所長簽核
```
1. resolve_approval(approval_id=M, decision='approved', decided_by='所長')   # 或 decision='rejected'
2. approve_leave(leave_request_id=N, approved_id=M, decided_by='所長')
   # 或 reject_leave(leave_request_id=N, rejected_approval_id=M, decided_by='所長', reason='...')
```

### 取消
```
cancel_leave(leave_request_id=N, reason='不請了', actor='王律師')
```

### 查餘額
```
get_leave_balance(employee_id=1, year=2026, leave_type_code='annual')
```

### 待簽列表（啟動跑）
```
list_pending_leave_requests()   # 單一律所：列全所待簽（不帶 business_unit）
```

---

## 中斷恢復

如 context 被壓縮：
1. `get_context_summary(scope='full')` — 看「等待中」是否有 leave_request 相關
2. `list_pending_leave_requests()` — 看當前所有待簽
3. 從 leave_request id 反推當初的對話 / approval，繼續處理

---

## 注意事項

- 跨年禁止（系統會擋）
- 半天用小數天數（0.5）
- 餘額原子化扣減 / 回補（防 race condition、防超扣 / underflow）
- HITL gate 嚴格驗證 `resume_params` 一致 + 單次消費，**詳見 CLAUDE.md HITL 章節**
- 單一律所為單一所運作、`business_unit` 留空（inert）；該欄位為日後擴編成多所 / 多部門保留的升級路
- 離職人員的 `leave_requests` 透過 `ON DELETE SET NULL` 保留紀錄（顯示「人員 #X（已離職）」），不會被刪
- **請假天數 ≠ 訴訟時限**：本檔所有「天數」都是人事休假概念、與 legal-admin 的法定期間零關係（見檔首硬邊界）
