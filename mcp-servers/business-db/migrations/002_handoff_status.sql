-- 002_handoff_status.sql
-- session_handoffs 加 status / resolved_at / resolved_note
-- 目的：避免「過期 handoff 被當最新讀到」trap。新 session 接手後跑 resolve_handoff 標 resolved，
--      get_context_summary 只回 active 的、舊的留 audit log。

ALTER TABLE session_handoffs ADD COLUMN status TEXT DEFAULT 'active';
ALTER TABLE session_handoffs ADD COLUMN resolved_at DATETIME;
ALTER TABLE session_handoffs ADD COLUMN resolved_note TEXT;

CREATE INDEX IF NOT EXISTS idx_handoffs_status_created ON session_handoffs(status, created_at DESC);
