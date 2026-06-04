# legal-admin Vertical 整體設計藍圖

> 律師事務所行政管理專版。從 SME-AI-Kit 分支 `legal-admin`（已確認當前分支），單一律所、不做多事業體、一路 diverge 不回併。
> 核心命題：**律所最痛＝時限管理（漏一個＝執業過失），而時限是時間驅動的——人沒開 Claude 也在倒數，所以該起在 system 層，不該綁在互動 session。** 既有 escalation 三層投遞基建（cron 保證層 + claude -p 品質層 + in-session 即時層）就是現成範本，把 `pending_escalations` 的「事件驅動寫入端」改成「cron 時間驅動掃描寫入端」即可。
> **紀律聲明**：所有法定天數均經研究 WebSearch 查證、附法條依據。天數一律由 service 層確定性程式碼計算、附 `statutory_basis`，**絕不交給 LLM 心算**（呼應反捏造原則）。法規版本鎖定基準：民國 115 年（2026）5 月。

---

## 1. 模組地圖：沿用 / 移除 / 改造 / 新建

當前模組（已確認）：`accounting / approvals / attachments / crm / hr / inventory / knowledge / leave / notifications / orders / settings / snapshots / tasks`；shared：`auth / business_units / db / escalation / floor_map / floor_policy / migrations / utils`。

### 1.1 沿用原樣（橫向基礎設施，幾乎不動）

| 模組 / 機制 | 律所用途 | 備註 |
|---|---|---|
| `tasks` | 案件待辦、內部交辦 | `category` 加法務值：`pleading`(書狀) / `hearing`(開庭) / `filing`(遞狀) / `research`(研究)；`tags` 帶 matter_id |
| `leave` | 員工請假、特休 | 完全不變 |
| `approvals` + HITL gate | 信託動支審核、超門檻收費、對外文件遞交、利衝放行 | gate 的 `resume_params` 一字不差 + `consumed_at` 單次消費，用於**鎖死信託動支金額/收款人**——比一般記帳更需要 |
| `knowledge`（business_rules + rule_relations + 機密軸） | 書狀範本邏輯、法律見解、內規、收費標準 | 法所最吃知識庫；`confidential` 軸天生對映「機密見解只合夥人可見」；`source_quote` 反捏造對法律意見更關鍵 |
| `attachments` | document 的物理載體（存路徑不存檔） | 不變，由新 `documents` 表掛上層語意 |
| `settings` | escalation_triggers、deadline 安全緩衝天數、在途預設等 | 不變 |
| `snapshots` | 換指標（見 1.3） | 結構沿用 |
| `notifications` + **escalation 三層投遞** | **本 vertical 命脈復用點** | cron flush + claude -p notifier + in-session push 原樣套用於時限提醒 |
| `auth`（_resolve_trusted_actor / active-request） | floored session 不信任 agent 自填 actor | 律所保密敏感度更高，價值更大 |
| `floor_policy` / `floor_map`（兩道牆 + SME_FLOOR 三態） | 律所信任邊界 + 利衝隔離牆 | 見第 3 節 |
| `access_zones` / `access_zone_grants`（migration 005） | **利益衝突隔離牆（ethical wall）** 的天然載體 | 同層內 case-level 隔離，floor 之外再切 |
| `line` 模組 | 與當事人溝通、收文件、陌生人 intake 路由（潛在新案） | 不變 |
| `company`（id=1 單列） | 單一律所完美契合 `CHECK(id=1)` | `approval_threshold` 改語意（見 1.3）；新增律所統編、所在法院轄區（算在途用） |
| `interaction_log`（審計） | 「誰看了哪個案、誰動了信託帳」 | 用量大增、不變 |
| `session_handoffs` / db.py commit-hook 機制 | Context 壓縮恢復、commit 後 fire-and-forget 觸發投遞 | 不變 |

### 1.2 移除 / 退化

