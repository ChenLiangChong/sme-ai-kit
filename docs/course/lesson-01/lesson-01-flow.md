# 第一堂直播課 · 合作者／老師執行方案

## 核心架構

**不是教學員手把手操作，而是讓 Claude Agent 自己跑、老師在旁邊解說 Claude 在做什麼。**

學員要做的事只有三件：
1. 打開 Claude Desktop / Claude Code
2. 貼一份 `lesson-01.md` 到 chat 按送出
3. 當 Claude 問公司資料時據實回答

其他全部由 Claude agent 自動：裝 skill、跑分析、產 PPT、最後給學員成品。

**老師的角色是「解說員」** —— Claude 走到哪個 step，老師就講那段的原理。30 分鐘內 Claude 做完、老師講完、學員帶一份 PPT 走。

## 方案總覽

| 項目 | 內容 |
|------|------|
| 定位 | Skool 年費社群第一堂入門課、30 分鐘 |
| 學員帶走的產出 | 一份 `.pptx` 行銷產業分析報告（12 頁、基於他自己公司資料） |
| 安裝的工具（由 Claude Agent 自動完成） | social-media skill + sme-design skill + Playwright/bun 依賴 |
| **不涵蓋** | SME-AI-Kit MCP（business-db、LINE、自動化）——下一堂主題 |
| 學員技術門檻 | 零。不需要會 git、不需要會 command line、不需要會任何技術 |

## 30 分鐘時間軸（**大致預期，非硬性**）

Claude agent 會自主決定怎麼分階段、每階段用什麼 label，**老師追著它打出的 `## ▶ {做什麼}` 標題走**，切到對應 talk track 段落講解。agent 跑得快老師就加速、跑得慢就多鋪陳。

以下時間軸是基於使用者 case 平均複雜度的估計，實際會浮動：

| 大致時段 | Claude 應該在做 | 老師對應 talk track |
|---------|---------------|-------------------|
| 0-3 min | （還沒啟動） | 開場 + 秀成品 + 教貼 md |
| 3-8 min | 裝 skill + Playwright（`## ▶ 我在裝 XX` 之類） | skill 概念、為什麼不是 ChatGPT |
| 8-11 min | 問學員公司資料（題數由 agent 自決） | 引導學員把答案講清楚 |
| 11-20 min | 跑行銷分析（子模組由 agent 自選） | April Dunford、PMM 工作流、反 AI slop |
| 20-25 min | 設計 + 產 PPT（頁數/風格由 agent 自選） | sme-design 設計哲學、6 種台灣風格、瞇眼測試 |
| 25-27 min | 交付 + 學員打開成品 | 老師點評 1-2 位學員 PPT |
| 27-30 min | Done | Q&A + 下集預告 |

**同步原則**：
- Claude 打出新的 `## ▶ XXX` 標題 = 老師切 talk track 的信號
- Claude 在跑命令 / 等 WebSearch / 等 LLM 思考時 = 老師講背後原理的空檔
- Claude 暫停問學員 = 老師停下 talk track，讓學員專心回答
- **不要搶 Claude 的話**——Claude 在跑時老師說完一個重點就停下讓學員看 Claude output，別連講三個重點

---

## 分段詳解（老師用 talk track 素材庫）

**重要**：以下不是「Claude 一定會走這 5 Step」，而是「老師依 Claude 實際 output 對應切換的 talk track 素材」。若 Claude 把某階段拆更細 / 合併 / 用不同名稱，老師依主題（裝工具 / 收資料 / 跑分析 / 做 PPT / 交付）挑對應段落講即可。

### 0-3 min ── 開場（老師獨講）

**目標**：讓學員知道今天會拿到什麼、怎麼開始。

**老師要做的**：
1. 歡迎 + 定位一句話
2. 秀成品（flash 咖啡店 PPT 的 1-2 頁給學員看——「這是 Claude 做的、今天你也會做一份」）
3. 打開 Skool 資源包下載 `lesson-01.md`（🔴 合作者決定怎麼分發）
4. 教學員打開自己的 Claude、把 md **全部內容**貼到 chat、按送出

**老師口白 outline**：
> 「各位好，30 分鐘後你會拿到**你自己公司**的完整行銷產業分析簡報——（秀咖啡店 PPT 1 秒）——這個等級、完全客製。
>
> 今天架構很簡單：有一份 `lesson-01.md` 已經把整堂課的指令寫進去了。你只要貼進 Claude、按送出，Claude 就會自己開始幫你做事。它會幫你裝工具、問你公司資料、跑分析、設計 PPT——**你全程只需要回答它的問題**。
>
> 我會在旁邊跟大家解說 Claude 每一步在幹嘛、為什麼要這樣做。這不只是一堂教你用工具的課，是一堂教你**理解 AI 顧問怎麼思考**的課。
>
> OK，大家 Skool 資源包下載 `lesson-01.md`、打開 Claude、整份貼進去、按送出。」

