"""#H1 系統健康哨兵 + #H2 待確認跟催 單元測試（offline、standalone、不連網）。

跑法：
    cd mcp-servers/business-db
    SME_DB_PATH=/tmp/_t_hi.db /abs/.venv/bin/python3 tests/test_health_intake.py

涵蓋：
#H1 heartbeat + 失聯告警
- scan_and_enqueue_due_reminders 落 HEARTBEAT_SCAN heartbeat（即使零時限也寫＝證明掃描器在跑）
- check_scan_health：剛掃完 fresh / 注入舊 heartbeat → scan_overdue
- scan_health_and_alert（watchdog）：落自身 heartbeat、scan 失聯→enqueue scan_stalled、
  同失聯期 dedup 不重送、從未掃過但有待處理時限→告警、fresh→不告警
#H2 待確認跟催
- stage_deadline_intake 建 awaiting row（只存事實）
- scan_and_enqueue_unconfirmed_intakes：未達節點不催 / 達 4h 催 / 同節點冪等 / 24h 再催 /
  confirmed・discarded 不掃；提醒文字只含抽出的事實、絕不端 computed deadline（反捏造鐵律）
- create_deadline(confirm_intake_id=) 同 tx 關閉 backlog；resolve_deadline_intake 捨棄
- list_pending_intakes 只列 awaiting
- 結構性：pending_intakes 表「無任何 computed deadline 欄」（不可能洩權威日期）
"""
import atexit
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
DB_PATH = _tmp.name
_tmp.close()
os.environ["SME_DB_PATH"] = DB_PATH
os.environ.pop("SME_FLOOR", None)  # 全權限（is_full_access）跑 service / readout


@atexit.register
def _cleanup():
    try:
        os.unlink(DB_PATH)
    except OSError:
        pass


import server  # noqa: E402

server.DB_PATH = DB_PATH
server.init_db()

from shared import deadlines as D  # noqa: E402
from shared.db import get_db, transaction  # noqa: E402
from modules.deadlines import service as dsvc  # noqa: E402

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


def _id(text):
    m = re.search(r"#(\d+)", text or "")
    return int(m.group(1)) if m else None


def _exec(sql, params=()):
    with transaction() as db:
        db.execute(sql, params)


def _q1(sql, params=()):
    db = get_db()
    try:
        return db.execute(sql, params).fetchone()
    finally:
        db.close()


def _clear_health():
    """清掉 scan/watchdog heartbeat + scan_stalled 上報與其稽核鏡像（隔離 watchdog 場景）。"""
    _exec("DELETE FROM interaction_log WHERE action IN (?,?,?)",
          (D.HEARTBEAT_SCAN, D.HEARTBEAT_WATCHDOG, "escalation_scan_stalled"))
    _exec("DELETE FROM pending_escalations WHERE event_type='scan_stalled'")


def _set_latest_heartbeat(kind, ts):
    """把最近一筆某類 heartbeat 的 created_at 改成 ts（注入舊時間用）。"""
    row = _q1("SELECT id FROM interaction_log WHERE action=? ORDER BY id DESC LIMIT 1", (kind,))
    if row:
        _exec("UPDATE interaction_log SET created_at=? WHERE id=?", (ts, row["id"]))


def _insert_heartbeat(kind, ts):
    _exec("INSERT INTO interaction_log (actor, action, target_type, target_id, detail, created_at) "
          "VALUES (?,?,?,?,?,?)", ("系統·cron", kind, "system", None, "", ts))


# ============================================================
# #H1 系統健康哨兵
# ============================================================

# T1：scan_and_enqueue_due_reminders 落 heartbeat（空 DB 也寫）
_clear_health()
_stats = D.scan_and_enqueue_due_reminders()
_hb = _q1("SELECT COUNT(*) c FROM interaction_log WHERE action=?", (D.HEARTBEAT_SCAN,))
_assert("H1-T1: scan 跑完落 HEARTBEAT_SCAN（零時限也證明在跑）", _hb["c"] == 1, detail=str(_stats))

# T2：剛掃完 → check_scan_health fresh
_db = get_db()
try:
    _h = D.check_scan_health(_db)
finally:
    _db.close()
_assert("H1-T2: 剛掃完 scan_never=False、scan_overdue=False", (not _h["scan_never"]) and (not _h["scan_overdue"]))

# T3：注入舊 heartbeat（單一）→ scan_overdue（用注入 now、純讀不寫）
_clear_health()
_insert_heartbeat(D.HEARTBEAT_SCAN, "2026-01-01 00:00:00")
_db = get_db()
try:
    _h3 = D.check_scan_health(_db, now=datetime(2026, 1, 2, 8, 0, 0))  # 32h later
