# 報表生成專業指南（律所內部彙總）

## 觸發情境

「這週的彙總」「日報」「週報」「月報」「這個月做了哪些事」「匯出」

> 對象是**所內**（主持律師 / 律師 / 助理 / 行政），對內彙總、不對外。律所**無**對外客戶報表、行銷成效、收費/帳務/計時計費報表（這些已移出產品，本檔任何區塊都不含）。
> 與 ops-dashboard 的差異：dashboard 是**即時快照**（現在狀況），report-gen 是**期間彙總**（一段時間內發生什麼）。兩者互補、都是**純讀取**。

---

## 一、報表類型

> 報表內容聚焦：**案件待辦 / 今日（期間）完成 / 明日到期書狀 / 即將到期法定時限 / 逾期時限 / 待簽請假**。法定時限一律是 legal-admin 時限引擎在 `create_deadline` 當下確定性算好、附 `statutory_basis` 的既存事實，報表**只把它列出來、絕不在報表裡心算或重算天數**（反捏造、算錯＝執業過失）。

### 日報

觸發：使用者主動要求；或啟動流程時由 agent 判斷該不該主動提一句（系統的「每日固定時間推全所一份」走 legal-admin 的 cron `scan_deadlines.py` + 每日彙整，見 legal-admin `daily-digest.md`；report-gen 這份是「被問時現算現答」的版本）

```
{事務所名稱} 日報 — {日期}

📝 案件待辦
  今日完成：X 項
  今日新增：X 項
  明日到期：X 項

📑 明日到期書狀 / 庭期
  - {書狀名 / 庭期}（案號 / 案件代號）承辦：XX 律師

⏰ 即將到期法定時限（7 日內、按內部期限升冪）
  - [#{deadline_id}] {案號} {文書類型}：內部 {internal_deadline}（法定 {statutory_deadline}·{statutory_basis}）→ 承辦 XX 律師 {[需人工複核]?}

🔴 逾期時限：X 筆（如有，逐筆列、最高優先）
⏳ 待簽請假：X 件（如有列出）
```

### 週報

觸發：使用者說「週報」（系統不會每週固定自動推週報；自動推送的是每日彙整。要定時週報得靠未來補上的排程器）

```
{事務所名稱} 週報 — 第 XX 週（MM/DD - MM/DD）

📝 案件待辦
  完成：X 項（完成率 XX%）
  新增：X 項
  逾期（待辦）：X 項
  下週到期（待辦）：X 項

📁 案件動態
  新建案件：X 件
  本週遞交書狀：X 件（mark_deadline_filed 計）

⏰ 法定時限（下週 14 日內、按內部期限升冪）
  - 逐筆列：內部期限（盯這個）／法定期限（底線）／法條依據／承辦律師
  - 標 [需人工複核] / [已逾內部期限] 者排前面

⏳ 請假
  本週簽核：核准 X 件 / 駁回 X 件
  待簽：X 件

🔑 重點事項
  - {本週最重要的 1-3 件事，例如失權硬倒數的案件}

📋 下週重點
  - {下週最需要盯的 1-3 件事}
```

### 月報

觸發：使用者說「月報」（系統不會每月固定自動推月報；要定時得靠未來的排程器）

```
{事務所名稱} 月報 — {YYYY}年{MM}月

📝 案件待辦統計
  總待辦：X 項
  完成率：XX%
  準時率：XX%
  平均完成天數：X 天

📁 案件統計
  在辦案件：X 件（本月新建 +X）
  本月結案 / 退場：X 件
  本月遞交書狀：X 件

⏰ 法定時限統計
  本月新建時限：X 筆
  本月已遞交（filed）：X 筆
  目前 pending：X 筆，其中 [需人工複核] X 筆
  本月發生逾期：X 筆（逐筆列、評估回復原狀者標注）

⏳ 請假統計
  本月請假：X 件（核准 X / 駁回 X）

📋 知識庫變更（法律見解 / SOP）
  {knowledge_changelog(days=30) 摘要}
  新增：X 條 | 更新：X 條

🔍 知識健檢
  {lint_knowledge() 摘要 — 矛盾 X 組、過期 X 條、覆蓋缺口 X 個}

🔑 本月亮點
  - {最好的 1-3 件事}

⚠️ 需要關注
  - {需要改善的 1-3 件事，例如逾期 / 久未確認入庫的時限}
```

---

## 二、資料來源對照

