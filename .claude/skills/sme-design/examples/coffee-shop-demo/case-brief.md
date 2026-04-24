# case-brief.md — 獨立精品咖啡店競品與定位分析 Deck

> **dogfooding 範例**：sme-ai-kit 的 `social-media` + `sme-design` 雙 skill 串接產出。這份文件是 **Skool 第一堂直播課的講師示範作品**，學員課程現場用自己的產業資料跑一份同樣結構的報告。
>
> 所有「我方品牌」欄位一律用 `[範例咖啡品牌]`、負責人 `[負責人]`、員工 `[員工甲]` `[員工乙]`、地點 `[XX 區]`、內部數字用 `[XX]` 或標 🔴——這是全系統的占位符原則，學員要替換的欄位都明顯。
>
> 競品是真實品牌（星巴克、路易莎、興波 Simple Kaffa），引用的是公開市場事實，不是編造 quote。

---

## 1. 案例脈絡（模擬「老闆客戶」）

- **品牌名**：`[範例咖啡品牌]`
- **位置**：`[範例北部商圈]`（台北某非一級商圈，單店）
- **業態**：獨立精品咖啡店，開業 2-3 年；自家烘焙 + 手沖 + 濃縮 + 少量輕食
- **團隊**：老闆主力、2 位正職 barista、假日 1 位兼職
- **客群輪廓**：週間 70% 外帶（辦公室族）、假日 70% 內用（生活型客群 + 咖啡愛好者）

### 老闆的五個煩惱（deck 要回答的核心問題）

| # | 煩惱 | 對應 deck 頁 |
|---|------|--------------|
| 1 | 500m 內新開路易莎／星巴克門市，外帶客被瓜分 | P4 競爭地圖 + P5 星巴克 battlecard + P6 路易莎 battlecard |
| 2 | 生豆成本漲 20%，單杯毛利從 60% 掉到 48%（🔴 假設數字） | P2 Exec Summary + P7 興波 battlecard（精品同業的應對方式）+ P10 90 天清單 |
| 3 | 有人介紹 `[範例信義區店面]` 要不要擴第二家 | P8 定位 + P10 90 天清單 + P11 風險 |
| 4 | 要不要上 Uber Eats（30% 抽成、包裝塑膠、單價壓低） | P8 定位（通路選擇）+ P9 訊息框架（通路版本）+ P11 風險 |
| 5 | 熟客變少但沒會員系統、不知原因 | P9 訊息框架 + P10 90 天清單（啟動 LINE OA + 熟客訪談） |

### 報告用途

老闆 + 合夥人週末會議室決策用：

- **主要**：筆電投電視（1920×1080 簡報模式）
- **次要**：A4 彩色列印做筆記（合夥人要在上面畫記）
- **衍生**：LINE 群組分享節選截圖給會計師、供應商窗口

---

## 2. 十題最小 context（我自己代答「範例老闆」立場）

對照 `references/junior-workflow.md` Step 0 必問五類。

| # | 題目 | 範例老闆的答案 |
|---|------|---------------|
| 1 | 這份報告給誰看？ | 老闆 + 合夥人（2 人）。合夥人不懂行銷術語，但看得懂數字表格和競爭態勢圖 |
| 2 | 呈現場合？ | 週末 2-3 小時會議，筆電投 55 吋電視 + A4 彩印在桌上。結束後可能傳 LINE 群組給會計師 |
| 3 | 有沒有品牌資料？ | 🔴 沒有 Brand Guide、沒有制式色票，只有 IG 大頭貼（深棕色＋咖啡豆插畫）。**本案採「沒有品牌資產」路徑**，用中性深藍灰 `#1a365d` + 仿報紙米底 `#f5f1e8` + 酒紅 `#8b2e2e` 當主視覺；交付時明示「這是通用推薦色，等您提供店招／名片照片我再改」 |
| 4 | 有沒有參考的現有產品／網站？ | 沒有過去簡報。參考氣質：「像經濟日報社論、要穩重不要跳」；拒絕「看起來很電商／很 SaaS」 |
| 5 | 資料手上有了嗎？ | 競品資料我（Claude）自己上網查（2024-2026 公開數據可查）。內部數據（單杯毛利、熟客流失率、每月營收）老闆**手上沒整理**，留 🔴 給老闆填 |
| 6 | 保真度多高？ | Full hi-fi，但資料層允許 🔴 混在裡面（因為老闆要帶回去填） |
| 7 | Scope？ | 12 頁完整 deck，一次交付 |
| 8 | Variations 想看幾種？ | 給 1 個方向做到位即可（本次是 dogfooding 範例，不做 variations；真實客戶會給 3 個） |
| 9 | 要即時調哪些參數？ | 主色、金額欄位（🔴 填實數）、地點名（`[範例北部商圈]` → 真地點）、競品名保留但可以加備註 |
| 10 | 匯出需求？ | HTML（電視投影）+ PPT（A4 列印、寄給合夥人）。PDF 非必要 |

