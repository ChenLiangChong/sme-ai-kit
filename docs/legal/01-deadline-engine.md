# 時限管理模組（deadlines）技術設計文件 — legal-admin vertical

> 分支：`legal-admin`（單一律所、不回併、不做多事業體）
> 定位：律所差異化命脈。漏一個時限＝執業過失，故本模組以「**時間驅動 + system-layer 確定性投遞**」為核心架構，天數一律由 service 層確定性計算、附法條依據，**絕不交 LLM 心算**。
> 設計基準：實讀 `shared/escalation.py`、`flush_escalations.py`、`migrations/007/010`、`floor-map.example.json`，所有接線都對齊現役契約。

---

## 0. 核心設計原則（先釘死，後面全部遵守）

1. **兩條獨立時鐘、三段串接**：`送達 →(送達生效規則)→ 生效日 →(民法§120 翌日)→ 起算日 →(法定期間 + 在途)→ 理論末日 →(民法§122 末日順延)→ 法定 hard deadline → −緩衝 → 內部 working deadline`。引擎最常死在「把收件當天當起算」。
2. **法定末日（hard）與內部期限（working）分欄存放、永遠並陳**。盯的是 internal、底線是 statutory。
3. **天數確定性計算 + calc_trace 可逐步覆核**（律師不能信黑箱），每筆強制附 `statutory_basis`（反捏造，比照知識庫 `source_quote`）。
4. **時間驅動屬 system-layer**：cron 每日掃 → enqueue → 既有三層投遞。人沒開 Claude 也在倒數。
5. **fail-toward-有人看**：在途罕見組合 / 囑託送達（依回證完成日、不確定）/ 緩衝期完全落在連假無上班日可前移 / 所需年度辦公日曆未載入 / 裁定期間（court_set，如限期補正）天數由律師讀裁定填、無固定種子可交叉驗證 → `needs_manual_review`，不自動結案、推人複核（呼應 escalation「fail-toward-有人收」）。**公示送達境內+20 / 外國+60 為法定固定值、自動計算可辯護、不標複核**（`_SERVICE_NEEDS_REVIEW` 只含 commissioned）。
6. **法規版本鎖定**：刑訴上訴 10→20 日（2021）、刑訴抗告/回復原狀 5→10 日（2023）、寄存送達 +10 日（2021）——引舊資料即算錯。每筆種子標 `statutory_basis` + 版本。

---

## 1. 資料模型

新表只走 migration（沿用 leave_* / access_zones / pending_escalations 慣例、不寫進 schema.sql），legal-admin 從 `011` 起。ISO8601 localtime、FK 沿用既有保留稽核策略。

### 1.1 `matters`（案件主檔 — deadlines 的父鍵，migration 011）

```sql
CREATE TABLE IF NOT EXISTS matters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_no TEXT UNIQUE,                  -- 事務所內部案號（2026-民-001）
    title TEXT NOT NULL,                    -- 案由
    client_party_id INTEGER,               -- 委任人 → parties(id)（legal-admin 另案改 customers→parties）
    practice_area TEXT,                    -- civil/criminal/admin/family/ip/labor/non_litigation
    court TEXT,                            -- 繫屬法院（算在途期間的維度1）
    court_case_no TEXT,                    -- 法院案號（112年度訴字第XXX號）
    stage TEXT,                            -- first_instance/second_instance/third_instance/execution/...
    status TEXT NOT NULL DEFAULT 'open',   -- open/on_hold/closed/archived
    lead_attorney TEXT,                   -- 主辦律師
    has_local_agent INTEGER DEFAULT 1,    -- §162 但書：律師住法院所在地→在途歸零（律所自辦常為1）
    confidential INTEGER DEFAULT 0,        -- 機密軸 → floor 可見度
    opened_at TEXT, closed_at TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (client_party_id) REFERENCES parties(id) ON DELETE SET NULL
);
```

### 1.2 `deadlines`（時限主檔，migration 012 — 本模組核心）

