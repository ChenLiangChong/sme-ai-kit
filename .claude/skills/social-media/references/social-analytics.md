# 社群分析與成長

社群媒體分析、ROI 計算與 X/Twitter 成長策略。

---

> **台灣市場適用指引**
> - 台灣社群平台優先順序：LINE OA（必備）> FB > IG > YouTube > TikTok > Threads（新興），X/Twitter 在台灣使用率低，僅作參考
> - 台灣 Meta 廣告 CPC（Cost Per Click 每次點擊成本）基準：零售 NT$5-10、金融 NT$15-30，詳見 [taiwan-market.md](taiwan-market.md)
> - LINE 行銷成效指標見 [line-marketing.md](line-marketing.md)

> **工具可用性**：本模組會嘗試呼叫 `query_knowledge`（屬 business-db MCP）載入既有品牌／訊息脈絡。若該工具不可用（例如第一堂課只裝了 Claude Desktop + social-media skill），請直接向使用者詢問所需資訊，不要因工具缺失而停止。
>
> **最小問題清單（沒 MCP 時先問這些）：**
> - 您的公司／品牌是什麼？主要產品或服務？
> - 目標客戶是誰？（規模、行業、痛點）
> - 目前的行銷／定位狀況？有什麼既有資料可以參考？
> - 要分析哪個平台的哪段期間？關注的是觸及、互動還是轉換？

---

## social-media-analyzer


# 社群媒體分析器

Campaign 成效分析，包含互動指標、ROI 計算與平台基準比較。


## 目錄

