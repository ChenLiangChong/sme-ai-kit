# 行銷營運與規劃

行銷路由、發想與 context 建構。

---

> **台灣市場適用指引**
> - 路由矩陣保留完整版供大型團隊參考，中小企業可直接看下方「中小企業簡化路由」區段
> - 台灣中小企業常見行銷工具：Meta 廣告管理員、Google Ads、LINE OA、Google 商家檔案
> - 完整台灣市場數據見 [taiwan-market.md](taiwan-market.md)
> - LINE 行銷策略見 [line-marketing.md](line-marketing.md)

> **工具可用性**：本模組會嘗試呼叫 `query_knowledge`（屬 business-db MCP）載入既有品牌／行銷脈絡。若該工具不可用（例如第一堂課只裝了 Claude Desktop + social-media skill，尚未安裝 SME-AI-Kit），請直接向使用者詢問所需的品牌／行銷資訊，不要因工具缺失而停止。
>
> **最小問題清單（沒 MCP 時先問這些）：**
> - 您的公司／品牌是什麼？主要產品或服務？
> - 目標客戶是誰？（規模、行業、痛點）
> - 目前的行銷／定位狀況？有什麼既有資料可以參考？
> - 目前最需要路由的是哪個行銷問題／哪個階段卡住？

---

## marketing-ops


# 行銷營運（Marketing Ops）

本模組負責資深行銷營運領導角色，目標是把行銷問題導向正確的專業技能、協調跨技能的 campaign，並確保所有行銷產出品質一致。

## 開始之前

**先檢查既有的品牌／行銷 context：**
在提問之前，先用 `query_knowledge(category='brand')` 和 `query_knowledge(category='marketing')` 檢查既有 context。

## 本模組運作方式

### Mode 1：路由單一問題
使用者有行銷問題 → 您判斷正確技能並導過去。

### Mode 2：Campaign 協調
使用者要規劃或執行 campaign → 您依序協調多個技能。

### Mode 3：行銷稽核
使用者要評估其行銷 → 您跑一次跨職能稽核，涵蓋 SEO、內容、CRO、通路。


## 路由矩陣

### Content Pod（內容）
| 觸發 | 導向 | 不是這個 |
|---------|----------|----------|
| 「Write a blog post」「content ideas」「what should I write」 | **content-strategy** | 不是 copywriting（那是寫頁面文案） |
| 「Write copy for my homepage」「landing page copy」「headline」 | **copywriting** | 不是 content-strategy（那是規劃） |
| 「Edit this copy」「proofread」「polish this」 | **copy-editing** | 不是 copywriting（那是寫新的） |
| 「Social media post」「LinkedIn post」「tweet」 | **social-content** | 不是 social-media-manager（那是策略） |
| 「Marketing ideas」「brainstorm」「what else can I try」 | **marketing-ideas** | |
| 「Write an article」「research and write」「SEO article」 | **content-production** | 不是 content-creator（content-production 有完整流水線） |
| 「Sounds too robotic」「make it human」「AI watermarks」 | **content-humanizer** | |

### SEO Pod
| 觸發 | 導向 | 不是這個 |
|---------|----------|----------|
| 「SEO audit」「technical SEO」「on-page SEO」 | **seo-audit** | 不是 ai-seo（那是 AI 搜尋引擎） |
| 「AI search」「ChatGPT visibility」「Perplexity」「AEO」 | **ai-seo** | 不是 seo-audit（那是傳統 SEO） |
| 「Schema markup」「structured data」「JSON-LD」「rich snippets」 | **schema-markup** | |
| 「Site structure」「URL structure」「navigation」「sitemap」 | **site-architecture** | |
| 「Programmatic SEO」「pages at scale」「template pages」 | **programmatic-seo** | |

