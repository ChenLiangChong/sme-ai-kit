# 翻譯 QA 報告

比對範圍：
- 英文原檔：`.claude/skills/social-media/references/*.md`
- 中文 draft：`docs/skill-translation/drafts/*.md`
- 依據：`docs/skill-translation/terminology.md`、`docs/skill-translation/style-guide.md`

檢查完成日：2026-04-24  
總結：`✅ 通過 20` / `⚠️ 警告 2` / `❌ 失敗 0`

## 整體觀察

- 22 對檔案的主標題鏈、表格數、清單數、編號步驟數大致對齊，未發現整段缺失、表格遺漏或模板遺失。
- 14 個要求加入「工具可用性」區塊的 draft 都已補齊：`analytics`、`competitive-content`、`content-production`、`copy-editing`、`copywriting`、`email-outreach`、`growth-loops`、`marketing-ops`、`paid-acquisition`、`pmm-pricing`、`quality_checklist`、`retention`、`social-content`、`line-marketing`。
- 明確問題只有 2 個，皆屬小問題：
  - `copywriting.md`：原檔既有中文在地化段落被做了標點層級的重寫。
  - `quality_checklist.md`：原檔既有中文在地化段落有 1 處用詞被改寫。

---

## pmm-positioning — ✅ 通過

- 內容完整性：EN `L7-L201` 與 ZH `L7-L201` 主體章節完整對齊，`code/table/bullet/numbered` 計數皆相同（4/34/36/34），未見段落、表格或模板遺漏。
- 行數合理性：EN `204` 行，ZH `204` 行，差 `0` 行。
- 術語一致性：`Head-to-Head`、`April Dunford` 於 ZH `L41`、`L186` 保留英文，`定位聲明`、`價值主張` 用法與 terminology 一致，未見簡中自創譯名。
- 英文保留項：模板與英文關鍵詞保留正常，例如 `Head-to-Head`、`Create New Category` 仍在 ZH `L41-L57`。
- 結構對齊：EN `## Positioning Development`/`## Category Strategy`/`## Do's and Don'ts`/`## 快速參考` 對應 ZH `L7`/`L39`/`L170`/`L184`，層級一致。
- 工具降級提示：不適用；此檔不在 14 個必填清單。
- Do/Don't、快速參考：EN `L170-L201` 對應 ZH `L170-L201`，區塊齊全且順序未變。

## pmm-competitive — ✅ 通過

- 內容完整性：EN `L7-L212` 與 ZH `L7-L212` 標題鏈一致，`code/table/bullet/numbered` 計數同為 `2/31/24/54`，未見 Battlecard、Win/Loss 區段缺漏。
- 行數合理性：EN `215` 行，ZH `215` 行，差 `0` 行。
- 術語一致性：`Battlecard`、`Win/Loss`、`Playbook` 於 ZH `L30`、`L85`、`L146` 保留英文，`競品情報`、`競品態勢` 用詞穩定。
- 英文保留項：`Battlecard` 模板與 `Win/Loss` 標示完整保留，未把縮寫或品牌式寫法硬翻。
- 結構對齊：EN `## Competitive Intelligence Workflow` 到 `## 快速參考` 對應 ZH `L7-L197`，章節順序一致。
- 工具降級提示：不適用。
- Do/Don't、快速參考：ZH `L183-L212` 與 EN `L183-L212` 對齊，無缺段。

## pmm-gtm — ✅ 通過

- 內容完整性：EN `L7-L219` 與 ZH `L7-L219` 章節完整對應，`code/table/bullet/numbered` 計數同為 `4/58/23/45`。
- 行數合理性：EN `223` 行，ZH `223` 行，差 `0` 行。
- 術語一致性：`GTM`、`Sales Enablement`、`Campaign Brief` 分別見 ZH `L1`、`L55`、`L98`，均依術語表保留英文。
- 英文保留項：`Demo`、`RACI` 類英文專名皆保留，未見縮寫誤譯。
- 結構對齊：EN `## GTM Planning Workflow`/`## Channel Strategy`/`## Do's and Don'ts` 對應 ZH `L7`/`L20`/`L187`，順序一致。
- 工具降級提示：不適用。
- Do/Don't、快速參考：ZH `L187-L219` 完整覆蓋 EN `L187-L219`。

