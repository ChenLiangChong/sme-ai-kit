-- 010: pending_escalations 加 claimed_at（決策 #27 / codex#1：投遞租約、杜絕併發雙送 + 稽核漏記）
--
-- 缺口：cron flusher 與 claude -p notifier 兩條投遞路徑都「先送、後 UPDATE status='sent' WHERE pending」。
-- 併發時兩邊可對同一 row 都真的送出去（主管收到重複通報），但只有搶到 rowcount==1 的那一路會落
-- escalation_sent log → 打破 #27(a)「實際送出的內容一定落 log」的完整性承諾。
--
-- 修法：送前先做原子 claim（CAS 寫 claimed_at）。只有 claim 成功（rowcount==1）的那一路可發送 + 落 log，
--   輸的那路 rowcount==0 直接跳過、不重送不重記。claim 與 send 分開 transaction：claim 先 commit（讓併發
--   路徑立刻看見租約），再送（不持 write lock 過網路 I/O）。
--   notifier 經 list_pending_for_notifier claim-on-read 取得租約；cron 經 flush_pending_escalations claim。
--   claimed 但未完成（如 notifier 中途 crash）的 row 在 _CLAIM_TTL_MIN（程式常數、預設 10 分）後可被另一路
--   reclaim（status 仍 'pending'、未真送）→ 不會永久卡住。
--
-- 慣例：pending_escalations 只走 migration、不寫進 schema.sql（同 007/009）。純 DDL、單 statement、過 splitter guard。

ALTER TABLE pending_escalations ADD COLUMN claimed_at DATETIME;