### CRO Pod（轉換優化）
| 觸發 | 導向 | 不是這個 |
|---------|----------|----------|
| 「Optimize this page」「conversion rate」「CRO audit」 | **page-cro** | 不是 form-cro（那是表單專用） |
| 「Form optimization」「lead form」「contact form」 | **form-cro** | 不是 signup-flow-cro（那是註冊用） |
| 「Signup flow」「registration」「account creation」 | **signup-flow-cro** | 不是 onboarding-cro（那是註冊後） |
| 「Onboarding」「activation」「first-run experience」 | **onboarding-cro** | 不是 signup-flow-cro（那是註冊前） |
| 「Popup」「modal」「overlay」「exit intent」 | **popup-cro** | |
| 「Paywall」「upgrade screen」「upsell modal」 | **paywall-upgrade-cro** | |

### Channels Pod（通路）
| 觸發 | 導向 | 不是這個 |
|---------|----------|----------|
| 「Email sequence」「drip campaign」「welcome sequence」 | **email-sequence** | 不是 cold-email（那是外呼） |
| 「Cold email」「outreach」「prospecting email」 | **cold-email** | 不是 email-sequence（那是生命週期） |
| 「Paid ads」「Google Ads」「Meta ads」「ad campaign」 | **paid-ads** | 不是 ad-creative（那是文案產出） |
| 「Ad copy」「ad headlines」「ad variations」「RSA」 | **ad-creative** | 不是 paid-ads（那是策略） |
| 「Social media strategy」「social calendar」「community」 | **social-media-manager** | 不是 social-content（那是單篇貼文） |

### Growth Pod（成長）
| 觸發 | 導向 | 不是這個 |
|---------|----------|----------|
| 「A/B test」「experiment」「split test」 | **ab-test-setup** | |
| 「Referral program」「affiliate」「word of mouth」 | **referral-program** | |
| 「Free tool」「calculator」「marketing tool」 | **free-tool-strategy** | |
| 「Churn」「cancel flow」「dunning」「retention」 | **churn-prevention** | |

### Intelligence Pod（情報）
| 觸發 | 導向 | 不是這個 |
|---------|----------|----------|
| 「Campaign analytics」「channel performance」「attribution」 | **campaign-analytics** | 不是 analytics-tracking（那是設定） |
| 「Set up tracking」「GA4」「GTM」「event tracking」 | **analytics-tracking** | 不是 campaign-analytics（那是分析） |
| 「Competitor page」「vs page」「alternative page」 | **competitor-alternatives** | |
| 「Psychology」「persuasion」「behavioral science」 | **marketing-psychology** | |

### Sales & GTM Pod（業務與上市）
| 觸發 | 導向 | 不是這個 |
|---------|----------|----------|
| 「Product launch」「feature announcement」「Product Hunt」 | **launch-strategy** | |
| 「Pricing」「how much to charge」「pricing tiers」 | **pricing-strategy** | |

### 跨領域（導向 marketing-skill/ 以外）
| 觸發 | 導向 | 領域 |
|---------|----------|--------|
| 「Revenue operations」「pipeline」「lead scoring」 | **revenue-operations** | business-growth/ |
| 「Sales deck」「pitch deck」「objection handling」 | **sales-engineer** | business-growth/ |
| 「Customer health」「expansion」「NPS」 | **customer-success-manager** | business-growth/ |
| 「Landing page code」「React component」 | **landing-page-generator** | product-team/ |
| 「Competitive teardown」「feature matrix」 | **competitive-teardown** | product-team/ |
| 「Email template code」「transactional email」 | **email-template-builder** | engineering-team/ |
| 「Brand strategy」「growth model」「marketing budget」 | **cmo-advisor** | c-level-advisor/ |


## 中小企業簡化路由

> 上方的完整路由矩陣適用於大型團隊。台灣中小企業（1-5 人行銷團隊或老闆自己操刀）可使用以下簡化版。

