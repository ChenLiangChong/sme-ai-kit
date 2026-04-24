# template-guide.md —— 模板使用指南

**何時載入**：Step 1 選模板前、或使用者問「有什麼模板」時載入。這份文件列出 `templates/` 資料夾現有和規劃中的所有模板，以及每個的占位符、尺寸、擴充方式。

---

## 模板總覽

| 檔案 | 狀態 | 類型 | 尺寸 | 用途 |
|------|------|------|------|------|
| `battlecard.html` | ✅ 可用 | 一頁式 | 1920×1080 | 競品戰卡（內部使用） |
| `competitive-analysis.html` | 🔴 規劃中 | 多頁 | 1920×1080 | 多頁競品深度分析 |
| `monthly-report.html` | 🔴 規劃中 | 多頁 | 1920×1080 | 月報／季報 |
| `customer-brief.html` | 🔴 規劃中 | 一頁式或雙頁 | 1920×1080 | 客戶研究 brief |
| `one-pager.html` | 🔴 規劃中 | 一頁式 | A4 / 1920×1080 | 成果簡報、提案摘要 |

---

## battlecard.html（完整指南）

### 基本資訊

- **檔案路徑**：`/mnt/d/gitDir/sme-ai-kit/.claude/skills/sme-design/templates/battlecard.html`
- **尺寸**：1920×1080（固定，為了 PPT 匯出一致性）
- **風格方向**：預設為「經濟日報社論版」（深藍灰 + 襯線標題 + IBM Plex Mono 數字 + 米白底）
- **字型**：Noto Serif TC + Noto Sans TC + IBM Plex Mono（Google Fonts 載入）
- **頁數**：單頁

### 版面結構

```
┌─────────────────────────────────────────────────┐
│  HEADER · 150px                                 │
│  • Eyebrow: COMPETITIVE BATTLECARD · DATE       │
│  • Title: {brand_name} vs {competitor_name}     │
│  • Meta: date / analyst                         │
├─────────────────────────────────────────────────┤
│  MAIN · 1fr                                     │
│  ┌─ Column 1 ─┬─ Column 2 ─┬─ Column 3 ─┐      │
│  │ Basic Info │ Claim vs   │ Pricing /  │      │
│  │            │ Reality    │ ICP /      │      │
│  │            │            │ Overlap    │      │
│  └────────────┴────────────┴────────────┘      │
│  ┌─ Strengths ─┬─ Weaknesses ──────────┐       │
│  │             │                       │        │
│  └─────────────┴───────────────────────┘       │
│  ┌─ Our Adv ──┬─ Land Mines ──────────┐        │
│  │            │                        │        │
│  └────────────┴────────────────────────┘       │
│  ┌─ Talk Tracks ──────────────────────┐        │
│  │                                     │        │
│  └─────────────────────────────────────┘       │
├─────────────────────────────────────────────────┤
│  FOOTER · 210px                                 │
│  Last updated · source · footer note            │
└─────────────────────────────────────────────────┘
```

### 占位符清單

共 **21 個** `{{xxx}}` 占位符，全部要填（實際數量以 `grep -oE '\{\{[a-z_]+\}\}' battlecard.html | sort -u | wc -l` 為準，應得 21）。HTML/JS 註解內的假占位符已 escape 為 `&lbrace;&lbrace;xxx&rbrace;&rbrace;`，不會干擾 grep。若與實際數量不同，以 grep 結果為準、修這份文件。

| 占位符 | 欄位說明 | 範例值 |
|--------|---------|--------|
| `{{brand_name}}` | 我方公司名 | 「[我方公司名]」 |
| `{{competitor_name}}` | 競品公司名 | 「[競品公司名]」 |
| `{{brand_color}}` | 主色（HEX） | `#1a365d` |
| `{{analysis_date}}` | 分析日期 | `2026-04-23` |
| `{{analyst_name}}` | 分析師 | 「[負責人姓名]」 |
| `{{competitor_founded}}` | 競品成立年份 | `1988` |
| `{{competitor_size}}` | 競品規模 | `50-100 人 / 年營收 3 億` |
| `{{competitor_hq}}` | 競品總部 | `[縣市 + 行政區]` |
| `{{competitor_website}}` | 競品官網 | `[example-competitor.com]` |
| `{{competitor_claim}}` | 競品對外主張 | `「30 年老字號、品質保證」` |
| `{{competitor_reality}}` | 實際情況（您分析） | `SKU 過時、交期不穩、少數老客戶撐著` |
| `{{competitor_icp}}` | 競品 ICP（理想客戶） | `傳統連鎖家具行、中部為主` |
| `{{overlap_level}}` | 與我方客群重疊度 | `HIGH` / `MEDIUM` / `LOW` |
| `{{competitor_pricing}}` | 競品定價模式 | `批發價比市價低 15%、現金折扣 3%` |
| `{{their_strengths}}` | 他們的優勢（HTML 列表） | `<li>...</li><li>...</li>` |
| `{{their_weaknesses}}` | 他們的弱點（HTML 列表） | `<li>...</li>` |
| `{{our_advantages}}` | 我方優勢（HTML 列表） | `<li>...</li>` |
| `{{land_mines}}` | 雷區（銷售避雷）（HTML 列表） | `<li>...</li>` |
| `{{talk_tracks}}` | 話術（3 個 `.talk` block 的 HTML 字串） | 見下方範例 |
| `{{next_step_count}}` | Footer 右側大數字（Action Items 數量） | `03` |
| `{{big_num_label}}` | Footer 大數字下方 label | `Action Items` |

