# sme-design v0.4 終審報告
## 總結
- 🔴 問題：1
- 🟡 建議：0
- ✅ 驗證通過：2

## v0.3 修復驗證
- 1. 通過：`references/template-guide.md:12-15` 已將 4 個未實作模板明確標為「🔴 規劃中」；`references/template-guide.md:166-167`、`217-219`、`235-237`、`259-261`、`279-281`、`317-320`、`339` 均明確寫出「規劃中 + 三選一 + 不要嘗試 Read」，`SKILL.md:100-103`、`173-182` 也一致，不再把規劃中模板當成現成可用模板推薦。
- 2. 通過：`references/template-guide.md:229`、`246`、`290` 已將規劃中模板的占位符描述改為「屆時產出時定義」；本輪完整掃描 `.claude/skills/sme-design/` 全部檔案，未再發現 `TODO` / `TBD` 殘留。
- 3. 未通過：`references/template-guide.md:248-253`、`269-273` 已改成「若有 business-db MCP：...／若無 MCP：...」的條件化寫法，主修復點本身成立；但 `SKILL.md:99` 仍寫「收 context（見下方最小問題清單，若沒 business-db MCP）」 ，與 `SKILL.md:129-146` 的「本 skill 無 MCP 依賴」及固定最小問題清單形成殘留矛盾，表示 MCP 敘述尚未全檔收斂一致。

## 問題（若無寫「本輪無意見」）
- `SKILL.md:99` — 寫成「若沒 business-db MCP 才看最小問題清單」，會推導出「有 MCP 時可不走這套提問」；這與 `SKILL.md:129-146` 的無 MCP 依賴敘述及 `references/junior-workflow.md:42-50` 的新任務必問流程不一致，屬殘留行為矛盾。

## 最終評級
**可以上線：否**
尚有一處 MCP 行為說明前後不一致，會直接影響 agent 是否完整收集 context，建議先收斂再上線。
