---
name: company-ops
description: "中小企業營運 AI 助理（business-db MCP 驅動）。適用於：庫存盤點、進出貨、記帳、月結、收支、應收應付、催款、退款、任務指派、待辦追蹤、客戶/供應商/經銷商/外包夥伴管理、下單、QC、出貨、退貨、員工請假、簽核、年度配額、LINE 推播、廣播、Flex Message、營運儀表板、「今天有什麼事」、日報週報月報、新員工到職、LINE 綁定、離職、老闆說規則 SOP 要存、HITL 簽核（核准 #N 駁回）、多事業體 business_unit 篩選、部門安全層（floor）啟動、上報通知、機密規則、權限分層；產出透過 business-db / line MCP 工具操作、必走 HITL gate、LINE 訊息必有結局（reply / mark_read）。不適用於：純寫程式、改 skill、視覺設計或投影片（用 sme-design）、純社群數據分析（用 social-media）。"
---

# 公司營運技能包 (Company Ops)

一站式企業營運管理 — 多個功能模組，按需載入。
背後由 `business-db` MCP 驅動，覆蓋知識 / 任務 / 員工 / 客戶 / 庫存 / 帳務 / 訂單 / 審核 / 請假 / 事業體 / LINE 整合 / 會話交接 等領域，支援多事業體（`business_unit`）與多 LINE OA。

## 模組總覽

| 模組 | 檔案 | 觸發情境 |
|------|------|---------|
| 環境設定 | [setup.md](references/setup.md) | 首次啟動 / LINE 未設定 / MCP 連線問題 |
| 營運儀表板 | [ops-dashboard.md](references/ops-dashboard.md) | 「目前狀況」「今天有什麼事」「營運報告」 |
| 任務管理 | [task-ops.md](references/task-ops.md) | 建立/指派/追蹤/完成任務 |
| 知識萃取 | [knowledge-capture.md](references/knowledge-capture.md) | 系統導入/老闆分享規則/SOP/決策 |
| 客戶管理 | [crm-ops.md](references/crm-ops.md) | 新增/查詢/分析客戶、行銷觸及 |
| 訂單管理 | [order-ops.md](references/order-ops.md) | 下單/出貨/品檢/收款/退貨 |
| 庫存管理 | [inventory-ops.md](references/inventory-ops.md) | 查庫存/進出貨/盤點/警報 |
| 帳務管理 | [accounting-ops.md](references/accounting-ops.md) | 記帳/報銷/收支查詢/應收帳款 |
| 請假管理 | [leave-ops.md](references/leave-ops.md) | 請假/排休/查餘額/簽核請假/分配年度配額 |
| LINE 通訊 | [line-comms.md](references/line-comms.md) | 推播/廣播/回覆/訊息處理 |
| 品牌語氣 | [brand-voice.md](references/brand-voice.md) | 對外文案/信件/行銷內容 |
| 報表生成 | [report-gen.md](references/report-gen.md) | 日報/週報/月報 |
| 新人導引 | [onboarding.md](references/onboarding.md) | 新員工設定/教學/LINE 綁定 |

## 安全執行模型（載入本技能包先意識到）

本技能包在 LINE-runtime 下可能跑在**受限部門 session（有 `SME_FLOOR`）**，並非總是全權限環境。處理任何業務情境前，先記住下列分層事實（細節各以一句話交叉引用，不在此重述機制）：

