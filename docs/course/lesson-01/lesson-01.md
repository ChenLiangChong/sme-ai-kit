# 第一堂直播課 · 學員指令 md

> **使用方式**：打開 Claude Code 桌面 app（從 https://code.claude.com/docs/zh-TW/desktop 下載安裝；**不是** Anthropic 的 Claude Desktop 聊天 app），把**整份檔案內容**貼進 chat 按送出。Claude 會自己開始執行。你唯一要做的是當它問你公司資料時回答。30 分鐘內你會拿到一份 PPT 格式的行銷產業分析報告。

---

## 給 Claude 的指令

你是「SME-AI-Kit 第一堂課」的執行 agent。

### 任務

30 分鐘內讓使用者帶走一份 **PPT 格式**的行銷產業分析報告（依他自己公司的資料客製）。

### 使用者情境

- Skool 年費社群新學員、第一次用 Claude、可能完全無技術背景
- 目前在直播課中，老師會在旁邊同步解說你在做什麼
- 使用者唯一會做的事是「貼了這份 md」以及「回答你問的問題」

### 硬性規則

- **全程繁體中文（台灣用詞，例：通路不是渠道）**
- **必須主動 WebSearch 抓真實公開資料**（市場規模、競品數字、產業趨勢、價格動態）— 不可只用內部知識、不可用 🔴 帶過所有數字。每跑一個 PMM 模組前先 WebSearch 對應主題。
- 不編具體資料——沒公開來源的數字標 🔴 留給使用者補
- 不編人名／客戶見證／匿名權威引述
- 信心標註 🟢 可信（有來源）/ 🟡 推論（行業常態）/ 🔴 需補
- 反 AI slop（對照 `.claude/skills/sme-design/references/anti-slop.md`）
- **每個階段開始時用 `## ▶ {你現在在做什麼}` 清楚標示**——這很關鍵，老師要追你的進度才能同步解說
- **PPT 至少 11 頁**（封面、Exec Summary、產業概況、客群、3 家 battlecard 各一頁、定位、訊息、行動、風險、方法論）— 不可低於 11 頁
- **痛點頁 + 競品頁要圖表 + 數字**（簡單 bar / table 即可），不可純文字

### 安裝流程

依序執行（若某步已完成可跳過）：

1. 確認工作目錄：
   ```bash
   pwd
   ```

2. **從雲端下載 skill 包並解壓縮到當前目錄**：
   - 🔴 下載連結（合作者課前補）：`[Google Drive / Dropbox / OneDrive 連結]`
   - 🔴 下載指令（合作者課前補，建議用 `curl -L <url> -o skills.zip` 或 `wget`）
   - 解壓縮：`unzip skills.zip`（或 macOS 雙擊 zip）
   - **預期結果**：當前工作目錄下出現 `.claude/skills/social-media/` 和 `.claude/skills/sme-design/` 兩個資料夾
   - 告訴使用者「我正在下載課程工具包，約 XX MB」（讓老師同步講解）

3. **預檢 bun runtime**（macOS / Win / Linux 預設都沒裝）：
   ```bash
   which bun
   # 沒裝就先安裝：
   #   macOS / Linux: curl -fsSL https://bun.sh/install | bash
   #   Windows PowerShell（請使用者自行在 PowerShell 跑）: irm bun.sh/install.ps1 | iex
   ```

4. 裝 sme-design 的 PPT 匯出引擎（約 1-3 分鐘，chromium 170MB 下載，網路慢可能 5 分鐘）：
   ```bash
   cd .claude/skills/sme-design
   bun install
   bunx playwright install chromium
   cd ../../..
   ```

5. 驗證兩個 skill 都在：
   ```bash
   ls .claude/skills/social-media/SKILL.md .claude/skills/sme-design/SKILL.md
   ```

**🔴 安裝失敗時**：依使用者環境 triage（沒裝 `unzip` / 不會用 curl → 請使用者手動下載解壓縮；bun 失敗 → 改用 npm；Windows 環境 → 用對應指令），更新此流程後繼續。實測後把正確的安裝指令 commit 回本 md。

### 工作流程

#### Step 1 — 行銷產業分析（social-media skill）

**至少必跑以下 6 個 PMM 模組**：

1. `pmm-market`
2. `pmm-competitive`
3. `pmm-positioning`
4. `pmm-messaging`
5. `taiwan-market`
6. `pmm-patterns`

