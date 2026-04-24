# sme-design Skill 品質審查（v0.1）

Codex 審查日期：2026-04-23
審查範圍：`.claude/skills/sme-design/`（SKILL.md + 6 references + templates + scripts）
對照源材料：`huashu-design/` + `docs/design.md`（Claude Design 原版）

## 總評

- 可以當作第一堂直播 demo：**否**
- 整體品質：**B**
- 必修問題：**7 處**
- 可修問題：**8 處**

核心結論：有真實蒸餾、不是純表面搬運，但 `asset-protocol` 退化最嚴重，加上 battlecard 的 slide scale 自相矛盾、腳本缺可觀測性，現在還不適合上線。

## 真正汲取到的核心（白名單 · 11 項）

1. Junior designer ↔ manager 關係正確轉成報告場景
2. 「先 context、不要憑空做」保留了原 prompt 主幹
3. `assumptions + reasoning + placeholder` 有真正操作化
4. 10 題一次問完的做法有保留
5. 3+ variations 與探索矩陣落成 battlecard 場景語言
6. `Mood, Not Layout` 被正確移植
7. `oklch` 作為內部衍生色工具被保留
8. Data slop / Quote slop / Bento / landing-template slop 四種都寫清楚
9. `One thousand no's for every yes` 不只引用，還加了自問清單
10. 5 維度 critique 幾乎完整蒸餾成功
11. 台灣傳產 fallback（FB 粉專／104／名片）是有價值的本土原創 insight

## 漏掉／假抄的地方（黑名單 · 10 項）

1. **最大漏洞**：`asset-protocol` 拿了 huashu 5 步外殼，卻丟掉「資產 > 規範」核心洞見（huashu/SKILL.md:79-97）
2. 漏掉產品圖／UI 截圖的一等公民地位（huashu/SKILL.md:118-169）
3. 漏掉 `5-10-2-8` 素材門檻（huashu/SKILL.md:170-197）
4. 漏掉「找不到 Logo 要停下問」硬停規則（huashu/SKILL.md:273-280）
5. design-philosophy 拿掉了原版「最佳執行路徑」，只剩風格目錄
6. anti-slop 少了「品牌識別度保護」的深層邏輯
7. anti-slop 少了「CSS 剪影代替真產品圖」反模式
8. template-guide 寫 20 個 placeholder 但實際只有 19 個
9. `overlap_level` 只是裝飾字串，沒有驅動畫面
10. `html_to_pptx.mjs` 幾乎沒有 validation，容易輸出壞 PPT

## 7 必修問題

| # | 問題 | 位置 |
|---|------|------|
| 1 | SKILL.md 把不存在的模板寫成標準流程 | SKILL.md:100, 159-163 |
| 2 | anti-slop 禁 Inter，design-philosophy 卻推薦 Inter Tight | anti-slop.md:119-127 vs design-philosophy.md:107-111, 149-152 |
| 3 | asset-protocol 漏掉「Logo/產品圖/UI 截圖 > 色值」核心 | asset-protocol.md:47-205 |
| 4 | placeholder 數量寫錯（寫 20，實際 19） | template-guide.md:61-83 |
| 5 | `overlap_level` 沒有真正驅動畫面 | battlecard.html:577-586 |
| 6 | battlecard 字級（11-14px）嚴重低於自己制定的 slide 規範（24px） | anti-slop.md:260-267 vs battlecard.html:206-230, 260-263 |
| 7 | html_to_pptx.mjs 缺 pageerror/requestfailed/overflow 可觀測性 | html_to_pptx.mjs:153-189 |

## 8 可修問題

| # | 問題 | 位置 |
|---|------|------|
| 1 | description 觸發詞缺「客戶 brief / 客戶研究 / 成果簡報」 | SKILL.md:3, 14-18 |
| 2 | 最小問題清單只有 5 題，junior-workflow 標準是 10 題 | SKILL.md:128-133 |
| 3 | design-philosophy 缺每個風格的最佳執行路徑 | design-philosophy.md:15-257 |
| 4 | anti-slop 缺合法例外與品牌 override 規則 | anti-slop.md:24-209 |
| 5 | template-guide 沒明寫 talk_tracks 需要三個 `.talk` block | template-guide.md:79-83 |
| 6 | battlecard footer `big-num` 固定是 `08`，無語義 | battlecard.html:660-668 |
| 7 | html_to_pptx.mjs dependency 錯誤訊息過於籠統，不建立輸出目錄 | html_to_pptx.mjs:128-135, 217 |
| 8 | `凭空` 應改 `憑空`（繁簡混字） | SKILL.md:24, 32, 187 |
