# 部門 floor 在 NAS 上的部署設計

> 2026-06-02 與老闆討論「系統上 NAS」時釐清的部署拓樸與安全邊界。
>
> **為什麼記成文件、不存 business-db**：客戶端是全新的 db、開發機（dogfood）的 db 不會跟著過去。
> 這種「要帶到客戶現場用」的部署知識必須留在 repo 裡、隨產品 clone 過去；存進 business-db 到客戶那邊就消失了。
> （通則：travels-to-customer 的知識 → repo 檔；只屬這家公司營運的規則 → business-db。）

## 拓樸決策：單機跑、NAS 只當儲存

- 所有部門的 Claude Code session 跑在**同一台電腦**上（一台機器、多個 `SME_FLOOR` session），那台機器掛載 / 連到 NAS。
- **NAS 本身不跑 runtime、不是獨立的存取點**，只是被掛載的檔案來源。
- 推論：floor 的兩道牆只需要在「跑 session 的那一台機器」上守；NAS 不增加新的把關面。

## 威脅模型（老闆明確界定）

- **只防「員工透過 agent 越權看不該看的」。**
- 員工直接開 NAS 資料夾（網路磁碟機 / web 介面）拿檔 **不在範圍內** —— 老闆原話：「那個沒差，就只是要防止員工透過 agent 越權」。
- 推論：**不需要 NAS 資料夾 ACL 那道 storage 層的牆**。現有兩道牆即完整設計、`sandbox-only` 正確：
  1. **檔案牆**：Claude Code sandbox（cwd = 該層資料夾 + `allowWrite` 限該夾 + `denyRead` 列其他所有層 / 家目錄 / `.mcp.json` / `business.db` / `line-channels.json` / `floor-map.json`）。
  2. **資料牆**：business-db MCP 依 `SME_FLOOR` + `floor-map.json` 物理移除該層不該有的工具。

  （兩道牆機制細節見 root `CLAUDE.md`〈部門安全層（floor）與兩道牆〉，此處不重述。）

## 對現有機制的影響 ≈ 只有「路徑」要變

上 NAS **不動**現有 floor 機制，唯一要處理的是**絕對路徑**：

- 每層 sandbox 設定（`.claude/line-runtime-<floor>.json`）目前硬編碼 `/mnt/d/gitDir/sme-ai-kit/...`。
- `denyRead` 還**手列了其他每一個 floor 資料夾**（O(n²) 交叉表）：例如 `accounting` 的 `denyRead` 列了 `confidential` / `general` / `external`。加第 5 層就得回每個檔補一行、**漏一個 = 那層的牆破一個洞**。
- 上 NAS → base path 改成 NAS 掛載點（`/volume1/...` 之類）→ 這些檔每條路徑都要重寫、交叉表還要維持完整。

## 因此：#13 manifest 生成器 = 客戶端做 NAS 部署時的正解

- 把資料夾結構 + 每層 sandbox 設定，從**單一份 `floor-map.json`** 自動產出（`denyRead` 交叉表自動填滿、base path 參數化）。
- 「換資料夾 / 換機器只改 manifest 一處重生成」，取代手改 N 個檔，並消除「漏列一層」的人為破口。
- 順帶把散落的硬編碼（`server.ts` 的預設 floor / boss target、`floor_policy` / `escalation` 的 `FULL_ACCESS_FLOORS` 等）一起收進 manifest。

## 時機與範圍（明確界定）

- **NAS 部署 + #13 都到客戶現場再做**（決策 #188「不主動拆、去客戶那邊再拆」的延伸）。dogfood 階段維持 `/mnt/d` 現狀、不動工。
- **不做** NAS ACL（威脅模型不含「員工直接開檔」）。
- **不為**「單機多 session」以外的拓樸設計（沒有「員工各自電腦掛載 NAS」這種情境）。
- 此文件只記錄設計與取捨，供客戶端實際部署時照著做。
