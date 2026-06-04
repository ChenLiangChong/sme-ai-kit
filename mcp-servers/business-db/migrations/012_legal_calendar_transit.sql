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

-- === office_calendar 不在 migration 種任何資料（codex r4 HIGH：避免半套年度陷阱）===
-- 為何不種：calendar_year_loaded 已改為「該年逐日完整（365/366）才算已載入」。若 migration 種「部分
-- 年度」（如舊版僅種 ~17 天 2026 假日），會落入「半套被當已載入、缺的國定假日靜默退回週末預設＝
-- 末日順延誤算」的陷阱（且舊版 2026-02-07 補班還是錯誤臆測）。故 migration 只建「空表 + index」。
-- 正解：辦公日曆一律由 import_office_calendar.py 吃官方來源 JSON（行政院人事行政總處辦公日曆 /
--   ruyut TaiwanCalendar）**整年逐日**匯入（匯入器強制單一年度逐日完整、雙重把關）。
--   部署步驟見 .claude/skills/legal-admin/references/privacy-deploy.md；
--   測試以 tests/fixtures/taiwan_calendar_<年>.json 真實整年檔匯入（test_deadline_engine.py）。
-- 未載入任何完整年度時，compute_deadline 對該年期限一律標 needs_manual_review（fail-toward、不靜默誤算）。
