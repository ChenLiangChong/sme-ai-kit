---
name: company-ops
description: "律師事務所所內營運 AI 助理（business-db MCP 驅動，所內專用、單一律所）。適用於：所內案件任務與行政待辦的指派/追蹤、所務規則 SOP/決策萃取、導入新律所（訪談建檔）、律師/助理/行政人員請假/查餘額/簽核/年度配額、所內 LINE 推播/通知/訊息處理、所務儀表板/「今天有什麼事」/「目前狀況」、日報週報月報、新進人員到職/LINE 綁定/離職、所長說規則 SOP 要存、HITL 簽核（核准 #N 駁回）、部門安全層（floor）啟動、上報通知、機密規則、權限分層；產出透過 business-db / line MCP 工具操作、必走 HITL gate、LINE 訊息必有結局（reply / mark_read）。**算法定時限/上訴抗告答辯補正期限/建案件 matter/收判決書裁定抽取到期日/委任人諮詢預約 → 用 legal-admin 技能包**。不適用於：純寫程式、改 skill、視覺設計或投影片（用 sme-design）。"
---

# 事務所營運技能包 (Company Ops)

事務所**所內**營運管理的橫向基建 — 多個功能模組，按需載入。
背後由 `business-db` MCP 驅動，覆蓋知識/SOP、案件任務與行政待辦、人員（律師/助理/行政）、審核、請假、所內 LINE 整合、會話交接、部門安全層（floor）、上報（escalation）等領域。單一律所、所內專用，不做多事業體、無對外通道。

> **與 legal-admin 的分工**：本包是「橫向所務行政層」（任務/SOP/人員/請假/報表/儀表板/所內 LINE）。**案件（matter）、法定時限計算、判決書/裁定收件抽取、委任人諮詢預約、行事曆同步、去識別化** 屬垂直核心，一律走 **`legal-admin` 技能包**——本包的儀表板/報表只是「讀取」legal-admin 算好的時限來呈現、**絕不自己算法定天數**。

## 模組總覽

| 模組 | 檔案 | 觸發情境 |
|------|------|---------|
| 環境設定 | [setup.md](references/setup.md) | 首次上線 / 所內 LINE 未設定 / MCP 連線問題 |
| 營運儀表板 | [ops-dashboard.md](references/ops-dashboard.md) | 「目前狀況」「今天有什麼事」「所務概況」 |
| 任務管理 | [task-ops.md](references/task-ops.md) | 建立/指派/追蹤所內案件任務與行政待辦 |
| 知識萃取 | [knowledge-capture.md](references/knowledge-capture.md) | 導入新律所 / 所長分享所務規則 SOP / 決策 |
| 請假管理 | [leave-ops.md](references/leave-ops.md) | 律師/助理/行政請假 / 查餘額 / 簽核 / 年度配額 |
| LINE 通訊 | [line-comms.md](references/line-comms.md) | 所內 LINE 訊息處理 / 推播 / 回覆 |
| 報表生成 | [report-gen.md](references/report-gen.md) | 日報/週報/月報（案件待辦/時限/任務） |
| 人員導引 | [onboarding.md](references/onboarding.md) | 新進律師/助理/行政設定 / LINE 綁定 / 離職 |

> 案件查詢、收件算時限、諮詢預約、行事曆、隱私部署等情境 → 載入 `.claude/skills/legal-admin/` 對應 reference。

## 安全執行模型（載入本技能包先意識到）

本技能包在 LINE-runtime 下可能跑在**受限部門 session（有 `SME_FLOOR`）**，並非總是全權限環境（個人律所預設不設 floor、全權限單人；增員或多人所才分層）。處理任何情境前先記住下列分層事實（細節各以一句話交叉引用，不在此重述機制）：

