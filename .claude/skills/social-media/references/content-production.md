# 內容生產與人性化

完整內容流水線與 AI 人性化。

---

> **台灣市場適用指引**
> - 內容生產原則為通用框架，適用於所有市場
> - 台灣繁體中文文案的特殊注意事項見 [copywriting.md](copywriting.md) 的「台灣中文文案注意事項」段落
> - 完整台灣市場數據見 [taiwan-market.md](taiwan-market.md)

> **工具可用性**：本模組會嘗試呼叫 `query_knowledge`（屬 business-db MCP）載入既有品牌／行銷脈絡。若該工具不可用（例如第一堂課只裝了 Claude Desktop + social-media skill，尚未安裝 SME-AI-Kit），請直接向使用者詢問所需的品牌／行銷資訊，不要因工具缺失而停止。
>
> **最小問題清單（沒 MCP 時先問這些）：**
> - 您的公司／品牌是什麼？主要產品或服務？
> - 目標客戶是誰？（規模、行業、痛點）
> - 目前的行銷／定位狀況？有什麼既有資料可以參考？
> - 這次要產出哪種內容、目標關鍵字／主題是什麼？

---

## content-production


# 內容生產

本模組負責內容生產，具備跨 B2B、服務業、零售、技術受眾的深度經驗。目標是把主題從零帶到完稿、可排名、可轉換、實際被讀的成品。

這是執行引擎，不是策略層。這裡是來「建」的，不是來「規劃」的。

## 開始之前

**先檢查既有的品牌／行銷 context：**
在提問之前，先用 `query_knowledge(category='brand')` 和 `query_knowledge(category='marketing')` 檢查既有 context。

一次蒐集以下 context（一口氣問完，不要一滴一滴問）：

### 您需要什麼
- **主題／暫定標題** —— 要寫什麼？
- **目標關鍵字** —— 主要搜尋詞（若 SEO 重要）
- **受眾** —— 誰會讀這篇？他們已經知道什麼？
- **目標** —— 傳遞資訊、轉換、建立權威、帶動試用？
- **大約篇幅** —— 800 字？2,000 字？長文？
- **既有內容** —— 有哪些內容這篇應該連結過去？

如果主題很含糊（「寫一篇關於 AI 的」），反推：「給我具體角度 —— 讀者是誰？他們要解決什麼問題？」

## 本模組運作方式

三種模式。從最適合的那個開始：

### Mode 1：Research & Brief（研究與內容 Brief）
有主題、還沒內容。先做研究、繪製競品態勢、定義角度，在動筆前先產出內容 Brief。

### Mode 2：Draft（撰稿）
已有 Brief（自行提供或來自 Mode 1）。寫出完整文章 —— 引言、主體、結論、各級標題 —— 依 Brief 的結構與瞄準參數撰寫。

### Mode 3：Optimize & Polish（優化與打磨）
已有初稿。跑完整優化：SEO 訊號、可讀性、結構稽核、meta tags、內部連結、品質閘門。輸出可發布版本。

可以依序跑完三階段，也可以直接跳到任一模式。


## Mode 1：Research & Brief

### Step 1 —— 競品內容分析

動筆前先理解已排名的內容。針對目標關鍵字：

1. 找出前 5-10 名內容
2. 盤點它們的角度：是列表文？教學文？評論文？比較文？
3. 找缺口：既有內容缺了什麼？哪個角度被低估？
4. 檢查搜尋意圖：搜尋者是要學習、比較、購買，還是解決某個具體問題？

**意圖訊號：**
| SERP 模式 | 意圖 | 寫什麼 |
|---|---|---|
| 「What is / How to」主導 | 資訊型 | 完整指南或解釋文 |
| 產品頁、評論 | 商業型 | 比較或買家指南 |
| 新聞、更新 | 導航／新聞型 | 跳過，除非有獨特角度 |
| 論壇結果（Reddit、Quora） | 探索型 | 有觀點、帶真實視角的文章 |

### Step 2 —— 來源蒐集

擬稿前先蒐集 3-5 個可信、可引用的來源。優先選：
- 原創研究（研究、調查、報告）
- 官方文件
- 可歸屬的專家引語
- 有具體數字的資料（不是含糊主張）

**規則：** 如果您引用不出具體數字，就不要做含糊的主張。「Studies show」是紅旗。去找到那份實際研究。

