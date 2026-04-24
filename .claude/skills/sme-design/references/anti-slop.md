# anti-slop.md —— 反 AI 痕跡（台灣版）

**何時載入**：產出任何 hi-fi 視覺前自我檢核、收到「這看起來很 AI」的回饋時、或 Mode 3（優化既有設計）時。這份文件是品質守門——做完記得對照檢查。

---

## 為什麼台灣老闆對 AI 痕跡特別敏感

台灣中小企業老闆日常看兩類文件：
- **報紙／雜誌／同業公會文件**——培養出「正經專業」的視覺期待
- **LINE 群組轉傳的 PowerPoint**——認得內建模板的味道

當您產出一份紫漸變 + emoji icon + 圓角卡片的「現代感」報告，老闆的反應不是「好漂亮」，而是：

- 🔴 「這是年輕人 / 設計師 / 大學生玩的」
- 🔴 「像 PowerPoint 內建模板」
- 🔴 「看起來不穩重」
- 🔴 「像電商／網紅在用的」

**這不是審美保守，是「場合辨識」**——老闆要把文件拿到銀行、給合夥人、寄給客戶。他需要的是「合適的衣服」，不是「時髦的衣服」。

---

## 例外規則：品牌 override 優先於 anti-slop

本清單是**通用防呆**，不是絕對戒律。若**品牌官方已經在使用某個本文列為「必避」的 pattern**，保留品牌識別優先於 anti-slop 規則。例如：

- 某新創品牌的 Logo 本身就是**紫漸變** → 報告保留紫漸變（否則違反 asset-protocol 的「不竄改品牌色」）
- 某科技公司官網全站都用 **Inter** → 保留 Inter 以求一致性
- 某餐飲品牌 Logo 全是 **emoji-style 手繪** → 內部模仿該風格做 menu

**如何正確 override**：在報告開頭或交付訊息中**明示品牌例外**，用以下模板：

```
🔔 品牌例外：{客戶品牌名} 官方使用 {被例外的 pattern}，
本報告保留該元素以維持品牌識別，不走 anti-slop 通用規則。
來源：{brand.com/brand 或具體證據}
```

**不可以的 override**：
- ❌ 你覺得紫漸變好看 → 不是品牌 override，是你的偏好
- ❌ 使用者說「我覺得圓角卡片比較現代」→ 禮貌提醒 anti-slop 理由；使用者堅持則照做，但**記錄是使用者決定**不是品牌要求
- ❌ 「AI slop 規則太死板所以繞過」→ 不是 override，是放棄專業判斷

心法：**anti-slop 是保護，不是監獄**。真實的品牌識別永遠贏過通用美感規則。

---

## 必避清單（一眼看就 AI）

### 必避 1：紫 / 藍紫漸變背景

```css
/* ❌ 一眼 AI */
background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
background: linear-gradient(to right, #8B5CF6, #EC4899);
```

**為什麼是 AI 痕跡**：這組配色是 2020-2023 Midjourney / Stability / 各種 AI 工具首頁的標配，所有人都用，所有人都認得。老闆看到會直接連結到「AI 生成的東西」。

**台灣老闆的具體反應**：
- 「這紫色太花」
- 「像比特幣詐騙網站」
- 「我們公司又不是做化妝品」

---

### 必避 2：Emoji 當 icon

```html
<!-- ❌ 一眼 AI -->
<h3>📊 營收分析</h3>
<li>💰 利潤率上升</li>
<li>🚀 成長 30%</li>
<li>⚡ 快速執行</li>
```

**為什麼是 AI 痕跡**：Emoji 是 LLM 在無資訊時填版面的最廉價手段。「要有重點感 → 加 🔥」是 AI 的通用套路。

**台灣老闆的具體反應**：
- 「這是年輕人玩的」
- 「不夠正式」
- 「LINE 貼圖嗎」

**唯一例外**：給年輕員工看的內部訊息、或給 Z 世代客戶的行銷文案。正式報告絕對不用。

---

### 必避 3：圓角 8-12px + 左 border accent 色條

```css
/* ❌ AI 設計師的標準套路 */
.card {
  border-radius: 12px;
  border-left: 4px solid #3B82F6;
  background: white;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  padding: 24px;
}
```

