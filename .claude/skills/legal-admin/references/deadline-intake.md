# 時限收件（deadline intake）— 核心 loop 的步驟 1~3

> 觸發：律師/助理在 LINE 傳判決書／裁定／開庭通知（照片或 PDF）、或文字描述「某案某文書某日送達，幫我算上訴/抗告期限」。
> 這是整個產品最關鍵的流程。**算錯期限＝執業過失**，每一步都有反捏造與 HITL 防線。

## 流程總覽

```
丟檔案 → 你讀檔抽取（送達日+文書類型+教示天數）→ 推回 LINE 給人一鍵確認
   → 確認後 create_deadline（引擎確定性算雙日期）→ 寫行事曆（去識別化）→ 回報
```

## 步驟 1：讀檔抽取（你做、但只抽事實、不算天數）

LINE 訊息含 `[圖片]` 路徑或 PDF → 用 Read 工具看內容。抽出這幾個**事實**（不要算天數、不要推斷法條）：

1. **文書類型** → 對應 `type`：
   - 一審判決 → 上訴：民事 `appeal_civil` / 刑事 `appeal_criminal` / 行政 `appeal_admin` / 家事**訴訟事件** `appeal_family`
   - 裁定 → 抗告：民事 `abjection_civil` / 刑事 `abjection_criminal` / 家事**非訟事件** `abjection_family`（10 日、與家事訴訟上訴 20 日不同、勿混用）
   - 第三審上訴理由書補提 `appeal_reason`、訴願 `petition_appeal`、支付命令異議 `payment_order_objection`
   - **限期補正裁定**（命補正當事人能力／法定代理／書狀程式／裁判費等）→ `type='correction'`（裁定期間、特殊處理見下方「限期補正」）
   - 開庭通知 → 不是「期間」是「期日」，建 `type='custom'` + `period_type='court_set'`、或直接寫行事曆庭期（見下方「開庭通知」）
2. **送達日 / 基準日** → `service_base_date`（YYYY-MM-DD）：判決書/裁定上的「送達證書收受日」、或 LINE 訊息裡人講的收受日。
3. **送達類型** → `service_type`：一般 `normal` / 寄存送達 `registered_deposit`（+10）/ 公示送達境內 `public_domestic`（+20）/ 外國 `public_foreign`（+60）/ 囑託 `commissioned`（需人工複核）。**看不出來就當 `normal` 並在確認步驟問人。**
4. **判決書教示天數** → `stated_period_days`：判決書末頁「如不服本判決，得於收受後 __ 日內提起上訴」那個數字。**有就一定要抓**——引擎拿它跟採用的法定天數交叉比對（安全網）。
5. **文書作成日** → `document_date`：判決/裁定上的**裁判日期**（非送達日）。**刑事案件、再審/回復原狀翻出的舊案一定要抓**——法版檢核依文書作成日判斷適用哪版法（舊判決可能修法後才送達，只看送達日會漏）。
6. **當地代理人** → `has_local_agent`：律師住法院所在地→在途歸零（律所自辦常為是）。不確定沿用案件設定（傳 -1）。

> **抽取不確定就標出來問人，不要猜**。掃描檔糊、巨型判決（數百頁）找不到送達證書/教示頁 → 在確認步驟明講「教示頁沒抓到、請補送達日與天數」。

## 步驟 2：一鍵確認才入（HITL，人擋在中間）

把抽出的事實**整理成一條確認訊息**推回 LINE，請對方確認或修正，**不要直接 `create_deadline`**：

```
【請確認時限資料】案件：{matter}
- 文書類型：一審民事判決 → 提起上訴（appeal_civil）
- 送達日：2026-06-01（一般送達）
- 判決書教示：20 日
- 緩衝：3 天（內部期限 = 法定 − 3）
回「確認」即入庫並寫行事曆；要改回我哪裡不對。
```

**推這條確認訊息的「當下」同時呼叫 `stage_deadline_intake`** 把抽出的事實暫存成可掃描的待確認 backlog（只存事實、不算天數、不建 deadline）：

```
stage_deadline_intake(
  extracted_summary="王案一審民事判決 2026-06-01 送達、教示20日",  # 推回確認的那條摘要
  matter_id=<案件ID 或 0（還沒建案）>,
  matter_label="王案一審民事判決",      # 去識別化、勿放當事人姓名
  doc_type="appeal_civil",
  service_base_date="2026-06-01",
  stated_period_days=20,
  document_date="2026-05-28",
  submitted_by="<丟檔的人>",
)
```

回傳的 `#intake_id` 記著、步驟 3 入庫時帶回。

**為什麼一定要 stage**：核心 loop 刻意把人擋中間，副作用＝對方忘了回「確認」→ 時限沒入庫 → 一般掃描掃不到 → **隱形漏掉**（漏期＝執業過失）。暫存讓「待確認」變成 `scan_unconfirmed_intake.py` 能跟催的 backlog（逾 4h/24h/72h 主動提醒「有 M 件待確認、最久 X 小時」），人忘了回不會靜默漏掉。