### Step 3 —— 產出內容 Brief

Brief 定義：
- 目標關鍵字 + 次要關鍵字
- 讀者輪廓與他要完成的任務
- 角度與獨特觀點
- 必要段落與 H2 結構
- 要證明的核心主張
- 要納入的內部連結
- 要打敗的競品內容


## Mode 2：Draft

已有 Brief，開始寫。

### 先畫大綱

填內文前先搭好標題骨架。好的大綱：
- H1 有鉤子（含關鍵字、帶出好奇）
- 4-7 個 H2 按邏輯推進
- H3 少用 —— 只在段落真的需要細分時才用
- 結尾導向 CTA

不要把大綱過度工程化。如果結構卡超過 5 分鐘，直接開始寫，之後再重組。

### Intro 原則

引言只有一個任務：讓讀者相信這篇會回答他的問題。3-4 句內達成。

可行公式：
1. 點出讀者的處境或問題
2. 指出這篇要對它做什麼
3. 可選：給對方相信您在這個主題上有份量的理由

**要避免的：**
- 以「In today's digital landscape...」開頭（每個人都這樣寫）
- 除非真的很犀利，不要以問句開頭
- 把重點埋在 3 句 context-setting 之後

### 逐段撰寫方式

每個 H2 段落：
1. 在第一句就講出主論點（不要留到最後）
2. 用範例、數據或比較佐證
3. 在轉到下一段之前加一個可行的 takeaway

讀者會掃讀。每個段落要能自己傳遞價值。

### 結論

三個元素：
1. 核心論點摘要（1-2 句）
2. 最重要的那一件下一步
3. CTA（若與目標相關）

不要灌水結論。寫完就是寫完。


## Mode 3：Optimize & Polish

已有初稿，按順序執行以下。

### SEO 優化 (SEO Pass)

- **Title tag**：含主要關鍵字、60 字以內、引發好奇
- **H1**：與 title tag 不同、關鍵字密度夠、讀起來自然
- **H2**：至少 2-3 個含次要關鍵字或相關語彙
- **第一段**：主要關鍵字出現在前 100 字內
- **圖片 alt text**：具描述性、自然情況下含關鍵字
- **URL slug**：短、關鍵字前置、不含停用詞

### 可讀性優化 (Readability Pass)

目標可讀性分數 70+。

手動檢查：
- 平均句長：目標 15-20 字，要有變化
- 任何段落都不超過 4 句（網頁讀者需要空氣）
- 不含未解釋的行話（對非專家受眾）
- 主動語態：找出被動結構並翻轉

### 結構稽核

- Intro 有兌現標題承諾嗎？
- 每個 H2 段落都值得存在嗎？（不值得就刪）
- 至少有 2 個範例或具體說明嗎？
- 結論感覺有被「賺來」嗎？

### 內部連結

至少加 2-4 條內部連結：
- 從現有高流量頁連到這篇
- 從這篇連到相關既有內容
- 錨文字要描述目的地，不要通用（「click here」沒意義）

### Meta 標籤 (Meta Tags)

撰寫：
- **Meta description**：150-160 字、含關鍵字、以行動或鉤子結尾
- **OG title / OG description**：可與 meta 不同，為社群分享優化
- **Canonical URL**：設定它，即使很明顯也要設

### 品質閘門 (Quality Gates) —— 沒通過不發

核心閘門：
- [ ] 主要關鍵字自然出現 3-5 次（不塞關鍵字）
- [ ] 每個事實主張都有來源，或明確標示為意見
- [ ] 至少一張圖、表格或視覺元素打破文字牆
- [ ] Intro 沒用陳腔濫調開頭
- [ ] 所有內部連結可用
- [ ] 可讀性分數 ≥ 70
- [ ] 字數在目標的 10% 誤差內


## Proactive Triggers（主動觸發）

不等使用者問就標示：

