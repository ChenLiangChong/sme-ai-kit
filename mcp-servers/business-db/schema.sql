-- SME-AI-Kit Database Schema
-- SQLite for Taiwan SME operations
-- All timestamps are ISO 8601 in Asia/Taipei

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- ============================================================
-- Core Tables
-- ============================================================

CREATE TABLE IF NOT EXISTS company (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    name TEXT NOT NULL,
    industry TEXT,
    boss_name TEXT,
    boss_title TEXT DEFAULT '老闆',
    boss_line_id TEXT,
    timezone TEXT DEFAULT 'Asia/Taipei',
    approval_threshold REAL DEFAULT 5000,
    created_at DATETIME DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS business_entities (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    channel_id TEXT,
    approval_threshold REAL,
    notes TEXT,
    created_at DATETIME DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    role TEXT DEFAULT 'staff',
    department TEXT,
    line_user_id TEXT UNIQUE,
    permissions TEXT DEFAULT 'basic',
    phone TEXT,
    business_units TEXT,
    notes TEXT,
    active INTEGER DEFAULT 1,
    created_at DATETIME DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS business_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'explicit',
    source_quote TEXT,
    set_by TEXT,
    business_unit TEXT,
    superseded_by INTEGER REFERENCES business_rules(id) ON DELETE SET NULL,
    created_at DATETIME DEFAULT (datetime('now', 'localtime')),
    CHECK (source_type IN ('explicit', 'observed', 'inferred')),
    CHECK (source_type != 'explicit' OR source_quote IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    assignee TEXT,
    status TEXT DEFAULT 'pending',
    priority TEXT DEFAULT 'normal',
    category TEXT DEFAULT 'general',
    tags TEXT,
    business_unit TEXT,
    due_date TEXT,
    parent_task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    created_by TEXT,
    completed_at DATETIME,
    created_at DATETIME DEFAULT (datetime('now', 'localtime')),
    CHECK (status IN ('pending', 'in_progress', 'done', 'cancelled')),
    CHECK (priority IN ('urgent', 'normal', 'low'))
);

CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT DEFAULT 'customer',
    phone TEXT,
    email TEXT,
    line_user_id TEXT,
    tags TEXT,
    notes TEXT,
    pipeline_stage TEXT DEFAULT 'none',
    -- Legacy aggregates (向後相容，與 total_fulfilled / last_fulfilled_date 同步)
    total_purchases REAL DEFAULT 0,
    last_purchase_date TEXT,
    discount_rate REAL DEFAULT 0,
    payment_terms TEXT DEFAULT 'net30',
    -- v4: Split sales aggregates (Bug #2)
    total_ordered REAL DEFAULT 0,        -- 下單累計金額（含未出貨）
    total_fulfilled REAL DEFAULT 0,      -- 已出貨累計金額（≈ 已認列營收）
    total_paid REAL DEFAULT 0,           -- 實收累計金額
    last_order_date TEXT,
    last_fulfilled_date TEXT,
    last_payment_date TEXT,
    -- v4: Cross-entity primary ownership (Obs #6)
    primary_business_unit TEXT,
    created_at DATETIME DEFAULT (datetime('now', 'localtime')),
    CHECK (type IN ('customer', 'supplier', 'distributor'))
);

-- v4: External partners（外包夥伴，與 employees / customers 區分）
-- 設計原則：
-- - 不是員工（沒 employees.role/permissions 管控）
-- - 不是客戶（沒 customers.type='supplier' 語意）
-- - 獨立類別：外景拍攝/影片剪輯/社群發布/設計/顧問協作…
CREATE TABLE IF NOT EXISTS external_partners (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    role TEXT,                       -- 自由文字（如：影片剪輯 / 社群發布 / 外景拍攝）
    line_user_id TEXT,               -- LINE User ID（per-OA，多 OA 請補 notes）
    phone TEXT,
    email TEXT,
    business_units TEXT,             -- 逗號分隔服務的事業體（如 'brand_e,brand_a'）
    payment_terms TEXT,              -- '月結' / '案件計酬' / '預付'
    notes TEXT,
    active INTEGER DEFAULT 1,
    created_at DATETIME DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_partners_line ON external_partners(line_user_id) WHERE line_user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_partners_active ON external_partners(id) WHERE active = 1;

CREATE TABLE IF NOT EXISTS customer_entity_terms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    business_unit TEXT NOT NULL,
    discount_rate REAL DEFAULT 0,
    payment_terms TEXT DEFAULT 'net30',
    notes TEXT,
    created_at DATETIME DEFAULT (datetime('now', 'localtime')),
    UNIQUE(customer_id, business_unit)
);

CREATE TABLE IF NOT EXISTS inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT NOT NULL,
    name TEXT NOT NULL,
    category TEXT,
    current_stock INTEGER DEFAULT 0,
    reserved INTEGER DEFAULT 0,          -- v4: 預訂量（create_order 預留，fulfill_order 扣）
    min_stock INTEGER DEFAULT 0,
    unit TEXT DEFAULT '個',
    unit_cost REAL,
    sell_price REAL,
    business_unit TEXT,
    location TEXT,
    last_restock_date TEXT,
    notes TEXT,
    created_at DATETIME DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS line_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT DEFAULT 'default',
    line_message_id TEXT,
    user_id TEXT NOT NULL,
    user_name TEXT,
    source_type TEXT DEFAULT 'user',
    group_id TEXT,
    direction TEXT NOT NULL,
    content TEXT NOT NULL,
    msg_type TEXT DEFAULT 'text',
    status TEXT DEFAULT 'queued',
    session_id TEXT,
    reply_content TEXT,
    replied_at DATETIME,
    created_at DATETIME DEFAULT (datetime('now', 'localtime')),
    CHECK (direction IN ('inbound', 'outbound', 'broadcast')),
    CHECK (status IN ('queued', 'processed', 'replied'))
);

CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    requester TEXT,
    summary TEXT NOT NULL,
    detail TEXT,
    status TEXT DEFAULT 'waiting',
    approver TEXT,
    business_unit TEXT,
    decided_at DATETIME,
    expires_at DATETIME,
    created_at DATETIME DEFAULT (datetime('now', 'localtime')),
    CHECK (status IN ('waiting', 'approved', 'rejected', 'expired'))
);

CREATE TABLE IF NOT EXISTS session_handoffs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    summary TEXT NOT NULL,
    pending_items TEXT,
    created_at DATETIME DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS interaction_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT,
    action TEXT NOT NULL,
    target_type TEXT,
    target_id INTEGER,
    detail TEXT,
    business_unit TEXT,
    created_at DATETIME DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS rule_relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id_a INTEGER NOT NULL REFERENCES business_rules(id) ON DELETE CASCADE,
    rule_id_b INTEGER NOT NULL REFERENCES business_rules(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL DEFAULT 'related',
    created_by TEXT,
    created_at DATETIME DEFAULT (datetime('now', 'localtime')),
    CHECK (relation_type IN ('related', 'depends_on', 'conflicts_with')),
    CHECK (rule_id_a != rule_id_b)
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    amount REAL NOT NULL,
    category TEXT,
    description TEXT,
    related_customer_id INTEGER REFERENCES customers(id) ON DELETE SET NULL,
    related_order_id INTEGER REFERENCES orders(id) ON DELETE SET NULL,
    related_invoice TEXT,
    business_unit TEXT,
    payment_status TEXT DEFAULT 'paid',
    due_date TEXT,
    paid_amount REAL DEFAULT 0,
    recorded_by TEXT,
    transaction_date TEXT NOT NULL,
    created_at DATETIME DEFAULT (datetime('now', 'localtime')),
    CHECK (type IN ('income', 'expense')),
    CHECK (payment_status IN ('paid', 'pending', 'overdue'))
);

-- ============================================================
-- Orders（訂單管理）
-- ============================================================

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER REFERENCES customers(id) ON DELETE SET NULL,
    status TEXT DEFAULT 'pending',
    total_amount REAL DEFAULT 0,
    items TEXT,
    business_unit TEXT,
    notes TEXT,
    payment_terms TEXT,
    discount_applied REAL DEFAULT 0,
    qc_status TEXT DEFAULT 'pending' CHECK (qc_status IN ('pending', 'passed', 'failed', 'partial')),
    qc_notes TEXT,
    qc_checked_by TEXT,
    qc_checked_at DATETIME,
    driver TEXT,
    estimated_delivery TEXT,
    delivered_at DATETIME,
    created_by TEXT,
    created_at DATETIME DEFAULT (datetime('now', 'localtime')),
    updated_at DATETIME DEFAULT (datetime('now', 'localtime')),
    CHECK (status IN ('pending', 'confirmed', 'shipped', 'delivered', 'paid', 'cancelled', 'returned'))
);