| 報表區塊 | 資料來源 |
|---------|---------|
| 案件待辦統計 | `list_tasks()` + 篩選（status / due_date） |
| 案件動態 / 在辦案件 | `list_matters(status='open')` |
| 即將到期 / 逾期法定時限 | `list_upcoming_deadlines(within_days=N)`（按內部期限升冪；逾期者帶 `[已逾內部期限]`）／`list_deadlines(matter_id=N)`（單案）／`get_deadline(deadline_id)`（單筆 calc_trace） |
| 本月遞交書狀 | `list_deadlines` 篩 `status='filed'`（`mark_deadline_filed` 標記的） |
| 請假簽核 / 待簽 | `list_pending_leave_requests()` / `list_leave_requests()` |
| 規則變更 | `knowledge_changelog(days=30)` |
| 知識健檢 | `lint_knowledge()` |
| 整體狀態 | `get_context_summary()` |

> **時限相關工具一律是「讀」**：報表只搬 `list_upcoming_deadlines` 既有的內部 / 法定雙日期 + `statutory_basis`，**不在報表裡呼叫 `create_deadline` 重算、不調整天數、不心算末日順延或在途期間**——那些是時限引擎的事（見 legal-admin `deadline-intake.md`）。

---

## 三、數據解讀原則

### 不只報數字，要給洞察

| 差的報表 | 好的報表 |
|---------|---------|
| 「本月新建案件 8 件」 | 「本月新建案件 8 件，比上月多 3 件，主要是勞資爭議類增加」 |
| 「pending 時限 12 筆」 | 「pending 時限 12 筆，其中 3 筆 7 日內到期、1 筆已逾內部期限（#23 王案上訴），建議今天優先處理」 |
| 「逾期 1 筆」 | 「逾期 1 筆（#23），已逾內部期限 2 天但仍在法定期限前；同步附上回復原狀備援供律師評估」 |

### 比較維度

每個指標盡量附帶至少一個比較：
- 上月（MoM）
- 去年同月（YoY，如有資料）
- 目標值（如有設定）

### 異常標記

| 變動幅度 | 標記 |
|---------|------|
| ±5% 以內 | 正常，不特別標記 |
| ±5-15% | 📈 / 📉 標記趨勢 |
| ±15-30% | ⚠️ 標記為異常 |
| ±30% 以上 | 🔴 標記為重大異常，附帶解釋 |

> **時限類絕不只看「幅度」**：任何**逾期**或 **7 日內到期且嚴重度 red（不變期間失權硬倒數）**的時限，不論數量多寡一律標 🔴 列最前、附法條依據與承辦律師，不適用上面的百分比門檻。

---

## 四、輸出方式

### LINE 精簡版

用 `reply` 發送 3-5 個核心數字。
前綴加 `[日報]` / `[週報]` / `[月報]`。
不超過 500 字。
**逾期 / 即將失權的時限即使精簡版也要列**（這是律所報表的命脈）。

### 對話詳細版

在對話中以 markdown 呈現完整報表。

### 檔案匯出

使用者要求「匯出」「完整版」「Excel」「PDF」時，使用 office skill 產出檔案：

| 格式 | 使用的 Skill | 適用場景 |
|------|-------------|---------|
| .xlsx | xlsx skill | 月報、案件 / 時限明細表（含公式和格式） |
| .pdf | pdf skill | 正式彙總報告 |
| .docx | docx skill | 內部正式文件 |

操作流程：
1. 用 MCP tool 撈取數據（`list_upcoming_deadlines`、`list_matters`、`list_tasks`、`list_leave_requests` 等）
2. 整理成結構化資料
3. 載入對應的 office skill → 按 SKILL.md 流程產出檔案
4. 檔案產出到 `data/media/exports/` 目錄，命名格式：`{日期}_{報表名}.{格式}`
   例如：`data/media/exports/2026-06_月報.xlsx`
5. 回報：「報表已產出：{檔案路徑}」

> ⚠️ **去識別化**：匯出檔若要離開本地（寄出 / 上傳雲端 / 貼進外部行事曆），比照 legal-admin 隱私標準——當事人名 / 案由屬機密，外流前先去識別化（案件代號代替）。對內留存的明細表可含真名。原則見 CLAUDE.md〈反捏造原則〉與 legal-admin `privacy-deploy.md`、`calendar-sync.md`。

Python 環境：`.venv/bin/python3`（已安裝 openpyxl、pypdf、python-pptx 等依賴）

---

## 五、推送時機（非系統排程）

**report-gen 這份報表沒有自己的排程器、也不會定時推 LINE。** 律所唯一的系統定時推送是 legal-admin 的「每日彙整今日工作事項」（cron `scan_deadlines.py` + 每日彙整、推全所一份，見 legal-admin `daily-digest.md`）；那是「漏不掉」的時限倒數命脈、由基建保證層跑，**不靠 agent 開著 Claude**。

