"""
Migration runner 安全性測試（補 codex review 提的 BLOCKER）。

涵蓋：
- Fresh DB：001 baseline 邏輯正確
- Existing DB：所有 critical tables 都在時自動標 001 applied
- Half-broken DB：只有部分 critical tables 時 NOT 標 baseline
- Re-run idempotent：跑多次不重複套用、不壞 schema_version
- Failure rollback：migration 中途失敗，schema_version 不留紀錄、DDL 不半套
- 嚴格檔名 + 重複 version 偵測
- Statement splitter：處理 comment、空行
"""
import atexit
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from shared.migrations import (  # noqa: E402
    _existing_db_has_baseline_tables,
    _list_migration_files,
    _parse_version,
    _split_sql_statements,
    current_version,
    run_migrations,
)


# tempfile cleanup（atexit）
_temp_dbs: list[str] = []


def _mk_db() -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    _temp_dbs.append(tmp.name)
    return tmp.name


@atexit.register
def _cleanup():
    for p in _temp_dbs:
        try:
            os.unlink(p)
        except OSError:
            pass


passed = 0
failed = 0
failures: list[str] = []


def check(name: str, cond: bool, detail: str = ""):
    global passed, failed
    if cond:
        print(f"OK    {name}")
        passed += 1
    else:
        print(f"FAIL  {name}{('  → ' + detail) if detail else ''}")
        failed += 1
        failures.append(name)


# === 1. Fresh DB（從零）run_migrations 之前 init_db 已建好所有 critical table ===

print("\n=== Fresh DB ===")
db_path = _mk_db()
os.environ["SME_DB_PATH"] = db_path
if "server" in sys.modules:
    del sys.modules["server"]
import server  # noqa: E402

server.DB_PATH = db_path

# init_db() 不可崩。常見崩法（決策 #174）：新欄位同時寫進 schema.sql 的 CREATE TABLE
# 又留在某 migration 的 ALTER ADD COLUMN → fresh DB 先建含欄的表、migration 再 ALTER →
# duplicate column → run_migrations 無 per-statement try/except → RuntimeError → 起不來。
_fresh_ok, _fresh_err = True, ""
try:
    server.init_db()  # 跑既有 init_db 邏輯 + run_migrations
except Exception as e:
    _fresh_ok, _fresh_err = False, repr(e)
check("fresh DB: init_db() 不崩（schema.sql=凍結 baseline、新表/新欄只走 migration）",
      _fresh_ok, detail=_fresh_err)

if _fresh_ok:
    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT version, notes FROM schema_version").fetchall()
    check("fresh DB: schema_version has version 1 (baseline)",
          any(r[0] == 1 for r in rows))
    check("fresh DB: noted as baseline",
          any("baseline" in (r[1] or "") for r in rows))
    # 跑到最新 migration 版本＝所有 migration 都 apply 成功（auto-track migrations 目錄、不寫死）
    _latest = max((_parse_version(p.name) for p in _list_migration_files()), default=0)
    check(f"fresh DB: 跑到最新 migration 版本 {_latest}（每支 migration 都 apply 成功、無中途崩）",
          current_version(conn) == _latest,
          detail=f"got {current_version(conn)}, latest {_latest}")
    conn.close()


# === 2. Existing DB baseline detection ===

print("\n=== Existing DB baseline detection ===")
db_path2 = _mk_db()
conn = sqlite3.connect(db_path2)
# 模擬既有 DB：所有 critical tables 都在
for tname in ["business_rules", "company", "employees", "customers",
              "orders", "transactions", "inventory", "approvals", "tasks"]:
    conn.execute(f"CREATE TABLE {tname} (id INTEGER PRIMARY KEY)")
conn.commit()
check("baseline detect: all critical tables → True",
      _existing_db_has_baseline_tables(conn) is True)
conn.close()


# === 3. Half-broken DB（只有部分 critical tables）===