### `{{talk_tracks}}` 結構說明

與其他列表欄位**不同**——`talk_tracks` 不是 `<li>`，而是 3 個 `.talk` block 的 HTML 字串，直接 inject 進 `.talk-grid` 容器。每個 block 有 `.objection`（客戶說）和 `.response`（我方回）兩行。

**建議提供 3 個**（對應 footer 的 3 欄 grid）：

```html
<div class="talk">
  <div class="objection">「太貴了，你們比 XX 貴 15%。」</div>
  <div class="response">重新框架為 ROI：單價高 15% 但實木占比 70% vs 40%，單位 CP 其實贏。</div>
</div>
<div class="talk">
  <div class="objection">「我們跟 XX 合作 10 年了，很熟。」</div>
  <div class="response">尊重既有關係，定位為「補 XX 補不到的洞」：3 件起試單、14 天打樣。</div>
</div>
<div class="talk">
  <div class="objection">「交期真的能 14 天？」</div>
  <div class="response">提供過去 30 天實際交期數據 + 延遲補償條款。</div>
</div>
```

CSS 的 `.talk .objection::before` 和 `.talk .response::before` 會自動加上「客戶說」「我方回」的 eyebrow label，不需要自己寫。

### 替換方式（Claude 用字串替換即可）

HTML 檔案底部有 `<script>` 區塊，內建 demo 資料（[我方公司名]）。**您（Claude）的做法**：

**做法 A（推薦、最乾淨）**：直接改 HTML 原檔的 `{{xxx}}` 字串

```bash
# 讀檔 → 字串替換 → 寫新檔
# 用 Edit tool：
# old_string: {{brand_name}}
# new_string: [我方公司名]
```

**做法 B**：改底部 `<script>` 區的 `demo` 物件值

```javascript
const demo = {
  brand_name: "[我方公司名]",  // 改這裡
  competitor_name: "[競品公司名]",
  // ...
};
```

Script 會在瀏覽器載入時自動替換未被替換的 `{{xxx}}`。

**做法 A 和 B 的取捨**：
- A 比較乾淨、打開就是最終版、不需要 JS
- B 比較適合快速預覽、demo 資料可保留比對

**正式交付用 A**。

### HTML 列表欄位的格式

`{{their_strengths}}`、`{{their_weaknesses}}` 等需要放多行內容的欄位，**必須用 HTML `<li>` 標記**：

```html
<!-- 填入前 -->
{{their_strengths}}

<!-- 填入後 -->
<li>中部連鎖家具行 30 年關係深厚</li>
<li>現金折扣機制靈活</li>
<li>交期彈性（可散裝出貨）</li>
```

**不要**直接填純文字或 markdown 條列，會排版跑掉。

### 適用情境 vs 不適用

**✅ 適用**：
- 一對一競品 vs 我方的摘要分析
- 給業務/銷售團隊當隨身參考卡
- 老闆給合夥人說明「為什麼這個競品不可怕」
- 搭配 social-media skill 的 `pmm-competitive` 產出的內容

**❌ 不適用**：
- 三個以上競品同時分析（太擠）→ 此類型模板還沒建。跟使用者確認三選一：(a) 從 `battlecard.html` 改造（擴成多頁）、(b) 為此任務從零寫一份、(c) 改用 Anthropic 內建 pptx skill
- 給老闆看長達 10 頁的深度分析 → 同上，多頁深度分析模板規劃中，跟使用者確認 (a)/(b)/(c)
- 只需要一句話簡報 → 不需要這個模板，直接寫訊息
- 對外行銷素材 → 這是對內文件，不對外

### 如何擴充

**擴充 1：新增一個區塊**

假設要加「客戶評價對比」區塊：

1. 在 CSS 新增 `.customer-reviews` class（參考既有 `.strengths` 的樣式）
2. 在 HTML 的 grid 中插入區塊
3. 在占位符清單加 `{{their_reviews}}` `{{our_reviews}}`
4. 在底部 `script` 的 `demo` 物件補 demo 資料

**擴充 2：換風格（例如改成日式極簡商社版）**

