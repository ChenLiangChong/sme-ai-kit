# Email Outreach（Email 觸及）
生命週期 Email 序列與冷開發（cold outreach）Campaign。

---

> **台灣市場適用指引**
> - 台灣中小企業的客戶溝通以 LINE 和電話為主，Email 行銷主要用於電子報和自動化流程
> - 冷開發信（cold email）在台灣商業文化中不常見且效果有限，建議改用 LINE/電話/社群私訊
> - B2B 場景可用 Email，但須搭配電話跟進；B2C 場景 LINE 推播效果遠優於 Email
> - 完整台灣市場數據見 [taiwan-market.md](taiwan-market.md)
> - LINE 行銷策略見 [line-marketing.md](line-marketing.md)

> **工具可用性**：本模組會嘗試呼叫 `query_knowledge`（屬 business-db MCP）載入既有品牌／行銷脈絡。若該工具不可用（例如第一堂課只裝了 Claude Desktop + social-media skill，尚未安裝 SME-AI-Kit），請直接向使用者詢問所需的品牌／行銷資訊，不要因工具缺失而停止。
>
> **最小問題清單（沒 MCP 時先問這些）：**
> - 您的公司／品牌是什麼？主要產品或服務？
> - 目標客戶是誰？（規模、行業、痛點）
> - 目前的行銷／定位狀況？有什麼既有資料可以參考？
> - 目標寄送名單從哪來？

---

## email-sequence


# Email 序列設計

本模組專注於 Email 行銷與自動化，目標是設計能養成關係、推動行動、並引導對方朝轉換前進的 Email 序列。

## 初步評估

**先檢查既有的品牌／行銷脈絡：**
在問問題之前，先用 `query_knowledge(category='brand')` 和 `query_knowledge(category='marketing')` 查詢既有脈絡。

建立序列前，先釐清：

1. **序列類型**
   - 歡迎／Onboarding 序列
   - 線索養成（Lead nurture）序列
   - 再互動（Re-engagement）序列
   - 購後序列
   - 事件觸發序列
   - 教育型序列
   - 銷售序列

2. **受眾脈絡**
   - 他們是誰？
   - 什麼觸發他們進入這個序列？
   - 他們已經知道／相信什麼？
   - 他們和您目前的關係是什麼？

3. **目標**
   - 主要轉換目標
   - 關係經營目標
   - 分群目標
   - 什麼叫做成功？


## 核心原則

1. **一封信只做一件事** — 一個 CTA（行動呼籲），一個目標
2. **開頭不說自己** — 先講對方的痛點或情境
3. **150 字以內** — 超過就砍，手機螢幕兩屏為上限
4. **Subject line（主旨）要具體** — 避免「合作邀約」「自我介紹」這類空泛標題
5. **每封信都要有退出機制** — CAN-SPAM／台灣個資法要求

## 輸出格式

### 序列總覽
```
序列名稱 (Sequence Name)：[序列名稱]
觸發條件 (Trigger)：[什麼觸發序列啟動]
目標 (Goal)：[主要轉換目標]
長度 (Length)：[幾封 Email]
節奏 (Timing)：[Email 之間的間隔]
退出條件 (Exit Conditions)：[退出序列的條件]
```

### 每封 Email
```
Email [#]：[名稱／目的]
寄送時機 (Send)：[寄送時機]
主旨 (Subject)：[主旨]
預覽文字 (Preview)：[預覽文字]
內文 (Body)：[完整內文]
CTA（Call to Action 行動呼籲）：[按鈕文字] → [連結目的地]
分群／條件 (Segment/Conditions)：[若適用]
```

### 指標計畫
要衡量什麼以及基準值


## 任務專屬提問

1. 什麼觸發進入這個序列？
2. 主要目標／轉換行動是什麼？
3. 對方對您已有多少認識？
4. 他們同時還收到什麼其他 Email？
5. 您目前 Email 的表現如何？


## 工具整合

主要 Email 工具：

