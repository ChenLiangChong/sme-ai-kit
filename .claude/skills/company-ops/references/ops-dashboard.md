# 事務所每日彙整／開機儀表板專業指南

## 觸發情境

使用者（律師／助理）說「今天有什麼事」「目前狀況」「今天有哪些時限」「dashboard」，或 session 剛啟動時。

> 律所 readout 的核心是**時限**。本模組負責開機／被問時的「總覽彙整」；每日固定時間 cron 自動推全所一份的「今日工作事項」流程見 legal-admin 的 [daily-digest.md](../../legal-admin/references/daily-digest.md)（投遞由 escalation 三層基建負責、不靠你開著 Claude）。

---

## 一、執行步驟

> 與 CLAUDE.md 啟動流程一致。CLAUDE.md 是主控，本模組負責產出內容。

1. `get_context_summary(scope='full')` — 系統狀態
2. **判斷是否為首次啟動**：
   - 如果員工數 = 0 → 這是全新系統，自動載入 knowledge-capture 的「系統導入標準流程」，引導所長完成初始設定（律師 / 助理 / 行政名冊、LINE 綁定、常用行事曆）
   - 如果員工數 > 0 → 正常啟動，繼續下面的步驟
3. **掃描器 heartbeat 健康（最優先、列最前）** — 檢查 `get_context_summary` 回傳的哨兵狀態：時限掃描器（`scan_deadlines.py`）與 watchdog（`scan_heartbeat.py`）是否還活著。**失聯要列在 readout 最前面**——時限恐停止倒數、是執業過失高風險（見下方〈三、掃描器 heartbeat 與靜默失敗哨兵〉）。
4. `list_pending_intakes()` — **待確認到期日**：已抽出送達日 / 文書類型、推回 LINE 但律師還沒一鍵確認入庫的 backlog（`stage_deadline_intake` 暫存、只存事實未算天數）。**這裡列的是「等待人確認」、不是已確定時限**，不端權威倒數日期。
5. `list_upcoming_deadlines(within_days=7)` — **即將到期法定時限**：已確認入庫的 pending 時限，按**內部期限升冪**（最急在前）。每筆**只搬不算**——並陳內部期限（盯這個）＋法定期限（底線）＋ `statutory_basis` 法條依據，全部讀 `deadlines` 表既有欄位。**dashboard 絕不自己心算天數**（天數是 `create_deadline` 確定性算好寫入的事，見 CLAUDE.md〈反捏造原則〉與 legal-admin 鐵律）。
6. **逾期時限** — `list_upcoming_deadlines` / `list_deadlines` 中 `days_left < 0` 者另列「已逾期」區塊（最高優先）。回報時帶**回復原狀**備援提示（`get_deadline` 的 `recovery_window`），立刻提醒主持律師、不要只記一筆了事。
7. `list_pending_leave_requests()` — 待簽請假申請（單人律所通常為空、顯示 0 件；多人所有助理 / 行政請假時才會有資料）
8. 檢查 `daily_snapshots` 表有沒有今天的紀錄 → 沒有就 `save_daily_snapshot()`
9. **待投遞 escalation** — `list_pending_escalations()` 檢查上報投遞狀況：有 `failed` / 逾期未送達（claim 租約超時）或某筆**查無收件人**就在 readout 末尾點出（否則上報靜默失敗無人知）。escalation 觸發 / 投遞 / 收件人 coalesce 機制見 CLAUDE.md〈上報（escalation）機制〉。
10. 整理成結構化摘要，簡短報告後處理使用者的問題

### floor-aware 啟動分支（**多人版才適用**的附註）

> **個人律所通常不設 `SME_FLOOR`**：單一律師、看全部、沒有對內隱藏對象 → 部署為全權限單人，下列分支等同「不過濾、全跑」（上面〈執行步驟〉就是預設主敘述）。`SME_FLOOR` / floor gate **保留為 inert 升級路**，待增助理或多人所再啟用。以下分支**全是多人版才生效**的機制，個人所不會觸發；引用機制名稱即可、不要在本檔寫死層清單。

