# 每日彙整（daily digest）— 核心 loop 的步驟 3 後半

> 觸發：每天固定時間的「今日工作事項」推播；律師問「今天有哪些時限要盯」「這週有什麼到期」；逾期提醒。
> 設計原則：**全所一份彙整**（不是 per-律師分送）；時間驅動（人沒開 Claude 也在倒數）。

## 兩條投遞路徑（你只負責「彙整內容」、投遞是基建在做）

時限提醒走既有 escalation **三層投遞**（見 CLAUDE.md〈上報（escalation）機制〉），你不用自己接：

1. **保證層（主）** —— OS cron `scan_deadlines.py` 每日跑（部署在 host、crontab 07:00），純讀 `deadlines` 表 pending 列 → 命中 `escalation_lead_days` 提醒節點 / 逾期 → `enqueue_escalation`（與業務寫入同一原子 commit）。收件人走 `resolve_escalation_target`（boss/全所）、`channel_id=None`（BU→OA 解析）。**全所一份**。
2. **品質層** —— `claude -p` single-shot notifier 把 enqueue 的乾資料潤成自然語言推播。

> 你（互動 session）的角色：被律師**主動問**「今天有什麼」時，現算現答（下方流程）；或部署/維護 cron。**自動倒數不靠你開著 Claude**。

## 互動式彙整（被問「今天有哪些時限」時）

1. `list_upcoming_deadlines(within_days=7)` —— 列出 pending 時限、按**內部期限升冪**（最急在前），每筆並陳內部期限（盯這個）＋法定期限（底線）＋法條依據。
2. 標示這幾類，律師一眼看出輕重：
   - **已逾內部期限** → `[已逾內部期限]`（最高優先、評估回復原狀）
   - **需人工複核** → `[需人工複核]`（送達/在途/法版/教示比對有疑義、別當已確定）
   - 嚴重度 red（不變期間失權硬倒數）排前面
3. 交叉行事曆（見 calendar-sync）：cron 版會讀「事務所慣用行事曆」當天/近期事件（涵蓋我們寫的 + 律師手動加的庭期）+ 交叉 `deadlines` 表補法條/雙日期，避免漏掉只記在行事曆沒進系統的庭期。

## 彙整訊息範例（全所一份）

```
【今日工作事項 2026-06-15】
■ 失權硬倒數
- [#23] 2026-民-014 王案 上訴期限：內部 6/18（法定 6/21·民訴§440）剩 3 個工作日 承辦：林律師
■ 需人工複核
- [#27] 2026-刑-003 陳案 抗告：[需人工複核 法版] 判決日早於刑訴§406 修法、請確認適用 5 或 10 日
■ 本週庭期（行事曆）
- 6/17 10:00 北院 M-2026-014 言詞辯論
```

## 逾期處理（最高優先）

時限 `days_left < 0` → cron 每日推 `deadline_missed`、升級 boss。回報時務必帶**回復原狀**備援（`get_deadline` 的 `recovery_window`）：
- 民事 民訴§164：遲誤非因過失、原因消滅後 10 日內聲請回復原狀 + 補行訴訟行為、距末日逾 1 年不得聲請。
- 刑事 刑訴§67：遲誤非因過失、原因消滅後 10 日內聲請 + 同時補行。

**逾期是執業過失高風險區**——立刻通知主持律師、不要只記一筆了事。

## 失敗情境判讀

- **cron 沒推但時限明明快到** → 查 `scan_deadlines.py` 是否在跑（crontab）、`deadlines.escalation_lead_days` 提醒節點是否含當前 days_left、`reminders_sent` 是否已記過該節點（同節點不重推）。
- **enqueue 了但沒送達** → `list_pending_escalations` 看 `failed`/逾期未送；收件人 coalesce 失敗（查無 boss）會留 pending、提醒維護者種 boss 身份（見 privacy-deploy）。
- **行事曆有庭期但系統沒提醒** → 那筆只在行事曆、沒進 `deadlines`。把它補建（庭期見 deadline-intake「開庭通知」）或靠 cron 讀行事曆交叉補上。