- **floor 分層執行**：部門層被兩道牆框住，工具白名單與可讀資料受限（見 CLAUDE.md〈部門安全層（floor）與兩道牆〉）。被工具白名單擋下時是預期行為、不是系統錯誤。個人律所不設 `SME_FLOOR` 時這層全程 inert。
- **通知 / 簽核走上報**：要通知所長 / 簽核人時，floored 層不一定撈得到對方 `user_id`、也不一定 push 得到——一律走上報（escalation）機制或由全權限層處理，不要自己撈 `role=boss` 去 reply（見 CLAUDE.md〈上報（escalation）機制〉、line-comms〈執行模型〉）。
- **HITL gate**：請假簽核（`approve_leave`）走 gate（resume_params 比對 + consumed_at 單次消費）；到期日確認 / 對法院遞交的 HITL 由 legal-admin 走 approval。不要 agent 手寫繞過（見 CLAUDE.md〈HITL 審核〉）。
- **知識有機密軸**：`store_fact` 預設員工可見、`log_decision` 預設機密；非全權限層 `query_knowledge` 會過濾掉機密規則（見 CLAUDE.md〈機密軸（confidential）〉）。導入訪談碰到收費/HR/策略類答案要明確 `confidential=True`。
- **actor 身份**：floored session 的 actor 由系統取 line-channel 驗過的 `user_id`、**agent 自填的值會被忽略**；不可逆人事動作具名 actor + 權限關卡已落實（#10）：`update_employee` 需 admin、audit 記 verified 操作者名，operator（無 floor）為全權限路徑（見 CLAUDE.md〈actor 身份信任〉）。

## 常用工作流

1. **早安開工**：ops-dashboard → 看待處理任務 / 待確認到期日 / 即將到期法定時限 / 待簽請假 / 掃描器健康 → 逐一處理
2. **LINE 訊息處理**：line-comms → 辨識 OA（`channel_id`；單一律所通常只有一個所內 OA）→ 辨識身份（所內名冊：律師/助理/行政）→ 依內容調用對應模組 → 回覆（帶回同一個 channel_id）或 mark_read
3. **收檔算時限**（垂直核心，走 legal-admin）：律師/助理在 LINE 傳判決書/裁定/通知 → `legal-admin` 的 deadline-intake（讀檔→抽送達日→**一鍵確認才入**→引擎確定性算法定+內部雙日期→寫行事曆→每日彙整）
4. **知識建檔**：knowledge-capture（訪談 / 被動捕捉）→ 寫入 DB（全域或機密規則）→ 所有模組自動受益
5. **新人報到**：onboarding（建檔 + 綁定 LINE）→（選用）leave-ops 分配年度配額 → task-ops（分配訓練任務）
6. **人員請假**：leave-ops（`request_leave`）→ HITL gate（CLAUDE.md HITL 章節）→ 主管 LINE 核准 → `approve_leave` 原子扣餘額 → line-comms 通知（通知 / 執行可能跨 session（全權限層）、見 line-comms〈執行模型〉）
7. **彙整 / 報表**：report-gen（日報/週報/月報、純讀取）或 legal-admin daily-digest（每日工作事項推全所）

## 單一律所說明

本版定位為**單一律師事務所、所內專用**：`business_unit`（多事業體）軸**退化、預設留空**（保留為 inert 升級路，與 `pleading-manager` 合併版或多所/分所時再啟用，不從程式移除）。所有建立/查詢資料時 `business_unit` 留空即可；如該所要以「執業領域（民事/刑事/家事…）」分項，可在建案時用 legal-admin `matters.practice_area`，與本包橫向工具無關。

## 工具參數注意

- **日期一律傳實際 `YYYY-MM-DD`**：`create_task.due_date`、`request_leave` 的 `start_date`/`end_date`、`list_tasks` / `list_deadlines` 的日期篩選等日期欄位，工具**不解析**「今天 / 下週 / 一週後」這類自然語言——agent 要先換算成實際 `YYYY-MM-DD` 字串再傳（範例裡 `<… YYYY-MM-DD>` 佔位就是提醒這點）。
- **`task.due_date` ≠ 法定時限**：任務的 due_date 是內部行政提醒，上訴/抗告/答辯/補正等**法定期限一律走 legal-admin `create_deadline`**（確定性計算附 `statutory_basis`），絕不建成 task（見 task-ops 檔首硬邊界）。

## 品質檢核（dev / 維護者用、非 agent runtime 載入）

- [quality_checklist.md](references/quality_checklist.md) — 格式確認、內容審計、readiness 判定。本 skill 包自身的健康檢查清單、給文件編修者跑、不在業務情境自動載入（CLAUDE.md Skills 模組表不含此檔）

## 使用方式

- 直接描述你要做的事，系統會自動載入對應模組
- 不需要記模組名稱或指令