| 項目 | 處置 | 理由 |
|---|---|---|
| `inventory` 模組 + `inventory` 表 + `reserved` / `fulfill_order` 扣庫存鏈 | **整個移除** | 律所無實體商品庫存；文件指標由 `attachments` / `documents` 涵蓋，不需用 inventory 偽裝 |
| `business_units` 機制（`business_entities` 表、`register_business_entity`、各 tool 的 `business_unit` 參數、`customer_entity_terms` 的多 BU 條件） | **退化（保留欄位、固定 NULL、不用），不物理刪** | 單一律所、不做多事業體。`business_unit` 散落十幾張表 + 幾乎每個 tool 參數，物理刪是大工程且高風險；務實做法是「保留欄位固定不用 + 從 tool 參數移除/忽略」。**好處**：escalation / approvals snapshot 等仍引用該欄的程式碼不需改 |
| `qc_failed` / `order_cancelled_shipped` escalation triggers | 移除（換成法務 triggers，見 3.6） | 電商語意 |

### 1.3 改造（換語意、結構近似）

| 現有 | 改成 | 改法要點 |
|---|---|---|
| `orders` 模組 + `orders` 表 | **`matters` 模組 + `matters` 表（案件）** | 砍物流/QC/庫存全鏈；狀態機 `pending→shipped→delivered→paid` → `open→on_hold→closed→archived`；`create_order` 超門檻 in-tx 自建審核（#26）邏輯保留→平移成「收費條件超門檻/成功報酬案」自建審核。詳見 3.1 |
| `crm` 模組 + `customers` 表 | **`parties` 模組 + `parties` 表（當事人/關係人）** | `type` 值域 `customer/supplier/distributor` → `client/opposing/opposing_counsel/third_party/court`；砍銷售聚合欄；加 `id_no`（利衝精準比對）。詳見 3.2 |
| `accounting` 模組 + `transactions` 表 | **營業帳沿用 + 信託帳獨立** | `transactions` 當營業帳（律師費收入、薪資、租金、代墊規費）；信託款一律不進 transactions、另立 `trust_ledger`。詳見 3.3 |
| `hr` / `employees` | 律所角色 | `role`：`partner / associate / paralegal / admin`；`external_partners` → 特約律師 / 委外（鑑定/公證/翻譯）。`update_employee` 的 admin-gate（#10）原樣保留 |
| `customer_entity_terms` | **per-matter 收費條件** | 多事業體折扣 → 收費模式（時薪/包案/後酬/顧問）併入 matters 的 `fee_terms` |
| `snapshots` 指標 | 換指標 | 待遞書狀數 / 本週到期時限數 / 未對帳信託餘額 / 未計時工時 / 逾期收款 |
| `company.approval_threshold` | 信託動支門檻 + 收費審核門檻 | 語意換、結構不變 |

### 1.4 新建（律所獨有，migration 從 **011** 起，沿用「新表只走 migration、不寫進 schema.sql」慣例）

新模組目錄：`modules/matters/`、`modules/parties/`（取代 crm）、`modules/deadlines/`、`modules/conflicts/`、`modules/billing/`（time_entries + 計費）、`modules/trust/`（信託帳）、`modules/documents/`。

**(A) `matters`（案件）— 核心聚合根，所有業務表掛其下**
```
matters(id, matter_no UNIQUE, title, client_party_id→parties,
  practice_area(民事/刑事/行政/家事/智財/勞資/非訟), court, court_case_no(如112年度訴字第XXX號),
  division(股別/承股 — 台灣特有), stage(偵查/一審/二審/三審/執行/調解/結案),
  status(open/on_hold/closed/archived), fee_type(hourly/fixed/contingency/retainer),
  fee_terms TEXT(JSON：時薪率/包案總額/後酬%), lead_attorney, opened_at, closed_at,
  confidential INTEGER DEFAULT 0, retention_until(保存到期日,結案時設),
  business_unit TEXT NULL/*退化保留*/, created_at)
```
重點：**案號/股別/承辦法官會隨審級改變**——掛「審級子紀錄」（`matter_stages` 子表或在 deadlines/documents 帶 stage），不是單一案號欄。委任**每審級重提委任狀**本身是一個流程提醒點。

