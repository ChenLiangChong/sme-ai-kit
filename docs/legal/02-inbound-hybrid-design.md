# legal-admin LINE Inbound 混合處理架構（設計定稿草案）

> 來源：2026-06-05 multi-agent workflow（5 盤點→5 設計→候選→5 紅隊 HIGH→整合）。
> 狀態：**設計定稿、待老闆拍板開放參數與實作範圍**（見 §6）。尚未實作。
> 紅隊核心結論：CAS lease 必須下沉到「副作用層」（gate-consume + claim-before-push），
>   不能只鎖在投遞層——因為活 interactive session 從不經過投遞層的 lease。

---

# legal-admin LINE Inbound 混合處理架構 — 最終定稿 SPEC

> 狀態：架構定稿（待老闆拍板開放參數見 §6）。本文已整合 5 份候選 + 5 個 high 級紅隊發現。**每個「會破」的洞都有對應堵法、並標出哪些是縱深防禦、哪些仍是誠實殘留。**
> 域特性：legal-admin = 漏期=執業過失。**本架構同時防兩個方向：漏掉（訊息沒人處理）與重複/矛盾（同一判決書被兩個處理者各算一次、推出兩個不同到期日）。後者在本域比漏更危險、是紅隊的核心打擊面。**

---

## 0. 紅隊發現如何改變了設計（先講總綱，因為它推翻了候選的核心防線拓樸）

候選把「防雙重處理」全押在 **per-row CAS lease（claimed_at）+ per-row ack（reply 帶 line_message_id）**。五個 high 紅隊發現證明這條防線拓樸選錯了，核心一句話：

> **CAS lease 只擋得住「也走 CAS 的那一路」。但 live interactive session 從不走 CAS —— 它在 channel 注入當下就開始 LLM turn，整條執行路徑（Read PDF → stage_intake → create_deadline → reply）對 claimed_at 零耦合。lease 只能序列化 reaper↔reaper、reaper↔timer，序列化不了 reaper-worker↔live-session。**

對照 escalation：那裡 CAS 有效，是因為**兩個 racer（cron flush + claude -p notifier）都在唯一副作用（LINE push）前過同一個 `_CLAIM_UPDATE`**（escalation.py:430-432，已讀確認）。inbound 的拓樸不同 —— racer 非對稱。

**因此最終架構做三個拓樸層級的改變（缺一仍破）：**

| 層級 | 候選做法（被紅隊打破） | 最終做法 |
|------|---------------------|---------|
| **鎖在哪** | lease 鎖在「投遞/spawn 決策端」 | **鎖下沉到「真正會建資料的 tool 入口」（gate-consume），且 outbound reply 改 claim-before-push** — 鎖回到唯一副作用前，恢復 escalation 的正確拓樸 |
| **ack 怎麼算** | reply 翻 status = 唯一真值，line_message_id 可選、漏帶退回 per-chat | **ack 與 reply 解耦**：status 翻轉只由「指名該 row 的 ack」驅動，per-chat 批量翻改 explicit opt-in（預設關）；reaper claimable 條件加 `acked_message_id` 校驗，「我被翻 replied 但 ack 的是別人」視為未處理 |
| **下游冪等** | 無（stage_intake / insert_deadline 都是裸 INSERT） | **下游寫入冪等化**：pending_intakes 加 `(chat_id, source_message_id)` UNIQUE、deadlines 加 `(matter_id,type,trigger_event,service_base_date) WHERE status!='cancelled'` 部分 UNIQUE、create_deadline 守衛改「先檢查再 insert」 |

外加紅隊揭穿的兩個「宣稱有但實際不存在」的安全網：
- **watchdog cron 根本沒裝**（install.sh:184-205 已讀確認，只裝 flush_escalations.py；scan_*.py 全靠註解叫人手動 crontab）→ §6.2 / §5 階段 6 補裝。
- **active-request 單檔在並發下 = 垂直權限提升**（auth.py:_check_permission 已讀確認只查全域 permission、不綁 floor、不綁 row）→ §3.6 把 actor 升級為 per-message keying + gate 層綁 floor。

---

## 1. 最終推薦架構

### 1.1 元件總覽

```
                          ┌─────────────────────────────────────────┐
                          │  line-gatewayd（新獨立常駐 daemon）          │
                          │  身份 = operator（無 SME_FLOOR、讀得到 DB）   │
                          │  ─────────────────────────────────────    │
   LINE 平台 ──webhook──▶ │  • Bun.serve webhook (8789) 唯一持有        │
   (ngrok/cloudflared)    │  • ngrok/tunnel 子進程 + exited 監督 + 重PUT │
                          │  • IPC broadcast server + inject token      │
                          │  • verifySignature → resolveTargetFloor     │
                          │  • saveMessageToDb(queued) + target_floor    │
                          │  • writeActiveRequest(per-msg, §3.6)        │
                          │  • 附件複製進 data/<floor>/inbox-media       │
                          │  • presence(floor) 握手表 + 小窗 debounce 聚合 │
                          │  • in-process ack-timer（品質層觸發 fallback）│
                          │  • heartbeat: line_gateway_heartbeat        │
                          └──────┬───────────────────────┬─────────────┘
                                 │ IPC (unix socket)      │ fire-and-forget
                                 │ notifyAll(注入活session) │ spawn claude -p
                    ┌────────────▼──────────┐   ┌─────────▼───────────────┐
                    │ 活 interactive session │   │ claude -p single-shot    │
                    │ (start-line.sh 啟動)   │   │ worker (floor 重建 §4)    │
                    │ line MCP = pure IPC    │   │ 自帶 line MCP + business  │
                    │ client（永不自建webhook）│   │ -db MCP 子進程            │
                    └───────────┬───────────┘   └─────────┬───────────────┘
                                │ 兩者回覆都走自己的 line MCP 子進程        │
                                │ reply/mark_read = claim-before-push(§3.5)│
                                ▼                          ▼
                       ┌─────────────────────────────────────────┐
                       │  business.db（單一真值）                    │
                       │  line_messages: queued→processed/replied   │
                       │   + claimed_at/processor/claim_token       │
                       │   + target_floor/attempt_count             │
                       │   + acked_message_id/consumed_at           │
                       │  gate-consume @ create_deadline/stage_intake│
                       │  pending_intakes (chat_id,source_msg) UNIQUE│
                       │  deadlines (matter,type,evt,date) UNIQUE    │
                       └─────────────────────────────────────────┘
                                ▲                          ▲
                    ┌───────────┴──────────┐   ┌───────────┴──────────────┐
   保證層（cron）─▶  │ reap_inbound.py */1   │   │ gateway_watchdog.py */1   │ ◀─ 看門狗（cron）
   純讀row→CAS claim │ 掃 queued 逾 hard-DL  │   │ 查 daemon heartbeat 年齡   │   走 flush 路徑直打
   →spawn worker     │ + acked_message_id校驗 │   │ + 4040 tunnel 探針        │   LINE API（繞過死daemon）
                     └──────────────────────┘   │ + 最近inbound年齡         │
                                                  └──────────────────────────┘
```