| 工具 | 最適用途 |
|------|---------|
| **Customer.io** | 行為觸發型自動化 |
| **Mailchimp** | 中小企業 Email 行銷 |
| **Resend** | 開發者友善的交易型 Email |
| **SendGrid** | 大規模交易型 Email |
| **Kit** | 創作者／電子報導向 |


## Related Skills

- 見本檔案下方的 cold-email 區段 — 用於針對未 opt-in 的對象做對外開發（outbound prospecting）。不適合已表達興趣的溫線索或訂閱者。
- **copywriting.md** — 轉換文案、內容策略。當 Email 連到的到達頁需要文案優化時使用。不適合撰寫 Email 本身的文案。
- **pmm-launch.md** — 產品上市執行（已合併 launch-strategy）。當需要搭配特定產品上市設計 Email 序列時使用。不適合長青的 nurture 或 onboarding 序列。
- **analytics.md** — 行銷分析與追蹤（已合併 analytics-tracking + campaign-analytics）。設定 Email 點擊追蹤、UTM 參數和歸因時使用。不適合撰寫或設計序列本身。


## Communication（溝通原則）

Email 序列要以完整、可立即寄送的草稿交付——每封信都要附主旨、預覽文字、完整內文與 CTA。必須明列觸發條件與寄送時機。序列較長（5 封以上）時，先附序列總覽表再列個別 Email。若有某封 Email 可能與受眾收到的其他序列衝突，需標記出來。撰寫前先用 `query_knowledge(category='brand')` 和 `query_knowledge(category='marketing')` 取得品牌語氣、ICP（理想客戶輪廓）和產品脈絡。


## Proactive Triggers（主動觸發）

- **使用者提到試用轉付費率低** → 先詢問是否有試用到期前的 Email 序列，再建議產品內或定價調整。
- **使用者回報開信率高但點擊低** → 先診斷 Email 內文和 CTA 具體度，不要直接怪主旨。
- **使用者說要「做 Email 行銷」** → 先釐清序列類型（歡迎、養成、再互動等），再動手寫。
- **使用者有產品即將上市** → 建議把 Email 序列與站內訊息、到達頁文案協調一致，確保訊息一貫。
- **使用者提到名單冷掉** → 建議用漸進式 Offer 的再互動序列，不要急著花錢獲客。


## Output Artifacts（產出物）

| 使用者要什麼 | Claude 給什麼 |
|-------------|--------------|
| 序列架構文件 | 完整序列的觸發、目標、長度、時機、退出條件與分支邏輯 |
| 完整 Email 草稿 | 每封信的主旨、預覽文字、完整內文與 CTA |
| 指標基準 | 每種 Email 類型與序列目標對應的開信率、點擊率、轉換率目標 |
| 分群規則 | 受眾進入／退出條件、行為分支與排除名單 |
| 主旨變體 | 每封信 3 組主旨替代版本，用於 A/B 測試 |

---

## cold-email


# Cold Email Outreach（冷開發信）

本模組專注於 B2B 冷開發信，目標是幫忙撰寫、建構、迭代冷開發信序列——寫起來像一個有思考的人，而不是銷售機器，並且能真的收到回覆。

## 開工前

**先檢查既有的品牌／行銷脈絡：**
問問題之前，先用 `query_knowledge(category='brand')` 和 `query_knowledge(category='marketing')` 查詢既有脈絡。

收集以下脈絡：

### 1. 寄件者
- 對方在公司的角色與層級？（影響寫法）
- 賣什麼、誰買？
- 有沒有真實的客戶成果或 Proof Point（證據點）可引用？
- 是以個人身分還是公司身分寄信？

### 2. 潛在客戶
- 目標是誰？（職稱、公司類型、公司規模）
- 這個人可能有什麼問題是寄件者能解決的？
- 有沒有具體的觸發理由或原因現在聯絡？（融資、招聘、新聞、技術棧訊號）
- 有明確的名字和公司可以做個人化，還是這是給一個客群用的模板？

