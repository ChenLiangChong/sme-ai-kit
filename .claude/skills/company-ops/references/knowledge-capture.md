# 知識萃取專業指南

## 觸發情境

**日常知識萃取**：所長說「從現在開始...」「我們的規定是...」「以後遇到這種情況...」
**系統導入**：「第一次設定」「幫我建立系統」「導入」「開始使用」

---

## 零、導入訪談標準流程（新律所首次部署）

> 每次交付給新事務所、依此流程訪談建檔。不需一次做完，可分 2-3 天；所長累了就停、下次接續（用 `create_task(category='admin')` 追蹤每步）。
> **反捏造**：本流程只設「組織與營運層慣例」（人員/權限/案件編號/內部緩衝/行事曆）；**法定時限天數、法條、在途一律 legal-admin 引擎確定性計算**，導入訪談絕不臆造任何法律數值。
> **移出產品（不在此導入、見 `docs/legal/SPEC.md`〈不做〉）**：記帳/會計、計時計費、信託帳、利益衝突「自動偵測」、對外客戶通道、對外行銷。問到這些 → 誠實說「系統不內建、可現場另案客製」，**不要假裝已設定**。

### Step 1：事務所基本資料

`update_company` 設定核心資訊：
```
update_company(name='○○法律事務所', industry='法律服務', boss_name='主持律師姓名', approval_threshold=0)
```
描述性資訊用 `store_fact(category='company')`：統一編號、所在地縣市、**平常往來法院**（如台北地院 / 士林地院 / 台灣高等法院——這是時限引擎「在途期間」查表的輸入事實，**不在此心算天數**）、執業領域、所規模。

### Step 2：人員名冊 + 權限分層 + LINE 綁定（問卷第一、二節）

逐位 `register_employee`：姓名、對外職稱（主持律師 / 合夥律師 / 受僱律師 / 法務助理 paralegal / 行政 / 工讀）、`role`（boss/manager/staff 底層）、`permissions`、所屬執業領域組（`department`）。
```
register_employee(name='○○○', role='manager', department='訴訟組', permissions='manager', phone='...')
```
- **權限四級**：admin（改人事 / 看全部 / 不可逆動作把關，通常主持律師）、manager（簽核 / 較高權限、不碰人事）、basic（建案 / 記時限 / 查案）、none（停用）。預設：主持律師 = admin、受僱律師 = basic、助理 / 行政 = basic、工讀 = basic 或 none。
- **LINE 綁定**：每人傳「我是○○○」→ `lookup_employee` → 確認 → `update_employee(line_user_id=)`。⚠️ **主持律師（boss）必須第一個綁定**，後續審核 / 時限通知都發給他；確認他已加入所內 OA 為好友（沒加→push 靜默失敗）。
- **escalation 主收件人**：問「漏掉就出事、要第一個被叫醒的人是誰？」（時限快到 / 逾期、審核待簽）→ `update_company(boss_line_id=主持律師 verified LINE user_id)`，fail-toward-有人收（見 CLAUDE.md〈上報（escalation）機制〉）。
- **部門安全層（floor）判斷**：問「有沒有資料不能讓所內所有人都看到？」（受僱律師只看自己案、助理不看 HR / 機密見解）。
  - **個人所 / 全員互信小所 → 不分**（不設 `SME_FLOOR`、全權限單人；`confidential` 與 floor gate 保留 inert 升級路）＝**預設**。
  - 要分 → 用「誰看不到什麼」描述、配 `data/floor-map.json`（見 setup.md 多人版段）。**誠實邊界**：floor 擋得住工具去留 / 財務 / HR / 機密知識過濾，但**案件資料的列級過濾（#11）尚未落地**——**不可**向所長宣稱「設了 floor 該層律師只查得到自己案件」。

### Step 3：執業領域

問「主要承辦哪些領域？」→ `store_fact(category='sop', title='承接執業領域', content='民事 / 家事 / ...')`。建案時用 legal-admin `create_matter(practice_area=)` 分類（civil/criminal/family/admin/ip/labor/non_litigation）。**這是資料分類、非多事業體**（`business_unit` 留空 inert）。

### Step 4：案件慣例（編號 + 利益衝突 SOP）