### 1.2 資料流圖（一則判決書 PDF + 一句「幫我算上訴期限」的完整路徑）

```
LINE 送達 2 個 event：[file=判決書.pdf] + [text=幫我算上訴期限]
   │
   ▼ daemon webhook handler（逐 event）
[1] verifySignature（HMAC，失敗 401）
[2] 下載附件：PDF → data/media/line/files/<id>.pdf
       └─ 同時 hardlink/copy → data/<target_floor>/inbox-media/<id>.pdf（worker sandbox 讀得到）
[3] saveMessageToDb：INSERT OR IGNORE（line_message_id UNIQUE 去重）
       row#A(file, queued, target_floor) / row#B(text, queued, target_floor)
       —— created_at 寫入、target_floor 寫死（daemon 算定、非 worker 重算）
   │
   ▼ daemon 小窗 debounce 聚合（同 channel_id+chat_id，1.5s 窗）★紅隊②修
[4] 把 row#A+row#B 打包成「處理單元 unit_id」
       └─ 產 claim_token、寫進每 row 的 processor 欄 + active-request-<floor>-<unit>.json
   │
   ▼ 判定（§2）
[5] presence(target_floor) > 0 ?
   ├─ 是：CAS claim 整個 unit（processor='session'、claim_token、claimed_at=now）
   │       → notifyAll 一次注入「這批 row（按 id 升序、PDF 先）」進活 session
   │         meta 帶 unit_id + 每 row 的 line_message_id + claim_token + enqueued_ms（全 String()）★紅隊③④
   │       → 排 in-process timer(_ACK_WINDOW_SEC)
   │
   └─ 否：CAS claim 整個 unit（processor='fallback'）→ 直接 spawn worker（§4）
   │
   ▼ 處理（活 session 或 worker，路徑相同）
[6] 處理前 re-validate lease：row 的 claim_token 還是不是「我這次注入/claim 的」？★紅隊③
       └─ 不是（已被 reclaim 給別路）→ 放棄這個 turn、不處理、不 reply（攔住 turn-queue 延遲重放）
[7] Read inbox-media PDF（pdf skill 抽取）→ 合看文字指示
[8] gate-consume @ stage_deadline_intake：★紅隊①核心修
       同 tx 先 UPDATE line_messages SET consumed_at,consumed_by WHERE id IN(unit rows) AND consumed_at IS NULL
       rowcount==0 → 「此訊息已被另一處理者消費」、放棄（恢復 escalation 拓樸：鎖在唯一副作用前）
[9] stage_deadline_intake：INSERT OR IGNORE（chat_id+source_message_id UNIQUE）★紅隊①冪等
       撞 UNIQUE → 讀既有 intake（不重抽）→ 推回 LINE 一鍵確認卡（pending_intakes 外部化 HITL）
   │
   ▼ ack（§3.5）★紅隊②核心修
[10] reply_flex(line_message_id=<unit 主 row>)：claim-before-push
        同 tx 先 CAS UPDATE status='replied', acked_message_id=<id> WHERE line_message_id=? AND claim_token=?
        rowcount==0（已被別路 claim/replied）→ 拒送、不呼叫 linePush、回「已被接手、跳過」
        rowcount==1 → 才 linePush + 翻整個 unit 的 status（per-unit ack，非 per-chat、非孤立 per-row）
   │
   ▼ 後續 HITL（人之後回「確認 #N」= 另一則新 inbound、走同一條路由）
[11] create_deadline(confirm_intake_id=N)：先檢查 intake awaiting + deadline UNIQUE 再 insert ★紅隊①
        確定性算雙日期 + 附 statutory_basis（絕不心算）
   │
   ▼ 保證層（完全獨立、不看 presence）
[*] cron reap_inbound.py */1：撈 status='queued' 逾 hard-deadline
       OR (status IN(replied,processed) AND acked_message_id != id)  ★紅隊②縱深
       → 被別人副作用翻走的 row 仍撈得回 → 恢復「漏不掉」
   ▼ 看門狗（完全獨立、走 flush 路徑直打 LINE）
[*] cron gateway_watchdog.py */1：daemon heartbeat 年齡 / 4040 tunnel / 最近 inbound 年齡 → escalate ★紅隊⑤
```

---

## 2. 精確切換邏輯（presence + ack-timeout）

### 2.1 三個判定訊號

1. **presence(target_floor)**：daemon 維護 IPC 握手表。**新增握手**：client 連 IPC 時送 `{type:'hello', floor: myFloor()}`（現狀 server.ts:865 只 `ipcClients.add(socket)` 不知 floor，已讀確認）。daemon 據此知「某 floor 有沒有連著的 instance」。**僅低延遲加速、非真值。**
2. **ack 訊號**：row 的 `status` 是否仍 `'queued'`。`'processed'`（mark_read）與 `'replied'`（reply）**都算已處理**。
3. **claim_token 一致性**：row 當前 `claim_token` 是否仍屬於「這次注入/claim」——處理前與 ack 前都要 re-validate（攔 wedged-session 醒來重放）。