開機 readout 在多人版依本 session 的部門安全層（`SME_FLOOR`）收斂——核心機制（兩道牆 / 三態 / 工具白名單）見 CLAUDE.md〈部門安全層（floor）與兩道牆〉，本段只講 dashboard 在各層怎麼產出：

- **全權限層（`SME_FLOOR=''` 或 `confidential`）**：跑完整 readout（即上方步驟 1-10），並負責步驟 9 的 `list_pending_escalations()` 上報投遞檢查。
- **非全權限層也砍 HR 工具**：`list_pending_leave_requests` / `lookup_employee` 等員工 / 請假工具被 `apply_floor_policy` 物理移除——dashboard 的「待簽請假」區塊在這些層以「本層不可見」呈現、非當缺資料。
- **非全權限層共通**：`list_pending_escalations` / `mark_escalation_sent` 也已被移除——受限層**不負責**檢查或投遞上報，上報投遞由全權限層 + cron 保證層處理（見 CLAUDE.md〈上報（escalation）機制〉）；本層 readout 不放上報投遞檢查。
- **#166 開機自動讀取早退**：`get_context_summary` 在非全權限層走 `is_full_access()` 早退安全子集，避免「開機 hook 自動跑就洩漏」（見 CLAUDE.md〈已收斂 vs 仍有缺口〉）。
- 不確定本層有哪些工具 / 可見度 → 用 `floor_status` / `floor_config_status` 診斷，不要硬猜。

---

## 二、輸出格式

```
事務所開機彙整 — {日期}

掃描器：時限掃描器 正常 / watchdog 正常
待確認到期日：X 件（已抽出、待律師一鍵確認入庫）
   → [#intake_id] {案件/當事人} {文書類型} 送達 {日期} 已等 N 小時
即將到期法定時限：X 筆（按內部期限升冪）
   → [#deadline_id] {案號} {當事人} {時限類型}：內部 {日期}（法定 {日期}·{statutory_basis}）剩 N 個工作日 承辦：{律師}
逾期時限：X 筆
   → [#deadline_id] {案號} {當事人} {時限類型} 已逾內部期限 {N} 天（評估回復原狀 {recovery_window}）
待簽請假：X 件
   → 最久：{助理/行政} {假別} {天數} 天 已等 N 天
待處理任務：X 項（Y 項緊急）
   → 最緊急：{任務標題}，截止 {日期}
待投遞上報：X 筆（如有 failed / 逾期未送達 / 查無收件人）
今日 LINE 互動：X 則
人員：主持律師 X / 律師·助理·行政 X

{如果有緊急事項（逾期時限、掃描失聯、查無收件人），在最後加一句建議}
```

> 時限類型用底層 enum 對應的中文呈現（如 `appeal_*`→上訴、`abjection_*`→抗告、`correction`→限期補正、`provisional_litigation`→保全命起訴、`admin_revocation`→行政訴訟撤銷、`statute_*`/`197_*`→消滅時效）；天數一律來自 `deadlines` 表既有欄位、**dashboard 不重算**。

---

## 三、掃描器 heartbeat 與靜默失敗哨兵（律所專屬、列最前）

時限倒數是**時間驅動**的（cron `scan_deadlines.py` 每日跑、人沒開 Claude 也在倒數）。哨兵的存在是補「漏不掉」的盲區——核心機制見 legal-admin SKILL〈靜默失敗哨兵（#H1/#H2）〉與 privacy-deploy，本段只講 dashboard 怎麼呈現：

| 哨兵 / 健康項 | 偵測來源 | dashboard 呈現（失聯列最前） |
|------|---------|------|
| 時限掃描器失聯 | `scan_deadlines.py` 的 heartbeat 過期（沒跑 / 報錯）；watchdog `scan_heartbeat.py` 偵測逾門檻即 `scan_stalled` 上報 | `[時限掃描失聯]` 紅字置頂 → 時限恐停止倒數，立刻人工 `list_upcoming_deadlines` 巡一次並修 crontab |
| watchdog 失聯 | `scan_heartbeat.py` 自身 heartbeat 過期 | `[watchdog 失聯]` 紅字置頂 → 連「失聯偵測器」都停了，最高優先排查 |
| 待確認 backlog 久未入庫 | `stage_deadline_intake` 暫存後人忘了回確認；`scan_unconfirmed_intake.py` 逾時跟催 | 「待確認到期日 N 件」（步驟 4）；此時還沒算天數，只列送達日 / 文書類型 / 等待時數 |