report-gen 報表一律是「使用者要求時產出」，或在**啟動流程**被觸發時由 agent 自行判斷該不該主動提一句、屬 agent 後續動作而非系統定時任務：
- 日報：使用者要求時產出；agent 在啟動流程若判斷今天還沒給過、可主動提
- 週報：使用者說「週報」時產出；agent 可在週末前後判斷要不要提醒
- 月報：使用者說「月報」時產出；agent 可在月初判斷要不要提醒

要做到「每週固定推週報 / 每月 1 日推月報」這類定時推送、需等未來補上排程器；現況靠 agent 在被喚醒（啟動 / 收到 LINE 訊息）的當下判斷。**注意分清楚**：時限的每日倒數彙整**已有** cron 保證（legal-admin），缺的只是 report-gen 這種「週 / 月統計報表」的定時推送。

---

## Do's and Don'ts

### Do
- 數據全來自 DB，找不到的區塊標注「無資料」而非跳過
- 每個指標附帶至少一個比較（上月 MoM、目標值）
- 不只報數字，要給洞察和可能原因
- 逾期 / 即將失權的時限一律標 🔴 列最前、附法條依據與承辦律師
- 時限的內部期限 + 法定期限 **兩個都列**，叫律師盯「內部期限」、把「法定期限」當底線

### Don't
- 不要編造數字或推測沒有資料支撐的趨勢
- **不要在報表裡心算 / 重算任何法定時限天數**——只搬 `list_upcoming_deadlines` 既有的雙日期與 `statutory_basis`（算天數是時限引擎 `create_deadline` 的事，見 legal-admin `deadline-intake.md`）
- 不要發明台灣法律細節（法條 / 天數 / 法院規則）；報表只引用引擎已附的 `statutory_basis`，不自己補充法律解釋
- 不要跳過數據為零或找不到資料的區塊
- 不要在資料不足 2 個月的情況下做趨勢分析
- 不要做純讀取以外的操作（report-gen 不寫入、不標 filed、不建時限）

## 快速參考

### 日報
1. `get_context_summary(scope='full')` — 系統全貌（含待確認時限 / 掃描失聯哨兵）
2. `list_upcoming_deadlines(within_days=7)` — 7 日內到期 + 逾期時限（按內部期限升冪、含 `statutory_basis`，**只列不算**）
3. `list_tasks(status='pending')` + `list_tasks(status='done')` — 案件待辦完成 / 新增 / 明日到期（任務的 `due_date` 與法定時限天數**零關係**）
4. 整理成日報格式 → LINE 推送或回覆

### 週報
1. `list_tasks(status='done')` + `list_tasks(status='pending')` — 待辦統計
2. `list_matters(status='open')` — 在辦案件、本週新建
3. `list_upcoming_deadlines(within_days=14)` — 下週時限（只搬雙日期，逾期 / red 排前）
4. `list_pending_leave_requests()` — 待簽請假
5. 整理含「🔑 重點事項」和「📋 下週重點」

### 月報 + 匯出
1. `list_tasks()` — 待辦月度統計
2. `list_matters()` / `list_deadlines`（篩 filed）— 案件與書狀遞交統計
3. `knowledge_changelog(days=30)` + `lint_knowledge()` — 知識庫變更 / 健檢
4. 需要匯出 → 載入 xlsx skill → 產出到 `data/media/exports/`（外流前去識別化）

---

## 六、注意事項

- 純讀取，不做寫入
- 數據全來自 DB，不要編造
- 找不到資料的區塊標注「無資料」而非跳過
- 跟 ops-dashboard 的差異：dashboard 是即時快照，report-gen 是期間彙總
- 一般待辦的趨勢分析至少需要 2 個月以上的資料才有意義
- **時限永遠是引擎事實、報表只讀**：報表中的內部 / 法定雙日期、法條依據、`[需人工複核]` / `[已逾內部期限]` 標記，全部沿用 `list_upcoming_deadlines` / `get_deadline` 回傳的既有值，report-gen **不重算、不補法律解釋**。律師質疑某筆日期算對不對時，給他看 `get_deadline` 的 `calc_trace`（見 legal-admin `matter-query.md`），不要在報表裡自己解釋演算法。
- **floor 可見度（個人律所通常 inert）**：個人律所多半不設 `SME_FLOOR`（全權限單人、看全部），floor / `confidential` 為**保留 inert** 的升級路（見 CLAUDE.md〈部門安全層（floor）與兩道牆〉、legal-admin SKILL〈安全執行模型〉）。**若未來啟用受限層**：機密案件（`matters.confidential`）之時限在非全權限層不可見，`list_upcoming_deadlines` / `get_deadline` 會收斂——此時報表產不出機密案件的時限屬正常（呈現「本層不可見」、非當缺資料）。知識區塊方面，**只有 `query_knowledge` 保證機密過濾**；`knowledge_changelog` / `lint_knowledge` 不做 floor 過濾，月報的「知識變更 / 健檢」一律在全權限層產出。