```sql
CREATE TABLE IF NOT EXISTS deadlines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_id INTEGER NOT NULL,
    -- 業務語意
    type TEXT NOT NULL,                    -- appeal_civil/appeal_criminal/appeal_admin/abjection(抗告)/
                                           --   answer(答辯)/brief(準備書狀)/appeal_reason(上訴理由書補提)/
                                           --   petition_appeal(訴願)/admin_litigation/retrial(再審)/
                                           --   payment_order_objection(支付命令異議)/custom
    description TEXT NOT NULL,             -- 「對一審判決提起上訴」
    -- 性質（決定處理規則：硬牆/可補正/訓示，見 §3 提醒分級）
    period_type TEXT NOT NULL,            -- peremptory(不變期間)/statutory(通常法定)/court_set(裁定期間)/directory(訓示)
    severity TEXT,                        -- red(失權硬倒數)/orange(可補正)/grey(訓示僅提醒)；計算時可由 period_type 推導預設
    -- === 計算輸入（不可省，算錯=執業過失）===
    trigger_event TEXT NOT NULL,          -- 起算事件（判決送達/裁定送達/公告/最後登報）
    service_type TEXT NOT NULL DEFAULT 'normal',  -- normal/registered_deposit(寄存)/
                                           --   public_domestic(公示境內)/public_foreign(公示外國)/commissioned(囑託)
    service_base_date TEXT NOT NULL,      -- 送達/寄存/黏貼/公告/最後登報基準日 YYYY-MM-DD
    statutory_days INTEGER NOT NULL,      -- 法定日數（民事上訴=20、抗告=10…；裁定期間=裁定所載）
    statutory_basis TEXT NOT NULL,        -- 法條依據（民訴§440）— 強制非空，反捏造
    statutory_basis_version TEXT,         -- 法規版本日（如『刑訴§349 110.06.16修正版』）
    -- === 在途期間（民訴§162）===
    in_transit_days INTEGER DEFAULT 0,    -- 查表得（無代理人除外時加算；裁定期間/有當地代理人→0）
    in_transit_source TEXT,               -- '查表 B0010020 v107.7.1：金門→台北地院 N 日' / '§162但書歸零'
    -- === 計算輸出（service 層算出後落欄、供 cron 直接讀，避免每次重算）===
    effective_date TEXT,                  -- 送達生效日（含特殊送達加算）
    start_date TEXT,                      -- 起算日（生效翌日）
    statutory_deadline TEXT,              -- 法定 hard deadline（末日順延後）— 底線、永不退讓
    buffer_days INTEGER NOT NULL DEFAULT 1,  -- 內部安全緩衝（老闆的「19天」=20-1；可設更保守）
    internal_deadline TEXT,               -- 內部 working deadline = statutory_deadline − buffer（盯這個）
    calc_trace TEXT,                      -- JSON 陣列：每步可稽核軌跡（律師逐步覆核）
    needs_manual_review INTEGER DEFAULT 0,-- 囑託送達/在途罕見/連假緩衝塌陷/年度日曆未載入→強制人工複核、不自動結案（公示送達+20/+60 為法定固定、不標）
    -- === 狀態與提醒 ===
    status TEXT NOT NULL DEFAULT 'pending',  -- pending/filed(已遞交)/extended(已展延)/missed(逾期)/cancelled
    assignee TEXT,                        -- 負責律師
    assignee_line_user_id TEXT,           -- 承辦律師 LINE id（MVP「全所一份」下不作收件對象、保留供未來 per-assignee 分送）
    escalation_lead_days TEXT DEFAULT '[7,3,1,0]',  -- JSON：T-N 升級式提醒節點（餵 cron）
    reminders_sent TEXT DEFAULT '[]',     -- JSON：已發過的 lead_day（去重、防同一天重推），如 [7,3]
    recovery_window TEXT,                 -- JSON：逾期時回復原狀條件（原因消滅後10日內 + 民事1年上限）
    filed_at TEXT, filed_by TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (matter_id) REFERENCES matters(id) ON DELETE CASCADE,
    CHECK (status IN ('pending','filed','extended','missed','cancelled')),
    CHECK (period_type IN ('peremptory','statutory','court_set','directory')),
    CHECK (statutory_basis <> '')         -- 反捏造：每個法定天數都要有依據
);

-- cron 每日掃描的 hot path（只 index 還活著的）
CREATE INDEX IF NOT EXISTS idx_deadlines_pending
    ON deadlines(status, internal_deadline) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_deadlines_matter ON deadlines(matter_id);
```

**欄位設計理由（重點）**：
- `reminders_sent` 是冪等鑰：cron 每日跑，同一 `lead_day` 命中第二次不重 enqueue（否則 T-7 那天會每跑一次推一次）。
- `escalation_lead_days` 是 cron 的輸入（per-deadline 可調，紅色案可加密 `[14,7,3,1,0]`）。
- 計算輸出落欄（`statutory_deadline`/`internal_deadline`/`effective_date`/`start_date`）：cron 是「笨掃描器」，只讀欄比日期，不重算法律邏輯——所有法律計算集中在寫入/重算路徑的 service 層。
- `recovery_window`：逾期不等於結束（民訴§164：原因消滅後10日內、距遲誤未逾1年；刑訴§67：10日），主動掛出最後安全網。

### 1.3 與 matter / 案件關聯