`store_fact(category='sop')` 記：
- **案件編號規則**（如 `M-2026-013` 或本所慣例）。
- **利益衝突檢核 SOP**：⚠️ **系統不自動偵測利益衝突**（SPEC 移出產品；`matters` 只有 `client_name`、無對造結構化欄）。收新案的人工 SOP：律師用 `find_matter_by_party(name)` 撈同名既有當事人**當輔助清單**，但**衝突判斷 100% 靠律師人工**、AI 只列同名、**絕不下「無衝突」結論**。把這條 SOP 存起來。

### Step 5：時限內部慣例（律所一級設定）

法定天數是引擎算的；**內部緩衝、覆核責任**是各所慣例 → `store_fact(category='sop')`：
- **內部緩衝天數**：法定期限往前抓幾天當內部死線（如上訴期內部提前 5 天）。
- **誰覆核時限計算**：算完誰複核（`mark_deadline_reviewed`）、責任歸屬到人。
- **送達日輸入責任**：誰負責把判決書送達日填對（填錯＝全盤錯）。
- **法院往來 / 在途**：平常往來法院（Step 1 已記）；罕見跨區組合引擎會標 `needs_manual_review` 由律師確認。

### Step 6：請假制度（選用）

先問「要不要正式管請假？口頭講就好？」口頭 → 跳過。要管 → `register_leave_type`（特休 / 病假 / 事假 / 婚假 / 喪假 / 生理假 / 公假-出庭作證，天數依規章 / 勞基法、**不發明**）+ 逐人 `set_leave_balance`。詳見 `leave-ops.md`。

### Step 7：行事曆整合 + 隱私部署

- **行事曆（核心外部依賴）**：問「事務所實際用什麼行事曆？」（Google Calendar / 其他 / 紙本）。Google → 接**該所自己的** Google 帳號（OAuth / service account）；沒有 → 退「系統內建 + 選配同步」。寫入走可插拔行事曆 MCP，**去識別化**（只放案件代號 + 期限類型 + 日期、不放當事人名 / 案由）。
- **隱私（律師保密義務、一級約束）**：①**訓練關閉（必做）**：Claude 訂閱設定關「Help improve Claude」。②**本地優先**：案件帳本只存所內機器 / NAS。③**最小化送 Claude**：完整文件只在抽送達日那次送。詳見 legal-admin `privacy-deploy.md`。

### Step 8：部署驗收（上線前必過、漏一項＝賣點失效）

「時限漏＝執業過失」整個賣點靠時間驅動基建，上線前逐項確認：
- [ ] **四支 cron 裝了且跑得到 `business.db`**：`flush_escalations.py`（投遞保證層）、`scan_deadlines.py`（時限倒數）、`scan_heartbeat.py`（watchdog）、`scan_unconfirmed_intake.py`（未確認跟催）。crontab 指對 `SME_DB_PATH`、`claude -p` 走訂閱（`env -u ANTHROPIC_API_KEY`）。
- [ ] **掃描器 heartbeat 有寫**：開機 readout 看得到「掃描存活」、非「失聯」。
- [ ] **辦公日曆當年 + 次年已 import**：末日順延 / 工作日倒數依賴台灣官方辦公日曆；跨年時限若次年沒灌 → 每筆標 `needs_manual_review` 洗版。
- [ ] **`taiwan-legal-db` MCP 就緒**：8 支工具連得到台灣官方資料庫（寫法條前 `query_regulation` 查證的前提；沒裝＝無從查證＝違反反捏造）。
- [ ] **行事曆 MCP 就緒**（或確認退回只寫 `deadlines` 表）：核心 loop「寫兩處」的第二處。
- [ ] **常駐 session 作息對齊**：誰的機器常開著接審核閉環 / escalation 即時層 / in-session push？單人所＝「你就是那唯一 session」、下班關機時即時層斷、只剩 cron 保證層 + claude -p 品質層推 LINE——**跟所長講清楚、別讓他以為 24/7 即時**。
- [ ] **`mark_deadline_filed` 責任**：誰負責書狀遞交後標記（標了 cron 才停對該時限提醒；漏標＝狼來了、真逾期被埋）。

### Step 9：校準測試（跑一輪真實時限 loop）