### 2.2 判定狀態機

```
daemon 聚合一個 unit → saveMessageToDb(queued) → writeActiveRequest(per-msg)
  │
  ├─ presence(target_floor) > 0 ?
  │     ├─ 是：CAS claim unit（processor='session', claim_token=T_s, claimed_at=now）
  │     │       → notifyAll 注入活 session（即時層）
  │     │       → 排 in-process timer(_ACK_WINDOW_SEC)
  │     │             └─ 到點查 unit 主 row：
  │     │                   status 翻 processed/replied 且 acked_message_id 對 → done
  │     │                   status 仍 queued（claim_token 仍 T_s、未過 TTL）→ 視為「session 沒接」
  │     │                        → reclaim：CAS 改 processor='fallback', claim_token=T_f → spawn worker
  │     │
  │     └─ 否（presence=0）：不浪費等待 → CAS claim processor='fallback' → 立即 spawn worker
  │
  └─ [保證層・完全獨立] cron reap_inbound.py */1：
        撈 (status='queued' 逾 hard-deadline)
            OR (status IN(replied,processed) AND acked_message_id IS NOT NULL AND acked_message_id != id)
        AND (claimed_at IS NULL OR claimed_at <= now - _INBOUND_CLAIM_TTL_MIN)
        → CAS claim → spawn worker（daemon 死了照撈、被副作用誤翻的 row 也撈得回）
```

### 2.3 為什麼 _ACK_WINDOW_SEC 與 reclaim TTL 必須是同一語意（紅隊③修正候選自相矛盾）

候選設 `_ACK_TIMEOUT_SEC=90` 但 `_SESSION_ACK_TTL=120`、又規定「claimed_at 過期才 reclaim」→ 90s 到點時 120s 短租沒過 → **白等到 120s 才能 reclaim**。紅隊③指出這是矛盾。

**最終：合併成單一常數 `_ACK_WINDOW_SEC`** —— 「等 session ack 的時間」與「session 短租到期可被 reclaim 的時間」在語意上是同一件事。timer 到點 = 短租到期 = 可立即 reclaim，無等待真空。**cross-file guard 綁死 `_ACK_WINDOW_SEC == 活 session 短租 TTL`。**

### 2.4 為什麼 presence 不能當真值（寫死）

`inject` 成功只代表 IPC socket bytes 進了 kernel buffer（server.ts:536-541 `client.write` 只在 socket closed 才 catch，已讀確認），**不代表 session turn-loop 在消費、更不代表處理了**。wedged session（context 壓縮 / 卡慢工具）socket 連著但不消費 turn → presence 誤報為活。**所以 presence>0 仍排 ack-timer + claim_token re-validate；保證層 cron 完全不看 presence。**

### 2.5 逃生口（題目要求）

daemon 讀 channel 設定或 `env SME_FORCE_SINGLESHOT=<floor>` → 該 floor 收訊跳過 notifyAll、`_ACK_WINDOW_SEC=0` → 直接 single-shot。用於「某層 session 已知壞掉、強制確定性處理」。

### 2.6 建議 timeout 秒數與理由

| 常數 | 建議值 | 理由 |
|------|--------|------|
| `_ACK_WINDOW_SEC`（=活 session 短租 TTL，單一常數） | **90** | 夠短客戶不久等；夠長讓互動 session 至少回一則。**必 << active-request 過期（見下）** |
| `_INBOUND_CLAIM_TTL_MIN`（worker 租約 reclaim 門檻） | **20** | 必 > 單則最壞處理時間 `_ASSUMED_MAX_WORKER_SEC`，否則處理中被 reclaim 重算 |
| `_ASSUMED_MAX_WORKER_SEC` | **720**（12 分） | single-shot 跑 LLM + pdf skill + stage_intake + reply，分鐘級 |
| `_HARD_DEADLINE_MIN`（cron 才撈） | **5** | 必 > `_ACK_WINDOW_SEC/60`，避免 cron 與 daemon timer 搶同一則 |
| `_INBOUND_CLAIM_BATCH` | **3** | 每 row = 一隻 claude -p = 一套 MCP 子進程，節流 |
| active-request 過期（沿用既有） | **600**（10 分，auth.py:34） | `_ACK_WINDOW_SEC(90) << 600`，spawn 時 active-request 不過期 |

**關鍵不變量（必須 > active-request TTL 限制，紅隊③）**：worker 處理可達 `_INBOUND_CLAIM_TTL_MIN=20分` > active-request 10 分 TTL → **worker 必須在 long-task 中週期刷新 active-request 的 `written_ms`（透過 `renew_inbound_lease` tool，同時續租 `claimed_at`）**，否則 12 分的合法處理會在第 10 分讓 verified actor 過期、不可逆動作被 `__unverified__` 擋下。這把候選 §8「續租是可選強化」改為**必需**。

---

## 3. 防雙送機制（拓樸已從投遞層下沉到副作用層）

### 3.1 migration 015（一支）

最新 migration 是 014（已確認），故為 `015_line_messages_inbound_lease.sql`：

