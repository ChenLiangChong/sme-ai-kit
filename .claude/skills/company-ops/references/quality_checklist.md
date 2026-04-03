# Quality Checklist — company-ops

最後更新：2026-04-03

---

## 格式確認

| 檢查項 | 結果 | 備註 |
|--------|------|------|
| format_check.py | ✅ 0 error, 0 warning | |
| quick_validate.py | ✅ valid | |
| audit_unreferenced_files.py | ✅ 0 issues (10 referenced / 10 files) | |
| audit_skill_references.py | ✅ 0 issues | |
| Frontmatter name/description | ✅ | description 用雙引號避免 YAML `>` 問題 |
| Trailing whitespace | ✅ 已修復 | knowledge-capture.md, report-gen.md |

---

## 要求/規範確認

| 項目 | 狀態 | 備註 |
|------|------|------|
| SKILL.md 有模組表格 | ✅ | 10 個模組，連結語法正確 |
| 每個 reference 有明確觸發情境 | ✅ | |
| 語言一致（繁體中文） | ✅ | |
| MCP tool 名稱正確 | 🟡 | line-comms.md 引用不存在的 `get_line_quota`（見內容審計） |
| 跨模組 handoff 清楚 | 🟡 | 進貨/記帳跨模組串接未明確 |
| 品牌語氣裝飾器定位被其他模組尊重 | ✅ | crm-ops、line-comms、report-gen、onboarding 正確引用 |

---

## 內容審計發現（2026-04-03）

### 🔴 嚴重

1. **訂單管理流程完全缺席** — 7 個 order 相關 MCP tool 無人引用（create_order, get_order, list_orders, update_order, fulfill_order, qc_order, record_payment）
2. **`get_line_quota` 工具不存在** — line-comms.md 第八節引用了不存在的工具
3. **accounting-ops HITL 矛盾** — 第一節暗示 `record_transaction` 自動攔截大額交易，但 CLAUDE.md 的 HITL 規則是 Claude 先判斷 → `create_approval` → 核准後才 `record_transaction`

### 🟡 中等

4. 缺少 `update_employee` tool，LINE 綁定和離職流程無法完成（onboarding.md）
5. 進貨與記帳的跨模組串接缺失（inventory-ops / accounting-ops）
6. `check_overdue` tool 未被任何模組引用（應在 task-ops 的到期提醒中使用）
7. `save_session_handoff`、`add_attachment`、`list_attachments` 未被引用
8. RFM 的 Frequency 資料來源不明（crm-ops）
9. report-gen 引用不存在的 `xlsx` skill
10. task-ops 的 `blocked` 狀態需確認 DB schema 支援

---

## 最終判定

| 維度 | 評級 |
|------|------|
| 格式合規 | ✅ PASS |
| 內容品質 | 🟡 B+（架構清晰，但有 3 個嚴重問題待修） |
| 整體 Readiness | ⏸️ CONDITIONAL — 修完 Top 3 嚴重問題後可 PASS |
