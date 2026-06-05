# legal-admin 產品規格（精簡定案版）

> 2026-06-03 與老闆逐輪收斂後定案。**此檔為權威規格**；同目錄 `00-vertical-blueprint.md` / `01-deadline-engine.md` / `99-research-appendix.md` 是原始研究與時限引擎技術細節，**範圍已大幅收斂**，僅當參考（時限計算的法律細節仍以 `01` 為準）。

## 定位

**事務所內部用的 LINE 法務行政秘書。** 單一律所、不做多事業體、無對外通道（LINE 只給所內律師/助理用，不接客戶對話、不做陌生人路由、不做對外行銷）。需求本質是**行政**，不是法律問答。

## 核心 loop（四個動作）

1. **丟檔案** — 律師/助理在 LINE 傳判決書／裁定／開庭通知（照片或 PDF）→ AI 讀檔，抽出 **送達日 + 文書類型** → 時限引擎算出 **法定期限 + 內部期限（法定−緩衝）**。
2. **一鍵確認才入** — AI 抽取結果推回 LINE 給律師/助理確認（送達日對不對、是上訴還是抗告、可改）→ **確認後**才寫入。理由：律師業算錯期限 = 執業過失，人必須擋在中間，不全自動。
3. **寫兩處 + 每日彙整**
   - 寫入 **內部 `deadlines` 表**（系統帳本：`calc_trace` 計算軌跡 + `statutory_basis` 法條依據 + 法定/內部雙日期 + 狀態 pending/filed）。
   - 寫入 **事務所慣用的行事曆**（優先 Google Calendar）：把確認後的期限/庭期建成 event。
   - **每天固定時間**：cron **讀那本慣用行事曆**當天/近期事件（涵蓋我們寫的 + 他們手動加的）+ 交叉我們 `deadlines` 表補法條/雙日期 → `claude -p` 彙整「今日工作事項」→ LINE 推 **全所一份**。
4. **隨時查** — 自然語言（人名／案號／當事人）→ 直接查到案件、期限、行事曆。

## 不做（移出產品，客戶現場真要再客製）

記帳/會計、計時計費、信託帳、利益衝突檢查、對外客戶通道、陌生人路由、對外行銷 HITL。
當事人（parties）只需「名字能被查到」的輕量程度，不做完整 CRM。

## 行事曆整合（關鍵外部依賴）

- **source of truth = 事務所慣用的行事曆。現場第一件事 = 確認他們實際用什麼**（Google Calendar？其他軟體？紙本/白板？）。
- 若 **Google Calendar**：建小型 GCal client（用**該所自己的** Google 帳號，OAuth 或 service account），供 cron + 確認流程讀寫。
  - ⚠️ 注意：開發環境若連到的是開發者個人 Google Calendar、**不是該律所的帳號**，不能拿來測真實流程；客戶端必須接律所自己的 Google 帳號（OAuth／service account）。
- 若**沒有數位行事曆**：退回「系統內建行事曆」+ 選配同步到 Google。
- 行事曆整合做成**可插拔 adapter**：核心（文件→抽取→確認→deadlines 表→查詢→每日彙整推 LINE）**不依賴**特定行事曆，現場確認用什麼再接 adapter。

## 隱私設計（標準檔起步、每層可升級）

律師有保密義務，隱私是本 vertical 的一級設計約束。核心原則：**身分與內容留本地，外部只給「時間 + 代號」。** 資料流經四方：本地 `business.db`（最安全）/ Google Calendar / LINE(LY Corp) / Anthropic(Claude)。

**標準檔（定案、預設）：**
1. **訓練關閉（必做、不可省）**：Claude 訂閱（Free/Pro/Max）預設可能拿對話訓練模型並保留 5 年；必須關「Help improve Claude」→ 變成不訓練 + 30 天保留。訂閱方案拿不到 ZDR（零保留需 Enterprise、成本跳級，與走訂閱省成本衝突），故靠下面「去識別 + 最小化」補。
2. **本地優先**：案件帳本（matters/deadlines/當事人對照）只存事務所自己機器/NAS，不進 SaaS 雲。＝對比 Clio 全雲端的賣點。
3. **行事曆去識別化**：寫進 Google/外部行事曆的 event 只放「案件代號 + 期限類型 + 日期」（如「M-2026-013 上訴期限」），**不放當事人名/案由**；代號↔真實對照表只存本地 DB。
4. **最小化送 Claude**：完整文件只在「抽送達日」那一次送；確認後存結構化欄位，之後每日摘要/查詢用結構化資料跑，不重複送整份機密。

