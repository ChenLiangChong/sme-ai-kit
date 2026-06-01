-- 009: pending_escalations 加 source_floor（決策 #27 escalation 稽核硬化「來源層蓋章」）
--
-- 缺口：主管收到的上報只說「操作者」（verified 員工名 / '__unverified__' / 空），沒說「哪一層在座」。
-- 全權限層 operator/cowork 觸發時 actor 為空 → 訊息顯示「未具名」、主管無從判斷來源與性質。
--
-- 修法：enqueue 當下由系統讀 SME_FLOOR（get_floor()）寫死「觸發層」進 row、非靠 claude -p notifier 措辭。
--   target_floor = 「該被誰看到」（收件層、MVP 老闆層 'confidential'）。
--   source_floor = 「誰幹的」（觸發層）：''＝全權限層 operator/cowork（無 SME_FLOOR）；
--                  'confidential' / 'accounting' / … ＝該部門層。既有 row 取 NULL（legacy、來源不明）。
-- cron flusher + claude -p notifier + in-session push 三條投遞路徑一致引用，主管一眼知「哪一層在座」、
-- 且「系統 vs 個人」性質可由 (source_floor, actor) 確定性推導（兩者皆系統蓋章、非 LLM）。
--
-- 慣例：pending_escalations 只走 migration、不寫進 schema.sql（同 007）。純 DDL、單 statement、過 splitter guard。

ALTER TABLE pending_escalations ADD COLUMN source_floor TEXT;