```sql
-- 鏡像 010_escalation_claimed_at.sql：claimed_at 是租約戳記、非新 status。
-- line_messages 維持 CHECK(status IN queued/processed/replied) 不動。
ALTER TABLE line_messages ADD COLUMN claimed_at DATETIME;            -- nullable 無 default
ALTER TABLE line_messages ADD COLUMN claim_token TEXT;              -- 紅隊③：誰持租（session/fallback 各自唯一 token、非僅診斷字串）
ALTER TABLE line_messages ADD COLUMN processor TEXT;               -- 'session' | 'fallback'（診斷）
ALTER TABLE line_messages ADD COLUMN target_floor TEXT;           -- daemon 收訊算定寫死（floor 真值來源）
ALTER TABLE line_messages ADD COLUMN unit_id TEXT;               -- 紅隊②：同 chat 多 row 的處理單元（ack 粒度）
ALTER TABLE line_messages ADD COLUMN acked_message_id INTEGER;  -- 紅隊②：實際被指名 ack 的 row id
ALTER TABLE line_messages ADD COLUMN consumed_at DATETIME;     -- 紅隊①：side-effect tool gate-consume 用
ALTER TABLE line_messages ADD COLUMN consumed_by TEXT;
ALTER TABLE line_messages ADD COLUMN attempt_count INTEGER DEFAULT 0;  -- dead-letter 計數
CREATE UNIQUE INDEX IF NOT EXISTS idx_line_messages_msgid
  ON line_messages(line_message_id) WHERE line_message_id IS NOT NULL;  -- at-least-once 去重
-- 既有 idx_line_messages_dir(direction,status) 已服務 reaper 撈取。
```

> server.ts `getDb()` 是 `CREATE TABLE IF NOT EXISTS`（不自動加欄）→ daemon/server.ts 啟動補一句 `try{ALTER TABLE ... ADD COLUMN}catch{}` 雙保險（鏡像現有補 channel_id 欄寫法）。

### 3.2 共用候選條件 + 原子 CAS（照搬 escalation.py:423-432，已讀確認模式）

新增於 `shared/inbound.py`：

```python
# claimed_at 用 datetime('now','localtime','-N minutes')，寫入用 _now()（db.py:39 localtime 字串）
# —— 絕不混 UTC CURRENT_TIMESTAMP（時區錯位 = 租約立刻過期或永不過期）。
_INBOUND_CLAIMABLE_WHERE = (
    "direction='inbound' "
    # 紅隊②縱深：不只認 queued，被別人副作用誤翻 replied/processed 但 ack 別人的 row 也可重派
    "AND (status='queued' "
    "     OR (status IN ('replied','processed') AND acked_message_id IS NOT NULL AND acked_message_id != id)) "
    "AND (claimed_at IS NULL OR claimed_at <= datetime('now','localtime','-'||?||' minutes'))"
)
# rowcount==1 才贏。params: (now, claim_token, processor, id, claim_ttl_min)
_INBOUND_CLAIM_UPDATE = (
    "UPDATE line_messages SET claimed_at=?, claim_token=?, processor=? WHERE id=? AND " + _INBOUND_CLAIMABLE_WHERE
)
```

### 3.3 claim 與 process 分兩 tx、claim 先 commit（照搬 escalation.py:497-503）

1. reaper `SELECT ... WHERE _INBOUND_CLAIMABLE_WHERE AND created_at<=now-_HARD_DEADLINE ORDER BY id`（獨立連線、讀完即 close）→ **按 (channel_id, chat_id) 分組**。
2. 逐 unit 對其所有 row `with transaction() as cdb: cdb.execute(_INBOUND_CLAIM_UPDATE, ...).rowcount`。**claim 自己 commit**（讓併發路徑立刻看見租約）。
3. unit 內任一 row claim 失敗（rowcount!=1）→ 整個 unit skip（別把半個 unit 餵 worker）。
4. 全搶到才 `spawn_inbound_worker(unit_rows, ...)`（**claim 與 spawn 分 tx**：不持 write lock 過 LLM I/O）。

### 3.4 三道防雙送 + 兩個拓樸修正（核心）

| 防線 | 機制 | 對應 escalation / 紅隊 |
|------|------|----------------------|
| **去重** | `line_message_id` UNIQUE + saveMessageToDb 改 `INSERT OR IGNORE` | LINE at-least-once 重送同 event |
| **per-row CAS lease** | 三路送前 `_INBOUND_CLAIM_UPDATE` rowcount==1 | 照搬 escalation 010 |
| **gate-consume（拓樸修正①）** | create_deadline / stage_intake **入口同 tx** `UPDATE line_messages SET consumed_at WHERE id IN(unit) AND consumed_at IS NULL` rowcount==0 拒絕 | 紅隊①：把鎖搬到**唯一副作用前**（比照 approvals consumed_at，repository 已讀確認模式），恢復 escalation 正確拓樸 — 不管 session 還是 worker，誰先在 side-effect 搶到消費權，另一個被擋 |
| **claim-before-push（拓樸修正②）** | reply/mark_read **push 前** CAS UPDATE，rowcount==0 不送 | 紅隊③：lease 延伸到 outbound，wedged session 醒來一 reply 撞 0 changes、push 根本不發 |
| **下游冪等** | pending_intakes `(chat_id,source_message_id)` UNIQUE + deadlines `(matter,type,evt,date) WHERE status!='cancelled'` UNIQUE + create_deadline 先檢查再 insert | 紅隊①：即使前面全漏，第二個處理者撞 UNIQUE → 讀既有、不重抽，杜絕兩個矛盾到期日 |

### 3.5 ack 改 per-unit + claim-before-push（紅隊②③ 核心修，改 server.ts）

現狀 reply/reply_flex/mark_read 的 UPDATE WHERE = `user_id/group_id+channel_id+status IN(...)`（server.ts:376/404/444，**已讀確認 per-chat、無 claimed_at、無 line_message_id**）。改動：

1. **三個工具新增 `line_message_id` 參數**。reaper/即時注入帶 message context 時 **必填**；缺它**絕不**退回 per-chat 批量翻 —— per-chat 批量翻改為 explicit `ack_all=true` 旗標（預設關，僅 operator 單 session 場景）。對照 escalation `mark_escalation_sent` by-id 強制（已確認），這才是同安全標準。
2. **改 push-before-status 為 claim-before-push**：
   ```
   同 tx 先：UPDATE line_messages SET status=?, acked_message_id=? 
             WHERE line_message_id=? AND channel_id=? AND status IN('queued','processed')
                   AND claim_token=?           -- caller 從注入 meta 帶回的 token
   rowcount==0（已被別路 claim/已 replied/token 不符）→ 直接 return「此則已被接手、跳過」、不呼叫 linePush
   rowcount==1 → 才 linePush + 翻整個 unit（acked_message_id 標主 row）
   ```