finally:
    _db.close()
_assert("H1-T3: 32h 前的 heartbeat → scan_overdue=True", _h3["scan_overdue"], detail=str(_h3["scan_age_hours"]))
_assert("H1-T3: scan_age_hours≈32", _h3["scan_age_hours"] and 31.9 < _h3["scan_age_hours"] < 32.1)
_assert("H1-T3: 未逾門檻的 watchdog 不誤報（此處 watchdog_never=True、非 overdue）",
        _h3["watchdog_never"] and (not _h3["watchdog_overdue"]))

# T4：watchdog 偵測 scan 失聯（real-relative：heartbeat=now-48h）→ enqueue scan_stalled + 落自身 heartbeat
_clear_health()
_insert_heartbeat(D.HEARTBEAT_SCAN, (datetime.now() - timedelta(hours=48)).strftime("%Y-%m-%d %H:%M:%S"))
_w = D.scan_health_and_alert()  # now=None（real）
_sc = _q1("SELECT COUNT(*) c FROM pending_escalations WHERE event_type='scan_stalled'")
_wdh = _q1("SELECT COUNT(*) c FROM interaction_log WHERE action=?", (D.HEARTBEAT_WATCHDOG,))
_assert("H1-T4: watchdog 告警 scan 失聯（alerted=True）", _w["alerted"], detail=str(_w))
_assert("H1-T4: enqueue 一筆 scan_stalled", _sc["c"] == 1, detail=str(_sc["c"]))
_assert("H1-T4: watchdog 落自身 heartbeat（自證活著）", _wdh["c"] >= 1)

# T5：同失聯期再跑 → dedup 不重送（SCAN_REALERT_HOURS 內）
_w2 = D.scan_health_and_alert()
_sc2 = _q1("SELECT COUNT(*) c FROM pending_escalations WHERE event_type='scan_stalled'")
_assert("H1-T5: 同失聯期 dedup（第二次 alerted=False）", not _w2["alerted"], detail=str(_w2))
_assert("H1-T5: scan_stalled 仍只有 1 筆（未重送）", _sc2["c"] == 1, detail=str(_sc2["c"]))

# T6：從未掃過但已有待處理時限 → 告警
_clear_health()
_m = _id(dsvc.create_matter("測試案", "2026-健康-001", "", "", "", "", "", "王律師", 0, 0, "系統"))
_d = dsvc.create_deadline(
    matter_id=_m, type="appeal_civil", description="", trigger_event="一審判決送達",
    service_base_date="2026-05-01", service_type="normal", statutory_days=0, statutory_basis="",
    statutory_basis_version="", period_type="", severity="", has_local_agent=1, in_transit_days=0,
    court_region="", party_region="", buffer_days=1, stated_period_days=0, document_date="",
    assignee="", assignee_line_user_id="", escalation_lead_days="", created_by="系統",
)
_assert("H1-T6 setup: 建一筆 pending 時限成功", _id(_d) is not None, detail=_d[:80])
_w6 = D.scan_health_and_alert()
_assert("H1-T6: 從未掃過 + 有待處理時限 → 告警", _w6["alerted"] and _w6["scan_never"], detail=str(_w6))

