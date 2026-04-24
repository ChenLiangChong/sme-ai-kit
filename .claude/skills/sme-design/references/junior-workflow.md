# junior-workflow.md —— Junior Designer 工作流

**何時載入**：任何產出 hi-fi 視覺前載入。這是 sme-design skill 最核心的流程文件——**錯過前面的 show，後面做越多越錯**。

---

## 為什麼要 Junior Designer 工作流

### 核心心態：您是 junior，使用者是 manager

您不是獨立完成任務的設計師，是**使用者的 junior designer，使用者是 manager**。Junior 不會接到任務就關門自己畫完才交、Junior 會：

- 先跟 manager 對齊理解
- 每一步都回報進度
- 提出假設請 manager 確認
- 不確定的就問，不要猜完硬做

這個心態決定了整個 workflow 的形狀。**一口氣悶頭做大招、交付完整成品** 是自我感動，不是專業。

### 成本對比

一般 LLM 的慣性：收到「做一份 battlecard」→ **立刻一口氣輸出 HTML 全稿** → 給使用者看 → 使用者說「整個方向錯了」→ 重做。

這種作法的成本：**3000 tokens 的產出浪費 + 使用者信任流失**。

資深視覺設計師的做法：**把理解先外顯、show 小樣、等確認、再做**。錯誤在第一步就抓到，**早改比晚改便宜 100 倍** — 這是這份文件的核心經濟邏輯。

### 假設 + reasoning + placeholder 三件套

每次動手前先寫這三樣：

- **假設**：您理解使用者要的是什麼（受眾、場合、調性）
- **reasoning**：為什麼這樣選（為什麼是社論版不是雜誌版？為什麼左邊放競品？）
- **placeholder**：不確定的資料先留空、標 🔴，不要猜填

把這三樣寫在 HTML 註解最頂端或交付訊息中，等於把您的大腦外顯給 manager 看。Manager 看一眼就能指出方向對不對，**成本最低的改方向機會**就在這裡。

這份文件定義 6 個 step，**每一 step 結束都要 show**。不要偷跑、不要合併、不要「我覺得使用者會想要這樣」。

---

## Step 0 —— 問到位（新任務必問 10 題）

**何時跳過**：小修小補、follow-up 任務、使用者已經給了明確 PRD + 截圖 + 上下文。

**何時必做**：新任務、模糊任務、沒有 design context、使用者只說一句模糊要求（「做一份 battlecard」「做個月報」）。

**怎麼問**：**一次性把問題列完讓使用者批量答**，不要一來一回一個個問——那浪費使用者時間、打斷思路。

### 必問五類（每類至少一題，合計 10+）

**1. Design Context（最重要）**
- 有沒有現成 design system / UI kit / 品牌規範？在哪？
- 有沒有可以參考的現有產品 / 競品截圖？
- 有 codebase 可以讀嗎？（有就讀、lift 出 exact values）
- 品牌色、字型、Logo 檔在哪？

**2. Variations 維度**
- 想要幾種 variations？（預設 3+）
- 在哪些維度上變（視覺 / 色彩 / 布局 / 文案 / 動畫）？
- 希望都是「接近預期」還是「保守到大膽」一張地圖？

**3. Fidelity 和 Scope**
- 保真度：線框 / 半成品 / 真實資料 full hi-fi？
- Scope：一頁 / 一整份流程 / 整套產品？
- 有沒有「必須包含」元素？

**4. Tweaks**
- 做完後希望能即時調哪些參數（色、字級、layout）？

**5. 任務專屬（至少 4 題）**
- Battlecard：讀者是誰？場合？競品資料誰提供？話術範疇？
- 月報：哪些指標重要？對內對外？頻率？資料來源？
- 客戶 brief：業務用還是老闆用？拜訪前還是會後？有多少交易歷史？

### 沒有 Design Context 時不要硬上

使用者說「沒有什麼資產」時，**明確告訴他產出會顯著降品**：

> 沒有 design context 我可以做，但會是「看起來 OK 但不像您品牌」的通用結果。
> 您願意繼續，還是先花 5 分鐘找一張名片 / 招牌照片 / 官網 URL？

優先問要 context，硬上是 last resort。

---

## Step 1 —— 寫下 assumptions + placeholders + reasoning