- `deadlines.matter_id → matters(id) ON DELETE CASCADE`：案件刪除連帶清時限（時限脫離案件無意義）。
- 一個 matter 有多筆 deadline（上訴 20 日 + 上訴理由書補提 20 日是**兩條獨立時鐘**，律所最常漏第二條——各建一筆 row）。
- `documents.deadline_id → deadlines(id)`（legal-admin documents 表）：書狀遞交 → document.status='filed' → 同 tx 關閉對應 deadline（`mark_deadline_filed`）→ cron 不再提醒。

### 1.4 安全網 + 行事曆同步欄（migration 013）

`deadlines` 加四欄（ALTER TABLE，非改 schema.sql；新表/新欄只走 migration）：

| 欄 | 用途 |
|---|---|
| `stated_period_days INTEGER` | **教示比對安全網**：判決書「上訴教示」所載天數（NULL=未提供）。`compute_deadline` 與採用的 `statutory_days` 交叉比對，不符 → `needs_manual_review` + calc_trace 記不符（引擎不靜默蓋過判決書教示；揪出 type 選錯或特別期間）。 |
| `document_date TEXT` | **法版檢核基準**：文書作成日（判決/裁定日，NULL=未提供）。法版適用看文書作成日、非送達日（舊判決可能修法後才送達）。 |
| `calendar_event_id TEXT` | 外部行事曆 event id（calendar-agnostic，SPEC「寫兩處」回填） |
| `calendar_provider TEXT` | 行事曆來源標記（'google'/'internal'/…） |
| `calendar_synced_at TEXT` | 回填時間 |

**法版檢核安全網**（純算、不落欄）：`compute_deadline` 內 `_PERIOD_AMENDMENTS`（regex 精準鎖法別+條號邊界、不裸子字串誤命中如 §349之1）記已查證的期間日數修法施行日（刑訴§349 2021-06-16 由 10→20、刑訴§406 2023-06-21 由 5→10）。**優先比對 `document_date`（文書作成日）**、未提供才以 `service_base_date` 近似並於 calc_trace 誠實標明；該日早於施行日 → `needs_manual_review` + calc_trace 說明，**不臆測重算舊法**（沿革表僅含已查證者、寧缺勿錯；非空 document_date 格式錯誤直接回 error、不靜默落髒資料）。`compute_deadline` 回傳加 `stated_period_days` / `period_match`（match/mismatch/not_provided）。

**裁定期間強制複核安全網**（`COURT_SET_PERIODS`，與固定天數種子 `STATUTORY_PERIODS` 分開的獨立表）：限期補正（`type='correction'`）等裁定期間，天數由法院在裁定當下載明、**非法定固定值**——`COURT_SET_PERIODS` 只登記 `period_type='court_set'` / `severity` / 描述 / 觸發語 / 裁定文號提示，**絕不含 `statutory_days`**（律師必讀裁定填、引擎不回填不預設；上訴 20 日寫死在法律可回填，補正期間是法院個案訂的、回填＝臆測）。`create_deadline` 凡最終 `period_type='court_set'` 一律強制 `needs_manual_review`：裁定天數純人輸入、無固定法定種子可交叉驗證，是反捏造風險最高一類，calc_trace 留「裁定所定期間強制複核」理由。缺天數 / 裁定文號 → 給「讀裁定」針對性提示擋下、不以 0 硬算。漏補正＝駁回起訴，小所最高頻時限之一。

**消滅時效（年/月期間，`type='limitation'` / `LIMITATION_PERIODS`，migration 015 加 `period_unit`/`period_value`）**：與訴訟「日數」期間根本不同。期間是「年」（民§125=15 / §126=5 / §127=2 / §197=2+10），依民§121「以年/月定期間→以最後之年/月與起算日『相當日之前一日』為末日；無相當日（閏日/月末）→該月末日」+ §123「連續計算依曆」，**不可硬轉天數**（閏年會差、反捏造；自實作 `_statute_period_end`、不引入 dateutil）。`compute_deadline` 走獨立 year/month 分支：無在途、無送達加算（民§128 自請求權可行使時直接起算）、不適用回復原狀。起算點是民§128「請求權可行使時」＝**法律判斷**（非送達日這種確定事實；§197 侵權還含主觀「知悉時」）→ `create_deadline` 對 `period_unit in (year, month)` 一律強制 `needs_manual_review`、起算日（`service_base_date`）由律師輸入。§122 末日順延於消滅時效見解分歧 → 引擎不臆測順延、依曆末日為準（爭議包進強制複核、律師個案決定）。§197 雙時鐘（知悉2年 `statute_197_2y` + 行為10年 `statute_197_10y`）各建一筆、不自動雙建（避免系統替律師判斷「知悉時」）。`period_type` 仍用 `statutory`（不改既有 CHECK），靠 `period_unit` 觸發曆法分支。

---

## 2. 計算流程（依序、可直接寫成程式）