**(B) `deadlines`（時限）— 本 vertical 命根，時間驅動**
```
deadlines(id, matter_id→matters ON DELETE CASCADE, type(appeal_civil/appeal_criminal/
  appeal_admin/petition_訴願/answer答辯/brief準備書狀/brief_reason補提上訴理由/statute_of_limitation/custom),
  description,
  -- 計算三件套（算錯=過失，service 層確定性算）
  trigger_event(判決送達/裁定送達/公告), service_type(一般送達/寄存送達/公示送達_境內/公示送達_外國/囑託送達),
  service_base_date, statutory_days, statutory_basis(法條,強制非空—反捏造),
  period_type(不變期間/通常法定期間/裁定期間), in_transit_days DEFAULT 0, has_local_agent INTEGER,
  effective_date(送達生效日,含寄存+10/公示+20/+60), start_date(起算日=生效+1),
  statutory_deadline(法定末日,末日順延後), buffer_days DEFAULT 1,
  internal_deadline(=statutory_deadline−buffer ＝老闆的「19天」),
  escalation_lead_days TEXT(JSON如[7,3,1,0]), status(pending/filed/extended/missed/cancelled),
  assignee, needs_manual_review INTEGER(囑託/外國/在途罕見→人工複核),
  filed_at, filed_by, calc_trace TEXT(每步可稽核軌跡), created_at)
```

**(C) `conflict_checks`（利益衝突）— 收案前強制 gate**
```
conflict_checks(id, matter_id→matters NULL(收案前可空), query_name, query_id_no(精準比對),
  result(clear/potential/blocked), hits TEXT(JSON:命中party_id/matter_id),
  resolution(拒接/設ethical_wall/當事人書面同意), approved_id→approvals(potential以上走HITL),
  checked_by, checked_at, created_at)
```
另建 `conflict_index(matter_id, party_name, party_id_norm, party_role)` 供快速掃描。`blocked` 硬接線觸發 escalation 給合夥人。

**(D) `time_entries`（計時）— 時薪/成本命脈**
```
time_entries(id, matter_id→matters ON DELETE CASCADE, attorney, work_date,
  minutes(6分鐘=0.1小時為單位), description, billable DEFAULT 1, rate,
  billed DEFAULT 0, invoice_ref, created_at)
```

**(E) `trust_ledger`（信託/受託款）— 合規紅線，與營業帳物理分離**
```
trust_ledger(id, matter_id→matters, party_id→parties,
  entry_type(deposit/disbursement/transfer_to_fee/refund), amount,
  balance_after(每筆後該當事人結餘,可對帳, CHECK>=0), purpose, bank_ref,
  approved_id→approvals(動支強制走gate鎖金額+收款人), recorded_by, entry_date, created_at)
```
不變量：每 party 信託餘額不可為負；事務所層級「信託專戶總額 = Σ各當事人信託餘額」可對帳。動支硬接線 escalation。

**(F) `documents`（書狀/文件版本）— attachments 升級**
```
documents(id, matter_id→matters ON DELETE CASCADE,
  doc_type(pleading書狀/contract/evidence/court_doc判決裁定通知/correspondence/kyc委任資料),
  title, version DEFAULT 1, status(draft/review/final/filed), confidential DEFAULT 0,
  deadline_id→deadlines(此書狀對應哪個時限,遞交即關閉該時限),
  approved_id→approvals(對外/向法院遞交前審核), file_path(沿用存路徑), authored_by, created_at)
```
「向法院遞交」動作應原子地：`document.status='filed'` → 關閉對應 `deadline.status='filed'` → 取消該 deadline 的 escalation。

---

## 2. system-layer 架構總圖

### 2.1 核心思想（沿用既有解耦）

既有 escalation 把 **「寫入端（in-tx enqueue 一筆已蓋章的 row）」與「投遞端（笨投遞器讀 row → push → 更新 status，不重算身份/措辭）」徹底解耦**。律所框架 = **在既有「投遞三層」前面，新增一條「cron 掃描 → enqueue」的時間驅動寫入端**。

**關鍵泛化**：`pending_escalations` 泛化為通用 `pending_notifications`，加 `kind` 欄區分 `escalation` / `deadline_reminder` / `hearing_reminder` / `billing_reminder` / `conflict_check`。三層投遞器**零改動**（只擴 SELECT 不限 kind）即可推送律所提醒。

### 2.2 跑在哪一層