### 任務專屬題（Battlecard 3 家）

| # | 題目 | 答案 |
|---|------|------|
| B1 | 要比較哪 3 家？ | **星巴克**（國際連鎖代表，代表「氛圍 + 品牌信任 + 穩定」）、**路易莎**（本土連鎖代表，代表「價格戰 + 通路密度 + 快速複製」）、**興波 Simple Kaffa**（獨立名店頂標，代表「專業極致 + 目的地型消費 + 匠人敘事」）。三家剛好涵蓋「量-價-質」三個方向，老闆才能對自己做 triangulation |
| B2 | 每家要抓哪些 objection？ | 星巴克：「大品牌比較安全、位置方便、空間好」；路易莎：「便宜又穩定、點數活動多、隨處可見」；興波：「世界冠軍做的咖啡當然比較好、值得專程去」 |
| B3 | 客群重疊度怎麼看？ | 星巴克：中重疊（共同搶商務外帶、生活型內用）；路易莎：重度重疊（共同搶低價外帶）；興波：輕度重疊（客群是週末目的地型，但「精品」這個標籤重疊，客戶會拿它比） |

---

## 3. 視覺系統決策（寫在前面，後面 HTML 直接引用）

### 風格選擇：顧問諮詢所風格 + 雜誌特別報導感

對照 `references/design-philosophy.md`：

- **主結構走「顧問諮詢所報告版」**（Page 3 section 3）
  - 理由：老闆要決策、合夥人要看數據表格、受眾是 40-50 歲台灣中小企業主——「像 McKinsey / BCG 但用繁中」是最高信任感的視覺語言
  - 特徵：明確 12 欄 grid、數字靠右對齊、Exhibit N / Figure N 編號、Footer 固定放資料來源方法論、幾乎不用圓角
- **關鍵頁面混入「雜誌特別報導」氣質**（Page 2 section 2）
  - 用在封面、Executive Summary、P8 定位建議——讓老闆看到「這是精心寫的東西，不是草稿」
  - 特徵：襯線標題、首字放大、pull quote 大字引言
- **避開**：新創 Pitch（太 hype、不適合老闆）、政府標案（太冷、合夥人看了累）、日式極簡（密度不足）、經濟日報（太老派，獨立咖啡店氣質要一點質感）

### 主色系統（🔴 無品牌資產，用中性推薦）

對照 `references/asset-protocol.md` 備援 5（全沒有時的「通用傳產」預設），略做咖啡業調整：

```css
:root {
  /* Primary — 深藍灰（顧問版主色，穩重、可信） */
  --brand-primary:       #1a365d;
  --brand-primary-dark:  #0f2340;
  --brand-primary-light: #3d5f8a;

  /* Secondary — 米底（雜誌版底色，咖啡業的溫度） */
  --paper:               #f5f1e8;
  --paper-dark:          #e8e2d4;

  /* Ink — 文字色 */
  --ink:                 #1a1a1a;
  --ink-soft:            #4a4a4a;
  --ink-mute:            #8a8a8a;

  /* Accent — 酒紅（只用在關鍵對比、警訊、🔴 標記） */
  --accent:              #8b2e2e;

  /* Grid / Lines */
  --line:                #d8d4cc;
  --line-soft:           #eae5db;
}
```

**選色邏輯**：
- 深藍灰 = 理性、決策感（顧問版主色）
- 米底 = 溫度、咖啡業的質感（雜誌版底色）—— 在關鍵 Exec Summary、battlecard 小區塊用，破解純白的冷調
- 酒紅 = 警訊（🔴 標記、風險、關鍵對比數字）—— 絕不用在大面積
- **避開**：紫漸變、任何飽和色塊、emoji 裝飾（對照 `anti-slop.md` 必避 1、2、3）

### 字型系統

對照 `anti-slop.md` 字型建議區：

