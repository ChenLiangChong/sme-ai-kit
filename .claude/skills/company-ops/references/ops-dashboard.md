# 營運儀表板專業指南

## 觸發情境

使用者說「今天有什麼事」「目前狀況」「營運報告」「dashboard」，或 session 剛啟動時。

---

## 一、執行步驟

> 與 CLAUDE.md 啟動流程一致。CLAUDE.md 是主控，本模組負責產出內容。

1. `get_context_summary(scope='full')` — 系統狀態
2. **判斷是否為首次啟動**：
   - 如果員工數 = 0 → 這是全新系統，自動載入 knowledge-capture 的「系統導入標準流程」（Step 1-9），引導老闆完成初始設定
   - 如果員工數 > 0 → 正常啟動，繼續下面的步驟
3. `low_stock_alerts()` — 庫存警報
4. `check_overdue()` — 逾期帳款。**非財務層此工具已被 floor 移除**（同 `monthly_summary`、見下方〈floor-aware 啟動分支〉以「本層不可見」處理、不要當缺資料）
5. `list_pending_leave_requests()` — 待簽請假申請（**HR 工具、僅全權限層**：floored 非全權限層此工具被移除、本區塊以「本層不可見」呈現；全權限層無資料時自然回 empty、顯示 0 件）
6. `monthly_summary()` — 本月收支（CLAUDE.md 啟動 readout 要求項；`get_context_summary` 本身不含這段）。**非財務層此工具已被 floor 移除**：見下方〈floor-aware 啟動分支〉，該區塊以「本層不可見」呈現、不是顯示 0 或當缺資料。
7. 檢查 `daily_snapshots` 表有沒有今天的紀錄 → 沒有就 `save_daily_snapshot()`（會自動存全域 + 各事業體快照）
8. 整理成結構化摘要，簡短報告後處理使用者的問題

### floor-aware 啟動分支

開機 readout 依本 session 的部門安全層（`SME_FLOOR`）收斂——核心機制（兩道牆 / 三態 / 工具白名單）見 CLAUDE.md〈部門安全層（floor）與兩道牆〉，本段只講 dashboard 在各層怎麼產出：

- **全權限層（`SME_FLOOR=''` 或 `confidential`）**：跑完整 readout，並**額外**呼叫 `list_pending_escalations()` 檢查上報投遞狀況——有 `failed` / 逾期未送達（claim 租約超時，見下方異常偵測表）或某筆**查無收件人**就在 readout 末尾點出、提醒老闆，否則上報靜默失敗無人知。escalation 投遞 / 收件人 coalesce 機制見 CLAUDE.md〈上報（escalation）機制〉。
- **非財務層（floor-map `financial_visibility` 非 `all`）**：`monthly_summary` / `check_overdue` 等財務讀取工具已被 `apply_floor_policy` 物理移除（呼叫不到）。「本月收支」區塊**以「本層不可見」呈現**（如 `本月收支：本層不可見`），不要顯示 0、不要當成工具失敗、不要嘗試從別處湊數字。
- **非全權限層共通**：`list_pending_escalations` / `mark_escalation_sent` 也已被移除——受限層**不負責**檢查或投遞上報，上報投遞由全權限層 + cron 保證層處理（見 CLAUDE.md〈上報（escalation）機制〉）；本層 readout 不放上報投遞檢查。
- **非全權限層也砍 HR 工具**：`list_pending_leave_requests` / `lookup_employee` 等員工 / 請假工具被移除——dashboard 的「待簽請假」區塊在這些層以「本層不可見」呈現、非當缺資料。
- 不確定本層有哪些工具 / 可見度 → 用 `floor_status` / `floor_config_status` 診斷，不要硬猜。

---

## 二、輸出格式