```
時間驅動（律所新增寫入端）                事件驅動（既有 escalation 寫入端複用）
─────────────────────                  ──────────────────────────────
OS cron 每日掃 deadlines/hearings/billing   業務 service in-tx enqueue
（純 Python 薄殼，鏡像 flush_escalations.py，  （create_matter / 信託動支 / update_employee）
 移除 SME_FLOOR、不解析身份）
        │                                          │
        └──────────────┬───────────────────────────┘
                       ▼
        enqueue 一批 pending_notifications row
        （建立當下蓋章：收件人 coalesce / source_floor 系統讀 / 案號 / 法條，投遞器不重算）
                       │
   ┌───────────────────┼────────────────────────────────────┐
   ▼                   ▼                                      ▼
保證層（主）            品質層                                  即時層（best-effort）
OS cron flush          claude -p single-shot                  in-session push (IPC 注入)
*/2 * * * *            commit 後 fire-and-forget               line-channel owner socket
純 Python urllib       走訂閱(env pop ANTHROPIC_API_KEY)        meta 必 Record<string,string>
零 LLM 成本            全權限(pop SME_FLOOR/_MAP)               idle 律師 session 即時自醒
retry/backoff/failed   SME_NOTIFIER=1 防遞迴                    （#182：int/None 被 CC 靜默丟）
確定性必達★命脈        窄工具白名單、合併人話/利衝判斷
                       claim 租約防雙送(claimed_at CAS,TTL10分)
```

### 2.3 新增 cron job（鏡像 `flush_escalations.py` 薄殼模式，install.sh marker 防重複）

| Cron job | 頻率 | 資料流 |
|---|---|---|
| **A. `scan_deadlines.py`** 時限掃描 | `0 7 * * *`（每日 7:00） | SELECT `deadlines WHERE status='pending' AND (internal_deadline−today) ∈ escalation_lead_days` → 每筆 `enqueue(kind='deadline_reminder', target=assignee, summary='【112訴字X】答辯狀 內部期限6/12(法定6/13) 剩3天 §民訴267')` → commit → 觸發三層 |
| **B. `scan_hearings.py`** 庭期掃描 | `0 18 * * *`（前一晚） | SELECT 明日庭期 → `enqueue(kind='hearing_reminder', summary='明日6/12 09:30 台北地院 言詞辯論 案號X')` |
| **C. `scan_billing.py`** 收款掃描 | `0 9 * * 1`（週一） | SELECT 將到期/逾期帳單 → `enqueue(kind='billing_reminder')`；催款文案走 claude -p 草擬但**對外必走 HITL approval** |
| **D. `flush_escalations.py`**（既有） | `*/2 * * * *` | 泛化掃所有 kind 的 pending（保證層主路，只擴 SELECT） |

### 2.4 claude -p single-shot 呼叫點（品質層，鏡像 `spawn_notifier`）

1. **每日時限摘要生成器**（scan_deadlines 之後）：把某律師當天所有到期 row 合併成**一則排序好的 LINE 摘要**（最急在前、附法條與內部/法定兩日期），而非逐筆洗版。prompt 硬約束「收件人照 row、不同律師不合併」。兜底：保證層 cron 仍逐筆推。
2. **接案利益衝突檢查器**（事件驅動，登錄新案時）：claude -p 讀新案當事人 → query 既有 matters/conflict_index 找對造重疊、關係人交叉。**比純 SQL 強的點**：人名變體（公司全名 vs 簡稱、自然人同名）、間接關聯需 LLM 判斷。寫 `log_decision(confidential=True)` 留底。
3. **收款催繳文案生成器**（選配）：依逾期天數分級寫不同語氣草稿。**對外催款屬對外訊息、須走 HITL `create_approval`**，claude -p 只草擬不直接發。

### 2.5 哪些必須留在互動 session（system-layer 只負責提醒/監看/確定性投遞）

- **登錄案件與起算事件**：判決送達日是人工事實認定，機器無法自動知道；律師/助理輸入後 cron 才有資料算。
- **確認時限已完成**：律師遞狀後 session `mark_deadline_filed`（pending→filed），否則 cron 一直提醒。
- **利衝最終裁決**：claude -p 只標記疑似；是否接案、是否設 ethical wall 由合夥人決定 + `log_decision` 留底。
- **任何對客戶訊息 / 對外催款**：走 HITL `create_approval`。
- **時限例外計算**：在途加計、回復原狀聲請（民訴§164：原因消滅後10日內、逾1年不得）需人工判斷。
- **規則/SOP 寫入**：律所內規（如「內部緩衝統一抓3天」）由老闆經知識庫 flow 落 `store_fact`。

### 2.6 時限計算引擎（已查證，service 層確定性算、絕不 LLM 心算）