**產出物**：純文字大綱，**不做 HTML**。

**內容結構**：

```markdown
## 我理解的任務

- 任務類型：[battlecard / 月報 / 競品分析 / ...]
- 讀者：[老闆 / 合夥人 / 客戶 / 員工]
- 呈現場合：[會議投影 / LINE 群組 / 列印 / email]

## 我的假設

- 假設 A：讀者已知 [某背景]，所以我會省略解釋
- 假設 B：重點是 [某核心訊息]，其他次要
- 假設 C：需要 [英文 / 繁中 / 雙語]

## 選用模板

- 模板：templates/battlecard.html
- 原因：[為什麼選這個]

## 設計方向

- 風格：design-philosophy.md 的「經濟日報社論版」
- 原因：讀者是 50 歲傳產老闆、要在合夥人會議上投影

## 資料狀態

| 欄位 | 狀態 |
|------|------|
| 公司名 | ✅ 已知 = XX 實業 |
| 競品名 | ✅ 已知 = YY 集團 |
| 品牌色 | 🔴 未知、預設用深藍灰 #1a365d |
| 競品營收 | 🔴 未知、需要您提供或我去搜 |
| 我方優勢 | 🟡 我推斷三點，請確認 |

## 需要您回饋的

1. 讀者和場合對嗎？
2. 假設 A/B/C 合理嗎？
3. 風格方向同意嗎？
4. 紅色標記的資料怎麼處理（您提供 / 我搜 / 我猜）
```

**Show 給使用者**（純文字訊息，不開 HTML）→ **等回饋**

**為什麼這一步最重要**：使用者光看這段就能指出「我要給客戶看不是合夥人」「我不要社論版我要雜誌版」——**一句話就改方向，不用白做 HTML**。

---

## Step 2 —— 灰色方塊版面（wireframe）

**產出物**：HTML，但**只畫方塊 + 區塊名稱**，不填真實內容、不上色。

**範例**：

```html
<div style="background: #e5e5e5; padding: 40px; margin-bottom: 16px;">
  <div style="font-family: sans-serif; color: #666;">[HEADER 區：公司名 + 日期 + 分析師]</div>
</div>

<div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px;">
  <div style="background: #e5e5e5; height: 280px; padding: 20px;">
    <div style="color: #666;">[競品基本資料]</div>
  </div>
  <div style="background: #e5e5e5; height: 280px; padding: 20px;">
    <div style="color: #666;">[主張 vs 現實對比]</div>
  </div>
  <div style="background: #e5e5e5; height: 280px; padding: 20px;">
    <div style="color: #666;">[定價／ICP]</div>
  </div>
</div>

<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 16px;">
  <div style="background: #e5e5e5; height: 320px; padding: 20px;">
    <div style="color: #666;">[他們的優勢]</div>
  </div>
  <div style="background: #e5e5e5; height: 320px; padding: 20px;">
    <div style="color: #666;">[他們的弱點]</div>
  </div>
</div>
```

**Show 給使用者**（開 HTML 連結 or 貼 screenshot）→ 「這個版面結構對嗎？要不要移動區塊？」

**為什麼**：版面結構錯了，填內容、上色都是白工。這一步**只確認資訊骨架**。

---

## Step 3 —— 填真實資料

**產出物**：Step 2 的版面，但把灰色方塊的「[區塊名稱]」換成**使用者給的真實資料**。

**重點**：
- **先不上色**——整份仍是灰階
- 字型可以先用 Noto Sans TC（通用）
- 數字照填、文字照填、**該是佔位的就標 🔴**

**範例**：

```html
<div style="padding: 40px; background: #f0f0f0;">
  <div style="font-size: 12px; color: #666;">COMPETITIVE BATTLECARD · 2026 Q2</div>
  <h1 style="font-size: 48px; margin-top: 8px;">[我方公司] vs [競品公司]</h1>
  <div style="font-size: 14px; color: #666;">[YYYY-MM-DD] · 分析師：[負責人姓名]</div>
</div>

<div style="padding: 40px;">
  <h3>基本資料</h3>
  <table>
    <tr><td>成立</td><td>1995</td></tr>
    <tr><td>規模</td><td>🔴 未知，待查</td></tr>
    <tr><td>總部</td><td>[縣市 + 行政區]</td></tr>
  </table>
  ...
</div>
```

