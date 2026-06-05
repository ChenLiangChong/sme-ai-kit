-- legal-admin（信任/稽核）：時限異動稽核表 deadline_audit
--
-- 為什麼：時限的命脈是「送達日 + 法定期間 → 雙日期」。一旦律師發現送達日填錯、或裁定期間天數讀錯，
--   amend_deadline 會重算雙日期——但「改了什麼、誰改的、改前改後各是什麼」必須留痕（漏期=執業過失，
--   時限被悄悄改掉卻無軌跡＝最危險）。鏡像既有 transaction_deleted 的稽核+上報模式。
--
-- 每筆 amend 落一列：before_snapshot / after_snapshot（關鍵欄位 JSON 快照）+ changed_fields（變動欄位
--   JSON list）+ amended_by（actor fail-closed 解析後的具名操作者）+ reason（為何改）。
--   amend 同 tx 另 enqueue deadline_amended 上報主持律師（接現役三層投遞）。
--
-- ON DELETE CASCADE：deadline 被刪則其稽核列隨之（稽核軌跡仍可由 interaction_log 的 deadline_amended
--   鏡像回溯）。每行一 statement、不含 TRIGGER/BEGIN/COMMIT（splitter 限制）。
-- 只走 migration、不寫 schema.sql（fresh-install 雙寫=崩潰、test_migration_safety 明文擋）。

CREATE TABLE IF NOT EXISTS deadline_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deadline_id INTEGER NOT NULL REFERENCES deadlines(id) ON DELETE CASCADE,
    matter_id INTEGER,
    amended_by TEXT,
    amended_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    reason TEXT,
    changed_fields TEXT,
    before_snapshot TEXT,
    after_snapshot TEXT
);

CREATE INDEX IF NOT EXISTS idx_deadline_audit_deadline ON deadline_audit(deadline_id);
