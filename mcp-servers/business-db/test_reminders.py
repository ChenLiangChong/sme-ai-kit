#!/usr/bin/env python3
"""Standalone test — scheduled_reminders 派工器（直接跑：python test_reminders.py）。

建臨時 DB → executescript(schema.sql) baseline → run_migrations（含 011）→ 驗證：
schedule / 時間推進（daily / weekly / weekdays 跳週末）/ 到期 flush（fake push）/ at-most-once 不重送 /
once 失敗轉 failed / cancel。不碰正式 DB（用 SME_DB_PATH 指到 tempfile）。
"""
import os
import sys
import tempfile
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)


def _dt(s):
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


def main() -> int:
    tmp = tempfile.mkdtemp()
    os.environ["SME_DB_PATH"] = os.path.join(tmp, "t.db")
    os.environ.pop("SME_FLOOR", None)

    from shared.db import get_db
    from shared.migrations import run_migrations
    from shared import reminders

    # baseline schema + migrations（含 011）
    db = get_db()
    with open(os.path.join(_HERE, "schema.sql"), encoding="utf-8") as f:
        db.executescript(f.read())
    db.commit()
    applied = run_migrations(db)
    cols = {r[1] for r in db.execute("PRAGMA table_info(scheduled_reminders)").fetchall()}
    db.close()
    assert cols, "scheduled_reminders 表沒建出來（011 未套用）"
    assert {"next_fire_at", "recurrence", "status", "fail_count"} <= cols, cols
    print(f"[ok] migration 011 applied (applied={applied})")

    # ── 純函式：時間推進 ───────────────────────────────────────────────
    # daily：fire 當下 → 隔天同時刻
    assert reminders.advance_fire("2026-06-22 09:00:00", "daily", _dt("2026-06-22 09:00:00")) == "2026-06-23 09:00:00"
    # weekly：+7 天
    assert reminders.advance_fire("2026-06-22 09:00:00", "weekly", _dt("2026-06-22 09:00:00")) == "2026-06-29 09:00:00"
    # weekdays 從週一 → 週二
    assert reminders.advance_fire("2026-06-22 09:00:00", "weekdays", _dt("2026-06-22 12:00:00")) == "2026-06-23 09:00:00"
    # weekdays 從週五 → 跳過六日到週一（2026-06-26 是週五、6-29 週一）
    assert reminders.advance_fire("2026-06-26 09:00:00", "weekdays", _dt("2026-06-26 09:00:00")) == "2026-06-29 09:00:00"
    # 停機數天 → 一次推進到未來、不補發
    assert reminders.advance_fire("2026-06-19 09:00:00", "daily", _dt("2026-06-22 12:00:00")) == "2026-06-23 09:00:00"
    print("[ok] advance_fire（daily / weekly / weekdays 跳週末 / 停機不補發）")

    # monthly：+1 個月 / 月底夾日(1/31→2/28) / 跨年 / 停機跨多月一次推進
    assert reminders.advance_fire("2026-01-15 09:00:00", "monthly", _dt("2026-01-15 09:00:00")) == "2026-02-15 09:00:00"
    assert reminders.advance_fire("2026-12-20 09:00:00", "monthly", _dt("2026-12-20 09:00:00")) == "2027-01-20 09:00:00"
    assert reminders.advance_fire("2026-01-31 09:00:00", "monthly", _dt("2026-01-31 09:00:00")) == "2026-02-28 09:00:00"
    assert reminders.advance_fire("2026-01-15 09:00:00", "monthly", _dt("2026-04-10 12:00:00")) == "2026-04-15 09:00:00"
    print("[ok] advance_fire monthly（+1月 / 月底夾日 / 跨年 / 停機跨多月一次推進）")

    # ── schedule + flush ───────────────────────────────────────────────
    r = reminders.schedule_reminder(title="once-past", message="嗨一次性", target_id="U_alice",
                                    recurrence="once", fire_at="2020-01-01 09:00")
    assert "已排程" in r, r
    reminders.schedule_reminder(title="daily-group", message="每日待辦", target_id="C_group",
                                recurrence="daily", fire_at="2026-06-22 09:00")

    sent = []

    def push_ok(channel_id, to, text):
        sent.append((to, text)); return True

    # now 設在 daily 的 09:00 之後、兩筆都到期
    stats = reminders.flush_due_reminders(push_ok, now="2026-06-22 12:13:00")
    assert stats["fired"] == 2, stats
    assert any(to == "U_alice" for to, _ in sent), sent
    assert any(to == "C_group" for to, _ in sent), sent
    print(f"[ok] flush 推出兩筆 {stats}")

    # at-most-once：同 now 再 flush 一次 → once 已 done、daily 已前進到隔天 → 0 fired
    stats2 = reminders.flush_due_reminders(push_ok, now="2026-06-22 12:13:00")
    assert stats2["fired"] == 0 and stats2["candidates"] == 0, stats2
    print("[ok] at-most-once：同時點不重送")

    # once 已 done、daily 仍 active 且 next_fire_at 前進到隔天
    assert "once-past" in reminders.list_reminders(status="done"), "once 應為 done"
    active = reminders.list_reminders(status="active")
    assert "daily-group" in active and "2026-06-23 09:00:00" in active, active
    print("[ok] once→done、daily 前進到 2026-06-23 09:00")

    # ── monthly schedule（migration 012 後 DB CHECK 允許）──────────────────
    rm = reminders.schedule_reminder(title="monthly-bill", message="月度請款單提醒", target_id="C_group",
                                     recurrence="monthly", fire_at="2026-07-25 09:00")
    assert "已排程" in rm and "每月" in rm, rm
    act = reminders.list_reminders(status="active")
    assert "monthly-bill" in act and "2026-07-25 09:00:00" in act, act
    print("[ok] schedule monthly（每月、DB CHECK 接受）")

    # ── once 推失敗 → failed ────────────────────────────────────────────
    reminders.schedule_reminder(title="once-fail", message="會推失敗", target_id="U_bob",
                                recurrence="once", fire_at="2020-01-01 09:00")

    def push_fail(channel_id, to, text):
        return False

    sf = reminders.flush_due_reminders(push_fail, now="2026-06-22 12:13:00")
    assert sf["failed"] == 1, sf
    assert "once-fail" in reminders.list_reminders(status="failed"), "once 推失敗應為 failed"
    print("[ok] once 推失敗 → failed")

    # ── cancel ─────────────────────────────────────────────────────────
    rc = reminders.schedule_reminder(title="to-cancel", message="待取消", target_id="C_group",
                                     recurrence="daily", fire_at="23:30")
    rid = int(rc.split("#")[1].split(" ")[0])
    assert "已取消" in reminders.cancel_reminder(rid), "cancel 應成功"
    assert "無法取消" in reminders.cancel_reminder(rid), "重複 cancel 應擋下"
    assert "to-cancel" not in reminders.list_reminders(status="active"), "取消後不應在 active"
    print("[ok] cancel + 重複 cancel 擋下")

    print("\nALL OK ✅ scheduled_reminders 派工器")
    return 0


if __name__ == "__main__":
    sys.exit(main())