- **薄內容風險** —— 若目標關鍵字的競品都是 2,000+ 字、權威高的文章，600 字的文章排不上。在擬稿開始前先提出。
- **關鍵字蠶食** —— 若既有內容已瞄準這個關鍵字，標示出來。發第二篇只會稀釋權威，不會累積。
- **意圖不符** —— 若請求的角度與搜尋意圖不符（例：用品牌知名度文去搶交易型關鍵字），指出來。文章會帶來不會轉換的流量。
- **來源缺失** —— 若初稿出現「many companies」「studies show」沒有來源，每一處都在發稿前標示。
- **CTA／目標脫節** —— 若文章目標是「帶動試用註冊」但沒有 CTA、或 CTA 埋在第 12 段，標示出來。


## Output Artifacts（產出物）

| 使用者要什麼 | Claude 給什麼 |
|---|---|
| 研究與 Brief | 完整內容 Brief：關鍵字目標、受眾、角度、H2 結構、來源、競品缺口 |
| 完整初稿 | H1、H2、引言、主體、結論、行內來源標記齊全的文章 |
| SEO 優化 | 附 title tag、meta description、關鍵字放置稽核、OG 文案註記的草稿 |
| 可讀性稽核 | 可讀性評分器輸出 + 逐句編輯標記 |
| 發布檢核表 | 每一閘門過／不過的完成檢核表 |


## Communication（溝通原則）

所有產出遵循結構化溝通標準：
- **先結論** —— 先給答案再解釋
- **What + Why + How** —— 每個發現都包含三項
- **行動有負責人與期限** —— 不寫「我們或許應該...」
- **信心標註** —— 🟢 已驗證 / 🟡 中等 / 🔴 假設

審閱初稿時：指出問題 → 解釋影響 → 給具體修法。不是「改善可讀性」。應該說：「第 3 段平均每句 32 字。把第二句拆成兩句。」


## Related Skills

- **copywriting.md** —— 轉換文案、內容策略。原 copywriting + content-strategy skill。決定「要寫什麼」時用 content-strategy 區段；Landing Page、CTA、轉換文案用 copywriting 區段。不適合長篇內容（那是本模組負責的）。
- 本檔下方的 content-humanizer 區段 —— 擬稿後發現文章讀起來像機器人或 AI 時使用。在 SEO 優化之前先跑這個。

---

## content-humanizer


# 內容人性化

本模組負責真實寫作與品牌語氣，目標是把讀起來像機器生成（即便技術上真的是）的內容，轉化為聽起來像真人、有真觀點、有真經驗、有真切身利害的寫作。

這不是清潔服務。不是把「delve」刪掉就收工。是把語氣從地基重新蓋起來。

## 開始之前

**先檢查既有的品牌／行銷 context：**
在提問之前，先用 `query_knowledge(category='brand')` 和 `query_knowledge(category='marketing')` 檢查既有 context。

動手前蒐集所需：

### 您需要什麼
- **內容** —— 貼上要人性化的草稿
- **品牌語氣註記** —— 用 `query_knowledge(category='brand')` 檢查既有語氣指引；若沒有就問：「您的語氣是直接／口語／技術／玩世不恭？給我一個您喜歡的寫作範例。」
- **受眾** —— 誰會讀？（這會改變「人味」的長相）
- **目標** —— 這篇要做什麼？（知道目標就知道要多少個性）

若需要，只問一題：「重寫之前，給我一個您寫過或讀過、感覺對的範例。具體的比描述性的好。」

## 本模組運作方式

三種模式。可依序跑完以達成完整轉化，也可以跳到需要的那一個：

### Mode 1：Detect —— AI 模式分析
稽核內容中的 AI 痕跡。在修正之前先命名錯在哪、為什麼錯。這是診斷，不是編輯。

### Mode 2：Humanize —— 模式移除與節奏修正
刪掉 AI 模式。修正句子節奏。把通用換成具體。內容開始聽起來像人。

### Mode 3：Voice Injection —— 品牌人格
在通用被移除後，把品牌的特定人格注入進去。這裡是「人」變成「**您品牌的**人」的關鍵。

Context 足夠時一次跑完三階段。客戶需要先看稽核再編輯時則分開跑。


## Mode 1：Detect —— AI 模式分析

掃描以下類別。嚴重度評分：🔴 致命（毀信譽）/ 🟡 中等（削弱影響力）/ 🟢 輕微（只需打磨）。


### 核心 AI 痕跡類別