對方回「確認」→ 才進步驟 3。對方修正 → 改完再確認。確定不是時限（誤傳/重複）→ `resolve_deadline_intake(intake_id, action='discarded')` 收掉、停止跟催。**這一關不可省**（SPEC 核心：律師業必須人擋在中間）。

## 步驟 3：create_deadline（引擎確定性計算，你絕不心算天數）

確認後呼叫 `create_deadline`。**天數、法條、雙日期全由引擎算**，你只負責把事實餵對：

```
create_deadline(
  matter_id=<案件ID>,
  type="appeal_civil",            # 種子 type 會自動回填 statutory_days/basis/period_type/description
  trigger_event="一審判決送達",
  service_base_date="2026-06-01",
  service_type="normal",
  stated_period_days=20,           # 判決書教示天數（安全網、有就帶）
  document_date="2026-05-28",      # 文書作成日（裁判日；法版檢核用，刑事/舊案一定要帶）
  buffer_days=3,                   # 內部緩衝（老闆的「19天」概念 = 20−1；可設更保守）
  has_local_agent=-1,              # -1=沿用案件設定
  created_by="<操作者>",
  confirm_intake_id=<步驟2的 intake_id>,  # 帶回步驟2暫存 id → 同 tx 關閉待確認跟催 backlog
)
```

- **type 在種子表內**（appeal_civil/abjection_civil/appeal_criminal/abjection_criminal/appeal_admin/appeal_family/abjection_family/appeal_reason/petition_appeal/payment_order_objection）→ `statutory_days`/`statutory_basis`/`period_type`/`description` 自動回填，你不用查。
- **type 不在種子表**（罕見特別期間）→ **必須**手動帶 `statutory_days` + `statutory_basis` + `period_type`，否則引擎擋下（反捏造：缺法條依據不給算）。**法條依據要查證、不要編**，查不到就請律師給。
- **無當地代理人又要算在途** → 帶 `court_region` + `party_region`（如 `court_region="taipei"`, `party_region="kinmen"`）查在途表；查不到引擎標複核。
- 回傳含 `internal_deadline`（盯這個）/ `statutory_deadline`（底線）/ `calc_trace`（逐步軌跡）。**回報給人時兩個日期都講、叫他盯內部期限。**

入庫成功後 → 進 [calendar-sync.md](calendar-sync.md) 寫行事曆（去識別化）+ `mark_deadline_calendared` 回填 event_id。

## 開庭通知（期日、不是期間）

開庭通知是「某日某時到某法庭」的**期日**，不是倒數「期間」——**不走 `create_deadline`**（時限引擎只算「期間」、會擋下 `statutory_days=0`）。處理：
- 寫進行事曆（庭期 event：去識別化代號 + 日期 + 時間 + 法庭，見 calendar-sync）。
- 要系統提醒就 `create_task`（title=庭期說明、due_date=開庭日、assignee=承辦律師）。
- 每日彙整 cron 會讀「事務所慣用行事曆」當天/近期事件、自然涵蓋庭期（見 daily-digest）。

## 限期補正（裁定命補正、`type='correction'`）

法院裁定命「於本裁定送達後 ○ 日內補正」（補正當事人能力、法定代理權、書狀程式、繳裁判費等程式欠缺）。
**漏補正＝駁回起訴／上訴**，小所最高頻時限之一，但與上訴/抗告有一個關鍵差異要特別小心：

- **天數不是法定固定值、是法院在這紙裁定當下訂的**——多少天只有讀那份裁定才知道。引擎沒有、也不會替
  `correction` 預設天數（反捏造鐵律：上訴 20 日寫死在法律可回填，補正期間寫死＝臆測）。你**必須讀裁定
  主文抓出那個 ○ 日**填 `statutory_days`。
- `statutory_basis` 填的不是法條、是**那紙裁定的文號**（如「臺灣臺北地方法院 114 年度補字第 ○ 號裁定」）。
- `type='correction'` 會自動帶 `period_type='court_set'`（裁定期間、在途歸零·§162）、`severity=orange`、描述、觸發語。
- **一律標 `[需人工複核]`**：裁定天數純人讀、沒有固定法定種子可交叉驗證，是反捏造風險最高的
  一類——引擎強制複核，請律師確認天數無誤後再倚賴。這不是出錯、是保護。

抽取（步驟1）→ 一鍵確認（步驟2，`doc_type='correction'`）→ 入庫：

```
create_deadline(
  matter_id=<案件ID>,
  type="correction",
  trigger_event="補正裁定送達",                       # 留空會自動填
  service_base_date="2026-06-15",                     # 補正裁定送達日
  service_type="normal",
  statutory_days=10,                                  # ← 必填！讀裁定主文「○ 日內補正」的 ○
  statutory_basis="臺北地院114年度補字第123號裁定",     # ← 必填！裁定文號（非法條）
  buffer_days=1,
  created_by="<操作者>",
  confirm_intake_id=<步驟2的 intake_id>,
)
```