> watchdog 是**時間驅動**的（OS cron），不靠你開著 Claude；它報的是「掃描器死了」這個元事件。dashboard 只是把哨兵已寫入的狀態讀出來置頂、不是 dashboard 自己去 ping cron。

---

## 四、全部正常時

列出各項為零的明細，讓所長確認系統有在跑：

```
事務所開機彙整 — {日期}

一切正常
掃描器：時限掃描器 正常 / watchdog 正常
待確認到期日：0 件
即將到期法定時限：0 筆
逾期時限：0 筆
待簽請假：0 件
待處理任務：0 項
待投遞上報：0 筆
今日 LINE 互動：X 則
人員：主持律師 X / 律師·助理·行政 X
```

---

## 五、被律師主動問「今天有哪些時限」時

不必跑整套開機 readout，直接走 legal-admin daily-digest 的互動式彙整：

1. `list_upcoming_deadlines(within_days=7)` — 按內部期限升冪，每筆並陳內部期限（盯這個）＋法定期限（底線）＋法條依據。
2. 標示這幾類，律師一眼看出輕重：
   - **已逾內部期限** → `[已逾內部期限]`（最高優先、評估回復原狀）
   - **需人工複核** → `[需人工複核]`（送達 / 在途 / 法版 / 教示比對有疑義，別當已確定倒數）
   - 嚴重度 red（不變期間失權硬倒數）排前面
3. 交叉行事曆（見 legal-admin [calendar-sync.md](../../legal-admin/references/calendar-sync.md)）補上只記在行事曆、沒進 `deadlines` 的庭期。

詳細流程與彙整訊息範例見 [daily-digest.md](../../legal-admin/references/daily-digest.md)。

---

## 六、異常偵測

Dashboard 不只報數字。先分清楚**哪些是系統自動產出、哪些要 agent 自己分析**，回報時別把後者講成「系統自動偵測」。

### 系統自動產出（`get_context_summary` 本身就含）

`get_context_summary` 回傳裡已內建這幾項，直接讀就有、不用另算：

| 系統自動產出 | 來源 | 呈現 |
|------|------|------|
| 掃描器失聯哨兵 | `get_context_summary` 讀 `scan_deadlines.py` / `scan_heartbeat.py` heartbeat（過期 / `scan_stalled`） | `[時限掃描失聯]` / `[watchdog 失聯]` 紅字置頂 |
| 待確認 backlog | `get_context_summary` / `list_pending_intakes`（`stage_deadline_intake` 久未確認） | 「待確認到期日 N 件，請律師確認送達日 / 文書類型」 |
| 待審超時提示 | `get_context_summary` 對 approval 建立時間判讀（過 `expires_at` 啟動時自動標 expired） | 「有審核項目等了超過時限，請確認」 |
| 日期字串提醒 | `get_context_summary` 內 `_date_reminders()`（有限的日期關鍵字命中） | 對應提醒文字 |
| 待簽請假等 >= N 天 | `list_pending_leave_requests` 自動於 label 附加「已等 N 天」（HR 工具、多人版的全權限層才有資料） | 「{助理/行政} {假別} 申請已等 N 天，請盡快處理」（>= 7 天視為緊急） |

> **時限本身的「即將到期 / 逾期」不是 `get_context_summary` 算出來的**——倒數由 cron `scan_deadlines.py` 命中 `escalation_lead_days` 節點時 `enqueue_escalation`；dashboard 是讀 `list_upcoming_deadlines` 既有 `days_left`、**搬不算**。

### agent 自行分析（系統不自動偵測、要 agent 算）

