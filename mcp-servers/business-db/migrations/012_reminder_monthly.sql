-- 012: scheduled_reminders.recurrence 新增 'monthly'（月度循環）。
--
-- 動機：請款單每月 25 日、每月例行等「月度提醒」原本 schedule_reminder 排不了
--       （011 只允許 once / daily / weekdays / weekly）。加 monthly 後月度提醒可搭
--       已在跑的 reminder_dispatcher 自動推進、不必再裝專屬 OS cron、也不靠人記。
--
-- SQLite 無法 ALTER 既有 CHECK 約束 → 標準做法：重建表（CREATE 新表 + 複製資料 +
--   DROP 舊表 + RENAME + 重建 partial index）。scheduled_reminders 無 FK、重建安全。
-- 純 DDL、無 TRIGGER、無 BEGIN/COMMIT（runner 自管 transaction）、過 splitter guard。
-- 欄位與 011 完全一致，僅 recurrence CHECK 多一個 'monthly'。

CREATE TABLE scheduled_reminders_v2 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    target_type TEXT NOT NULL DEFAULT 'user',
    target_id TEXT NOT NULL,
    channel_id TEXT,
    recurrence TEXT NOT NULL DEFAULT 'once',
    next_fire_at DATETIME NOT NULL,
    business_unit TEXT,
    note TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    last_fired_at DATETIME,
    last_attempt_at DATETIME,
    fire_count INTEGER NOT NULL DEFAULT 0,
    fail_count INTEGER NOT NULL DEFAULT 0,
    created_by_floor TEXT,
    created_by TEXT,
    created_at DATETIME DEFAULT (datetime('now', 'localtime')),
    CHECK (status IN ('active', 'done', 'cancelled', 'failed')),
    CHECK (recurrence IN ('once', 'daily', 'weekdays', 'weekly', 'monthly')),
    CHECK (title <> '' AND message <> '' AND target_id <> '')
);

INSERT INTO scheduled_reminders_v2
    (id, title, message, target_type, target_id, channel_id, recurrence, next_fire_at,
     business_unit, note, status, last_fired_at, last_attempt_at, fire_count, fail_count,
     created_by_floor, created_by, created_at)
SELECT
    id, title, message, target_type, target_id, channel_id, recurrence, next_fire_at,
    business_unit, note, status, last_fired_at, last_attempt_at, fire_count, fail_count,
    created_by_floor, created_by, created_at
FROM scheduled_reminders;

DROP TABLE scheduled_reminders;

ALTER TABLE scheduled_reminders_v2 RENAME TO scheduled_reminders;

CREATE INDEX IF NOT EXISTS idx_sr_due ON scheduled_reminders(next_fire_at) WHERE status = 'active';