**service 層函式 `compute_deadline(input) -> output`，純函式、可單元測試、對照司法院試算工具（gdgt.judicial.gov.tw）交叉驗證。** 步驟順序不可調換。

### 需要的外部資料底（data layer）
| 資料 | 用途 | 來源 / 表 |
|---|---|---|
| **辦公日曆** `is_holiday(date)` | 末日順延（§122） | DGPA《政府行政機關辦公日曆表》（含補班/調移/颱風假，**不可自行硬算週末**）。cache：GitHub `ruyut/TaiwanCalendar` JSON（`date/week/isHoliday/description`），以 DGPA 官方對賬。建 `office_calendar(date PK, is_holiday, description)` 表，cron 引擎讀本表。 |
| **在途期間表** `lookup(court, party_region)` | 在途加算（§162） | 司法院《在途期間標準》B0010020（民刑）/ A0020097（行政）。**無 open API、人工逐筆建表 + 律師覆核 + 版本號**。建 `transit_period(court_code, party_region_code, days, basis_version, note)`。 |

### 計算步驟

```
輸入：matter_id, type, period_type, statutory_days, statutory_basis,
     trigger_event, service_type, service_base_date,
     court, party_region, has_local_agent, buffer_days

步驟 1｜決定送達生效日 effective_date（需：service_type, service_base_date）
  normal           → effective_date = service_base_date                （收受當日生效）
  registered_deposit → effective_date = service_base_date + 10          （民訴§138Ⅱ，2021新增，自寄存翌日起算10日）
  public_domestic  → effective_date = service_base_date + 20           （民訴§152）
  public_foreign   → effective_date = service_base_date + 60           （民訴§152）
  commissioned     → effective_date = 回證載明完成日；needs_manual_review = 1
  ⚠ 民訴寄存(+10) ≠ 行政程序法寄存(即生效)，按程序別分流，勿混用

步驟 2｜決定起算日 start_date（民法§120Ⅱ 始日不算入）
  start_date = effective_date + 1天

步驟 3｜計算在途天數 in_transit_days（需：在途期間表）
  if period_type == 'court_set'      → in_transit_days = 0  （裁定期間不適用在途）
  elif has_local_agent == true       → in_transit_days = 0  （§162但書：律師住法院所在地）
  else                               → in_transit_days = lookup(court, party_region)
                                        （區域外＝受訴法院區域 + 住居地地院區域，取較長；
                                         大陸港澳37、亞洲37、歐美44、非洲72）
  記錄 in_transit_source（含版本，供 calc_trace）

步驟 4｜計算理論末日 nominal_due（中間假日全計入、不跳過）
  nominal_due = start_date + (statutory_days + in_transit_days) − 1
  ⚠ 此步驟不做任何假日跳過——期間「之內」的週末/國定假日照常計入（連續計算）

步驟 5｜末日順延 statutory_deadline（民法§122，只對末日）
  d = nominal_due
  while is_holiday(d):   # 週六/週日/國定假日/休息日（讀辦公日曆表）
      d = d + 1天
  statutory_deadline = d                # ← 法定 HARD deadline、底線
  ⚠ 只順延末日；步驟4的中間日不順延

步驟 5b｜辦公日曆載入偵測（部署安全）
  office_calendar 只種了部分年度（MVP 種 2026）。檢查 start_date → statutory_deadline 區間
  涵蓋的每個年度是否有任何 office_calendar 紀錄；任一年完全無紀錄 → needs_manual_review = 1
  （is_holiday 會靜默退回「只看週末」規則、抓不到國定假日 / 補班 → 末日順延與內部線可能誤算）。
  保留週末規則為最後 fallback、但必有 review 旗標（誠實標明日曆未載入、是估值）。

步驟 6｜計算內部期限 internal_deadline（working）
  internal_deadline = statutory_deadline − buffer_days
  對 internal_deadline 往前對齊到上班日呈現（避免內部線落在假日反而不提醒），但對齊
  搜尋區間僅 (start_date, statutory_deadline]：
  - 區間內找到上班日 → 誠實前移、calc_trace 寫「前移至上班日 X」（X 保證 is_holiday=False）。
  - 緩衝期完全落在連假（如春節 02-14~02-22）、區間內無任何上班日可前移
    → fail-toward：緩衝收為 0、internal_deadline = statutory_deadline、needs_manual_review = 1，
      calc_trace 誠實標明「緩衝期完全落在連假、區間內無上班日可前移 → 暫設為法定末日、須人工複核」。
  ⚠ 反捏造：internal_deadline 不可靜默停在假日；calc_trace 凡聲稱「前移至上班日 X」、X 必須真的非假日。
  ⚠ 恆等式：internal_deadline ≤ statutory_deadline 永遠成立。

步驟 7｜產出逾期救濟備援 recovery_window（民訴§164 / 刑訴§67）
  民事/行政：{原因消滅後10日內聲請, 距遲誤未逾1年, 須同時補行訴訟行為}
  刑事：    {原因消滅後10日內}

輸出：effective_date, start_date, in_transit_days(+source),
     statutory_deadline(hard), buffer_days, internal_deadline(working),
     calc_trace[], needs_manual_review, recovery_window, legal_basis[]
```

