-- 011: scheduled_reminders — runtime 自助排程的週期/一次性提醒（「派工器模式」）
--
-- 背景／決策：受限與機密層 runtime 跑在 bwrap sandbox 內、allowWrite 不含 crontab spool ＋ Cron* 工具被砍，
-- 無法自寫 OS cron（這是刻意的第一道牆：cron job 跑在 sandbox 外＝host 持久化逃逸原語）。為了讓 runtime
-- 仍能「自助排程定時提醒、達 OS-cron 級可靠、不必每次喊老闆」，一般化既有 escalation 模式：
--   runtime 經 gated MCP 工具 schedule_reminder 寫一筆 row（碰不到 crontab）→ 人工裝一次的笨投遞器
--   reminder_dispatcher.py（OS cron、host 跑、讀得到 DB＋LINE token）定時讀到期 row 推播。
--
-- 與 pending_escalations 的語意差異（不可混用）：
--   escalation = 被動觸發（硬接線、事件發生才寫）、at-least-once 必達、只通知主管。
--   reminder   = 主動排程（runtime 預先排）、at-most-once（漏一次 < 洗版群組）、recurring 自動推進 next_fire_at。
--
-- 投遞 claim＝next_fire_at CAS 前進（並發 dispatcher 不雙送）；once 送完 status='done'、
-- recurring 由 runtime 在條件達成時 cancel_reminder（自動完成＝v2）。floor gate：schedule/cancel/list
-- 對非全權限層移除（排程＝定時推播任意對象、broadcast-ish；只機密層/operator 可排，
-- 見 floor_policy.REMINDER_ADMIN_TOOLS）。
--
-- 慣例：新表只走 migration、不寫 schema.sql（同 007/009/010）。純 DDL、無 TRIGGER、過 splitter guard。

CREATE TABLE IF NOT EXISTS scheduled_reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,                         -- 一行摘要（給 list / 老闆看）
    message TEXT NOT NULL,                       -- 實際推播給對象的完整內文（直接照送、不加系統抬頭）
    target_type TEXT NOT NULL DEFAULT 'user',    -- 'user' | 'group'（僅標示；push 一律用 target_id）
    target_id TEXT NOT NULL,                     -- 收件 LINE userId / groupId（push 的 to）
    channel_id TEXT,                             -- 用哪個 OA 推（NULL=default OA）
    recurrence TEXT NOT NULL DEFAULT 'once',     -- once | daily | weekdays（一~五）| weekly（每 7 天）
    next_fire_at DATETIME NOT NULL,              -- 下次該觸發（localtime 'YYYY-MM-DD HH:MM:SS'、字串排序即時序）
    business_unit TEXT,                          -- 所屬事業體（NULL=全域）
    note TEXT,                                   -- 完成條件/備註（如「盯到 order #123 出貨」）；不外送、只供 list 與追蹤
    status TEXT NOT NULL DEFAULT 'active',
    last_fired_at DATETIME,                      -- 上次成功推出
    last_attempt_at DATETIME,                    -- 上次嘗試（claim 當下）
    fire_count INTEGER NOT NULL DEFAULT 0,
    fail_count INTEGER NOT NULL DEFAULT 0,
    created_by_floor TEXT,                       -- 排程當下 SME_FLOOR（稽核：哪層排的）
    created_by TEXT,                             -- 排程者 actor
    created_at DATETIME DEFAULT (datetime('now', 'localtime')),
    CHECK (status IN ('active', 'done', 'cancelled', 'failed')),
    CHECK (recurrence IN ('once', 'daily', 'weekdays', 'weekly')),
    CHECK (title <> '' AND message <> '' AND target_id <> '')
);

-- dispatcher 撈到期的 hot path（部分索引、僅 index active，仿 idx_pe_pending）
CREATE INDEX IF NOT EXISTS idx_sr_due ON scheduled_reminders(next_fire_at) WHERE status = 'active';