## pmm-launch — ✅ 通過

- 內容完整性：EN `L7-L282` 與 ZH `L7-L282` 所有上市層級、RACI、Go/No-Go、Retro、台灣草根上市策略都在；`table/bullet/numbered` 計數同為 `89/35/41`。
- 行數合理性：EN `286` 行，ZH `286` 行，差 `0` 行。
- 術語一致性：`RACI`、`Go/No-Go`、`Retro` 於 ZH `L93`、`L143`、`L165-L176` 保留英文，`上市層級`、`利害關係人` 等譯名一致。
- 英文保留項：`Tier 1`、`SaaS`、`Output Artifacts` 等保留正常。
- 結構對齊：EN `## Launch Tiers` 到 `## 快速參考` 對應 ZH `L7-L264`，台灣在地化段落也對齊於 `L219`。
- 工具降級提示：不適用。
- Do/Don't、快速參考：ZH `L250-L282` 與 EN `L250-L282` 完整相符。

## pmm-market — ✅ 通過

- 內容完整性：EN `L7-L155` 與 ZH `L7-L155` 皆含 `ICP`、`TAM/SAM/SOM`、`Bottom-Up`、訪談指南與輸出模板；`code/table/bullet/numbered` 計數同為 `4/30/14/33`。
- 行數合理性：EN `159` 行，ZH `159` 行，差 `0` 行。
- 術語一致性：`TAM / SAM / SOM` 於 ZH `L51-L55` 保留英文縮寫，`ICP`、`買家人物誌` 等符合 terminology。
- 英文保留項：`Bottom-Up` 與 `Output` 於 ZH `L59`、`L111` 保留正常。
- 結構對齊：EN `## ICP Definition Workflow`/`## Market Sizing Framework`/`## 快速參考` 對應 ZH `L7`/`L49`/`L141`。
- 工具降級提示：不適用。
- Do/Don't、快速參考：ZH `L127-L155` 與 EN `L127-L155` 對齊。

## pmm-messaging — ✅ 通過

- 內容完整性：EN `L7-L178` 與 ZH `L7-L178` 全數對應，`Proof Points`、`Landing Pages`、`Email Sequences`、`Objection Handling` 均在；`code/table/bullet/numbered` 計數同為 `2/62/13/20`。
- 行數合理性：EN `182` 行，ZH `182` 行，差 `0` 行。
- 術語一致性：`Persona`、`Proof Point`、`Landing Pages` 見 ZH `L31`、`L64`、`L79`，用法符合術語表。
- 英文保留項：`Email`、`Landing Pages`、`Proof Point` 等專有詞保留正常。
- 結構對齊：EN `## Messaging Framework Development` 到 `## 快速參考` 對應 ZH `L7-L163`，無換序。
- 工具降級提示：不適用。
- Do/Don't、快速參考：ZH `L148-L178` 與 EN `L148-L178` 一致。

## pmm-patterns — ✅ 通過

- 內容完整性：EN `L7-L219` 與 ZH `L7-L219` 對齊，`Anti-Rationalization`、`Execution Report`、`Weekly Report`、`ORCHESTRATOR`、`KPIs` 都在；`code/table/bullet/numbered` 計數同為 `4/67/21/25`。
- 行數合理性：EN `223` 行，ZH `223` 行，差 `0` 行。
- 術語一致性：`ORCHESTRATOR`、`KPIs`、`PMM Weekly Report` 見 ZH `L177`、`L146`、`L108`，保留英文合理。
- 英文保留項：報告模板標題如 `Summary`、`Gate Outputs`、`Next Steps` 仍保留英文，符合填空模板規則。
- 結構對齊：EN `## Anti-Rationalization Patterns` 到 `## 快速參考` 對應 ZH `L7-L206`。
- 工具降級提示：不適用。
- Do/Don't、快速參考：ZH `L192-L219` 與 EN `L192-L219` 對齊。

## pmm-pricing — ✅ 通過

