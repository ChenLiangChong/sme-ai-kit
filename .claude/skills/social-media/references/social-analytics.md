# Social Analytics & Growth

Social media analytics, ROI calculation, and X/Twitter growth strategy.

---

> **台灣市場適用指引**
> - 台灣社群平台優先順序：LINE OA（必備）> FB > IG > YouTube > TikTok > Threads（新興），X/Twitter 在台灣使用率低，僅作參考
> - 台灣 Meta 廣告 CPC 基準：零售 NT$5-10、金融 NT$15-30，詳見 [taiwan-market.md](taiwan-market.md)
> - LINE 行銷成效指標見 [line-marketing.md](line-marketing.md)

## social-media-analyzer


# Social Media Analyzer

Campaign performance analysis with engagement metrics, ROI calculations, and platform benchmarks.


## Table of Contents

- [Analysis Workflow](#analysis-workflow)
- [Engagement Metrics](#engagement-metrics)
- [ROI Calculation](#roi-calculation)
- [Platform Benchmarks](#platform-benchmarks)
- [Tools](#tools)
- [Examples](#examples)


## Analysis Workflow

Analyze social media campaign performance:

1. Validate input data completeness (reach > 0, dates valid)
2. Calculate engagement metrics per post
3. Aggregate campaign-level metrics
4. Calculate ROI if ad spend provided
5. Compare against platform benchmarks
6. Identify top and bottom performers
7. Generate recommendations
8. **Validation:** Engagement rate < 100%, ROI matches spend data

### Input Requirements

| Field | Required | Description |
|-------|----------|-------------|
| platform | Yes | instagram, facebook, twitter, linkedin, tiktok |
| posts[] | Yes | Array of post data |
| posts[].likes | Yes | Like/reaction count |
| posts[].comments | Yes | Comment count |
| posts[].reach | Yes | Unique users reached |
| posts[].impressions | No | Total views |
| posts[].shares | No | Share/retweet count |
| posts[].saves | No | Save/bookmark count |
| posts[].clicks | No | Link clicks |
| total_spend | No | Ad spend (for ROI) |

### Data Validation Checks

Before analysis, verify:

- [ ] Reach > 0 for all posts (avoid division by zero)
- [ ] Engagement counts are non-negative
- [ ] Date range is valid (start < end)
- [ ] Platform is recognized
- [ ] Spend > 0 if ROI requested


## Engagement Metrics

### Engagement Rate Calculation

```
Engagement Rate = (Likes + Comments + Shares + Saves) / Reach × 100
```

### Metric Definitions

| Metric | Formula | Interpretation |
|--------|---------|----------------|
| Engagement Rate | Engagements / Reach × 100 | Audience interaction level |
| CTR | Clicks / Impressions × 100 | Content click appeal |
| Reach Rate | Reach / Followers × 100 | Content distribution |
| Virality Rate | Shares / Impressions × 100 | Share-worthiness |
| Save Rate | Saves / Reach × 100 | Content value |

### Performance Categories

| Rating | Engagement Rate | Action |
|--------|-----------------|--------|
| Excellent | > 6% | Scale and replicate |
| Good | 3-6% | Optimize and expand |
| Average | 1-3% | Test improvements |
| Poor | < 1% | Analyze and pivot |


## ROI Calculation

Calculate return on ad spend:

1. Sum total engagements across posts
2. Calculate cost per engagement (CPE)
3. Calculate cost per click (CPC) if clicks available
4. Estimate engagement value using benchmark rates
5. Calculate ROI percentage
6. **Validation:** ROI = (Value - Spend) / Spend × 100

### ROI Formulas

| Metric | Formula |
|--------|---------|
| Cost Per Engagement (CPE) | Total Spend / Total Engagements |
| Cost Per Click (CPC) | Total Spend / Total Clicks |
| Cost Per Thousand (CPM) | (Spend / Impressions) × 1000 |
| Return on Ad Spend (ROAS) | Revenue / Ad Spend |

### Engagement Value Estimates

| Action | Value | Rationale |
|--------|-------|-----------|
| Like | $0.50 | Brand awareness |
| Comment | $2.00 | Active engagement |
| Share | $5.00 | Amplification |
| Save | $3.00 | Intent signal |
| Click | $1.50 | Traffic value |

### ROI Interpretation

| ROI % | Rating | Recommendation |
|-------|--------|----------------|
| > 500% | Excellent | Scale budget significantly |
| 200-500% | Good | Increase budget moderately |
| 100-200% | Acceptable | Optimize before scaling |
| 0-100% | Break-even | Review targeting and creative |
| < 0% | Negative | Pause and restructure |


## Platform Benchmarks

### Engagement Rate by Platform

| Platform | Average | Good | Excellent |
|----------|---------|------|-----------|
| Instagram | 1.22% | 3-6% | >6% |
| Facebook | 0.07% | 0.5-1% | >1% |
| Twitter/X | 0.05% | 0.1-0.5% | >0.5% |
| LinkedIn | 2.0% | 3-5% | >5% |
| TikTok | 5.96% | 8-15% | >15% |

### CTR by Platform

| Platform | Average | Good | Excellent |
|----------|---------|------|-----------|
| Instagram | 0.22% | 0.5-1% | >1% |
| Facebook | 0.90% | 1.5-2.5% | >2.5% |
| LinkedIn | 0.44% | 1-2% | >2% |
| TikTok | 0.30% | 0.5-1% | >1% |

### CPC by Platform (Global)

| Platform | Average | Good |
|----------|---------|------|
| Facebook | $0.97 | <$0.50 |
| Instagram | $1.20 | <$0.70 |
| LinkedIn | $5.26 | <$3.00 |
| TikTok | $1.00 | <$0.50 |

### CPC by Platform (Taiwan, TWD)

| Platform | Average | Notes |
|----------|---------|-------|
| Facebook (零售/美妝) | NT$5-10 | 大眾品類 |
| Facebook (金融/高價值) | NT$15-30 | B2B、高單價服務 |
| Instagram | FB 的 1.5-1.7x | IG CPC 通常高 50-70% |
| CPM (Facebook) | NT$25-30 | 每千次曝光 |

台灣市場特定數據請參考 [taiwan-market.md](taiwan-market.md)。


## Tools

### Calculate Metrics

Calculates engagement rate, CTR, reach rate for each post and campaign totals.

### Analyze Performance

Generates full performance analysis with ROI, benchmarks, and recommendations.

**Output includes:**
- Campaign-level metrics
- Post-by-post breakdown
- Benchmark comparisons
- Top performers ranked
- Actionable recommendations


## Examples

### Sample Input

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

### Sample Output

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

### Interpretation

The sample campaign shows:
- **Engagement rate 8.36%** vs 1.22% benchmark = Excellent (6.8x above average)
- **CTR 1.55%** vs 0.22% benchmark = Excellent (7x above average)
- **ROI 660%** = Outstanding return on $500 spend
- **Recommendation:** Scale budget, replicate successful elements


## Platform Benchmarks（參考基準）

| 指標 | Facebook | Instagram | Threads |
|------|----------|-----------|---------|
| Engagement Rate | 0.5-1.5% | 1-3% | 2-5%（新平台紅利） |
| Organic Reach | 5-10% | 10-20% | 變動大 |
| CTR (organic) | 1-2% | 0.5-1% | N/A |
| 最佳發文時間 | 週二～四 12-15 時 | 週一～五 11-13 時 | 晚間 19-22 時 |

台灣市場特定數據：見 [taiwan-market.md](taiwan-market.md)

## Proactive Triggers

- **Engagement rate below platform average** → Content isn't resonating. Analyze top performers for patterns.
- **Follower growth stalled** → Content distribution or frequency issue. Audit posting patterns.
- **High impressions, low engagement** → Reach without resonance. Content quality issue.
- **Competitor outperforming significantly** → Content gap. Analyze their successful posts.

## Output Artifacts

| When you ask for... | You get... |
|---------------------|------------|
| "Social media audit" | Performance analysis across platforms with benchmarks |
| "What's performing?" | Top content analysis with patterns and recommendations |
| "Competitor social analysis" | Competitive social media comparison with gaps |

## Communication

All output passes quality verification:
- Self-verify: source attribution, assumption audit, confidence scoring
- Output format: Bottom Line → What (with confidence) → Why → How to Act
- Results only. Every finding tagged: 🟢 verified, 🟡 medium, 🔴 assumed.

## Related Skills

- **social-content.md** — 社群內容創作與管理。原 social-content + social-media-manager skill。For creating social posts. Use this skill for analyzing performance.
- **analytics.md** — 行銷分析與追蹤。原 campaign-analytics + analytics-tracking skill。For cross-channel analytics including social.
- **copywriting.md** — 轉換文案、內容策略。原 copywriting + content-strategy skill。content-strategy 區段 for planning social content themes.
- **marketing-ops.md** — 行銷路由與上下文建構。原 marketing-context + marketing-ideas + marketing-ops skill。Provides audience context for better analysis.

---

## x-twitter-growth


# X/Twitter Growth Reference

> **台灣適用性說明：** X/Twitter 在台灣的使用率較低，非主流社群平台。本區段保留為參考，適用於有國際受眾或科技業客戶。台灣中小企業應優先經營 FB/IG/Threads/LINE。

X-specific growth reference. For general social media content across platforms, see `social-content.md`. For social strategy and calendar planning, see the social-media-manager section in `social-content.md`.

## When to Use This

| Need | Use |
|------|-----|
| X-specific content (tweet, thread) | **This section** |
| Plan content across FB + IG + Threads | social-content.md |
| Analyze engagement metrics | 見本檔案上方的 social-media-analyzer 區段 |
| Build overall social strategy | social-content.md (social-media-manager 區段) |

## Profile Essentials

- Clear value proposition in bio first line
- Specific niche, social proof element, CTA or link
- No hashtags in bio
- Pinned tweet: less than 30 days old, strong hook, clear CTA

## Content Types (by growth impact)

1. **Threads** — Highest reach and follow conversion. Hook in <7 words, 5-12 tweets, each standalone-worthy, end with CTA.
2. **Atomic Tweets** — Observations, listicles, contrarian takes. Under 200 chars, one idea, no links in body.
3. **Quote Tweets** — Add data, counterpoint, or experience. Never just "This."
4. **Replies** — Reply to accounts 2-10x your size with genuine value. Fastest path to visibility.

## Algorithm Quick Reference (2025-2026)

| Signal | Weight | Action |
|--------|--------|--------|
| Replies received | Very high | Questions, debates |
| Time spent reading | High | Threads, line breaks |
| Bookmarks | High | Lists, frameworks |
| Retweets/Quotes | Medium | Bold takes |
| Likes | Low-medium | Relatable content |
| Link clicks | Low (penalized) | Links in reply only |

**Reach killers:** Links in tweet body, editing within 30 min, >2 hashtags, tagging non-engagers.

## Growth Playbook Summary

- **Week 1-2:** Profile audit, 20 niche accounts to engage with, 2-3 tweets/day, 10-20 replies/day
- **Week 3-4:** Double down on winning formats, 3-5 posts/day, 2-3 threads/week
- **Month 2+:** Recurring series, cross-platform repurposing, mutual engagement groups

## Related Skills

- **social-content.md** — Multi-platform content creation and overall social strategy.
- 見本檔案上方的 social-media-analyzer 區段 — Cross-platform analytics.
- **content-production.md** — Long-form content that feeds threads.
- **copywriting.md** — Headline and hook writing techniques.