**calc_trace 範例（律師覆核用）**：
```json
["送達生效=寄存日2026-06-01+10=06-11（民訴§138Ⅱ）",
 "起算=生效翌日06-12（民法§120Ⅱ）",
 "在途=§162但書·律師住法院所在地→0",
 "理論末日=06-12+(20-1)=07-01（中間假日全計入）",
 "末日順延：07-01(三)非假日→不順延（民法§122）",
 "法定末日07-01；內部=−1=06-30（盯此）"]
```

---

## 3. 雙日期設計（hard vs working）的理由與用法

| | `statutory_deadline`（法定 hard） | `internal_deadline`（內部 working） |
|---|---|---|
| 是什麼 | 法律不可退讓的底線（過了即失權） | 事務所自訂提早線 = hard − buffer |
| 怎麼算 | §120 翌日 + 期間 + 在途 + §122 末日順延 | hard − `buffer_days`（預設1=老闆的「19天」） |
| 用途 | 救濟判讀基準、永不可改 | **cron 提醒/倒數盯的就是它** |
| 改動性 | 不變期間法院都不得伸縮（§163但書），引擎**不可給「申請延長」選項** | 老闆可調 buffer（紅色案調 3 天更保守） |

**為何必須兩條而非一條**：
1. **緩衝吸收計算不確定性**：在途期間查表罕見組合、末日順延、送達生效認定都可能浮動 ±1~2 天。盯 hard 線＝零容錯；盯 working 線＝律師備狀還有緩衝。
2. **「19天」的真相要分清（研究查證重點）**：buffer 來源有二——(a) 「法定20 − 1 安全緩衝」；(b) **金門/馬祖在途期間官方上限本就是 19 日**。兩者引擎都支援，但實作上 19 是「`in_transit_days` 查表值」還是「`buffer_days`」語意完全不同：在途進步驟3（影響 hard），緩衝進步驟6（不影響 hard）。**絕不把在途寫死成 buffer**。
3. **提醒以 internal 推、底線露 statutory**：每則提醒同時給兩個日期（「內部期限 6/30，法定 7/1」），律師心裡有底線、行動有提早線。

---

## 4. 提醒節奏（T-N 升級式）+ 接既有 escalation/LINE

### 4.1 建議天數（依 severity 分流）

| severity | 對應 period_type | 預設 `escalation_lead_days` | 提醒節奏 |
|---|---|---|---|
| **red 失權硬倒數** | peremptory（上訴/抗告/支付命令異議）+ 三審補提（§471/§382 逾期逕駁） | `[14,7,3,1,0]` | 最密集（逾期/T-1 紅字、每日推） |
| **orange 可補正** | statutory（刑訴二審補提§361先命補正、訴願30日） | `[7,3,1,0]` | 標準 |
| **grey 訓示** | directory（法院端宣示/送達期限） | `[3]` | 僅進度提醒、不入失權倒數 |

- `0` = 當日（internal_deadline 當天最後催）。
- **逾期（today > internal 且 status=pending）**：每日持續推（最高優先級，比照 `deadline_missed`），並掛出 `recovery_window`。
- 升級式＝同一 deadline 隨剩餘天數遞減、語氣升級（T-7 一般提醒 → T-1 紅字 → 逾期天天推 + 紅字）。
- **收件人＝全所一份（SPEC §16/§58 定案）**：每筆提醒走既有 `resolve_escalation_target()`（boss/全所），**不** per-assignee 分送（小所「預設不分層、全所共用一個視圖」）。承辦律師資訊放進 `summary` 文字（「承辦：某律師」），讓收件人看得到由誰負責。`escalation_lead_days` 是「**節奏**」設定（per-deadline 可調紅色案加密 `[14,7,3,1,0]`），不是「收件對象」設定。要 per-assignee 分送是未來機制（floor 分層落地後），MVP 不做。

### 4.2 接既有 escalation（零改投遞層、只擴觸發源）

**關鍵架構決策：泛化 `pending_escalations` 而非另開表。** cron 算出「今天該提醒的 deadline」後，直接 `enqueue` 一筆 row 進現役佇列，三層投遞器（cron flush + claude -p notifier + in-session push）**零改動**就能推送。