- 內容完整性：EN `L7-L379` 與 ZH `L11-L383` 主體、研究方法、定價頁設計、台灣在地化補充、快速參考都在；`code/table/bullet/numbered` 計數同為 `6/53/80/29`。
- 行數合理性：EN `383` 行，ZH `387` 行，差 `+4` 行；差異來自 draft 新增工具降級提示與分隔線，屬合理範圍。
- 術語一致性：`SaaS`、`Value Metric`、`Good-Better-Best` 於 ZH `L16`、`L79`、`L109` 保留英文，`價值定價`、`價格錨定` 等無自創譯名。
- 英文保留項：`Van Westendorp`、`MaxDiff`、`Related Skills` 等保留正常。
- 結構對齊：EN `## Pricing Strategy (from pricing-strategy skill)`/`## Before Starting`/`## Do's and Don'ts` 對應 ZH `L11`/`L20`/`L353`；台灣在地化補充也對齊於 ZH `L311`。
- 工具降級提示：必填且已補；見 ZH `L7`。
- Do/Don't、快速參考：ZH `L353-L383` 與 EN `L349-L379` 對齊；原檔既有中文在地化補充 `EN L307-L379` 與 ZH `L311-L383` 未見內容改寫。

## copywriting — ⚠️ 警告

- 內容完整性：EN `L11-L487` 與 ZH `L16-L492` 兩個子技能 (`copywriting`、`content-strategy`) 及其表格、CTA、在地化注意事項、快速參考均完整存在；`table/bullet/numbered` 計數同為 `47/151/26`。
- 行數合理性：EN `493` 行，ZH `498` 行，差 `+5` 行；主因是 draft 新增工具降級提示與分隔線，屬合理。
- 術語一致性：`CTA`、`Landing Page`、`Meta` 於 ZH `L150`、`L177`、`L238` 保留正常；簡中詞 `帖子/博客/快拍/博主/視頻/點贊` 只出現在在地化對照表與提醒句（ZH `L296-L306`、`L460-L466`），這些內容原檔已有，不算術語錯誤。
- 英文保留項：`Landing Page`、`Meta`、`Headline`、`content-strategy` 等保留正確，未見 API/變數被翻譯。
- 結構對齊：EN `## copywriting` 到第二段 `## Related Skills` 的順序，對應 ZH `L16-L492`，兩段模組結構完整對齊。
- 工具降級提示：必填且已補；見 ZH `L12`。
- Do/Don't、快速參考：ZH `L453-L492` 與 EN `L448-L487` 對齊，但 `台灣中文文案注意事項` 屬原檔既有中文段落，draft 在 ZH `L310-L314`、`L333-L343` 把 source `EN L305-L309`、`L328-L338` 的破折號 `—` 改成 `——`；屬標點級重寫，依規範建議保留原樣，因此列警告。

## copy-editing — ✅ 通過

- 內容完整性：EN `L12-L501` 與 ZH `L16-L505` 七掃框架、Checklist、Examples、快速參考、Related Skills 皆完整；`table/bullet/numbered` 計數同為 `30/159/52`。
- 行數合理性：EN `506` 行，ZH `510` 行，差 `+4` 行；來自工具降級提示與分隔線。
- 術語一致性：`Sweep 1`、`Voice and Tone`、`Zero Risk` 於 ZH `L41`、`L67`、`L227` 保留正常，`文案編修` 等譯名一致。
- 英文保留項：七掃標籤與英文例句均保留，未見變數或模板誤翻。
- 結構對齊：EN `## copy-editing`/`## Core Philosophy`/`## 快速參考` 對應 ZH `L16`/`L23`/`L482`，順序一致。
- 工具降級提示：必填且已補；見 ZH `L12`。
- Do/Don't、快速參考：ZH `L467-L505` 與 EN `L463-L501` 對齊，且引用 `copywriting.md` 的台灣中文注意事項保留於 ZH `L9`。

## content-production — ✅ 通過

