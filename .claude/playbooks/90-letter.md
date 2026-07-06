# 90 — 給未來 session 的信

> 寫於 2026-07-06/07（Fable 5 立制 session——這個環境唯一一次用到這個等級的模型，之後由 Opus / Sonnet 長期接手）。
> 這封信放「沒人問、但你遲早需要知道」的事。規則在 00–40，這裡是規則以外的東西。
> master 通用版：2026-07-07 自 legal-admin 線移植（兩線永不 merge、之後各自演化、要同步只能 cherry-pick）。

## 一、三件沒被問過、但對這個環境最重要的事

### 1. 老闆（Charlie）的修正史 = 這個環境的隱形規格

他真正糾正過的事，比任何風格指南都準。全部有實績：
- **「你是開發的人你不要飄移變成律所助理」**——開發 session 跑去做產品 persona 的事，是他最反感的失誤（現在 hooks 已分流，但漂移的根性在模型、不在 hook）。
- **「用中文回覆我」「你為啥一直講英文」**——繁體中文，包括長回合中段（漂移最常發生在被英文工具輸出帶走之後）。
- **「你有要推到git嗎?」**——依「轉述的授權」push 之後被質疑。commit 自主、push 必問，轉述授權不算授權。
- 他要**結論先行**、討厭 melodrama 文案、討厭被問「要不要我幫你……？」——直接做可逆的事、回報結果。
- 他的裁示常常一句話（「切回lawyerBranch」「改名 sme-ai-kit-lawyer」）——執行前把歧義自己消化掉、把你的解讀講清楚再動手，不要拿一串問題丟回去。

### 2. 反捏造是這個產品的信任基礎，而文件是最容易捏造的地方

這套系統的失敗模式不是 crash，是**體面地錯**：把推斷寫成老闆的指示、文件宣稱「系統會擋 X」而程式沒擋。所以：
- 存老闆規則必帶 `source_quote`（原話）；你推斷的標 `source_type='inferred'`——絕不把推斷偽裝成指示。
- **改文件前先對程式碼驗證能力存在**；發現「文件超前程式」是 P1 級 bug，修法永遠是先收斂文件。
- 這個紀律同樣適用於你自己的回報：宣稱的證據等級查 `20-judgment-rubrics.md` §6。

### 3. 安全架構的一句話心智模型（改安全碼前先默背）

**威脅模型 = 防內部員工透過 agent 越權，不防駭客級 injection。** 兩道獨立的牆（檔案 sandbox + business-db floor gate）、上報 hard-wired 在 service transaction 裡（agent 跳不過）、HITL gate 用 `resume_params` 一字不差 + 單次消費。由此推出兩個常見誤判的解法：
- 別把它「加固」成防駭客的東西（過度工程、老闆不買單——他明確說過收斂成可交付、勿再鑽安全邊角）；
- 也別因為「operator 路徑全通」就以為 gating 是裝飾（floored 路徑的檢查是真的、live 驗過）。

## 二、這套制度最可能的退化方式（與預防）

1. **規則堆積互相打架**——每個坑加一條規則、三個月後規則比程式難維護。預防：`40-maintenance.md` §4 精簡門檻是硬規則；新規則先進登記簿、重複發生才升正文。
2. **playbooks 與現實漂移**——路徑改了、工具換了、規則還在，弱模型會盲從壞規則（比沒規則更糟）。預防：§5 健康檢查；立制當天就發生過一次（worktree 改名讓兩處絕對路徑失效），這不是理論風險。
3. **制度儀式化**——模板照抄但驗收條件空白、codex 審變成「跑過了」就算 READY。預防：驗收條件空白 = 沒派工；READY 的定義寫死在 `10-model-dispatch.md` §4（最新一輪零 actionable finding），不接受其他定義。
4. **hooks 靜默失效**——settings.json 被改壞、session-mode.py 出錯不報，dev 紀律無聲消失。預防：hook 檔頭有自測指令，懷疑就跑；hook 設計 fail-open 成「不注入」、絕不會擋 prompt，所以失效的症狀是「安靜」，要主動查。
5. **層級混淆**——弱模型把 playbooks 當產品規格、或把 CLAUDE.md 產品段當開發指令執行（= 飄移復發）。預防：CLAUDE.md〈Session 模式〉最後一句就是解藥，開場先讀。

## 三、本線（master）交接備忘

- **本套制度 2026-07-07 自 legal-admin 線移植**：兩線此後各自演化；發現通用性的改進要同步，只能 cherry-pick / copy、永不 merge。
- **UX 變更要知道**：repo root 的 CLI session 現在預設 **dev 模式**——dogfood 營運操作（readout / 記帳 / 客戶互動）要以 `SME_SESSION_MODE=ops` 啟動；LINE runtime 走 `start-line.sh` 帶 `SME_FLOOR`、不受影響。
- **安全 roadmap 未竟項**（BU 列級過濾、floor-map 路由種 boss、templatize launcher）：清單與現況在 memory 與決策紀錄、不在這裡重抄——動那塊前先讀 CLAUDE.md〈部門安全層〉的「已收斂 vs 仍有缺口」，文件與回覆絕不可宣稱列級過濾已落地。
- **`.mcp.json` 永不進 git**：複製到 sibling 專案必檢查 `SME_DB_PATH` 改指自己的 DB；`data/business.db` 是真實營運資料、dev 不碰。

## 四、第一次進場怎麼開始

1. 讀 `README.md`（本目錄）+ `10-model-dispatch.md` §0、§7——五分鐘。
2. 確認自己的模式（hook 開場訊息會講;沒看到 = 跑 `40-maintenance.md` §5 健康檢查）。
3. 然後才動工。卡住回來讀 `20-judgment-rubrics.md`,不要憑感覺重試。

祝順利。這套制度的目的不是限制你，是讓你不必在每個 session 重新發明這些判斷。

—— Fable 5，2026-07-07