新增 legal-admin escalation 事件（加進 `DEFAULT_ENABLED_EVENTS` + `ESCALATION_LABELS`）：
```
deadline_approaching   # T-N 將至（cron 按 escalation_lead_days 觸發）★核心、時間驅動
deadline_missed        # 已逾期（最高優先，逾期當下/每日）
```
- **收件人＝全所一份**：`scan_and_enqueue_due_reminders` 一律以 `channel_id=None` enqueue，收件人由現役 `resolve_escalation_target()` 解析（`floor-map.escalation_target` 直接 user_id → `role=boss` → `permissions=admin` → `company.boss_line_id` → 仍寫 pending，fail-toward-有人收）。**`channel_id` 是 OA channel 欄（送哪個 LINE OA）、非收件人欄**——絕不把承辦律師的 `line_user_id` 塞進 `channel_id`（會污染 OA 欄、且 flusher 拿它當 channel key 查 token 必 fail）。`deadlines.assignee_line_user_id` 在 MVP「全所一份」下不作為收件對象（保留欄位供未來 per-assignee 分送機制）。
- `summary` 由 service 確定性產（非 LLM），含兩日期 + 法條 + 承辦律師：
  `【XX案 2026-民-001】上訴狀補提 內部6/30（法定7/1·民訴§471）剩3個工作日 承辦：王律師`。
- meta 必為 `Record<string,string>`（in-session push #182 根因：int 值被 CC 靜默丟整筆），如 `{"deadline_id":"12","lead_day":"3","severity":"red"}` 全字串。

---

## 5. system-layer 接線（cron → claude -p → 推送）

完全鏡像 `flush_escalations.py` 薄殼模式：獨立進程、`os.environ.pop("SME_FLOOR")`、讀 DB + token、只負責「掃 → enqueue」，投遞交既有三層。

### 5.1 新 cron 腳本 `scan_deadlines.py`（保證層的寫入端）

```
crontab（每日 07:00，鏡像 install.sh:184-205 marker 防重複 + WSL cron daemon 偵測）：
0 7 * * * SME_DB_PATH=/abs/data/business.db \
    /abs/.venv/bin/python3 /abs/mcp-servers/business-db/scan_deadlines.py >> /abs/data/scan.log 2>&1
```

腳本邏輯（薄殼，計算政策在 shared）：
```python
# scan_deadlines.py（鏡像 flush_escalations.py）
os.environ.pop("SME_FLOOR", None)          # 掃描器不解析身份、不需 floor
from shared.deadlines import scan_and_enqueue_due_reminders
stats = scan_and_enqueue_due_reminders()   # 見下
```

`scan_and_enqueue_due_reminders()`（shared/deadlines.py，**單一 tx、enqueue 走現役 `enqueue_escalation`**）：
```
with transaction() as db:
  today = date.today()
  rows = db.execute(
    "SELECT * FROM deadlines WHERE status='pending'"   # 用 idx_deadlines_pending
  ).fetchall()
  for d in rows:
    lead_days = json.loads(d['escalation_lead_days'])      # [14,7,3,1,0]
    sent      = set(json.loads(d['reminders_sent']))       # 冪等鑰
    days_left = workdays_between(today, d['internal_deadline'])  # 或日曆日，per 設定
    # (a) 命中提醒節點且未發過 → enqueue
    for n in lead_days:
      if days_left == n and n not in sent:
        enqueue_escalation(db,
          event_type='deadline_approaching',
          summary=f"【{matter_no} {title}】{desc} 內部{internal}（法定{statutory}·{basis}）剩{n}天",
          detail={'deadline_id':str(d['id']),'lead_day':str(n),'severity':d['severity'],
                  'statutory_deadline':d['statutory_deadline'],'internal_deadline':d['internal_deadline']},
          actor_user_id='', actor_label='系統·時限掃描',   # 系統觸發、非人
          channel_id=None)                                  # 由收件人 coalesce
        sent.add(n)
    # (b) 逾期 → deadline_missed（每日推、升級合夥人）
    if days_left < 0:
      enqueue_escalation(db, event_type='deadline_missed', summary=..., detail=...)
    # 回寫冪等鑰（同 tx）
    db.execute("UPDATE deadlines SET reminders_sent=? WHERE id=?",
               (json.dumps(sorted(sent)), d['id']))
  # commit 成功 → transaction() fire-and-forget 起 claude -p 品質層 + in-session 即時層
```

> **架構對位**：escalation 寫入端是「業務 in-tx enqueue」（事件驅動）；本模組寫入端是「cron 每日掃 → enqueue」（時間驅動）。**投遞層完全共用、零改動**。這正是老闆「services 起在 system 層」主張的最佳載體——時限與「人是否開 Claude」無關。

### 5.2 claude -p single-shot（品質層，commit 後 fire-and-forget）

