# PMM Patterns

Anti-rationalization patterns, pressure resistance, execution reporting, and quality verification for PMM workflows.

---

## Anti-Rationalization Patterns

### Universal Anti-Rationalizations

| Rationalization | Why It's WRONG | Required Action |
|-----------------|----------------|-----------------|
| "We don't have time for research" | Skipping research causes expensive pivots later | **Minimum viable research: 5 customer interviews** |
| "We already know the market" | Assumptions ≠ validated knowledge | **Document assumptions, then validate 3+** |
| "Let's just ship and see" | Post-launch positioning is 10x harder to change | **Position before you ship** |
| "Everyone is our customer" | Selling to everyone = selling to no one | **Define ICP with specific criteria** |
| "We can figure out pricing later" | Pricing anchors are hard to change | **Set pricing before launch** |
| "The product is too early for marketing" | Early marketing = early feedback = better product | **Start marketing from Day 1** |

### PMM-Specific Anti-Rationalizations

| Rationalization | Why It's WRONG | Required Action |
|-----------------|----------------|-----------------|
| "Market is obvious" | Assumptions cause positioning failures | **Quantify with data** |
| "We know our competitors" | Knowledge gaps cause blind spots | **Complete systematic analysis** |
| "Messaging can evolve" | Evolution needs baseline | **Create complete framework first** |
| "Pricing can be adjusted" | Price anchoring is psychological — first price sets expectations | **Research willingness to pay** |
| "Our product sells itself" | No product sells itself at scale | **Build positioning and distribution** |
| "We can skip market analysis" | Skipping research leads to positioning failures | **Complete systematic research** |
| "We need more features first" | Feature parity is a losing game | **Compete on positioning, not features** |
| "Branding can wait" | Every touchpoint is branding whether you plan it or not | **Define brand guidelines early** |

---

## Pressure Resistance Patterns

### Common Pressure Scenarios

| Pressure | Response | Why |
|----------|----------|-----|
| "Just launch already" | Complete at minimum Gates 2-3 (positioning + messaging) | Launching without positioning wastes budget |
| "We already know the market" | Validate with Gate 1 data | Assumptions ≠ evidence |
| "Competitors don't matter" | Complete Gate 5 anyway | Sales needs battlecards regardless |
| "Pricing can wait" | At minimum define launch pricing | Post-launch pricing changes damage trust |
| "Skip GTM, just do PR" | PR is one channel in GTM, not a substitute | Multi-channel always outperforms single |
| "Copy what [competitor] does" | Their positioning works for their strengths | Ours should highlight where we're different |
| "We don't need sales enablement" | Sales will make up their own messaging | Inconsistent messaging confuses buyers |

### How to Push Back

1. **Quantify the risk**: "Without positioning, our $X campaign spend has no targeting basis"
2. **Show precedent**: "Last launch without PMM generated Y% fewer MQLs"
3. **Offer minimum viable**: "Let me do a 2-hour positioning sprint instead of skipping entirely"
4. **Escalate with data**: "Here's what competitors did — we need at least parity"
5. **Document the decision**: If overruled, record the decision and risks for accountability

### Escalation Framework

1. **State the risk**: "If we skip X, we risk Y"
2. **Offer alternatives**: "Here's a faster version that still covers the critical parts"
3. **Document the decision**: "Stakeholder decided to skip X. Risks noted: Y, Z"
4. **Set review trigger**: "If [metric] doesn't hit [target] by [date], we revisit X"

---

## Execution Report Template

### PMM Execution Report

