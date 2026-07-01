# pleading-manager 整合回寫（選配）— 把 sme 算好的末日 / 收文寫進地端案件 UI

> **何時載入**：本所同時用 pleading-manager（地端書狀/案件管理 UI）、且案件已綁定對應、要把 legal-admin 算好的時限 / 收到的文書回寫過去給律師在 UI 看。
> **單向 sme→pleading**：legal-admin 是引擎、pleading 是 UI。pleading 不回算、不回呼 sme。少了 pleading，legal-admin 引擎/提醒照常跑（見〈失敗情境〉「未配置」）。

## 前提：整合「已配置」才做（inert）

回寫**只在整合已配置時執行**，否則整段略過、當它不存在（解耦鐵則：additive + inert，延伸到指令層、不只 DB）。「已配置」= 三者皆備：
1. 現場有 pleading MCP（提供 `upsert_deadline` / `upsert_correspondence` / `get_deadlines` / `get_correspondence`）——Task C 接線；工具不在＝未配置。
2. 該案 `matters.pleading_case_id` 有值（已綁定 pleading 案件）。
3. 拿得到該案 **lead_attorney 的 pleading token**（Task D 的 token 存放/選取）。

**任一不備 → 不回寫、不報錯、不提醒**（pleading 純單機、legal-admin 純單機，各自完整）。

## 不變式（細節見 KB 契約 `contract_sme_pleading_integration` v3）

- **去識別化**：回寫只帶「期限類型 + 日期 + 法條依據 + 去識別化摘要」，**絕不帶當事人姓名 / 案由**（同 `mark_deadline_calendared` 既有去識別化規則；當事人身分留 pleading 自己的客戶主檔）。寫前可用 `screen_calendar_text` 自檢。
- **pleading 不自算**：`internal_deadline`（working）由 legal-admin 算好回寫，pleading 只顯示、永不自己推。`statutory_deadline`（法定硬底線）與 `internal_deadline` **兩個都回寫**。
- **不蓋手填**：sme 只 upsert 自己 `source='sme_engine'` 的列（以 `external_ref` 認）；律師在 pleading 手填的列（`source='manual'`）永不碰。同一真實末日若兩來源並存 → 由 pleading UI 並陳讓律師手動併、不自動 merge。

## 身分：用該案 lead_attorney 的 token（§127）

回寫一律以**該案 lead_attorney 的個人 pleading token** 呼叫（非 service 帳號）。理由：期限是有法律後果的寫入、背後必須是真實當責律師；pleading gate 套該律師真權限、稽核留痕 = 該律師。row 帶 `source='sme_engine'` + `computed_by` → pleading 稽核呈現「律師X，經 sme 引擎自動回寫」、**不偽裝成律師手填**。token 取得 / 選取 = Task D（依 `matters.lead_attorney` 選、存於全權限層專屬、不經任何工具回傳）。

## 末日回寫（#1）

確認入庫（`create_deadline` 含 `confirm_intake_id`）或 `amend_deadline` 重算後、若整合已配置：

1. 呼 pleading `upsert_deadline(case_id=<pleading_case_id>, external_system="sme", external_ref=<sme deadline id>, source="sme_engine", statutory_deadline, internal_deadline, status, type, period_type, severity, period_unit, period_value, statutory_basis, statutory_basis_version, trigger_event, service_base_date, statutory_days, needs_manual_review, calc_trace, computed_by, reviewed_by, reviewed_at)`（欄位定義見 KB `pleading_wave1_tool_signatures`；冪等 by external_ref，同 id 再呼 = update）。
2. 取回傳的 pleading 列 id，呼 `mark_deadline_calendared(deadline_id=<sme deadline id>, calendar_event_id=<pleading 列 id>, calendar_provider='pleading')` 存回對位（pleading 視為一個行事曆 provider，沿用既有去重/更新機制）。
3. deadline 狀態變動（`mark_deadline_filed` 已遞交 / `amend` 改期 / 取消）→ 同 `external_ref` 再 upsert 帶新 `status` 即同步。

## 收文回寫（#2）