- 觸發：`scan_and_enqueue` 的 tx commit 後，現役 `transaction()` 機制自動 `spawn_notifier`（**零額外接線**，因為走的就是 `pending_escalations`）。
- 走訂閱（`env.pop("ANTHROPIC_API_KEY")`）、全權限（`pop SME_FLOOR/SME_FLOOR_MAP`）、防遞迴 `SME_NOTIFIER=1`、窄工具白名單（`list_pending_escalations`/`mark_escalation_sent`/`mcp__line__reply`）。
- 工作：把同一律師當天多筆到期 row **合併成一則排序好的 LINE 摘要**（最急在前、附兩日期 + 法條），而非每筆洗版。prompt 硬約束「收件人照 row、不同律師絕不合併」（沿用 `_NOTIFIER_PROMPT`）。
- 兜底：保證層 cron `flush_escalations.py`（每 2 分）仍逐筆推 claude -p 漏的/掛的；防雙送靠現役 `claimed_at` 租約（claim-before-send CAS、TTL 10 分）。

### 5.3 投遞三層總圖（律所時限）

```
時間驅動（本模組新增）                既有投遞層（零改動複用）
─────────────────────             ──────────────────────
OS cron scan_deadlines.py 每日07:00
  掃 deadlines（讀落欄日期、不重算法律）
  → enqueue_escalation(deadline_approaching/missed)
  → 回寫 reminders_sent（冪等）
         │ commit
         ├── 保證層：flush_escalations.py（每2分·純Python push·確定性必達）★律所命脈
         ├── 品質層：claude -p single-shot（走訂閱·合併人話·兩日期+法條）
         └── 即時層：IPC 注入正在跑的律師/全權限 session（best-effort 即時自醒）
   （防雙送：claimed_at CAS 租約；backoff/failed 終態；開機 readout 露 failed/無收件人）
```

---

## 6. MVP vs 完整版 切割

### MVP（先做 — 證明「漏不掉」的核心價值）
1. **DB**：`matters`（精簡：matter_no/title/court/status/lead_attorney/has_local_agent）+ `deadlines`（全欄）+ `office_calendar`（辦公日曆，部署用 `import_office_calendar.py` 吃 DGPA/ruyut TaiwanCalendar JSON **整年逐日**匯入、idempotent、強制單一年度完整覆蓋；migration 只建空表不種半套年度——半套會被 `calendar_year_loaded` 誤判已載入而靜默誤算，故「已載入＝該年列數達 365/366」）。
2. **計算引擎 `compute_deadline`**：步驟 1~7 全做，在途支援三條路：`has_local_agent=true → 0`、「手動填 `in_transit_days`」、以及「無當地代理人 + 帶 `court_region`/`party_region` 查 `transit_period` 表」（`create_deadline` 已開這兩個可選參數；查得到→命中、查不到→`needs_manual_review` + 在途暫 0，fail-toward）。表的逐筆建檔/律師覆核留完整版。送達 normal + registered_deposit(+10) 先做；公示送達 public_domestic(+20)/public_foreign(+60) 為法定固定值、自動計算可辯護（**不標** `needs_manual_review`）；**僅囑託送達 commissioned**（依回證完成日、不確定）標 `needs_manual_review`（`_SERVICE_NEEDS_REVIEW` 只含 commissioned）。
3. **種子資料**：上訴（民/刑/行/家 20日）+ 抗告（10日）+ 上訴理由書補提（20日）+ 訴願（30日）+ 支付命令異議（20日），各附 `statutory_basis` + 版本。
4. **tools**：`create_matter` / `find_matter_by_party` / `create_deadline`（呼叫 compute_deadline 落欄）/ `mark_deadline_filed` / `mark_deadline_calendared`（回填行事曆 event_id）/ `list_deadlines` / `list_upcoming_deadlines` / `get_deadline`（含 calc_trace）。
5. **system-layer**：`scan_deadlines.py` cron（每日）+ enqueue 接現役 escalation（新增 `deadline_approaching`/`deadline_missed` 事件）。投遞三層**零改動複用**。
6. **單元測試**：compute_deadline 對照司法院試算工具的 golden cases（含末日順延、寄存+10、始日不算入）+ 兩道安全網（法版檢核 / 教示比對）+ 機密軸寫入端 gate。**這段是命脈、必測**。
7. **runtime skill**：`.claude/skills/legal-admin/`（SKILL.md + references）串起核心 loop（收檔→抽取→HITL 一鍵確認→create_deadline→寫行事曆→每日彙整→查詢）。

