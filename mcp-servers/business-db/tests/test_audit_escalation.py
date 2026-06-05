"""escalation 投遞租約稽核硬化測試（codex 全專案安全稽核 E 群、offline、standalone、不連網）。

跑法：
    cd mcp-servers/business-db
    SME_DB_PATH=/tmp/_t_audit_esc.db /abs/.venv/bin/python3 tests/test_audit_escalation.py

涵蓋（mark_sent_tool 租約 guard，codex E-HIGH / E-MED）：
- [E-HIGH] 裸 pending（未經 list_pending_for_notifier / cron claim、claimed_at IS NULL）
  直接呼 mark_escalation_sent 被擋下（rowcount=0、不標 sent、不落 log）→ 未送出的高風險上報
  不會被品質層 LLM 誤呼叫永久清成 sent、cron 仍會補送。
- 持有有效租約（claimed_at 在 _CLAIM_TTL_MIN 內）的 row 可標 sent + 落 interaction_log。
- [E-MED] 租約逾 TTL（被 cron / 另一支 notifier 視為可 reclaim）後，舊持有者不可標 sent
  （rowcount=0），避免被 reclaim 後仍雙投 / 繞 backoff。
- list_pending_for_notifier claim-on-read 取得租約後可正常標 sent（端到端正路）。
"""
import atexit
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
DB_PATH = _tmp.name
_tmp.close()
os.environ["SME_DB_PATH"] = DB_PATH
os.environ.pop("SME_FLOOR", None)  # 全權限（is_full_access）跑 enqueue / mark


@atexit.register
def _cleanup():
    try:
        os.unlink(DB_PATH)
    except OSError:
        pass


import server  # noqa: E402

server.DB_PATH = DB_PATH
server.init_db()

from shared.db import get_db, transaction  # noqa: E402
from shared.escalation import (  # noqa: E402
    enqueue_escalation,
    mark_sent_tool,
    list_pending_for_notifier,
    _CLAIM_TTL_MIN,
)

passed = 0
failed = 0
failures: list[str] = []


def _assert(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"OK    {name}")
    else:
        failed += 1
        failures.append(name)
        print(f"FAIL  {name}" + (f"  // {detail}" if detail else ""))


def _q1(sql, params=()):
    db = get_db()
    try:
        return db.execute(sql, params).fetchone()
    finally:
        db.close()


def _enqueue(summary, *, claimed_at_sql=None):
    """enqueue 一筆 escalation（保證有收件人）。claimed_at_sql 非 None 時直接設 claimed_at
    （注入租約狀態：'now' / '-15 minutes' 等 SQLite datetime 修飾）。回 escalation id。"""
    with transaction() as db:
        eid = enqueue_escalation(
            db, event_type="transaction_deleted", summary=summary,
            detail={"txn_id": 1}, actor_user_id="", business_unit="",
        )
        # enqueue 解析不到收件人（測試 DB 無老闆）→ 補一個 target，否則 _CLAIMABLE / mark 都跳過
        db.execute(
            "UPDATE pending_escalations SET target_line_user_id='Uaudit123' WHERE id=?", (eid,)
        )
        if claimed_at_sql is not None:
            db.execute(
                f"UPDATE pending_escalations SET claimed_at=datetime('now','localtime'{claimed_at_sql}) "
                "WHERE id=?", (eid,)
            )
    return eid


def _status(eid):
    return _q1("SELECT status FROM pending_escalations WHERE id=?", (eid,))["status"]


def _has_sent_log(eid):
    return _q1(
        "SELECT 1 FROM interaction_log WHERE action='escalation_sent' AND target_id=?", (eid,)
    ) is not None


# === [E-HIGH] 裸 pending（未 claim）不可直接標 sent ===
_eid_bare = _enqueue("audit·裸 pending 不可標 sent")
_pre = _q1("SELECT claimed_at FROM pending_escalations WHERE id=?", (_eid_bare,))
_assert("[E-HIGH] enqueue 後 claimed_at 為 NULL（裸 pending、未經 claim）",
        _pre["claimed_at"] is None)
_res_bare = mark_sent_tool(_eid_bare, sent_text="不該被接受")
_assert("[E-HIGH] 裸 pending 呼 mark_sent → 被拒（回未持有有效租約）",
        "未持有有效租約" in _res_bare)