print("\n=== Half-broken DB ===")
db_path3 = _mk_db()
conn = sqlite3.connect(db_path3)
# 只建 business_rules + company，缺其他 → 不算 baseline applied
conn.execute("CREATE TABLE business_rules (id INTEGER PRIMARY KEY)")
conn.execute("CREATE TABLE company (id INTEGER PRIMARY KEY)")
conn.commit()
check("baseline detect: partial tables → False（不誤標）",
      _existing_db_has_baseline_tables(conn) is False)
conn.close()


# === 4. Re-run idempotent ===

print("\n=== Re-run idempotent ===")
db_path4 = _mk_db()
os.environ["SME_DB_PATH"] = db_path4
if "server" in sys.modules:
    del sys.modules["server"]
import server  # noqa: F811

server.DB_PATH = db_path4

def _table_count(path: str) -> int:
    c = sqlite3.connect(path)
    try:
        return c.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchone()[0]
    finally:
        c.close()

# 跑 3 次 init_db；table 數比「1 次後」vs「3 次後」是否相同（測冪等、不寫死絕對表數，
# 否則每加一個 migration 表就要改測試＝又會 stale，正是 #174 stale test 的根因）
server.init_db()
_count_after_1 = _table_count(db_path4)
server.init_db()
server.init_db()
_count_after_3 = _table_count(db_path4)
conn = sqlite3.connect(db_path4)
rows = conn.execute("SELECT version FROM schema_version").fetchall()
check("idempotent: 3 次 init_db 後 schema_version 沒重複 row",
      len(rows) == len(set(r[0] for r in rows)),
      detail=f"versions: {[r[0] for r in rows]}")
check("idempotent: table 數穩定（1 次 vs 3 次 init 相同、不隨重跑增減）",
      _count_after_1 == _count_after_3,
      detail=f"after1={_count_after_1} after3={_count_after_3}")
conn.close()


# === 5. Failure rollback ===

print("\n=== Failure rollback ===")
db_path5 = _mk_db()
conn = sqlite3.connect(db_path5)

# 模擬 existing baseline DB
for tname in ["business_rules", "company", "employees", "customers",
              "orders", "transactions", "inventory", "approvals", "tasks"]:
    conn.execute(f"CREATE TABLE {tname} (id INTEGER PRIMARY KEY)")
conn.commit()

# 建一個會 mid-failure 的 migration（暫時放到 migrations dir）
fake_mig = ROOT / "migrations" / "999_test_rollback.sql"
fake_mig.write_text(
    "CREATE TABLE rollback_test_ok (id INTEGER);\n"
    "CREATE TABLE rollback_test_ok (id INTEGER);\n"  # 重複 CREATE，第二個失敗
    "CREATE TABLE rollback_test_bad (id INTEGER);\n",
    encoding="utf-8",
)
try:
    raised = False
    try:
        run_migrations(conn)
    except RuntimeError:
        raised = True
    check("rollback: failed migration raises RuntimeError", raised)

    # 驗證：rollback_test_ok 跟 rollback_test_bad 都不應存在（整 migration rollback）
    existing = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    check("rollback: rollback_test_ok 不應落地",
          "rollback_test_ok" not in existing)
    check("rollback: rollback_test_bad 不應落地",
          "rollback_test_bad" not in existing)

    # 驗證：schema_version 不應有 999
    versions = {r[0] for r in conn.execute("SELECT version FROM schema_version").fetchall()}
    check("rollback: schema_version 沒有失敗的 999",
          999 not in versions)
finally:
    if fake_mig.exists():
        fake_mig.unlink()
    conn.close()


# === 6. 嚴格檔名規範 ===

print("\n=== Filename validation ===")
check("filename: 001_initial.sql parses to 1",
      _parse_version("001_initial.sql") == 1)
check("filename: 042_xxx.sql parses to 42",
      _parse_version("042_leave_request.sql") == 42)
check("filename: 1.sql（沒底線）→ None",
      _parse_version("1.sql") is None)