```css
/* 標題：雜誌氣質襯線 + 繁中穩定襯線 */
--font-display: 'Playfair Display', 'Noto Serif TC', serif;

/* 副標 / 內文：顧問版無襯線 */
--font-body:    'Instrument Sans', 'Noto Sans TC', sans-serif;

/* 數字 / 標籤：Mono 對齊 */
--font-mono:    'IBM Plex Mono', monospace;
```

**避開**：Inter、Roboto、Fraunces（anti-slop 必避 6）

### Grid 與字階

1920×1080 報告型（**不是**簡報型——老闆近距離看螢幕、A4 列印）：

- **Grid**：12 欄，左右 margin 80px，gutter 24px
- **Safe area**：1760×920（扣除 top/bottom 80px、left/right 80px）
- **字階（對照 anti-slop.md Scale 規範 B 報告型，正文 14-18px）**：

| 層級 | 字級 | 字型 | 用途 |
|------|------|------|------|
| Hero | 72-96px | Playfair Display / Noto Serif TC | 封面主標 |
| H1 | 48-56px | Noto Serif TC Bold | 頁面主標 |
| H2 | 32-36px | Noto Serif TC Bold | 節標題 |
| H3 | 20-22px | Noto Sans TC SemiBold | 區塊標題 |
| Body | 14-16px | Noto Sans TC 400, line-height 1.7 | 正文（繁中行距加大） |
| Label | 11-13px | IBM Plex Mono uppercase, letter-spacing 0.15em | Eyebrow、Exhibit 編號 |
| Data Big | 48-72px | IBM Plex Mono Medium | 關鍵數字 |
| Data Tabular | 14-16px | IBM Plex Mono 400 | 表格數字 |

### 版面通用元素（每頁都有）

- **Top ribbon**：2px 深藍灰線條分隔 header 區（顧問版典型）
- **Exhibit 編號**：右上角小字 `EXHIBIT 01 / 12 · [範例咖啡品牌] × 獨立精品咖啡店競品分析`
- **Footer**：左側資料來源簡寫、中間 `[範例咖啡品牌] · 內部決策用途 · v2026-04`、右側頁碼 `02 — 12`
- **🔴 標記**：酒紅色小圓點 ● + 「待補」提示，明確告訴學員「這格要自己填」

### 每頁版面節奏（對照 critique-guide.md 視覺層級）

- 封面（P1）：極簡留白 + 大 hero 標題（雜誌氣質）
- 資料密度中等（P2、P3、P11）：單欄大標題 + 三分區重點 + 註腳
- 資料密度高（P4、P5-7、P9、P10、P12）：多欄 grid + 表格
- 敘事為主（P8）：兩欄不對稱 layout + pull quote

### 匯 PPT 的 slide 定界

每頁用 `<section data-slide>` 包，CSS 設 `width: 1920px; height: 1080px; overflow: hidden;`。`html_to_pptx.mjs --selector "[data-slide]"` 會逐一截圖。

---

## 4. 資料狀態（🔴 / 🟡 / 🟢 清單）

對照 `junior-workflow.md` Step 1：

