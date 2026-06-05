# 隱私與部署（privacy & deploy）

> 觸發：上線前檢查、隱私問題、cron 設定、每日提醒沒推、辦公日曆未載入、種 boss 收件人。
> 律師有保密義務，**隱私是本 vertical 的一級設計約束**。權威見 `docs/legal/SPEC.md`〈隱私設計〉。

## 隱私標準檔（定案、預設）

核心原則：**身分與內容留本地，外部只給「時間 + 代號」。** 資料流經四方：本地 `business.db`（最安全）/ Google Calendar / LINE(LY Corp) / Anthropic(Claude)。

1. **訓練關閉（必做、不可省）** —— Claude 訂閱（Free/Pro/Max）預設可能拿對話訓練模型並長期保留；**上線前必關「Help improve Claude」**→ 變成不訓練 + 30 天保留。訂閱方案拿不到 ZDR（零保留需 Enterprise、成本跳級、與走訂閱省成本衝突），故靠下面「去識別 + 最小化」補。
2. **本地優先** —— 案件帳本（matters/deadlines/當事人對照）只存事務所自己機器/NAS，不進 SaaS 雲（對比全雲端競品的賣點）。
3. **行事曆去識別化** —— 寫進 Google/外部行事曆的 event 只放「案件代號 + 期限類型 + 日期」，不放當事人名/案由；代號↔真實對照只存本地 DB（見 calendar-sync）。
4. **最小化送 Claude** —— 完整文件只在「抽送達日」那一次送；確認後存結構化欄位，之後每日摘要/查詢用結構化資料跑、不重複送整份機密。

**升級路（要收緊隨時開）**：每日摘要也代號化（連 LINE 都看不到名）／文件抽取前本地先 OCR + 遮當事人名只送含日期那段／最敏感原始檔走本地上傳不經 LINE／評估 Enterprise ZDR。

> **別把「隱私（對外）」跟「機密層（對內）」搞混**：個人律所沒有對內越權問題（不設 floor）、但**對外隱私照樣全部適用**（見 SKILL〈安全執行模型〉）。

## 部署檢查清單（上線前）

- [ ] **訓練關閉**：Claude 帳號設定關「Help improve Claude」。
- [ ] **辦公日曆載入（部署必做、否則時限全標人工複核）**：`office_calendar` migration **不種任何資料**（避免半套年度被誤判已載入）。部署用 `import_office_calendar.py` 灌**當年度 + 次年度**完整日曆（末日順延 民法§122 的資料底；匯入器強制單一年度逐日完整、`calendar_year_loaded` 也要求該年達 365/366 才算載入）：
  ```
  curl -sO https://raw.githubusercontent.com/ruyut/TaiwanCalendar/master/data/2026.json
  curl -sO https://raw.githubusercontent.com/ruyut/TaiwanCalendar/master/data/2027.json   # 次年公告後再補
  SME_DB_PATH=/abs/data/business.db /abs/.venv/bin/python3 mcp-servers/business-db/import_office_calendar.py 2026.json 2027.json
  ```
  整年逐日匯入、idempotent 可重跑、來源記在 `source` 欄。**務必與人事行政總處官方對賬**（反捏造：填錯假日＝算錯期限）。未載入年度的時限引擎會標 `needs_manual_review`（末日順延算不準）——這是保護、但別讓律師天天踩，每年初記得補次年度。
- [ ] **種 boss 收件人**：每日提醒/逾期上報的收件人走 `resolve_escalation_target`（coalesce 到 boss/全所）。確認有一個可達的收件身份（`company.boss_line_id` 或 floor-map `escalation_target`），否則 enqueue 會留 pending 沒人收。
- [ ] **cron 設定（`install.sh` 已自動裝四支、缺一支都留靜默失敗破口）**：`install.sh` §8 用 `add_cron` 冪等裝 `flush_escalations`（每 2 分）+ `scan_deadlines`（每日 07:00）+ `scan_heartbeat`（#H1、每 2h）+ `scan_unconfirmed_intake`（#H2、每 4h），分鐘數已錯開、重跑不重複。cron 在 host 跑、不受 LINE-runtime sandbox 管（讀得到 DB）。**部署只需確認 cron daemon 有在跑**（`install.sh` 會 `pgrep` 檢查、沒跑會 err）：
  ```
  # 確認已裝（4 行 SME-AI-Kit 標記）：
  crontab -l | grep SME-AI-Kit
  # WSL 啟動 cron daemon（沒跑則上述 cron 全不觸發）：
  sudo service cron start    # 或 systemctl enable --now cron
  ```
  手動 fallback（`crontab` 不可用 / 要自訂時段時，路徑換絕對路徑）：
  ```
  0  7   * * *  SME_DB_PATH=/abs/data/business.db /abs/.venv/bin/python3 /abs/mcp-servers/business-db/scan_deadlines.py        >> /abs/data/scan.log 2>&1
  17 */2  * * *  SME_DB_PATH=/abs/data/business.db /abs/.venv/bin/python3 /abs/mcp-servers/business-db/scan_heartbeat.py       >> /abs/data/heartbeat.log 2>&1
  37 */4  * * *  SME_DB_PATH=/abs/data/business.db /abs/.venv/bin/python3 /abs/mcp-servers/business-db/scan_unconfirmed_intake.py >> /abs/data/intake.log 2>&1
  ```
  **為何要 `scan_heartbeat.py`（第二支極小 cron）**：`scan_deadlines.py` 若靜默掛掉，時限停止倒數且沒人知＝漏期根因。watchdog 是另一支幾乎不會自己壞的進程，互為 dead-man：被監看的掛了→watchdog 上報；watchdog 掛了→全權限開機 readout 反過來標「watchdog 失聯」（門檻常數 `SCAN_STALE_HOURS`/`WATCHDOG_STALE_HOURS` 在 `shared/deadlines.py`、勿在他處另寫）。`flush_escalations.py`（每 2 分、投遞保證層）見 CLAUDE.md〈上報（escalation）機制〉。
- [ ] **行事曆 MCP**：現場確認律所用哪本行事曆、配置對應 MCP（見 calendar-sync）。**用律所自己的 Google 帳號**，不是開發者個人帳號。
- [ ] **在途期間**：律所自辦（住法院所在地）→ `has_local_agent=1`、在途歸零；常跨區（如金門→台北）才需 `transit_period` 查表資料。

## 失敗情境判讀

- **時限算出來但帶「辦公日曆未載入」** → 該年度沒匯入，補 `office_calendar`（見上）。
- **enqueue 了但 `list_pending_escalations` 一直 pending/failed** → 收件人解析不到（沒種 boss），或行事曆/LINE 投遞失敗；種好 boss 身份再重跑。
- **跨年度時限大量標複核** → 次年度日曆沒匯入，部署時一次匯兩年。
- **開機 readout 出現「時限掃描失聯」紅字** → `scan_deadlines.py` cron 沒在跑 / 報錯（看 `data/scan.log`）。時限可能已停止倒數，先人工 `list_upcoming_deadlines` 巡一次未結時限，再修 cron。
- **開機 readout 出現「監看 watchdog 失聯/未部署」** → `scan_heartbeat.py` cron 沒設或掛了；時限本身仍在數，但時間驅動的失聯告警下線、補上 cron。
- **「待確認時限 N 件尚未入庫」一直在** → 有人丟了檔、AI 推了確認、人忘了回。用 `list_pending_intakes` 查、確認走 `create_deadline(confirm_intake_id=)`、確定不算了用 `resolve_deadline_intake(id, 'discarded')`。
