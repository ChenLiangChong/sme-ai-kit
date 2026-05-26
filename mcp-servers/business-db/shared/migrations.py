"""
Migration runner — 把 schema 演進從散在 init_db 內的 ALTER 邏輯改為 numbered SQL files。

設計原則：
- 保守：不取代 init_db 既有邏輯，在 init_db 結尾 call 一次即可
- 001_initial.sql 是 baseline（= schema.sql 的副本）
- 既有 DB（已有所有 critical baseline tables）首次跑時，自動把 001 標為 applied
- 002+ 是未來新功能（leave module 等）

Transaction safety（codex review fix）：
- 不用 sqlite3.executescript（會 implicit commit、無法 rollback half-applied DDL）
- 切到 autocommit 模式、手動 BEGIN/COMMIT、失敗 ROLLBACK
- 每個 migration 整個套用 + INSERT schema_version 在同一 transaction 內，原子性保證

Schema：
    schema_version (
        version INTEGER PRIMARY KEY,
        applied_at DATETIME,
        notes TEXT
    )

檔名規範：嚴格 `^\\d+_.+\\.sql$`，例如
    migrations/001_initial.sql
    migrations/002_<short_name>.sql
"""
import re
import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"

# 嚴格匹配：開頭數字 + 底線 + 名稱 + .sql
FILENAME_RE = re.compile(r"^(\d+)_[A-Za-z0-9_\-]+\.sql$")

# Baseline detection：必須有所有 critical table 才認定 001 已 applied
# 比只看 business_rules 更穩，避免半壞 DB 被誤標為 baseline applied
_BASELINE_CRITICAL_TABLES = (
    "business_rules",
    "company",
    "employees",
    "customers",
    "orders",
    "transactions",
    "inventory",
    "approvals",
    "tasks",
)


