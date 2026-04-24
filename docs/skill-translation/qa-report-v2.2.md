# QA Report v2.2

審核範圍：`.claude/skills/social-media/references/` 下 22 個 skill 檔（排除 `taiwan-market.md`）  
審核基準：`docs/skill-translation/style-guide.md`、`docs/skill-translation/term-gloss.md`  
審核方式：只讀複審，逐檔核對 v2.2 清單，不修改 skill 原檔

## 總結

本輪 **22 檔皆已覆蓋**。  
類別 A / B / C 的已修項目，本輪未發現回歸：

- 13 檔降級清單皆有 4 題（通用 3 題 + 專屬 1 題）
- `pmm-messaging.md` 已在第一個 `---` 後補上完整工具降級區塊
- `social-analytics.md` 已在「台灣市場適用指引」後補上完整工具降級區塊
- `pmm-competitive.md` 的 Battlecard 模板已改為 Title Case
- `pmm-gtm.md` 的 Campaign Brief 模板已改為 Title Case，`CTA` 保留全大寫符合例外
- `pmm-market.md` 的台灣段落位於 SaaS 段前

但仍有 3 個阻塞檔案，主因是 **Title Case / 雙語化規則未完全落實到非主模板的 code block / table label**。  
結論：**可以上線：否**

## 🔴 阻塞問題

### 1. `pmm-pricing.md`

- `65-79`：三條軸線 code block 仍使用全大寫英文 label：`PACKAGING`、`VALUE METRIC`、`PRICE POINT`。依 style guide 的 v2.1 / v2.2 規則，模板內英文 label 應避免全大寫，且此處未做中文在前、英文在後的雙語化。
- `141-150`：方案比較表仍有純英文 label：`Entry`、`Better`、`Best`、`Email`、`SLA`。屬表格內 label，應雙語化或中文化處理。

### 2. `pmm-messaging.md`

- `43`：表頭 `Persona` 未雙語化。
- `51`：表頭 `Persona` 未雙語化。
- `101`：表頭 `Email`、`CTA` 未雙語化。
- `110`：表頭 `CTA` 未雙語化。

### 3. `retention.md`

- `165-171`：`Dunning Email` 序列表格仍保留純英文 label：`Day`、`Email`、`CTA`，且列值 `Day 0`、`Day 3`、`Day 7`、`Day 12`、`Day 15` 也未雙語化。依本輪「表格內英文 label 是否雙語化」檢查項，屬未完成。

## 🟡 次要問題

### 1. `pmm-gtm.md`

- `95`：Demo 流程 code block 中 `Next steps` 未採 Title Case；應為 `Next Steps`。屬單點格式問題，不影響內容完整性，但與本輪 Title Case 規則不完全一致。

## 逐檔狀態

| 檔案 | 狀態 | 結論 |
|------|------|------|
| `analytics.md` | ✅ | 工具可用性區塊與 4 題齊備；多個 code block 未見本輪阻塞項；`GA4/GTM/Attribution` 首次註解可接受。 |
| `competitive-content.md` | ✅ | 工具可用性區塊與 4 題齊備；未見 Title Case、術語註解、簡中殘留或內容缺漏問題。 |
| `content-production.md` | ✅ | 工具可用性區塊與 4 題齊備；專屬題通順；未見阻塞級 Title Case / 雙語化問題。 |
| `copy-editing.md` | ✅ | 工具可用性區塊與 4 題齊備；未見本輪阻塞項。 |
| `copywriting.md` | ✅ | 工具可用性區塊與 4 題齊備；簡中詞出現在「繁簡差異」對照表中屬示例用途，非殘留。 |
| `email-outreach.md` | ✅ | 工具可用性區塊與 4 題齊備；未見阻塞項。 |
| `growth-loops.md` | ✅ | 工具可用性區塊與 4 題齊備；未見本輪阻塞項。 |
| `line-marketing.md` | ✅ | 工具可用性區塊與 4 題齊備；未見本輪阻塞項。 |
| `marketing-ops.md` | ✅ | 工具可用性區塊與 4 題齊備；未見本輪阻塞項。 |
| `paid-acquisition.md` | ✅ | 工具可用性區塊與 4 題齊備；未見本輪阻塞項。 |
| `pmm-competitive.md` | ✅ | Battlecard 模板已依類別 C 修正為 Title Case；工具可用性區塊與 4 題齊備。 |
| `pmm-gtm.md` | 🟡 | 類別 C 的 Campaign Brief 模板已通過；但 `95` 的 `Next steps` 未採 Title Case。 |
| `pmm-launch.md` | ✅ | 工具可用性區塊與 4 題齊備；未見本輪阻塞項。 |
| `pmm-market.md` | ✅ | 台灣段 `36-49` 位於 SaaS 段 `55-64` 前，順序正確；工具可用性區塊與 4 題齊備。 |
| `pmm-messaging.md` | 🔴 | 工具降級區塊位置正確，但多個表頭 label 未雙語化（`43`、`51`、`101`、`110`）。 |
| `pmm-patterns.md` | ✅ | 工具可用性區塊與 4 題齊備；主要 code block 未見本輪阻塞項。 |
| `pmm-positioning.md` | ✅ | April Dunford 模板格式可接受；工具可用性區塊與 4 題齊備；未見阻塞項。 |
| `pmm-pricing.md` | 🔴 | code block 與表格 label 仍有全大寫 / 純英文未雙語化問題（`65-79`、`141-150`）。 |
| `quality_checklist.md` | ✅ | 工具可用性區塊與 4 題齊備；未見本輪新增阻塞項。 |
| `retention.md` | 🔴 | `165-171` 的 Dunning 表格仍有純英文 label，未符合表格雙語化規則。 |
| `social-analytics.md` | ✅ | 工具降級區塊位置正確且題數足夠；未見本輪阻塞項。 |
| `social-content.md` | ✅ | 工具可用性區塊與 4 題齊備；專屬題通順；未見本輪阻塞項。 |

## 備註

- 本輪未發現明顯的原有中文段落刪除痕跡。
- 本輪未發現類別 A / B / C 的回歸。
- 本輪未發現需另外升級為 🔴 的簡中殘留；`copywriting.md` 中的簡中詞為對照表反例，屬可接受用例。

🔴 3 / 🟡 1 / 🟢 0 / ✅ 18｜可以上線：否
