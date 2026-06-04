-- legal-admin vertical：時限管理核心 — matters（案件主檔）+ deadlines（時限主檔）
--
-- 設計依據：docs/legal/01-deadline-engine.md §1.1 / §1.2、docs/legal/SPEC.md。
-- 鐵律：時限天數一律 service 層確定性計算、每筆附 statutory_basis 法條依據
--       （反捏造、絕不 LLM 心算）。calc_trace 落 JSON 供律師逐步覆核。
--
-- 偏差說明（與 01 §1.1 的差異、build contract §0 已釘）：
-- - 不建 parties 表（SPEC §22「當事人只需名字能被查到的輕量程度」、MVP 不做 CRM）。
--   matters 改用輕量 client_name TEXT 內嵌欄位；保留可選 client_party_id INTEGER
--   但「不加 FK constraint」（父表 parties 不存在、加 FK 會讓 fresh-install 的
--   PRAGMA foreign_keys=ON 後續 insert 炸）。留待 customers→parties 重構再補 FK。
--
-- 退化欄位：business_unit 單一律所、保留為 NULL 即可、不接多事業體邏輯。
-- 新表只走 migration、不寫進 schema.sql（fresh-install 雙寫=崩潰、test_migration_safety 明文擋）。

-- === matters（案件主檔 — deadlines 的父鍵）===
CREATE TABLE IF NOT EXISTS matters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_no TEXT UNIQUE,                  -- 事務所內部案號（2026-民-001）
    title TEXT NOT NULL,                    -- 案由
    client_name TEXT,                       -- 委任人名字（輕量、不做完整 CRM）
    client_party_id INTEGER,                -- 可選 → 未來 parties(id)；MVP 不加 FK constraint
    practice_area TEXT,                     -- civil/criminal/admin/family/ip/labor/non_litigation
    court TEXT,                             -- 繫屬法院（算在途期間的維度1）
    court_case_no TEXT,                     -- 法院案號（112年度訴字第XXX號）
    stage TEXT,                             -- first_instance/second_instance/third_instance/execution/...
    status TEXT NOT NULL DEFAULT 'open',    -- open/on_hold/closed/archived
    lead_attorney TEXT,                     -- 主辦律師
    has_local_agent INTEGER DEFAULT 1,      -- §162 但書：律師住法院所在地→在途歸零（律所自辦常為1）
    confidential INTEGER DEFAULT 0,         -- 機密軸 → floor 可見度（與 query_knowledge migration 006 同 pattern）
    business_unit TEXT,                     -- 退化欄位（單一律所、保留 NULL）
    opened_at TEXT,
    closed_at TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    CHECK (title <> ''),
    CHECK (status IN ('open', 'on_hold', 'closed', 'archived')),
    CHECK (has_local_agent IN (0, 1)),
    CHECK (confidential IN (0, 1))
);

CREATE INDEX IF NOT EXISTS idx_matters_status ON matters(status);
CREATE INDEX IF NOT EXISTS idx_matters_lead_attorney ON matters(lead_attorney);

-- === deadlines（時限主檔 — 本模組核心）===
CREATE TABLE IF NOT EXISTS deadlines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_id INTEGER NOT NULL,
    -- 業務語意
    type TEXT NOT NULL,                     -- appeal_civil/appeal_criminal/appeal_admin/abjection(抗告)/
                                            --   answer(答辯)/brief(準備書狀)/appeal_reason(上訴理由書補提)/
                                            --   petition_appeal(訴願)/admin_litigation/retrial(再審)/
                                            --   payment_order_objection(支付命令異議)/custom
    description TEXT NOT NULL,              -- 「對一審判決提起上訴」
    -- 性質（決定處理規則：硬牆/可補正/訓示，見 01 §3 提醒分級）
    period_type TEXT NOT NULL,             -- peremptory(不變期間)/statutory(通常法定)/court_set(裁定期間)/directory(訓示)
    severity TEXT,                         -- red(失權硬倒數)/orange(可補正)/grey(訓示僅提醒)；可由 period_type 推導預設
    -- === 計算輸入（不可省，算錯=執業過失）===
    trigger_event TEXT NOT NULL,           -- 起算事件（判決送達/裁定送達/公告/最後登報）
    service_type TEXT NOT NULL DEFAULT 'normal',  -- normal/registered_deposit(寄存)/
                                            --   public_domestic(公示境內)/public_foreign(公示外國)/commissioned(囑託)
    service_base_date TEXT NOT NULL,       -- 送達/寄存/黏貼/公告/最後登報基準日 YYYY-MM-DD
    statutory_days INTEGER NOT NULL,       -- 法定日數（民事上訴=20、抗告=10…；裁定期間=裁定所載）
    statutory_basis TEXT NOT NULL,         -- 法條依據（民訴§440）— 強制非空，反捏造
    statutory_basis_version TEXT,          -- 法規版本日（如『刑訴§349 110.06.16修正版』）
    -- === 在途期間（民訴§162）===
    in_transit_days INTEGER DEFAULT 0,     -- 查表得（無代理人除外時加算；裁定期間/有當地代理人→0）
    in_transit_source TEXT,                -- '查表 B0010020 v107.7.1：金門→台北地院 N 日' / '§162但書歸零'
    -- === 計算輸出（service 層算出後落欄、供 cron 直接讀，避免每次重算）===
    effective_date TEXT,                   -- 送達生效日（含特殊送達加算）
    start_date TEXT,                       -- 起算日（生效翌日）
    statutory_deadline TEXT,               -- 法定 hard deadline（末日順延後）— 底線、永不退讓
    buffer_days INTEGER NOT NULL DEFAULT 1,  -- 內部安全緩衝（老闆的「19天」=20-1；可設更保守）
    internal_deadline TEXT,                -- 內部 working deadline = statutory_deadline − buffer（盯這個）
    calc_trace TEXT,                       -- JSON 陣列：每步可稽核軌跡（律師逐步覆核）
    needs_manual_review INTEGER DEFAULT 0, -- 囑託/外國/在途罕見→強制人工複核、不自動結案
    -- === 狀態與提醒 ===
    status TEXT NOT NULL DEFAULT 'pending',  -- pending/filed(已遞交)/extended(已展延)/missed(逾期)/cancelled
    assignee TEXT,                         -- 負責律師
    assignee_line_user_id TEXT,            -- 提醒收件人（enqueue 蓋章用；缺則 coalesce 到 lead_attorney/boss）
    escalation_lead_days TEXT DEFAULT '[7,3,1,0]',  -- JSON：T-N 升級式提醒節點（餵 cron）
    reminders_sent TEXT DEFAULT '[]',      -- JSON：已發過的 lead_day（去重、防同一天重推），如 [7,3]
    recovery_window TEXT,                  -- JSON：逾期時回復原狀條件（原因消滅後10日內 + 民事1年上限）
    filed_at TEXT,
    filed_by TEXT,
    business_unit TEXT,                    -- 退化欄位（單一律所、保留 NULL）
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (matter_id) REFERENCES matters(id) ON DELETE CASCADE,
    CHECK (status IN ('pending', 'filed', 'extended', 'missed', 'cancelled')),
    CHECK (period_type IN ('peremptory', 'statutory', 'court_set', 'directory')),
    CHECK (statutory_basis <> ''),         -- 反捏造：每個法定天數都要有依據
    CHECK (statutory_days >= 0),
    CHECK (needs_manual_review IN (0, 1))
);

-- cron 每日掃描的 hot path（只 index 還活著的）
CREATE INDEX IF NOT EXISTS idx_deadlines_pending
    ON deadlines(status, internal_deadline) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_deadlines_matter ON deadlines(matter_id);