**保留為可開關、要收緊隨時開（升級路）：**
- 每日摘要也代號化（連 LINE 都看不到當事人名）。
- 文件抽取前**本地先 OCR + 遮當事人名**，只送「含日期那段」給 Claude（算期限不需要名字）。
- 最敏感原始文件改走本地上傳、不經 LINE。
- 評估 Enterprise ZDR（零保留）——成本跳級，預設不採。

## 模組（相對原藍圖大幅瘦身）

- **新建**：`matters`（案件，輕量：案號/案由/法院/階段/當事人名/承辦律師）、`deadlines`（時限，技術細節見 `01-deadline-engine.md`）、行事曆 adapter、文件接收與抽取流程。
- **新增能力（原研究未涵蓋、本版核心）**：**文件 → 到期日抽取**（讀 LINE 傳入的判決/裁定/通知照片或 PDF，抽送達日 + 文書類型）。
- **沿用橫向基建**：`tasks`、`knowledge`（法律見解/SOP，機密軸）、`approvals`（HITL 用在「到期日確認」與「對法院遞交」）、`attachments`（存檔案）、`line`、escalation 投遞三層（cron 保證層 + claude -p 品質層 + in-session 即時層）。
- **移除**：`inventory`；**退化**：`business_units`（單一律所）。
- **floor / 機密層（個人律所＝不需要）**：機密層 / floor 是「**對內**防員工越權」的機制，前提是有別的員工要擋。**個人律所只有一個律師、看全部、沒有對內隱藏的對象 → 不需要機密層**。部署＝不設 SME_FLOOR（全權限單人）、不配置任何 floor。我們已建的 `confidential` 欄 + floor gate **保留為 inert**（全權限層下永遠可見、不過濾、零成本），**待增員（助理）或多人 / 與 pleading-manager 合併版再啟用** —— 不從程式移除（移除＝白工、且失去升級路）。
  - ⚠️ 別把「機密層（對內）」跟「隱私（對外）」搞混：個人律所**沒有對內問題**，但**對外隱私（Google/Claude/LINE 不該看到當事人機密）照樣全部適用**（見〈隱私設計〉）。

## system-layer（沿用既有 escalation 三層基建）

- 新增 cron 薄殼（鏡像 `flush_escalations.py`）：每日定時讀行事曆 + `deadlines` → claude -p 彙整 → LINE 推全所。
- 文件抽取後的「請確認」提醒走即時層 / LINE reply。
- 把 `pending_escalations` 泛化成 `pending_notifications`（加 `kind`），投遞三層幾乎零改動。

## 靜默失敗哨兵（#H1/#H2，「漏不掉」的兩道補強）

HITL + cron 自帶兩個結構盲區，補上才稱得上「漏不掉」：

1. **#H1 系統健康哨兵** —— `scan_deadlines.py` 若靜默掛掉，時限停止倒數且沒人知＝漏期根因。
   - 掃描器每次成功跑完落一筆 `deadline_scan` heartbeat（`interaction_log`，零時限也寫＝證明在跑）。
   - 第二支極小 cron `scan_heartbeat.py`（watchdog、互為 dead-man）：落自身 heartbeat 自證活著 + 偵測掃描器失聯（heartbeat 過期 `SCAN_STALE_HOURS`，或從未跑但已有待處理時限）→ enqueue `scan_stalled` 上報（時間驅動、人沒開 Claude 也跑、同失聯期 `SCAN_REALERT_HOURS` 內 dedup）。
   - 全權限開機 readout（`get_context_summary`）把「掃描失聯 / watchdog 失聯」列在最前。門檻常數集中於 `shared/deadlines.py`、cross-file guard 綁死。

2. **#H2 未確認到期日跟催** —— 核心 loop「一鍵確認才入」刻意把人擋中間；副作用＝丟了檔、AI 推確認、人忘了回 → 時限沒進 `deadlines` → 一般掃描掃不到 → 隱形漏掉。
   - 抽取當下 `stage_deadline_intake` 把事實暫存進 `pending_intakes`（migration 014；**結構上不放任何 computed deadline 欄**＝待確認階段引擎還沒算、不可能洩權威日期，反捏造的結構性保證）。
   - cron `scan_unconfirmed_intake.py` 跟催「M 件待確認、最久 X 小時」（提醒只列送達日/文書類型/等待時數）。
   - 確認入庫走 `create_deadline(confirm_intake_id=)` 同 tx 關閉 backlog；不算了 `resolve_deadline_intake(id,'discarded')`。
   - 開機 readout 露「待確認時限 N 件」。

## 時限計算紀律（不可妥協）

天數一律由 service 層確定性程式碼算、附 `statutory_basis` 法條（反捏造、絕不 LLM 心算）。需資料底：台灣官方辦公日曆（末日順延）；在途期間預設「有住法院所在地律師代理 → 在途=0」、罕見組合標 `needs_manual_review`。核心法定期間種子（民訴§440 上訴 20 日、§487 抗告 10 日、刑訴§349 上訴 20 日…）見 `01-deadline-engine.md`。