- 內容完整性：EN `L12-L511` 與 ZH `L16-L515` 研究、Brief、Draft、Humanization、Repurposing、快速參考與 Related Skills 完整；`table/bullet/numbered` 計數同為 `30/131/24`。
- 行數合理性：EN `514` 行，ZH `518` 行，差 `+4` 行；原因為工具降級提示。
- 術語一致性：`Research & Brief`、`Draft` 於 ZH `L46-L49` 保留英文，整體用詞與 terminology 一致。
- 英文保留項：`Brief`、`CTA`、`Related Skills` 等英文保留正常。
- 結構對齊：EN `## content-production` 到 `## Related Skills` 對應 ZH `L16-L515`，未換序。
- 工具降級提示：必填且已補；見 ZH `L12`。
- Do/Don't、快速參考：ZH `L480-L515` 與 EN `L476-L511` 對齊。

## marketing-ops — ✅ 通過

- 內容完整性：EN `L12-L585` 與 ZH `L17-L590` 路由矩陣、Campaign Orchestration、Audit、台灣中小企業簡化路由與快速參考均在；`code/table/bullet/numbered` 計數同為 `6/110/154/43`。
- 行數合理性：EN `589` 行，ZH `594` 行，差 `+5` 行；來自工具降級提示與分隔線。
- 術語一致性：`Campaign Orchestration`、`query_knowledge`、`marketing context` 見 ZH `L564-L565`，英文保留合理，未見簡中詞。
- 英文保留項：函式與模組名如 `query_knowledge(category='brand')`、`Campaign Orchestration` 均保留。
- 結構對齊：EN `## marketing-ops`/`## Before Starting`/`## 快速參考` 對應 ZH `L17`/`L24`/`L573`，順序一致。
- 工具降級提示：必填且已補；見 ZH `L13`。
- Do/Don't、快速參考：`## Do's and Don'ts` 在 ZH `L561-L571`，`## 快速參考` 在 ZH `L573-L590`，與 EN `L556-L585` 對齊。

## email-outreach — ✅ 通過

- 內容完整性：EN `L13-L425` 與 ZH `L17-L435` Email 序列、冷開發、範本、快速參考與 Related Skills 皆完整；`code/table/bullet/numbered` 計數同為 `4/54/79/42`。
- 行數合理性：EN `429` 行，ZH `439` 行，差 `+10` 行；差值仍在 ±15 內，主因是工具降級提示與中文換行。
- 術語一致性：`Email`、`CTA` 等於 ZH `L1`、`L55` 保留英文，未見簡中詞。
- 英文保留項：`Email Sequence`、`subject line`、`CTA` 等均保留，模板無誤翻。
- 結構對齊：EN `## email-sequence` 到 `## Related Skills` 對應 ZH `L17-L435`，無缺段。
- 工具降級提示：必填且已補；見 ZH `L13`。
- Do/Don't、快速參考：ZH `L397-L435` 與 EN `L387-L425` 對齊。

## paid-acquisition — ✅ 通過

- 內容完整性：EN `L12-L620` 與 ZH `L16-L637` 兩段子技能 (`ad-creative`、`paid-ads`)、台灣電商廣告補充、快速參考皆完整；`code/table/bullet/numbered` 計數同為 `6/56/163/48`。
- 行數合理性：EN `623` 行，ZH `640` 行，差 `+17` 行；超出 ±15，但可由 ZH `L12-L14` 新增工具降級提示、以及中文段落換行擴張解釋，未造成內容缺漏。
- 術語一致性：`Meta Ads`、`Pre-Launch`、`Offer`、`Campaign` 於 ZH `L7`、`L505`、`L30`、`L291` 保留正常，未見簡中詞。
- 英文保留項：`query_knowledge`、平台名、`CTR/CVR/CPA` 與 `Pre-Launch` 均保留。
- 結構對齊：EN `## ad-creative`/`## paid-ads`/`## 快速參考` 對應 ZH `L16`/`L277`/`L624`，兩大段順序一致。
- 工具降級提示：必填且已補；見 ZH `L12`。
- Do/Don't、快速參考：ZH `L610-L637` 與 EN `L593-L620` 對齊；原檔台灣在地化補充也仍在 ZH `L569-L637`。

## growth-loops — ✅ 通過