用一份真實判決書 / 裁定跑完整核心 loop：
- [ ] LINE 傳判決書照片 / PDF → legal-admin 讀檔抽送達日 + 文書類型
- [ ] 推回 LINE **一鍵確認**（送達日對不對、上訴還是抗告）→ `create_deadline` 引擎算法定 + 內部雙日期附 `statutory_basis`
- [ ] 寫行事曆（去識別化）+ 每日彙整推全所
- [ ] 自然語言查（人名 / 案號）查得到案件與時限
- 給所長看，問「這樣對嗎？」調整 → 回 Step 4-5 補慣例規則。

### Step 10：上線

- 第一週每天看 ops-dashboard：待確認到期日 / 即將到期時限 / 掃描器健康。
- 遇系統不會處理的 → 問所長 → 被動捕捉新規則（見下〈被動捕捉流程〉）。
- 每天結束 `save_session_handoff` 確保隔天接續。

### 導入進度追蹤
用 `create_task(category='admin')` 追每步（`導入 Step N：...`），每完成一步 `update_task(status='done')`。

---

## 一、核心哲學

引用 SOP Creator 的原則：**沒人看 50 頁文件。**

好的企業知識：
- **可掃描** — 標題、列點、表格。不要整段文字
- **可執行** — 每一步是具體動作，不是「考慮」「斟酌」
- **夠具體** — 有數字、有名字、有門檻。不要「適當」「視情況」
- **可驗證** — 怎麼知道做對了？有明確的完成標準
- **有人維護** — 知道是誰定的、什麼時候定的、誰可以改

### Be Specific 對照表

| 不要這樣寫 | 要這樣寫 |
|-----------|---------|
| 「聯繫相關人員」 | 「LINE 通知承辦律師 / 助理小芳」 |
| 「等到準備好」 | 「等狀態顯示『完成』（約 5 分鐘）」 |
| 「仔細檢查」 | 「確認 A、B、C 三個欄位」 |
| 「視情況而定」 | 「金額 > NT$5,000 時」 |
| 「定期」 | 「每週一早上 9 點」 |
| 「盡快」 | 「2 小時內」 |

---

## 二、被動捕捉流程

所長在對話中提到一條規則時：

1. **辨識** — 這是規則還是閒聊？
   - 規則特徵：「從現在開始」「一律」「不可以」「超過 X 就要」
   - 閒聊特徵：「我覺得」「搞不好」「有一次」

2. **提取原話** — 用所長的原話當 `source_quote`

3. **確認** — 回覆：
   ```
   我理解的是：

   📋 {整理後的規則，具體化}

   所長原話：「{source_quote}」
   分類：{category}

   這樣對嗎？確認後我就存進系統。
   ```

4. **存入** — 所長確認後：
   ```
   store_fact(
     category=分類,
     title=規則標題,
     content=整理後的規則,
     source_type='explicit',
     source_quote=原話,
     set_by=所長名
   )
   ```

5. **矛盾處理** — 如果 store_fact 回傳矛盾警告：
   - 列出衝突的舊規則
   - 問所長：「這跟之前的規則 #{id} 有衝突，要取代它嗎？」
   - 確認後用 `update_rule` 取代

---

## 二之一、機密軸（confidential）— 哪些知識不該被部門層看到

寫規則時除了 `category` / `business_unit`，還要判斷一條**獨立的軸 `confidential`**：這條知識該不該讓部門層人員看到。導入時的重點是——**`store_fact` 不特別指定就是公開**，敏感內容（財務 / HR / 定價底線）若沒設 `confidential=True`，部門層人員日後 `query_knowledge` 就查得到＝洩漏。預設值、`confidential` 與 `business_unit` 兩軸獨立、非全權限層過濾規則等機制見 CLAUDE.md〈機密軸（confidential）〉/ migration 006。

### 哪些主題該存成機密

導入訪談有幾個領域**最容易碰到機密內容**，這類答案應明確 `store_fact(confidential=True)`：

| 訪談領域 | 為什麼該設機密 |
|---------|---------------|
| 收費（收費模式、議價底線、特定當事人優惠的理由） | 部門層人員不該看到收費底細 |
| HR（薪資級距、考績規則、個別人員註記） | 人員 PII / 待遇屬機密 |
| 法律見解 / 案件策略（和解底線、勝算評估、攻防策略） | 機密、僅承辦與主持律師可見 |
| 特定當事人敏感事項（身分、案情、不欲人知的背景） | 律師保密義務 |