時間軸分兩段串接，**不可調換順序**：
```
[送達] →(送達生效規則)→ [生效日] →(民法§120翌日起算)→ [起算日] →(法定期間+在途)→ [理論末日] →(民法§122末日順延)→ [最終到期日]
```
- **R1 起算**：始日不算入，`起算日 = 送達生效日 + 1`（民法§120 II）。
- **R2 中間假日全計入**：理論末日 = 起算日 +(法定+在途−1)，計算過程不跳假日。
- **R3 末日順延**：末日遇週六日/國定假日/休息日 → 逐日推到次一上班日（民法§122）。`is_holiday()` **必用官方辦公日曆表**（行政院人事行政總處 DGPA / data.gov.tw dataset 14718；可用 GitHub `ruyut/TaiwanCalendar` JSON 當 cache 再對賬）——補班/颱風假/調移無法自行硬算。
- **R4 在途期間**（民訴§162 + 司法院《在途期間標準》pcode=B0010020）：先判斷「有住法院所在地的訴訟代理人」→ 在途歸零（§162 但書，律所自辦案件常落此）；裁定期間不吃在途；否則查表（court × party_region，區域外取較長）。**此表無 open data，須人工逐筆建 `transit_period(court_code, party_region_code, days, basis_version)` 表 + 律師覆核、版本鎖定**。
- **R5 不變期間是硬牆**（民訴§163 但書）：法院不得伸縮，引擎**不給「申請延長」選項**；裁定期間才可。
- **R6 回復原狀安全網**：deadline 標 missed 後不直接判死，掛出「原因消滅後10日內 + 距遲誤未逾1年（民事）」路徑，提示須同時補行訴訟行為。
- **R7 送達生效**：一般送達=收受日；寄存送達=+10日（民訴§138 II，2021修正，**不可沿用舊「寄存即生效」，且與行政程序法版不同**）；公示境內=+20、外國=+60（民訴§152）；囑託送達=依回證完成日（標 `needs_manual_review`）。

**核心法定期間種子資料**（已查證，種 deadlines 規則底）：

| 程序別 | 動作 | 期間 | 性質 | 法條 |
|---|---|---|---|---|
| 民事 | 上訴(二審/三審) | **20日** | 不變期間 | 民訴§440 |
| 民事 | 抗告 | **10日** | 不變期間 | 民訴§487 |
| 民事 | 三審補提理由書 | **20日**(逾期逕駁) | 法定 | 民訴§471 I |
| 民事 | 被告答辯狀 | 收狀後10日/期日5日前 | 法定 | 民訴§267 |
| 刑事 | 上訴 | **20日**(2021由10改) | 不變期間 | 刑訴§349 |
| 刑事 | 抗告 / 回復原狀 | **10日**(2023由5改) | 不變/救濟 | 刑訴§406/§67 |
| 刑事 | 二審補提理由書 | 20日(先命補正) | 法定 | 刑訴§361 III |
| 行政 | 上訴 | **20日** | 不變期間 | 行訴§241 |
| 行政 | 撤銷訴訟起訴 | **2個月** | 不變期間 | 行訴§106 |
| 行政(前置) | 訴願 | **30日** | 法定(當不變管) | 訴願法§14 |
| 家事 | 上訴/抗告 | 20日/10日 | 不變期間 | 家事§51準用/§94 |
| 勞動 | 上訴等 | 同民事 | 不變期間 | 勞動事件法§15準用 |

> **法規版本鎖定強制要求**：刑訴上訴(10→20，2021)、刑訴抗告+回復原狀(5→10，2023)兩次修正若引用舊資料直接算錯。`statutory_basis` 標版本日期、定期以全國法規資料庫覆核。

---

## 3. floor / 安全模型在律所的對應

威脅模型不變：**防內部員工透過 agent 越權看不該看的，非駭客級 prompt injection**。律所保密義務（律師法、律師倫理規範）使 floor 模型**更好賣**——client confidentiality 是律師業紅線。兩道牆原樣沿用：① 檔案 sandbox（cwd 限該層資料夾、denyRead 別層/家目錄/business.db/floor-map.json、`--tools` built-in 白名單砍逃逸工具保留 Bash/Edit）；② business-db MCP 工具白名單（`apply_floor_policy` 依 SME_FLOOR 物理移除工具）。

### 3.1 律所層別（機制層描述，**不寫死數量**——隨 onboarding 的 floor-map 客製而變）

現有 floor-map 預設 4 層（confidential/general/external/accounting）。律所對映機制如下（具體層名/數量由 onboarding 拍板、寫死層名屬 Batch B）：

