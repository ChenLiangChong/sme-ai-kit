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

- **F-P2-WIN-1 產品層修正（2026-07-07 Windows e2e、marketing ledger 同步）**：①
  onboarding 導入訪談（knowledge-capture）沒有引導律師綁 pleading 整合 token
  （`bind_pleading_token`）→ vault 無憑證、回寫靜默跳過——導入流程該加一步「若有裝
  pleading，現在綁 token」。② `pleading_writeback` 在「`PLEADING_API_BASE` 已配置
  但該律師無 token」時連 `interaction_log` 都不記＝靜默失敗（純未配置的 inert 靜默是
  對的、但「配了一半」該留一行 log 供排查）。兩條都是 post-run 修正、勿在 e2e 中途改碼。
- **F-P2-WIN-2 產品層修正（🔴 去識別化邊界、碼證確認）**：`pleading_writeback` 的
  `_DEADLINE_FIELDS` 把 `trigger_event`（自由文字）verbatim 送進 pleading——`title` 有
  結構性去識別化（`type_label`）、`trigger_event` 沒有，operator 在裡面寫對造名（「沅泰
  物流」）就直通洩漏。修法：回寫邊界對 `trigger_event` 過 `screen_calendar_text` 同款
  當事人名 gate（比對 matter 欄位、命中→以 type 衍生的泛稱替換、同 `_safe_title` 哲學）；
  `calc_trace` **已證實**逐字內嵌 statutory_basis 等自由文字（案C 法院名第二藏身處、
  案A/B 乾淨純屬運氣）——gate 欄位定案清單＝`trigger_event`＋`statutory_basis`＋
  `calc_trace`＋新欄 default in-scope。誠實邊界同 #6c：只擋得住已知當事人名／法院名、
  不宣稱擋任意 PII。post-run 修。
  縱深第二道（pleading 側、pleading_coder1 提、需兩側同步版本）：pleading API 對
  source=sme_engine 寫入把 `trigger_event` 收斂成受控字彙＋結構欄＝「去識別化靠紀律」
  變「schema 上不可能」。（原疑慮「audit/版本史留含 PII 舊 payload」經停機審證實不存在。）
- **F-P3-WIN-1 產品層修正（mark_filed 對 needs_review 無警示＋無 un-file 路徑）**：
  碼證＝`mark_deadline_filed` 只查存在/機密軸/status=pending/actor，**不看
  `needs_manual_review`**；文件明寫「覆核≠遞交、兩事件分明」＝gate 從未被設計或宣稱
  （非 regression、非文件捏造，是 e2e 挖出的真設計課題）。風險：教示不符未覆核的
  時限被標 filed → 提醒靜默熄燈。修法候選：(a) filed 時該筆仍 needs_review → 工具
  輸出大聲警語＋interaction_log 記「遞交時尚未覆核」（**全擋 vs 警示由老闆定**——
  全擋會擋住「真的已遞交」的事實登記、我傾向警示+留痕）；(b) **un-file 修正路徑**
  （具名+audit+上報主持律師），與 redact 同族＝「不可逆狀態轉換缺修正路」。
- **部署完整性（Windows e2e 案C 順帶暴露）**：正式部署的 `.mcp.json` 該不該掛
  `taiwan-legal-db`（法條查證 MCP、PyPI 可裝）？e2e 部署沒掛、產品誠實回「無法自動查證
  法條」走 court_set+覆核＝行為正確，但接了可讓答辯期等非種子型別自動附法源。裝法：
  pip 進部署 venv + `.mcp.json.win-template` 加 entry。由老闆決定要不要進標準部署包。