**為什麼是 AI 痕跡**：這個 pattern 來自 Tailwind UI / shadcn / Vercel 範例，所有 LLM 都學過。產出的 SaaS dashboard 都長這樣，老闆一眼看出「這是網站上的東西」。

**台灣老闆的具體反應**：
- 「像在看 App」
- 「太軟了」
- 「不像報告」

---

### 必避 4：所有東西都 border-radius 12px

```css
/* ❌ 所有元素都圓角 */
.button, .card, .input, .image, .avatar { border-radius: 12px; }
```

**為什麼是 AI 痕跡**：真正的設計會依元素性質決定圓角——按鈕可以圓、卡片可以直角、照片不圓角。全部統一 12px 是偷懶。

**台灣老闆的具體反應**：
- 「電商感」
- 「像購物網站」

---

### 必避 5：SVG 畫人物 / 抽象流線 / 螺旋

```html
<!-- ❌ AI 畫不好人物 -->
<svg><!-- 火柴人 / 抽象人形 --></svg>

<!-- ❌ 抽象流線、螺旋、波浪線裝飾 -->
<svg><path d="M 0 100 Q 50 0 100 100 T 200 100" /></svg>
```

**為什麼是 AI 痕跡**：AI 畫的人物比例怪、手指多一隻、抽象螺旋就是「我不知道放什麼」的填空。

**台灣老闆的具體反應**：
- 「這人看起來怪怪的」
- 「這圈圈是什麼意思」

---

### 必避 6：Inter 系列 / Roboto / Arial 當 display font

```css
/* ❌ 通用無襯線當標題 */
h1 { font-family: 'Inter', 'Inter Tight', 'Roboto', 'Arial', sans-serif; font-weight: 900; }
```

**為什麼是 AI 痕跡**：Inter / Inter Tight / Roboto 是「中性安全」—— 所有科技公司、所有 AI 工具、所有 SaaS 都用。用在標題會讓文件變成「PowerPoint 內建模板」的氣味。

**Inter 家族統一避免**：Inter、Inter Tight、Inter Display 都算 AI 標配，除非品牌**已經官方採用 Inter**（那是品牌識別優先於 anti-slop，見本文「例外規則」），否則一律換掉。替代：Instrument Sans / Bricolage Grotesque / IBM Plex Sans / Geist Sans。

**台灣老闆的具體反應**：
- 「這是 Microsoft Word 打出來的嗎」
- 「跟我秘書做的一樣」

---

### 必避 7a：Data Slop（編造數字裝飾）

```html
<!-- ❌ 編造沒來源的 stats -->
<div>已服務 10,000+ 客戶</div>
<div>99.9% 滿意度</div>
<div>訂單成長 187%</div>
```

**為什麼是 AI 痕跡**：沒有真資料就編一個漂亮數字是 AI 最廉價的「填版面」手段。台灣老闆**特別敏感**—— 中小企業的數字是真實存在、可被稽核的，編一個「10,000 客戶」老闆自己看了都尷尬（我根本沒這麼多）。

**替代**：
- 有真數據 → 填真數據，即使是「38 家」也比「10,000+」有說服力
- 沒真數據 → 留 🔴 placeholder，跟老闆要
- 真的沒有數據可講 → 刪掉這個區塊，不要為了版面塞數字

---

### 必避 7b：Quote Slop（編造金句裝飾）

```html
<!-- ❌ 編造客戶評價 -->
<blockquote>「XX 公司讓我們業績翻倍，強烈推薦！」— 某大型連鎖客戶</blockquote>
```

**為什麼是 AI 痕跡**：「某大型連鎖客戶」「業界資深人士」這種匿名 quote 一眼就是編的。台灣業界小、圈子窄，**真實客戶願意露名才有可信度**。

**替代**：
- 有真 quote 且對方願意露名 → 用，附客戶名 + 職稱 + 日期
- 沒有真 quote → 留 🔴 placeholder，跟老闆要
- 老闆說「我們有案例但不能露名」→ 改用「某中部連鎖餐飲（3 家門市，1998 年起合作）」這種有具體細節但不露名的寫法

---

### 必避 7c：Bento Grid 過度泛濫