# T7：fresh scan heartbeat → watchdog 不告警
_clear_health()
_insert_heartbeat(D.HEARTBEAT_SCAN, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
_w7 = D.scan_health_and_alert()
_assert("H1-T7: 剛掃過（fresh）→ watchdog 不告警", not _w7["alerted"], detail=str(_w7))


# ============================================================
# #H2 待確認跟催
# ============================================================

# T8：stage 建 awaiting row（只存事實）
_st = dsvc.stage_deadline_intake(
    matter_id=0, matter_label="陳案一審民事判決", doc_type="appeal_civil",
    service_base_date="2026-06-01", stated_period_days=20, document_date="2026-05-28",
    extracted_summary="陳案一審民事判決 2026-06-01 送達、教示20日", submitted_by="林律師",
)
_iid = _id(_st)
_row = _q1("SELECT * FROM pending_intakes WHERE id=?", (_iid,))
_assert("H2-T8: stage 建 awaiting 暫存", _row and _row["status"] == "awaiting", detail=_st[:80])
_assert("H2-T8: 暫存存的是事實（送達日/教示）", _row["service_base_date"] == "2026-06-01" and _row["stated_period_days"] == 20)

# 把 created_at 釘成已知時間，方便注入 now 做等待時數
_FIX = "2026-06-01 09:00:00"
_exec("UPDATE pending_intakes SET created_at=? WHERE id=?", (_FIX, _iid))
_base = datetime(2026, 6, 1, 9, 0, 0)

# T9：等待 1h（未達 4h 節點）→ 不催
_s9 = D.scan_and_enqueue_unconfirmed_intakes(now=_base + timedelta(hours=1))
_assert("H2-T9: 等待1h未達節點 → reminded=0", _s9["reminded"] == 0, detail=str(_s9))

# T10：等待 5h（達 4h 節點）→ 催一筆 + reminders_sent 記 4
_s10 = D.scan_and_enqueue_unconfirmed_intakes(now=_base + timedelta(hours=5))
_iu = _q1("SELECT * FROM pending_escalations WHERE event_type='intake_unconfirmed' ORDER BY id DESC LIMIT 1")
_row10 = _q1("SELECT reminders_sent FROM pending_intakes WHERE id=?", (_iid,))
_assert("H2-T10: 達4h節點 → reminded=1", _s10["reminded"] == 1, detail=str(_s10))
_assert("H2-T10: enqueue intake_unconfirmed", _iu is not None)
_assert("H2-T10: reminders_sent 記入 4", "4" in (_row10["reminders_sent"] or ""))

# T10b：反捏造鐵律——提醒文字只含抽出的事實、絕不端 computed deadline
_summary = _iu["summary"] if _iu else ""
_assert("H2-T10b: 提醒含送達日（事實）", "2026-06-01" in _summary, detail=_summary)
_assert("H2-T10b: 提醒含教示天數（事實）", "教示20日" in _summary, detail=_summary)
_assert("H2-T10b: 提醒『不』端 computed 權威日期（無內部/法定期限字樣）",
        ("內部期限" not in _summary) and ("法定期限" not in _summary)
        and ("internal_deadline" not in _summary) and ("statutory_deadline" not in _summary),
        detail=_summary)

# T11：同節點冪等（再掃 6h、24h 節點未到）→ 不重催
_s11 = D.scan_and_enqueue_unconfirmed_intakes(now=_base + timedelta(hours=6))
_assert("H2-T11: 同節點冪等 → reminded=0", _s11["reminded"] == 0, detail=str(_s11))

# T12：達 24h 節點 → 再催一筆
_s12 = D.scan_and_enqueue_unconfirmed_intakes(now=_base + timedelta(hours=25))
_row12 = _q1("SELECT reminders_sent FROM pending_intakes WHERE id=?", (_iid,))
_assert("H2-T12: 達24h節點 → reminded=1", _s12["reminded"] == 1, detail=str(_s12))
_assert("H2-T12: reminders_sent 記入 24", "24" in (_row12["reminders_sent"] or ""))

# T13：create_deadline(confirm_intake_id=) 同 tx 關閉 backlog
_m13 = _id(dsvc.create_matter("確認案", "2026-健康-013", "", "", "", "", "", "王律師", 0, 0, "系統"))
_st13 = dsvc.stage_deadline_intake(
    matter_id=_m13, matter_label="確認案", doc_type="appeal_civil",
    service_base_date="2026-06-02", stated_period_days=20, document_date="",
    extracted_summary="確認案一審判決 6/2 送達", submitted_by="林律師",
)
_iid13 = _id(_st13)
_d13 = dsvc.create_deadline(
    matter_id=_m13, type="appeal_civil", description="", trigger_event="一審判決送達",
    service_base_date="2026-06-02", service_type="normal", statutory_days=0, statutory_basis="",
    statutory_basis_version="", period_type="", severity="", has_local_agent=1, in_transit_days=0,
    court_region="", party_region="", buffer_days=1, stated_period_days=20, document_date="",
    assignee="", assignee_line_user_id="", escalation_lead_days="", created_by="林律師",
    confirm_intake_id=_iid13,
)
_did13 = _id(_d13)
_row13 = _q1("SELECT status, resolved_deadline_id FROM pending_intakes WHERE id=?", (_iid13,))
_assert("H2-T13: confirm_intake_id 把暫存標 confirmed", _row13["status"] == "confirmed", detail=str(dict(_row13)))
_assert("H2-T13: 暫存連到入庫的時限 id", _row13["resolved_deadline_id"] == _did13)
_assert("H2-T13: 回覆註記已關閉跟催", "跟催關閉" in _d13)
# confirmed 不再被掃
_s13 = D.scan_and_enqueue_unconfirmed_intakes(now=_base + timedelta(days=10))
_awaiting_after = _q1("SELECT COUNT(*) c FROM pending_intakes WHERE id=? AND status='awaiting'", (_iid13,))
_assert("H2-T13: confirmed 暫存不再被跟催掃描", _awaiting_after["c"] == 0)

# T14：resolve_deadline_intake 捨棄
_st14 = dsvc.stage_deadline_intake(
    matter_id=0, matter_label="誤判案", doc_type="", service_base_date="2026-06-03",
    stated_period_days=0, document_date="", extracted_summary="誤傳的非判決文件", submitted_by="助理",
)
_iid14 = _id(_st14)
_r14 = dsvc.resolve_deadline_intake(_iid14, action="discarded", note="非判決、誤傳", resolved_by="林律師")
_row14 = _q1("SELECT status FROM pending_intakes WHERE id=?", (_iid14,))
_assert("H2-T14: resolve discarded → status=discarded", _row14["status"] == "discarded", detail=_r14[:80])
# 重複收掉擋下
_r14b = dsvc.resolve_deadline_intake(_iid14, action="discarded", note="", resolved_by="林律師")
_assert("H2-T14: 已收掉的暫存不可重複收（rowcount guard）", _r14b.startswith("ERROR"), detail=_r14b[:80])

# T15：結構性反捏造——pending_intakes 表無任何 computed deadline 欄
_dbc = get_db()
try:
    _cols = {r["name"] for r in _dbc.execute("PRAGMA table_info(pending_intakes)").fetchall()}
finally:
    _dbc.close()
_forbidden = {"internal_deadline", "statutory_deadline", "start_date", "effective_date", "calc_trace"}
_assert("H2-T15: pending_intakes 結構上無 computed deadline 欄（不可能洩權威日期）",
        not (_cols & _forbidden), detail=str(_cols & _forbidden))

# T16：list_pending_intakes 只列 awaiting
_lst = dsvc.list_pending_intakes(limit=50)
_assert("H2-T16: list 含仍待確認的（T8 那筆 #%d）" % _iid, f"#{_iid}" in _lst, detail=_lst[:120])
_assert("H2-T16: list 不含已 confirmed 的（#%d）" % _iid13, f"#{_iid13}" not in _lst)
_assert("H2-T16: list 不含已 discarded 的（#%d）" % _iid14, f"#{_iid14}" not in _lst)


# ============================================================
# codex r1 修補回歸（機密軸 + 資料完整性）
# ============================================================

def _with_floor(floor, fn):
    """暫時設 SME_FLOOR 跑 fn、用後還原（模擬受限層）。"""
    old = os.environ.get("SME_FLOOR")
    os.environ["SME_FLOOR"] = floor
    try:
        return fn()
    finally:
        if old is None:
            os.environ.pop("SME_FLOOR", None)
        else:
            os.environ["SME_FLOOR"] = old


# T17：confirm_intake_id anti-oracle —— 受限層不可藉公開案件 + 猜 id 關掉機密 intake、
# 且「機密存在」與「根本不存在」回覆不可區分（皆「未對位」、皆非「跟催關閉」）
_mc = _id(dsvc.create_matter("機密案", "2026-健康-機", "陳XX", "", "", "", "", "王律師", 1, 1, "系統"))
_stc = dsvc.stage_deadline_intake(
    matter_id=_mc, matter_label="機密案", doc_type="appeal_civil", service_base_date="2026-06-09",
    stated_period_days=20, document_date="", extracted_summary="機密案待確認", submitted_by="王律師",
)
_iidc = _id(_stc)
_mp = _id(dsvc.create_matter("公開案", "2026-健康-公", "", "", "", "", "", "王律師", 0, 0, "系統"))

def _restricted_confirm_conf():
    return dsvc.create_deadline(
        matter_id=_mp, type="appeal_civil", description="", trigger_event="一審判決送達",
        service_base_date="2026-06-09", service_type="normal", statutory_days=0, statutory_basis="",
        statutory_basis_version="", period_type="", severity="", has_local_agent=1, in_transit_days=0,
        court_region="", party_region="", buffer_days=1, stated_period_days=0, document_date="",
        assignee="", assignee_line_user_id="", escalation_lead_days="", created_by="general員工",
        confirm_intake_id=_iidc,  # 指向機密 intake
    )

_r_conf = _with_floor("general", _restricted_confirm_conf)
_rowc = _q1("SELECT status FROM pending_intakes WHERE id=?", (_iidc,))
_assert("H2-T17: 受限層用公開案件 confirm 機密 intake → 未關閉（仍 awaiting）", _rowc["status"] == "awaiting", detail=str(dict(_rowc)))
_assert("H2-T17: 回覆為『未對位』、非『跟催關閉』（不洩機密存在）",
        ("未對位" in _r_conf) and ("跟催關閉" not in _r_conf), detail=_r_conf[-120:])

# T18：跨案不連結（全權限也守資料完整性）—— intake 屬 A 案、create_deadline 在 B 案 → 不關閉
_mA = _id(dsvc.create_matter("A案", "2026-健康-A", "", "", "", "", "", "王律師", 0, 0, "系統"))
_mB = _id(dsvc.create_matter("B案", "2026-健康-B", "", "", "", "", "", "王律師", 0, 0, "系統"))
_stA = dsvc.stage_deadline_intake(
    matter_id=_mA, matter_label="A案", doc_type="appeal_civil", service_base_date="2026-06-10",
    stated_period_days=20, document_date="", extracted_summary="A案待確認", submitted_by="王律師",
)
_iidA = _id(_stA)
_dB = dsvc.create_deadline(
    matter_id=_mB, type="appeal_civil", description="", trigger_event="一審判決送達",
    service_base_date="2026-06-10", service_type="normal", statutory_days=0, statutory_basis="",
    statutory_basis_version="", period_type="", severity="", has_local_agent=1, in_transit_days=0,
    court_region="", party_region="", buffer_days=1, stated_period_days=0, document_date="",
    assignee="", assignee_line_user_id="", escalation_lead_days="", created_by="王律師",
    confirm_intake_id=_iidA,  # A 案的 intake、卻在 B 案入庫
)
_rowA = _q1("SELECT status, resolved_deadline_id FROM pending_intakes WHERE id=?", (_iidA,))
_assert("H2-T18: 跨案 confirm 不關閉（仍 awaiting、未錯連）",
        _rowA["status"] == "awaiting" and _rowA["resolved_deadline_id"] is None, detail=str(dict(_rowA)))
_assert("H2-T18: 跨案回『未對位』", "未對位" in _dB, detail=_dB[-120:])

# T19：list_pending_intakes 機密過濾下推 SQL —— 受限層 limit=1 且最舊是機密時，仍看得到可見公開 backlog
# 先清掉前面測試殘留的 awaiting（隔離：本場景只留下方兩筆，才能用 limit=1 驗「機密不吃配額」）
_exec("UPDATE pending_intakes SET status='discarded' WHERE status='awaiting'")
_mc19 = _id(dsvc.create_matter("機密案19", "2026-健康-機19", "", "", "", "", "", "王律師", 1, 1, "系統"))
_mp19 = _id(dsvc.create_matter("公開案19", "2026-健康-公19", "", "", "", "", "", "王律師", 0, 0, "系統"))
_sc19 = _id(dsvc.stage_deadline_intake(matter_id=_mc19, matter_label="機密案19", doc_type="", service_base_date="2026-06-11", stated_period_days=0, document_date="", extracted_summary="機密19", submitted_by="王律師"))
_sp19 = _id(dsvc.stage_deadline_intake(matter_id=_mp19, matter_label="公開案19", doc_type="", service_base_date="2026-06-12", stated_period_days=0, document_date="", extracted_summary="公開19", submitted_by="王律師"))
# 機密的設為更舊（沒 SQL 過濾的話 limit=1 會先抓到它、Python 再濾掉 → 假性「空」）
_exec("UPDATE pending_intakes SET created_at='2026-06-11 00:00:00' WHERE id=?", (_sc19,))
_exec("UPDATE pending_intakes SET created_at='2026-06-12 00:00:00' WHERE id=?", (_sp19,))
_lst19 = _with_floor("general", lambda: dsvc.list_pending_intakes(limit=1))
_assert("H2-T19: 受限層 limit=1 仍見可見公開 backlog（機密不吃配額）", f"#{_sp19}" in _lst19, detail=_lst19[:160])
_assert("H2-T19: 機密暫存不列給受限層", f"#{_sc19}" not in _lst19)
# 全權限層仍看得到機密（inert、不過濾）
_lst19_fa = dsvc.list_pending_intakes(limit=50)
_assert("H2-T19: 全權限層看得到機密暫存", f"#{_sc19}" in _lst19_fa)


print(f"\n{'='*50}\n{passed} passed, {failed} failed")
if failures:
    print("FAILURES:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
sys.exit(0)
