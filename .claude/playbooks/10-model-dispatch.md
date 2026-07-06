# 10 — 模型調度守則（指揮官不下場）

> 讀者：本 repo 開發 session 的主模型（預設 Opus）。目的：主對話的 context 只用來做判斷與整合，把讀取與機械工作推給便宜的手。
> 為什麼需要這份：見 `00-diagnosis.md` 第二、三名。

## 0. 核心原則（三句話）

1. **指揮官不下場**：大量讀取、掃 repo、查網頁、批次改檔 → 一律派 subagent；主對話只進結論與 `檔:行`。
2. **派工三件套**：每次派工必含〔目標與動機〕〔驗收條件〕〔回報格式〕，缺一件就是在賭 subagent 的運氣。模板見 `30-delegation-templates.md`。
3. **驗證不自驗**：做的人不驗收。驗收派 fresh-context agent（read-back / 跑測試），高風險加 codex 第二意見。

## 1. 本環境可用的棋子（實際型號，不憑印象）

| 棋子 | 怎麼叫 | 適合 | 注意 |
|------|--------|------|------|
| 主 session（Opus） | 就是你自己 | 判斷、整合、跟老闆對話、寫最終結論 | 你的 context 是最貴的資源，別拿去掃檔案 |
| `Explore` subagent | Agent tool, subagent_type=`Explore` | 唯讀搜索：找檔案 / 符號 / 慣例，跨多檔回答「在哪裡、長怎樣」 | 唯讀、不能改檔；它讀片段、適合定位不適合深審 |
| `Plan` subagent | Agent tool, subagent_type=`Plan` | 設計實作方案、列關鍵檔案與取捨 | 唯讀；產出是計畫不是程式 |
| `general-purpose` subagent | Agent tool, subagent_type=`general-purpose` | 多步驟執行：實作、批次改檔、跑測試回報 | 全工具；派工三件套必須齊 |
| model 降級 | Agent tool 的 `model` 參數：`haiku` / `sonnet` / `opus` | 機械工作降 haiku/sonnet 省成本 | Agent tool **沒有** per-call effort 參數；要固定 effort 就在 `.claude/agents/*.md` 定義專用 agent（frontmatter 設 model/effort） |
| codex（外部血統） | Bash 直呼（見 §4） | 對抗式審查、第二實作意見、卡死救援 | 不同模型家族 = 不會跟你犯同款錯；**必用 Bash 直呼、不走 codex-rescue agent**（sandbox flag regression 會卡死） |
| Workflow tool | 需使用者明講才可用（如「用 workflow」/「ultracode」） | 大規模 fan-out（審查面、遷移面） | 別自作主張啟用；一般開發 Agent tool 夠用；部分 harness 版本沒有此工具、沒有就當沒有 |

**禁手**：併發 `claude -p`（每個進程複製整套 MCP、~130MB/份、實測凍死 8GB WSL）。要平行就用 Agent tool subagent（0 OS 進程開銷）。單發 `claude -p` 要砍 MCP：`--strict-mcp-config --mcp-config '{"mcpServers":{}}'`。

## 2. 什麼任務派給誰（查表，別即興）

| 任務型態 | 派給 | model |
|----------|------|-------|
| 「X 在哪裡定義 / 有哪些呼叫點」 | Explore | sonnet（預設）；範圍大再開多隻平行 |
| 讀懂一個子系統、回結構化摘要 | Explore 或 general-purpose | sonnet |
| 已知模式的機械套用（改 N 個呼叫點、批次 rename） | general-purpose | sonnet；模式是你解出來的、附一個完整範例 |
| 新功能實作（有既有慣例可循） | general-purpose | sonnet 起步；卡了升 opus（見 §5） |
| 新功能實作(跨模組/安全相關/floor/escalation/gate) | 自己做或 general-purpose(opus) | opus；完成後必過 codex 審 |
| 架構決策、trade-off | Plan（opus）+ 你自己判斷 | opus |
| 審查 / 驗收 | fresh general-purpose + codex | 見 §6 |
| 網頁研究、官方文件查證 | general-purpose（給明確問題清單） | sonnet |

單一事實、已知檔案的單點查看：主對話直接 Read/Grep，**不要**為一行資訊開 agent（過度派工也是浪費）。

## 3. 派工三件套（每次派工的最低要求）

1. **目標與動機**：做什麼 + 為什麼（動機讓 subagent 在邊界情況做對取捨）。
2. **驗收條件**：可機械檢查的清單（「測試 X 綠」「回傳每個檔案的 檔:行」「不碰 Y 目錄」）。
3. **回報格式**：只回結論與 `檔:行`；長產物（diff、報告、log）落檔傳路徑，不要貼全文。