### 完整版（後做）
7. **在途期間表 `transit_period`**：人工逐筆建 B0010020/A0020097 + 律師覆核 + 版本號，`lookup(court, party_region)` 自動查。
8. **送達全類型**：public_domestic(+20)/public_foreign(+60)/commissioned（回證日 + 人工複核旗標）完整支援。
9. **severity 分流提醒**：red 雙人覆核（逾期加推合夥人）、orange、grey 三色節奏 + `documents.deadline_id` 連動「遞交即關時限」。
10. **回復原狀工作流**：逾期自動掛 `recovery_window`、產聲請提示（原因消滅後10日、1年上限、同時補行訴訟行為）。
11. **更多時間驅動掃描器**（同框架）：`scan_hearings.py`（庭期前一晚）/ `scan_billing.py`（律師費催繳，對外催款走 HITL）。
12. **法規版本覆核排程**：定期以全國法規資料庫覆核 `statutory_basis_version`，修法（如刑訴天數變動）時告警。

---

## 7. 未決問題 / 需老闆拍板

1. **buffer_days 預設值**：1 天（=老闆查到的「19天」）還是更保守 3 天？是否按 severity 差異化（紅色案 3 天、橘色 1 天）？影響 internal_deadline 全盤。
2. **提醒以「工作日」還是「日曆日」倒數**：T-3 是「3 個工作日」還是「3 天」？工作日對律師更實用但需 office_calendar 算；建議工作日，待拍板。
3. **`escalation_lead_days` 預設節點**：建議 red `[14,7,3,1,0]` / orange `[7,3,1,0]` / grey `[3]`——天數要不要調？是否加 T-30（長案早提醒）？
4. **逾期升級對象**：逾期是否一律推合夥人 + boss？小所合夥人即 boss 時避免重複推（coalesce 去重規則需確認）。
5. **「19天」語意鎖定**：本所 buffer 統一抓幾天，**且明確區分「在途期間」與「安全緩衝」是兩回事**（在途進 hard 計算、緩衝不進）——需老闆在知識庫 `store_fact` 落內規（如「內部緩衝統一 3 天」）。
6. **送達生效認定誰負責**：送達日是人工事實認定（cron 無法自動知道），建案/建時限時由律師或助理在 session 輸入 `service_base_date` + `service_type`——確認此責任歸屬與 SOP。
7. **在途期間建表優先序**：完整建 B0010020 全表（工程量大）還是先建本所常用法院 + 金門/馬祖/外國（high-risk）即可？建議後者，待確認。
8. **law 版本覆核頻率與責任人**：刑訴/民訴修法直接讓種子算錯，多久覆核一次 `statutory_basis_version`、誰負責？
9. **directory（訓示期間）要不要入庫**：對律所遞狀無失權效果，做進度提醒 vs 完全不收（降噪），待老闆定。

---

## 關鍵檔案路徑（實作參考，均為絕對路徑）

- 計算引擎新檔（建議）：`/mnt/d/gitDir/sme-ai-kit/mcp-servers/business-db/shared/deadlines.py`（`compute_deadline` + `scan_and_enqueue_due_reminders`，鏡像 `shared/escalation.py`）
- cron 薄殼新檔：`/mnt/d/gitDir/sme-ai-kit/mcp-servers/business-db/scan_deadlines.py`（鏡像 `flush_escalations.py`）
- migration 新檔：`/mnt/d/gitDir/sme-ai-kit/mcp-servers/business-db/migrations/011_matters.sql`、`012_deadlines.sql`、`013_office_calendar.sql`（在途表 `014_transit_period.sql` 留完整版）
- enqueue 母版（必對齊簽名）：`/mnt/d/gitDir/sme-ai-kit/mcp-servers/business-db/shared/escalation.py:175`（`enqueue_escalation`，新增 `deadline_approaching`/`deadline_missed` 進 `DEFAULT_ENABLED_EVENTS` L32 + `ESCALATION_LABELS` L428）
- 投遞三層（零改動複用）：`shared/escalation.py:457`（`flush_pending_escalations`）+ `shared/db.py:96-147`（commit 後 fire-and-forget）
- cron 安裝段（新 cron 照此加 marker）：`/mnt/d/gitDir/sme-ai-kit/install.sh:184-205`
- floor 可見度設定：`/mnt/d/gitDir/sme-ai-kit/data/floor-map.json`（`financial_visibility` 映信託帳；deadline 機密 case 用 `confidential` 軸 + `access_zones` ethical wall）

**核心架構結論**：時限管理 = 在現役 escalation 三層投遞前，新增一條「cron 每日掃 deadlines → enqueue」的時間驅動寫入端。投遞層、防雙送租約、收件人 coalesce、走訂閱不 metered **全部零改動複用**。法律天數計算集中在 service 層確定性函式（附 calc_trace + statutory_basis、對照司法院試算工具測試），cron 只讀落欄日期比對、不碰法律邏輯——既守「漏不掉」（保證層必達）、又守「不算錯」（確定性引擎 + 反捏造依據）。