- **全權限層**（SME_FLOOR 未設或 `confidential`）：合夥人 / 老闆 / 開發層。看全部含信託帳全貌、機密法律見解；開機額外檢查 `list_pending_escalations` 待投遞/失敗。
- **財務層**（`financial_visibility=all`、role=manager）：會計/出納。看營業帳 + 信託帳對帳，但不碰案件機密內容 / HR。
- **受僱律師/助理層**（`financial_visibility=none`、role=staff）：看經辦案件，看不到信託帳全貌、看不到 HR PII。
- **對外/前台層**：收文、排程、不看案件實體內容。

floor-map 各層欄位律所語意映射：`financial_visibility` → 信託帳/營業帳可見度；`role` → partner/associate 對映 admin/manager（給 #10 HITL + #9 上報用）；`escalation_target` → 時限/利衝上報收件人。**無 floor-map 條目 = 安全預設 `none`**（等同未分層）。

### 3.2 利益衝突隔離牆（ethical wall）= floor 之外的 case-level 隔離

律師倫理規範「同所連坐」：一律師受利衝限制，同所其他律師亦受限。但**單一衝突案需在同層內再切**——用既有 `access_zones` + `access_zone_grants`（migration 005）：某衝突案資料夾只有特定律師可讀。這是 floor（部門牆）之上的 case-level 隔離，現有兩道牆模型已足以承載。

### 3.3 機密軸對映保密義務

`log_decision` 預設 `confidential=True`（策略/法律見解只合夥人可見）；`store_fact` 預設公開——**導入訪談（定價策略/案件策略/機密見解）最易誤公開**，須明確 `store_fact(confidential=True)`，否則受僱律師/助理層 `query_knowledge` 全看得到 = 實質洩漏委任人機密。

### 3.4 escalation triggers 換法務事件（沿用 #173 in-tx enqueue + 三層投遞）

新 trigger 清單（settings `escalation_triggers` 可覆寫，現有預設 6 個含 `approval_pending`）：
- `deadline_approaching`（時限將至，cron 按 escalation_lead_days 觸發）★ 核心、時間驅動、新增
- `deadline_missed`（時限已逾期，最高優先級）
- `conflict_blocked`（利衝擋下，收案前）
- `trust_disbursement`（信託動支，合規上報）
- `contingency_fee_violation`（家事/刑事/少年案設後酬 → 違反倫理規範§35，擋下並上報）
- `approval_pending`（沿用：對外文件/收費審核一建立即通知簽核合夥人）
- 移除：`order_cancelled_shipped` / `qc_failed`（電商語意）

收件人 coalesce 不變（floor-map.escalation_target → role=boss → permissions=admin → company.boss_line_id → 仍寫 pending）；身份/收件人/來源層建立當下蓋章、投遞器不重算（#27）；漏期限=過失故 **fail-toward-有人收**。

---

## 4. 分階段建置計畫

### Phase 0：地基切換（先做、不可跳）
- 確認 `legal-admin` 分支（已在）；建 migration 011 起；`inventory` 移除、`business_units` 退化（保留欄位固定 NULL、tool 參數移除）。
- floor-map 改律所語意（機制層、暫不寫死層名）；escalation triggers 換法務事件清單。
- **可交付**：乾淨地基 + 法務化的 floor/escalation 框架；既有測試（test_bugfixes/test_get_tools/test_update_employee）綠燈。

### Phase 1（MVP）：時限管理先行 ★
**理由**：這是唯一「漏一個＝執業過失」的痛點、是 system-layer 主張的最佳載體、是相對網頁 AI/通用助理不可取代的核心價值、且基建現成（escalation 三層）只需加 cron 寫入端。
- 新建 `matters`（最小欄位足以掛 deadline）+ `deadlines` + 時限計算引擎（service 層、附 calc_trace + statutory_basis）。
- 種子：核心 12 條法定期間規則 + 辦公日曆表（DGPA）+ 在途期間表（人工建 + 律師覆核、版本鎖定）。
- `scan_deadlines.py` cron + 泛化 `pending_notifications`（加 kind）+ claude -p 每日時限摘要 + in-session push。
- `mark_deadline_filed` 互動工具；開機 readout 露「本週到期時限 / failed 投遞」。
- **單元測試 + 對照司法院線上試算工具（gdgt.judicial.gov.tw）交叉驗證**——天數錯=過失，這段強制測試覆蓋。
- **可交付**：律師沒開 Claude，cron 也在替每個案件倒數法定/內部兩條死線、多閾值（D-7/D-3/D-1/當日）主動推 LINE，附法條依據與 calc_trace。