3. **ack 粒度 = unit（非孤立 per-row）**：避免「session 只 ack 文字、PDF row 被孤立成 queued 必觸發 fallback 重算」（紅隊②的反向漏）。

### 3.6 verified actor 升級為 per-message keying + gate 綁 floor（紅隊④ 垂直權限提升修，最嚴重）

紅隊④證實（auth.py 已讀）：`_check_permission` 只比對 verified actor 的**全域** permission、不綁 floor、不綁 row；`active-request-<floor>.json` 是 per-floor 單檔、同層任兩則互相覆寫。daemon 並發下 = basic 助理 worker 讀到剛好被 manager 訊息覆寫的 active-request → 借到 manager 簽核/記帳/刪帳權限，audit 還具名成那位 manager。這是**垂直權限提升**，不是候選輕描淡寫的「誤歸因 trade-off」。

**修法（三步，gate 層 enforce、不靠 LLM 自律）：**

1. **active-request per-message keying（server.ts + auth.py）**：daemon 寫 `active-request-<floor>-<unit_id>.json`（消除同層覆寫）。worker spawn 時 reaper 以 **env `SME_ACTIVE_UNIT_ID`（已展開字面、agent 改不到，比照 SME_FLOOR）** 傳入。`_read_active_request` 依 `(floor, SME_ACTIVE_UNIT_ID)` 精確取檔，取不到 → `__unverified__`（fail-closed），**絕不 fallback 到「該層任一 active-request」**（現狀 auth.py:26 的舊全域 fallback 對 floored worker 要關掉）。
2. **gate 層綁 actor↔floor（補既有缺陷，auth.py:_check_permission）**：verified actor 撈出 employee 後，檢查 `emp.department`（或 business_units→floor 映射）是否屬於 `get_floor()`；不符即 `ERROR: 操作者不屬於本層`。把「只查全域 permission」修成「全域 permission AND 屬於本層」。FULL_ACCESS（confidential/operator）維持不綁。
3. **resolve_approval 等高風險 gate 額外綁 row.user_id（approvals/service.py:230，已知傳空 actor）**：require caller 傳入正在處理的 message 對應 user_id，service 內 assert `_resolve_trusted_actor() == row.user_id`，不一致即拒（把候選的 prompt 交叉核對下沉到 service enforce）。

> 連帶：`resolveTargetFloor`（server.ts:559，已讀確認只認 boss/admin）讓處理機密案件的 manager 律師落 general → manager actor 出現在 general active-request。應讓 floor-map（#13）以 `employees.department` 收斂路由（降低觸發頻率、與 1/2 縱深疊加，非取代）。**此項屬 #13 範圍、本架構標為依賴、不在本批必做。**

---

## 4. spawn claude -p 的 floor 重建清單（逐項對照 start-line.sh:45-50，已讀確認）

`spawn_inbound_worker(unit_rows, target_floor, unit_id, project_root)` 於 `shared/inbound.py`，骨架照搬 `spawn_notifier`（escalation.py:676-797）**但 floor 方向與 notifier 完全相反**。

| start-line.sh 對應 | notifier 做法（相反） | inbound worker 必做 |
|-------------------|---------------------|---------------------|
| `set ::env(SME_FLOOR) $layer`（:45） | `env.pop("SME_FLOOR")` 取全權限 | **`env["SME_FLOOR"] = target_floor`**（絕不 pop、絕不空、絕不含 `$`/`{`）。spawn 前**斷言非空**，空則拒 spawn + enqueue escalation 報「floor 解析失敗」 |
| （新增）verified actor 對位 | 無 | **`env["SME_ACTIVE_UNIT_ID"] = unit_id`**（紅隊④，per-msg active-request 對位） |
| `cd $floor`（:46） | `cwd=project_root` | **`cwd=data/<target_floor>`**（中和 harness 把 cwd('.') 塞 allowWrite 的破口） |
| `--settings $settings`（:50） | （notifier 不帶 floor settings） | **`--settings .claude/line-runtime-<target_floor>.json`**（牆#1 檔案牆，與 interactive 同一份；絕不誤用 line-runtime-settings.json 全權限預設層） |
| `--tools` built-in 白名單（:50） | `--disallowedTools Bash Edit Write Read` | **`--allowedTools ToolSearch Read Bash Edit Skill mcp__line__reply mcp__line__reply_flex mcp__line__mark_read mcp__business-db__*`**（比 notifier 寬：要 Read 判決書 PDF + Bash/Skill 跑 legal-admin 流程；但不含 Agent/Monitor/Task/Cron/Workflow = 等效砍逃逸工具） |
| （env 物理隔離） | `env.pop("ANTHROPIC_API_KEY")` | **照抄**（走 Max 訂閱、不走 metered API） |
| （防遞迴） | `SME_NOTIFIER=1` | **`env["SME_INBOUND_WORKER"]="1"`** + 進程開頭 `if os.environ.get("SME_INBOUND_WORKER"): return` |
| 牆#2 資料牆 | （business-db apply_floor_policy 自動隨 SME_FLOOR） | **不需額外做事**：worker fork 自己 business-db 子進程，server.py:644 自動依 SME_FLOOR 砍工具 |
| mcp-config 安全 | mkstemp 0600 受保護 state dir、GC、絕不 /tmp | **照抄**（/tmp 在每層 allowWrite 內、受限層員工可劫持注入惡意 MCP server；舊碼 0644 /tmp 是 #27 根因） |
| spawn 護欄 | debounce lock + pre-spawn guard | **照抄**（SQL 條件改 inbound 版「沒 claimable 且逾 hard-deadline 的 row 就不起」） |
| Popen | `start_new_session=True, stderr→log` | **照抄**（stderr→`data/inbound-worker.log`） |