```
🏢 {公司名稱} 營運狀態 — {日期}

📝 待處理任務：X 項（Y 項緊急）
   → 最緊急：{任務標題}，截止 {日期}
⏳ 待審核：X 項
🏖️ 待簽請假：X 件（如有）
   → 最久：{員工} {假別} {天數} 天 已等 N 天
⚠️ 庫存警報：X 項
   → 最低：{品名} 剩 {數量}（安全庫存 {數量}）
💹 本月收支：收入 NT${X} / 支出 NT${X} / 淨額 NT${X}
💬 今日 LINE 互動：X 則
👥 人員：老闆 X / 員工 X / 外包 X | 👤 客戶：X 位

{如果有多事業體，加分項}
📊 事業體分項：
  WFA：任務 X / 訂單 X / 收入 NT${X}
  Content：任務 X / 訂單 X / 收入 NT${X}
  Distribution：任務 X / 訂單 X / 收入 NT${X}

{如果有緊急事項，在最後加一句建議}
```

---

## 三、全部正常時

列出各項為零的明細，讓老闆確認系統有在跑：

```
🏢 {公司名稱} 營運狀態 — {日期}

✅ 一切正常
📝 待處理任務：0 項
⏳ 待審核：0 項
🏖️ 待簽請假：0 件
⚠️ 庫存警報：0 項
💹 本月收支：收入 NT${X} / 支出 NT${X}
💬 今日 LINE 互動：X 則
👥 人員：老闆 X / 員工 X / 外包 X | 👤 客戶：X 位
```

---

## 四、Scorecard 概念（EOS 框架）

### 週度關鍵數字

建議追蹤 5-10 個每週核心指標，每個有目標值和負責人：

| 指標 | 目標 | 本週 | 趨勢 | 負責人 |
|------|------|------|------|--------|
| 週營收 | NT$100K | NT$95K | 📉 | 老闆 |
| 新客數 | 5 | 3 | 📉 | 業務 |
| 任務完成率 | 80% | 85% | 📈 | 全員 |
| 庫存準確率 | 98% | 96% | → | 倉管 |
| 客訴數 | <3 | 2 | ✅ | 客服 |
| LINE 回覆率 | 100% | 100% | ✅ | 全員 |

指標未達標 → 紅色標記 + 附帶建議

### 設定方式

初次導入時用 knowledge-capture 詢問老闆：
- 「你最關心哪 5 個數字？」
- 「每個的目標值是多少？」
- 存入 business_rules(category='scorecard')

---

## 五、季度 Rocks（EOS 框架）

### 什麼是 Rocks

每季選 3-7 個最重要的目標，SMART 格式：

| Rock | 負責人 | 截止 | 狀態 |
|------|--------|------|------|
| Q2 完成新品上架 | 老闆 | 6/30 | 🟡 進行中 |
| 建立 3 家新經銷商 | 業務 | 6/30 | 🔴 落後 |
| 庫存週轉率提升到 8 | 倉管 | 6/30 | 🟢 達成中 |

### 在 Dashboard 中的呈現

Rocks 用 tasks 表管理，category='rock'。**`get_context_summary` 不會自動附帶 Rocks 進度**——如有設定，由 agent 在產 readout 時另以 `list_tasks(category='rock')` 撈該分類任務、自行整理進度區塊（`search_tasks` 只吃 `query` 關鍵字、不以 category 篩，要按關鍵字找才用）。系統不主動偵測或推送 Rocks 落後。

---

## 六、異常偵測

Dashboard 不只報數字。先分清楚**哪些是系統自動產出、哪些要 agent 自己分析**，回報時別把後者講成「系統自動偵測」。

### 系統自動產出（`get_context_summary` 本身就含）

`get_context_summary` 回傳裡已內建這幾項，直接讀就有、不用另算：

| 系統自動產出 | 來源 | 呈現 |
|------|------|------|
| 待審超時提示 | `get_context_summary` 對 approval 建立時間判讀（過 `expires_at` 啟動時自動標 expired） | 「有審核項目等了超過時限，請確認」 |
| 庫存警報摘要 | `get_context_summary` / `low_stock_alerts`（current_stock <= 安全庫存） | 「{品名} 剩 {數量}（安全庫存 {數量}）」 |
| 逾期帳款摘要 | `get_context_summary` 撈逾期應收 | 「逾期帳款 NT${X}，請確認催收」 |
| 日期字串提醒 | `get_context_summary` 內 `_date_reminders()`（有限的日期關鍵字命中） | 對應提醒文字 |
| 待簽請假等 >= N 天 | `list_pending_leave_requests` 自動於 label 附加「已等 N 天」（HR 工具、僅全權限層） | 「{員工} {假別} 申請已等 N 天，請盡快處理」（>= 7 天視為緊急） |