漏填 `statutory_days` 或 `statutory_basis` → 引擎給「請讀裁定」的針對性提示擋下，不會用 0 硬算（反捏造）。

## 消滅時效（請求權時效、`type='limitation'` / `statute_*`）

這跟上訴/補正是**不同性質的東西**——不是「收到某文書後倒數」，是律師主動算「這個請求權（債權／損害賠償）還能不能行使」。三個關鍵差異，務必小心：

1. **起算點是法律判斷、不是送達日**：民§128「自請求權可行使時起算」。何時可行使、起算日（尤其侵權「知悉時」）要律師認定 → `service_base_date` 填「請求權可行使日」（**不是**任何送達日）、引擎**一律標需人工複核**，請律師確認起算日。
2. **期間是「年」、依曆算（民§121/§123）**：15／5／2 年。引擎用曆法（相當日之前一日、閏日落該月末日），**不可硬轉天數**。不必你算，餵對 type + 起算日即可（`period_unit`/`period_value` 種子自動帶）。
3. **無在途、無送達加算、不適用回復原狀**（時效完成是實體權利消滅、非程序遲誤）。

常用 type（種子自動帶期間/法條/描述，你只給起算日）：
- `statute_125` 一般請求權 **15 年**（民§125）
- `statute_126` 利息/租金/贍養費/退職金等定期給付 **5 年**（民§126）
- `statute_127` 旅店/運送/租賃/醫藥/**律師會計師報酬**等八款 **2 年**（民§127）
- 侵權損害賠償 §197 是**雙時鐘**，建**兩筆**、各帶不同起算日（不要只建一筆）：
  - `statute_197_2y`：自**知有損害及賠償義務人時**起 2 年（`service_base_date`＝知悉日）
  - `statute_197_10y`：自**侵權行為時**起 10 年（`service_base_date`＝行為日）
  - 兩者先到者時效完成。

```
create_deadline(
  matter_id=<案件ID>,
  type="statute_125",              # 種子自動帶 period_unit=year / period_value=15 / 民§125 / 描述
  trigger_event="請求權可行使",
  service_base_date="2010-01-01",  # ← 請求權可行使日（律師判斷、不是送達日）
  buffer_days=30,                  # 消滅時效通常提前很多盯（可設數月）
  created_by="<操作者>",
)
```

§122 末日順延（末日遇休息日是否順延）於消滅時效**見解分歧**：引擎依曆算末日、不自動順延，但已強制複核——由律師個案決定。時效可中斷（民§129 請求/承認/起訴 → 重新起算），中斷後請律師更新起算日重算。

## 失敗情境判讀（遇到這些不是系統壞、是引擎在保護你）

- **回傳帶 `[需人工複核]`** → 引擎偵測到不確定因素（送達/在途/**法版/教示比對/裁定期間**之一）。看 `get_deadline` 的 `calc_trace` 知道是哪一項：
  - 「法版檢核：文書日期早於修法施行日…」→ 判決日早於該法條期間修法（如刑訴§349 2021-06-16、§406 2023-06-21）。**舊判決可能適用舊法天數**、引擎不臆測重算 → 請律師確認適用版本與確切施行日。
  - 「裁定期間（court_set）：補正期間 X 日採律師讀裁定填寫…」→ 限期補正等裁定期間，天數是你從裁定讀進來的、引擎強制複核（無固定法定種子可交叉驗證）。**核對裁定主文天數無誤即可**，確認後當正常時限盯。這不是出錯、是反捏造保護。
  - 「消滅時效末日…依曆計（民§121/§123）；§128 起算點『請求權可行使時』屬法律判斷…」→ type=limitation/statute_*。**起算日（請求權可行使時／侵權知悉時）是你給的法律判斷**、引擎一律標複核。確認起算日 + 時效有無中斷（民§129 請求/承認/起訴會重新起算）後再倚賴；侵權記得 `statute_197_2y` + `statute_197_10y` 兩筆都建。
  - 「教示比對：判決書教示 X 日 ≠ 引擎採用 Y 日」→ 可能法定期間判斷錯（type 選錯）或屬特別期間。**回去檢查 type 對不對**，真的是特別期間就手動帶正確 `statutory_days` + `statutory_basis`。
  - 「辦公日曆未載入：所需年度…」→ 該年度國定假日沒匯入、末日順延算不準。請維護者匯入該年度 `office_calendar`（見 privacy-deploy 部署）。
  - 「囑託送達 / 無當地代理人查無在途」→ 回證日/在途天數要人工認定，律師確認後手動帶 `in_transit_days` 或 `service_base_date`（回證日）。
- **「statutory_basis 不可為空」** → type 不在種子表又沒手動帶法條。請律師提供法條依據，不要自己編一個。
- **「案號 已存在」** → 該案號已有 matter，改用 `find_matter_by_party` 或 `get_matter` 找到既有案件、把時限掛上去。