check("filename: abc.sql → None",
      _parse_version("abc.sql") is None)
check("filename: 001_initial.txt → None（非 .sql）",
      _parse_version("001_initial.txt") is None)


# === 7. Duplicate version detection ===

print("\n=== Duplicate version ===")
fake_dup1 = ROOT / "migrations" / "888_dup_a.sql"
fake_dup2 = ROOT / "migrations" / "888_dup_b.sql"
try:
    fake_dup1.write_text("SELECT 1;", encoding="utf-8")
    fake_dup2.write_text("SELECT 1;", encoding="utf-8")
    raised = False
    try:
        _list_migration_files()
    except RuntimeError as e:
        raised = "Duplicate" in str(e)
    check("dup version: raises RuntimeError on collision", raised)
finally:
    for p in (fake_dup1, fake_dup2):
        if p.exists():
            p.unlink()


# === 8. SQL statement splitter ===

print("\n=== SQL statement splitter ===")
sql1 = "CREATE TABLE a (id INTEGER); CREATE INDEX b ON a(id);"
stmts1 = _split_sql_statements(sql1)
check("split: 2 simple statements",
      len(stmts1) == 2 and "CREATE TABLE" in stmts1[0] and "CREATE INDEX" in stmts1[1])

sql2 = "-- comment\nCREATE TABLE a (id INTEGER);\n-- another\n"
stmts2 = _split_sql_statements(sql2)
check("split: line comment stripped",
      len(stmts2) == 1 and "comment" not in stmts2[0])

sql3 = "/* block */ CREATE TABLE a (id INTEGER); /* trailing */"
stmts3 = _split_sql_statements(sql3)
check("split: block comment stripped",
      len(stmts3) == 1 and "block" not in stmts3[0])

sql4 = "  \n\n  ;  ;  CREATE TABLE a (id INTEGER);  \n\n  "
stmts4 = _split_sql_statements(sql4)
check("split: empty statements filtered",
      len(stmts4) == 1)


# === 9. Splitter guards（codex review v3 fix）===

print("\n=== Splitter guards ===")


def _expect_raises(label: str, sql_input: str, expected_substring: str = ""):
    """跑 _split_sql_statements 應該 raise ValueError、可選驗 msg substring。"""
    try:
        _split_sql_statements(sql_input)
        check(f"guard: {label}", False, detail="did not raise")
    except ValueError as e:
        if expected_substring and expected_substring not in str(e):
            check(f"guard: {label}", False,
                  detail=f"raised but msg lacked '{expected_substring}': {e}")
        else:
            check(f"guard: {label}", True)


_expect_raises("CREATE TRIGGER raises", "CREATE TRIGGER t AFTER INSERT ON a BEGIN SELECT 1; END;", "TRIGGER")
_expect_raises("CREATE TEMP TRIGGER raises", "CREATE TEMP TRIGGER t AFTER INSERT ON a BEGIN SELECT 1; END;", "TRIGGER")
_expect_raises("CREATE TEMPORARY TRIGGER raises", "CREATE TEMPORARY TRIGGER t AFTER INSERT ON a BEGIN SELECT 1; END;", "TRIGGER")

_expect_raises("頂層 BEGIN; raises", "BEGIN;", "BEGIN")
_expect_raises("BEGIN TRANSACTION; raises", "BEGIN TRANSACTION;", "BEGIN")
_expect_raises("BEGIN IMMEDIATE; raises", "BEGIN IMMEDIATE;", "BEGIN")
_expect_raises("BEGIN DEFERRED; raises", "BEGIN DEFERRED;", "BEGIN")
_expect_raises("BEGIN EXCLUSIVE; raises", "BEGIN EXCLUSIVE;", "BEGIN")
_expect_raises("COMMIT; raises", "COMMIT;", "COMMIT")
_expect_raises("ROLLBACK; raises", "ROLLBACK;", "ROLLBACK")