- **F-P2-WIN-2 擴大（statutory_basis 含法院名）**：court_set 的 `statutory_basis` 寫了
  「臺灣臺中地方法院」並 verbatim 回寫——去識別化契約列法院名 in-scope。修法（marketing
  設計裁示）：**所有回寫自由文字欄過同一道 gate、新欄 default in-scope**（trigger_event／
  statutory_basis／未來新增欄），不做逐欄打地鼠；當事人名→泛稱、法院名→「法院裁定」。
  **加做補救路徑**（e2e 實測 operator 無法事後清 PII：amend 刻意只收計算輸入、
  statutory_basis 工具不可改、無 delete＝稽核永存設計）：出一支具名+audit 的
  `redact_deadline_field`（或 amend 加受控參數）改寫自由欄→冪等重回寫覆蓋 pleading 列；
  pleading 版本史殘留舊 payload 歸停機審裁定。本輪測試資料 #2/#4（marketing 最終裁示、
  取代先前「留展品」版）：由 pleading 的**律師編輯路徑**（PUT /api/deadlines/{id}、合法
  產品路徑）清兩列的 trigger_event/statutory_basis；**凍結規則＝邊界修好前 sme 側
  deadline #2/#4 不得再觸發任何回寫**（六個 hook 點任一都會把 sme 原文全量覆寫回去＝
  PII 復發；「時效中斷」情境若要跑要先上 bridge 問）。finding 維持 🔴 OPEN（邊界 gap＋
  sme 工具層無逃生門都是實錄）。停機審（雙人獨立 immutable 讀）已結案：**清洗前 PII
  payload 快照在 pleading audit_log 不存在**（audit summary 不內嵌欄位 payload）＝
  歷史殘留議題 moot、無需清。
- **F-P2-WIN-3（🟡 title fallback 吐生代碼）**：`_GENERIC_TYPE_LABELS` 只有
  `answer`/`brief`，operator 用了 `answer_civil` → fallback「法定期限（answer_civil）」
  ＝零 PII 但使用者可見醜代碼。**性質＝coverage 非 regression**（round-1 修的是
  `answer`、`answer_civil` 是新代碼）。修法候選：擴 map + `create_deadline` 對
  unmapped type 回警示建議已標籤代碼（引導收斂字彙、勿讓自由 type 字串增生）；
  marketing 設計裁示：**枚舉全量 type 做映射＋「缺 label 即測試紅」的 fallback 測試**、
  不要一個 type 一個 type 補。

- **legal-admin CLAUDE.md 的決策編號清理**：機制段還留著 #166/#173/#27/#182 等指向 dogfood DB 的編號，客戶部署看不懂。master 已做過同樣清理（commit `58c23c1`）可當範本。低風險、機械性，適合派 sonnet + read-back。
- ~~hooks ops 文字的律所化~~ / ~~inject-line-routing.py 的 SME 路由文字~~：**已完成（2026-07-07，老闆核准「全改」）**——session-mode.py 的 ops 開機清單改對齊 ops-dashboard.md（掃描器哨兵 / 待確認到期日 / 即將到期時限）、寫入檢查改律所領域（時限走收件抽取、絕不心算）；inject-line-routing.py 改所內名冊二分路由 + 判決書收件抽取、刪陌生人行銷路由。SME 原文在 git 歷史（9beffcd 之前）。
- ~~playbooks 是否複製到 master~~：**已完成（2026-07-07 老闆「通用的切過去補一個」）**——master `6289034` 通用版（pytest 入口、dev DB 紀律反轉、去律所專屬項）。兩線此後各自演化、同步只能 cherry-pick。
- ~~Windows 實機部署階段~~：**已執行（2026-07-07 Windows e2e）**——`D:\gitDir\sme-pleading-e2e\` 攤平部署（產品 CLAUDE.md 在根、settings env 設 SME_SESSION_MODE=ops、.mcp.json 指 e2e DB）；P0–P6 全跑完、findings 見上方。留給正式客戶部署的教訓：hooks 指令要 Windows 原生寫法（py -3.12 + 絕對路徑 + argv 顯式模式）、曆表匯入與 watchdog cron 要進安裝清單、老闆 LINE id 要在 onboarding 設。
- **pleading 側**：`PLEADING_DB_PATH` 進 pleading production repo 的 commit 仍 HOLD 等老闆點頭（那是另一個 repo、另一位負責，不是這邊的事，但別誤以為漏做）。
- **本 worktree `.mcp.json` 的 pleading token**：`PLEADING_SESSION_TOKEN` 留空等老闆從 GUI 產生後以環境變數帶入;祕密永遠不進 git / bridge / KB。

## 四、第一次進場怎麼開始

1. 讀 `README.md`（本目錄）+ `10-model-dispatch.md` §0、§7——五分鐘。
2. 確認自己的模式（hook 開場訊息會講;沒看到 = 跑 `40-maintenance.md` §5 健康檢查）。
3. 然後才動工。卡住回來讀 `20-judgment-rubrics.md`,不要憑感覺重試。

祝順利。這套制度的目的不是限制你，是讓你不必在每個 session 重新發明這些判斷。

—— Fable 5，2026-07-07
