"""
Shared DB connection helper — modules 跟 server.py 共用。

抽離原因（Phase 1 拆 module）：拆出的 module tool 都需要 get_db、避免重複實作。

DB path resolution：
- `DB_PATH` 是 module-level constant、import 時 evaluate（向後相容）
- `get_db()` 內動態讀 SME_DB_PATH env、支援 test fixture 改 env 後切換
  （Python module cache 不會 reload shared.db、若 get_db 用 stale DB_PATH 就無法 test 多個 DB）
"""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

# mcp-servers/business-db/shared/db.py → parent×3 = mcp-servers/business-db/.. = repo
_DEFAULT_DB_PATH = str(Path(__file__).parent.parent.parent.parent / "data" / "business.db")


def get_db_path() -> str:
    """每次 call 動態讀 SME_DB_PATH env（支援 test fixture 動態切換）。"""
    return os.environ.get("SME_DB_PATH", _DEFAULT_DB_PATH)


# 向後相容：import 時 evaluate 一次（既有 code 寫 `from shared.db import DB_PATH` 仍能用）
DB_PATH = get_db_path()


def get_db() -> sqlite3.Connection:
    db = sqlite3.connect(get_db_path())
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=5000")
    db.row_factory = sqlite3.Row
    return db


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@contextmanager
def transaction(mode: str = "deferred"):
    """Service-layer transaction helper for write flows.

    Pattern：
        with transaction() as db:
            repository.foo(db, ...)
            repository.bar(db, ...)
        # 正常結束自動 commit；中途任何 raise 自動 rollback；永遠 close

    repository 函數應預期 db 是 caller-managed、自己不 commit / rollback。
    read-only 場景仍可用 `db = get_db(); try: ...; finally: db.close()`，
    或 with transaction() — commit no-op、語意一致也 OK。

    Args:
        mode: 'deferred'（預設，SQLite 預設行為、第一次寫才升級到 write lock）
              'immediate'（HITL approval-gated flow 用：tx 開頭就搶 write lock、
              避免「兩個 client 同時讀到 unused approval、輸家做了 insert 才在
              mark_consumed 被 rowcount=0 擋掉並 rollback」的浪費寫入。codex
              P2.13 LOW A）

    Caveats（codex P2.1 review）：
    - **不要 nested with transaction()**：每次都 get_db() 開新 connection、不是巢狀
      transaction；內層 commit 後外層 rollback 撤不掉。並發寫入靠 SQLite busy_timeout
      （5s）擋鎖衝突。
    - 只攔 Exception、KeyboardInterrupt / GeneratorExit 直接走 finally 不 rollback
      （MCP server 場景罕見到、不額外處理）
    - 若 rollback 或 close 自己拋例外，可能遮蓋原始例外（罕見、SQLite 一般不會）
    """
    if mode not in ("deferred", "immediate"):
        raise ValueError(f"transaction mode 必須是 'deferred' 或 'immediate'，got {mode!r}")
    db = get_db()
    try:
        # SQLite Python driver 預設會在第一個寫入前 implicit BEGIN DEFERRED；要 IMMEDIATE
        # 必須先關 driver autocommit、自己下 BEGIN IMMEDIATE。
        # BEGIN IMMEDIATE 放進 try 才能在 busy_timeout 超時拋 OperationalError 時走到
        # finally close（codex P2.13 round-2 LOW B2）
        if mode == "immediate":
            db.isolation_level = None  # 進入 autocommit 模式、避免 driver 偷下 BEGIN
            db.execute("BEGIN IMMEDIATE")
        yield db
        if mode == "immediate":
            db.execute("COMMIT")
        else:
            db.commit()
    except Exception:
        if mode == "immediate":
            try:
                db.execute("ROLLBACK")
            except Exception:
                pass
        else:
            db.rollback()
        raise
    finally:
        db.close()