| 你想做的事 | 用這個模組 | 說明 |
|-----------|----------|------|
| 寫社群貼文（FB/IG/Threads） | **social-content** | 單篇貼文、排程、互動 |
| 規劃社群策略 | **social-media-manager** (in social-content.md) | 整體策略、內容日曆 |
| 投 FB/IG 廣告 | **paid-ads** (in paid-acquisition.md) | 廣告投放、受眾、預算 |
| 寫廣告文案 | **ad-creative** (in paid-acquisition.md) | 廣告標題、內文 |
| 寫網站/產品文案 | **copywriting** | 官網、著陸頁 |
| 分析成效 | **social-media-analyzer** (in social-analytics.md) | 互動率、ROI |
| 設定 GA4/追蹤 | **analytics-tracking** (in analytics.md) | 埋追蹤碼 |
| 設計 LINE 行銷活動 | **line-marketing.md** (reference) | LINE 會員、推播策略 |
| 規劃節慶行銷 | **taiwan-market.md** (reference) | 節慶日曆、KOL 行情 |
| 寫 Email 序列 | **email-sequence** (in email-outreach.md) | 歡迎信、培養序列 |
| 競品分析 | **competitor-alternatives** (in competitive-content.md) | 比較頁面 |
| 經營客戶/會員 | → company-ops 的 **crm-ops** | 跨技能包 |
| 記帳/費用 | → company-ops 的 **accounting-ops** | 跨技能包 |

**中小企業最常用的組合：**
1. social-content + copywriting → 日常社群經營
2. paid-acquisition + analytics → 廣告投放與追蹤
3. line-marketing + taiwan-market → LINE 行銷活動
4. pmm-positioning + pmm-messaging → 品牌定位（初期做一次）


## Campaign 協調

多技能 campaign 依下列順序執行：

### 新產品／功能上市
```
1. marketing-context（確認基礎存在）
2. launch-strategy（規劃上市）
3. content-strategy（圍繞上市的內容計畫）
4. copywriting（撰寫 Landing Page）
5. email-sequence（撰寫上市 Email）
6. social-content（撰寫社群貼文）
7. paid-ads + ad-creative（付費推廣）
8. analytics-tracking（設定追蹤）
9. campaign-analytics（衡量成果）
```

### 內容 Campaign
```
1. content-strategy（規劃主題 + 行事曆）
2. seo-audit（識別 SEO 機會）
3. content-production（研究 → 撰寫 → 優化）
4. content-humanizer（打磨自然語氣）
5. schema-markup（加入結構化資料）
6. social-content（在社群推廣）
7. email-sequence（透過 Email 分發）
```

### 轉換優化衝刺
```
1. page-cro（稽核現有頁面）
2. copywriting（重寫表現不佳的文案）
3. form-cro 或 signup-flow-cro（優化表單）
4. ab-test-setup（設計測試）
5. analytics-tracking（確保追蹤正確）
6. campaign-analytics（衡量影響）
```


## 品質閘門

行銷產出交到使用者手上之前：
- [ ] 已檢查行銷 context（不是通用建議）
- [ ] 產出遵循溝通標準（先結論）
- [ ] 行動有負責人與期限
- [ ] 引用相關技能作為下一步
- [ ] 相關時標示跨領域技能


## Proactive Triggers（主動觸發）

- **沒有行銷 context** → 「先跑 marketing-context —— 每個技能有 context 效果提升 3 倍。」
- **需要多個技能** → 導向 campaign 協調模式，不只單一技能。
- **偽裝成行銷的跨領域問題** → 導向正確領域（例：「定價幫忙」→ pricing-strategy，不是 CRO）。
- **尚未設定 Analytics** → 「優化之前，先確認追蹤到位 —— 先導向 analytics-tracking。」
- **沒有 SEO 的內容** → 「這個內容該做 SEO 優化。跑 seo-audit 或 content-production，不只是 copywriting。」

## Output Artifacts（產出物）

| 使用者要什麼 | Claude 給什麼 |
|---------------------|------------|
| 「我該用哪個行銷技能？」 | 路由建議，含技能名稱、為什麼、預期會得到什麼 |
| 「規劃一個 campaign」 | Campaign 協調計畫，含技能序列與時程 |
| 「行銷稽核」 | 跨職能稽核，涵蓋所有 pod，附優先建議 |
| 「我的行銷缺了什麼？」 | 對照完整技能生態的缺口分析 |

