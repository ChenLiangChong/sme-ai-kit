-- legal-admin vertical（#H2）：待確認時限暫存表 pending_intakes
--
-- 解決的盲區：核心 loop 第二步「一鍵確認才入」刻意把人擋在中間（律師業必須人擋中間、SPEC 核心）。
-- 副作用＝丟了檔、AI 推確認、人忘了回 → 時限沒進 deadlines 表 → 一般掃描（WHERE status='pending'）
-- 掃不到 → 隱形漏掉（漏期＝執業過失）。本表讓「待確認」變成可掃描狀態，cron（scan_unconfirmed_intake.py）
-- 跟催「有 M 件待確認、最久 X 小時」。
--
-- 反捏造設計（結構性）：本表只存「抽出的事實」（送達日 / 文書類型 / 教示天數 / 文書作成日），
--   刻意「不放任何 computed deadline 欄」——待確認階段 compute_deadline 根本還沒跑、權威日期尚不存在，
--   故結構上不可能把未經引擎確認的權威日期洩出去。確認入庫一律走 create_deadline（引擎確定性計算）。
--
-- 新表只走 migration、不寫進 schema.sql（fresh-install 雙寫=崩潰、test_migration_safety 明文擋）。
-- 每行一 statement、不含 TRIGGER / BEGIN / COMMIT（splitter 限制）。

CREATE TABLE IF NOT EXISTS pending_intakes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    -- 母案件：抽取當下案件可能還沒建（剛收到判決），故可為 NULL；案件被刪→SET NULL（跟催仍要看得到）
    matter_id INTEGER REFERENCES matters(id) ON DELETE SET NULL,
    matter_label TEXT,            -- 顯示用快照（案號 / 案件代號 / 案由；去識別化、勿放當事人姓名）
    doc_type TEXT,                -- 文書類型（人話或 create_deadline 的 type 代碼）
    service_base_date TEXT,       -- 送達日（抽出的事實、YYYY-MM-DD；未經引擎計算）
    stated_period_days INTEGER,   -- 判決書「上訴教示」所載天數（抽出的事實；NULL=未提供）
    document_date TEXT,           -- 文書作成日（裁判日；抽出的事實；NULL=未提供）
    extracted_summary TEXT NOT NULL,  -- 一行人話摘要（推回 LINE 請人確認的那條；不可空）
    submitted_by TEXT,            -- 誰丟的檔 / 誰要算（回頭催誰）
    status TEXT NOT NULL DEFAULT 'awaiting',  -- awaiting（待確認）/ confirmed（已入庫）/ discarded（不算了）
    reminders_sent TEXT DEFAULT '[]',  -- 冪等鑰：已提醒過的等待節點（小時）JSON list
    resolved_deadline_id INTEGER, -- 確認入庫後連到 deadlines.id（稽核對位；不放回算結果、僅外鍵）
    resolved_at TEXT,             -- 確認 / 捨棄的時間
    resolved_by TEXT,             -- 確認 / 捨棄的操作者
    created_at DATETIME DEFAULT (datetime('now', 'localtime')),
    CHECK (status IN ('awaiting', 'confirmed', 'discarded')),
    CHECK (extracted_summary <> '')
);

-- partial index：cron 只掃 awaiting（待確認）那批，與 deadlines pending 索引同模式
CREATE INDEX IF NOT EXISTS idx_pending_intakes_awaiting
    ON pending_intakes(status) WHERE status = 'awaiting';

CREATE INDEX IF NOT EXISTS idx_pending_intakes_matter
    ON pending_intakes(matter_id);