def _ensure_version_table(db: sqlite3.Connection) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at DATETIME DEFAULT (datetime('now', 'localtime')),
            notes TEXT
        )
        """
    )


def _applied_versions(db: sqlite3.Connection) -> set[int]:
    return {row[0] for row in db.execute("SELECT version FROM schema_version").fetchall()}


def _existing_db_has_baseline_tables(db: sqlite3.Connection) -> bool:
    """既有 DB 判定：所有 critical table 都存在 → 假設 001_initial 早已 applied。

    比單看 business_rules 更穩 — 半壞 DB（只剩部分表）不會被誤標為 baseline applied。
    """
    existing = {
        row[0]
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    return all(t in existing for t in _BASELINE_CRITICAL_TABLES)


def _parse_version(filename: str) -> int | None:
    m = FILENAME_RE.match(filename)
    return int(m.group(1)) if m else None


def _list_migration_files() -> list[Path]:
    """列出 migrations/ 下符合 `^\\d+_<name>.sql$` 的檔，按 version int 排序。

    同 version 重複 raise（避免歧義）。
    """
    if not MIGRATIONS_DIR.exists():
        return []
    seen_versions: dict[int, Path] = {}
    for p in MIGRATIONS_DIR.iterdir():
        if not p.is_file():
            continue
        version = _parse_version(p.name)
        if version is None:
            continue
        if version in seen_versions:
            raise RuntimeError(
                f"Duplicate migration version {version}: "
                f"{seen_versions[version].name} and {p.name}"
            )
        seen_versions[version] = p
    return [seen_versions[v] for v in sorted(seen_versions)]


_LINE_COMMENT_RE = re.compile(r"--[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)

# Full-text guards：splitter 切之前在整段 SQL 上偵測（trigger body 含巢狀 ; 會被誤切）
_TRIGGER_RE = re.compile(
    r"\bCREATE\s+(?:TEMP(?:ORARY)?\s+)?TRIGGER\b", re.IGNORECASE
)

# Per-statement guards：split 後在每個 statement 開頭偵測（同行多 statement 也能抓）
# BEGIN 涵蓋所有變體：BEGIN; / BEGIN TRANSACTION; / BEGIN IMMEDIATE; / BEGIN DEFERRED; / BEGIN EXCLUSIVE;
_FORBIDDEN_STMT_PREFIXES = (
    (re.compile(r"^\s*BEGIN\b", re.IGNORECASE),
     "BEGIN（runner 已包 transaction，不允許巢狀）"),
    (re.compile(r"^\s*COMMIT\b", re.IGNORECASE),
     "COMMIT（runner 自己管 transaction）"),
    (re.compile(r"^\s*ROLLBACK\b", re.IGNORECASE),
     "ROLLBACK（runner 自己管 transaction）"),
    (re.compile(r"^\s*END\b", re.IGNORECASE),
     "END（trigger/compound statement 不支援）"),
    (re.compile(r"^\s*SAVEPOINT\b", re.IGNORECASE),
     "SAVEPOINT（巢狀 transaction 不支援）"),
    (re.compile(r"^\s*RELEASE\b", re.IGNORECASE),
     "RELEASE（巢狀 transaction 不支援）"),
)


def _split_sql_statements(sql: str) -> list[str]:
    """Naive SQL splitter for migration scripts.

    處理：line comment `-- ...`、block comment `/* ... */`、空 statement。
    Guards（codex review v2/v3 fixes）：受限 grammar，違反就 raise ValueError：
    - 整段 full-text：禁止 CREATE TRIGGER（內含巢狀 ; 會被誤切）
    - 每個 statement 開頭：禁止 BEGIN / COMMIT / ROLLBACK / END / SAVEPOINT / RELEASE
      （runner 自己管 transaction、不允許 migration SQL 動 transaction state）
      → 同行多 statement 如 `CREATE TABLE a(id); COMMIT;` 切完後第二個 statement 會被攔到

    若需要 TRIGGER 或 compound statement，未來再升級為 token-aware parser。
    """
    cleaned = _LINE_COMMENT_RE.sub("", sql)
    cleaned = _BLOCK_COMMENT_RE.sub("", cleaned)

    # Full-text guard：trigger body 含 ; 會被誤切，必須在 split 前攔
    if _TRIGGER_RE.search(cleaned):
        raise ValueError(
            "Migration SQL 含 CREATE TRIGGER（splitter 不支援巢狀 ;）。"
            "請拆成多個 migration 或升級 splitter。"
        )

    parts = [s.strip() for s in cleaned.split(";")]
    stmts = [s for s in parts if s]

    # Per-statement guard：開頭 token 攔，同行多 statement 也能抓
    for stmt in stmts:
        for pattern, label in _FORBIDDEN_STMT_PREFIXES:
            if pattern.match(stmt):
                raise ValueError(
                    f"Migration 含不支援的 statement：{label}"
                )

    return stmts


def run_migrations(db: sqlite3.Connection) -> list[int]:
    """執行 pending migrations，回傳這次 apply 的 version list。

    Transaction safety：
    - 切到 autocommit 模式管理 transaction（不用 executescript）
    - 每個 migration 的所有 statements + schema_version INSERT 在同一 BEGIN/COMMIT
    - 中途任何 statement 失敗 → ROLLBACK、整個 migration 沒被 apply、schema_version 沒寫入
    - 下次重跑會從這個 version 重新嘗試（不會撞到 half-applied schema）
    """
    _ensure_version_table(db)
    db.commit()

    applied = _applied_versions(db)
    files = _list_migration_files()
    if not files:
        return []

    # Baseline：既有 DB 沒有 schema_version row、但所有 critical baseline tables 已存在
    # → 把 001 標為 applied，避免重跑 001_initial 失敗
    if not applied and _existing_db_has_baseline_tables(db):
        baseline_version = _parse_version(files[0].name)
        if baseline_version is not None:
            db.execute(
                "INSERT INTO schema_version (version, notes) VALUES (?, ?)",
                (baseline_version, f"baseline (existing DB): {files[0].name}"),
            )
            db.commit()
            applied.add(baseline_version)

    # 切到 autocommit、手動管 transaction（避免 Python sqlite3 driver 隱式行為）
    saved_isolation = db.isolation_level
    db.isolation_level = None

    newly_applied: list[int] = []
    try:
        for mig_file in files:
            version = _parse_version(mig_file.name)
            if version is None or version in applied:
                continue
            sql = mig_file.read_text(encoding="utf-8")
            statements = _split_sql_statements(sql)
            try:
                db.execute("BEGIN")
                for stmt in statements:
                    db.execute(stmt)
                db.execute(
                    "INSERT INTO schema_version (version, notes) VALUES (?, ?)",
                    (version, mig_file.name),
                )
                db.execute("COMMIT")
                newly_applied.append(version)
            except Exception as e:
                try:
                    db.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise RuntimeError(
                    f"Migration {mig_file.name} failed: {e}"
                ) from e
    finally:
        db.isolation_level = saved_isolation

    return newly_applied


def current_version(db: sqlite3.Connection) -> int:
    """回傳當前 schema_version 的最大值；沒任何 row 回 0。"""
    _ensure_version_table(db)
    row = db.execute("SELECT MAX(version) FROM schema_version").fetchone()
    return (row[0] if row and row[0] is not None else 0)
