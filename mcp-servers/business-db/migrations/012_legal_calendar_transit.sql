-- legal-admin vertical：時限計算的「外部資料底」— office_calendar（辦公日曆）+ transit_period（在途期間查表）
--
-- 設計依據：docs/legal/01-deadline-engine.md §2「需要的外部資料底（data layer）」、§5。
-- 鐵律：末日順延（民法§122）一律讀 office_calendar（不可自行硬算週末——含補班/調移/颱風假）；
--       在途期間（民訴§162）查 transit_period（MVP 預設「有住法院所在地代理人 → 在途=0」）。
--
-- 核心「法定期間種子」（民訴§440 上訴 20 日…）刻意「不入表」、改放程式常數
-- shared/deadlines.py STATUTORY_PERIODS：理由——
--   1. 法定天數 + statutory_basis + 版本是「反捏造」命脈，放程式常數可隨原始碼版控、
--      可直接單元測試對照法條、修法時 diff 一目了然（migration 改 seed 反而難覆核）。
--   2. compute_deadline 是純函式、查種子不該依賴 DB 連線（service 與 cron 共用、避免 import DB）。
--   3. build contract §8「表或程式常數擇一」——選程式常數。office_calendar / transit_period
--      因「cron 與 service 都要查、且資料量大、需逐日/逐組合」才落表。
--
-- 新表只走 migration、不寫進 schema.sql（fresh-install 雙寫=崩潰、test_migration_safety 明文擋）。

-- === office_calendar（辦公日曆）— 末日順延（民法§122）讀本表 ===
-- date 為主鍵（YYYY-MM-DD）；is_holiday=1 表「非上班日」（週末 / 國定假日 / 休息日）。
-- 注意：表內「只記與『預設週末規則』不同或需明列的日」即可，但 MVP 為求 is_holiday() 邏輯單純、
--       週末由程式判斷（date.weekday() >= 5）、本表負責「國定假日 + 補班（週末要上班）」兩類例外。
--   is_holiday=1 + 非週末 → 平日的國定假日（如 2026 元旦）
--   is_holiday=0 + 週末   → 補班日（週末要上班、不順延，如颱風補班）
CREATE TABLE IF NOT EXISTS office_calendar (
    date TEXT PRIMARY KEY,                  -- YYYY-MM-DD
    is_holiday INTEGER NOT NULL DEFAULT 1,  -- 1=非上班日（順延）/ 0=上班日（補班、不順延）
    description TEXT,                        -- '中華民國開國紀念日' / '颱風補班' …
    source TEXT,                            -- 'DGPA 2026 辦公日曆表' / 'ruyut/TaiwanCalendar'
    CHECK (is_holiday IN (0, 1))
);

-- === transit_period（在途期間查表）— 在途加算（民訴§162 / 行政程序）讀本表 ===
-- MVP：預設「有住法院所在地代理人 → 在途=0」（compute_deadline 直接歸零、不查表）；
-- 本表供「無當地代理人」罕見組合查表用。查不到組合 → compute_deadline 標 needs_manual_review、不臆測。
CREATE TABLE IF NOT EXISTS transit_period (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    court_region TEXT NOT NULL,             -- 受訴法院所在區域代碼（如 'taipei' / 'kinmen'）
    party_region TEXT NOT NULL,             -- 當事人住居地區域代碼（如 'kinmen' / 'overseas_asia'）
    days INTEGER NOT NULL,                  -- 在途天數
    basis_version TEXT NOT NULL,            -- '司法院在途期間標準 B0010020 v107.7.1'（反捏造：附依據+版本）
    note TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    UNIQUE(court_region, party_region),
    CHECK (days >= 0),
    CHECK (basis_version <> '')             -- 反捏造：在途天數一樣要有依據
);

CREATE INDEX IF NOT EXISTS idx_transit_period_lookup
    ON transit_period(court_region, party_region);

-- === office_calendar 種子：2026 台灣國定假日（一小批、供測試與末日順延）===
-- TODO（deploy 步驟）：完整年度日曆 import DGPA《政府行政機關辦公日曆表》或 ruyut/TaiwanCalendar JSON
--   （含補班/調移/颱風假）；本批僅種「跨假日不停止計算」與「末日順延」測試需要的關鍵日。
-- 來源：行政院人事行政總處 115 年（2026）政府行政機關辦公日曆表。
INSERT OR IGNORE INTO office_calendar (date, is_holiday, description, source) VALUES
    ('2026-01-01', 1, '中華民國開國紀念日', 'DGPA 2026 辦公日曆表'),
    ('2026-02-14', 1, '農曆除夕前彈性放假（調整放假）', 'DGPA 2026 辦公日曆表'),
    ('2026-02-16', 1, '農曆除夕', 'DGPA 2026 辦公日曆表'),
    ('2026-02-17', 1, '春節（初一）', 'DGPA 2026 辦公日曆表'),
    ('2026-02-18', 1, '春節（初二）', 'DGPA 2026 辦公日曆表'),
    ('2026-02-19', 1, '春節（初三）', 'DGPA 2026 辦公日曆表'),
    ('2026-02-20', 1, '春節（初四，調整放假）', 'DGPA 2026 辦公日曆表'),
    ('2026-02-27', 1, '和平紀念日彈性放假（調整放假）', 'DGPA 2026 辦公日曆表'),
    ('2026-02-28', 1, '和平紀念日', 'DGPA 2026 辦公日曆表'),
    ('2026-04-03', 1, '兒童節及民族掃墓節彈性放假', 'DGPA 2026 辦公日曆表'),
    ('2026-04-04', 1, '兒童節', 'DGPA 2026 辦公日曆表'),
    ('2026-04-06', 1, '民族掃墓節補假', 'DGPA 2026 辦公日曆表'),
    ('2026-05-01', 1, '勞動節', 'DGPA 2026 辦公日曆表'),
    ('2026-06-19', 1, '端午節', 'DGPA 2026 辦公日曆表'),
    ('2026-09-25', 1, '中秋節', 'DGPA 2026 辦公日曆表'),
    ('2026-10-09', 1, '國慶日彈性放假（調整放假）', 'DGPA 2026 辦公日曆表'),
    ('2026-10-10', 1, '國慶日', 'DGPA 2026 辦公日曆表');

-- 補班日範例（週末要上班、不順延）：對應上方某次調整放假的補班。
-- 2026-02-07（六）補 02-20（春節初四）的班 → is_holiday=0（週末但仍是上班日、末日落此不順延）。
INSERT OR IGNORE INTO office_calendar (date, is_holiday, description, source) VALUES
    ('2026-02-07', 0, '補班（補 02-20 春節調整放假）', 'DGPA 2026 辦公日曆表');