---

### 當 Claude 在裝工具階段（老師講 skill 概念）

**Claude 會做**：
- 跑 `pwd`、`ls .claude/skills/`
- 如需要，`git clone` sme-ai-kit repo 或用 `/plugin install` 裝 social-media + sme-design
- 跑 `bun install && bunx playwright install chromium`（~170MB 下載，2-4 分鐘）

**這段時間老師講什麼**：

**3-5 min · skill 概念**
- 「你看 Claude 正在下載工具。這個叫 skill——是一整套 AI 要用的『技能包』，不是 ChatGPT 那種你每次從零寫提示的玩法。」
- 「一個 skill 裡面有幾十個 reference 模組。social-media skill 有 22 個（市場分析、競品分析、定位、訊息、付費廣告、SEO 等）。你不用記哪個模組做什麼，Claude 會依你問題自動選。」
- 「這就是為什麼 Claude + skill 跟 ChatGPT 不一樣：ChatGPT 是通用對話、Claude + skill 是結構化顧問思考。」

**5-8 min · sme-design skill + 為什麼產 PPT 不是套模板**
- 「第二個工具 sme-design 是我們自己做的——它把 Claude 變成**資深視覺設計師**。它沒有模板、每份報告都依你公司從零設計。」
- 「一般 AI 做 PPT 會套模板——你看 ChatGPT 出的東西一眼就是紫漸變、emoji icon、爛大街 landing 樣。sme-design 內建了『反 AI slop』過濾器，做出來的不會讓客戶一眼看出是 AI。」
- 「看 Claude 現在在做什麼——它在下載一個叫 Playwright 的引擎，這是讓 HTML 變 PPT 的工具。170MB，下載要幾分鐘，這段時間我們繼續講。」

**關鍵提醒**：若 Claude Step 1 跑超過 5 分鐘（downloading 卡住），老師要：
- 不要讓氣氛冷掉——繼續講 skill vs. ChatGPT 對比、秀自己跑過的範例 markdown
- 網路問題的 fallback：讓學員會後重跑、這堂直播先用老師已跑好的結果示範
- 🔴 合作者應預先跑一遍、確認時間

---

### 當 Claude 問公司資料時（老師引導學員）

**Claude 會做**：
- 列出 6 題（品牌、產業、業務、客群、對手、煩惱）請學員一次回答
- 學員貼答案後 Claude 會複述理解、缺的標 🔴

**老師講什麼**：

- 「Claude 現在要問你公司的事——**6 個問題**。請把答案寫完整、一次貼給 Claude。**沒有的資料直接說『🔴 沒這個數字』** ——Claude 會標假設，後續你自己填。」
- 「**為什麼 Claude 要問這麼多？** 因為 skill 靠 context 吃飯。你給的 context 越豐富、它跑出來的分析越對你的 case。Garbage in, garbage out——你餵糞進去，它吐糞給你。」
- 「最後一題『目前最煩惱的事』是**最重要**的——這會決定分析的重點。你寫『不知道怎麼定位』跟『銷售掉 30%』跑出來會是完全不同方向的報告。」
- 引導慢的學員：「有困難就在 chat 裡打『不知道』、Claude 會用行業常態推測」

**預想狀況**：
- 有學員不會打字快 → 老師提醒「打不完沒關係、後續可以補充」
- 有學員資料很少 → 老師說「這堂課是示範、不是你公司的真實最終分析。能講多少講多少」
- 有學員不想公開公司名 → 可以用 `[我的公司]` 占位，Claude 會接受

---

### 當 Claude 跑行銷分析時（老師深度 talk track）

**Claude 會做**（約 9 分鐘）：
- 載入 social-media skill 的 `pmm-market.md` + `pmm-competitive.md` + `pmm-positioning.md` + `pmm-messaging.md`
- WebSearch 抓市場規模、競品公開資料
- 產出 `analysis.md`（完整繁中 markdown 分析）

**老師 talk track**（9 分鐘，依 Claude output 即興分配）：

