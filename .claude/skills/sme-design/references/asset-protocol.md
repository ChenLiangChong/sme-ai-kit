# asset-protocol.md —— 品牌資產抓取 5 步

**何時載入**：任何產出物涉及「具體品牌」時強制載入——客戶自己的公司、要分析的競品、要放上去的合作夥伴 logo。目的是避免從記憶猜品牌色（最常見的 AI 失誤源頭）。

---

## 核心原則

**絕不從記憶猜品牌色。** 您對台積電是深綠、鴻海是橘、統一是紅——這些印象可能錯、可能過時、可能只對。正確的做法是**從官方資產抓真實值**。

抓不到就標 🔴「未知」讓使用者補，**不要猜一個貼上去**。使用者貼 PPT 給合夥人看，一眼看到主色錯，整份文件就廢了。

---

## 資產 > 規範（本協議第一優先）

**視覺設計的「真實感」八成來自資產，兩成來自規範**。色值、字型、排版規則是「規範」—— 它們只決定東西長得「一致」。但一份報告看起來像**該品牌**、不是「一份關於該品牌的報告」，靠的是**真實資產**：Logo、產品圖、UI 截圖。

### 資產的識別度階梯

| 資產類型 | 識別度貢獻 | 必需性 |
|---------|----------|--------|
| **Logo** | 最高 | 任何品牌必備 |
| **產品圖／渲染圖** | 極高 | 實體產品必備 |
| **UI 截圖／介面素材** | 極高 | 數位產品必備 |
| 色值 | 中 | 輔助 |
| 字體 | 低 | 輔助 |

意思是：**有 Logo + 產品圖、配色略失真**，看起來仍像該品牌；**色值字體全對、沒 Logo 沒產品圖**，看起來只是一份「用該品牌配色的通用文件」。前者可接受，後者是失敗。

### 5-10-2-8 素材門檻（典型一份 hi-fi 報告）

做一份有品牌識別度的 hi-fi 報告，典型需要：

- **5 張產品圖**（或實景照、渲染圖）—— 不同角度／情境
- **10 張 UI 截圖**（如果是數位產品）—— 首頁／流程／詳情等關鍵畫面
- **2 組色值**（主色 + 強調色，至少）
- **8 種字型 weight**（字型家族內部的字重變化，Light / Regular / Medium / Bold … 至少能涵蓋標題、內文、caption）

**這是「門檻」不是「目標」**——湊不到這個量，報告會視覺單薄。**沒湊夠就先停，跟使用者要**，不要硬做。典型的不夠做法：只有 Logo + 1 張產品圖 → 產出會有大片空白需要填裝飾（然後就開始生 AI slop）。

### 找不到 Logo 要停下問

**找不到可用 Logo 時，停下來問使用者，不要繼續**。三個絕對禁區：

- ❌ **絕不 AI 生成替代 Logo** —— 畫一個「感覺像他們的」是造假
- ❌ **絕不用 CSS 方塊 / SVG 剪影手畫** —— 圓圈 + 公司首字縮寫、幾何形剪影、簡筆畫都算
- ❌ **絕不用通用剪影**（建築物、人頭、抽象符號）充當 Logo

**正確做法**：
1. 先試 Step 2 的所有管道（press-kit、inline SVG、社群大頭貼、Brandfetch）
2. 全失敗 → 放 `[品牌名] Logo（待提供）` 的灰色方塊 placeholder，標 🔴
3. 交付訊息裡明說：「Logo 抓不到，請您給我一張（SVG / PNG / 名片照 / 招牌照都可），我再補上。」

### 執行規則（違反本協議）

以下情況算**違反本協議**，不要做：

- 🚫 **只抽色值不找 Logo** —— 配色對、沒 Logo，報告失去 80% 識別度
- 🚫 **用 CSS 剪影 / SVG 手畫替代真實產品圖** —— 幾何方塊、漸變形狀假裝成手機／盒子／產品
- 🚫 **記憶畫 Logo** —— 「我印象中那個字的 M 是這樣彎」— 沒資產就不畫
- 🚫 **抓到低解析 Logo 硬放大** —— 糊掉比缺失更難看，寧可放 placeholder
- 🚫 **Logo 抓不到就改風格用文字 Wordmark 硬扛** —— 除非品牌本身就是 Wordmark（無圖形 Logo），否則是在變相自畫

**心法**：資產不夠的時候，**缺失比造假好**。placeholder 讓使用者知道要補；造假讓使用者誤以為那就是最終樣貌，到印刷階段才發現出錯。

---

## Design Context 的優先序

在動手抓資產前先想一件事：**這份設計可以借力的 context 有幾層？** 按品質排序：