`stage_deadline_intake` 收到文書當下（整合已配置）→ 呼 `upsert_correspondence(case_id, external_system="sme", external_ref=<sme intake id>, source="sme_engine", direction="in", doc_type, service_base_date=收文日, document_date, extracted_summary=去識別化摘要, stated_period_days, linked_deadline_ref=NULL, status)`。
- 律師一鍵確認、`create_deadline` 入庫後 → **同 `external_ref` 再 upsert 一次**，把 `linked_deadline_ref` 補上該 deadline 的 `external_ref`（收文先入、deadline 後生；nullable + 可二次覆寫）。
- 來文機關 / 完整主旨 / 附件真檔 = 律師在 pleading 本地補，sme 去識別化端不帶。

## 撤回 / 取消（void vs cancelled）

- intake 被 `resolve_deadline_intake(action='discarded')`、或回寫出錯需撤回 → 同 `external_ref` upsert `status='void'`（整合撤回、留痕、pleading 排除 active+提醒；**update 非 delete**）。
- 業務上真的取消 deadline → `status='cancelled'`（語義與 void 分開：cancelled=業務取消、void=整合撤回/錯誤回寫）。

## 雙重提醒（避免合售雙報）

合售時末日同時在 legal-admin（escalation + LINE、全所一份）與 pleading（#1 自有提醒）。約定：**`source='sme_engine'` 的列由 pleading 抑制自身提醒、改由 legal-admin 報**（legal-admin 提醒模型較完整）；pleading 純單機時才用自己的提醒。此抑制在 pleading 側落地（你這邊不需動作、知道即可）。

## 接線（C：薄 pleading REST client；真 e2e 待整合環境）

**per-call token 路線（已拍板）**：背景引擎程式化多律師回寫天生需 per-call 身分，故 sme 引擎走
**pleading REST API 直連、per-request 帶該案承辦律師 token**（Cookie pm_session / Bearer）；MCP adapter
留給互動式 LLM（一 session 一律師）的鏡子。鐵律校準為「**REST＝唯一契約面、MCP＝其 LLM 鏡子**」。
（否決「auth-token 當工具參數」——會落 LLM tool-call transcript＝洩密。）

guardrails（守住 6 解耦鐵則）：REST 視為**穩定 versioned 契約面**（不碰 pleading 內部）；sme REST client
與互動路徑一樣**薄＋去識別化**（同 payload／external_ref 冪等／不帶當事人名）。

- **C＝sme 側「薄 pleading REST client」**：依 Task D 選出的該律師 token、per-request 呼 pleading REST
  端點（對應 upsert_deadline / upsert_correspondence / get_*）；whoami 探活也走 REST。
- token 選取＝Task D（已 ready、不變：互動=觸發者、自主=該案 deadline.assignee→lead_attorney；僅 active；
  whoami 探活）。
- **真 e2e（實呼 pleading live REST）待整合環境**（pleading 部署 + 律師自發 token）；client 碼可先 mock 單測。
- **inert**：未配置 pleading REST（無端點/無 token）→ 整段回寫略過、legal-admin 純單機照跑。

## 失敗情境判讀（不是壞、是解耦在保護你）

- **整合未配置（無 pleading MCP / 未綁定 / 無 token）**：略過回寫、不報錯。legal-admin 引擎、提醒、intake 全照跑。這是預設、正常。
- **回寫得 404（case 不存在）**：pleading 該案被刪了。→ `link_matter_pleading(matter_id, '')` 清掉對應（回純單機）、本次回寫略過。不重試、不崩。
- **回寫得 401（token 失效 / 撤銷）**：該律師 token 過期。→ 略過本次回寫、標記請該律師重新 provision token。**pleading 鏡像會暫時落後、但 legal-admin 引擎/提醒不受影響**（回寫是 best-effort 鏡像、非權威來源）。
- **背景 cron 回寫**：`scan_deadlines.py` 等無 live session 的回寫，一樣用該案 lead_attorney token、同 containment；token 失效同上 graceful。

> 交叉參考：寫入契約與冪等/auth = KB `contract_sme_pleading_integration`、工具簽章 = KB `pleading_wave1_tool_signatures`、去識別化與部署 = [privacy-deploy.md](privacy-deploy.md)、外部行事曆回填 = [calendar-sync.md](calendar-sync.md)、root 機制（escalation / HITL / 機密軸）= CLAUDE.md。