```html
<!-- ❌ 每份 AI 產出都長這樣 -->
<div class="bento">
  <div class="big">主要 feature</div>
  <div class="small">feature 2</div>
  <div class="medium">feature 3</div>
  ...
</div>
```

**為什麼是 AI 痕跡**：2023-2024 Apple / Vercel / Linear 帶起 bento 風潮後，所有 AI 產出的 landing page / 報告都無腦 bento。**除非資訊結構真的適合 bento（不同權重的 6-9 個並列 item），不要用**。

**替代**：
- 標準資料表 → 用表格，不要硬塞 bento
- 2-3 個 feature → 用水平 3 欄，不要拼成不規則 bento
- 月報數字 → 用數字卡水平排列 + 分隔線

---

### 必避 7d：大 Hero + 3 欄 Features + CTA（爛大街 landing page 模板）

```
┌────────────────────────┐
│    大標題 + Sub        │   ← Hero
│    [CTA Button]        │
├──────┬──────┬──────────┤
│ ✓ F1 │ ✓ F2 │ ✓ F3   │   ← 3 欄 feature
├────────────────────────┤
│  客戶 logo wall        │
├────────────────────────┤
│  [再次 CTA]            │
└────────────────────────┘
```

**為什麼是 AI 痕跡**：這個結構從 2015 年被用到今天。AI 訓練資料裡一半的 landing page 長這樣。**對中小企業老闆來說，這個結構的即時聯想是「像補教業官網」「像健身房廣告」**。

**替代**：依內容性質選非 template 結構——
- 產品說明 → 用「問題」「方案」「證明」三段式說書結構
- 服務介紹 → 用「流程圖」或「時間軸」取代 3 欄
- 公司簡介 → 用「編年史」或「成就列舉」

---

### 必避 8：每段加星號 / 火焰 / 💎 / 🔥

```markdown
<!-- ❌ AI 裝飾 -->
### ⭐ 核心價值
💎 高品質服務
🔥 火熱促銷
✨ 特別推薦
🎯 精準定位
```

**為什麼是 AI 痕跡**：這是 ChatGPT 早期 template 的遺毒。資訊密度低 + 裝飾符號多 = AI 生成。

**台灣老闆的具體反應**：
- 「像微商群組」
- 「這不是報告，是廣告」

---

## 心態原則：一千個 No，才配一個 Yes

最核心的反 slop 心法：**Don't add filler content**。每個元素都必須**earn its place**。

台灣老闆對「版面空」的焦慮常會傳染給您，誘導您加東西：多一段 quote、多一個圖示、多一排數字。**這個直覺要壓制**——空白不是內容問題，是構圖問題，用**留白、對比、節奏**解決，不是靠內容填滿。

### 三個自我質問（每加一個元素前）

1. 如果刪掉這段，設計會變差嗎？答案若是「不會」，就刪掉。
2. 這個元素解決了什麼真問題？如果是「讓頁面不那麼空」，刪掉。
3. 這個 stats / quote / feature 有真資料支撐嗎？沒有就標 🔴 不要編。

「One thousand no's for every yes」。

### 主動加內容前先問使用者

您覺得多加一段 / 一頁 / 一個 section 會更好？**先問使用者，不要單方面加**。原因：

- 使用者知道他的受眾比您清楚
- 加內容有成本（審閱時間、版面擠壓），使用者可能不想要
- 單方面加內容違反了「junior designer 向 manager 回報」的關係

---

## Scale 規範（字級 / 點擊區 / 對比度）

字級不夠大是台灣中小企業報告最常見的技術性問題（老闆年紀大、投影環境不好）：

### 簡報（1920×1080 PPT）

**分兩種用途，字級底線不同**：

**(A) 簡報型（遠距離投影，會議室投影、演講）**
- 正文**最小 24px**，理想 28-36px
- 標題 60-120px
- Section title 80-160px
- Hero headline 可以用 180-240px 的大字
- **永遠不要** 用 < 24px 的字放會議室投影簡報