1. **使用者的 Design System / UI Kit** — 有最完整的組件、色票、字型規範（最理想，通常中小企業沒有）
2. **使用者的 Codebase** — 有 `theme.ts` / `tokens.css` / `_variables.scss`，可以直接讀 exact values
3. **使用者已發布的產品 / 網站** — 用 curl/WebFetch 抓 HTML + CSS、grep 色值
4. **品牌指南 / Logo / 已有素材** — Brand Guide PDF、Logo SVG、過去的 PPT
5. **競品 / 參考對象** — 「像 XX 網站那樣」 —— 請使用者提供 URL 或截圖
6. **已知的公開設計系統（fallback）** — Radix Colors / Tailwind palette / Material Design（使用者什麼都沒有時的起點）

**心法**：花 10 分鐘收集 context，比花 1 小時憑空做 hi-fi 有價值 100 倍。Step 1 時**先問、再做**，不要直接跳到 grep。

### 有 Codebase 時怎麼讀

使用者把公司 SaaS 產品 / 官網 repo 指給您看時，**不要憑印象畫**，讀代碼 lift exact values：

```bash
# 找所有樣式相關檔案
find <repo> -type f \( -name "*.ts" -o -name "*.css" -o -name "*.scss" \) \
  | xargs grep -l -E "color|theme|token|brand" | head -20

# 優先讀這些
# - src/theme.ts / src/styles/tokens.css / tailwind.config.js
# - src/components/Button.tsx（看 hover/active 的色彩與陰影）
# - src/styles/global.css（看 font-face 和基礎重置）
```

**目標**：讀下來 30+ 個具體 value（hex、px、font-family、shadow spec）才算真的 lift 到。憑「大概」印象做出來的跟 codebase 不會 match。

---

## Step 1 —— 問（一次問完）

**資產清單一次問全，不要來回問三次**。建議開場模板：

> 「要幫您產這份 [文件類型]，涉及 [品牌 A、品牌 B]。請問您手上有以下資產嗎？(有哪幾個就回哪幾個，沒有的我再想辦法)
>
> 1. **Logo 檔**（SVG / PNG 優先，JPG 也行）
> 2. **產品照片**（要放進報告的那幾張）
> 3. **品牌色值**（HEX / RGB 清單，或 Brand Guide PDF）
> 4. **字型**（有指定中／英文字型嗎）
> 5. **既有設計模板**（過去的簡報、網站截圖）
> 6. **官網網址**（我可以自己去抓）」

如果使用者回「都沒有，只有公司名」—— 跳 Step 2，但要告知：「沒有資產我會盡量從官網抓，抓不到的會標 🔴 未知請您確認」。

---

## Step 2 —— 搜官方

按優先順序嘗試：

### 2.1 品牌專屬頁面

```
<brand>.com/brand
<brand>.com/press
<brand>.com/press-kit
<brand>.com/media-kit
<brand>.com/about/logo
<brand>.com.tw/press
```

多數上市櫃公司、知名品牌有 press-kit（投資人關係 / 媒體中心）。

### 2.2 Header 的 inline SVG

用 `WebFetch` 或 `curl` 抓網站首頁 HTML，搜 `<svg`——很多網站 logo 直接 inline 在 header，可以整段複製下來當 SVG 檔用。

```bash
curl -sL https://brand.com.tw | grep -A 30 '<svg'
```

### 2.3 社群大頭貼

- **FB 粉專**：`https://graph.facebook.com/<page_id>/picture?type=large`
- **IG**：右鍵 profile 圖片另存（低解析度，只能當備援）
- **LinkedIn**：公司頁 logo（PNG 300x300）

### 2.4 Google Images 反查

搜 `<品牌名> logo SVG` 或 `<品牌名> logo transparent`—— Wikipedia、Vecteezy、Brandfetch 常有高解析度版本。**Brandfetch（brandfetch.com）是抓品牌資產最快的通路**，輸入 domain 直接給 logo + 色值 + 字型建議。

### 2.5 台灣公司專屬通路

- **證交所公開資訊觀測站**（mops.twse.com.tw）：上市櫃公司年報 PDF 封面通常有高解析 logo
- **經濟部商業司**（gcis.nat.gov.tw）：公司登記資料，偶爾有 logo
- **各地工業區管理處**：傳產公司常在管理處網頁有簡介 + logo

---

## Step 3 —— 下載（三條兜底路徑）

依品質排序，失敗就降級：

**路徑 A：SVG 獨立檔（最佳）**
- 從 press-kit 下載 `.svg` 或 `.ai` / `.eps`
- 可自由改色、無限放大