加上**範圍圍欄**：明說不可以動什麼（「不改測試斷言」「不碰 master」「不寫 dogfood DB」）。subagent 沒有你的對話脈絡，圍欄不寫等於沒有。

## 4. codex 直呼規約（外部第二意見）

```bash
# prompt 寫到 scratchpad 檔，輸出 redirect 到檔，背景跑
codex exec --dangerously-bypass-approvals-and-sandbox -m gpt-5.4 \
  < /path/to/prompt.txt > /path/to/out.txt 2>&1
```
- fresh-thread 原則：`codex exec` 每次都開新 thread、不要沿用舊 thread（會卡）；prompt 必須自含全部脈絡。
- prompt 結尾要求精簡輸出格式：「逐點 confirmed / 有問題（嚴重度 + 檔:行 + 場景 + 最小修法）；全部沒問題就明講『無 actionable finding』；不要客套」。
- 讀結果：`tail` / `grep` 出結論段，別整檔進主對話。
- 收斂標準:codex 最新一輪零 actionable finding = READY（一輪乾淨即可、不需連續多輪）。對 codex 的 finding 也要驗證（它有 false positive 實績,見 `00-diagnosis.md` 第三名的 F-P0-4 案例）:先跑測試證實,再改。

## 5. 升降級路徑（照走，不要自己發明）

- **haiku 錯一次** → 直接升 sonnet 重派（不要 haiku 重試第二次）。
- **sonnet 同一子任務連錯兩次** → 帶**完整失敗軌跡**（兩次的 prompt、輸出、錯在哪）升 opus。失敗軌跡是升級最有價值的 payload,別只丟原始任務。
- **解出模式後** → 把模式寫成「一個完整範例 + 邊界清單」降回 sonnet 批次套用。
- **同一件事最多重試兩輪**（不分 model）→ 第三輪前必須換路：換方法、換工具、或按 `20-judgment-rubrics.md` §4 判斷是否方向錯了、§3 判斷是否該問使用者。

## 6. 驗證不自驗（驗收規約）

- **檔案類產出**：派 fresh-context agent read-back——只給它檔案路徑 + 驗收問題清單，**不給它你的結論**，讓它獨立回答「檔案存在嗎、內容涵蓋 X 嗎、與 Y 檔矛盾嗎」。
- **程式類產出**：跑測試或實跑。本 repo 全量回歸：`.venv/bin/python3 -m pytest mcp-servers/business-db/tests/ -q`；輸出落檔、主對話只看失敗清單。「測試都綠」的宣稱必須附測試輸出的數字（幾 passed）。
- **高風險判斷**（安全邊界、floor/gate/escalation、時限引擎、資料遷移）：加 codex 對抗審(§4)，或多答案評審選優（兩個 agent 獨立解、第三個 fresh agent 比較選優）。
- 驗收 agent 的回報若與做事 agent 的宣稱衝突 → **信驗收**，把衝突當 finding 處理。

## 7. 本 repo 環境 gotchas（派工前掃一眼）

| Gotcha | 規則 |
|--------|------|
| 改 `mcp-servers/business-db/` 程式 | MCP server 是既有進程,改完必須重啟 session 或 `/mcp` reconnect 才載新碼；不重啟=測到舊碼 |
| 改 `mcp-servers/line-channel/` | 必 `pkill` 舊 webhook owner 再重啟,否則舊進程還握著 webhook |
| Skill 觸發 eval | 用 `~/.claude/skills/skill-creator-advanced/scripts/run_eval.py`;跑前 `env -u ANTHROPIC_API_KEY`(走訂閱);必砍 MCP(`--strict-mcp-config`)否則凍 WSL;偵測「真 Skill 呼叫名」、Read 檔案不算觸發 |
| 產品行為驗證 | `data/business.db` 是 dogfood **真實營運資料**、dev 絕不寫;驗證行為用 scratch DB(`SME_DB_PATH` 另指、如 `/mnt/d/pm-scratch/` 下自建) |
| git 推送 | 律所線→`legal-admin`、通用線→`master`,兩線永不 merge;**push 前先問使用者**(commit 可以,push 要授權) |
| `docs/` | default-ignore、只有白名單通用檔進 git;新檔放 docs/ 不要主動 git add |
| CLAUDE.md | 改它 commit 時 pre-commit hook 自動同步 AGENTS.md(需 `git config core.hooksPath .githooks`);別手改 AGENTS.md |
| WSL 記憶體 8GB | 禁併發 `claude -p`;大量平行工作用 Agent tool |

## 教訓登記簿（本檔自身的）

（尚無。格式與升正文規則見 `40-maintenance.md` §3、§4。）