**(B) 報告型（近距離閱讀，1920×1080 當單頁 hi-fi 報告用、列印 A3、電腦上看、LINE 群組傳圖、一頁式 battlecard）**
- 正文**最小 14px**，理想 14-18px（讀者眼睛離螢幕 40-60cm）
- 標題 40-72px
- eyebrow / caption / mono label 11-13px 可接受
- 如果同一份檔案**兩種用途都要**（既要螢幕看又要投影），取嚴標準：24px
- 怎麼判斷？問使用者「最終會不會投影？」—— 會 → 套 (A)；不會 → 套 (B)

1920×1080 的 battlecard、月報、客戶 brief 這類「一頁式 hi-fi 報告」模板屬於 (B)，14px 內文合理。

### 印刷文件 / A4 報告

- 正文**最小 10pt**（≈ 13.3px），理想 11-12pt
- 標題 18-36pt
- Caption 8-9pt

### 網頁 / 手機

- 正文最小 **14px**（給老人看用 16px）
- Mobile 正文 **16px**（避免 iOS 自動縮放）
- 可點擊元素最小 **44×44px**
- 行高 1.5-1.7（中文 1.7-1.8，繁中比英文需要更大行距）

### 對比度（避免「看不清楚」的投訴）

- 正文 vs 背景 **至少 4.5:1**（WCAG AA）
- 大字 vs 背景 **至少 3:1**
- 淺灰 `#888` 配白底是常見地雷—— 印刷或投影都糊

---

## 字型具體建議（避開 AI 愛用字）

AI 訓練資料讓它特別愛用 Inter / Roboto / Space Grotesk / Fraunces，這些字看起來「現代」但**已經變成 AI 味標配**：

### 避開的烂大街字

- Inter（AI 生成 landing page 標配）
- Roboto
- Arial / Helvetica（Office 預設）
- 純 system font stack
- Fraunces（AI 發現後用到爛）
- Space Grotesk（AI 最近的新歡）

### 有特點的 Google Fonts 冷門好選

**中文**：
- **Noto Serif TC**（穩定、繁中首選襯線）
- **Source Han Serif TC**（思源宋體，Adobe 出品，字型更飽滿）
- **Shippori Mincho**（日系明朝，中日混排場合好用）
- **jf open 粉圓 / 台北黑體**（在地化的開源字型，有個性）

**英文標題（display）**：
- Instrument Serif（近年人文感襯線的 Rising star）
- Cormorant Garamond（古典襯線的現代版）
- Bricolage Grotesque（可變字重的幾何無襯線）
- Playfair Display Italic（雜誌派愛用）

**英文內文（body）**：
- Geist Sans（Vercel 出的，乾淨）
- Work Sans（人文感無襯線）
- IBM Plex Sans（技術感但不冰冷）

**Mono（數字）**：
- IBM Plex Mono（數字對齊漂亮）
- JetBrains Mono（程式碼感 + 數字好看）

**好的搭配範式**：
- 襯線 display + 無襯線 body（editorial 氣質）
- Mono display + sans body（technical 氣質）
- Heavy display + light body（對比氣質）

---

## 現代 CSS 神器（用了品質翻倍）

以下 CSS 特性是區分「2020 年 AI 產出」和「2026 年設計師產出」的關鍵：

### 排版

```css
/* 標題斷行自動平衡，避免最後一行孤字 */
h1, h2, h3 { text-wrap: balance; }

/* 內文斷行自動避免孤字寡婦 */
p { text-wrap: pretty; }

/* 繁中排版神器：標點擠壓、行首行尾控制 */
p {
  text-spacing-trim: space-all;     /* 中文標點不吃兩個字位 */
  hanging-punctuation: first;        /* 引號吊掛到行首外 */
}

/* 中文行距加大（比英文需要多 10-20%） */
p { line-height: 1.75; }
```

### Layout

```css
/* CSS Grid + named areas = 可讀性爆棚 */
.layout {
  display: grid;
  grid-template-areas:
    "header header"
    "sidebar main"
    "footer footer";
  grid-template-columns: 240px 1fr;
}

/* Subgrid 對齊多卡片內元素 */
.card { display: grid; grid-template-rows: subgrid; }
```

### 色彩

```css
/* color-mix 衍生 hover / 半透明變體 */
.button:hover {
  background: color-mix(in oklch, var(--brand) 85%, black);
}
```

### 條件樣式

```css
/* :has() 讓條件樣式變簡單 */
.card:has(img) { padding-top: 0; }

/* container queries 讓卡片真正響應式 */
@container (min-width: 500px) { ... }
```