> 判斷原則：**「對內的規則 / 流程」可所內人員可見（大家要照著做），「為什麼這樣定 / 數字底線 / 個人待遇 / 案件策略」設機密。** 例如「書狀格式統一用所內範本」可公開（`confidential=False`），但「○○案打算和解、底線 200 萬」應 `store_fact(confidential=True)`。
> 不確定就問所長：「這條要讓所有所內人員都查得到，還是只有您（和特定律師）看得到？」確認後再決定 `confidential`。

---

## 三、主動訪談流程

系統初次導入或所長說「幫我建立所務規則」時，按領域逐一提問（與〈零、導入訪談〉的 Step 4-7 互補：那邊建一次性設定、這邊持續累積 SOP / 慣例）：

### 訪談大綱

| 順序 | 領域 | 核心問題 |
|------|------|---------|
| 1 | 案件慣例 | 「案件編號怎麼編？怎麼分類？收案流程？」 |
| 2 | 時限慣例 | 「法定期限往前抓幾天當內部死線？誰覆核時限計算？送達日誰負責填？」 |
| 3 | 利益衝突 | 「收新案怎麼查衝突？（人工 SOP；系統不自動偵測、只輔助列同名）」 |
| 4 | 人事 | 「上班時間？請假規定？加班怎麼算？」 |
| 5 | 委任人服務 | 「委任人多久回報一次進度？回電規矩？申訴 / 服務疏失怎麼處理？」 |
| 6 | 文件 / 卷宗 | 「卷宗怎麼命名？歸檔流程？電子 / 紙本存哪？」 |
| 7 | 收費慣例 | 「怎麼收費（計時 / 固定 / 成功報酬 / 顧問月費）？代墊款怎麼處理？」（**記成 SOP 知識；系統不做記帳 / 開帳單**） |
| 8 | 對外溝通語氣 | 「對委任人書面 / LINE 通知的語氣？去識別化規矩（行事曆不放當事人名）？」 |

> 領域 2（時限）/ 3（利益衝突）涉及執業責任、領域 4（人事）/ 7（收費）涉及機密底線 / 個人待遇時，答案要 `store_fact(confidential=True)`，否則部門層人員 `query_knowledge` 全看得到。判斷與範例見〈二之一、機密軸〉。

### 訪談技巧

**追問邊界案例：**
- 「如果送達日跨年、次年辦公日曆還沒灌呢？」（→ 引擎標 `needs_manual_review`、律師確認）
- 「如果收的新案當事人跟既有案的對造同名呢？」（→ 利益衝突人工查核）
- 「如果同一天有 3 個人請假呢？」

**追問數字：**
- 「內部緩衝『提前一點』是幾天？3 天？5 天？」
- 「『重要當事人』多久回報一次？每週？每兩週？」

**追問例外：**
- 「這個規則有沒有例外？什麼情況下不適用？」

每個回答都走被動捕捉流程（確認 → 存入）。
所長不想回答的就跳過，不強迫。

---

## 四、知識分類體系

### 預設類別

`hr`, `matter`, `deadline`, `conflict`, `client_service`, `document`, `fee`, `sop`, `company`, `settings`, `general`

不在預設裡的 → Claude 判斷最接近的，或用 `general`。

### 分類決策

| 關鍵字 | 分類 |
|--------|------|
| 上班/請假/加班/薪水/考績 | `hr` |
| 案件/案號/收案/結案/分類 | `matter` |
| 時限/緩衝/覆核/送達日/在途 | `deadline` |
| 利益衝突/對造/ethical wall | `conflict` |
| 委任人/回報/回電/申訴/服務 | `client_service` |
| 卷宗/歸檔/命名/文件存放 | `document` |
| 收費/計時/固定/成功報酬/代墊款 | `fee` |
| 流程/步驟/SOP/標準 | `sop` |
| 對外語氣/去識別化/書面通知措辭 | `sop` |

---

## 五、知識品質檢查

每條規則存入前，內部驗證：

- [ ] 有具體的觸發條件（什麼情況下用這條規則）
- [ ] 有具體的動作（要做什麼）
- [ ] 有數字或門檻（不是「很多」「很久」）
- [ ] 有明確的負責人或適用對象
- [ ] 邊界案例有涵蓋（例外情況怎麼辦）

不完整的 → 追問補充後再存。

---

## 六、反捏造原則