### agent 自行分析（系統不自動偵測、要 agent 算）

以下**不是** `get_context_summary` 自動回的——若老闆要看，由 agent 在產 readout 時用對應工具拉資料自行判讀，系統目前不自動偵測或推送這些：

| 可另行分析的異常 | agent 怎麼算 | 建議動作 |
|------|---------|---------|
| 連續多天零營收 | agent 比對 `monthly_summary` / `list_transactions` 近幾日 income | 「已經幾天沒有收入紀錄，是沒記帳還是真的沒有？」 |
| 任務逾期率偏高 | agent 用 `list_tasks` 算逾期任務 / 總任務 | 「逾期率偏高，建議檢討工作量分配」 |
| 多項商品斷貨 | agent 用 `check_stock` / `low_stock_alerts` 數 current_stock = 0 的品項 | 「多項商品斷貨，需要緊急處理」 |
| 知識庫矛盾 | agent 主動跑 `lint_knowledge(checks='contradictions')`（非開機自動跑） | 「知識庫有 X 組潛在矛盾，建議檢視」 |

### 上報投遞異常（**僅全權限層**，系統有 enqueue、投遞要看狀態）

| 異常 | 偵測邏輯 | 建議動作 |
|------|---------|---------|
| 上報投遞異常 | 全權限層 readout 主動跑 `list_pending_escalations()`、看有無 `failed` / 逾期未送達（claim 租約超時、見 CLAUDE.md〈上報（escalation）機制〉） | 「有 X 筆內部上報未送達 / 查無收件人，請確認」——否則上報靜默失敗無人知。受限層此工具已被移除、不在此層檢查 |

> escalation 的「觸發」本身是系統硬接線自動的（approval_pending / 記帳超門檻 / 已出貨單被取消 / 刪帳 / 員工權限變動 / qc_failed 會在 in-tx 自動 `enqueue_escalation`，見 CLAUDE.md〈上報（escalation）機制〉）；上表只是全權限層**檢查投遞結果**、不是 dashboard 自己去偵測該不該上報。

---

## 七、自動日報推送

CLAUDE.md 啟動流程會決定是否推送日報。本模組只負責產出內容。
推送時訊息前綴加 `[日報]`，方便 DB 查詢今天是否已推過。

---

## Do's and Don'ts

### Do
- 數字為零也要列出，讓老闆知道系統有在跑
- 某個工具呼叫失敗 → 跳過那個區塊，繼續其他的
- 善用系統自動產出的提示（待審超時 / 庫存警報 / 逾期帳款 / 日期提醒 / 待簽請假已等 N 天）；其餘異常（連續零營收、任務逾期率、斷貨數、知識庫矛盾）由 agent 用對應工具自行判讀後再提醒，別講成「系統自動偵測」（系統目前不自動排程或偵測這些）
- 員工數 = 0 時引導到 knowledge-capture 導入流程
- 人員回報依 `employees.role` 拆分（老闆 / 員工 / 外包），不要混合計數成「員工 X 人」

### Don't
- 不要編造或猜測任何數字 — 全部來自 DB
- 除啟動流程要求的 `save_daily_snapshot()`（見第一節步驟 7）外，不做其他寫入操作
- 不要省略為零的區塊

---

## 八、注意事項

- 除啟動流程的 `save_daily_snapshot()`（步驟 7）外純讀取、不做其他寫入
- 資料全來自 DB，不要猜測或編造
- 某個工具呼叫失敗 → 跳過那個區塊繼續其他的
- 數字為零也要列出，讓老闆知道系統有在跑
