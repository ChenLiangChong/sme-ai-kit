# 90 — 給未來 session 的信

> 寫於 2026-07-06/07（Fable 5 立制 session——這個環境唯一一次用到這個等級的模型，之後由 Opus / Sonnet 長期接手）。
> 這封信放「沒人問、但你遲早需要知道」的事。規則在 00–40，這裡是規則以外的東西。

## 一、三件沒被問過、但對這個環境最重要的事

### 1. 老闆（Charlie）的修正史 = 這個環境的隱形規格

他真正糾正過的事，比任何風格指南都準。全部有實績：
- **「你是開發的人你不要飄移變成律所助理」**——開發 session 跑去做產品 persona 的事，是他最反感的失誤（現在 hooks 已分流，但漂移的根性在模型、不在 hook）。
- **「用中文回覆我」「你為啥一直講英文」**——繁體中文，包括長回合中段（漂移最常發生在被英文工具輸出帶走之後）。
- **「你有要推到git嗎?」**——依「轉述的授權」push 之後被質疑。commit 自主、push 必問，轉述授權不算授權。
- 他要**結論先行**、討厭 melodrama 文案、討厭被問「要不要我幫你……？」——直接做可逆的事、回報結果。
- 他的裁示常常一句話（「切回lawyerBranch」「改名 sme-ai-kit-lawyer」）——執行前把歧義自己消化掉、把你的解讀講清楚再動手，不要拿一串問題丟回去。

### 2. 反捏造是這個產品的命，而文件是最容易捏造的地方

律所 vertical 的失敗模式不是 crash，是**體面地錯**：時限天數心算錯一天 = 執業過失;文件宣稱「系統會擋 X」而程式沒擋 = 客戶以為有保護。所以：
- 法條 / 天數只能來自 `taiwan-legal-db` 查證 + 引擎輸出（附 `statutory_basis`）。
- **改文件前先對程式碼驗證能力存在**；發現「文件超前程式」是 P1 級 bug，修法永遠是先收斂文件。
- 這個紀律在 CLAUDE.md 裡叫「反捏造」，但它同樣適用於你自己的回報：宣稱的證據等級查 `20-judgment-rubrics.md` §6。

### 3. 安全架構的一句話心智模型（改安全碼前先默背）

**威脅模型 = 防所內員工透過 agent 越權，不防駭客級 injection。** 兩道獨立的牆（檔案 sandbox + business-db floor gate）、上報 hard-wired 在 service transaction 裡（agent 跳不過）、HITL gate 用 `resume_params` 一字不差 + 單次消費。由此推出兩個常見誤判的解法：
- 別把它「加固」成防駭客的東西（過度工程、老闆不買單——他明確說過收斂成可交付、勿再鑽安全邊角）；
- 也別因為「operator 路徑全通」就以為 gating 是裝飾（floored 路徑的檢查是真的、live 驗過）。

## 二、這套制度最可能的退化方式（與預防）

1. **規則堆積互相打架**——每個坑加一條規則、三個月後規則比程式難維護。預防：`40-maintenance.md` §4 精簡門檻是硬規則；新規則先進登記簿、重複發生才升正文。
2. **playbooks 與現實漂移**——路徑改了、工具換了、規則還在，弱模型會盲從壞規則（比沒規則更糟）。預防：§5 健康檢查；立制當天就發生過一次（worktree 改名讓兩處絕對路徑失效），這不是理論風險。
3. **制度儀式化**——模板照抄但驗收條件空白、codex 審變成「跑過了」就算 READY。預防：驗收條件空白 = 沒派工；READY 的定義寫死在 `10-model-dispatch.md` §4（最新一輪零 actionable finding），不接受其他定義。
4. **hooks 靜默失效**——settings.json 被改壞、session-mode.py 出錯不報，dev 紀律無聲消失。預防：hook 檔頭有自測指令，懷疑就跑；hook 設計 fail-open 成「不注入」、絕不會擋 prompt，所以失效的症狀是「安靜」，要主動查。
5. **層級混淆**——弱模型把 playbooks 當產品規格、或把 CLAUDE.md 產品段當開發指令執行（= 飄移復發）。預防：CLAUDE.md〈Session 模式〉最後一句就是解藥，開場先讀。

## 三、未完成項目交接（立制 session 沒做完 / 刻意不做的）

- **legal-admin CLAUDE.md 的決策編號清理**：機制段還留著 #166/#173/#27/#182 等指向 dogfood DB 的編號，客戶部署看不懂。master 已做過同樣清理（commit `58c23c1`）可當範本。低風險、機械性，適合派 sonnet + read-back。
- **hooks ops 文字的律所化**：`session-mode.py` 的 ops 文字沿用 SME 用語（「老闆原話」「庫存異動」「收支金額」），與律所 branch 不搭、且其開機清單（low_stock_alerts / check_overdue）與 CLAUDE.md〈啟動流程〉律所守則（待確認到期日 / 時限 / 掃描器健康）是兩份不同清單。**刻意逐字保留**（本次改動守「營運行為零改變」）；要改 = 營運行為變更，先問老闆。
- **`inject-line-routing.py` 的 SME 路由文字**：這支 UserPromptSubmit hook 對含 LINE 訊息的 prompt 注入「陌生人依意圖路由通知負責人」「對外行銷先 create_approval」等 SME 流程，與本 branch CLAUDE.md「不做對外行銷、不做陌生人意圖分層路由」直接矛盾。同屬營運行為變更，要改先問老闆。
- **playbooks 是否複製到 master**：這套制度是通用的，但兩線永不 merge——要過去只能 copy。等老闆裁示。
- **Windows 實機部署階段**（老闆已預告）：目標 = Claude Desktop code tab + 自包含 sme 專案資料夾（含自己的 CLAUDE.md）。部署時記得：`.mcp.json` per-project 重生成、`SME_DB_PATH` 指自己、hooks/settings 隨資料夾走。
- **pleading 側**：`PLEADING_DB_PATH` 進 pleading production repo 的 commit 仍 HOLD 等老闆點頭（那是另一個 repo、另一位負責，不是這邊的事，但別誤以為漏做）。
- **本 worktree `.mcp.json` 的 pleading token**：`PLEADING_SESSION_TOKEN` 留空等老闆從 GUI 產生後以環境變數帶入;祕密永遠不進 git / bridge / KB。

## 四、第一次進場怎麼開始

1. 讀 `README.md`（本目錄）+ `10-model-dispatch.md` §0、§7——五分鐘。
2. 確認自己的模式（hook 開場訊息會講;沒看到 = 跑 `40-maintenance.md` §5 健康檢查）。
3. 然後才動工。卡住回來讀 `20-judgment-rubrics.md`,不要憑感覺重試。

祝順利。這套制度的目的不是限制你，是讓你不必在每個 session 重新發明這些判斷。

—— Fable 5，2026-07-07
