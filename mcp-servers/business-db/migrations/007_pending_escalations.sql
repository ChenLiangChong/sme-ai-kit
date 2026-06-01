-- 007: REPORT 硬接線佇列 pending_escalations（決策 #162「REPORT 必硬」/ #173 重設計版）
--
-- 模型「部門硬牆 / 角色軟(上報為主)」的「上報」那一半：員工/有權幹部做了「主管該知道的事」，
-- service 層在「真正執行那支 tool 的同一個 transaction 內」無條件寫一筆上報（agent 看不到、跳不過），
-- 再由「笨投遞器」flusher（OS cron 獨立腳本 / line-channel owner inbound 搭便車、非 setInterval daemon）
-- 讀 status='pending' 推給主管。
--
-- 與 approvals 的語意差異（不可混用）：
--   approvals = 閘（gate_check 擋住操作直到核准、verify_resume_params 一字不差、gate_consume 單次綁定 record）。
--   escalation = 只通知（不擋業務、不需參數比對、不綁 record）。狀態機只有 pending → sent / failed。
--
-- 設計要點（對抗審查 wks27te3k 收斂）：
-- 1. actor 與 target_line_user_id 一律在「enqueue 當下」(service in-tx、active-request 還在) 解析寫死；
--    flusher 是純「讀 row → push → UPDATE」的 dumb 投遞器、不重算身份/收件人（背景 flush 時 active-request 早被清）。
-- 2. retry：未拿到 LINE API 真 ok 不可標 sent（push 對未加 OA 好友的主管回 200 但靜默不達＝假成功）；
--    retry_count + last_attempt_at + 終態 failed，達上限/毒丸進 failed、由全權限層開機 readout 提醒老闆。
-- 3. target_floor 存「目標層（該被誰看到）」非「觸發層」：部門層 session 不該撈到自己被上報的事；
--    MVP fallback 老闆層（'confidential' 或 NULL）。觸發者/觸發 BU 另存 actor / business_unit 供稽核。
-- 4. 範圍紀律（#162 skeptic 已砍）：不做 severity 分級 / digest 聚合 / anomaly / rate-limit（降 v2）。
--    高頻 trigger（cross_bu_access）預設關，要開再加 dedup（不在本 migration）。
--
-- 慣例：新表只走 migration、不寫進 schema.sql（同 leave_* / access_zones）。純 DDL、過 splitter guard。

CREATE TABLE IF NOT EXISTS pending_escalations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,             -- transaction_recorded_over_threshold / order_cancelled_shipped / employee_permissions_changed / qc_failed / transaction_deleted / cross_bu_access ...
    summary TEXT NOT NULL,                -- 一行人話摘要（推給主管的內文主體）
    detail TEXT,                          -- 完整 JSON（target_type/target_id/amount/原始 actor 等）供事後稽核
    actor TEXT,                           -- 可信觸發者（enqueue 當下 _resolve_trusted_actor 取的 verified user_id / 員工名 / '__unverified__'）
    business_unit TEXT,                   -- 觸發事件所屬事業體（NULL=全域/未指定）
    target_floor TEXT,                    -- 「目標層」：該被哪層/主管撈到（MVP 老闆層 'confidential' 或 NULL）
    target_line_user_id TEXT,             -- enqueue 當下解析出的收件主管 LINE user_id（NULL=當下無收件人、留 pending 等 onboarding 種老闆）
    channel_id TEXT,                      -- 用哪個 OA 推（觸發來源 channel 優先、否則 default）
    status TEXT NOT NULL DEFAULT 'pending',
    retry_count INTEGER NOT NULL DEFAULT 0,
    last_attempt_at DATETIME,
    created_at DATETIME DEFAULT (datetime('now', 'localtime')),
    sent_at DATETIME,
    CHECK (status IN ('pending', 'sent', 'failed')),
    CHECK (summary <> '')
);

-- flusher 撈待送的 hot path（部分索引、僅 index pending、仿 idx_approvals_unused）
CREATE INDEX IF NOT EXISTS idx_pe_pending ON pending_escalations(status) WHERE status = 'pending';
-- 全權限層開機 readout 按目標層撈失敗/無收件人
CREATE INDEX IF NOT EXISTS idx_pe_floor ON pending_escalations(target_floor);
