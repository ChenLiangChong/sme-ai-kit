---
name: company-ops
description: "公司營運技能包。當使用者或 LINE 訊息涉及以下情境時自動載入：管理任務、查詢或調整庫存、記帳記支出、經營客戶、處理訂單、發送 LINE 通知、查看營運狀態儀表板、產出報表、處理新人報到、設定公司規則。"
---

# 公司營運技能包 (Company Ops)

一站式企業營運管理 — 11 個功能模組，按需載入。

## 模組總覽

| 模組 | 檔案 | 觸發情境 |
|------|------|---------|
| 營運儀表板 | [ops-dashboard.md](references/ops-dashboard.md) | 「目前狀況」「今天有什麼事」「營運報告」 |
| 任務管理 | [task-ops.md](references/task-ops.md) | 建立/指派/追蹤/完成任務 |
| 知識萃取 | [knowledge-capture.md](references/knowledge-capture.md) | 系統導入/老闆分享規則/SOP/決策 |
| 客戶管理 | [crm-ops.md](references/crm-ops.md) | 新增/查詢/分析客戶、行銷觸及 |
| 訂單管理 | [order-ops.md](references/order-ops.md) | 下單/出貨/品檢/收款/退貨 |
| 庫存管理 | [inventory-ops.md](references/inventory-ops.md) | 查庫存/進出貨/盤點/警報 |
| 帳務管理 | [accounting-ops.md](references/accounting-ops.md) | 記帳/報銷/收支查詢/應收帳款 |
| LINE 通訊 | [line-comms.md](references/line-comms.md) | 推播/廣播/回覆/訊息處理 |
| 品牌語氣 | [brand-voice.md](references/brand-voice.md) | 對外文案/信件/行銷內容 |
| 報表生成 | [report-gen.md](references/report-gen.md) | 日報/週報/月報 |
| 新人導引 | [onboarding.md](references/onboarding.md) | 新員工設定/教學/LINE 綁定 |

## 常用工作流

1. **早安開工**：ops-dashboard → 看有什麼事 + 逾期帳款 → 逐一處理
2. **LINE 訊息處理**：line-comms → 辨識身份 → 根據內容調用對應模組 → 回覆或 mark_read
3. **訂單處理**：crm-ops（查客戶）→ inventory-ops（確認庫存）→ order-ops（建單→QC→出貨）→ accounting-ops（記帳→收款）→ line-comms（通知客戶）
4. **客戶行銷**：crm-ops（選客群）→ brand-voice（套語氣）→ line-comms（發送）
5. **月底結帳**：accounting-ops（核對收支）→ inventory-ops（盤點）→ report-gen（出報表）
6. **知識建檔**：knowledge-capture（訪談）→ 寫入 DB → 所有模組自動受益
7. **新人報到**：onboarding（註冊+綁定）→ task-ops（分配訓練任務）

## 品質檢核

- [quality_checklist.md](references/quality_checklist.md) — 格式確認、內容審計、readiness 判定

## 使用方式

- 直接描述你要做的事，系統會自動載入對應模組
- 不需要記模組名稱或指令