以下**不是** `get_context_summary` 自動回的——若所長要看，由 agent 在產 readout 時用對應工具拉資料自行判讀，系統目前不自動偵測或推送這些：

| 可另行分析的異常 | agent 怎麼算 | 建議動作 |
|------|---------|---------|
| 任務逾期率偏高 | agent 用 `list_tasks` 算逾期任務 / 總任務 | 「逾期率偏高，建議檢討工作量分配」 |
| 多筆時限集中同週到期 | agent 看 `list_upcoming_deadlines` 同週筆數 | 「本週有 X 筆時限集中到期，提醒排程」（仍只搬既有 days_left、不重算） |
| 知識庫矛盾 | agent 主動跑 `lint_knowledge(checks='contradictions')`（非開機自動跑） | 「知識庫有 X 組潛在矛盾，建議檢視（法律見解 / SOP）」 |

### 上報投遞異常（多人版**僅全權限層**，系統有 enqueue、投遞要看狀態）

| 異常 | 偵測邏輯 | 建議動作 |
|------|---------|---------|
| 上報投遞異常 | readout 主動跑 `list_pending_escalations()`、看有無 `failed` / 逾期未送達（claim 租約超時、見 CLAUDE.md〈上報（escalation）機制〉#27） | 「有 X 筆內部上報未送達 / 查無收件人，請確認」——否則上報靜默失敗無人知。多人版的受限層此工具已被移除、不在此層檢查 |

> escalation 的「觸發」本身是系統硬接線自動的（時限命中提醒節點 / 逾期 `deadline_missed`、approval_pending、員工權限變動等會在 in-tx 自動 `enqueue_escalation`，見 CLAUDE.md〈上報（escalation）機制〉與 legal-admin daily-digest）；上表只是檢查**投遞結果**、不是 dashboard 自己去偵測該不該上報。

---

## 七、自動每日彙整推送

CLAUDE.md 啟動流程會決定是否推送。每日固定時間 cron `scan_deadlines.py` 推全所一份「今日工作事項」的流程、訊息範例與投遞三層見 legal-admin [daily-digest.md](../../legal-admin/references/daily-digest.md)；本模組只負責被問時 / 開機時的內容產出。
推送時訊息前綴加 `[今日工作事項]`，方便 DB 查詢今天是否已推過。

---

## Do's and Don'ts

### Do
- 數字為零也要列出，讓所長知道系統有在跑
- **掃描器失聯 / watchdog 失聯列在 readout 最前面**（時限恐停止倒數＝執業過失高風險）
- 某個工具呼叫失敗 → 跳過那個區塊，繼續其他的
- 善用系統自動產出的提示（掃描器失聯 / 待確認 backlog / 待審超時 / 日期提醒 / 待簽請假已等 N 天）；其餘異常（任務逾期率、集中到期、知識庫矛盾）由 agent 用對應工具自行判讀後再提醒，別講成「系統自動偵測」
- 員工數 = 0 時引導到 knowledge-capture 導入流程
- 人員回報依 `employees.role` 拆分（主持律師 / 律師·助理·行政），不要混合計數

### Don't
- 不要編造或猜測任何數字 — 全部來自 DB
- **絕不自己心算時限天數** — 即將到期 / 逾期天數一律讀 `deadlines` 表既有欄位（`days_left` / 雙日期 / `statutory_basis`），dashboard 只搬不算（見 CLAUDE.md〈反捏造原則〉）
- 把「待確認到期日」（`list_pending_intakes`）當成已確定時限端權威倒數 — 那是**還沒確認入庫**的 backlog、未算天數
- 除啟動流程要求的 `save_daily_snapshot()`（見第一節步驟 8）外，不做其他寫入操作
- 不要省略為零的區塊

---

## 八、注意事項

- 除啟動流程的 `save_daily_snapshot()`（步驟 8）外純讀取、不做其他寫入
- 資料全來自 DB，不要猜測或編造；時限天數來自引擎確定性計算的既有欄位、不重算
- 某個工具呼叫失敗 → 跳過那個區塊繼續其他的
- 數字為零也要列出，讓所長知道系統有在跑