### Phase 2：庭期 + 文件遞交閉環
- `hearings` 表 + `scan_hearings.py`；`documents` 表（書狀版本 + 對外遞交走 HITL）；遞交動作原子關閉對應 deadline + 取消 escalation。
- **可交付**：庭期前一晚自動提醒 + 書狀遞交即關時限，倒數與文件狀態一致。

### Phase 3：當事人 + 利益衝突
- `crm`→`parties` 改造；`conflict_checks` + `conflict_index` + claude -p 利衝檢查器（收案前強制 gate、blocked 硬接線上報合夥人 + ethical wall 用 access_zones）。
- **可交付**：接案前一鍵利衝檢查（含人名變體/間接關聯 LLM 判斷），符合律師倫理規範強制要求。

### Phase 4：計費 + 信託帳
- `time_entries`（LINE 快速記時降摩擦）+ 計費（台灣四結構：按審級/鐘點/單件/後酬 + 倫理規範§35 合規 gate：家事/刑事/少年禁後酬偵測擋下上報）；`trust_ledger`（動支走 HITL gate 鎖金額+收款人 + 硬接線上報 + 不可負 + 總額對帳）；`accounting` 拆營業帳/信託帳。
- **可交付**：時薪計費全鏈 + 信託帳合規分離（即使台灣不強制專戶，分帳本身是賣點）。

### Phase 5：結案歸檔 + 報表
- 結案觸發帳務結清檢核 + 卷宗歸檔 + 設保存到期日（`retention_until`，年尺度 cron）；snapshots 換律所指標；報表（待遞書狀/到期時限/信託對帳/工時）。
- **可交付**：完整 matter lifecycle 閉環 + 律所儀表板。

---

## 5. 競品差異化定位

> **「跑在 LINE 上、人沒開電腦也在替你倒數法定死線的 AI 律所行政助理。」**

台灣市場兩類玩家結構性互斥：**(A) 法學/AI 內容工具**（Lawsnote 七法 NT$7,800/人/年、LawChat 等）幫你查法律 + 生書狀，但**完全不管案件死線、不管行政**；**(B) 事務所管理系統**（康瓏、文易管、世盈、ezip、益盛）有期限/計費/利衝（table-stakes），但全部是 **(1) 被動式——要登入工作平台/開系統才看得到提醒、(2) 無 LINE、(3) 無 AI、(4) 價格不透明需業務電洽、(5) 導入重**。**沒有一家把兩者 + LINE 主動推播縫起來。**

國際工具（Clio 估值 50 億美元、MyCase、PracticePanther）成熟度高、Clio Manage AI 能從法院文件自動抽死線——但它們的 court-rules engine 綁**美國法院規則、台灣用不了**，且全部是 web/app 被動式，**沒有一家是 system-layer 時間驅動、人沒開系統仍在倒數並主動戳你**。

切入點正是這整片空白：台灣法定期間相對單純（20/10/5日 + 在途 + 末日順延），「用送達日驅動 + 確定性引擎算 + LINE 主動推 + system-layer cron 倒數」就能做到八成價值。**死線天生是 time-driven，而既有 escalation 三層投遞基建（cron 保證層確定性必達 + claude -p 品質層寫人話 + in-session 即時層）就是現成範本**——把 `pending_escalations` 換成 `pending_deadlines/notifications` 即可。司法院免費就有日期試算工具，所以**護城河不在「會算日期」，而在「把每個案件的送達日抓進來、自動倒數、主動提醒、且人沒開電腦也在跑」**——這正是老闆架構主張的核心，也是本系統 runtime（Claude Code 訂閱、非 metered）能撐得起的場景。

---

## 6. 風險與未決問題清單（給老闆拍板）