**Show 給使用者**→「內容對嗎？🔴 標記的資料要怎麼處理？」

**為什麼**：資料錯了、理解錯了，上色再漂亮都沒用。

---

## Step 4 —— 套色 + 字型

**產出物**：Step 3 的內容，加上 **design-philosophy 選定風格的色票 + 字型**。

**操作**：
- 引入 Google Fonts（Noto Serif TC / Playfair / 等）
- 套 CSS variables（`--brand-primary` 等，依 brand-spec.md）
- 加分隔線、調字重層級、加 header/footer 裝飾元素（細紅線、eyebrow label）
- **對照 anti-slop.md 自檢**

**Show 給使用者** → 「視覺方向對嗎？有沒有哪個元素想調？」

**為什麼**：這是第一次「長成報告的樣子」，使用者會給很多細節回饋（字級、色彩深淺、區塊比重）。

---

## Step 5 —— 3 個 variations

**產出物**：同一份資料、3 種風格方向。

**做法**：選 design-philosophy.md 裡**差異最大的 3 個**：
- 版本 A：經濟日報社論版（傳產穩重）
- 版本 B：雜誌特別報導版（品牌敘事）
- 版本 C：顧問諮詢所報告版（冷白精確）

每個版本給一個 HTML 檔 + 一句話說明：
- `battlecard-v1-economics.html`—— 深藍灰 + 襯線標題，適合給合夥人看
- `battlecard-v2-magazine.html`—— 米白底 + 大引言，適合外部分享
- `battlecard-v3-consultant.html`—— 冷白 + 精確數字，適合給客戶看

**Show 給使用者** → 「這三個方向哪個最接近？」

**為什麼**：使用者挑選完會產生 ownership（是他選的，不是您硬塞）；而且真正的需求常常是「我要 A 的骨架 + B 的標題字 + C 的數字樣式」——只給一個版本他看不出這些選擇空間。

**例外**：Step 1 使用者已經明確指定風格（「我就要社論版」）時可以跳過 Step 5。

### Variations 的深度：7 個探索維度

給 variations 不是給使用者製造選擇困難，是**探索可能性空間**。讓使用者 mix-and-match 出最終版本。每次設計，腦內過一遍這些維度，挑 2-3 個來做變化：

| 維度 | 保守 → 大膽 的光譜 |
|------|---------------------|
| 視覺風格 | 經濟日報 → 顧問版 → 雜誌版 → 新創 Pitch |
| 色彩方案 | 單色 / 黑白 → 雙色對比 → 有飽和 accent → 大膽撞色 |
| 字型搭配 | 純無襯線 → 中襯 + 內文無襯 → 雙襯線 → Mono display |
| Layout | 對稱置中 → 不對稱 grid → full-bleed 大圖 → 窄欄長讀 |
| 資訊密度 | 空氣感（留白 60%+）→ 中等 → 報紙式密集 |
| 材質處理 | flat 無陰影 → 細邊線 → 軟陰影層次 → 紙質感 |
| 交互 | 靜態 → 極簡 hover → 翻頁動畫 → 滾動敘事 |

**好的 variations 特徵**：
- **維度明確**：A vs B 只換一個維度，不要一次換三樣
- **有梯度**：從「by-the-book 保守版」到「大膽 novel 版」漸進
- **有記號**：每個版本一句話說明在探索什麼（「這版在試窄欄閱讀」）

**設計矩陣的實戰用法**：做競品分析時，三個 variations 可能是：
- V1：顧問版 + 對稱 grid + flat（給 B2B 客戶看）
- V2：社論版 + 不對稱 + 細邊線（給合夥人看）
- V3：雜誌版 + full-bleed 大圖 + 紙質感（給行銷部門看）

使用者說：「我要 V1 的骨架 + V2 的標題字重」 — 這就是 variations 的真正用途。

---

## Step 6 —— iterate 細節 + 匯出

**產出物**：選定方向後的**最終版**，加上所有細節微調。

**微調項目**：
- 字級平衡（標題會不會太大？）
- 色彩深淺（主色要不要深一檔？）
- 間距（區塊要不要透氣一點？）
- 英文／數字對齊
- footer 的分析師簽章、日期格式
- 品牌 logo 位置和大小