-- ============================================================
-- Attachments（附件管理，存路徑不存檔案）
-- ============================================================

CREATE TABLE IF NOT EXISTS attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_type TEXT NOT NULL,
    target_id INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    file_type TEXT,
    file_name TEXT,
    description TEXT,
    uploaded_by TEXT,
    created_at DATETIME DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_attachments_target ON attachments(target_type, target_id);

-- ============================================================
-- Daily Snapshots（每日快照，用於趨勢分析）
-- ============================================================

CREATE TABLE IF NOT EXISTS daily_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date TEXT NOT NULL,
    business_unit TEXT DEFAULT '',
    pending_tasks INTEGER DEFAULT 0,
    completed_tasks_today INTEGER DEFAULT 0,
    overdue_tasks INTEGER DEFAULT 0,
    total_income REAL DEFAULT 0,
    total_expense REAL DEFAULT 0,
    pending_receivables REAL DEFAULT 0,
    low_stock_count INTEGER DEFAULT 0,
    total_customers INTEGER DEFAULT 0,
    line_messages_today INTEGER DEFAULT 0,
    active_orders INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS line_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT DEFAULT 'default',
    group_id TEXT NOT NULL,
    group_name TEXT,
    group_type TEXT DEFAULT 'other',
    purpose TEXT,                    -- v4: 一句話描述群組功能（例：品牌 C內勤訂單協調）
    notes TEXT,
    created_at DATETIME DEFAULT (datetime('now', 'localtime')),
    updated_at DATETIME DEFAULT (datetime('now', 'localtime')),
    UNIQUE(channel_id, group_id)
);