1. 改 `:root` CSS variables：
   - `--brand` 改成更冷的藍（或朱紅）
   - `--paper-cool` 改成象牙白 `#fffef5`
   - `--ink` 改成墨黑 `#1c1c1c`
2. 字型換：`Noto Serif JP` 取代 `Noto Serif TC`（或混用）
3. 拉大所有區塊的 padding（留白佔比提高到 50%）
4. 刪掉 `header::before` 的紅色細條（日式極簡不用裝飾）

**擴充 3：改成多頁（PPT 匯出時自動分頁）**

在每個要獨立成頁的 `<section>` 上加 `data-slide` 屬性：

```html
<section data-slide style="width: 1920px; height: 1080px;">
  <!-- Page 1 -->
</section>

<section data-slide style="width: 1920px; height: 1080px;">
  <!-- Page 2 -->
</section>
```

匯出 PPT 時加 `--selector "[data-slide]"`：

```bash
bun run scripts/html_to_pptx.mjs \
  --input battlecard.html \
  --output battlecard.pptx \
  --selector "[data-slide]"
```

---

## competitive-analysis.html（🔴 規劃中 — 檔案尚未存在）

**目前做法**：遇到此類需求時，跟使用者三選一（(a) battlecard 改寫成多頁、(b) 從零做、(c) 改用 pptx skill）。**不要嘗試 Read 這個檔**。

**規劃用途**：2-4 頁的深度競品分析。相對於 battlecard（一頁速覽），這份是給老闆/合夥人坐下來看 10 分鐘的版本。

**規劃結構**（預計 4 頁）：
- Page 1：封面 + Executive Summary
- Page 2：市場地圖（我方 vs 主要競品的定位象限）
- Page 3：3 個競品的逐一深度分析
- Page 4：策略建議 + Next Actions

**規劃占位符**：屆時產出時定義。

**開發優先級**：中（等使用者第一次要求時再建）

---

## monthly-report.html（🔴 規劃中 — 檔案尚未存在）

**目前做法**：遇到此類需求時，跟使用者三選一（(a) battlecard 改寫、(b) 從零做、(c) 改用 pptx skill）。**不要嘗試 Read 這個檔**。

**規劃用途**：中小企業月報。整合訂單、帳務、庫存、任務資料，產出給老闆看的「本月概況」。

**規劃結構**（預計 3 頁）：
- Page 1：三大指標卡（營收 / 毛利 / 應收帳款） + 本月重點
- Page 2：訂單分析（數量 / 金額 / 客戶分佈）
- Page 3：庫存警報 + 任務完成率 + 下月預告

**規劃占位符**：屆時產出時定義。

**資料來源建議**（本 skill 無 MCP 硬依賴；若執行環境同時有 SME-AI-Kit 的 business-db MCP，可用以下 tools 自動帶資料，否則請使用者手動提供 CSV／Excel／截圖）：
- 若有 business-db MCP：`monthly_summary(year, month)` → 本月概況
- 若有 business-db MCP：`list_orders(status)` → 訂單
- 若有 business-db MCP：`low_stock_alerts()` → 庫存警報
- 若有 business-db MCP：`check_overdue()` → 逾期帳款
- 若無 MCP：請使用者提供月份營收、毛利、前 10 大客戶訂單、當月庫存警報清單、應收帳款清單

**開發優先級**：高（月報是最常用的場景）

---

## customer-brief.html（🔴 規劃中 — 檔案尚未存在）

**目前做法**：遇到此類需求時，跟使用者三選一（(a) battlecard 改寫、(b) 從零做、(c) 改用 pptx skill）。**不要嘗試 Read 這個檔**。

**規劃用途**：客戶研究 brief。業務/老闆拜訪客戶前的簡報，整合客戶基本資料、交易歷史、對應窗口、關鍵痛點。

**規劃結構**（預計 1-2 頁）：
- Page 1：客戶基本資料 + 決策者 + 我方關係現況
- Page 2（選用）：過去交易 + 溝通記錄 + 建議策略

**資料來源建議**（本 skill 無 MCP 硬依賴；以下為 optional 強化，若無 MCP 請使用者提供）：
- 若有 business-db MCP：`find_customer(name)` → 客戶資料
- 若有 business-db MCP：`list_orders(customer_id)` → 交易歷史
- 若有 business-db MCP：`log_interaction` 的歷史紀錄
- 若無 MCP：請使用者提供客戶名片／統編／主要聯絡人／近一年交易摘要

**開發優先級**：中高

---

## one-pager.html（🔴 規劃中 — 檔案尚未存在）

**目前做法**：遇到此類需求時，跟使用者三選一（(a) battlecard 改寫、(b) 從零做、(c) 改用 pptx skill）。**不要嘗試 Read 這個檔**。

