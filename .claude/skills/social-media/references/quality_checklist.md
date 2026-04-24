# Quality Checklist — social-media

最後更新：2026-04-03

---

> **工具可用性**：本模組會嘗試呼叫 `query_knowledge`（屬 business-db MCP）載入既有品牌／行銷脈絡。若該工具不可用（例如第一堂課只裝了 Claude Desktop + social-media skill，尚未安裝 SME-AI-Kit），請直接向使用者詢問所需的品牌／行銷資訊，不要因工具缺失而停止。
>
> **最小問題清單（沒 MCP 時先問這些）：**
> - 您的公司／品牌是什麼？主要產品或服務？
> - 目標客戶是誰？（規模、行業、痛點）
> - 目前的行銷／定位狀況？有什麼既有資料可以參考？
> - 這次要檢核的是哪個 skill / 哪一批修改？

---

## 格式確認

| 檢查項 | 結果 | 備註 |
|--------|------|------|
| format_check.py | ✅ 0 error, 0 warning | |
| quick_validate.py | ✅ valid | |
| audit_unreferenced_files.py | ✅ 0 issues (22 referenced / 22 files) | |
| audit_skill_references.py | ✅ 0 issues | |
| Frontmatter name/description | ✅ | description 用雙引號 |
| 斷裂引用連結 | ✅ 已清除 | 37+10 個已修 |
| `marketing-context.md` 條件引用 | ✅ 已替換 | 26 個已改為 `query_knowledge`（含本次追加修正 6 個） |
| 幽靈腳本引用 (`scripts/*.py`) | ✅ 已清除 | ~30 個 |
| 幽靈外部整合引用 (`../../tools/`) | ✅ 已清除 | ~12 個 |
| Related Skills 舊 skill 名稱 | ✅ 已更新 | 全部 22 個 reference |
| PMM 重複段落 | ✅ 已消除 | pmm-market 的 International Expansion 指向 pmm-gtm |

---

## 重構記錄（2026-04-03）

### 拆分

| 原檔案 | 行數 | 拆分結果 |
|--------|------|---------|
| content-copy.md | 1,859 | copywriting.md + content-production.md + copy-editing.md + email-outreach.md |
| strategy-ops.md | 1,803 | marketing-ops.md + analytics.md + competitive-content.md |
| growth.md | 1,679 | paid-acquisition.md + growth-loops.md + retention.md |
| social.md | 1,001 | social-content.md + social-analytics.md |

### 刪除

- pricing-strategy 區段（與 pmm-pricing.md 逐字重複）
- brand-guidelines 區段（Anthropic 專屬，與本專案無關）
- content-creator 區段（空殼 redirect）
- launch-strategy 區段（已合併到 pmm-launch.md）

---

## 內容審計發現（2026-04-03）

### 🔴 嚴重（已修復）

1. ~~幽靈 reference 連結（30+）~~ → 已刪除
2. ~~幽靈腳本引用（18+）~~ → 已刪除
3. ~~幽靈外部整合引用~~ → 已刪除
4. ~~Related Skills 引用舊 skill 名稱~~ → 已更新
5. ~~marketing-context 引用 .agents/ 路徑~~ → 已改為 business-db

### 🟡 中等（已知，保留觀察）

1. ~~**內容適用性**~~ → ✅ 已在地化：新增 taiwan-market.md 和 line-marketing.md，各模組加入台灣市場指引，SaaS 用語已改為產業中立。
2. **品牌語氣 handoff 不完整** — SKILL.md 宣告了與 company-ops brand-voice 的協作，但各 reference 內部未實作 handoff 指示。
3. ~~**平台偏差**~~ → ✅ 已修正：Platform Quick Reference 改為台灣優先順序（LINE OA > FB > IG > YouTube > TikTok > Threads），X/Twitter 區段已縮減為參考。
4. ~~**金額單位**~~ → ✅ 已加入 TWD 基準：Platform Benchmarks 加入台灣數據，growth-loops 預算改為 TWD。
5. **growth-loops.md 行數較多** — 包含 referral-program + free-tool-strategy + demand-acquisition，性質差異大，未來可考慮再拆。

### 🟢 建議（未來改善）

1. ~~補充台灣特有場景~~ → ✅ 已新增 taiwan-market.md（節慶日曆、KOL、Google 商家、法規）
2. ~~為最常用模組加繁中摘要段~~ → ✅ 已加入台灣市場適用指引區段
3. ~~SKILL.md 加一行說明 reference 為英文知識庫~~ → ✅ 已更新 SKILL.md

---

## 在地化記錄（2026-04-02）

### 新增檔案
- taiwan-market.md — 台灣市場通用參考（平台生態、廣告基準、節慶日曆、KOL 行情、法規、Google 商家、LINE 策略摘要）
- line-marketing.md — LINE 行銷策略參考（OA 功能、群發策略、Flex Message、會員經營）

### 全域修改
- 所有 12 個執行模組加入「台灣市場適用指引」區段（繁體中文 blockquote）
- SaaS 非技術性描述改為產業中立用語
- 平台表格改為台灣優先順序（LINE OA > FB > IG > YouTube > TikTok > Threads）
- X/Twitter Growth 區段縮減為精簡參考
- demand-acquisition 預算改為 TWD，通路改為口碑+LINE+Google 商家+社群
- paid-acquisition 平台選擇改為 Meta Ads 為主
- copywriting.md 加入「台灣中文文案注意事項」
- retention.md 加入「實體/服務業留客策略」
- marketing-ops.md 加入「中小企業簡化路由」

---

## 最終判定

| 維度 | 評級 |
|------|------|
| 格式合規 | ✅ 通過 (Pass) |
| 內容品質 | ✅ A（知識品質高，已在地化） |
| 整體上架準備 (Readiness) | ✅ 通過 (Pass)（結構完整，已台灣化） |