# 同行多 statement — 關鍵案例（codex review 點名）
_expect_raises("同行多 statement: CREATE TABLE a(id); COMMIT; raises",
               "CREATE TABLE a(id INTEGER); COMMIT;", "COMMIT")
_expect_raises("同行多 statement: CREATE TABLE a(id); ROLLBACK; raises",
               "CREATE TABLE a(id INTEGER); ROLLBACK;", "ROLLBACK")
_expect_raises("同行多 statement: CREATE TABLE a(id); BEGIN; raises",
               "CREATE TABLE a(id INTEGER); BEGIN;", "BEGIN")

_expect_raises("SAVEPOINT raises", "SAVEPOINT sp1;", "SAVEPOINT")
_expect_raises("RELEASE raises", "RELEASE sp1;", "RELEASE")


# === 9b. Migration 003 approval consume columns（P2.13）===

print("\n=== Migration 003: approval consume columns ===")
db_path_m3 = _mk_db()
os.environ["SME_DB_PATH"] = db_path_m3
if "server" in sys.modules:
    del sys.modules["server"]
import server  # noqa: F811

server.DB_PATH = db_path_m3
server.init_db()

conn = sqlite3.connect(db_path_m3)
appr_cols = {r[1] for r in conn.execute("PRAGMA table_info(approvals)").fetchall()}
for col in ("consumed_at", "consumed_by_type", "consumed_by_id"):
    check(f"m003: approvals has {col} column", col in appr_cols,
          detail=f"cols: {appr_cols}")

idx = conn.execute(
    "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_approvals_unused'"
).fetchone()
check("m003: idx_approvals_unused 已建立", idx is not None)

versions = {r[0] for r in conn.execute("SELECT version FROM schema_version").fetchall()}
check("m003: schema_version 含 3", 3 in versions, detail=f"versions={versions}")
conn.close()


# === 9d. Migration 004 leave management tables（P3b）===

print("\n=== Migration 004: leave management tables ===")
db_path_m4 = _mk_db()
os.environ["SME_DB_PATH"] = db_path_m4
if "server" in sys.modules:
    del sys.modules["server"]
import server  # noqa: F811

server.DB_PATH = db_path_m4
server.init_db()

conn = sqlite3.connect(db_path_m4)
tables = {r[0] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table'"
).fetchall()}
for t in ("leave_types", "leave_balances", "leave_requests"):
    check(f"m004: table {t} 已建立", t in tables, detail=f"tables={tables}")

# 驗證 leave_balances 的 UNIQUE 約束
lb_schema = conn.execute(
    "SELECT sql FROM sqlite_master WHERE type='table' AND name='leave_balances'"
).fetchone()[0]
check("m004: leave_balances UNIQUE(employee_id, leave_type_id, year)",
      "UNIQUE" in lb_schema and "employee_id" in lb_schema and "leave_type_id" in lb_schema)

# 驗證 leave_requests CHECK constraints
lr_schema = conn.execute(
    "SELECT sql FROM sqlite_master WHERE type='table' AND name='leave_requests'"
).fetchone()[0]
check("m004: leave_requests CHECK status enum",
      "CHECK" in lr_schema and "approved" in lr_schema and "rejected" in lr_schema)
check("m004: leave_requests CHECK days > 0", "days > 0" in lr_schema)
check("m004: leave_requests CHECK start_date <= end_date",
      "start_date <= end_date" in lr_schema)

versions = {r[0] for r in conn.execute("SELECT version FROM schema_version").fetchall()}
check("m004: schema_version 含 4", 4 in versions, detail=f"versions={versions}")
conn.close()


# === 9e. Migration 011/012 legal-admin（matters/deadlines/office_calendar/transit_period）===

print("\n=== Migration 011/012: legal-admin tables ===")
db_path_legal = _mk_db()
os.environ["SME_DB_PATH"] = db_path_legal
if "server" in sys.modules:
    del sys.modules["server"]