**用這些現代 CSS**，中小企業老闆看不出差別，但**一眼區分 slop vs craft**的效果大。

---

## 取代方案（一一對應）

| 必避 | 取代 |
|------|------|
| 紫/藍紫漸變背景 | 單色區塊；或極細漸變（10% 亮度差） |
| Emoji icon | Lucide 線條 icon（SVG）或純文字 label；或 Unicode 幾何符號 ▲ ■ ● |
| 圓角 + 左色條卡片 | 直角 + 細邊 top border 1-2px |
| 全部 12px 圓角 | 按鈕 4-6px、卡片 0 或 2px、照片 0 |
| 抽象 SVG 裝飾 | 真實照片 placeholder + 提示「需要提供」；或純留白 |
| Inter / Roboto 當 display | Noto Serif TC / Playfair Display / Instrument Serif / Cormorant Garamond（標題） |
| emoji 裝飾符號 | 編號 01 / 02 / 03；或羅馬字 I / II / III；或章節記號 § |

---

## 正確範例（對照組）

### 範例 1：標題區

```html
<!-- ❌ AI 味 -->
<div style="background: linear-gradient(135deg,#667eea,#764ba2); padding: 40px; border-radius: 12px;">
  <h1 style="font-family: Inter; color: white;">🚀 營收成長報告</h1>
  <p style="color: white;">💰 Q4 業績超標 30%</p>
</div>

<!-- ✅ 正經版 -->
<header style="border-bottom: 3px double #1a1a1a; padding: 40px 0;">
  <div style="font-family: IBM Plex Mono; font-size: 12px; letter-spacing: 0.3em; color: #8b2e2e;">QUARTERLY REPORT · 2026 Q4</div>
  <h1 style="font-family: 'Noto Serif TC'; font-weight: 900; font-size: 56px; margin-top: 8px;">營收成長報告</h1>
  <p style="font-family: 'Noto Serif TC'; font-style: italic; color: #4a4a4a;">本季業績達成率 130%，詳見第二節</p>
</header>
```

### 範例 2：資料卡

```html
<!-- ❌ AI 味 -->
<div style="border-radius: 12px; border-left: 4px solid #3B82F6; box-shadow: 0 4px 6px rgba(0,0,0,0.1); padding: 24px;">
  <h3>📊 營收</h3>
  <div style="font-size: 32px;">$12.5M</div>
  <p>🔥 成長 30%</p>
</div>

<!-- ✅ 正經版 -->
<div style="border-top: 2px solid #1a365d; padding: 20px 0; border-bottom: 1px solid #d8d4cc;">
  <div style="font-family: 'IBM Plex Mono'; font-size: 11px; letter-spacing: 0.2em; color: #8a8a8a;">REVENUE · QOQ</div>
  <div style="font-family: 'IBM Plex Mono'; font-size: 48px; font-weight: 500; margin: 8px 0;">12.5M</div>
  <div style="font-family: 'Noto Sans TC'; font-size: 14px; color: #4a4a4a;">較上季 <span style="color: #1a365d; font-weight: 700;">+30%</span></div>
</div>
```

### 範例 3：條列

```markdown
<!-- ❌ AI 味 -->
### ⭐ 本季重點
- 🎯 進入新市場
- 💰 提高毛利率
- 🚀 加速產品線
- ✨ 新客戶簽約

<!-- ✅ 正經版 -->
### 本季重點
01  進入北部 B2B 市場，首批客戶三家
02  毛利率自 28% 提升至 34%
03  新產品線 X-3 提前兩週出貨
04  簽入年約客戶—— 中鋼衛星廠
```

---

## 台灣特化的反 AI 細節

### 紫色的文化包袱

台灣老闆對紫色的負面聯想：
- **信仰**：紫色在部分傳統場合有特殊含義（靈性、法會）
- **產業**：紫色被視為「美容」「SPA」「算命」的顏色
- **世代**：50+ 老闆覺得紫色「不是做生意的顏色」

**替代**：深藍灰 `#1a365d` / 酒紅 `#722f37` / 墨綠 `#2d4a3e`—— 這些是台灣商業場合「安全」的色彩。