_assert("[E-HIGH] 裸 pending 被拒後仍 pending（未被清成 sent、cron 可補送）",
        _status(_eid_bare) == "pending")
_assert("[E-HIGH] 裸 pending 被拒後不落 escalation_sent log（無假稽核紀錄）",
        not _has_sent_log(_eid_bare))


# === 持有有效租約（TTL 內）可標 sent ===
_eid_held = _enqueue("audit·有效租約可標 sent", claimed_at_sql="")  # claimed_at = now
_res_held = mark_sent_tool(_eid_held, sent_text="【系統通報】帳目被刪除（持租送出）")
_assert("持有效租約 → mark_sent 成功（回已標記 sent）", "已標記 sent" in _res_held)
_assert("持有效租約 → status=sent", _status(_eid_held) == "sent")
_assert("持有效租約 → 落 escalation_sent log（實際送出內容）",
        _has_sent_log(_eid_held))
_log_held = _q1(
    "SELECT detail FROM interaction_log WHERE action='escalation_sent' AND target_id=?",
    (_eid_held,))
_assert("持有效租約 → log 含 notifier 自報送出文字",
        _log_held is not None and "持租送出" in _log_held["detail"]
        and "[notifier→" in _log_held["detail"])


# === [E-MED] 租約逾 TTL（被 reclaim）後舊持有者不可標 sent ===
# claimed_at 設在 TTL+5 分前 → 視為可被 cron / 另一支 notifier reclaim，舊持有者標 sent 應被擋。
_eid_stale = _enqueue("audit·逾 TTL 租約不可標 sent",
                      claimed_at_sql=f",'-{_CLAIM_TTL_MIN + 5} minutes'")
_res_stale = mark_sent_tool(_eid_stale, sent_text="逾期不該被接受")
_assert("[E-MED] 租約逾 TTL → mark_sent 被拒（舊持有者不可標、防 reclaim 後雙投）",
        "未持有有效租約" in _res_stale)
_assert("[E-MED] 逾 TTL 被拒後仍 pending（留給接手者）", _status(_eid_stale) == "pending")
_assert("[E-MED] 逾 TTL 被拒後不落 sent log", not _has_sent_log(_eid_stale))

# 邊界：剛好在 TTL 邊緣內側（TTL-1 分）仍視為有效租約 → 可標 sent
_eid_edge = _enqueue("audit·TTL 內側邊界可標 sent",
                     claimed_at_sql=f",'-{_CLAIM_TTL_MIN - 1} minutes'")
_res_edge = mark_sent_tool(_eid_edge, sent_text="邊界內送出")
_assert("租約 TTL 內側邊界（TTL-1 分）→ 仍可標 sent", "已標記 sent" in _res_edge
        and _status(_eid_edge) == "sent")


# === 端到端正路：list_pending_for_notifier claim-on-read → mark_sent ===
_eid_e2e = _enqueue("audit·notifier claim-on-read 端到端")
# 標記前先清 claimed_at（_enqueue 沒設、本來就 NULL；保險）
with transaction() as db:
    db.execute("UPDATE pending_escalations SET claimed_at=NULL WHERE id=?", (_eid_e2e,))
_listed = json.loads(list_pending_for_notifier(limit=50))
_leased = any(it["id"] == _eid_e2e for it in _listed["pending"])
_row_e2e = _q1("SELECT claimed_at FROM pending_escalations WHERE id=?", (_eid_e2e,))
_assert("端到端：list_pending_for_notifier claim-on-read 取得租約（claimed_at 寫入）",
        _leased and _row_e2e["claimed_at"] is not None)
_res_e2e = mark_sent_tool(_eid_e2e, sent_text="【系統通報】notifier 取租後送出")
_assert("端到端：claim-on-read 後可正常標 sent", "已標記 sent" in _res_e2e
        and _status(_eid_e2e) == "sent")
_assert("端到端：標 sent 後落 log", _has_sent_log(_eid_e2e))


# === 收尾 ===
print(f"\n{'='*50}")
print(f"PASSED {passed}  FAILED {failed}")
if failures:
    print("FAILURES:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("ALL GREEN")