import server  # noqa: F811

server.DB_PATH = db_path_legal
server.init_db()

conn = sqlite3.connect(db_path_legal)
conn.execute("PRAGMA foreign_keys=ON")
ltables = {r[0] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table'"
).fetchall()}
for t in ("matters", "deadlines", "office_calendar", "transit_period", "pending_intakes"):
    check(f"legal: table {t} 已建立", t in ltables, detail=f"tables={ltables}")

# #H2 pending_intakes：結構性反捏造——只存抽出的事實、不得有任何 computed deadline 欄
# （待確認階段引擎還沒算、表上若有權威日期欄就可能被誤當已確認洩出去）
pi_schema = conn.execute(
    "SELECT sql FROM sqlite_master WHERE type='table' AND name='pending_intakes'"
).fetchone()[0]
pi_cols = {r[1] for r in conn.execute("PRAGMA table_info(pending_intakes)").fetchall()}
_pi_forbidden = {"internal_deadline", "statutory_deadline", "start_date", "effective_date", "calc_trace"}
check("legal(#H2): pending_intakes 無任何 computed deadline 欄（結構性不可洩權威日期）",
      not (pi_cols & _pi_forbidden), detail=str(pi_cols & _pi_forbidden))
check("legal(#H2): pending_intakes CHECK status enum（awaiting/confirmed/discarded）",
      "awaiting" in pi_schema and "confirmed" in pi_schema and "discarded" in pi_schema)
check("legal(#H2): pending_intakes CHECK extracted_summary <> ''（不可空摘要）",
      "extracted_summary <> ''" in pi_schema)

# deadlines 的反捏造 CHECK + status enum
dl_schema = conn.execute(
    "SELECT sql FROM sqlite_master WHERE type='table' AND name='deadlines'"
).fetchone()[0]
check("legal: deadlines CHECK statutory_basis <> ''（反捏造）",
      "statutory_basis <> ''" in dl_schema)
check("legal: deadlines CHECK period_type enum",
      "peremptory" in dl_schema and "court_set" in dl_schema)
check("legal: deadlines CHECK status enum",
      "pending" in dl_schema and "filed" in dl_schema and "missed" in dl_schema)

# index 落地（含 partial WHERE status='pending'）
lindexes = {r[0] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='index'"
).fetchall()}
for idx in ("idx_deadlines_pending", "idx_deadlines_matter",
            "idx_matters_status", "idx_transit_period_lookup"):
    check(f"legal: index {idx} 已建立", idx in lindexes, detail=f"indexes={lindexes}")
idx_pending_sql = conn.execute(
    "SELECT sql FROM sqlite_master WHERE type='index' AND name='idx_deadlines_pending'"
).fetchone()
check("legal: idx_deadlines_pending 是 partial（WHERE status='pending'）",
      idx_pending_sql and "status" in (idx_pending_sql[0] or "") and "pending" in (idx_pending_sql[0] or ""))

# parties 表「不存在」是 build contract §0 釘死的契約點
check("legal: parties 表不存在（MVP 用 client_name 內嵌、不加 FK）",
      "parties" not in ltables)
matter_fks = conn.execute("PRAGMA foreign_key_list(matters)").fetchall()
check("legal: matters 無 FK（client_party_id 不加 constraint）",
      len(matter_fks) == 0, detail=f"fks={matter_fks}")

# deadlines → matters ON DELETE CASCADE
dl_fks = conn.execute("PRAGMA foreign_key_list(deadlines)").fetchall()
check("legal: deadlines 有 1 條 FK 指向 matters（CASCADE）",
      len(dl_fks) == 1 and dl_fks[0][2] == "matters" and dl_fks[0][6] == "CASCADE",
      detail=f"fks={dl_fks}")