**三道反捏造安全網（引擎自動跑，`compute_deadline` / `create_deadline` 內）：**
1. **法版檢核** —— STATUTORY_PERIODS 編現行法日數。**文書作成日**（判決/裁定日 `document_date`，非送達日——舊判決可能修法後才送達）早於某法條「期間日數修正施行日」（如刑訴§349 上訴 2020-01-15 由 10→20、刑訴§406 抗告 2023-06-21 由 5→10）→ 標 `needs_manual_review` + `calc_trace` 說明，**不臆測重算舊法**（沿革表僅含已查證者、寧缺勿錯；條號用 regex 精準比對、不裸子字串誤命中如 §349之1；`document_date` 未提供則以送達日近似並於 trace 誠實標明）。舊判決（再審/回復原狀）特別需要。
2. **教示比對** —— 建時限帶 `stated_period_days`（判決書「上訴教示」所載天數）→ 與引擎採用的 `statutory_days` 交叉比對，不符即標複核（揪出 type 選錯或屬特別期間）。引擎不靜默蓋過判決書教示。
3. **裁定期間強制複核** —— 限期補正（`type='correction'`）等裁定期間，天數由法院在裁定當下載明、非法定固定值（獨立 `COURT_SET_PERIODS` 表只登記 court_set/severity/描述/裁定文號提示，**絕不含 statutory_days**、律師必讀裁定填）。`create_deadline` 凡 `period_type='court_set'` 一律強制 `needs_manual_review`（純人輸入、無固定法定種子可交叉驗證＝風險最高）；缺天數/裁定文號給「讀裁定」針對性提示擋下、不以 0 硬算。漏補正＝駁回起訴、小所最高頻時限之一。

**消滅時效（請求權時效，`type='limitation'` / `statute_125/126/127/197_2y/197_10y`）**：與訴訟期間根本不同——期間是「年」（§125=15/§126=5/§127=2/§197=2+10），依民§121 曆法（相當日之前一日、無相當日→該月末日）+ §123 連續依曆、**不可硬轉天數**；起算點是民§128「請求權可行使時」＝法律判斷（非送達日這種確定事實）→ 一律強制人工複核、起算日（請求權可行使時/侵權知悉時）律師輸入；無在途、無送達加算、不適用回復原狀。§197 侵權是雙時鐘（知悉起2年 + 行為時起10年）各建一筆。引擎加 `period_unit`/`period_value`（migration 015）+ `counting_regime`（limitation/procedural）解耦「年/月」與「時效 regime」；§122 末日順延於消滅時效見解分歧 → 引擎不臆測、依曆末日為準（包進強制複核）。

4. **保全命起訴期間（`type='provisional_litigation'`，民訴§529Ⅰ/§533）**：法院命債權人「於一定期間內起訴」、期間由命起訴裁定當下所定（非法定 30 日＝坊間慣例非法律值），歸 court_set 由律師讀裁定填、強制複核、severity=red（逾期→保全被撤銷）；提醒§529Ⅲ夫妻剩餘財產 10 日特例。

5. **程序月期間（`type='admin_revocation'`，行訴§106Ⅰ 撤銷訴訟訴願決定書送達後2個月不變期間）**：與消滅時效都是「月」但 regime 不同——走程序機制（送達+次日+依曆2月§121/§123+在途§89+§122順延、行訴§88 期間依民法），起算用送達日這個確定事實 → **不**強制複核（相對時效可確定性自動算）；回復原狀依**行政訴訟法§91**（1個月，≠民訴§164 之10日）；回覆提醒三例外（逾3年長期、利害關係人知悉在後、不經訴願§106Ⅲ）。

## 行事曆寫入（calendar-agnostic）與 skill

- **行事曆寫入是 agent 動作、走現場配置的行事曆 MCP**（Google 或律所慣用的其他），非 business-db 內建特定 client。流程：agent 用行事曆 MCP `create_event`（去識別化：只放案件代號 + 期限類型 + 日期）→ `mark_deadline_calendared(deadline_id, calendar_event_id, calendar_provider)` 把回傳 id 存回 `deadlines`（供去重 / 後續對位）。`deadlines` 新增 `calendar_event_id`/`calendar_provider`/`calendar_synced_at` 三欄（migration 013）。
- **runtime playbook = `.claude/skills/legal-admin/`**：SKILL.md（核心 loop + 鐵律 + 安全執行模型）+ references（deadline-intake / daily-digest / matter-query / calendar-sync / consultation / privacy-deploy）。串起「收檔→抽取→HITL 一鍵確認→`create_deadline`→寫行事曆→每日彙整→查詢」。