| 欄位 | 狀態 | 備註 |
|------|------|------|
| 公司名稱 | 🔴 未知 | 用 `[範例咖啡品牌]` 占位，學員替換 |
| 負責人 | 🔴 未知 | 用 `[負責人]` 占位 |
| 店址 | 🔴 未知 | 用 `[範例北部商圈]` / `[範例信義區店面]` 占位 |
| 單杯毛利 | 🔴 內部數據 | 用「60% → 48%」假設，明確標 🔴 請學員填真值 |
| 熟客流失率 | 🔴 內部數據 | 留空，提示「半年前熟客變少」是定性觀察 |
| 每月營收 | 🔴 內部數據 | 留空 |
| 台灣咖啡市場總產值 | 🟢 公開資料 | 2024 年 800 億元；[Food Next 2024](https://www.foodnext.net/column/columnist/paper/5357772897) |
| 台灣人均年飲杯數 | 🟢 公開資料 | 122-184 杯（ICO 2021 vs 2023 業界估算）；[數位時代 2024](https://www.bnext.com.tw/article/80737/coffee-convenience-store-strategy) |
| 咖啡館總數 | 🟢 公開資料 | 2022 年 4,096 家；1/4 在台北；[ETtoday 2023](https://finance.ettoday.net/news/2118947) |
| 星巴克門市 | 🟢 公開資料 | 2025 約 560 間；[Dailyview 2025](https://dailyview.tw/daily/4564) |
| 路易莎門市 | 🟢 公開資料 | 2025 約 560 間（含籌備中）；[Dailyview 2025](https://dailyview.tw/daily/4564) |
| cama 門市 | 🟢 公開資料 | 超過 100 間 |
| 興波定位 | 🟢 公開資料 | 2020 亞洲 50 大最佳咖啡廳第一名、吳則霖 WBC 冠軍；[Simple Kaffa 官網](https://simplekaffa.com/) |
| 阿拉比卡生豆 2024-2025 漲幅 | 🟢 公開資料 | 2024→2025 期貨漲 70%、較 2023 漲 80%；[公視新聞](https://news.pts.org.tw/article/728804) |
| 我方獨特優勢 | 🟡 推斷 | 依一般獨立咖啡店邏輯推斷三點；明確標「Claude 推斷，請老闆確認」 |

---

## 5. 需要使用者回饋的地方（明示給學員）

課程設計：學員看到這份 case-brief 後，會立刻知道要做的三件事：

1. **把占位符替換成自己公司的真實資料**（公司名、地點、競品調整）
2. **把 🔴 欄位填上內部數字**（毛利、熟客流失率、營收）
3. **選風格方向**：本案示範顧問版 + 雜誌氣質，學員可以要求換成社論版、日式極簡、或新創 Pitch

**如果學員是「咖啡店 + 烘焙工坊」的業態**，可以保留 80% 結構，只改 P4 競爭地圖（把烘焙業的同業加上去）、P6 路易莎 battlecard 改成烘焙豆廠競品。

**如果學員完全不是咖啡業**（例如做家具、牙科、補教），結構也通用：
- P4 競爭地圖換軸（價位 × 專業度 → 價位 × 服務深度）
- P5-7 Battlecard 換家（家具：IKEA + 宜得利 + 誠品生活；牙科：醫美連鎖 + 區域老診所 + 網路直銷；補教：連鎖品牌 + 地區強校 + 家教）
- P8 定位不用改 April Dunford 六段，只是填的內容變

這是 dogfooding 的核心訊息：**結構可通用，內容客製化**。

---

## 6. 對照兩個 skill 的職責分工

| 階段 | 用的 skill | 產出 |
|------|------------|------|
| 1. 市場規模、五層結構、競爭地圖軸線選定 | social-media → `pmm-market.md` | content-outline.md 的 P3、P4 |
| 2. 競品 battlecard 框架、objection、talk track | social-media → `pmm-competitive.md` | content-outline.md 的 P5、P6、P7 |
| 3. April Dunford 六段定位 | social-media → `pmm-positioning.md` | content-outline.md 的 P8 |
| 4. 訊息框架、通路版本、proof point | social-media → `pmm-messaging.md` | content-outline.md 的 P9 |
| 5. 台灣 LINE 行銷 / 數位通路策略 | social-media → `taiwan-market.md` | content-outline.md 的 P10 部分行動 |
| 6. 視覺風格決策、色票、字階、grid | sme-design → `design-philosophy.md` | 本文第 3 節 |
| 7. 反 AI slop 自檢 | sme-design → `anti-slop.md` | critique.md 的「細節執行」維度 |
| 8. 品牌資產處理（本案用備援路徑） | sme-design → `asset-protocol.md` | 本文第 3 節「🔴 無品牌資產」路徑 |
| 9. 6 步驟工作流 | sme-design → `junior-workflow.md` | 整份 deck 的產出順序 |
| 10. 5 維度評審 + 瞇眼測試 | sme-design → `critique-guide.md` | critique.md |

---

## 7. 預期 critique 自評（做完再對照）

對照 `critique-guide.md` 5 維度、場景「PMM 深度分析」（最重要：功能性、細節執行；次重要：視覺層級；可放寬：創新性）：

- **哲學一致性** 目標 8+：顧問版主結構不能跑掉。可能扣分：雜誌氣質混入過多、變成「顧問版皮、雜誌版骨」
- **視覺層級** 目標 8+：12 頁每頁一眼看得出重點。瞇眼測試要通過（瞇眼後看得到標題 + 關鍵數字）
- **細節執行** 目標 9+：這是顧問版的命根子，對齊、間距、字級必須精確；用 8pt grid（8/16/24/32/48/64）
- **功能性** 目標 9+：老闆要能照著 P10 行動清單執行、合夥人要能在 A4 上畫記
- **創新性** 可放寬到 6-7：本場景不需驚艷，只需「像顧問做的、可信」

**交付前必跑瞇眼測試**（對照 `critique-guide.md` 第二維度）：瞇眼看每一頁，視覺層級還在不在？
