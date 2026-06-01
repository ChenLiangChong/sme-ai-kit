-- Phase: per-person 檔案/資料權限 access zones（決策 #157/#158/#160）
--
-- 兩張表（Codex 設計）：
-- - access_zones：被註冊成可控的「資料夾」(path 相對所屬 floor/layer)，= 權限邊界、不是檔清單
-- - access_zone_grants：誰（角色/員工/客戶/夥伴）能讀/寫某 zone
--
-- 安全要點：
-- - path 必須相對 floor（schema 層擋絕對路徑 '/...' 與 '..' traversal；PreToolUse hook 再做 realpath 二次防線）
-- - layer = 此 zone 屬哪個敏感度層(機密/通用/對外)；同一 DB 跨多 floor session 共用，hook 用 layer 篩「我這層的 zone」
-- - layer 不設值域 CHECK：通用模組要讓客戶端自訂層名（深訪客製）

CREATE TABLE IF NOT EXISTS access_zones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    path TEXT NOT NULL,
    layer TEXT DEFAULT 'general',
    business_unit TEXT,
    notes TEXT,
    active INTEGER DEFAULT 1,
    created_at DATETIME DEFAULT (datetime('now', 'localtime')),
    UNIQUE(path),
    CHECK (active IN (0, 1)),
    CHECK (path <> ''),
    CHECK (path NOT LIKE '/%'),
    CHECK (path NOT LIKE '%..%')
);

CREATE INDEX IF NOT EXISTS idx_access_zones_active ON access_zones(active);
CREATE INDEX IF NOT EXISTS idx_access_zones_layer ON access_zones(layer);
CREATE INDEX IF NOT EXISTS idx_access_zones_bu ON access_zones(business_unit);

-- grant：subject_ref = role 名(employee_role) / employee.id / customer.id / external_partner.id
-- can_write=1 必須 can_read=1（不能只寫不能讀）
CREATE TABLE IF NOT EXISTS access_zone_grants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    zone_id INTEGER NOT NULL REFERENCES access_zones(id) ON DELETE CASCADE,
    subject_type TEXT NOT NULL,
    subject_ref TEXT NOT NULL,
    can_read INTEGER DEFAULT 1,
    can_write INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT (datetime('now', 'localtime')),
    UNIQUE(zone_id, subject_type, subject_ref),
    CHECK (subject_type IN ('employee_role', 'employee', 'customer', 'external_partner')),
    CHECK (can_read IN (0, 1)),
    CHECK (can_write IN (0, 1)),
    CHECK (can_write = 0 OR can_read = 1)
);

CREATE INDEX IF NOT EXISTS idx_azg_zone ON access_zone_grants(zone_id);
CREATE INDEX IF NOT EXISTS idx_azg_subject ON access_zone_grants(subject_type, subject_ref);