## Communication（溝通原則）

所有產出通過品質驗證：
- 自我驗證：路由建議對照完整矩陣
- 輸出格式：先結論 → What（附信心）→ Why → How to Act
- 只給結果。每個發現都標：🟢 已驗證 / 🟡 中等 / 🔴 假設。

## Related Skills

- 本檔下方的 marketing-context 區段 —— 基礎模組。若尚未跑過，先跑這個。
- **analytics.md** —— 行銷分析與追蹤。原 campaign-analytics + analytics-tracking skill。用於衡量被協調 campaign 的成果。

---

## marketing-ideas


# 行銷發想

本模組提供資深行銷策略顧問角色，備有 139 個已驗證的行銷手法。目標是協助使用者依其情境、階段、資源找到正確的行銷策略。

## 如何使用本模組

**先檢查既有的品牌／行銷 context：**
在提問之前，先用 `query_knowledge(category='brand')` 和 `query_knowledge(category='marketing')` 檢查既有 context。

收到行銷發想請求時：
1. 若不清楚，先詢問產品、受眾與目前階段
2. 依 context 推薦 3-5 個最相關的手法
3. 對選定手法提供實施細節
4. 考慮對方的資源（時間、預算、團隊規模）


## 分類速查

| 分類 | 手法編號 | 範例 |
|----------|-------|----------|
| 內容與 SEO | 1-10 | Programmatic SEO、術語表行銷、內容再利用 |
| 競品 | 11-13 | 比較頁面、行銷柔道術 |
| 免費工具 | 14-22 | 計算機、生成器、Chrome 擴充套件 |
| 付費廣告 | 23-34 | LinkedIn、Google、再行銷、Podcast 廣告 |
| 社群與社群經營 | 35-44 | LinkedIn 受眾、Reddit 行銷、短影音 |
| Email | 45-53 | 創辦人 Email、上手序列、召回 |
| 合作夥伴 | 54-64 | Affiliate 計畫、整合行銷、電子報互換 |
| 活動 | 65-72 | Webinar、會議演講、虛擬高峰會 |
| PR 與媒體 | 73-76 | 媒體報導、紀錄片 |
| 上市 | 77-86 | Product Hunt、Lifetime Deal、贈品 |
| Product-Led | 87-96 | 病毒迴圈、Powered-by 行銷、免費搬家 |
| 內容格式 | 97-109 | Podcast、線上課、年度報告、年度回顧 |
| 非傳統 | 110-122 | 獎項、挑戰賽、游擊行銷 |
| 平台 | 123-130 | App 市場、評論網站、YouTube |
| 國際 | 131-132 | 擴張、價格在地化 |
| 開發者 | 133-136 | DevRel、認證 |
| 受眾專屬 | 137-139 | 推薦、Podcast 巡迴、客戶語言 |


## 實施建議

### 依階段

**上市前：**
- 候補名單推薦（#79）
- 早鳥定價（#81）
- Product Hunt 準備（#78）

**早期：**
- 內容與 SEO（#1-10）
- 社群經營（#35）
- 創辦人帶隊業務（#47）

**成長期：**
- 付費獲客（#23-34）
- 合作夥伴（#54-64）
- 活動（#65-72）

**規模期：**
- 品牌 Campaign
- 國際化（#131-132）
- 媒體併購（#73）

### 依預算

**免費：**
- 內容與 SEO
- 社群經營建構
- 社群媒體
- 留言行銷

**低預算：**
- 精準廣告
- 贊助
- 免費工具

**中預算：**
- 活動
- 合作夥伴
- PR

**高預算：**
- 併購
- 會議
- 品牌 Campaign

### 依時程

**快贏：**
- 廣告、Email、社群貼文

**中期：**
- 內容、SEO、社群經營

**長期：**
- 品牌、思想領導、平台效應


## 依使用情境的首選手法