# office_calendar：migration 建空表、**不種任何半套年度種子**（codex r4 HIGH：半套被當已載入＝陷阱）。
# 辦公日曆一律由 import_office_calendar.py 整年逐日匯入（見 012 註解 / privacy-deploy）。
oc_exists = conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name='office_calendar'"
).fetchone()
check("legal: office_calendar 表存在", oc_exists is not None)
oc_count = conn.execute("SELECT COUNT(*) FROM office_calendar").fetchone()[0]
check("legal: office_calendar migration 後為空（不種半套年度、避免被誤判已載入）", oc_count == 0)

# 反捏造 CHECK 實測：空 statutory_basis 應被擋
_basis_blocked = False
try:
    conn.execute("INSERT INTO matters (title, status) VALUES ('擋測', 'open')")
    mid_t = conn.execute("SELECT id FROM matters WHERE title='擋測'").fetchone()[0]
    conn.execute(
        "INSERT INTO deadlines (matter_id, type, description, period_type, trigger_event, "
        "service_type, service_base_date, statutory_days, statutory_basis, status) "
        "VALUES (?, 'custom', 'x', 'peremptory', '送達', 'normal', '2026-06-01', 20, '', 'pending')",
        (mid_t,))
except sqlite3.IntegrityError:
    _basis_blocked = True
conn.rollback()
check("legal: deadlines 空 statutory_basis 被 CHECK 擋下（反捏造生效）", _basis_blocked)

versions = {r[0] for r in conn.execute("SELECT version FROM schema_version").fetchall()}
check("legal: schema_version 含 11 與 12", 11 in versions and 12 in versions,
      detail=f"versions={versions}")
conn.close()


# === 9c. Pre-003 backward — 既有 approved approval migration 後仍可用一次（P2.13 LOW F）===

print("\n=== Migration 003: pre-003 backward behavior ===")
db_path_pre003 = _mk_db()
conn = sqlite3.connect(db_path_pre003)
# 模擬 baseline DB（所有 critical tables 已在用 stub id 欄就足以讓 baseline 偵測過）；
# approvals 表用 pre-003 完整 schema（沒 consumed_at / consumed_by_type / consumed_by_id）。
for tname in ["business_rules", "company", "employees", "customers",
              "orders", "transactions", "inventory", "tasks"]:
    conn.execute(f"CREATE TABLE {tname} (id INTEGER PRIMARY KEY)")
# session_handoffs：migration 002 會 ALTER 加 status 欄、表必須先存在
conn.execute("""CREATE TABLE session_handoffs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    summary TEXT NOT NULL,
    pending_items TEXT,
    created_at DATETIME DEFAULT (datetime('now', 'localtime'))
)""")
conn.execute("""CREATE TABLE approvals (
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
    created_at DATETIME DEFAULT (datetime('now', 'localtime'))
)""")
conn.execute("""INSERT INTO approvals (type, summary, detail, status, approver)
                VALUES ('expense', 'pre-003 已核准', '{}', 'approved', '老闆')""")
conn.commit()

# 直接跑 migration runner（跳過 init_db 的其他複雜 migration 邏輯、純驗 003 增欄）
run_migrations(conn)

appr_cols_post = {r[1] for r in conn.execute("PRAGMA table_info(approvals)").fetchall()}
check("m003 pre-003: consumed_at column 已加入",
      "consumed_at" in appr_cols_post)
check("m003 pre-003: consumed_by_type column 已加入",
      "consumed_by_type" in appr_cols_post)
check("m003 pre-003: consumed_by_id column 已加入",
      "consumed_by_id" in appr_cols_post)
legacy_row = conn.execute(
    "SELECT status, consumed_at FROM approvals WHERE summary = 'pre-003 已核准'"
).fetchone()
check("m003 pre-003: legacy approval status 保留 = approved",
      legacy_row and legacy_row[0] == "approved")
check("m003 pre-003: legacy approval consumed_at = NULL（可第一次使用）",
      legacy_row and legacy_row[1] is None)
conn.close()


