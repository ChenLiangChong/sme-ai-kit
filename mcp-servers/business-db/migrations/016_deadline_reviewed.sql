-- legal-admin（信任/稽核）：deadlines 加「律師覆核留痕」兩欄 reviewed_by / reviewed_at
--
-- 為什麼：引擎對不確定因素（送達/在途/法版/教示/裁定期間/消滅時效起算）標 needs_manual_review=1、
--   要求律師人工複核 calc_trace。但「誰、何時複核過」之前無留痕——律師只能口頭說「看過了」，
--   無稽核軌跡、也無法把「已複核確認」與「尚未有人看」區分開（漏期=執業過失，覆核留痕是信任命脈）。
--
-- 解法：mark_deadline_reviewed 由具名律師（actor fail-closed、floored 取 verified 員工名）逐筆覆核，
--   寫 reviewed_by（覆核律師）+ reviewed_at（覆核時間），並把 needs_manual_review 解除為 0
--   （＝該筆計算已經人確認、可作為權威倒數；scan/顯示的「未複核·非權威」警語隨之消失）。
--   「不可一鍵過」＝逐筆、具名、留時間戳；覆核（確認計算）≠ 遞交（mark_deadline_filed，書狀送出）兩事件分明。
--
-- 兩欄皆可為 NULL（未覆核）。每行一 statement、不含 TRIGGER/BEGIN/COMMIT（splitter 限制）。
-- 新欄只走 migration、不寫進 schema.sql（fresh-install 雙寫=崩潰、test_migration_safety 明文擋）。

ALTER TABLE deadlines ADD COLUMN reviewed_by TEXT;

ALTER TABLE deadlines ADD COLUMN reviewed_at TEXT;