### 3. 訴求
- 第一封信的目標？（約電、收到回覆、拿到轉介？）
- 時間緊迫程度？（每日發送量大的 SDR 業務，還是創辦人做精準觸及）


## 本模組的運作模式

### Mode 1：寫第一封信
需要單一首次接觸信或給客群用的模板時。

1. 理解 ICP、問題、觸發訊號
2. 選對框架（AIDA（Attention-Interest-Desire-Action 注意—興趣—欲望—行動）／PAS（Problem-Agitate-Solve 問題—放大—解決）／BAB（Before-After-Bridge 現況—未來—橋樑）／4Ps（Promise-Picture-Proof-Push 承諾—圖像—證明—推動）——依情境選）
3. 草擬第一封：主旨、開頭、內文、CTA
4. 對照下面的原則審視——沒站得住腳的句子就砍
5. 交付：Email 文案 + 2-3 個主旨變體 + 結構選擇的簡要說明

### Mode 2：建立跟進序列
需要多封 Email 的序列時（通常 4-6 封）。

1. 從第一封信開始（Mode 1）
2. 規劃跟進角度——每封信都要不同的切入點，不是單純催促
3. 設定間隔節奏（Day 1、Day 4、Day 9、Day 16、Day 25）
4. 每封跟進都要有能獨立讀的鉤子，不預設對方讀過前面的信
5. 最後一封用 breakup email 專業收尾
6. 交付：完整序列、每封的間隔、主旨，以及每封信做什麼的說明

### Mode 3：從成效資料迭代
已經有序列在跑，想要優化時。

1. 檢視目前的序列信件與表現（開信率、回覆率）
2. 診斷：問題是在主旨（開信低）、內文（開了不回）還是 CTA（回了但結果不對）？
3. 改寫表現差的環節
4. 交付：修改後的信件 + 診斷 + 測試建議


## 核心寫作原則

### 1. 用同儕的口吻寫，不要像廠商

一旦您的信讀起來像行銷文案，就完了。想像您會怎麼寫信給另一家公司一個聰明的同事、想和他開啟一段對話。

**測試：**朋友會這樣寫給朋友談公事嗎？不會的話——重寫。

- ❌ "I'm reaching out because our platform helps companies like yours achieve unprecedented growth..."
  （中文註解：「我來信是因為我們的平台幫助像您這樣的公司達成前所未有的成長……」——典型的模板語，整句都沒意義）
- ✅ "Noticed you're scaling your SDR team — timing question: are you doing outbound email in-house or using an agency?"
  （中文註解：「注意到您在擴編 SDR 團隊——時機問題：outbound Email 是自己做還是委外？」——具體、相關、只問一個問題）

### 2. 每一句都要站得住腳

冷開發信不是適合講完整的場合。每一句都要做到下列其中一件：製造好奇、建立相關性、建立信任、引導到訴求。做不到就砍。

大聲念草稿。一聽到自己在碎念，立刻停下來砍掉。

### 3. 個人化必須連到問題

空泛的個人化比沒有更糟。「看到您讀 MIT」之後接一段推銷，和 MIT 完全沒關係——這是假的個人化。

真正的個人化：「看到您在招三位 SDR——通常是想擴大冷開發的訊號，這正是我們在解決的問題。」

個人化必須連到您聯絡對方的原因。

### 4. 先講對方的世界，不是您的

開頭要談對方——他們的情境、問題、脈絡。不是談您或您的產品。

- ❌ "We're a sales intelligence platform that..."
  （中文註解：「我們是一個業務情報平台……」——一開口就講自己）
- ✅ "Your recent TechCrunch piece mentioned you're entering the SMB market — that transition is notoriously hard to do with an enterprise-built playbook."
  （中文註解：「您最近在 TechCrunch 提到要進入 SMB 市場——用企業版的 playbook 做這個轉變是出名的難」——先講對方情境）

### 5. 一封信一個訴求

不要一次要對方約電、看 Demo、讀案例、又回覆時程。挑一個訴求。要求越多，任何一件都越不會發生。


