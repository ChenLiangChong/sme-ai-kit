-- legal-admin vertical：時限引擎安全網 + 行事曆同步欄（在既有 deadlines 表加欄）
--
-- 設計依據：docs/legal/SPEC.md「寫兩處 + 每日彙整」「時限計算紀律」、01-deadline-engine.md。
-- 兩組新欄、互相獨立：
--   (A) 安全網 — stated_period_days：判決書「上訴教示」所載天數（律師確認時抓回）。
--       compute_deadline 拿它與引擎採用的 statutory_days 交叉比對；不符 → needs_manual_review
--       + calc_trace 記「教示比對不符」（反捏造：引擎不靜默蓋過判決書教示）。NULL=未提供。
--       （另一安全網「判決日 vs 修法日法版檢核」純算、不需落欄，結果走 calc_trace + needs_manual_review。）
--   (B) 行事曆同步（calendar-agnostic）— SPEC「寫兩處」：時限確認後除寫本表，也寫進「事務所慣用
--       行事曆」（現場配置的 MCP，Google 或其他）。agent 寫完外部 event 後把回傳 event_id 存回本表，
--       供每日彙整去重 / 後續更新對位。provider 標來源（'google'/'internal'/...）、不綁死特定行事曆。
--
-- 新欄只走 migration、不寫進 schema.sql（fresh-install 雙寫=崩潰、test_migration_safety 明文擋）。
-- ALTER TABLE ADD COLUMN 為既有慣例（見 006_knowledge_confidential.sql）；每行一 statement、
-- 不含 TRIGGER / BEGIN / COMMIT（splitter 限制）。

-- (A) 安全網：判決書上訴教示所載天數（NULL=未提供；提供時與引擎 statutory_days 交叉比對）
ALTER TABLE deadlines ADD COLUMN stated_period_days INTEGER;

-- (A2) 安全網：文書作成日（判決/裁定日，法版檢核依此而非送達日；NULL=未提供、引擎以送達日近似）
ALTER TABLE deadlines ADD COLUMN document_date TEXT;

-- (B) 行事曆同步（calendar-agnostic）
ALTER TABLE deadlines ADD COLUMN calendar_event_id TEXT;
ALTER TABLE deadlines ADD COLUMN calendar_provider TEXT;
ALTER TABLE deadlines ADD COLUMN calendar_synced_at TEXT;