**worker prompt `_INBOUND_WORKER_PROMPT`**（鏡像 `_NOTIFIER_PROMPT` 窄任務風格，reaper 把 unit rows 的 `id/chat_id/channel_id/content/user_id`+附件絕對路徑內嵌進 prompt）：

> 你是 inbound 補處理器。①**處理前先確認 claim_token 仍屬於你**（呼叫 business-db 驗租；不是 → 放棄不處理）。②處理這批 LINE 訊息（已按 id 升序＝送達序、PDF 先；同發訊者短時間多則視為一次溝通，先讀 `[檔案]` PDF 再讀文字指示合判）。③走 legal-admin 流程：判決書/裁定 PDF → pdf skill 抽取 → `stage_deadline_intake`（寫 pending_intakes、推回 LINE 一鍵確認；**絕不端出 computed deadline**；撞 UNIQUE 表示已有人抽過、改讀既有 intake）；需審核走 `create_approval`。④**每則務必呼叫 `reply(line_message_id=...)` 或 `mark_read(line_message_id=...)` 收尾**（claim-before-push、是唯一 ack）。⑤long-task 中週期呼叫 `renew_inbound_lease` 續租（防 active-request 10 分過期）。⑥做完即結束。

HITL loop 靠 #H2 已外部化的 `pending_intakes`/`approvals`：人之後回「確認 #N」是另一則新 inbound、走同一路由（可能另一支 single-shot）讀 awaiting intake + `create_deadline(confirm_intake_id=N)` 續接 —— loop 由 DB 串起、跨 single-shot 不需同進程在線。

---

## 5. 分階段實作計畫

> 原則：每階段可獨立交付 + 獨立測。**標★者純複用既有 pattern（escalation/H1/H2），風險低。**

### 階段 1：line MCP 退化成 pure IPC client（解耦前置、零行為改變）
- **改** `server.ts`：刪 `isPortInUse` owner 自選分支（:482-492），啟動一律 `connectIpc()`；保留 reply/reply_flex/multicast/mark_read/list_channels 工具不動。
- **可獨立交付**：此時 webhook 還沒抽出，但 line MCP 不再搶 owner（暫由手動跑一個 server.ts 當 owner 過渡）。
- **測**：起兩個 session，確認都當 client、不搶 port；reply 仍正常翻 status。

### 階段 2：migration 015 + claim-lease 骨架 ★（純複用 escalation）
- **新** `015_line_messages_inbound_lease.sql`、`shared/inbound.py`（`_INBOUND_CLAIMABLE_WHERE`/`_INBOUND_CLAIM_UPDATE`/常數）。
- **改** `test_smoke_all.py`：cross-file guard（`_ACK_WINDOW_SEC == 活session短租`、`_INBOUND_CLAIM_TTL_MIN*60 > _ASSUMED_MAX_WORKER_SEC`、`_HARD_DEADLINE_MIN*60 > _ACK_WINDOW_SEC`、`_ACK_WINDOW_SEC < 600`）。
- **測**：單元測 CAS rowcount（兩路搶同 row 只一個贏）、TTL reclaim。

### 階段 3：line-gatewayd daemon（核心抽離）
- **新** `daemon.ts`：import server.ts 純函式（verifySignature/downloadLineContent/resolveTargetFloor/writeActiveRequest/saveMessageToDb/lineGetProfile），接管 webhook+IPC+ngrok+presence握手+附件複製進 `data/<floor>/inbox-media`+heartbeat。
- **新** `start-line-daemon.sh` / `sme-line-gatewayd.service`（無 SME_FLOOR=operator、pkill 殘留、systemd Restart=always+WatchdogSec）。
- **改** `server.ts`：補 IPC `hello` 握手送 floor。
- **測**：daemon 起、session 全當 client、收訊寫 queued+target_floor、附件落該層 inbox-media；**殺 session → 確認 webhook 仍活、訊息仍進 DB**（這是整個架構的核心驗收）。

### 階段 4：ack 改 per-unit + claim-before-push（紅隊②③）
- **改** `server.ts` reply/reply_flex/mark_read：加 `line_message_id`（注入場景必填）、claim-before-push、per-unit 翻、`acked_message_id`、`ack_all` opt-in。
- **改** `daemon.ts`：小窗 debounce 聚合 unit、注入 meta 帶 unit_id/line_message_id/claim_token/enqueued_ms（**全 String()**，#182）。
- **測**：PDF+文字同 chat → 確認 reply 文字**不**誤翻 PDF row；wedged session 醒來 reply 撞 rowcount==0 不送（模擬 token 失效）。

### 階段 5：fallback worker spawn + gate-consume + 下游冪等（紅隊①）
- **新** `reap_inbound.py`（cron 薄殼，鏡像 flush_escalations.py ★）；`shared/inbound.py` 補 `reap_and_spawn_inbound()`/`spawn_inbound_worker()`/`_INBOUND_WORKER_PROMPT`/`renew_inbound_lease`。
- **改** `daemon.ts`：in-process ack-timer（品質層）。
- **改** `deadlines/service.py` + `repository.py`：create_deadline/stage_intake 入口 gate-consume；pending_intakes `(chat_id,source_message_id)` UNIQUE（migration 015 補）+ INSERT OR IGNORE；deadlines `(matter,type,evt,date) WHERE status!='cancelled'` UNIQUE + create_deadline 先檢查 awaiting + deadline 存在再 insert（修 service.py:378 順序）。
- **改** `auth.py` + `server.ts`：active-request per-unit keying + gate 綁 floor + resolve_approval 綁 row.user_id（紅隊④）。
- **測**：presence=0 → spawn worker 處理 PDF；**雙處理者同 unit → 第二個 gate-consume rowcount==0 放棄 + stage_intake 撞 UNIQUE 讀既有**（確認只一筆 intake、一筆 deadline）；basic 助理 worker 不借 manager 權限（紅隊④回歸測）。

