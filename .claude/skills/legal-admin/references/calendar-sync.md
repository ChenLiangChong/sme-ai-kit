# 行事曆同步（calendar sync）— SPEC「寫兩處」的另一處

> 觸發：時限確認入庫後要寫進行事曆；庭期要進行事曆；「同步到 Google」。
> 設計原則：**calendar-agnostic**（不綁死特定行事曆）+ **去識別化**（外部行事曆只看到代號、看不到當事人）。

## 為什麼「寫兩處」

時限確認後寫**兩個地方**：
1. **內部 `deadlines` 表** —— 系統帳本（calc_trace + 法條 + 雙日期 + 狀態），是 source of truth、本地。
2. **事務所慣用行事曆** —— 律師日常在看的那本（Google Calendar 或其他）。把確認後的期限/庭期建成 event，律師不用切到我們系統也看得到。

## calendar-agnostic 怎麼做（不寫死 Google）

**行事曆寫入是 agent 動作、走「現場配置的行事曆 MCP」**，不是 business-db 內建一個 Google client：

1. 看現場配置了哪個行事曆 MCP（Google Calendar MCP？律所慣用的其他？）→ 用它的 `create_event` 建 event。
2. 建完拿回傳的 `event_id` → `mark_deadline_calendared(deadline_id, calendar_event_id="<回傳id>", calendar_provider="google", marked_by="<操作者>")` 存回 `deadlines`，供每日彙整去重 / 後續更新對位。
3. **現場沒有數位行事曆** → 退回只記內部 `deadlines` 表（系統內建行事曆視圖），等之後接 adapter。

> **現場第一件事 = 確認律所實際用什麼行事曆**（Google？其他軟體？紙本/白板？）。核心 loop（文件→抽取→確認→deadlines 表→查詢→每日彙整）**不依賴**特定行事曆；行事曆只是「另一處顯示」。

## 去識別化（律師有保密義務、外部行事曆是外流面）

寫進 Google / 外部行事曆的 event **只放「案件代號 + 期限類型 + 日期」**，**不放當事人名 / 案由**：

- 好：`M-2026-014 上訴期限`、`M-2026-014 言詞辯論 10:00 北院`
- 壞：`林曉明 詐欺案 上訴期限`（當事人名 + 案由外流到 Google）

代號 ↔ 真實對照只存本地 `deadlines`/`matters`（`matter_no`）。理由與升級路（連每日摘要都代號化、最敏感檔走本地不經 LINE）見 [privacy-deploy.md](privacy-deploy.md)。

## event 內容建議

- **標題**：`{matter_no} {期限類型}`（如 `2026-民-014 上訴期限`）
- **日期**：用 **內部期限**（盯這個）當 event 日；備註欄放法定期限（底線）+ 法條 + deadline_id，方便回查。
- **庭期**：用實際開庭日 + 時間 + 法庭（去識別化代號 + 地點）。

## 失敗情境判讀

- **行事曆 MCP 沒配置 / create_event 失敗** → 先確保**內部 `deadlines` 已寫成功**（那才是 source of truth、提醒靠它跑），行事曆同步失敗只是少了「另一處顯示」、不影響倒數。回報律師「時限已入庫、行事曆暫未同步」。
- **受限層對機密案件 `mark_deadline_calendared` 回「找不到時限 #N」** → 這是刻意設計：受限層對機密時限回**與「不存在」完全相同**的泛化錯誤（anti-oracle、不洩漏「存在但機密」這一位元），非真的查無。個人律所通常不分層、不會碰到（見 SKILL〈安全執行模型〉）。
- **同一時限重複寫 event** → 寫前先看 `get_deadline` 的「行事曆同步」狀態，已同步（有 calendar_event_id）就改用行事曆 MCP 的 update_event、不要再 create 一筆。