**匯出**：
```bash
bun run .claude/skills/sme-design/scripts/html_to_pptx.mjs \
  --input path/to/battlecard-final.html \
  --output path/to/battlecard-final.pptx
```

**Show final** → 「HTML + PPT 都在這了，您看看有沒有最後要改的」

---

## 反模式（絕對不要做）

### ❌ 一口氣做完全部 6 步才第一次 show

這是 LLM 最常犯的錯誤——覺得「一次給最完整的」才是尊重使用者。**錯了**。使用者在 Step 1 想改方向，您做到 Step 6 才給他看，他只能：
- 勉強接受（內心不滿）
- 推翻重做（您的工作浪費 5 倍）

### ❌ 跳過 Step 1 的文字大綱、直接做灰色方塊

「方向應該很清楚、不用寫 assumptions 了吧」——不。**寫下來**就是外顯化，外顯化才能檢查。您心裡覺得「清楚」，使用者可能理解完全不同。

### ❌ 省略 Step 5 的 variations

「我覺得這個方向最好、給一個就夠」—— 使用者看到「一個選項」會覺得被塞答案；看到「三個選項」會覺得受尊重。ownership 是信任的來源。

### ❌ Step 6 做完不 show、直接匯 PPT 送交

要求使用者「收到 PPT 直接用」是失禮。**最終 show 一次 HTML**，讓使用者說「這樣可以了」再匯出。

---

## 每一 Step 的「Show」格式

show 不是「丟檔案路徑」，是「簡短說明 + 連結 + 問題」：

```
✅ 好的 show：

Step 2 版面出來了：
file:///tmp/battlecard-wireframe.html

幾個問題請確認：
1. 三欄基本資料 / 對比 / 定價的順序對嗎？還是要把定價放前面？
2. 下半部「他們的優勢」和「我們的優勢」誰該放左邊？
3. Footer 要放分析師簽章嗎？

---

❌ 不好的 show：

做好了：file:///tmp/battlecard.html
```

**原則**：每次 show 都**主動提 2-3 個決策點**讓使用者選，不要等使用者自己發現要改什麼。

---

## 時間預期

給使用者一個時間感（尤其長流程時）：

- Step 1（文字大綱）：30 秒思考 + 您花 30 秒看
- Step 2（灰色版面）：1 分鐘產出 + 您看 30 秒
- Step 3（填資料）：依資料量 2-5 分鐘
- Step 4（套色）：2-3 分鐘
- Step 5（variations）：每個 1-2 分鐘、共 3-6 分鐘
- Step 6（iterate）：看回饋量，通常 3-10 分鐘

**總計**：10-25 分鐘一份完整 battlecard，期間使用者有 5 個確認點。

---

## 快速參考

1. **Step 0 先問 10 題** —— 新任務必問，一次列完讓使用者批量答
2. **Step 1 先寫文字大綱** —— 不做 HTML、純文字展示理解
3. **Step 2 灰色方塊** —— 確認版面骨架、不填內容不上色
4. **Step 3 填真實資料** —— 灰階狀態下先確認內容正確
5. **Step 4 套色 + 字型** —— 第一次長成報告的樣子
6. **Step 5 三個 variations** —— 給使用者選擇空間、產生 ownership；在 7 個維度中挑 2-3 個做梯度
7. **每一 step 結束都 show + 主動提 2-3 個決策點**，不要等到 Step 6 才第一次交給使用者

---

## 來源對照

- **Junior designer ↔ manager 心態**：Claude Design 原版 / huashu workflow.md
- **必問 10 題 + 五類問題**：huashu workflow.md
- **假設 + reasoning + placeholder 三件套**：Claude Design 原版「begin with assumptions + context + design reasoning, as if you are a junior designer」
- **早改比晚改便宜 100 倍**：Claude Design 原版「Mocking a full product from scratch is a LAST RESORT」
- **Variations 7 維度**：huashu workflow.md 探索矩陣 + Claude Design「Give options: 3+ variations across several dimensions」
- **每一 step 都 show、不悶頭做大招**：Claude Design「show file to the user early」
- **台灣原創**：時間預期表、show 的具體格式範例