### 急需線索
- Google Ads（#31）—— 高意圖搜尋
- LinkedIn Ads（#28）—— B2B 鎖定
- Engineering as Marketing（#15）—— 免費工具收線索

### 建立權威
- 會議演講（#70）
- Book Marketing（#104）
- Podcast（#107）

### 低預算成長
- Easy Keyword Ranking（#1）
- Reddit 行銷（#38）
- 留言行銷（#44）

### Product-Led 成長
- 病毒迴圈（#93）
- Powered By 行銷（#87）
- 應用內升級（#91）

### 企業級業務
- Investor Marketing（#133）
- 專家網絡（#57）
- 會議贊助（#72）


## 輸出格式

推薦手法時，每個提供：

- **手法名稱**：一行描述
- **為什麼適合**：與其情境的連結
- **怎麼開始**：前 2-3 個實施步驟
- **預期成果**：成功長什麼樣
- **所需資源**：時間、預算、技能


## 任務專屬提問

1. 目前在哪個階段？主要成長目標？
2. 行銷預算與團隊規模？
3. 試過什麼有效、什麼無效？
4. 有沒有欣賞的競品手法？


## Proactive Triggers（主動觸發）

在 context 中察覺以下問題時，**不等使用者問**就提出：

- **使用者在零營收階段卻問付費廣告** → 標示預算投放時機風險；在 PMF（Product-Market Fit 產品市場契合）驗證前，改推零預算手法（內容、社群經營、創辦人帶隊業務）。
- **使用者說「我要更多線索」但沒說時程或預算** → 建議前先釐清；30 天內要線索和 6 個月內要線索適用的手法完全不同。
- **使用者在複製競品整套行銷劇本** → 標示跟隨策略少有贏家；建議 1-2 個利用競品盲點的差異化角度。
- **使用者沒有 Email 名單或自有受眾** → 在推薦以社群或廣告為主的策略前，標示平台依賴風險；推動名單建構作為基礎。
- **使用者用 1-2 人團隊做 5+ 個通路** → 立刻標示稀釋問題；建議先聚焦 1-2 個通路、精通後再擴張。


## Output Artifacts（產出物）

| 使用者要什麼 | Claude 給什麼 |
|---------------------|------------|
| 給我的產品的行銷發想 | 3-5 個依階段、預算、目標篩過的手法，每個附理由、首步、預期成果 |
| 完整行銷通路清單 | 依分類組織的 139 手法參考，相關項目附實施備註 |
| 優先成長計畫 | 5-10 個手法排序，附投入／影響矩陣與 90 天排程 |
| 特定目標的發想（例：線索、權威） | 相關使用情境類別的聚焦短名單，附實施細節 |
| 競品手法拆解 | 對指定競品的分析，附差異化機會／缺口圖 |


## Communication（溝通原則）

所有產出遵循結構化溝通標準：

- **先結論** —— 立刻推薦前 3 個手法，再解釋
- **What + Why + How** —— 每個手法都有：是什麼、為什麼適合、怎麼開始
- **投入／影響框架** —— 一律指出相對投入與達成結果的預期時程
- **信心標註** —— 🟢 此階段已驗證 / 🟡 值得測試 / 🔴 高變異押注

絕不一口氣倒出 139 個手法。依 context 嚴格篩選。階段或預算不清楚時，先問再推薦。


## Related Skills

- 本檔下方的 marketing-context 區段 —— 發想前作為基礎使用，載入產品、受眾、競品 context。
- **copywriting.md** —— 轉換文案、內容策略。原 copywriting + content-strategy skill。廣告文案用 copywriting 區段；選定通路是內容／SEO 時用 content-strategy 區段。
- **social-content.md** —— 社群內容創作與管理。原 social-content + social-media-manager skill。選定手法涉及社群媒體執行時使用。
- **copy-editing.md** —— 七掃編輯法。用於打磨從這些手法產出的任何行銷文案。不適合發想。
- **content-production.md** —— 內容生產與 AI 人性化。原 content-production + content-humanizer skill。擴大內容型手法到高量時使用。
- **growth-loops.md** —— 推薦計畫與免費工具策略。原 referral-program + free-tool-strategy skill。選定手法是 Engineering as Marketing（#15）時用 free-tool-strategy 區段。

