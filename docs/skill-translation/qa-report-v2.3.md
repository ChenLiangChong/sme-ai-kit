# skill 翻譯 QA 報告 v2.3

本次依使用者列出的目標清單審查 `references/` 內 21 檔 `.md`（排除 `taiwan-market.md`），並以 `style-guide.md`、`term-gloss.md`、`terminology.md` 為準。

## ✅ 完全通過

- `analytics.md`
- `content-production.md`
- `copy-editing.md`
- `copywriting.md`
- `email-outreach.md`
- `line-marketing.md`
- `pmm-competitive.md`
- `pmm-gtm.md`
- `pmm-pricing.md`
- `retention.md`
- `social-analytics.md`
- `social-content.md`

## 🔴 必修

| 檔名 | 行號 | 問題描述 | 建議修法 |
|------|------|----------|----------|
| `competitive-content.md` | 328, 369 | `Social Proof` 在同檔前文用的是 `社群背書`，此處改成 `社群證明`，與 `term-gloss.md` / 同檔其他段落不一致。 | 統一改為 `Social Proof（社群背書）`；相關敘述一併改為「社群背書」。 |
| `growth-loops.md` | 573-575, 666-668 | 表格中的 `TOFU / MOFU / BOFU` 為全大寫英文 label，命中本輪「全大寫英文 label」必修條件。 | 首次出現改為中文主標加英文註記，例如 `問題認知（TOFU）`、`解法認知（MOFU）`、`高意圖轉換（BOFU）`，後文統一沿用。 |
| `marketing-ops.md` | 9 | 品牌名寫成 `META`，與其餘檔案一律使用 `Meta` 不一致。 | 改為 `Meta 廣告管理員`。 |
| `paid-acquisition.md` | 267 | code block 內的 `AD SET NAME` 為全大寫英文 label，命中必修條件。 | 改為中文主標加 Title Case 英文，如 `廣告組名 (Ad Set Name)`。 |
| `paid-acquisition.md` | 351-353 | 命名範例保留全大寫前綴 `META_...`，與同檔「避免全大寫」規則衝突，也命中全大寫 label 檢查。 | 改為一致的 Title Case 或小寫命名示例，例如 `Meta_Conv_...` / `meta_conv_...`，並與命名規則同步。 |
| `pmm-launch.md` | 155-162 | `GO / NO-GO` 為表格中的全大寫英文 label，命中必修條件。 | 改為 `可上線 (Go)` / `不可上線 (No-Go)`，其餘引用處同步。 |
| `pmm-market.md` | 120 | 連到 `pmm-gtm.md` 時寫成 `International Expansion`，但目標檔實際章名是 `國際市場拓展`，屬跨檔不一致。 | 改為 `詳見 pmm-gtm.md 的「國際市場拓展」區段`。 |
| `pmm-messaging.md` | 3 | 首句的 `Proof Point`、`Persona` 首次出現未依規則補中文註解。 | 改為 `Proof Point（證據點）`、`Persona（人物誌）`。 |
| `pmm-patterns.md` | 143, 147-152, 227 | `STOP` 以全大寫英文 label 出現在段落與表格中，命中必修條件。 | 改為 `停止 (Stop)` 或 `先停止並呈報 (Stop)`，全檔統一。 |
| `pmm-patterns.md` | 187, 194, 197 | `ORCHESTRATOR` / `OPERATOR` 為全大寫英文 label，命中必修條件。 | 改為 `Orchestrator（協調者）`、`Operator（操作者）`，並保留中英並陳。 |
| `pmm-positioning.md` | 33-38, 212 | 模板中的 `FOR / WHO / THE / IS A / THAT / UNLIKE / OUR PRODUCT` 仍是全大寫英文 label，命中必修條件。 | 全數改為中文在前、Title Case 英文在括號，例如 `為 (For)`、`其 (Who)`、`該 (The)`、`屬於 (Is A)`、`提供 (That)`、`相較於 (Unlike)`、`我方產品 (Our Product)`。 |

## 🟡 建議修正

| 檔名 | 行號 | 問題描述 | 建議修法 |
|------|------|----------|----------|
| `pmm-positioning.md` | 67-73 | 第三種品類策略寫成 `Create New Category`，與 `term-gloss.md` 的 `Category Creation（開創新品類）` 不一致。 | 改為 `開創新品類（Category Creation）`，範例與後文同步。 |

## 結論

本輪仍有多個 `🔴 必修`，且已命中本次最嚴格審查重點中的：

- 全大寫英文 label
- 術語首次出現漏中文註解
- 跨檔不一致

可以上線：否