**1. 濫用的填充詞** 🔴
模型愛用某些字，因為訓練資料中頻率高。看到就標記：
- 「delve」「delve into」「delve deeper」
- 「landscape」（如「the current AI landscape」）
- 「crucial」「vital」「pivotal」
- 「leverage」（「use」就夠了的時候）
- 「furthermore」「moreover」「in addition」
- 「navigate」（隱喻用法：「navigate this challenge」）
- 「robust」「comprehensive」「holistic」
- 「foster」「facilitate」「ensure」

**2. 避險鏈** 🔴
AI 不停避險。避險是因為它不知道自己對不對。人偶爾避險 —— 但不是每句都避。
- 「It's important to note that...」
- 「It's worth mentioning that...」
- 「One might argue that...」
- 「In many cases」「In most scenarios」
- 「It goes without saying...」
- 「Needless to say...」

**3. 破折號過度使用** 🟡
一篇文章用一兩個 em-dash：可以。每隔一段就有一個：AI 指紋。模型用破折號像人在換氣一樣插入子句 —— 但它做得很強迫症。

**4. 段落結構千篇一律** 🔴
每段都是：主題句 → 解釋 → 範例 → 橋接到下一段。AI 非常一致。非常無聊。真實寫作有短段落、斷句、插話、離題，然後又切回來。結構是有變化的。

**5. 缺乏具體性** 🔴
AI 把具體主張換成含糊主張，因為具體主張可能錯。找：
- 「Many companies」→ 哪些公司？
- 「Studies show」→ 哪些研究？
- 「Significantly improved」→ 改善多少？
- 「Leading brands」→ 舉一個
- 「A lot of」→ 多少？

**6. 假確定性／假權威** 🟡
AI 對沒有人能確定的事自信斷言。「Companies that do X are more successful.」根據什麼？這不是謙遜 —— 是懶惰披上自信外衣。

**7. 「In conclusion」段落** 🟡
AI 的結論常常是引言的複製。「In this article, we explored X, Y, and Z. By implementing these strategies, you can achieve...」沒有人這樣結尾。真實的結尾要嘛加入新東西，要嘛把收尾句釘牢。


## Mode 2：Humanize —— 模式移除與節奏修正

找出問題後，系統化地修。

### 替換填充詞

**規則：** 永遠不要只刪 —— 一律替換成更好的。

| AI 片語 | 人類替代 |
|---|---|
| 「delve into」 | 「look at」「dig into」「break down」或直接：「here's what matters」 |
| 「the [X] landscape」 | 「how [X] works today」「the current state of [X]」 |
| 「leverage」 | 「use」「apply」「put to work」 |
| 「crucial」／「vital」 | 「the part that actually matters」「the one thing」，或者直接講那件事 —— 讓它自證其重要性 |
| 「furthermore」 | 什麼都不寫（直接開始下句），或「and」、或「also」 |
| 「robust」 | 具體化：「handles 10,000 requests/sec」「covers 47 edge cases」 |
| 「facilitate」 | 「help」「make easier」「allow」 |
| 「navigate this challenge」 | 「handle this」「deal with this」「get through this」 |

### 修正句子節奏

**問題：** AI 產出千篇一律的句長。每句 18-22 字。耳朵會麻。

**修法：** 刻意變化。朗讀出聲。然後：
- 把長句拆兩句
- 長句後接短句。就像這樣。
- 需要強調時用斷句。特別是強調用。
- 當一個念頭需要展開、讀者又有 context 能跟上時，讓某些句子可以放長

**讓人有人味的節奏模式：**
- 長。短。長、長。短。
- 問句？答。證據。
- 主張。具體範例。所以呢？

### 把通用換成具體

每個含糊主張都是在邀請懷疑。換掉：

**前：** 「Many companies have seen significant improvements by implementing this strategy.」

**後：** 「HubSpot published their onboarding funnel data in 2023 — companies that hit their first-value moment within 7 days showed 40% higher 90-day retention. That's not a rounding error.」

若沒有具體資料，誠實以告：「我沒看到這方面的對照研究，但在我做客戶上手流程的經驗中，模式一致：早啟用 = 高留存。」

個人經驗勝過含糊權威。每一次都是。

### 變化段落結構

打破一致的 SEEB 模式（主題句 Statement → 解釋 Explanation → 範例 Example → 橋接 Bridge）：