### 階段 6：看門狗 + install.sh 真的裝 cron（紅隊⑤，補「宣稱有但沒裝」）
- **新** `gateway_watchdog.py`（cron */1：daemon heartbeat 年齡 > `LINE_GATEWAY_STALE_MIN(3)` / fetch localhost:4040 tunnel 探針 / 最近 inbound 年齡 → enqueue_escalation `line_gateway_stalled`，**走 flush_escalations.py 路徑直打 LINE API、繞過死 daemon**）。
- **改** `deadlines.py`：`check_scan_health`/`scan_health_and_alert` 加「queued 逾 hard-deadline 卻零 claimed_at」偵測（reaper 也死的 dead-man）。
- **改** `daemon.ts`：ngrok 子進程加 `child.exited` 監聽 → 自動重起 + 重 PUT webhook endpoint + 落 `interaction_log`（補 server.ts:950 零監督）；NGROK_DOMAIN 未設時改「啟動自己 ngrok 拿隨機 URL 再 PUT」而非整段跳過（修 server.ts:937 黑洞）。
- **改** `install.sh`：補裝 `reap_inbound.py`（*/1）+ `gateway_watchdog.py`（*/1）+ `scan_heartbeat.py`（既有 #H1、之前沒裝）三支 cron，且鏡像現有 pgrep cron 檢查（install.sh:200，沒跑就 err 叫人 `service cron start`）。
- **改** `knowledge/service.py`：全權限層 readout 加 queued backlog / claimed-stale / dead-letter 三數（full_access 早退之後）。
- **測**：殺 daemon → watchdog escalate 到老闆 LINE（繞過死 daemon）；殺 ngrok 留 daemon → 4040 探針抓到。

### 階段 7：dead-letter 收尾
- **改** `shared/inbound.py`：`_INBOUND_MAX_ATTEMPTS=3`，達上限不再自動 spawn → enqueue escalation `inbound_undeliverable`「請人工看 line_messages #<id>」；**row 不進終態、status 仍 queued**（人工 reply/mark_read 翻走）。`reclaim ≠ failed`（紅隊與 escalation 最不能照抄處：escalation `max_retry→failed` 會把客戶訊息標終態靜默漏）。
- **測**：worker 連續 crash 3 次 → 轉人工 dead-letter、row 仍可被人工處理。

---

## 6. 待老闆拍板的開放參數

1. **`_ACK_WINDOW_SEC`（注入後等多久才 fallback）**：建議 **90s**。更短=客戶更快收到 fallback 回覆但活 session 容易被搶（重複處理風險↑）；更長=活 session 更從容但客戶久等。**legal-admin 寧重勿漏，但「重」在本域=兩個矛盾到期日，所以不建議過短。**
2. **reply 工具接 daemon 還是直打 LINE**：本架構選 **worker/session 各自 line MCP 子進程直打 LINE**（解耦、daemon 死不影響回訊）。替代方案=reply 統一經 daemon 轉發（集中 rate-limit、但 daemon 成更大 SPOF、且 worker 要新 IPC 協定）。**建議維持直打。**
3. **daemon 看守方式**：WSL2（本專案實際環境）**無 systemd** → 選 (a) 手動 `systemctl --user`（需先開 WSL systemd 支援）或 (b) `@reboot while-true` bash keepalive + watchdog cron 兜 hang。**建議 (a) 若可開 systemd（WatchdogSec 救 hang），否則 (b)+watchdog。** 此項影響「daemon hang 偵測」能力，必須老闆知情。
4. **是否保留持久 interactive session 當主路徑**：建議 **保留**（連續對話 + in-session escalation push 的 UX 遠優於每則 single-shot）。single-shot 是 fallback 不是主路徑。替代=全砍持久 session、一律 single-shot（架構更簡單、但失去連續對話、每則冷啟動延遲、資源放大）。
5. **URL 穩定方案**：ngrok reserved domain（付費）vs cloudflared named tunnel（免費但需設定）vs 免費 ngrok 隨機 URL（每次重啟換 URL、災難）。**建議 setup 階段 fail-closed 擋掉「沒固定 URL 還想跑 daemon」。**
6. **`_INBOUND_CLAIM_BATCH`（並發上限）**：建議 **3**。尖峰（早上一批判決書）多 chat 並發會撞訂閱併發上限，調高=drain 快但資源/額度壓力大。

---

## 7. 明確不做 / 砍掉的（防 scope 膨脹）

1. **不做 #11 on-demand 列級過濾**：worker 跑 legal-admin 查案件/時限若用 `list_orders`/`check_stock`/`find_customer`/`list_tasks` 仍 fail-open（非全權限層省略 BU 撈全 BU）。**本架構不解、文件絕不可宣稱「部門層只看得到自己 BU」**；legal-admin 機密案件靠 matters/deadlines 的 `confidential` 欄列級過濾，`LEGAL_CONFIDENTIAL_TOOLS` 預設不啟用（不砍整支）。
2. **不做 follow/join 事件兜底**（候選 §5.6）：這類不落 line_messages → reaper 救不到。**列為已知殘留**（§8.4），階段 6 可選把 follow/join 也落 queued（標 optional、非本批必做）。
3. **不做 video/audio STT**：不下載（server.ts:738-743 佔位字串）。worker 看到佔位字串只回「目前無法處理語音/影片、請改傳文字或截圖」+ mark_read，**不假裝處理**。
4. **不做 reply 統一經 daemon 轉發**（§6.2）：維持直打 LINE。
5. **不做 floor-map 路由收斂（#13）的完整版**：§3.6 連帶項標為依賴、僅在 #13 落地後啟用；本批靠 per-unit keying + gate 綁 floor（縱深防禦已足夠擋權限提升，路由收斂只降頻率）。
6. **不做 active-request 改 per-message 之外的更細粒度**（如 per-tool-call）：per-unit keying 已收斂主要 race，更細不划算。
7. **不做群組非 @mention 兜底**：連 DB 都不寫（server.ts:697-708）、無 row 可兜，沿用現狀。

---

## 8. 誠實標出的殘留風險與不確定處