CREATE TABLE IF NOT EXISTS line_blocked_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT DEFAULT 'default',
    user_id TEXT NOT NULL,
    reason TEXT,
    created_at DATETIME DEFAULT (datetime('now', 'localtime')),
    UNIQUE(channel_id, user_id)
);

-- ============================================================
-- Indexes
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON tasks(assignee);
CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(due_date) WHERE status IN ('pending', 'in_progress');
CREATE INDEX IF NOT EXISTS idx_tasks_category ON tasks(category);
CREATE INDEX IF NOT EXISTS idx_customers_type ON customers(type);
CREATE INDEX IF NOT EXISTS idx_line_messages_status ON line_messages(status);
CREATE INDEX IF NOT EXISTS idx_line_messages_user ON line_messages(user_id);
CREATE INDEX IF NOT EXISTS idx_line_messages_dir ON line_messages(direction, status);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);
CREATE INDEX IF NOT EXISTS idx_rules_category ON business_rules(category);
CREATE INDEX IF NOT EXISTS idx_rules_active ON business_rules(id) WHERE superseded_by IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_rules_unique_active ON business_rules(category, title, COALESCE(business_unit, '')) WHERE superseded_by IS NULL;
CREATE INDEX IF NOT EXISTS idx_inventory_alert ON inventory(id) WHERE current_stock <= min_stock;
CREATE UNIQUE INDEX IF NOT EXISTS idx_inventory_sku_bu ON inventory(sku, COALESCE(business_unit, ''));
CREATE INDEX IF NOT EXISTS idx_employees_line ON employees(line_user_id) WHERE line_user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_customers_line ON customers(line_user_id) WHERE line_user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_interaction_log_time ON interaction_log(created_at);
CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(payment_status);
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(transaction_date);
CREATE INDEX IF NOT EXISTS idx_transactions_customer ON transactions(related_customer_id) WHERE related_customer_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_transactions_order ON transactions(related_order_id) WHERE related_order_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_snapshots_date_bu ON daily_snapshots(snapshot_date, COALESCE(business_unit, ''));
CREATE INDEX IF NOT EXISTS idx_snapshots_date ON daily_snapshots(snapshot_date);
CREATE INDEX IF NOT EXISTS idx_line_groups_type ON line_groups(group_type);
CREATE INDEX IF NOT EXISTS idx_line_messages_group ON line_messages(group_id) WHERE group_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_line_messages_channel ON line_messages(channel_id);
CREATE INDEX IF NOT EXISTS idx_line_groups_channel ON line_groups(channel_id);
CREATE INDEX IF NOT EXISTS idx_rules_bu ON business_rules(business_unit) WHERE business_unit IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tasks_bu ON tasks(business_unit) WHERE business_unit IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_inventory_bu ON inventory(business_unit) WHERE business_unit IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_transactions_bu ON transactions(business_unit) WHERE business_unit IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_orders_bu ON orders(business_unit) WHERE business_unit IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_approvals_bu ON approvals(business_unit) WHERE business_unit IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_transactions_customer_status ON transactions(related_customer_id, payment_status) WHERE related_customer_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tasks_assignee_status ON tasks(assignee, status) WHERE assignee IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_orders_status_bu ON orders(status, business_unit);
CREATE INDEX IF NOT EXISTS idx_rule_relations_a ON rule_relations(rule_id_a);
CREATE INDEX IF NOT EXISTS idx_rule_relations_b ON rule_relations(rule_id_b);
CREATE UNIQUE INDEX IF NOT EXISTS idx_rule_relations_pair ON rule_relations(rule_id_a, rule_id_b, relation_type);
-- v4: cross-entity customer indexing
CREATE INDEX IF NOT EXISTS idx_customers_primary_bu ON customers(primary_business_unit) WHERE primary_business_unit IS NOT NULL;
