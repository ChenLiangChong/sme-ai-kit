-- 021: employee_pleading_tokens — 每律師的 pleading-manager 個人 token 安全存放（Wave1 Task D）
--
-- 用途（整合契約 v4 auth + Task D）：sme 回寫末日/收文到 pleading 時，用「該案當責律師的個人 token」
--   呼叫（§127：法律後果寫入背後是真實當責律師、非幽靈服務）。本表存每位律師綁定的 token。
--
-- 安全（密鑰存放鐵則）：
--   - **full-access-only**：token = 完整律師身分密鑰；bind/unbind 工具雙牆（floor_policy
--     INTEGRATION_ADMIN_TOOLS 物理移除受限層 + service is_full_access 第二道）。
--   - **無讀回工具**：任何 MCP 工具都不回傳 token，只由回寫路徑內部讀（select）。
--   - **受限層讀不到**：business.db 對受限層 denyRead（檔案牆），此表隨之不可讀。
--   - **provisioning 不走 LINE 明文**：token 由 admin host 本機綁定（見 pleading-sync.md），
--     不貼進 LINE（否則落 LINE 訊息庫 + search_line_messages 撈得到＝洩密）。
--   - **離職清**：FK ON DELETE CASCADE（員工刪→token 自動清）；offboarding 設 active=0 時，
--     select 只取 active=1 員工的 token（停用員工 token 不被使用、即使 row 暫留）＋ unbind 工具。
--
-- 慣例：只走 migration（不寫 schema.sql）；純 DDL、單 statement／行、過 splitter guard。
-- PRIMARY KEY=employee_id（一律師一 token）；無額外 index（PK 即足）。

CREATE TABLE IF NOT EXISTS employee_pleading_tokens (
    employee_id INTEGER PRIMARY KEY REFERENCES employees(id) ON DELETE CASCADE,
    token TEXT NOT NULL,
    provisioned_at TEXT DEFAULT (datetime('now', 'localtime')),
    provisioned_by TEXT,
    last_verified_at TEXT,
    CHECK (token <> '')
);
