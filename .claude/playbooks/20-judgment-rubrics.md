# 20 — 判斷 rubric（把「經驗直覺」寫成可查表的判準）

> 讀者：本 repo 開發 session 的主模型與 subagent。每條判準附一個正例、一個反例——**正反例全部來自本專案真實歷史**，不是編的。
> 用法：宣稱完成前過 §2；卡住時過 §1 / §4；想重試第三次前必過 §4；碰到 §3 清單直接停下問使用者。

## §1 何時該升級模型（或把問題升回主對話）

**判準**：出現下列任一 → 升級，不要同級重試：
- 需要跨模組推理（改 A 會不會弄壞 B 的不變量）
- 需要對抗式思考（安全邊界、gate、floor、去識別化）
- 失敗原因說不清楚（「跑了但結果不對、不知道為什麼」）
- 任務涉及「判斷要不要做」而不只是「怎麼做」

**正例**：#190 attribution race 的解法評估（per-person session vs agent-passed actor）——涉及威脅模型與機率性 vs 結構性的取捨，用強模型 + 13 次行為實驗才定案「律所首選 per-person」。這種問題丟給 sonnet 只會得到看似合理的散文。
**反例**：把「幫我找 `_firm_buffer_days` 的所有呼叫點」升到 opus——這是 grep 等級的定位工作，Explore(sonnet) 就該做完，升級純浪費。

## §2 何時算真的完成（DoD，全中才能說「完成」）

1. **測試綠**（程式類改動）：跑了本次改動對應的測試 + 全量回歸（`mcp-servers/business-db/tests/run_all.sh`），宣稱時附數字（幾 passed）。純文件改動沒有對應測試，以條 2 的 read-back 取代本條。
2. **獨立驗證**：fresh-context agent read-back（檔案類）或 codex 對抗審 READY（程式類高風險）。
3. **文件同步**：改了行為 → 對應 skill reference / CLAUDE.md 段落同步（依 root〈文件權威層級〉分層），文件宣稱不超前程式。
4. **教訓落檔**：踩了坑 → 按 `40-maintenance.md` 寫回對應 playbook 或 memory。

**正例**：Task C post-run 三修——修完 → 71/71 + engine 335 + smoke 365 全綠 → codex 兩輪對抗審 READY → skill 文件同步（pleading-sync.md「4 接線點」改「6 接線點」）→ 才 commit。
**反例**：G5a 第一版用 `except Exception` 就宣稱「測試證明 unique index 擋下」——任何錯誤都會讓它假綠，是 codex 抓出來的。**「有測試」不等於「測試有鑑別力」**：問自己「如果程式是錯的，這個測試會紅嗎？」

## §3 何時該停下來問使用者（清單制，碰到就停）

- **push 到共用 branch**（commit 可以自主、push 要授權——有過「推了之後被質疑授權」的實績）
- **跨產品線的動作**：任何會讓 master 與 legal-admin 內容互流的操作（merge、大段複製）
- **刪除或重寫「不是你建立的」東西**（DB row、別人的檔、歷史 commit）；rebase / force push 一律先問
- **真實客戶 / 當事人資料**要進任何會離開本機的地方（git、bridge、雲端）
- **範圍升級**：做 A 途中發現「順便把 B 也改了比較對」——B 超出原委託就先問
- **兩輪重試後仍失敗**且換路也想不出來
- **發現文件與程式矛盾、而修正方向會改變產品行為**（修文件遷就程式=自主可做；改程式遷就文件=行為變更、先問）

**正例**：pleading 的 `PLEADING_DB_PATH` commit 進 production repo——HOLD 等老闆點頭才動，即使技術上一分鐘的事。
**反例**：依「轉述的授權」直接 push origin/legal-admin——老闆事後問「你有要推到git嗎?」。轉述授權 ≠ 直接授權，寧可多問一句。

## §4 方向錯了的訊號（該換路，不是再試一次）

出現任一訊號 → 停止同路重試，回到設計層重想（或按 §1 升級）：
- **修補在長大**：每輪修復讓 diff 更大、碰到更多不相關模組
- **測試要弱化才過**：想把斷言改鬆、把 case 刪掉、加 skip——這是程式錯不是測試錯的訊號
- **同一假設試了兩輪都不成立**：第三輪前必須先推翻假設本身
- **開始需要「宣稱」而非「證明」**：解釋越來越長、證據越來越少
- **在繞過防護而不是理解防護**：想 bypass gate / hook / unique index / sandbox 來讓東西動起來

**正例**：F-P0-4 codex 給的 MED（多筆 active settings 讀舊值）——寫測試去證實時發現 `IntegrityError`，立刻推翻假設：場景被 `idx_rules_unique_active` DB-prevented。跟著證據走、修正分析，而不是硬把測試改成能過。
**反例**：run_eval 初版在 WSL 上凍死時若繼續「調參數再跑一次」就死路——真因是 claude -p 併發 MCP fan-out（~130MB/份）；正解是換路：砍 MCP（`--strict-mcp-config`）+ 換 Agent tool 做行為實驗。

## §5 品質底線怎麼驗（按產出類型查表)

| 產出 | 底線驗法 |
|------|----------|
| 程式 | 對應測試 + 全量回歸；高風險（floor/gate/escalation/時限引擎/去識別化）加 codex 對抗審 |
| 測試本身 | 鑑別力檢查：故意把被測行為弄壞一下、測試必須紅（mutation 抽查一兩點即可） |
| 文件 | fresh agent read-back：只給路徑+驗收問題；逐一驗證文件裡的路徑/工具名/指令真的存在（`ls`/`grep` 實查, 不是「看起來對」） |
| 法律相關內容 | 法條號/天數一律 `taiwan-legal-db` `query_regulation` 查證；時限天數只能來自引擎輸出附 `statutory_basis`,**絕不 LLM 心算**（算錯=執業過失） |
| 對外文案 / 客戶內容 | 真實名稱不進 git（用 [XX] 占位）；繁體中文；老闆語氣規則見 memory |
| DB / migration | 在 dev DB 實跑 migration + 回歸；schema 與 migration 不可重複定義同一欄位（#12 fresh-install 崩潰的教訓） |

## §6 「證據等級」速查（宣稱任何事之前自問）

| 等級 | 例子 | 可以拿來宣稱什麼 |
|------|------|------------------|
| 一級：實跑輸出 | 測試 passed 數、live 驗證、read-back 結果 | 「已完成」「已修復」 |
| 二級：靜態閱讀 | 看碼推理、grep 結果 | 「應該是 / 我認為」——必須標明未驗證 |
| 三級：記憶 / 印象 | 「之前好像是這樣」 | 什麼都不能宣稱，只能當查證的起點 |

本專案的實績：二級判斷被一級證據推翻的案例至少三件（G5a 假綠、F-P0-4 DB-prevented、#182 meta int 靜默丟棄）。**跨等級混用（用二級語氣講三級內容）= 捏造。**

## 教訓登記簿（本檔自身的）

（尚無。格式與升正文規則見 `40-maintenance.md` §3、§4。）