### 圓角過大的「電商感」

台灣電商平台（蝦皮、momo、PChome）大量使用 12-16px 圓角卡片。老闆一看到會直覺聯想到「C2C 賣東西的」，對 B2B 正式文件是扣分。

**替代**：直角或 2-4px 微圓角。

### Emoji 的「年輕化」誤解

台灣商場文化中，emoji 等同於「不夠尊重」—— 尤其對長輩或客戶。商務 email 不用 emoji、正式簡報不用 emoji。

**例外**：對內員工溝通、對 Z 世代消費者的行銷文案。

### 襯線體的「權威」連結

台灣主流報紙（經濟日報、工商時報、聯合報）的標題都用襯線體。襯線體 = 報紙 = 權威。用 Noto Serif TC 做標題，老闆會直覺覺得「像正經文章」。

---

## 快速自檢（交付前過一遍）

- [ ] 有沒有紫/藍紫漸變？有 → 改單色或 10% 亮度差漸變
- [ ] 有沒有 emoji 當 icon 或裝飾？有 → 改文字 label / Lucide icon / 編號
- [ ] 卡片是不是 12px 圓角 + 左色條？是 → 改直角 + top border
- [ ] 標題是不是 Inter / Roboto？是 → 改 Noto Serif TC / Playfair
- [ ] 有沒有 SVG 抽象人物 / 螺旋 / 流線？有 → 改照片 placeholder 或留白
- [ ] 裝飾符號（🔥 💎 ⭐）有出現嗎？有 → 改編號或章節記號
- [ ] 整份看起來像「經濟日報」還是「SaaS dashboard」？要前者

---

## 快速參考

1. **紫漸變 = 即時 AI 警報**，看到直接改單色
2. **Emoji 正式場合絕對不用**，例外只有年輕人內部溝通
3. **圓角 12px + 左色條 = SaaS 味**，改直角 + top border
4. **標題用襯線體（Noto Serif TC）** 是台灣老闆的「專業」視覺語言
5. **裝飾符號換編號**（01 02 03 或 I II III），比 🔥 專業 10 倍
6. **One thousand no's for every yes** —— 不加 filler content，先刪後加
7. **字型避開 Inter / Roboto / Fraunces**，用有特點的 display + body 配對
8. **Scale 底線**：簡報 ≥ 24px / 印刷 ≥ 10pt / 網頁 ≥ 14px

---

## 決策速查：當您猶豫時

- 想加個漸變？→ 大概率不加
- 想加個 emoji？→ 不加
- 想給卡片加圓角 + border-left accent？→ 換其他強調方式
- 想用 SVG 畫個 hero 插畫？→ 不畫，用 placeholder
- 想加一段 quote 裝飾？→ 先問使用者有沒有真 quote
- 想加一排 icon features？→ 先問要不要 icon，可能不需要
- 用 Inter？→ 換一個更有特點的
- 用紫色漸變？→ 換一個有根據的配色
- 想無腦做 bento？→ 先想資訊結構是否適合

**當您覺得「加一下會更好看」的時候——那通常是 AI slop 的徵兆**。先做最簡的版本，只在使用者要求時加。

---

## 來源對照

- **必避 1-7（紫漸變 / emoji / 圓角左色條 / 全 12px / SVG 人物 / Inter / 裝飾符號）**：Claude Design 原版「AI slop tropes」+ huashu content-guidelines.md 黑名單
- **必避 7a-7d（data slop / quote slop / bento 泛濫 / 爛大街 landing 模板）**：huashu content-guidelines.md
- **Don't add filler content / One thousand no's**：Claude Design 原版直譯
- **Scale 規範**：Claude Design「appropriate scales」+ huashu Scale 規範
- **字型冷門建議 / 現代 CSS 神器**：Claude Design + huashu content-guidelines.md
- **台灣原創**：
  - 老闆對紫色的文化聯想（美容、SPA、算命、法會）
  - 電商平台圓角造成的「C2C 賣東西感」
  - 「像補教業官網、像健身房廣告」的 landing page template 聯想
  - 襯線體與台灣報紙的連結（經濟日報 / 工商時報 / 聯合報）
  - 繁中字型具體建議（Noto Serif TC / jf 粉圓 / 台北黑體）