**A. 範圍決策（決定 MVP 邊界）**
1. **信託帳（trust_ledger）做不做、何時做？** 台灣**無美國式強制信託專戶法制**（無 IOLTA），但倫理規範有「代收款應即時交付、不得挪用」義務。選項：(a) Phase 4 做完整分帳（合規賣點，但增複雜度）；(b) MVP 只做「代收未交付」提醒、帳本後置；(c) 不做、留 onboarding 客製。建議 (b)。
2. **計時計費（time_entries + billing）做不做？** 律師最討厭記時、最容易漏（漏記=少收錢）。選項：(a) 完整四結構計費；(b) 只做 LINE 快速記時降摩擦、出帳後置；(c) 不做（很多小所用按件計費規避記時）。
3. **利益衝突檢查深度？** 選項：(a) 純 SQL 姓名/統編精準比對（低風險、快）；(b) 加 claude -p 人名變體 + 間接關聯判斷（強但有誤判風險，需律師最終裁決）；(c) (a) 為 MVP gate、(b) 為 Phase 3 增強。建議 (c)。

**B. 法律正確性風險（算錯=執業過失，最高優先）**
4. **在途期間表**無 open data、須人工逐筆建 + 律師覆核 + 版本鎖定——誰負責建表覆核？建議 MVP 預設「有住法院所在地律師代理 → 在途=0」（§162 但書，律所自辦常成立），罕見組合標 `needs_manual_review` 不自動算死。
5. **法規版本鎖定**：刑訴上訴(2021)、刑訴抗告/回復原狀(2023)兩次修正——需定期以全國法規資料庫覆核機制（誰排程覆核？）。
6. **「19天」的真相分歧**：研究指向兩個來源——(a)「20日法定 − 1安全緩衝」、(b)「金門/馬祖在途上限本就19日（官方值）」。引擎**兩者都支援、用查表值不寫死19**；buffer_days 預設1（=19）還是更保守3天，由老闆/律所政策定。

**C. 架構/退化風險**
7. **business_unit 退化（保留欄位固定NULL）vs 物理刪**：建議退化（低風險、不改 escalation/approvals snapshot 引用）；但需確認所有 BU 篩選 tool 參數確實移除/忽略，避免殘留誤導。
8. **Claude Code channels 是 research preview（非 GA）**：LINE 投遞協定可能變——產品風險已知，是否影響交付時程承諾？

**D. 商業/合規護欄**
9. **倫理規範§35 合規 gate**：「明示酬金」「家事/刑事/少年禁後酬」做成自動檢查 + 上報——做到多嚴（提醒 vs 硬擋）？建議硬擋後酬違規（高風險不可逆）、酬金明示做提醒。
10. **對外催款文案**：claude -p 草擬 + HITL 審核才發——確認不可 claude -p 直接發給當事人（屬對外訊息）。

**E. 關鍵實作 gotcha（沿用既有教訓）**
- 改 line-channel 必 `pkill` 舊 webhook owner 再重啟；改 business-db 必重啟 session 才載新碼。
- in-session push 的 channel notification `meta` **必為 `Record<string,string>`**（int/None 被 CC 靜默丟整筆 = #182 根因）。
- cron 薄殼必 `os.environ.pop("SME_FLOOR")`、claude -p notifier 必 `pop("ANTHROPIC_API_KEY")`（走訂閱）+ `SME_NOTIFIER=1` 防遞迴。

**關鍵檔案路徑（供實作）**：
- escalation 三層 + enqueue 蓋章 + notifier 範本：`/mnt/d/gitDir/sme-ai-kit/mcp-servers/business-db/shared/escalation.py`
- cron 薄殼母版（scan_deadlines/hearings/billing 照此寫）：`/mnt/d/gitDir/sme-ai-kit/mcp-servers/business-db/flush_escalations.py`
- commit 後 fire-and-forget 觸發 + rollback 清旗標：`/mnt/d/gitDir/sme-ai-kit/mcp-servers/business-db/shared/db.py`
- crontab 安裝段（marker 防重複）：`/mnt/d/gitDir/sme-ai-kit/install.sh`
- floor 兩道牆：`/mnt/d/gitDir/sme-ai-kit/mcp-servers/business-db/shared/floor_policy.py`、`shared/floor_map.py`、`data/floor-map.json`、`floor-map.example.json`
- 改造主力：`modules/orders/`（→matters）、`modules/crm/`（→parties）、`modules/accounting/`（拆信託帳）
- 移除：`modules/inventory/`、`shared/business_units.py`（退化）
- 新表 migration 從 `migrations/011_*.sql` 起（現有止於 010）
- 機制契約：`/mnt/d/gitDir/sme-ai-kit/CLAUDE.md`