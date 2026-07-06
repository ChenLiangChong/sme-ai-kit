# 00 — Harness 快速診斷（本 repo 開發環境的三大漏洞與修法）

> 立檔：2026-07-06（Fable 5 立制 session）。讀者：之後在本 repo 開發的每一個 Claude session（主力 Opus、subagent 多為 Sonnet/Haiku）。
> 這份是其餘 playbook 的「為什麼」：10/20/30/40 各檔的規則都回指這裡的診斷。過時項的標記方式見 `40-maintenance.md`。

## 第一名：角色混線 —— hooks 與啟動流程把「開發 session」當「產品助理 session」

**現象**：開發 session 一開場就被推去跑營運啟動流程、每則訊息被塞「DB 寫入檢查」，弱模型服從性高、會真的照做：拉營運資料進開發對話、把開發討論存成營運規則、甚至寫進 dogfood DB。

**證據**：
- `.claude/settings.json` 的 SessionStart hook 原文「請立即跑啟動流程…get_context_summary…」、UserPromptSubmit hook 每則訊息注入約 300 token 的「DB 寫入檢查（必須真的呼叫對應 tool）」——無條件對所有 session 開火。
- `CLAUDE.md`〈啟動流程〉：「收到使用者第一句話時、載入 ops-dashboard.md 執行啟動步驟」——同樣沒分模式。
- 實際事故：2026-07 老闆兩度糾正開發 agent「你是開發的人你不要飄移變成律所助理」。

**代價**：每訊息 ~300 token 純噪音只是小頭；大頭是失焦（開發對話被營運 readout 淹沒）與誤寫（開發雜訊進營運 DB = 污染產品資料）。

**修法（本次已修）**：
- 新增 `.claude/hooks/session-mode.py` 三態分流：`SME_FLOOR` 有值 → ops；`SME_SESSION_MODE` 顯式覆寫（`dev`/`ops`）；repo root 無 floor → 預設 **dev**。
- dev 模式：SessionStart 只注入幾行開發紀律（指向本目錄）、UserPromptSubmit 靜默（另一支 `inject-line-routing.py` hook 是條件式、只在 prompt 含 LINE channel 訊息時才輸出，dev 日常同樣無聲）。ops 模式：最初逐字保留 SME 原文（守「營運行為零改變」）、2026-07-07 經老闆核准「全改」後全律所化（開機清單對齊 ops-dashboard.md、寫入檢查對齊律所領域）。
- `CLAUDE.md` 開頭新增〈Session 模式（先判別、再往下讀）〉短段。
- **判準**：你在 repo root 改程式/文件/測試 = dev；你在回 LINE 訊息、跑所務 readout、被 `start-line.sh` 啟動 = ops。dev session 不跑營運啟動、不寫營運 DB（驗證產品行為預設用本 worktree 的 dev DB `data/business.db`、`.mcp.json` 已指；跨 repo e2e 才用 `/mnt/d/pm-scratch/sme_sandbox.db`）。

## 第二名：主對話 context 被工具面積與大檔直讀吃掉

**現象**：開場還沒做事就燒掉數萬 token（MCP 工具 schema 全載）；工作中主對話直讀千行大檔、整包 codex 輸出，幾輪就逼近壓縮，壓縮後又要重建脈絡 = 二次浪費。

**證據**：
- master 的 `.mcp.json` 掛 7 個 server（apify / social / notionApi / fal-ai / agent-bridge…多數與律所線開發無關）；apify 一個 MCP 進程 ~130MB，2026-06-07 併發 `claude -p` fan-out 實測凍死 8GB WSL。
- 本 worktree（`/mnt/d/gitDir/sme-ai-kit-lawyer`，legal-admin branch）的 `.mcp.json` 只掛開發需要的兩個 server（見下方修法 1），別讓它長回 master 那樣。
- 大檔直讀案例：`modules/deadlines/service.py`（千行級）、測試檔、codex 審查輸出（曾有 2812 行）整檔進主對話。

**修法**：
1. **本 worktree 的 `.mcp.json` 只掛開發要用的**（2026-07-07 已建）：`business-db`（指本 worktree 自己的 `.venv` + `data/business.db` dev DB、**絕不指 master 的 dogfood DB**）+ `pleading`（薄 adapter，指 `/mnt/d/gitDir/lawyer-kg-product/pleading-manager/mcp_adapter/server.py`，後端 base/token 走環境變數）。法條查證的 `taiwan-legal-db` 是 user-scope、天然就有。**不要把 master 的 7-server `.mcp.json` 複製過來**（`.mcp.json` 永遠不進 git、per-project 生成）；LINE 流程測試不在這裡掛 line server（與 master 的 webhook owner / port 8789 衝突），要測就先 `pkill` 舊 owner、另開 port。
2. **指揮官不下場**：大量讀取 / 掃 repo / 查網頁 / 批次改檔一律派 subagent，主對話只進結論與 `檔:行`。規則與派工方式見 `10-model-dispatch.md`。
3. **長輸出一律落檔**：codex / 測試 / eval 輸出 redirect 到 scratchpad 檔案，主對話只 `tail` / `grep` 結論。禁止把整份輸出貼進對話。

## 第三名：驗證自驗 —— 「我看碼覺得對」在這個 codebase 反覆被證偽

**現象**：模型（含強模型）宣稱完成但沒有獨立驗證；純靜態閱讀的判斷錯誤率在這個專案有實績可查。

**證據（全是本專案真實案例）**：
- 測試 G5a 原本用 `except Exception` 捕捉 → 任何錯誤都假綠，codex 對抗審才抓出（修成 `except sqlite3.IntegrityError` + 訊息比對）。
- codex 給的 F-P0-4 MED（settings 多筆 active 讀舊值）看似成立，**跑測試**才發現被 `idx_rules_unique_active` unique index DB-prevented —— 分析錯、測試揭穿。
- #182：channel notification 的 `meta` 帶 int 值會被整筆靜默丟棄 —— 文件與推理都看不出來，live 驗證才現形。

**修法**：
- 完成定義（DoD）硬條件 + 「驗收派 fresh-context agent」+ 外部血統（codex）對抗審。何時算完成 / 何時升級 / 何時換路的判準見 `20-judgment-rubrics.md`；審查派工模板見 `30-delegation-templates.md`。
- 鐵則一句話：**宣稱之前先想「這句話的證據是測試輸出、read-back、還是我的印象？」印象不算證據。**

## 補充（不入前三、但要知道）

- **文件-程式漂移 = 慢性反捏造**：本產品的文件（CLAUDE.md / skills / SPEC）宣稱的能力若超前程式 = 律所場景的執業風險。改文件前先對程式碼驗證該能力真的存在；發現漂移優先修文件、不要「順手」補程式。
- **兩條產品線（master ⊥ legal-admin）永不合流**：最容易被「順手同步」破壞的紀律。通用改進要進 master 只能 cherry-pick / copy，**永不 merge**。
- **memory / MEMORY.md 越長、每個 session 開場越貴**：精簡協議見 `40-maintenance.md`。