- [分析流程](#分析流程)
- [互動指標](#互動指標)
- [ROI 計算](#roi-計算)
- [平台基準](#平台基準)
- [工具](#工具)
- [範例](#範例)


## 分析流程

分析社群媒體 campaign 成效：

1. 驗證輸入資料完整性（reach > 0、日期有效）
2. 計算每篇貼文的互動指標
3. 匯總 campaign 層級指標
4. 若提供廣告花費則計算 ROI
5. 與平台基準比較
6. 找出表現最佳與最差的貼文
7. 產出建議
8. **驗證：** 互動率 < 100%、ROI 與花費資料一致

### 輸入需求

| 欄位 | 必填 | 說明 |
|-------|----------|-------------|
| platform | 是 | instagram、facebook、twitter、linkedin、tiktok |
| posts[] | 是 | 貼文資料陣列 |
| posts[].likes | 是 | 按讚/反應數 |
| posts[].comments | 是 | 留言數 |
| posts[].reach | 是 | 觸及的不重複使用者數 |
| posts[].impressions | 否 | 總觀看次數 |
| posts[].shares | 否 | 分享/轉推數 |
| posts[].saves | 否 | 儲存/收藏數 |
| posts[].clicks | 否 | 連結點擊數 |
| total_spend | 否 | 廣告花費（用於 ROI 計算） |

### 資料驗證檢查

分析前請確認：

- [ ] 所有貼文的 reach > 0（避免除以零）
- [ ] 互動數非負
- [ ] 日期範圍有效（起始 < 結束）
- [ ] 平台已辨識
- [ ] 如需計算 ROI，花費 > 0


## 互動指標

### 互動率計算

```
互動率 (Engagement Rate) = (按讚 Likes + 留言 Comments + 分享 Shares + 儲存 Saves) / 觸及 Reach × 100
```

### 指標定義

| 指標 | 公式 | 解讀 |
|--------|---------|----------------|
| 互動率（Engagement Rate） | 互動數 / 觸及 × 100 | 受眾互動程度 |
| CTR（Click-Through Rate 點擊率） | Clicks / Impressions × 100 | 內容的點擊吸引力 |
| 觸及率（Reach Rate） | Reach / Followers × 100 | 內容擴散程度 |
| 病毒擴散率（Virality Rate） | Shares / Impressions × 100 | 內容值得被分享的程度 |
| 儲存率（Save Rate） | Saves / Reach × 100 | 內容實用價值 |

### 成效分級

| 評級 | 互動率 | 行動 |
|--------|-----------------|--------|
| 優異（Excellent） | > 6% | 放大並複製成功模式 |
| 良好（Good） | 3-6% | 優化並擴展 |
| 平均（Average） | 1-3% | 測試改善 |
| 待改善（Poor） | < 1% | 分析原因並轉向 |


## ROI 計算

計算廣告花費的回報：

1. 加總所有貼文的互動數
2. 計算每次互動成本（CPE）
3. 若有點擊資料，計算每次點擊成本（CPC）
4. 用基準費率估算互動價值
5. 計算 ROI 百分比
6. **驗證：** ROI =（價值 - 花費）/ 花費 × 100

### ROI 公式

| 指標 | 公式 |
|--------|---------|
| 每次互動成本（CPE） | 總花費 / 總互動數 |
| 每次點擊成本（CPC） | 總花費 / 總點擊數 |
| 每千次曝光成本（CPM，Cost Per Mille 每千次曝光成本） |（花費 / 曝光數）× 1000 |
| 廣告支出回報率（ROAS，Return On Ad Spend 廣告投報率） | 營收 / 廣告花費 |

### 互動價值估算

| 行為 | 價值 | 理由 |
|--------|-------|-----------|
| 按讚（Like） | $0.50 | 品牌知名度 |
| 留言（Comment） | $2.00 | 主動互動 |
| 分享（Share） | $5.00 | 擴散放大 |
| 儲存（Save） | $3.00 | 購買意圖訊號 |
| 點擊（Click） | $1.50 | 流量價值 |

### ROI 解讀

| ROI % | 評級 | 建議 |
|-------|--------|----------------|
| > 500% | 優異 | 大幅擴大預算 |
| 200-500% | 良好 | 適度增加預算 |
| 100-200% | 可接受 | 優化後再擴張 |
| 0-100% | 損益兩平 | 檢視受眾設定與素材 |
| < 0% | 負報酬 | 暫停並重新規劃 |


## 平台基準

### 各平台互動率

| 平台 | 平均 | 良好 | 優異 |
|----------|---------|------|-----------|
| Instagram | 1.22% | 3-6% | >6% |
| Facebook | 0.07% | 0.5-1% | >1% |
| Twitter/X | 0.05% | 0.1-0.5% | >0.5% |
| LinkedIn | 2.0% | 3-5% | >5% |
| TikTok | 5.96% | 8-15% | >15% |

### 各平台 CTR

| 平台 | 平均 | 良好 | 優異 |
|----------|---------|------|-----------|
| Instagram | 0.22% | 0.5-1% | >1% |
| Facebook | 0.90% | 1.5-2.5% | >2.5% |
| LinkedIn | 0.44% | 1-2% | >2% |
| TikTok | 0.30% | 0.5-1% | >1% |

### 各平台 CPC（全球）

| 平台 | 平均 | 良好 |
|----------|---------|------|
| Facebook | $0.97 | <$0.50 |
| Instagram | $1.20 | <$0.70 |
| LinkedIn | $5.26 | <$3.00 |
| TikTok | $1.00 | <$0.50 |

### 各平台 CPC（台灣，TWD）

| 平台 | 平均 | 備註 |
|----------|---------|-------|
| Facebook（零售/美妝） | NT$5-10 | 大眾品類 |
| Facebook（金融/高價值） | NT$15-30 | B2B、高單價服務 |
| Instagram | FB 的 1.5-1.7x | IG CPC 通常高 50-70% |
| CPM（Facebook） | NT$25-30 | 每千次曝光 |

台灣市場特定數據請參考 [taiwan-market.md](taiwan-market.md)。


## 工具

### 指標計算

計算每篇貼文與 campaign 總體的互動率、CTR、觸及率。

### 成效分析

產出完整成效分析，含 ROI、基準比較與建議。

**輸出包含：**
- Campaign 層級指標
- 逐篇貼文拆解
- 基準比較
- Top 表現貼文排名
- 可行動的建議


## 範例

### 輸入範例

```json
{
  "platform": "instagram",
  "total_spend": 500,
  "posts": [
    {
      "post_id": "post_001",
      "content_type": "image",
      "likes": 342,
      "comments": 28,
      "shares": 15,
      "saves": 45,
      "reach": 5200,
      "impressions": 8500,
      "clicks": 120
    }
  ]
}
```

### 輸出範例

```json
{
  "campaign_metrics": {
    "total_engagements": 1521,
    "avg_engagement_rate": 8.36,
    "ctr": 1.55
  },
  "roi_metrics": {
    "total_spend": 500.0,
    "cost_per_engagement": 0.33,
    "roi_percentage": 660.5
  },
  "insights": {
    "overall_health": "excellent",
    "benchmark_comparison": {
      "engagement_status": "excellent",
      "engagement_benchmark": "1.22%",
      "engagement_actual": "8.36%"
    }
  }
}
```

### 解讀

範例 campaign 顯示：
- **互動率 8.36%** vs 基準 1.22% = 優異（高於平均 6.8 倍）
- **CTR 1.55%** vs 基準 0.22% = 優異（高於平均 7 倍）
- **ROI 660%** = 對 $500 花費而言為卓越回報
- **建議：** 擴大預算，複製成功元素


## Platform Benchmarks（平台基準參考）

| 指標 | Facebook | Instagram | Threads |
|------|----------|-----------|---------|
| 互動率 (Engagement Rate) | 0.5-1.5% | 1-3% | 2-5%（新平台紅利） |
| 自然觸及 (Organic Reach) | 5-10% | 10-20% | 變動大 |
| 點擊率 (CTR, organic) | 1-2% | 0.5-1% | N/A |
| 最佳發文時間 | 週二～四 12-15 時 | 週一～五 11-13 時 | 晚間 19-22 時 |

台灣市場特定數據：見 [taiwan-market.md](taiwan-market.md)

## Proactive Triggers（主動觸發）

- **互動率低於平台平均** → 內容未引起共鳴。分析表現優異的貼文找出模式。
- **追蹤者成長停滯** → 內容擴散或發文頻率問題。檢視發文模式。
- **高曝光、低互動** → 有觸及但無共鳴，內容品質有問題。
- **競品表現明顯勝過您** → 有內容缺口，分析對方的熱門貼文。

## Output Artifacts（產出物）

| 使用者要什麼 | Claude 給什麼 |
|---------------------|------------|
| 「社群媒體稽核」 | 跨平台成效分析與基準比較 |
| 「哪些內容表現好」 | Top 表現內容分析，附模式與建議 |
| 「競品社群分析」 | 與競品的社群媒體對照，找出差距 |

## Communication（溝通原則）

所有輸出遵守品質驗證：
- 自我驗證：來源標註、假設稽核、信心評分
- 輸出格式：先結論 → What（附信心等級）→ Why → How to Act
- 只給結果。每項發現標註：🟢 已驗證 / 🟡 中等信心 / 🔴 假設待驗證

## Related Skills

- **social-content.md** — 社群內容創作與管理。適合用於創作社群貼文。若要分析成效，使用本模組。
- **analytics.md** — 行銷分析與追蹤。適合跨通路分析（含社群）。
- **copywriting.md** — 轉換文案與內容策略。content-strategy 區段用於規劃社群內容主題。
- **marketing-ops.md** — 行銷路由與上下文建構。提供受眾脈絡，讓分析更精準。

---

## x-twitter-growth


# X/Twitter 成長參考

> **台灣適用性說明：** X/Twitter 在台灣的使用率較低，非主流社群平台。本區段保留為參考，適用於有國際受眾或科技業客戶。台灣中小企業應優先經營 FB/IG/Threads/LINE。

X 平台專屬成長參考。跨平台的一般社群內容，見 `social-content.md`；社群策略與行事曆規劃，見 `social-content.md` 的 social-media-manager 區段。

## 何時使用本區段

| 需求 | 使用 |
|------|-----|
| X 專屬內容（tweet、thread） | **本區段** |
| 跨 FB + IG + Threads 規劃內容 | social-content.md |
| 分析互動指標 | 見本檔案上方的 social-media-analyzer 區段 |
| 建立整體社群策略 | social-content.md（social-media-manager 區段） |

## 個人檔案要點

- Bio 第一行就放清晰的價值主張
- 明確的利基、社群背書元素、CTA 或連結
- Bio 不放 hashtag
- 置頂 tweet：30 天內的新內容、強鉤子、明確 CTA

## 內容類型（依成長效益排序）

1. **Threads（推文串）** — 觸及與追蹤轉換最高。鉤子 <7 字、5-12 則推文、每則可獨立閱讀、結尾 CTA。
2. **單篇推文（Atomic Tweets）** — 觀察、列表、反直覺觀點。200 字以內、單一概念、內文不放連結。
3. **引用轉推（Quote Tweets）** — 加入數據、反論或個人經驗。絕不要只寫「This.」。
4. **回覆（Replies）** — 回覆比您大 2-10 倍的帳號，提供真正的價值。是最快取得曝光的路徑。

## 演算法速查（2025-2026）

| 訊號 | 權重 | 行動 |
|--------|--------|--------|
| 收到回覆 | 非常高 | 提問、辯論 |
| 閱讀停留時間 | 高 | 推文串、斷行 |
| 收藏（Bookmarks） | 高 | 列表、框架 |
| 轉推／引用 | 中 | 大膽觀點 |
| 按讚 | 低～中 | 有共鳴的內容 |
| 連結點擊 | 低（會被降權） | 連結放在回覆中 |

**觸及殺手：** 內文放連結、發文後 30 分鐘內編輯、超過 2 個 hashtag、標記無互動的帳號。

## 成長劇本摘要

- **第 1-2 週：** 個人檔案稽核、挑 20 個利基帳號互動、每日 2-3 則推文、每日 10-20 則回覆
- **第 3-4 週：** 加倍投入有效的格式、每日 3-5 則貼文、每週 2-3 個推文串
- **第 2 個月起：** 固定系列、跨平台再利用、互動社群

## Do's and Don'ts

### Do
- 分析前先驗證資料完整性——確認 reach > 0、日期有效、engagement 非負，避免除以零或無效結論
- 比較至少 3 種歸因模型（首次觸及、末次觸及、線性）再下結論，單一模型容易誤判
- 台灣市場以 FB/IG 為主要分析對象，X/Twitter 數據僅供國際受眾或科技業參考
- 用台灣本地 CPC 基準（FB 零售 NT$5-10、金融 NT$15-30）而非全球基準來評估成效
- 分析結論搭配具體行動建議——「engagement rate 低」要附上「測試新 hook / 換發文時間 / 增加互動」

### Don't
- 不要只看虛榮指標（追蹤者數、曝光數）——沒有互動的觸及毫無意義，優先看 engagement rate、CTR、save rate
- 不要用全球 CPC 基準直接套台灣市場——台灣 CPC 遠低於全球平均，錯用基準會誤判 ROI
- 不要在資料不足時就下結論——樣本太少（< 20 篇貼文）的趨勢分析沒有統計意義
- 不要把相關性當因果關係——「發文頻率高 + 互動高」不代表頻率是唯一原因

## 快速參考

### 社群成效分析流程
1. 驗證資料：reach > 0、日期有效、平台已辨識、spend > 0（若算 ROI）
2. 計算每篇貼文指標：engagement rate、CTR、reach rate、virality rate
3. 匯總 campaign 層級指標 + 與平台基準比較
4. 辨識 Top 3 / Bottom 3 貼文，找出成功模式（格式、hook、發文時間）
5. 產出行動建議：🟢 放大（excellent）/ 🟡 優化（average）/ 🔴 轉向（poor）

### ROI 計算流程
1. 加總所有互動數（likes + comments + shares + saves + clicks）
2. 計算 CPE（cost per engagement）= 總花費 / 總互動數
3. 計算 CPC = 總花費 / 總點擊數
4. 用互動估值（like $0.50 / comment $2 / share $5 / save $3 / click $1.50）估算價值
5. ROI% =（估算價值 - 花費）/ 花費 x 100

### 每週社群回顧
1. Top 3 表現貼文 → 為什麼成功？（格式、主題、時間）
2. Bottom 3 貼文 → 學到什麼？
3. 追蹤者成長趨勢（目標 > 5%/月）
4. Engagement rate 趨勢 vs 平台基準
5. 最佳發文時間（從數據中找）

## Related Skills

- **social-content.md** — 跨平台內容創作與整體社群策略。
- 見本檔案上方的 social-media-analyzer 區段 — 跨平台分析。
- **content-production.md** — 長內容產出，可作為推文串素材來源。
- **copywriting.md** — 主標與鉤子撰寫技巧。