- 內容完整性：EN `L12-L819` 與 ZH `L16-L825` 的 `Referral Program`、Loops、自帶係數與擴散機制、快速參考均完整；`code/table/bullet/numbered` 計數同為 `12/131/153/83`。
- 行數合理性：EN `824` 行，ZH `830` 行，差 `+6` 行；合理。
- 術語一致性：`Growth Loops`、`Referral Program` 等於 ZH `L1`、`L19` 保留英文，未見簡中詞或自創譯名。
- 英文保留項：所有程式碼框、變數與框架名稱均保留；`code fence` 數量 EN/ZH 同為 `12`。
- 結構對齊：EN `## referral-program`/`## Before Starting`/`## 快速參考` 對應 ZH `L16`/`L23`/`L807`。
- 工具降級提示：必填且已補；見 ZH `L12`。
- Do/Don't、快速參考：ZH `L793-L825` 與 EN `L787-L819` 對齊。

## retention — ✅ 通過

- 內容完整性：EN `L12-L294` 與 ZH `L19-L301` 的 `Cancel Flow`、退出問卷、Save Offer、Dunning、實體/服務業留客策略都在；`code/table/bullet/numbered` 計數同為 `2/53/74/9`。
- 行數合理性：EN `298` 行，ZH `305` 行，差 `+7` 行；合理。
- 術語一致性：`Cancel Flow`、`Dunning`、`VIP` 於 ZH `L54`、`L139`、`L230` 保留正常，`留客`、`流失` 用詞一致。
- 英文保留項：`Dunning`、`Offer`、`Email` 等保留正確。
- 結構對齊：EN `## churn-prevention`/`## 實體/服務業留客策略`/`## Related Skills` 對應 ZH `L19`/`L226`/`L301`。
- 工具降級提示：必填且已補；見 ZH `L12-L16`。
- Do/Don't、快速參考：ZH `L270-L301` 與 EN `L263-L294` 對齊；原檔既有中文 `實體/服務業留客策略` 在 ZH `L226-L296` 保留，`Related Skills` 反而修掉了 EN 殘留英文敘述。

## analytics — ✅ 通過

- 內容完整性：EN `L11-L540` 與 ZH `L15-L544` 的 `campaign-analytics`、`analytics-tracking`、GA4、GTM、UTM、跨平台追蹤均完整；`code/table/bullet/numbered` 計數同為 `22/50/74/38`。
- 行數合理性：EN `542` 行，ZH `546` 行，差 `+4` 行；合理。
- 術語一致性：`GA4`、`Google Tag Manager`、`UTM` 見 ZH `L280`、`L331`、`L415`，保留正常，未見簡中詞。
- 英文保留項：事件名、參數、追蹤工具名與 `code fence` 都完整保留。
- 結構對齊：EN `## campaign-analytics`/`## analytics-tracking`/`## 快速參考` 對應 ZH `L15`/`L171`/`L526`。
- 工具降級提示：必填且已補；見 ZH `L11`。
- Do/Don't、快速參考：ZH `L513-L544` 與 EN `L509-L540` 對齊。

## competitive-content — ✅ 通過

- 內容完整性：EN `L11-L411` 與 ZH `L16-L416` 的 `competitor-alternatives`、`marketing-psychology`、SEO、Schema、雙重快速參考都在；`code/table/bullet/numbered` 計數同為 `0/37/73/60`。
- 行數合理性：EN `415` 行，ZH `420` 行，差 `+5` 行；合理。
- 術語一致性：`SEO`、`Schema Markup`、`TL;DR` 於 ZH `L205`、`L221`、`L154` 保留正常。
- 英文保留項：`[Competitor]`、`Schema Markup`、`TL;DR`、`SEO` 等英文保留正確。
- 結構對齊：EN 第一個 `## Quick Reference` 在 `L332`，ZH 對應 `L337`；第二個 `## 快速參考` 在 EN `L393`、ZH `L398`，雙區塊皆完整。
- 工具降級提示：必填且已補；見 ZH `L12`。
- Do/Don't、快速參考：ZH `L384-L416` 與 EN `L379-L411` 對齊。

## social-content — ✅ 通過