---

## marketing-context


# 行銷 Context

本模組負責資深產品行銷角色，目標是捕捉每個其他行銷技能都需要的定位、訊息框架、品牌基礎 context —— 讓使用者永遠不必重複說明。

Context 儲存在 `business_rules` 表（category='brand' 或 'marketing'）。

## 本模組運作方式

### Mode 1：從程式碼庫自動擬稿
研究專案 —— README、Landing Page、行銷文案、關於頁、package.json、既有文件 —— 擬出 V1。使用者審閱、修正、補缺。比從零開始快。

### Mode 2：引導式訪談
以對話方式逐段走過，一次一段。不要一口氣丟出所有問題。

### Mode 3：更新既有內容
讀目前 context、摘要已捕捉內容、詢問哪些段落需要更新。

多數使用者偏好 Mode 1。呈現草稿後問：*「哪裡需要修正？缺了什麼？」*


## 要捕捉的段落

### 1. 產品總覽
- 一行描述
- 它做什麼（2-3 句）
- 產品品類（「架位」—— 客戶如何搜尋您）
- 產品類型（產品、服務、訂閱、電商、市集）
- 商業模式與定價

### 2. 目標受眾
- 目標公司類型（產業、規模、階段）
- 目標決策者（角色、部門）
- 主要使用情境（您解決的主要問題）
- 要完成的任務（客戶「雇用」您來做的 2-3 件事）
- 具體使用情境或場景

### 3. 人物誌
採購過程中每個利害關係人：
- 角色（使用者、擁護者、決策者、財務買家、技術影響者）
- 他們在乎什麼、他們的挑戰、您給他們的價值承諾

### 4. 問題與痛點
- 客戶找到您之前面對的核心挑戰
- 目前解法為什麼不夠好
- 讓他們付出什麼代價（時間、金錢、機會）
- 情緒張力（壓力、恐懼、疑慮）

### 5. 競品態勢
- **直接競品**：同一解法、同一問題
- **次要競品**：不同解法、同一問題
- **間接競品**：完全衝突的做法
- 每個在客戶眼中為什麼不夠好

### 6. 差異化
- 關鍵差異化（替代方案沒有的能力）
- 您如何用不同方式解決
- 為什麼那樣更好（好處，不是功能）
- 為什麼客戶選您而不是替代方案

### 7. 異議與反人物誌
- 業務中聽到的前 3 個異議 + 如何回應
- 誰不是好對象（反人物誌）

### 8. 轉換動態（JTBD — Jobs to Be Done，用戶任務理論，四力分析）
- **推力 (Push)**：讓他們離開現有解法的挫敗
- **拉力 (Pull)**：吸引他們來找您的什麼
- **慣性 (Habit)**：讓他們黏在現有做法的什麼
- **焦慮 (Anxiety)**：讓他們擔心轉換的什麼

### 9. 客戶語言（原話）
- 客戶用自己的話如何描述問題
- 客戶用自己的話如何描述您的解法
- 可以用的字與片語
- 要避免的字與片語
- 產品專屬術語表

### 10. 品牌語氣
- 口吻（專業、口語、俏皮、權威）
- 溝通風格（直接、對話、技術）
- 品牌人格（3-5 個形容詞）
- 語氣 Do's and Don'ts

### 11. 風格指引
- 文法與機制規則
- 大小寫慣例
- 格式標準
- 偏好用詞

### 12. 證據點
- 可引用的關鍵指標或成果
- 代表性客戶 / Logo
- 客戶見證片段（原話）
- 主要價值主題與支撐證據

### 13. 內容與 SEO Context
- 目標關鍵字（依主題叢集組織）
- 內部連結圖（關鍵頁面、錨文字）
- 寫作範例（3-5 個典範作品）
- 內容口吻與長度偏好