- **單句段落：** 用它。強調需要空氣。
- **問句段落：** 提一個問題。然後回答它。
- **中間插清單：** 有 3-5 個真正平行的項目時，丟一個快清單，然後回到散文。
- **插話／括號段落：** 一個顯露個性的小離題。（讀者其實喜歡這種。等同於一句中揚眉的動作。）
- **自白：** 「我第一次做錯了。」瞬間人味。

### 加入摩擦與不完美

AI 寫作太滑順、太完整。真人會：
- 在念頭中途換方向並承認：「Actually, let me back up...」
- 修飾不確定的東西，但不隱藏那份不確定
- 有可能錯的意見：「I might be wrong about this, but...」
- 注意到事情並說出來：「What's interesting here is...」
- 反應：「Which, if you've ever tried to debug this, you know is maddening.」


## Mode 3：Voice Injection —— 品牌人格

Humanizing 去掉 AI。Voice injection 讓它變成*您的*。

### 先讀語氣藍圖

用 `query_knowledge(category='brand')` 讀取品牌語氣段落與寫作範例。若沒有，要求一個該品牌喜歡的範例。一個就好。然後從中抽出模式。

**從語氣範例中要萃取的：**
- 句長偏好（短而有力 vs. 較長而流動？）
- 正式度（有縮寫？俚語？行話？）
- 幽默運用（冷幽默？自嘲？無？）
- 關係姿態（平輩？專家對學生？挑釁者？）
- 招牌片語或模式


### Voice Injection 技巧

**1. 個人軼事**
即使是品牌內容，在經驗中落地會更可信。「我們做 X 時親眼看過」勝過任何研究引用。

**2. 直接稱呼**
用「您」對讀者說話。不是「使用者」「團隊」「組織」。您。

**3. 不道歉的意見**
陳述您的立場。「我們認為業界在這件事上搞錯了」比「有不同觀點」更可信。選邊站。

**4. 插話**
一個簡短的括號式插話，顯示品牌知道的比說出來的多。「這也影響 API 效能，但那是另一個兔子洞。」

**5. 節奏簽名**
每個品牌都有自己的節奏。有的寫短促快打。有的寫長而迂迴、繞回來的句子。從範例中找到節奏並一致套用。

### 前／後範例

**前（AI 生成）：**
> It is crucial to leverage your existing customer data in order to effectively navigate the competitive landscape. Furthermore, by implementing a robust onboarding strategy, organizations can ensure that users achieve maximum value from the product and reduce churn significantly.

**後（人性化）：**
> Here's the thing nobody says out loud: most companies have the data to fix their churn problem. They just don't look at it until after customers leave.
>
> Your activation funnel is in there. Your best cohorts, your worst, the moment the drop-off happens. You don't need another tool — you need someone to stop ignoring what the tool is already showing you.
>
> Nail onboarding first. Everything else is downstream.

改了什麼：
- 移除：「crucial」「leverage」「navigate」「robust」「ensure」「significantly」「furthermore」
- 加入：直接稱呼、具體指控（「what the tool is already showing you」）、結尾短句重擊
- 改寫：被動建議 → 主動觀點


## Proactive Triggers（主動觸發）

不等使用者問就標示：

- **AI 指紋密度過高** —— 每 500 字有 10+ 個 AI 痕跡，修補沒用。標示這篇需要整篇重寫，不是編輯。試圖打磨一篇 80% 是 AI 模式的文章，結果只會是「用更好的字寫的 AI 模式」。
- **語氣 context 缺失** —— 若 `query_knowledge(category='brand')` 回空、使用者也沒提供，在注入語氣之前先暫停。要求一個範例。猜語氣猜錯會浪費大家時間。
- **具體度缺口** —— 若文章有 5+ 個含糊主張、零資料或歸屬，告知使用者。您能讓散文流暢，但沒辦法憑空造具體證據。要對方提供。
- **人性化後的語氣不符** —— 若文章現在真的有人味、但聽起來像不同品牌，標示出來。一致性跟品質一樣重要。
- **過度編輯風險** —— 若原稿中夾藏一兩段真的寫得好的內容在 AI 泥沼裡，在重寫前標示出來。不要不小心把好的部分弄丟。


## Output Artifacts（產出物）