- 內容完整性：EN `L13-L528` 與 ZH `L17-L532` 的 `social-content`、`social-media-manager`、平台表、內容再利用、稽核清單與快速參考皆完整；`code/table/bullet/numbered` 計數同為 `2/75/119/53`。
- 行數合理性：EN `534` 行，ZH `538` 行，差 `+4` 行；合理。
- 術語一致性：`Reels`、`LINE VOOM`、`Threads` 於 ZH `L57-L59` 保留正常；`帖子` 只在提醒句 ZH `L9` 作為禁用範例，非誤譯。
- 英文保留項：平台名、`LINE VOOM`、`Threads`、`Reels` 都保留正確。
- 結構對齊：EN `## social-content`/`## social-media-manager`/`## 快速參考` 對應 ZH `L17`/`L314`/`L509`。
- 工具降級提示：必填且已補；見 ZH `L13`。
- Do/Don't、快速參考：ZH `L494-L532` 與 EN `L490-L528` 對齊。

## social-analytics — ✅ 通過

- 內容完整性：EN `L12-L387` 與 ZH `L12-L387` 的社群分析、平台基準、ROI、工具、X/Twitter 參考與快速參考均完整；`code/table/bullet/numbered` 計數同為 `6/95/51/33`。
- 行數合理性：EN `392` 行，ZH `392` 行，差 `0` 行。
- 術語一致性：`ROI`、`CPC`、`X/Twitter` 於 ZH `L3`、`L168`、`L301` 保留正常。
- 英文保留項：`Platform Benchmarks`、`X/Twitter`、`CPC`、`CTR` 等都保留。
- 結構對齊：EN `## social-media-analyzer`/`## x-twitter-growth`/`## 快速參考` 對應 ZH `L12`/`L298`/`L364`。
- 工具降級提示：不適用；此檔不在 14 個必填清單。
- Do/Don't、快速參考：ZH `L349-L387` 與 EN `L349-L387` 完整一致。

## line-marketing — ✅ 通過

- 內容完整性：EN `L7-L286` 與 ZH `L14-L293` 主體內容對齊，`LINE OA`、`Rich Menu`、`Flex Message`、會員經營與活動範例都在；`code/table/bullet/numbered` 計數同為 `8/57/49/22`。
- 行數合理性：EN `290` 行，ZH `297` 行，差 `+7` 行；來自工具降級提示新增區塊。
- 術語一致性：`LINE OA`、`Rich Menu`、`Flex Message` 於 ZH `L24-L43` 保留正常，符合白名單。
- 英文保留項：LINE MCP 函式如 `reply`、`multicast`、`list_channels` 保留於 ZH `L7-L10`，未誤翻。
- 結構對齊：EN `## 與 company-ops line-comms 的分工`/`## LINE OA 基本功能`/`## 快速參考` 對應 ZH `L14`/`L30`/`L279`。
- 工具降級提示：必填且已補；見 ZH `L7-L12`。
- Do/Don't、快速參考：ZH `L265-L293` 與 EN `L258-L286` 對齊；原檔大部分中文內容保持原貌，僅前置新增工具區塊。

## quality_checklist — ⚠️ 警告

- 內容完整性：EN `L7-L90` 與 ZH `L11-L94` 的格式確認、重構記錄、內容審計、在地化記錄、最終判定都在；`table/bullet/numbered` 計數同為 `24/15/13`。
- 行數合理性：EN `96` 行，ZH `100` 行，差 `+4` 行；合理，主因是工具降級提示。
- 術語一致性：大多符合 terminology，但原檔既有中文記錄 `EN L82` 的「渠道」在 draft 改成 ZH `L86` 的「通路」；雖然是較符合台灣用詞的修正，仍屬既有中文段落改寫。
- 英文保留項：`Related Skills`、檔名清單與日期均保留正常。
- 結構對齊：EN `## 格式確認`/`## 重構記錄（2026-04-03）`/`## 最終判定` 對應 ZH `L11`/`L29`/`L94`，順序一致。
- 工具降級提示：必填且已補；見 ZH `L7`。
- Do/Don't、快速參考：本檔 source 本身沒有這兩區塊，屬不適用；警告點在 `在地化記錄` 的原檔中文段落未完全保留原樣，見 EN `L82` vs ZH `L86`。

---

## 結論

- `✅ 通過 20`
- `⚠️ 警告 2`
- `❌ 失敗 0`

建議先修正 `copywriting.md` 與 `quality_checklist.md` 兩個警告點，再進行最終覆蓋授權。
