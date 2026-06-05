-- legal-admin（消滅時效 type='limitation'）：deadlines 加「年/月期間」單位欄
--
-- 為什麼：現有引擎只算「日數」（statutory_days + 末日順延、純天數連續加法）。消滅時效是「年」期間
--   （民§125=15年 / §126=5年 / §127=2年 / §197=2年+10年），依民§123「稱月或年者，依曆計算」（連續
--   計算用曆、非每年365日硬轉）+ 民§121「以年/月定期間→以最後之年/月與起算日『相當日之前一日』為末日；
--   但無相當日（如閏日2/29）→該月末日」。**不可硬把年轉天數**（閏年會差、反捏造）。
--
-- 解法：加 period_unit / period_value 兩欄：
--   - period_unit='day'（預設）→ 現有行為完全不變，期間日數仍讀 statutory_days（向後相容、既有資料不動）。
--   - period_unit='year' / 'month' → compute_deadline 走 §121 曆法分支，期間數讀 period_value（非 statutory_days）。
--
-- period_value 可為 NULL（day unit 時不用、讀 statutory_days）。SQLite 的 ALTER TABLE ADD COLUMN
--   不能帶 CHECK 約束，故 period_unit 的合法值（day/month/year）由 service 層驗證（非 DB 層）。
--
-- 消滅時效的 period_type 仍用 'statutory'（它確是「通常法定期間」、不改既有 CHECK），靠 period_unit
--   觸發曆法分支；type='limitation' + 起算點是法律判斷（§128 自請求權可行使時起算）→ 一律強制人工複核。
--
-- 新欄只走 migration、不寫進 schema.sql（fresh-install 雙寫=崩潰、test_migration_safety 明文擋）。
-- 每行一 statement、不含 TRIGGER / BEGIN / COMMIT（splitter 限制）。

ALTER TABLE deadlines ADD COLUMN period_unit TEXT NOT NULL DEFAULT 'day';

ALTER TABLE deadlines ADD COLUMN period_value INTEGER;
