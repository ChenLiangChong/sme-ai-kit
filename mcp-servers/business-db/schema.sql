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
    stock_alert_threshold INTEGER DEFAULT 10,
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
    superseded_by INTEGER REFERENCES business_rules(id),
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
    due_date TEXT,
    parent_task_id INTEGER REFERENCES tasks(id),
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
    total_purchases REAL DEFAULT 0,
    last_purchase_date TEXT,
    created_at DATETIME DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    category TEXT,
    current_stock INTEGER DEFAULT 0,
    min_stock INTEGER DEFAULT 0,
    unit TEXT DEFAULT '個',
    unit_cost REAL,
    sell_price REAL,
    location TEXT,
    last_restock_date TEXT,
    notes TEXT,
    created_at DATETIME DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS line_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    created_at DATETIME DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    amount REAL NOT NULL,
    category TEXT,
    description TEXT,
    related_customer_id INTEGER REFERENCES customers(id),
    related_order_id INTEGER REFERENCES orders(id),
    related_invoice TEXT,
    payment_status TEXT DEFAULT 'paid',
    due_date TEXT,
    paid_amount REAL DEFAULT 0,
    recorded_by TEXT,
    transaction_date TEXT NOT NULL,
    created_at DATETIME DEFAULT (datetime('now', 'localtime')),
    CHECK (type IN ('income', 'expense'))
);

-- ============================================================
-- Orders（訂單管理）
-- ============================================================

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER REFERENCES customers(id),
    status TEXT DEFAULT 'pending',
    total_amount REAL DEFAULT 0,
    items TEXT,
    notes TEXT,
    qc_status TEXT DEFAULT 'pending',
    qc_notes TEXT,
    qc_checked_by TEXT,
    qc_checked_at DATETIME,
    driver TEXT,
    estimated_delivery TEXT,
    delivered_at DATETIME,
    created_by TEXT,
    created_at DATETIME DEFAULT (datetime('now', 'localtime')),
    updated_at DATETIME DEFAULT (datetime('now', 'localtime'))
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
    snapshot_date TEXT NOT NULL UNIQUE,
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
CREATE INDEX IF NOT EXISTS idx_inventory_alert ON inventory(id) WHERE current_stock <= min_stock;
CREATE INDEX IF NOT EXISTS idx_employees_line ON employees(line_user_id) WHERE line_user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_interaction_log_time ON interaction_log(created_at);
CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(payment_status);
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(transaction_date);
CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_snapshots_date ON daily_snapshots(snapshot_date);
