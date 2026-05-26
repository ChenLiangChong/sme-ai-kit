-- Phase 2.13: HITL approval gate 強化（codex final review HIGH finding）
--
-- 問題：原本 approval 一旦核准、可被任何 caller 在任何時候用 approved_id=N 繞過任何
-- 金額門檻。沒有單次使用綁定、沒有跟建立的 record 連結。
--
-- 解法：approvals 加 consumed_at / consumed_by_type / consumed_by_id。
-- - 使用前 SELECT WHERE status='approved' AND consumed_at IS NULL
-- - 使用後 UPDATE consumed_at = now, consumed_by_type/id = 建立的 record
-- - 既有未消耗的 approval 仍可第一次使用（向後相容）

ALTER TABLE approvals ADD COLUMN consumed_at DATETIME;
ALTER TABLE approvals ADD COLUMN consumed_by_type TEXT;
ALTER TABLE approvals ADD COLUMN consumed_by_id INTEGER;

CREATE INDEX IF NOT EXISTS idx_approvals_unused
    ON approvals(status, consumed_at) WHERE status = 'approved' AND consumed_at IS NULL;