# === 10. Legacy rebuild schema drift（codex Phase 1 review fix）===

print("\n=== Legacy rebuild schema drift ===")

# Simulate pre-v4 schemas (v1 base + UNIQUE/no-CHECK，沒 v4 加的 reserved/sales-aggregate)
# init_db 開頭的 ADD COLUMN 會補上後加欄位 → 然後 UNIQUE/CHECK rebuild path 觸發
db_path_legacy = _mk_db()
conn = sqlite3.connect(db_path_legacy)
# pre-v4 inventory：v1 base + UNIQUE(sku)、沒 business_unit/location/last_restock_date/notes/reserved
conn.execute("""CREATE TABLE inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    category TEXT,
    current_stock INTEGER DEFAULT 0,
    min_stock INTEGER DEFAULT 0,
    unit TEXT DEFAULT '個',
    unit_cost REAL,
    sell_price REAL,
    created_at DATETIME DEFAULT (datetime('now', 'localtime'))
)""")
conn.execute("INSERT INTO inventory (sku, name, current_stock) VALUES ('LEGACY-001', '舊資料', 50)")
# pre-v4 customers：v1 base、沒 CHECK constraint、沒 v4 sales aggregate split
conn.execute("""CREATE TABLE customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT DEFAULT 'customer',
    phone TEXT,
    email TEXT,
    tags TEXT,
    notes TEXT,
    created_at DATETIME DEFAULT (datetime('now', 'localtime'))
)""")
conn.execute("INSERT INTO customers (name, type) VALUES ('舊客戶', 'customer')")
conn.commit()
conn.close()

os.environ["SME_DB_PATH"] = db_path_legacy
if "server" in sys.modules:
    del sys.modules["server"]
import server  # noqa: F811

server.DB_PATH = db_path_legacy
server.init_db()  # 跑 ADD COLUMN + UNIQUE/CHECK rebuild

# 驗證 inventory 表的所有欄位（含 v4 reserved）
conn = sqlite3.connect(db_path_legacy)
inv_cols = {r[1] for r in conn.execute("PRAGMA table_info(inventory)").fetchall()}
check("legacy rebuild: inventory has reserved column（v4）",
      "reserved" in inv_cols,
      detail=f"cols: {inv_cols}")
check("legacy rebuild: inventory keeps legacy data",
      conn.execute("SELECT COUNT(*) FROM inventory WHERE sku='LEGACY-001'").fetchone()[0] == 1)
inv_reserved = conn.execute("SELECT reserved FROM inventory WHERE sku='LEGACY-001'").fetchone()
check("legacy rebuild: inventory.reserved default 0",
      inv_reserved is not None and inv_reserved[0] == 0)

# 驗證 customers 表的所有欄位（含 v4 sales aggregate split）
cust_cols = {r[1] for r in conn.execute("PRAGMA table_info(customers)").fetchall()}
expected_v4 = {"primary_business_unit", "total_ordered", "total_fulfilled", "total_paid",
               "last_order_date", "last_fulfilled_date", "last_payment_date"}
missing = expected_v4 - cust_cols
check(f"legacy rebuild: customers has all v4 columns",
      not missing,
      detail=f"missing: {missing}")
check("legacy rebuild: customers keeps legacy data",
      conn.execute("SELECT COUNT(*) FROM customers WHERE name='舊客戶'").fetchone()[0] == 1)

# CHECK constraint 必須是 customers / supplier / distributor
cust_schema = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='customers'").fetchone()
check("legacy rebuild: customers gets CHECK constraint",
      cust_schema and "CHECK" in cust_schema[0])
conn.close()


# === Summary ===

print("\n" + "=" * 60)
total = passed + failed
print(f"Results: {passed} passed, {failed} failed out of {total}")
if failed:
    print(f"\nFailures:")
    for name in failures:
        print(f"  - {name}")
    sys.exit(1)
else:
    print(f"\nALL TESTS PASSED")
    sys.exit(0)
