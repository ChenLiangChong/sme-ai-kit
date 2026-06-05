-- legal-admin（信任/稽核）：deadlines 持久化「建立當下的計算輸入」供 amend 忠實重算
--
-- 為什麼（codex 稽核#6b finding#1）：amend_deadline 重算一律走 compute_deadline，但原本只把「計算結果」
--   （in_transit_days / in_transit_source / 雙日期）落欄、沒存「計算輸入」（has_local_agent override、
--   court_region、party_region、in_transit 是否為人工 override）。amend 時若用「目前 matter.has_local_agent
--   + 現 row 的 in_transit_days 當 override」回推，會 drift：
--     (a) create 用過 has_local_agent override、之後 matter 改 → amend 走不同分支；
--     (b) 原靠 court_region/party_region 查表 / 行政§89 fail-toward 得到的 needs_manual_review 無法重現；
--     (c) **原查表得出的在途 >0，amend 會被重標成「手動指定在途 N 日」＝把系統查表結果偽裝成人工** ＝反捏造。
--
-- 解法：建立當下把「計算輸入」蓋章存欄，amend 直接讀回、以「與 create 完全相同的輸入」重算（provenance 忠實）。
--   compute_in_transit_override：create 傳給引擎的 in_transit override 原值（NULL=當時未 override、由
--   has_local_agent/查表決定）；amend 未改在途時沿用此值、不會把查表結果謊報成手動。
--
-- 既有資料 NULL：舊時限無這些欄 → amend 時 fallback 用 matter.has_local_agent（與舊行為一致、誠實標於
--   calc_trace），新建時限則完整蓋章。每行一 statement、不含 TRIGGER/BEGIN/COMMIT。只走 migration、不寫 schema.sql。

ALTER TABLE deadlines ADD COLUMN compute_has_local_agent INTEGER;

ALTER TABLE deadlines ADD COLUMN compute_court_region TEXT;

ALTER TABLE deadlines ADD COLUMN compute_party_region TEXT;

ALTER TABLE deadlines ADD COLUMN compute_in_transit_override INTEGER;
