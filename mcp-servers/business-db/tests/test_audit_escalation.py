"""escalation 投遞租約稽核硬化測試（codex 全專案安全稽核 E 群 + 修補複審 E-HIGH、offline、standalone、不連網）。

跑法：
    cd mcp-servers/business-db
    SME_DB_PATH=/tmp/_t_audit_esc.db /abs/.venv/bin/python3 tests/test_audit_escalation.py

涵蓋（mark_sent_tool 租約 + token guard，codex E-HIGH / E-MED + 修補複審 E-HIGH）：
- [E-HIGH] 裸 pending（未經 list_pending_for_notifier / cron claim、claimed_at IS NULL）
  直接呼 mark_escalation_sent 被擋下（rowcount=0、不標 sent、不落 log）→ 未送出的高風險上報
  不會被品質層 LLM 誤呼叫永久清成 sent、cron 仍會補送。
- legacy「無 token 租約」（raw SQL 設 claimed_at 未寫 token、向後相容 cron 直 claim）：不帶 token 可標 sent。
- [E-MED] 租約逾 TTL（被 cron / 另一支 notifier 視為可 reclaim）後，舊持有者不可標 sent（rowcount=0）。
- [修補複審 E-HIGH] list_pending_for_notifier 回傳 claim_token；持有 token 才可標 sent（端到端正路）。
- [修補複審 E-HIGH] token 不符 / 漏帶 token（標到別人正持有中的有 token 租約）→ 被拒（防誤標他人租約）。
- [修補複審 E-HIGH] stale-lease reclaim：租約逾 TTL 被另一路 reclaim 換新 token 後，舊 token 不可 mark_sent
  （rowcount=0、杜絕 stale-lease 雙送）。
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


def _token_of(eid):
    r = _q1("SELECT claim_token FROM pending_escalations WHERE id=?", (eid,))
    return r["claim_token"] if r else None


# === [E-HIGH] 裸 pending（未 claim）不可直接標 sent（連 token 都無從談起）===
_eid_bare = _enqueue("audit·裸 pending 不可標 sent")
_pre = _q1("SELECT claimed_at, claim_token FROM pending_escalations WHERE id=?", (_eid_bare,))
_assert("[E-HIGH] enqueue 後 claimed_at 為 NULL（裸 pending、未經 claim）",
        _pre["claimed_at"] is None)
_assert("[E-HIGH] enqueue 後 claim_token 為 NULL（尚未 claim、無租約憑證）",
        _pre["claim_token"] is None)
_res_bare = mark_sent_tool(_eid_bare, sent_text="不該被接受")
_assert("[E-HIGH] 裸 pending 呼 mark_sent → 被拒（回未持有此上報的有效租約）",
        "未持有此上報的有效租約" in _res_bare)
_assert("[E-HIGH] 裸 pending 帶任意 token 也被拒（沒 claim 過、token 必對不上）",
        "未持有此上報的有效租約" in mark_sent_tool(_eid_bare, claim_token="deadbeef", sent_text="x"))
_assert("[E-HIGH] 裸 pending 被拒後仍 pending（未被清成 sent、cron 可補送）",
        _status(_eid_bare) == "pending")
_assert("[E-HIGH] 裸 pending 被拒後不落 escalation_sent log（無假稽核紀錄）",
        not _has_sent_log(_eid_bare))


# === legacy「無 token 租約」（raw SQL 設 claimed_at 未寫 token）：不帶 token 可標 sent（向後相容 cron 直 claim）===
_eid_held = _enqueue("audit·legacy 無 token 租約可標 sent", claimed_at_sql="")  # claimed_at=now、claim_token NULL
_assert("legacy 租約：claimed_at 設了但 claim_token 仍 NULL（模擬 cron raw 設租約）",
        _token_of(_eid_held) is None)
_res_held = mark_sent_tool(_eid_held, sent_text="【系統通報】帳目被刪除（legacy 無 token 送出）")
_assert("legacy 無 token 租約 → 不帶 token mark_sent 成功（claim_token IS NULL 配對）",
        "已標記 sent" in _res_held)
_assert("legacy 無 token 租約 → status=sent", _status(_eid_held) == "sent")
_log_held = _q1(
    "SELECT detail FROM interaction_log WHERE action='escalation_sent' AND target_id=?",
    (_eid_held,))
_assert("legacy 無 token 租約 → log 含 notifier 自報送出文字",
        _log_held is not None and "legacy 無 token 送出" in _log_held["detail"]
        and "[notifier→" in _log_held["detail"])

# legacy 無 token 租約：帶「非空 token」反而對不上（claim_token IS NULL ≠ 'xxx'）→ 被拒（不可亂帶 token 標 legacy 租約）
_eid_legacy2 = _enqueue("audit·legacy 租約帶錯 token 被拒", claimed_at_sql="")
_assert("legacy 無 token 租約 → 帶非空 token 被拒（嚴格分支配不上 NULL）",
        "未持有此上報的有效租約" in mark_sent_tool(_eid_legacy2, claim_token="someerrtoken", sent_text="x")
        and _status(_eid_legacy2) == "pending")


# === [E-MED] 租約逾 TTL（被 reclaim）後舊持有者不可標 sent ===
# claimed_at 設在 TTL+5 分前 → 視為可被 cron / 另一支 notifier reclaim，舊持有者標 sent 應被擋。
_eid_stale = _enqueue("audit·逾 TTL 租約不可標 sent",
                      claimed_at_sql=f",'-{_CLAIM_TTL_MIN + 5} minutes'")
_res_stale = mark_sent_tool(_eid_stale, sent_text="逾期不該被接受")
_assert("[E-MED] 租約逾 TTL → mark_sent 被拒（舊持有者不可標、防 reclaim 後雙投）",
        "未持有此上報的有效租約" in _res_stale)
_assert("[E-MED] 逾 TTL 被拒後仍 pending（留給接手者）", _status(_eid_stale) == "pending")
_assert("[E-MED] 逾 TTL 被拒後不落 sent log", not _has_sent_log(_eid_stale))

# 邊界：剛好在 TTL 邊緣內側（TTL-1 分）仍視為有效租約 → 可標 sent（legacy 無 token 路徑）
_eid_edge = _enqueue("audit·TTL 內側邊界可標 sent",
                     claimed_at_sql=f",'-{_CLAIM_TTL_MIN - 1} minutes'")
_res_edge = mark_sent_tool(_eid_edge, sent_text="邊界內送出")
_assert("租約 TTL 內側邊界（TTL-1 分）→ 仍可標 sent", "已標記 sent" in _res_edge
        and _status(_eid_edge) == "sent")


# === [修補複審 E-HIGH] 端到端正路：list_pending_for_notifier claim-on-read 回 token → 帶 token mark_sent ===
_eid_e2e = _enqueue("audit·notifier claim-on-read 端到端")
# 標記前先清 claimed_at / token（_enqueue 沒設、本來就 NULL；保險）
with transaction() as db:
    db.execute("UPDATE pending_escalations SET claimed_at=NULL, claim_token=NULL WHERE id=?", (_eid_e2e,))
_listed = json.loads(list_pending_for_notifier(limit=50))
_item_e2e = next((it for it in _listed["pending"] if it["id"] == _eid_e2e), None)
_row_e2e = _q1("SELECT claimed_at, claim_token FROM pending_escalations WHERE id=?", (_eid_e2e,))
_assert("端到端：list_pending_for_notifier claim-on-read 取得租約（claimed_at 寫入）",
        _item_e2e is not None and _row_e2e["claimed_at"] is not None)
_assert("端到端：list 回傳 claim_token 且與 row 寫入的 token 一致（租約憑證交給 notifier）",
        _item_e2e is not None and _item_e2e.get("claim_token")
        and _item_e2e["claim_token"] == _row_e2e["claim_token"])
# 漏帶 token（有 token 租約、卻不帶 token）→ 被拒（防誤標他人正持有中的租約）
_assert("端到端：有 token 租約但 mark 漏帶 token → 被拒（不帶 token 不可標有 token 租約）",
        "未持有此上報的有效租約" in mark_sent_tool(_eid_e2e, sent_text="漏帶 token 不該過")
        and _status(_eid_e2e) == "pending")
# token 不符 → 被拒
_assert("端到端：token 不符 → 被拒（標到別人租約 / 亂猜 token 擋下）",
        "未持有此上報的有效租約" in mark_sent_tool(_eid_e2e, claim_token="wrong_token_xyz", sent_text="錯 token")
        and _status(_eid_e2e) == "pending")
# 帶正確 token → 標 sent + 落 log
_res_e2e = mark_sent_tool(_eid_e2e, claim_token=_item_e2e["claim_token"],
                          sent_text="【系統通報】notifier 取租後送出")
_assert("端到端：帶正確 token → 標 sent", "已標記 sent" in _res_e2e
        and _status(_eid_e2e) == "sent")
_assert("端到端：標 sent 後落 log", _has_sent_log(_eid_e2e))


# === [修補複審 E-HIGH] stale-lease reclaim：逾 TTL 被另一路 reclaim 換新 token 後，舊 token 不可 mark_sent ===
# 模擬：notifierA 取得租約（token_a）→ 久未送（租約逾 TTL）→ notifierB / cron reclaim（list 換新 token_b）。
_eid_recl = _enqueue("audit·stale-lease reclaim 舊 token 失效")
# notifierA 第一次 claim（拿到 token_a）
_listed_a = json.loads(list_pending_for_notifier(limit=50))
_item_a = next((it for it in _listed_a["pending"] if it["id"] == _eid_recl), None)
_token_a = _item_a["claim_token"] if _item_a else None
_assert("stale-reclaim：notifierA 首次 claim 取得 token_a", bool(_token_a))
# 把該租約「催老」成逾 TTL（模擬 notifierA 久未送）
with transaction() as db:
    db.execute(
        f"UPDATE pending_escalations SET claimed_at=datetime('now','localtime','-{_CLAIM_TTL_MIN + 5} minutes') "
        "WHERE id=?", (_eid_recl,))
# notifierB reclaim（list_pending_for_notifier 再 claim、寫新 token_b、claimed_at 刷新）
_listed_b = json.loads(list_pending_for_notifier(limit=50))
_item_b = next((it for it in _listed_b["pending"] if it["id"] == _eid_recl), None)
_token_b = _item_b["claim_token"] if _item_b else None
_assert("stale-reclaim：notifierB reclaim 取得新 token_b（claimed_at 已逾 TTL 可被接手）",
        bool(_token_b) and _token_b != _token_a)
# notifierA 帶舊 token_a 想標 sent → 被拒（reclaim 已換 token、stale-lease 雙送杜絕）
_res_recl_a = mark_sent_tool(_eid_recl, claim_token=_token_a, sent_text="A 舊 token 不該過（雙送）")
_assert("stale-reclaim：notifierA 舊 token_a mark_sent → 被拒（防 stale-lease 雙送）",
        "未持有此上報的有效租約" in _res_recl_a and _status(_eid_recl) == "pending")
_assert("stale-reclaim：A 被拒後不落 sent log（未雙送、無假稽核）",
        not _has_sent_log(_eid_recl))
# notifierB 帶新 token_b → 正常標 sent
_res_recl_b = mark_sent_tool(_eid_recl, claim_token=_token_b, sent_text="B 新 token 正路送出")
_assert("stale-reclaim：notifierB 新 token_b → 正常標 sent",
        "已標記 sent" in _res_recl_b and _status(_eid_recl) == "sent")


# === 收尾 ===
print(f"\n{'='*50}")
print(f"PASSED {passed}  FAILED {failed}")
if failures:
    print("FAILURES:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("ALL GREEN")