1. **worker 忘走 reply/mark_read 翻 status（紅隊未完全解）**：claim 租約只防併發、gate-consume 防重複建資料，但若 worker 處理完忘 ack → row 留 queued 被 TTL reclaim 重撈。**緩解**：prompt 鐵律 + gate-consume 後 status 仍 queued 會被縱深 reclaim（但因已 consumed_at、第二個 worker gate-consume rowcount==0 不會重建資料、只會重 reply）→ 退化成「重複回覆」而非「重複建期限」。**仍是 LLM 不保證 100% 呼叫工具的殘留、無法靠常數補。**
2. **claim_token re-validate 依賴 worker/session 主動驗租（紅隊③緩解非根除）**：步驟 [6]/[10] 的 re-validate 在 reply 工具內 enforce（claim-before-push 是 server.ts 層、不靠 LLM）→ outbound 那道是硬的；但「處理前先驗租」那道若 LLM 漏做，仍會做完整套抽取才在 reply 撞 0 changes（白做工、但不雙送）。**可接受（不破，只浪費 compute）。**
3. **daemon 是新集中 SPOF**：daemon 死的真空期新訊息 connection refused、LINE retry 後放棄 = **該則真丟、reaper 撈不到不存在的 row**。**緩解**：systemd RestartSec=2 + gateway_watchdog 走 flush 路徑繞過死 daemon 告警；**WSL 無 systemd 時 hang 偵測降級為 watchdog 分鐘級**。**這是整個架構唯一無法完全消滅的真丟窗口、老闆必須知情**（§6.3）。
4. **follow/join + video/audio 黑洞**（§7.2/7.3）：誠實列為不解。legal-admin 委任人加好友後第一句若是 follow 事件夾帶會丟。
5. **LINE push 假成功不可偵測**：對未加 OA 好友者 reply 回 200 但不達 → status 翻 replied 但對方沒收到（LINE 平台限制、與現狀同限制）。靠 onboarding 要求加好友。
6. **active-request per-unit keying 的部署過渡**：階段 5 切換期間，舊全域 fallback（auth.py:26）要關，但若 daemon 與舊 session 並存可能短暫對不上 actor → 部署必 `pkill -f` 舊 webhook owner 再起 daemon（MEMORY 已記此 gotcha）。
7. **TTL 估錯仍可能重複回覆（非重複建期限）**：worker 處理超 `_ASSUMED_MAX_WORKER_SEC(12分)` 被 reclaim → 第二隻 worker 起，但 gate-consume + 下游 UNIQUE 確保**不重建期限**、只可能重 reply。**legal-admin 域接受「偶發重複回覆」優於「漏掉」，且已消除「兩個矛盾到期日」這個比漏更危險的失敗模式。**
8. **不確定：CC channel notification 的 turn 邊界**：兩個 notification 是否一定觸發兩個 turn、或可能合併一個 turn，文件無明確保證。本架構靠「daemon 小窗 debounce 聚合成一次注入 + per-unit ack」規避對 turn 邊界的依賴（§5 階段 4），但 **wedged session 醒來重放舊 turn 的精確 CC 行為仍是 best-effort 攔截（claim-before-push 是最終硬防線）**。
9. **不確定：cloudflared/ngrok 子進程在 WSL2 mount 下的穩定性**：MEMORY 記 codex image_gen 曾遇 WSL bubblewrap 卡 /mnt/d/ mount；tunnel 子進程在 WSL2 的長期穩定性需 live 驗（階段 6 watchdog 是兜底、但 URL 抖動頻率未知）。

---

**實作參考錨點（均已讀確認）**：
- `/mnt/d/gitDir/sme-ai-kit/mcp-servers/line-channel/server.ts`：reply/reply_flex/mark_read ack UPDATE per-chat 無 lease（:376/:404/:444）、autoSetupNgrok 跳過邏輯+ngrok 零監督（:937-988）、shutdown stdin close（:1006-1011）、IPC 無 floor 握手（:865）、client.write 只 socket-closed 才 catch（:536-540）
- `/mnt/d/gitDir/sme-ai-kit/mcp-servers/business-db/shared/auth.py`：_check_permission 只查全域 permission 不綁 floor/row（:57-72）、active-request 舊全域 fallback（:26）、10 分 TTL（:34）、_resolve_trusted_actor（:40-54）
- `/mnt/d/gitDir/sme-ai-kit/mcp-servers/business-db/shared/escalation.py`：CAS 鎖在唯一副作用前（:430-432）、claim/send 分 tx 不變量（:407-432）、spawn_notifier 完整 shape（:676-797）
- `/mnt/d/gitDir/sme-ai-kit/mcp-servers/business-db/modules/deadlines/service.py`：confirm_intake_id 守衛在 insert 之後、只補 _NOMATCH 不 rollback（:378-402）、stage_deadline_intake（:657）
- `/mnt/d/gitDir/sme-ai-kit/mcp-servers/business-db/modules/deadlines/repository.py`：insert_deadline 裸 INSERT 無 UNIQUE（:93）
- `/mnt/d/gitDir/sme-ai-kit/install.sh`：只裝 flush_escalations.py、scan_*.py 全沒裝（:184-205）、pgrep cron 檢查範本（:200）
- `/mnt/d/gitDir/sme-ai-kit/mcp-servers/business-db/migrations/010_escalation_claimed_at.sql`（claimed_at 範本，新 migration 為 015）
- `/mnt/d/gitDir/sme-ai-kit/mcp-servers/business-db/migrations/014_pending_intakes.sql`（#H2 HITL 外部化範本）
- `/mnt/d/gitDir/sme-ai-kit/mcp-servers/business-db/flush_escalations.py`（cron 薄殼 + 直打 LINE API、繞過 daemon）
- `/mnt/d/gitDir/sme-ai-kit/start-line.sh`（floor 重建範本 :45-50）
- `/mnt/d/gitDir/sme-ai-kit/mcp-servers/business-db/tests/test_smoke_all.py`（cross-file guard :2509-2532）