**規劃用途**：通用一頁式。成果簡報、提案摘要、活動 brief、產品介紹——任何要「濃縮在一頁」的場景。

**規劃結構**：
- 頂部：大標題 + 一句話摘要
- 中段：3 個重點區塊（可換成 metrics / features / timeline）
- 底部：CTA 或 Next Steps

**規劃占位符**：高通用性，至少 15 個可替換欄位（屆時產出時定義）。

**開發優先級**：中

---

## 模板開發準則（給未來擴充用）

當您（Claude 或維護者）要新增模板時：

1. **固定尺寸 1920×1080**（或 A4：794×1123px @ 96dpi）—— 保證 PPT 匯出一致
2. **字型用 Google Fonts** + 系統字型 fallback（PingFang TC / Microsoft JhengHei）
3. **占位符用 `{{xxx}}`** —— snake_case、純英文
4. **CSS variables 放在 `:root`** —— `--brand`、`--ink`、`--paper`、`--line` 是標準命名
5. **底部放 `<script>`** 內建 demo 資料，支援 no-JS fallback（填好了就不跑 script）
6. **HTML 區塊用 `<section data-slide>`** 標記可獨立分頁的區塊
7. **對照 anti-slop.md 自檢** —— 做完看一遍，不要留 AI 痕跡
8. **每個模板對應 1-2 個 design-philosophy 風格**，不要想「全風格通用」

---

## 模板與場景的對應關係

模板只是起點——**實際交付時風格仍由 design-philosophy.md 決定**。同一份 `battlecard.html` 可以套進 3 個不同風格：

**目前可用**：只有 `battlecard.html`。

**規劃中（檔案尚未存在）**：競品分析、客戶 brief、月報、一頁式成果簡報。遇到這些需求時，**跟使用者確認三選一**：
- (a) 從 `battlecard.html` 改寫（擴版面、加頁）
- (b) 為此任務從零寫一份新模板（耗時較長）
- (c) 改用 Anthropic 內建 pptx skill 直接產 PPT

| 場景 | 目前對應 | 建議風格 | 建議尺寸 |
|------|---------|---------|---------|
| 一對一競品速覽（內部） | ✅ `battlecard.html` | 經濟日報社論版 | 1920×1080 |
| 給 B2B 客戶看的深度分析 | 🔴 多頁競品分析模板規劃中 → 三選一 | 顧問諮詢所報告版 | 多頁 1920×1080 |
| 客戶拜訪 brief（業務） | 🔴 客戶 brief 模板規劃中 → 三選一 | 顧問版 / 雜誌版 | 1-2 頁 |
| 給老闆看的月報 | 🔴 月報模板規劃中 → 三選一 | 經濟日報 / 顧問版 | 多頁 1920×1080 |
| 對外一頁式（品牌故事） | 🔴 一頁式模板規劃中 → 三選一 | 雜誌特別報導版 | A4 或 1920×1080 |
| 政府補助申請書 | 🔴 規劃中 → 三選一 | 政府標案版 | A4 縱向 |
| 精品 menu / 品牌書 | 🔴 規劃中 → 三選一 | 日式極簡商社版 | 依需求 |
| 新創 Demo Day deck | 🔴 規劃中 → 三選一 | 新創 Pitch Deck 版 | 1920×1080 |

**原則**：先選**場景 × 讀者 × 場合**，再選**風格**（design-philosophy），最後才選**模板**。模板是骨架，風格是衣服。

---

## 快速參考

1. **battlecard.html 是目前唯一可用模板** —— 其他 4 個 🔴 規劃中（檔案尚未存在），遇到需求跟使用者三選一（改寫 / 新做 / pptx skill）
2. **占位符用 `{{xxx}}`**，Claude 直接用 Edit 做字串替換即可
3. **HTML 列表欄位（strengths / weaknesses 等）要包 `<li>`** —— 不要填純文字
4. **擴充成多頁**：每個區塊加 `<section data-slide>`、匯 PPT 時加 `--selector "[data-slide]"`
5. **新模板優先級**：monthly-report > customer-brief > competitive-analysis > one-pager
6. **同一模板可套不同風格**：骨架共用，衣服按 design-philosophy.md 換

---

## 來源對照

- **場景 × 尺寸 × 信息密度對應**：huashu scene-templates.md 的「按輸出類型組織」
- **「骨架 vs 衣服」分離**：huashu design-styles.md + scene-templates.md 組合公式
- **台灣原創**：
  - 5 個具體模板（battlecard / competitive-analysis / monthly-report / customer-brief / one-pager）的規劃與優先級
  - `{{xxx}}` 占位符 + 底部 `<script>` demo 物件的雙軌替換法（做法 A vs B）
  - `<section data-slide>` + `--selector` 匯 PPT 的 pipeline
  - business-db MCP tools 的資料對應（monthly_summary / low_stock_alerts / find_customer）