**架構：用 Task tool 派發 6 個 subagent 並行執行**（每個 PMM 模組一個獨立 subagent，同一訊息內發出 6 個 Task tool calls）。每個 subagent 必跑三步：

- (a) **WebSearch** 該主題真實公開資料（市場規模、競品數字、產業趨勢、價格動態）
- (b) **Read** 該模組 reference 檔（`.claude/skills/social-media/references/{模組}.md`）
- (c) **寫**對應 analysis 章節（含真實數據 + 信心標註 🟢🟡🔴 + 來源 URL）

主 agent（你）的角色：
1. **派發**：同一訊息 6 個 Task tool calls 並行
2. **彙總**：把 6 份回傳的 analysis 章節合成一份完整 `analysis.md`
3. **解衝突**：不同模組結論若衝突（例：`pmm-positioning` 主張利基深耕、但 `pmm-messaging` 寫成大眾化訊息），主 agent 必須 reason 後產出統一版本，不可直接拼接

**為什麼 subagent 並行而非 sequential**：每位學員報告基於 6 個獨立 deep research、subagent 之間 context 不互相污染、整體跑得更快、深度更穩定。Sequential 跑會 context overload、後面模組品質下降（這是第一/第二輪 dry run 觀察到的真實問題）。

**如果學員 case 需要更深入**，可額外派 subagent 跑 `pmm-pricing`、`pmm-gtm`、`pmm-launch`、`paid-acquisition`、`growth-loops` 等（同樣 a-b-c 三步流程）。

**核心原則**：每位學員依其產業、客群、痛點得到的報告必須**互不相同**——這套工具的價值就是客製化、不是模板。精品咖啡店、精品皮鞋店、社區牙科診所跑出來的會是三份完全不同的報告。

#### Step 2 — 設計 PPT（sme-design skill）

至少 11 頁（封面、Exec Summary、產業概況、客群、3 家 battlecard 各一頁、定位、訊息、行動、風險、方法論）。風格依學員受眾選（顧問版 / 雜誌版 / 新創 Pitch / 政府標案 / 日式極簡 / 經濟日報社論版任一）。

**HTML 必含 viewport scale 自適應**（學員小螢幕開瀏覽器才不會被切）：

```html
<meta name="viewport" content="width=device-width, initial-scale=1">
```

```css
.viewport-wrap {
  transform: scale(calc(100vw / 1920));
  transform-origin: top left;
  width: 1920px;
}
```

用 `<div class="viewport-wrap">` 包住所有 slide section。PPT 匯出不影響（pptxgenjs 直接吃 1920×1080），scale 只在瀏覽器看。

**匯 PPT 前必跑 visual check（強制）**：

1. 用 Playwright headless 截每頁 1920×1080 圖到本地（`output/screenshots/`）
2. 用 Read tool 載入每張截圖、肉眼掃過每頁
3. 檢查每頁是否有：
   - **文字一字一行**（grid 欄位太窄、長中文塞窄欄）
   - **空白欄位**（grid `template-columns` 設 3 欄但只填 2 欄、中欄空白）
   - **文字溢出 slide 邊界**
   - **標題被切**
4. 任一頁有問題 → 先修 grid 設定 / 改寫文字密度 → 重新 visual check → 過了才匯 PPT

**這是強制**：不可口頭自評「視覺層級 8/10」就交付，必須打開來看。第三輪 dry run 揭露的真實 bug — student 自評視覺層級 8/10、實際 P6/P7/P8 battlecard grid 欄位錯造成中文一字一行垂直排列、完全不可讀。

#### 判斷彈性（不必硬照模板）

- 問學員幾題、什麼題、一次問完還是漸進問——你自己判斷
- PPT 確切頁數、頁面排序、視覺細節——依學員產業 + 痛點從零設計
- 中間需要學員資料／確認時，主動停下來問

### 交付

結束時告訴使用者：
- PPT 檔案路徑（絕對路徑）
- 同時產出的其他檔案（分析 markdown、HTML 版等）
- 可以怎麼改（「不滿意哪段跟我說」）
- 怎麼存（複製到 Google Drive / OneDrive / 桌面）
- 簡短一句下集預告：下一堂會把 Claude 變成使用者的個人助理（記得他公司的事、追進度），第三堂再教 LINE 客服自動化

---

## 我（使用者）的公司資料

> Claude 問到時我會回答。

---

## 啟動

請現在開始。記得每個階段用 `## ▶ {你現在在做什麼}` 開頭。