**路徑 B：網頁 inline SVG**
- 整段 `<svg>...</svg>` 複製存成 `.svg`
- 保真度 100%，但可能有 class 依賴需清

**路徑 C：社群大頭貼（兜底）**
- PNG，通常 400x400 以內
- 品質堪用，但放大會糊
- 用於小尺寸 icon（如 footer、caption）

**全失敗時**：在報告該位置放灰色方塊 + 文字 `{品牌名} Logo（待提供）`，標 🔴，Step 1 再跟使用者要。

---

## Step 4 —— grep 色值

從下載的資產（SVG / HTML / CSS）抓所有色值，按頻率排序：

```bash
# 從 SVG 抓
curl -sL https://brand.com/logo.svg | grep -oE '#[0-9a-fA-F]{6}' | sort | uniq -c | sort -rn

# 從網站 inline CSS 抓
curl -sL https://brand.com | grep -oE '#[0-9a-fA-F]{6}' | sort | uniq -c | sort -rn | head -20

# 抓 rgb() 和 rgba()
curl -sL https://brand.com | grep -oE 'rgba?\([0-9, .]+\)' | sort | uniq -c | sort -rn
```

**典型輸出解讀**：
```
     42 #1a365d   ← 出現 42 次，極可能是主色
     38 #ffffff   ← 白底（忽略）
     21 #f5f1e8   ← 背景米色，可能是輔色
     14 #2c3e50   ← 文字色
      8 #d4001a   ← 強調色（限用）
```

**判斷主色的原則**：
- 排除純白 `#ffffff`、純黑 `#000000`、近灰 `#xxxxxx`（R=G=B 或差距 < 10）
- 出現頻率最高的「有飽和度」的顏色通常是主色
- 出現次數不多但對比強烈的可能是強調色（accent）

**補 Tailwind config**：很多現代網站用 Tailwind，config 裡有完整色票：

```bash
curl -sL https://brand.com/_next/static/chunks/pages/_app-*.js | grep -oE 'color[s]?:\s*\{[^}]+\}'
```

---

## Step 5 —— 固化

在**該專案的根目錄**寫一份 `brand-spec.md`（不是全域，是該次報告的專案資料夾）：

```markdown
# {品牌名} Brand Spec

**來源**：官網 brand.com（抓於 2026-04-23）
**信心等級**：🟢 有 Brand Guide / 🟡 從官網 grep / 🔴 純猜測

## 色彩

| 角色 | HEX | 用途 |
|------|-----|------|
| `--brand-primary` | `#1a365d` | 主標題、重點區塊背景 |
| `--brand-secondary` | `#f5f1e8` | 底色、區塊分隔 |
| `--brand-accent` | `#d4001a` | 警訊、關鍵數字 |
| `--brand-ink` | `#1a1a1a` | 內文 |

## 字型

- 中文：Noto Serif TC（標題）/ Noto Sans TC（內文）
- 英文：Playfair Display（標題）/ Inter（內文）
- 數字：IBM Plex Mono

## Logo

- 主檔：`assets/brand-logo.svg`
- 白底版：`assets/brand-logo-dark.svg`
- 最小尺寸：40px 寬

## 使用原則