**11-13 min · PMM 工作流為什麼這個順序**
- 「你看 Claude 先跑 market、再跑 competitive、再跑 positioning、最後 messaging——**這不是隨便排的**。」
- 「市場決定你在玩什麼遊戲、競品決定你對手是誰、定位決定你在這個地圖上是哪個點、訊息決定你怎麼告訴客戶這個點。」
- 「很多人跳到第 4 步就開始寫文案、結果文案聽起來像你家對手——因為你沒做前 3 步。」

**13-16 min · April Dunford 定位法**
- 「Claude 現在在跑 pmm-positioning——它會用 April Dunford 這個人的六段式方法。」
- 「April Dunford 是正面定位大師——她的書《Obviously Awesome》是 B2B SaaS 圈必讀。她把定位拆成 6 段：FOR（誰）、WHO（他們痛點）、THE（你是什麼品類）、IS A（在這品類你是什麼）、THAT（你的差異能力）、UNLIKE（比較對象）。」
- 「**這 6 段套到你公司**——你會發現原本模糊的『我們不太一樣』突然可以講清楚。」

**16-18 min · 反 AI slop 的第一層守護**
- 「Claude 跑分析時已經在過濾 AI slop。看它引用來源——每個數字標了 🟢🟡🔴、沒來源的不會假裝有來源。」
- 「ChatGPT 會跟你講『87% 的消費者表示...』這種編的。這個 skill 強制要求**不編數字**——沒資料就標 🔴、等你自己補。」
- 「這是為什麼這份分析可以直接拿去客戶會議——因為你知道哪些數字是真的、哪些是你要補的。」

**18-20 min · 看學員跑到哪**
- 邀請 1-2 位學員螢幕共享、看 Claude 產出的進度
- 老師即時解讀：「你看這裡，Claude 用 WebSearch 找到這家競品 2024 年開 X 家店，所以它可以寫……」
- 「大家看 Claude 現在跑完了 positioning、要進 messaging——再 2 分鐘就文字版分析完成。」

---

### 當 Claude 在設計並產 PPT 時（老師講設計哲學）

**Claude 會做**（約 5 分鐘）：
- 從 `references/design-philosophy.md` 選風格（預設：顧問諮詢所 + 雜誌氣質）
- 寫 12 頁 content outline
- 產 12 頁 HTML（單檔、`data-slide` 容器）
- 跑 critique（5 維度 + 瞇眼測試）
- 匯 PPT

**老師 talk track**：

**20-22 min · 設計哲學**
- 「你現在看 Claude 切到 sme-design skill——它是我們自己做的、把 Claude 變成資深視覺設計師。」
- 「sme-design 內建 6 種台灣風格的設計哲學：經濟日報社論版、雜誌特別報導版、顧問諮詢所、新創 Pitch、日式極簡、政府標案。每份報告依你的受眾挑 1 個主風格 + 1 個輔風格。」
- 「你的 PPT 給合夥人看 → 顧問諮詢所；給投資人看 → 新創 Pitch；給政府審查 → 政府標案。**同一份內容、不同受眾、不同設計**。」

**22-24 min · 反 AI slop 的第二層守護**
- 「你看 Claude 產出的 HTML——它不會用紫漸變、不會用 emoji icon、不會用爛大街的『Hero + 3 欄 features + CTA』landing 樣式。」
- 「因為 sme-design 的 anti-slop reference 有 8 條禁令。Claude 每次產出前都會對照檢查。」
- 「這就是『顧問級』跟『AI 感』的差別——不是錢的問題、是知不知道要避開什麼。」

**24-25 min · 看學員的 PPT 產出**
- Claude 完成後螢幕會出現 PPT 檔案路徑
- 提醒學員：「去看你的工作目錄、雙擊 `.pptx` 檔打開」

---

### 當 Claude 交付成品後（學員互看 + 老師點評）

**老師要做的**：
- 邀 1-2 位自願學員螢幕分享他們的 PPT
- **即時點評**：
  - 「你這個定位寫得好——清楚跟對手區隔開」
  - 「Value Prop 這句還可以再磨——太長不好記」
  - 「這頁有 🔴 的地方、回家記得把真實數字補上」
- **事先套招**（🔴 合作者決定）：找 2 位事前測試過、品質高的學員先分享，帶節奏

---

### 27-30 min ── Q&A + 下集預告

**預想 Q&A**：

