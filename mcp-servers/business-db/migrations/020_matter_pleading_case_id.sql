-- 020: matters 加 pleading_case_id — legal-admin ↔ pleading-manager 整合對應鍵（Wave1 Task A）
--
-- 解耦鐵則（整合契約 contract_sme_pleading_integration v2 / log_decision「6 解耦鐵則」）：
--   跨產品線的對應「外鍵」只住在【可選的整合消費端 = sme(legal-admin)】、絕不放成 pleading 的必填欄。
--   matters.pleading_case_id 為 nullable：
--     NULL  = 此案未綁定 pleading（sme 純單機跑、引擎/提醒照常、不回寫）；
--     有值  = 對應 pleading-manager 的 case_id（不透明字串、sme 不解讀其內部結構）。
--   單向 sme→pleading：sme 持此對應、回寫末日/收文時用它定位 pleading 案件（重用 mark_deadline_calendared
--   的 provider 模式、pleading 當一個 calendar provider）；pleading 端零存任何 sme FK、照樣單機跑。
--   pleading 案件被刪 → sme 回寫得 404 → 上層偵測後 link_matter_pleading(matter_id,'') 清回 NULL（graceful）。
--
-- partial index：只索引「已綁定」的列（多數案件未綁定＝NULL、不佔索引；同 idx_deadlines_pending 模式）。
-- 慣例：matters 只走 migration（011 建表、不寫 schema.sql）；純 DDL、單 statement／行、過 splitter guard
--   （無 TRIGGER / BEGIN / COMMIT）。fresh install：init_db 跑 011 建表後本 migration ALTER 加欄、不崩。

ALTER TABLE matters ADD COLUMN pleading_case_id TEXT;
CREATE INDEX IF NOT EXISTS idx_matters_pleading_case_id ON matters(pleading_case_id) WHERE pleading_case_id IS NOT NULL;
