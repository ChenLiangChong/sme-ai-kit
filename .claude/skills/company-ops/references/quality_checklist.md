# Quality Checklist — company-ops

最後更新：2026-04-03

---

## 格式確認

| 檢查項 | 結果 | 備註 |
|--------|------|------|
| format_check.py | ✅ 0 error, 0 warning | |
| quick_validate.py | ✅ valid | |
| audit_unreferenced_files.py | ✅ 0 issues (11 referenced / 11 files) | order-ops.md 已加入 |
| audit_skill_references.py | ✅ 0 issues | |
| Frontmatter name/description | ✅ | description 用雙引號避免 YAML `>` 問題 |
| Trailing whitespace | ✅ 已修復 | knowledge-capture.md, report-gen.md |

---

## 要求/規範確認

| 項目 | 狀態 | 備註 |
|------|------|------|
| SKILL.md 有模組表格 | ✅ | 11 個模組（含 order-ops），連結語法正確 |
| 每個 reference 有明確觸發情境 | ✅ | |
| 語言一致（繁體中文） | ✅ | |
| MCP tool 名稱正確 | ✅ | line-comms.md `get_line_quota` 已移除，改為手動查詢說明 |
| 跨模組 handoff 清楚 | ✅ | inventory-ops 第四節已補進貨→記帳串接；order-ops 第十節有完整交互表 |
| 品牌語氣裝飾器定位被其他模組尊重 | ✅ | crm-ops、line-comms、report-gen、onboarding 正確引用 |
| 啟動流程一致性 | ✅ | ops-dashboard 已與 CLAUDE.md 啟動流程對齊 |
| LINE 處理流程一致性 | ✅ | line-comms 已與 CLAUDE.md LINE 訊息處理完全一致 |
| 催收邏輯一致性 | ✅ | accounting-ops 帳齡表與自動催收已統一，無矛盾 |

---

## 內容審計發現（2026-04-03）

### 🔴 嚴重（全部已修正）

1. ~~**訂單管理流程完全缺席**~~ → ✅ 已新增 order-ops.md（11 節完整指南：生命週期、建單、確認、QC、出貨、到貨、收款、退貨、查詢、跨模組交互）
2. ~~**`get_line_quota` 工具不存在**~~ → ✅ line-comms.md 第九節已改為手動查詢說明（LINE MCP 尚未支援 quota API）
3. ~~**accounting-ops HITL 矛盾**~~ → ✅ 第一節已修正：明確審核判斷由 AI 負責，`record_transaction` 不自動攔截

### 🟡 中等（全部已修正）

4. ~~缺少 `update_employee` tool~~ → ✅ 已新增，CLAUDE.md 和 onboarding.md 都正確引用
5. ~~進貨與記帳跨模組串接缺失~~ → ✅ inventory-ops 第四節步驟 5 已補完整進貨記帳流程
6. ~~`check_overdue` 未被任何模組引用~~ → ✅ 已在 ops-dashboard、accounting-ops、order-ops 中引用
7. ~~`save_session_handoff`、`add_attachment`、`list_attachments` 未被引用~~ → ✅ save_session_handoff 在 CLAUDE.md；add_attachment 在 crm-ops、order-ops、task-ops、inventory-ops、accounting-ops
8. ~~RFM 的 Frequency 資料來源不明~~ → ✅ crm-ops 已加註使用 `list_orders` 統計訂單筆數
9. ~~report-gen 引用不存在的 `xlsx` skill~~ → ✅ 已改為引用 xlsx/pdf/docx skill（皆存在）
10. ~~task-ops 的 `blocked` 狀態需確認 DB schema~~ → ✅ 已改為 `[BLOCKED]` 描述標記法，不依賴 DB 狀態欄

---

## 一致性修正記錄（2026-04-03）

| 修正項 | 涉及檔案 | 說明 |
|--------|---------|------|
| 啟動流程對齊 | ops-dashboard.md | 加入首次啟動判斷（Step 2），與 CLAUDE.md 完全一致 |
| LINE 處理流程對齊 | line-comms.md | 第一步~第四步重寫，與 CLAUDE.md 完全一致；陌生人處理段同步 |
| 權限不足回覆統一 | line-comms.md | 改為「這個操作需要主管權限。」（去掉多餘的「請聯繫」） |
| 權限表統一 | line-comms.md | 移除「對應模組」欄，合併「回報進度」和「建立任務」，與 CLAUDE.md 一致 |
| register_employee 參數 | onboarding.md | 資訊收集清單補上 permissions 參數說明 |
| 催收邏輯統一 | accounting-ops.md | 帳齡表設為主表，自動催收改為引用帳齡表的摘要，消除門檻矛盾 |

---

## 最終判定

| 維度 | 評級 |
|------|------|
| 格式合規 | ✅ PASS |
| 內容品質 | ✅ A（3 個嚴重 + 7 個中等問題全部已修正） |
| 跨模組一致性 | ✅ PASS（CLAUDE.md 與各模組完全對齊） |
| 整體 Readiness | ✅ PASS |