| 學員可能問 | 老師標準回答 |
|-----------|-------------|
| 這個分析要怎麼存？ | PPT 檔複製到桌面 / Google Drive；Markdown 複製到 Notion |
| 我可以改嗎？ | 當然可以。打開 chat 跟 Claude 說「第 5 頁這段不對、改 XX」 |
| 跑第二次會一樣嗎？ | 不會，每次依 context 重新思考；大方向穩定但細節會精修 |
| 這份可以拿去提案客戶嗎？ | 可以，但先把 🔴 假設換成你真實數據 |
| 跟 ChatGPT 比哪個好？ | 不是比較、是不同工具。通用對話用 ChatGPT、結構化顧問分析用 Claude + skill |
| 那個 Playwright 下載好大 170MB 要等 | 只有第一次；第二堂你已經不用再下載了 |
| Claude 跑到一半錯誤怎辦？ | 在 chat 裡跟 Claude 說「你卡在 XX、從 Step X 繼續」——它會接回去 |
| 這套會不會很貴？ | 🔴 合作者決定定價說法——基本 Claude Pro 夠用 |

**下集預告 口白**：
> 「各位今天做到了什麼？你拿到了**你自己公司**的顧問級行銷分析簡報——12 頁、完整、可以直接拿去會議用。這份找顧問公司做要 5 萬 + 2 週、你今天 30 分鐘就有了。
>
> 下一堂會進到 **SME-AI-Kit MCP 工具組** ——這不只是個 skill、是整套 AI 營運助理。裝完之後：
> - Claude 可以接你的 LINE、客人問價它直接回
> - 可以自動記帳、自動查庫存、自動追進度
> - 可以每天產營運日報給你看
>
> 你今天拿到的是**顧問報告**；下一堂拿到的是**24 小時上班的 AI 員工**。
>
> 請把今天的 PPT 存好。下一堂再見。」

---

## 事前待合作者敲定

上直播前要決定：

1. **Lesson-01.md 怎麼分發給學員**：Skool 資源包、email 附件、還是網站下載頁？
2. **學員 Claude 方案**：建議 Free / Pro / Team？跑 30 分鐘可能 Free 方案會觸發限額——要事前提醒升級還是老師 cover？
3. **skill 安裝方式**：目前 `lesson-01.md` 第 Step 1 的 🔴 安裝指令待實測後補——需要合作者在課前跑一遍、敲定具體指令（marketplace？git clone？`/plugin`？）
4. **Skool 社群規模**：10 人 vs. 100 人 Q&A 節奏差很多；事前決定要不要限報名人數
5. **直播平台**：Zoom / YouTube Live / Skool 內建？要事前演練螢幕共享、學員互動機制
6. **失敗 Plan B**：若某學員 Claude 跑爆、網路卡、Playwright 裝不起來——課堂上快速 triage 的 SOP 要定
7. **事前套招**：25-27 min 要找 2 位品質高的學員先分享、帶節奏——事前要跟他們對過
8. **課後 follow-up**：24 小時內 Skool 發錄影、48 小時發問卷、7 天後預告第二堂

---

## 附件清單

- **附件 A**：`lesson-01.md` — 學員貼給 Claude 的 agent 指令（本資料夾內）
- **附件 B**：咖啡店範例 PPT — `.claude/skills/sme-design/examples/coffee-shop-demo/report.pptx`（開場秀成品 + 示範品質用）
- **附件 C**：咖啡店範例 markdown — `.claude/skills/sme-design/examples/coffee-shop-demo/content-outline.md`（14-16 min 老師可秀「文字版分析長這樣」）
- **附件 D**：預想 Q&A 速查表（見本檔 27-30 min 段落）

## 本方案核心判斷

- **30 分鐘夠不夠**：取決於 Claude Step 1 + Step 3 + Step 4 的總時間（預估 22 分鐘）+ 老師開場 + Q&A（8 分鐘）= 30 min。若 Playwright 下載慢要改 40 分鐘或事前讓學員先下載
- **為什麼用 agent 貼 md 而不是手把手教安裝**：非工程師的學員對 command line 完全沒概念；讓 Claude 自己跑命令、學員只負責「貼 md + 回答問題」是現有 Claude 能力下最合理的 UX
- **為什麼第一堂就要有 PPT 產出**：markdown 一般使用者看不懂；PPT 才是「我可以拿去用」的成品；wow moment 要從第一堂就給
- **為什麼不教 MCP**：MCP 需要 LINE token / ngrok / server configuration，**絕對**不是第一堂可以消化；留給第二堂當主菜 + 續費鉤子
- **第一堂成功標準**：30 分鐘結束時 ≥ 70% 學員手上有一份自己公司的 PPT + 覺得「AI 真的能幫我做大事」+ 想來下一堂