- **floor 分層執行**：部門層被兩道牆框住，工具白名單與可讀資料受限（見 CLAUDE.md〈部門安全層（floor）與兩道牆〉）。被工具白名單擋下時是預期行為、不是系統錯誤。
- **通知 / 簽核走上報**：要通知老闆 / 簽核人時，floored 層不一定撈得到對方 `user_id`、也不一定 push 得到——一律走上報（escalation）機制或由全權限層處理，不要自己撈 `role=boss` 去 reply（見 CLAUDE.md〈上報（escalation）機制〉、line-comms 第六節執行模型）。
- **超門檻記帳系統自建審核**：`record_transaction` 超過門檻時由系統自動建審核並上報，**不要 agent 手寫 `create_approval`**（見 CLAUDE.md〈HITL 審核〉）。
- **知識有機密軸**：`store_fact` 預設員工可見、`log_decision` 預設機密；非全權限層 `query_knowledge` 會過濾掉機密規則（見 CLAUDE.md〈機密軸（confidential）〉）。
- **actor 身份**：floored session 的 actor 由系統取 line-channel 驗過的 `user_id`、**agent 自填的值會被忽略**；不可逆動作具名 actor + 權限關卡已落實（#10）：`update_employee` 需 admin、`delete_transaction` 需 manager、audit 記 verified 操作者名，operator（無 floor）為全權限路徑（見 CLAUDE.md〈actor 身份信任〉）。

## 常用工作流

1. **早安開工**：ops-dashboard → 看有什麼事 + 逾期帳款 → 逐一處理
2. **LINE 訊息處理**：line-comms → 辨識 OA（channel_id / business_unit）→ 辨識身份 → 根據內容調用對應模組 → 回覆（記得帶回同一個 channel_id）或 mark_read
3. **訂單處理**：crm-ops（查客戶）→ inventory-ops（確認庫存，按事業體）→ order-ops（建單→QC→出貨，帶 business_unit）→ accounting-ops（記帳→收款）→ line-comms（通知客戶）（記帳 / 通知 / 執行可能跨 session（全權限層、財務工具落在有 financial_visibility 的層）、見 line-comms 第六節〈執行模型〉）
4. **客戶行銷**：crm-ops（選客群）→ brand-voice（套語氣）→ line-comms（發送）
5. **月底結帳**：accounting-ops（核對收支，可按事業體）→ inventory-ops（盤點）→ report-gen（出報表）
6. **知識建檔**：knowledge-capture（訪談）→ 寫入 DB（全域或事業體專屬規則）→ 所有模組自動受益
7. **新人報到**：onboarding（註冊+綁定 LINE，可指定 business_units）→（選用）leave-ops 分配年度配額 → task-ops（分配訓練任務）
8. **員工請假**：leave-ops（request_leave）→ HITL gate（CLAUDE.md HITL 章節）→ 主管 LINE 核准 → approve_leave 原子扣餘額 → line-comms 通知員工（通知 / 執行可能跨 session（全權限層）、見 line-comms 第六節〈執行模型〉）

## 多事業體提醒

所有建立／修改資料的操作，若是從 LINE 而來，都應從訊息 meta 的 `business_unit` 讀取並傳入對應 tool：`create_order`、`record_transaction`、`create_task`、`update_stock`、`store_fact` 等。查詢時也可按 `business_unit` 篩選：`check_stock`、`low_stock_alerts`、`check_overdue`、`monthly_summary`、`query_knowledge`、`list_orders`、`list_tasks`。客戶對事業體的折扣／付款條件用 `set_customer_entity_terms` 覆寫，詳見 order-ops 與 accounting-ops。

## 工具參數注意

- **日期一律傳實際 `YYYY-MM-DD`**：`create_task.due_date`、`update_order.estimated_delivery`、`list_transactions` 的 `start_date`/`end_date`、`record_transaction.due_date`、`request_leave` 的 `start_date`/`end_date` 等日期欄位，工具**不解析**「今天 / 下週 / 出貨日前一天 / 一週後」這類自然語言——agent 要先換算成實際 `YYYY-MM-DD` 字串再傳（範例裡 `<… YYYY-MM-DD>` 佔位就是提醒這點）。

## 品質檢核（dev / 維護者用、非 agent runtime 載入）

- [quality_checklist.md](references/quality_checklist.md) — 格式確認、內容審計、readiness 判定。本 skill 包自身的健康檢查清單、給文件編修者跑、不在業務情境自動載入（CLAUDE.md Skills 模組表不含此檔）

## 使用方式

- 直接描述你要做的事，系統會自動載入對應模組
- 不需要記模組名稱或指令
