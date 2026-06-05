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


class _Connection(sqlite3.Connection):
    """sqlite3.Connection 子類：原生 Connection 不支援屬性 / weakref，子類可以。
    用來把「本 tx 的 escalation flush / in-session 注入 pending」綁在 connection 物件上
    （per-tx 隔離、不再用 module-global、避免重疊 tx 跨污染；codex 全專案審 E-MED）。"""
    pass

# mcp-servers/business-db/shared/db.py → parent×3 = mcp-servers/business-db/.. = repo
_DEFAULT_DB_PATH = str(Path(__file__).parent.parent.parent.parent / "data" / "business.db")


def get_db_path() -> str:
    """每次 call 動態讀 SME_DB_PATH env（支援 test fixture 動態切換）。"""
    return os.environ.get("SME_DB_PATH", _DEFAULT_DB_PATH)


# 向後相容：import 時 evaluate 一次（既有 code 寫 `from shared.db import DB_PATH` 仍能用）
DB_PATH = get_db_path()


def get_db() -> sqlite3.Connection:
    db = sqlite3.connect(get_db_path(), factory=_Connection)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=5000")
    db.row_factory = sqlite3.Row
    return db


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ── escalation 投遞觸發（#9g）+ B in-session push（#25）：enqueue_escalation 寫入上報後，
#    在「該筆 tx 的 connection」上記 pending；transaction() commit 成功後 fire-and-forget 起
#    claude -p 通報投遞器 + 經 IPC 注入全權限 session。
#    綁 connection（codex 全專案審 E-MED）：原本 module-global，重疊 tx 下 A 的 pending 會被 B 的
#    rollback 清掉、或被別人的 commit 誤送。改把 pending 存成 connection 物件屬性（每個 transaction()
#    各自 get_db() 開獨立 _Connection）→ 嚴格 per-tx 隔離；rollback 只影響自己這筆連線。──


def request_escalation_flush(db) -> None:
    """enqueue_escalation 寫入上報後呼叫（傳本 tx 的 db）；該 connection commit 成功後觸發投遞。"""
    db._sme_flush_pending = True


def queue_session_injection(db, payload: dict) -> None:
    """enqueue_escalation 呼叫（傳本 tx 的 db）：排一筆 in-session 注入 payload（notification dict）。
    該 connection commit 成功後 transaction() drain 並注入。"""
    if getattr(db, "_sme_injections", None) is None:
        db._sme_injections = []
    db._sme_injections.append(payload)


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
    committed = False
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
        committed = True
    except Exception:
        db._sme_flush_pending = False  # rollback → 本 connection：上報沒 commit、不投遞
        db._sme_injections = None      # rollback → 本 connection：業務沒 commit、不注入
        if mode == "immediate":
            try:
                db.execute("ROLLBACK")
            except Exception:
                pass
        else:
            db.rollback()
        raise
    finally:
        # 取出本 connection 的 pending；只動本 connection（per-tx 隔離）
        _do_flush = committed and getattr(db, "_sme_flush_pending", False)
        _drained = getattr(db, "_sme_injections", None) if committed else None
        db.close()
    # commit 成功且本 tx 寫過 escalation（連線已關、不持鎖）→ fire-and-forget 起 claude -p 通報投遞器。
    # 直接觸發（#9g）；best-effort——失敗不影響業務（上報已在佇列、cron flush_escalations.py 兜底）。
    if _do_flush:
        try:
            from shared.escalation import spawn_notifier
            spawn_notifier()
        except Exception:
            pass
    # B in-session push（#25）：commit 成功且本 tx 排了注入 → drain 並經 IPC socket 注入正在跑的
    # 全權限層 session。late import 避免 cycle（與 spawn_notifier 同理）；全 best-effort、吞例外。
    if _drained:
        try:
            from shared.escalation import inject_to_sessions
            for _p in _drained:
                inject_to_sessions(_p)
        except Exception:
            pass
