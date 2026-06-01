-- 008: 回填舊版 record_transaction approval 的 resume_params.related_invoice
--      （round-2 gate 全綁定相容性修補）
--
-- 背景：record_transaction 的 HITL gate 從「只驗 type/amount/business_unit」改成綁定完整
--   resume_params（type/amount/category/description/transaction_date/related_customer_id/
--   related_order_id/related_invoice/business_unit/payment_status/due_date），防「同金額同類型、
--   改掛別的客戶/訂單/發票/類別」重用已核准 approval。
-- 相容性問題：舊版 _build_approval_request 不存 related_invoice（其餘 10 欄一直都存），
--   升級後既有「待核准 / 已核准未執行」的 record_transaction approval 在 replay 時會被新 gate
--   以「related_invoice：approval 缺此欄位」誤拒（合法單被卡）。
-- 修補：對尚未消費的 record_transaction approval，json_insert 補上 related_invoice=''（只新增、
--   不覆寫既有值；其餘 10 欄舊版本來就有、不需回填）。idempotent：json_insert 對已存在的鍵 no-op。

UPDATE approvals
SET detail = json_insert(detail, '$.resume_params.related_invoice', '')
WHERE consumed_at IS NULL
  AND status IN ('waiting', 'approved')
  AND json_valid(detail)
  AND json_extract(detail, '$.resume_action') = 'record_transaction'
  AND json_type(detail, '$.resume_params') = 'object'
  AND json_extract(detail, '$.resume_params.related_invoice') IS NULL;