## 依對象校準語氣

根據寫給誰，調整口吻、長度與具體度：

| 受眾 | 長度 | 口吻 | 主旨風格 | 有效做法 |
|------|-----|------|---------|---------|
| C-suite（CEO、CRO、CMO） | 3-4 句 | 極簡、同儕等級、策略性 | 短、模糊、像內部信 | 大問題 → 相關佐證 → 一個問題 |
| VP／Director | 5-7 句 | 直接、重視數據 | 稍微具體 | 具體觀察 + 明確商業角度 |
| Mid-level（Manager、Analyst） | 7-10 句 | 務實、看得出做過功課 | 可以較描述性 | 具體問題 + 實用價值 + 容易行動的 CTA |
| Technical（Engineer、Architect） | 7-10 句 | 精準、不囉嗦 | 技術具體性 | 精確問題 → 精確解法 → 低門檻訴求 |

越往組織上層走，信越要短。CEO 一天收 100+ 封 Email。三句話加一個明確問題是禮物，不是失禮。


## 主旨：反行銷風格

主旨的目標是讓信被打開——不是傳達價值、不是展現聰明、不是給人留下印象。就是被點開而已。

最好的冷開發信主旨看起來像內部信。短、略模糊、製造剛好足夠的好奇心讓人點開。

### 有效的模式

| 模式 | 範例 | 為什麼有效 |
|------|-----|-----------|
| 兩三個字 | `quick question`（快問一個問題） | 像真的同事寄來的信 |
| 具體觸發 + 問題 | `your TechCrunch piece`（您在 TechCrunch 的文章） | 具體到不像垃圾信 |
| 共同脈絡 | `re: Series B`（Re: B 輪融資） | 感覺像跟進，不像冷接觸 |
| 觀察 | `your ATS setup`（您的 ATS 設定） | 具體、相關、不推銷 |
| 轉介鉤子 | `[mutual name] suggested I reach out`（[共同認識的人] 建議我聯絡您） | 前置社群背書 |

### 扼殺開信率的做法

- 全大寫任何字
- 主旨放 emoji（爭議大，常被垃圾信過濾器攔）
- 假的 Re: 或 Fwd:（大家學到教訓了——會毀掉信任）
- 主旨是問句（例如 "Are you struggling with X?"）——像廣告
- 提到自己的公司名（"Acme Corp: helping you achieve..."）
- 像部落格標題的數字（"5 ways to improve your..."）


## 跟進策略

大部分的成交發生在跟進裡。大部分的跟進是沒用的。差別在於跟進有沒有增加價值，還是只是製造噪音。

### 節奏

| Email | 寄送日 | 間隔 |
|-------|-------|-----|
| Email 1 | Day 1 | — |
| Email 2 | Day 4 | +3 天 |
| Email 3 | Day 9 | +5 天 |
| Email 4 | Day 16 | +7 天 |
| Email 5 | Day 25 | +9 天 |
| Breakup | Day 35 | +10 天 |

間隔隨時間拉長。持續但不煩人。

### 跟進規則

**每封跟進都要有新角度。**輪流使用：
- 新證據（案例、數據、近期成果）
- 新問題切入角度（對方世界裡不同的痛點）
- 相關洞察（觀察到對方產業、技術棧或新聞的事）
- 直接提問（直接問——有時候清楚就能穿透）
- 反向訴求（找不到對方就請對方轉介給合適的人）

**永遠不要「just check in（隨便問一下）」。**「只是跟進看您有沒有看到我上封信」是浪費雙方時間。沒有新東西就不要寄。

**不要引用前面所有的信。**每封跟進都要能獨立讀懂。對方不記得您之前的信，不要讓他們捲回去找。

### Breakup Email（結束信）

序列最後一封要專業地收尾。它表示這是最後一封——反常識地會提升回覆率，因為人不喜歡懸而未決。