| 使用者要什麼 | Claude 給什麼 |
|---|---|
| AI 稽核 | 每個 AI 模式都被標示、嚴重度評分、分類計數的標註版草稿 |
| 人性化草稿 | 完整改寫：AI 模式移除、節奏變化、具體度提升 |
| Voice injection | 套用品牌語氣後的標註版草稿 —— 具體改動被指出以利學習模式 |
| 前／後比較 | 關鍵段落並列，顯示改了什麼、為什麼改 |
| 人性分數 | 0-100 分數，依訊號類型分拆（AI 模式密度、節奏變化、具體度指數） |


## Communication（溝通原則）

所有產出遵循結構化標準：
- **先結論** —— 先給答案再解釋
- **What + Why + How** —— 每個發現都包含三項
- **行動有負責人與期限** —— 不寫「您或許想考慮...」
- **信心標註** —— 🟢 已驗證模式 / 🟡 中等 / 🔴 基於有限語氣 context 的假設

稽核時：命名模式 → 解釋為何讀起來像 AI → 給具體修法。不是「這聽起來像機器人」，而是「第 4 段以『It is important to note that』開頭 —— 這是純避險。刪掉。直接講那個 note。」


## Do's and Don'ts

### Do
- 先做研究再寫——依序走 Mode 1（Research & Brief）→ Mode 2（Draft）→ Mode 3（Optimize），不要跳過研究直接寫
- 每個事實主張都要有具體來源——「Studies show」是紅旗，找到實際的研究再引用
- 目標可讀性分數 ≥ 70——句子平均 15-20 字、段落不超過 4 句、主動語態優先
- Intro 在 3-4 句內讓讀者相信這篇文章會回答他的問題
- AI 生成的初稿一定要跑 content-humanizer，再進 SEO 優化

### Don't
- 不要用 "In today's digital landscape..." 之類的陳腔濫調開頭——每個人都這樣寫，直接講重點
- 不要事實主張沒有引用來源——「Many companies」「Studies show」「Significantly improved」都需要具體數字或出處
- 不要 AI 痕跡密度太高就試圖修補——每 500 字超過 10 個 AI 特徵，直接重寫比修補有效
- 不要在目標關鍵字已有現有內容時發新文——先檢查是否會造成 keyword cannibalization（關鍵字蠶食，多篇文章搶同一關鍵字反而稀釋排名）
- 不要交稿前跳過 Quality Gates checklist——關鍵字出現 3-5 次、每個事實有來源、可讀性 ≥ 70、intro 不是陳腔濫調

## 快速參考

### 從零到發布完整流程
1. **Research & Brief**：分析 Top 5-10 排名內容 → 找內容缺口 → 蒐集 3-5 個可引用來源 → 產出 Content Brief
2. **Draft**：建立 H2 骨架（4-7 個）→ 寫 Intro（痛點 → 本文做什麼 → 為什麼可信）→ 逐段寫（主論點 → 證據 → 行動建議）→ Conclusion（摘要 + 最重要的下一步 + CTA）
3. **Optimize & Polish**：SEO pass（title tag、H1、H2 關鍵字）→ Readability pass（句長、段落、主動語態）→ Structure audit → Internal links（2-4 條）→ Meta tags → Quality Gates checklist

### AI 內容人性化流程
1. **Detect**：掃描 AI 特徵（填充詞、避險鏈、破折號過度使用、段落結構單一、缺乏具體性）→ 標記嚴重度
2. **Humanize**：替換填充詞 → 修正句子節奏（長短交替）→ 用具體數據取代模糊說法 → 打破段落公式
3. **Voice Injection**：載入品牌語氣 → 注入個人軼事 / 直接稱呼 / 明確觀點 / 節奏簽名

### 內容 Brief (Content Brief) 結構
1. 目標關鍵字 + 次要關鍵字
2. 讀者輪廓 + 他要完成的任務（JTBD — Jobs to Be Done，用戶任務理論）
3. 獨特觀點角度 + 競爭對手缺口
4. 必要 H2 段落結構
5. 需要證明的核心主張 + 內部連結

## Related Skills

- 本檔上方的 content-production 區段 —— 用於產出初稿。擬稿後、SEO 優化前跑 content-humanizer。
- **copywriting.md** —— 轉換文案、內容策略。原 copywriting + content-strategy skill。轉換文案用 copywriting 區段；要決定寫什麼用 content-strategy 區段。不負責語氣或初稿執行。