- `source_type='explicit'` → **必須**有 source_quote（所長原話）
- 你觀察到的慣例 → `source_type='observed'`，告知所長
- 你推斷的 → `source_type='inferred'`，明確標注待確認
- **絕不可把 inferred 偽裝成 explicit**
- 引用規則時，優先引用 explicit，其次 observed，最後 inferred

---

## 七、知識更新與退役

### 更新流程

所長說「從現在開始改成...」：
1. `query_knowledge` 找到舊規則
2. 確認要取代哪條
3. `update_rule(old_id, new_content, reason)`
4. 舊規則自動標記 superseded_by

### 退役信號

以下情況建議所長檢討規則：
- 規則超過 6 個月沒被引用
- 同類別有 3 條以上互相矛盾
- 人員反映「系統說的跟實際做法不一樣」

### 知識健檢（Lint）

定期（建議每月一次）執行 `lint_knowledge()` 進行知識庫健檢：
- **矛盾**：偵測同類別中可能矛盾的規則對
- **過期**：標記超過 6 個月未更新的規則
- **覆蓋**：找出覆蓋不足的類別（空白或偏少）
- **孤立鏈**：檢查 superseded_by 指向不存在的 ID

可指定檢查：`lint_knowledge(checks='stale,coverage')`

建議月報時一併執行，結果納入「企業規則變更」區塊。

### 知識變更日誌

`knowledge_changelog(days=7)` — 查看最近 N 天的知識變更：
- 新增了哪些規則（按日期分組）
- 更新了哪些規則（含原因）
- 月報時用 `knowledge_changelog(days=30)`

### 交叉引用

規則之間可建立關聯（rule_relations 表）：
- `store_fact` 偵測到相似規則時**自動建立** 'related' 關聯
- 手動建立：`link_rules(rule_id_a=12, rule_id_b=45, relation_type='depends_on')`
- 查詢關聯：`get_rule_relations(rule_id=12)`
- `query_knowledge` 結果會附帶相關規則的交叉引用
- `update_rule` 更新時會自動遷移關聯並提醒檢查連動規則
- 關聯類型：`related`（相關）、`depends_on`（依賴）、`conflicts_with`（衝突）

---

## Do's and Don'ts

### Do
- 存入前一定要先回覆確認，等所長說「對」才存
- `source_type='explicit'` 必須附上 `source_quote`（所長原話）
- 每條規則確保有觸發條件、具體動作、數字門檻
- 所長改主意時用 `update_rule`，不要直接覆蓋
- 所有規則變更都 `log_interaction`

### Don't
- 不要自作主張存入規則（一定要確認）
- 不要把 `inferred` 偽裝成 `explicit`
- 不要一次問所長太多問題（每次 3-5 個領域）
- 不要存入模糊規則（「適當」「視情況」→ 追問具體數字）
- 不要用 `delete_fact` 取代更新 — 用 `update_rule` 保留歷史

## 快速參考

### 被動捕捉規則
1. 辨識所長話中的規則特徵（「從現在開始」「一律」「不可以」「超過 X 就要」）
2. 回覆確認：「我理解的是：{規則}。這樣對嗎？」
3. `store_fact(category='fee', title='成功報酬比例慣例', content='規則內容', source_type='explicit', source_quote='所長原話', set_by='所長名')`

### 更新既有規則
1. `query_knowledge(question='內部緩衝天數', category='deadline')` — 找到舊規則
2. `update_rule(rule_id=舊ID, new_content='新規則內容', reason='所長更新')`

### 知識健檢與變更日誌
1. `lint_knowledge()` — 全面健檢（矛盾、過期、覆蓋、孤立鏈）
2. `lint_knowledge(checks='stale')` — 只查過期規則
3. `knowledge_changelog(days=30)` — 查看最近 30 天的變更

### 交叉引用
1. `link_rules(rule_id_a=12, rule_id_b=45, relation_type='related')` — 手動建立關聯
2. `get_rule_relations(rule_id=12)` — 查看規則的所有關聯

---

## 八、注意事項

- 存入前一定要確認，不要自作主張
- 矛盾偵測靠 store_fact 內建的檢查
- 所長改主意時用 update_rule，不要直接覆蓋
- 訪談時不要一次問太多（每次 3-5 個領域，所長累了就停）
- 所有規則變更都記 interaction_log
