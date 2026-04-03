# PMM Gate 1: Market Analysis

TAM/SAM/SOM, segmentation, trends, ICP definition, and international market entry.

---

## ICP Definition Workflow

Define ideal customer profile for targeting:

1. Analyze existing customers (top 20% by LTV)
2. Identify common firmographics (size, industry, revenue)
3. Map technographics (tools, maturity, integrations)
4. Document psychographics (pain level, motivation, risk tolerance)
5. Define 3-5 buyer personas (economic, technical, user)
6. Validate against sales cycle and churn data
7. Score prospects A/B/C/D based on ICP fit
8. **Validation:** A-fit customers have lowest churn and fastest close

### Firmographics Template

| Dimension | Target Range | Rationale |
|-----------|--------------|-----------|
| Employees | 50-5000 | Series A sweet spot |
| Revenue | $5M-$500M | Budget available |
| Industry | [Your industry] | Product fit |
| Geography | US, UK, DACH | Market priority |
| Funding | Seed to Growth | Willing to adopt |

### Buyer Personas

| Persona | Title | Goals | Messaging |
|---------|-------|-------|-----------|
| Economic Buyer | VP, Director, Head of [Department] | ROI, team productivity, cost reduction | Business outcomes, ROI, case studies |
| Technical Buyer | Engineer, Architect, Tech Lead | Technical fit, easy integration | Architecture, security, documentation |
| User/Champion | Manager, Team Lead, Power User | Makes job easier, quick wins | UX, ease of use, time savings |

### ICP Validation Checklist

- [ ] 5+ paying customers match this profile
- [ ] Fastest sales cycles (< median)
- [ ] Highest LTV (> median)
- [ ] Lowest churn (< 5% annual)
- [ ] Strong product engagement
- [ ] Willing to do case studies

---

## Market Sizing Framework

### TAM/SAM/SOM Calculation

| Level | Definition | Method |
|-------|-----------|--------|
| TAM (Total Addressable Market) | Everyone who could use this type of solution | Industry reports + bottom-up sizing |
| SAM (Serviceable Addressable Market) | Segment you can reach with current product/channel | TAM filtered by ICP criteria |
| SOM (Serviceable Obtainable Market) | Realistic capture in 12-24 months | SAM × expected market share % |

### Bottom-Up Sizing Template

```
TAM = [# of potential customers] × [average annual contract value]
SAM = TAM × [% that match ICP] × [% in reachable geography]
SOM = SAM × [realistic market share in Year 1 (typically 1-5%)]
```

### Market Segmentation

| Segment | Size | Growth | Competition | Priority |
|---------|------|--------|-------------|----------|
| [Segment 1] | [# customers] | [% YoY] | [High/Med/Low] | [1-5] |
| [Segment 2] | [# customers] | [% YoY] | [High/Med/Low] | [1-5] |
| [Segment 3] | [# customers] | [% YoY] | [High/Med/Low] | [1-5] |

### Trend Analysis

1. Identify 3-5 macro trends affecting the market
2. Map each trend to opportunity or threat
3. Quantify impact timeline (6 months, 1 year, 3 years)
4. Align product roadmap to capitalize on tailwinds
5. Build defensive strategy against headwinds

---

> **International Expansion** — 詳見 pmm-gtm.md 的 International Expansion 區段。

---

## Market Research Methods

| Method | Speed | Cost | Depth |
|--------|-------|------|-------|
| Customer interviews (5-10) | 1-2 weeks | Low | High |
| Survey (100+ responses) | 2-3 weeks | Low-Med | Medium |
| Industry reports (Gartner, etc.) | Immediate | High | Medium |
| Competitor analysis | 1 week | Low | Medium |
| Social listening | Ongoing | Low | Low-Med |
| Sales call analysis | 1 week | Low | High |

### Customer Interview Guide

1. "Tell me about your current workflow for [problem area]"
2. "What's the most frustrating part?"
3. "What tools do you use today? What's missing?"
4. "How do you measure success in this area?"
5. "If you could wave a magic wand, what would change?"
6. "What would make you switch from your current solution?"
7. "How much time/money do you spend on this today?"
8. "Who else is involved in this decision?"

### Output: Market Analysis Document

```
docs/pmm/{product}/market-analysis.md
├── Executive Summary
├── Market Size (TAM/SAM/SOM)
├── Market Segmentation
├── Trend Analysis
├── ICP Definition
├── Buyer Personas
├── Key Findings & Recommendations
└── Data Sources & Assumptions
```