```markdown
# PMM Execution Report: [Product/Feature]

## Summary
- **Gates completed**: 1-7 / partial (list which)
- **Timeline**: [Start] to [End]
- **Key decisions**: [Top 3 decisions made]

## Gate Outputs
| Gate | Status | Key Finding | Deliverable |
|------|--------|-------------|-------------|
| 1. Market Analysis | ✅ Complete | [Key insight] | market-analysis.md |
| 2. Positioning | ✅ Complete | [Key insight] | positioning.md |
| 3. Messaging | ✅ Complete | [Key insight] | messaging-framework.md |
| 4. Pricing | ✅ Complete | [Key insight] | pricing-strategy.md |
| 5. Competitive Intel | ✅ Complete | [Key insight] | competitive-intel.md |
| 6. GTM Plan | ✅ Complete | [Key insight] | gtm-plan.md |
| 7. Launch | ✅ Complete | [Key insight] | launch-plan.md |

## Risks & Mitigations
| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| [Risk 1] | High/Med/Low | High/Med/Low | [Action] |

## Next Steps
1. [Action item + owner + deadline]
2. [Action item + owner + deadline]
3. [Action item + owner + deadline]

## Metrics to Track
| Metric | Baseline | Target | Timeline |
|--------|----------|--------|----------|
| [Metric] | [Current] | [Goal] | [When] |
```

### Weekly PMM Report

```markdown
# PMM Weekly Report — Week of [Date]

## Key Metrics
| Metric | This Week | Last Week | Target | Status |
|--------|-----------|-----------|--------|--------|
| [Metric 1] | [Value] | [Value] | [Target] | 🟢/🟡/🔴 |

## Completed This Week
- [Task]: [Result/Impact]

## In Progress
- [Task]: [Status, ETA]

## Blocked / Needs Decision
- [Item]: [What's needed, from whom]

## Next Week Priorities
1. [Priority 1]
2. [Priority 2]
```

---

## Blocker Criteria

**STOP and escalate when:**

| Blocker Type | Example | Action |
|--------------|---------|--------|
| **Missing Market Data** | No TAM estimates available | STOP. Request data or define assumptions. |
| **Conflicting Positioning** | Stakeholders disagree on differentiation | STOP. Facilitate alignment discussion. |
| **Undefined ICP** | "Everyone is our customer" | STOP. Require specific segment definition. |
| **No Competitive Data** | Can't identify competitors | STOP. Market may not exist or be misunderstood. |
| **Pricing Uncertainty** | No willingness-to-pay data | STOP. Recommend validation approach. |
| **Legal/Compliance Block** | Uncertain about claims or regulations | STOP. Get legal review before publishing. |

---

## PMM KPIs

| Metric | Target | Measurement |
|--------|--------|-------------|
| Product adoption | >40% in 90 days | Feature usage after launch |
| Win rate | >30% competitive | Deals won vs. competitors |
| Sales velocity | -20% YoY | Days from SQL to close |
| Deal size | +25% YoY | Average contract value |
| Launch pipeline | 3:1 ROMI | Pipeline $ : marketing spend |
| Messaging recall | >60% | Customers recall key messages in surveys |

---

## PMM Monthly Rhythm

| Week | Focus |
|------|-------|
| 1 | Review metrics, update battlecards, competitive monitoring |
| 2 | Create assets, publish content, sales enablement |
| 3 | Support launches, optimize campaigns, A/B tests |
| 4 | Monthly report, plan next month, stakeholder alignment |

---

## Quality Verification

All PMM output passes quality verification:
- Self-verify: source attribution, assumption audit, confidence scoring
- Output format: Bottom Line → What (with confidence) → Why → How to Act
- Results tagged: 🟢 verified (data-backed), 🟡 medium (reasonable inference), 🔴 assumed (needs validation)

## ORCHESTRATOR Principle

- **You're the orchestrator** — Dispatch PMM skills, don't market manually
- **Don't skip research** — Research prevents positioning failures
- **Don't assume market fit** — Validate systematically
- **Use agents for specialist work** — Dispatch specialists for complex analysis

### Good (ORCHESTRATOR):
> "I need GTM strategy for the new payment feature. Let me run market-analysis, then define positioning."

### Bad (OPERATOR):
> "I'll write the positioning based on what I think the market wants."
