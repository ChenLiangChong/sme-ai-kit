# Quality Checklist — company-ops（律所版）

最後更新：2026-06-07（legal-admin branch 全律所化 reframe）

> 本檔是 **company-ops 技能包自身的品質檢核清單**（dev / 維護者用、非 agent runtime 載入、不列入 CLAUDE.md / SKILL.md 模組表）。
> 本 branch 已把 company-ops 從通用 SME 改寫成**律師事務所所內營運橫向層**；檢核項依此調整。

---

## 模組集（律所版、8 個 reference）

保留並已律所化：`setup` / `ops-dashboard` / `task-ops` / `knowledge-capture` / `leave-ops` / `line-comms` / `report-gen` / `onboarding`。

**已刪除（依 `docs/legal/SPEC.md`〈不做〉— 移出產品 / 不適用律所）**：
- `order-ops`（訂單）、`inventory-ops`（庫存）：律所無實體商品 / 出貨 / 庫存鏈。
- `accounting-ops`（記帳 / 會計 / 信託帳）：SPEC 移出產品；信託帳系統無原生支援、寫進文件＝反捏造。
- `crm-ops`（完整 CRM）：當事人只需 `matters.client_name` 輕量查詢（走 legal-admin matter-query）。
- `brand-voice`（對外行銷文案）：律師倫理限制廣告招攬、所內專用無對外通道。

---

## 格式 / 結構確認

| 檢查項 | 結果 | 備註 |
|--------|------|------|
| SKILL.md 模組表 = 8 模組、連結正確 | ⬜ | 砍掉 order/inventory/accounting/crm/brand-voice 五列 |
| description frontmatter 無 SME 觸發詞 | ⬜ | 不得殘留 庫存 / 下單 / QC / 出貨 / 退貨 / 廣播 / Flex 行銷 / 多事業體；與 legal-admin 觸發明確分工 |
| 各 reference 有明確觸發情境 | ⬜ | |
| 語言一致（繁體中文） | ⬜ | |
| 對 5 個已刪模組零交叉引用 | ⬜ | `grep -rE 'crm-ops|order-ops|inventory-ops|accounting-ops|brand-voice'`（排除「已移出」說明句） |

---

## 律所版內容稽核（反捏造為一級）

| 維度 | 要求 |
|------|------|
| **反捏造 — 不宣稱不存在的能力** | 文件**絕不**宣稱：信託帳負值阻擋 / per-當事人餘額 / 利益衝突自動偵測 / `update_matter`（不存在）/ deadline 重指派工具（不存在）。離職案件 / 時限交接走 `store_fact` 記錄 + `create_task` + 人工。 |
| **反捏造 — 法律事實** | 法條 / 期間天數 / 在途**絕不出現在 company-ops 文件**；一律 legal-admin 引擎確定性計算附 `statutory_basis`。dashboard / report 只「讀取」、不重算。 |
| **天數語意硬邊界** | `task.due_date` / `leave_request.days` 檔首聲明「**≠ 法定時限**」（task-ops / leave-ops 對稱、交叉引用 legal-admin）。 |
| **核心機制原樣保留** | floor 兩道牆 / SME_FLOOR 三態 / escalation 上報 / actor 身份信任 / HITL gate（resume_params + consumed_at）/ 機密軸 / 知識寫入 flow / context 壓縮恢復＝領域無關、一字不改義（只改領域範例）。 |
| **單一律所定位** | `business_unit` 多事業體軸退化、留空 inert；個人律所不設 `SME_FLOOR`（floor 分支標「多人版才適用」、非主敘述）。 |
| **所內專用** | 無對外通道：非所內名冊不回覆業務內容；無陌生人意圖分層路由、無對外行銷 / 廣播；委任人約諮詢走電話人工建（不在 LINE 開委任人對話）。 |
| **誠實邊界** | floor 案件列級過濾（#11）未落地 → 不可宣稱「部門層只查得到自己案件」。 |

---

## 驗收（對齊決策 #186 三層）

| 維度 | 評級 | 工具 |
|------|------|------|
| 覆蓋率（工具 / 流程都有文件） | ⬜ | — |
| 觸發率（情境正確路由到模組） | ⬜ | `~/.claude/skills/skill-creator-advanced/run_eval.py`（claude -p 訂閱、跑前 `env -u ANTHROPIC_API_KEY`；company-ops 是路由型、拆包級 + 模組級） |
| 流程正確（mechanism 不丟、反捏造） | ⬜ | codex 覆審 + 本清單反捏造維度 |

> 本輪 reframe：Workflow draft→對抗驗證跑 7 個 reference（6 PASS + onboarding.md 抓到 `update_matter` 捏造、已手修）；knowledge-capture 另由手改、CLAUDE.md / SKILL.md 手改後經 codex 覆審（機制無改義 / 無捏造 / SPEC 對齊）。company-ops 現共 **8 reference + 本檔**。上線前再跑觸發率 eval。