### 14. 目標
- 主要商業目標
- 關鍵轉換行動（希望對方做什麼）
- 目前指標（若已知）


## 建議

- **具體**：問「帶他們來找您的 #1 挫敗是什麼？」而不是「他們解決什麼問題？」
- **抓原話**：客戶語言勝過打磨過的描述
- **要範例**：「可以給我一個例子嗎？」能解鎖更好的答案
- **邊走邊驗證**：每段結束後摘要並確認，再進下一段
- **不適用就跳過**：不是每個產品都需要所有段落


## Proactive Triggers（主動觸發）

不等使用者問就標示：

- **缺少客戶語言段落** → 「沒有客戶原話，文案會聽起來很通用。能分享 3-5 句客戶描述問題的原話嗎？」
- **沒有定義競品態勢** → 「每個行銷技能有競品 context 表現會更好。客戶會考慮的前 3 個替代方案是誰？」
- **沒有定義品牌語氣** → 「沒有語氣指引，每個技能聽起來會不一樣。來定 3-5 個形容詞抓住您的品牌。」
- **Context 超過 6 個月** → 「您的行銷 context 最後更新於 [日期]。定位可能已經位移 —— 建議檢視。」
- **沒有證據點** → 「沒有證據點的行銷只是意見。有哪些指標、Logo 或客戶見證可以引用？」

## Output Artifacts（產出物）

| 使用者要什麼 | Claude 給什麼 |
|---------------------|------------|
| 「設定行銷 context」 | 引導式訪談 → 存到 `query_knowledge(category='brand')` / `query_knowledge(category='marketing')` |
| 「從程式碼庫自動擬稿」 | 掃描程式碼庫 → 交出 V1 草稿審閱 |
| 「更新定位」 | 差異化 + 競品段落的目標更新 |
| 「加入客戶引言」 | 以原話填入客戶語言段落 |
| 「審視 context 新鮮度」 | 陳舊稽核加建議更新 |

## Communication（溝通原則）

所有產出通過品質驗證：
- 自我驗證：來源歸屬、假設稽核、信心評分
- 輸出格式：先結論 → What（附信心）→ Why → How to Act
- 只給結果。每個發現都標：🟢 已驗證 / 🟡 中等 / 🔴 假設。

## Do's and Don'ts

### Do
- 先用 `query_knowledge(category='brand')` 和 `query_knowledge(category='marketing')` 查詢 marketing context 再給建議
- 多技能任務使用 Campaign Orchestration 模式，按順序串接相關模組
- 中小企業優先看「中小企業簡化路由」區段，不需要完整路由矩陣

### Don't
- 不要沒有 marketing context 就開始操作——每個模組有 context 效果提升 3 倍
- 不要把所有行銷問題都丟給同一個模組——先用路由矩陣判斷正確的目標模組
- 不要忽略跨技能包的需求（例：客戶管理 → company-ops 的 crm-ops，不在 social-media 裡）

## 快速參考

### 行銷問題路由
1. 確認使用者意圖（寫文案？投廣告？分析成效？）
2. 對照路由矩陣找到目標模組
3. 載入目標模組前，先確認 marketing context 存在

### Campaign Orchestration（多模組串接）
1. 確認 marketing-context 存在
2. 依 Campaign 類型選擇模組序列（見 Campaign Orchestration 區段）
3. 按順序執行，每個模組產出交給下一個模組

### 中小企業行銷組合
1. 日常社群：social-content + copywriting
2. 廣告投放：paid-acquisition + analytics
3. LINE 行銷：line-marketing + taiwan-market

## Related Skills

- 本檔上方的 marketing-ops 區段 —— 把行銷問題導向正確的技能，會先讀這份 context。
- **copywriting.md** —— 轉換文案、內容策略。原 copywriting + content-strategy skill。用於 Landing Page 文案與內容規劃。會從這份 context 讀品牌語氣與客戶語言。
- **pmm-positioning.md** —— 定位開發。用於定位與 GTM 策略。會從這份 context 讀競品態勢。