結束信範例：
> "I'll stop cluttering your inbox after this one. If [problem] ever becomes a priority, happy to reconnect — just reply here and I'll pick it up.
>
> If there's someone else at [Company] I should speak with, a name would go a long way.
>
> Either way — good luck with [whatever's relevant]."

（中文註解：「這封之後就不再打擾您的信箱了。如果 [問題] 變成優先事項，歡迎再聯絡——回這封信我就會接手。如果在 [公司] 我應該找別人談，給我一個名字會很有幫助。無論如何——祝您 [相關的事] 順利。」）

Follow-up 節奏建議：Day 3 → Day 7 → Day 14 → Day 28（最後一封），每封換角度（痛點、案例、社群背書、最後機會）。


## 要避免的做法

這些不是建議——是讓您被認定為「非人類」、扼殺回覆率的模式：

| ❌ 要避免 | 為什麼失敗 |
|----------|-----------|
| "I hope this email finds you well" | 立刻暴露這是模板。砍掉。 |
| "I wanted to reach out because..." | 三個字的延遲才進入正題 |
| 第一封信就 Feature dump（功能轟炸） | 還沒信任之前，沒人在意功能 |
| 有 Logo 和顏色的 HTML 模板 | 看起來像行銷，被垃圾信過濾 |
| 假的 Re:／Fwd: 主旨 | 感覺欺騙——第一個字前就毀掉信任 |
| "Just checking in" 的跟進 | 沒加價值，反而失去信譽 |
| 開頭寫 "My name is X and I work at Y" | 他們看得到您的名字，用有趣的東西開頭 |
| 社群背書和對方問題無關 | "We work with 500 companies" 沒有脈絡毫無意義 |
| 第一封就長篇案例 | 留到對方表現興趣後再寄 |
| 被動 CTA（"Let me know if you're interested"） | 弱。直接提問或提出具體下一步。 |


## 送達率基礎

一封好的信從被標記的網域寄出永遠進不了收件匣。基本配置必須到位：

- **專用寄送網域** — 不要用主網域寄冷開發信。用 `mail.yourdomain.com` 或 `outreach.yourdomain.com`。
- **SPF、DKIM、DMARC** — 三個都要設定並通過驗證。用 mail-tester.com 確認。
- **網域暖身（Domain warmup）** — 新網域需要 4-6 週暖身（從每日 20 封開始，逐步拉高）。
- **純文字 Email** — 或最簡化的 HTML。厚重 HTML 觸發垃圾信過濾。
- **退訂機制** — 法律要求（CAN-SPAM、GDPR）。附一個簡單的退訂連結。
- **寄送上限** — 網域信譽建立前，每日每網域控制在 100-200 封以下。
- **退信率（Bounce rate）** — 超過 5% 傷送達率。寄送前先驗證名單。

Domain warmup 排程：第 1 週 20 封/天 → 第 2 週 50 → 第 3 週 100 → 第 4 週起依 bounce rate 調整。SPF/DKIM/DMARC 三者缺一不可。


## Proactive Triggers（主動觸發）

不等使用者問就主動提出：

- **Email 以 "My name is" 或 "I'm reaching out because" 開頭** → 重寫開頭。這些是到場即死的開頭。標記出來並提供以對方世界為起點的替代版本。
- **第一封信超過 150 字** → 幾乎一定太長。標記字數並幫忙精簡。
- **只用名字做個人化** → 模板感會拉低回覆率。問有沒有可引用的觸發或訊號。
- **跟進寫 "just checking in" 或 "circling back"** → 無用跟進。問這次接觸可以帶什麼新角度或價值。
- **HTML Email 模板** → 建議改純文字。純文字送達率更高，也不像行銷轟炸。
- **第一封信的 CTA 要求 30-45 分鐘會議** → 對冷觸及門檻太高。建議低承諾訴求（15 分鐘通話，或先問一個問題測試興趣）。


## Output Artifacts（產出物）

| 使用者要什麼 | Claude 給什麼 |
|-------------|--------------|
| 寫一封冷開發信 | 首次接觸信 + 3 個主旨變體 + 結構選擇的簡要說明 |
| 建立一個序列 | 5-6 封序列，含每封的間隔、主旨、角度摘要 |
| 批改我的信 | 逐行評估 + 改寫 + 每處修改的原因 |
| 只寫跟進信 | 第 2-6 封跟進（每封角度不同）+ breakup email |
| 分析序列表現 | 診斷序列在哪裡壞掉（主旨／內文／CTA）+ 具體改寫建議 |


## Communication（溝通原則）

所有輸出遵守結構化溝通標準：
- **先結論**（Bottom line first）— 先給答案，再給解釋
- **What + Why + How** — 每個結論都要三者俱全
- **行動要有負責人與期限** — 不說「我們應該考慮」
- **信心標註** — 🟢 已驗證／🟡 中等信心／🔴 假設


## Do's and Don'ts

### Do
- 一封信只放一個 CTA——問越多、對方越不會做任何一件
- 控制在 150 字以內——手機螢幕兩屏是上限，超過就砍
- Subject line 要具體——像內部信件的標題（「quick question」「your TechCrunch piece」），不像廣告
- Follow-up 每封換角度——新證據、新痛點、產業洞察、直接提問、轉介紹，不要重複同一訊息
- 用純文字格式——plain text 的送達率和回覆率都高於 HTML 模板

### Don't
- 不要用 "I hope this email finds you well" 開頭——這是模板化的即死句，直接砍掉
- 不要 follow-up 只說 "Just checking in" 或 "Circling back"——沒有新價值的 follow-up 只會降低信任
- 不要第一封就做 feature dump——對方還不信任你，功能列表毫無意義，先建立相關性
- 不要用 HTML 模板（有 logo、顏色、排版）——看起來像行銷信，容易進垃圾信箱
- 不要第一封信就要求 30-45 分鐘會議——太高門檻，先問一個問題或約 15 分鐘聊聊

## 快速參考

### Cold Email 序列建立流程
1. 確認 ICP（目標受眾）+ 痛點 + 觸發信號（融資、招聘、新聞）
2. 寫第一封信：Subject line（像內部信）→ Opener（講對方的情境）→ Body（建立相關性）→ CTA（一個問題）
3. 規劃 follow-up 角度（每封不同）：Day 1 → Day 4 → Day 9 → Day 16 → Day 25 → Day 35（breakup）
4. 每封 follow-up 獨立成篇，不要假設對方讀過前面的信
5. 最後一封 breakup email 專業收尾 + 請對方轉介

### Email Sequence 設計流程
1. 確認序列類型（歡迎 Welcome／養成 Nurture／再互動 Re-engagement／購後 Post-purchase／銷售 Sales）
2. 定義觸發條件 + 主要轉換目標 + 退出條件
3. 規劃每封信：目的、寄送時間、主旨 (Subject line)、預覽文字 (Preview text)、內文 (Body)、CTA
4. 設定指標計畫 (Metrics Plan)：開信率 (open rate)、點擊率 (click rate)、轉換率 (conversion rate) 基準

### 成效診斷與優化
1. Open rate 低 → 問題在 Subject line → 測試更短、更像內部信件的標題
2. Open 高但 Click 低 → 問題在 Body / CTA → 檢查內文是否太長、CTA 是否模糊
3. Click 高但 Reply/Conversion 低 → 問題在 CTA 或 Landing page → 降低 CTA 門檻或優化到達頁
4. 整體送達率低 → 檢查 SPF/DKIM/DMARC、domain warmup、bounce rate

## Related Skills

- 見本檔案上方的 email-sequence 區段 — 用於對已訂閱用戶的生命週期與養成 Email。不適合冷開發——那是本區段。
- **copywriting.md** — 轉換文案、內容策略。用於行銷頁面文案和冷開發信跟進中引用的內容資產（案例、指南）。
- **pmm-positioning.md** — 定位開發。用於定位和 ICP 定義。如果不知道要打誰、為什麼打，冷開發不是用來想清楚這件事的工具。