- 主色**禁止**用在大面積背景（超過 30% 版面）
- Logo 週邊要留 Logo 高度 50% 的淨空
- 標題字重 700+，內文字重 400-500
```

所有 HTML 引用 CSS variable，不寫死色值：

```css
:root {
  --brand-primary: #1a365d;  /* 從 brand-spec.md 來 */
}
.header { background: var(--brand-primary); }
```

這樣後續換色、換品牌都是改一個地方。

### 衍生深淺變體：oklch 優先

拿到主色後常常要衍生「變亮 20%」「變暗 15%」的版本（hover 狀態、背景、邊線）。**用 oklch 不要用 hsl/RGB 直接加減**：

```css
:root {
  --brand-primary: #1a365d;                         /* 給使用者看的 hex */
  --brand-primary-light: oklch(from #1a365d calc(l + 0.18) c h);
  --brand-primary-dark:  oklch(from #1a365d calc(l - 0.08) c h);
  --brand-primary-soft:  oklch(from #1a365d calc(l + 0.35) calc(c * 0.4) h);
}

/* 或直接計算後寫死，給舊瀏覽器備援 */
:root {
  --brand-primary: #1a365d;
  --brand-primary-light: #3d5f8a;
  --brand-primary-dark: #12253f;
  --brand-primary-soft: #c5d2e3;
}
```

**為什麼 oklch**：hsl 調 lightness 時色相會漂（藍變藍綠、紅變粉），oklch 不會——保持「同一個顏色的不同深度」的直覺。這是 2024+ 設計系統的預設選擇。

**hex fallback**：老闆的 PPT 要的是 hex，印刷廠要 Pantone/hex。oklch 是您內部計算的工具，**對外交付仍用 hex**。

---

## 備援：傳產公司沒官網怎麼辦

台灣很多中小企業——尤其製造業、傳產、家族事業——**沒有獨立網站**，只有 Facebook 粉專、104 徵才頁、或連粉專都沒有。這是 asset-protocol 最常遇到的情境。

**五條備援路徑，依品質排序**：

### 備援 1：Facebook 粉專

- **大頭貼**：`https://graph.facebook.com/<pagename>/picture?type=large`（公開粉專可直接抓）
- **封面照片**：右鍵另存，通常是品牌視覺最用心的一張
- **相簿「公司簡介」/「產品型錄」**：常有高解析度 logo 變體
- **色值抓取**：把大頭貼和封面丟進線上 color picker（如 imagecolorpicker.com），手動挑 3 個主要色

### 備援 2：104／1111 徵才頁

徵才頁有「公司簡介」欄位，老闆通常會放：
- 公司 logo（PNG，解析度中等）
- 公司地址、電話（拿來對資料用）
- 主要產品／服務描述（當後續報告內容素材）

網址格式：`www.104.com.tw/company/<company_id>`

### 備援 3：Google My Business（Google 商家）

搜尋「<公司名> <地址／區域>」，右側會跳 Google 商家卡片：
- 商家大頭貼（可能是 logo 或店面照）
- 店面實景照（當報告配圖）
- 評論數、評分（當報告社會證明素材）

### 備援 4：名片／招牌照片

直接**跟使用者要一張名片照片或公司招牌照**——這是實體世界最官方的品牌資產來源。

```
向使用者要：
- 一張名片（正面）
- 一張招牌照片（清楚、直拍）
- 一張發票或出貨單（有 logo 的）
```

用 Read 工具讀圖，手動挑色值。實體印刷物色值比網站可信——因為那是老闆真的花錢印出來的。

### 備援 5：全沒有時的「通用傳產」預設

真的一張資產都生不出來時，用以下通用方案並**明確標示 🔴**：

- 主色：`#1a365d`（深藍灰，傳產最安全值）
- 輔色：`#f5f1e8`（米白底，溫和）
- 強調色：`#8b2e2e`（暗紅，限用於關鍵處）
- 字型：Noto Serif TC + Noto Sans TC（繁中最穩）

**交付時加註**：
> 🔴 本份報告使用通用傳產配色，等您提供名片／招牌照片後我再調整為實際品牌色。

使用者看到 🔴 會知道要補資料，不會誤以為是您「設計出來的」品牌色。

---

## 反模式（不要做）

- ❌ 「統一企業應該是紅色」→ 記憶猜色，錯了很難看
- ❌ 「我幫您配一個日系風的綠」→ 沒問過就改品牌色
- ❌ 「網站沒抓到，我用隨機色」→ 隨機不如標 🔴
- ❌ 「Logo 抓不到我畫一個」→ 絕不畫 logo，要就放空白框
- ❌ 「這顏色好看，我改一下」→ 您不是該品牌的設計師，沒有權利改品牌色

---

## 快速參考

1. **先問、再搜、最後才猜**（猜要標 🔴）
2. **Logo 三條路徑**：官網 press-kit → 網頁 inline SVG → 社群大頭貼
3. **色值 grep 法**：`curl <url> \| grep -oE '#[0-9a-fA-F]{6}' \| sort \| uniq -c \| sort -rn`
4. **固化到 brand-spec.md** + CSS variables，HTML 不寫死色值
5. **傳產沒官網**：FB 粉專 → 104 → Google 商家 → 要名片照 → 標 🔴 通用色
6. **Codebase 在手時優先讀 tokens**，憑印象畫是懶惰不是風格
7. **衍生色用 oklch**，交付給使用者仍用 hex

---

## 來源對照

- **Design Context 6 級優先序**：Claude Design 原版 + huashu design-context.md
- **從 Codebase lift exact values**：Claude Design「lift exact values — hex codes, spacing scales, font stacks, border radii」
- **5 步硬流程（問 → 搜 → 下載 → grep → 固化）**：huashu design-context.md 與 workflow.md 融合
- **oklch 衍生色**：Claude Design 原版 + huashu content-guidelines.md
- **台灣原創**：傳產 5 條備援路徑（FB 粉專 / 104 / Google 商家 / 名片照 / 通用傳產預設）、台灣公司專屬通路（證交所觀測站 / 經濟部商業司 / 工業區管理處）、反模式的台灣化舉例
