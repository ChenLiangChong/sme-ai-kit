"""Shared reminder helper — 週期/一次性提醒的「派工器模式」（不開 crontab 寫權限給 floor）。

設計鏡像 shared.escalation：runtime（機密層 full-access / operator）透過 gated MCP 工具
schedule_reminder 寫一筆 scheduled_reminders row（不碰 OS crontab、不逃出 sandbox），由「笨投遞器」
reminder_dispatcher.py（OS cron 獨立進程、host 跑、讀得到 DB + LINE token）每 N 分鐘讀到期 row 推給
對象。runtime 自助排程 / 取消（cancel_reminder），但永遠碰不到 live crontab（保住第一道牆）。

語意：
- recurrence: once / daily / weekdays（一~五）/ weekly（每 7 天）/ monthly（每月、月底自動夾日）。
- next_fire_at: 下次該觸發（localtime 'YYYY-MM-DD HH:MM:SS'、字串排序即時序）。
- 投遞保證 = at-most-once：claim＝next_fire_at CAS 前進（並發 dispatcher 不雙送；process 在送出後
  crash 寧可漏這次也不重推＝不洗版群組）。escalation 是 at-least-once（必達），reminder 不是必達服務、
  取捨刻意不同。一次推進跨過所有錯過的時點（停機補開後不補發歷史、只發下一次）。
- 完成：once 送完 status='done'；recurring 由 runtime 在條件達成時 cancel_reminder（自動完成＝v2）。

放 shared/（非 module）理由同 escalation.py：standalone dispatcher 與 MCP tool 都要 call、直接 SQL、
只依賴 shared.db / shared.floor_policy，避免拆 module 時 import cycle。
"""
import calendar
from datetime import datetime, timedelta

from shared.db import _now, get_db, transaction

_FMT = "%Y-%m-%d %H:%M:%S"
RECURRENCES = ("once", "daily", "weekdays", "weekly", "monthly")
_REC_ZH = {"once": "一次性", "daily": "每日", "weekdays": "平日(一~五)", "weekly": "每週", "monthly": "每月"}
_STATUS_ZH = {"active": "啟用", "done": "已完成", "cancelled": "已取消", "failed": "推送失敗"}


# ── 時間推進 ──────────────────────────────────────────────────────────────
def _parse_dt(s: str) -> datetime:
    return datetime.strptime(s, _FMT)


def resolve_first_fire(fire_at: str, recurrence: str, now: datetime | None = None) -> str:
    """把使用者給的 fire_at 正規化成第一次 next_fire_at 字串。
    支援：'YYYY-MM-DD HH:MM[:SS]'（明確時點）或 'HH:MM[:SS]'（時刻、自動取下一個未來時點）。"""
    now = now or datetime.now()
    s = (fire_at or "").strip()
    if not s:
        raise ValueError("fire_at 不可為空（給 'YYYY-MM-DD HH:MM' 或 'HH:MM'）")
    # 明確時點
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s, fmt).strftime(_FMT)
        except ValueError:
            pass
    # 只給時刻 → 取下一個未來時點
    t = None
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            t = datetime.strptime(s, fmt)
            break
        except ValueError:
            pass
    if t is None:
        raise ValueError(f"fire_at 格式無法解析：{fire_at!r}（用 'YYYY-MM-DD HH:MM' 或 'HH:MM'）")
    cand = now.replace(hour=t.hour, minute=t.minute, second=t.second, microsecond=0)
    if recurrence == "weekdays":
        while cand <= now or cand.weekday() >= 5:
            cand += timedelta(days=1)
    elif cand <= now:
        cand += timedelta(days=1)
    return cand.strftime(_FMT)


def _add_months(dt: datetime, n: int = 1) -> datetime:
    """加 n 個月；目標月天數不足時夾到該月最後一天（如 1/31 → 2/28、跨年自動進位）。"""
    m0 = dt.month - 1 + n
    year = dt.year + m0 // 12
    month = m0 % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def advance_fire(next_fire_at: str, recurrence: str, now: datetime | None = None) -> str:
    """recurring 提醒送出後算下一個未來時點（一次推進跨過所有錯過的時點＝不補發、不洗版）。"""
    now = now or datetime.now()
    dt = _parse_dt(next_fire_at)
    if recurrence == "daily":
        while dt <= now:
            dt += timedelta(days=1)
    elif recurrence == "weekly":
        while dt <= now:
            dt += timedelta(days=7)
    elif recurrence == "weekdays":
        dt += timedelta(days=1)
        while dt <= now or dt.weekday() >= 5:
            dt += timedelta(days=1)
    elif recurrence == "monthly":
        while dt <= now:
            dt = _add_months(dt, 1)
    else:  # once：不推進
        return next_fire_at
    return dt.strftime(_FMT)


def _format_reminder(row) -> str:
    """推給對象的文字。提醒本質是業務內容、非系統通報 → 直接送 message（note 是內部備註、不外送）。"""
    return row["message"]


# ── service（MCP 工具呼叫）─────────────────────────────────────────────────
def schedule_reminder(*, title: str, message: str, target_id: str, recurrence: str = "once",
                      fire_at: str = "", channel_id: str = "", target_type: str = "user",
                      business_unit: str = "", note: str = "", created_by: str = "") -> str:
    from shared.floor_policy import get_floor
    recurrence = (recurrence or "once").strip()
    if recurrence not in RECURRENCES:
        return f"ERROR: recurrence 必須是 {', '.join(RECURRENCES)}"
    if not title.strip() or not message.strip() or not target_id.strip():
        return "ERROR: title / message / target_id 不可為空"
    if target_type not in ("user", "group"):
        return "ERROR: target_type 必須是 user 或 group"
    try:
        next_fire = resolve_first_fire(fire_at, recurrence)
    except ValueError as e:
        return f"ERROR: {e}"

    floor = get_floor()
    with transaction() as db:
        cur = db.execute(
            "INSERT INTO scheduled_reminders "
            "(title, message, target_type, target_id, channel_id, recurrence, next_fire_at, "
            " business_unit, note, created_by_floor, created_by) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (title.strip(), message.strip(), target_type, target_id.strip(), channel_id or None,
             recurrence, next_fire, business_unit or None, note or None,
             floor or "operator", created_by or None),
        )
        rid = cur.lastrowid
        db.execute(
            "INSERT INTO interaction_log "
            "(actor, action, target_type, target_id, detail, business_unit) VALUES (?,?,?,?,?,?)",
            (created_by or "system", "reminder_scheduled", "scheduled_reminder", rid,
             f"{recurrence} @ {next_fire} → {target_id.strip()}: {title.strip()}", business_unit or None),
        )
    return (
        f"提醒 #{rid} 已排程（{_REC_ZH[recurrence]}）\n"
        f"- 首次觸發：{next_fire}\n"
        f"- 對象：{target_id.strip()}（{target_type}）\n"
        f"- 內容：{title.strip()}"
        + (f"\n- 備註：{note}" if note else "")
    )


def cancel_reminder(reminder_id: int, reason: str = "") -> str:
    with transaction() as db:
        rc = db.execute(
            "UPDATE scheduled_reminders SET status='cancelled' WHERE id=? AND status='active'",
            (reminder_id,),
        ).rowcount
        if rc == 1:
            db.execute(
                "INSERT INTO interaction_log "
                "(actor, action, target_type, target_id, detail, business_unit) VALUES (?,?,?,?,?,?)",
                ("system", "reminder_cancelled", "scheduled_reminder", reminder_id, reason or "", None),
            )
    return (f"提醒 #{reminder_id} 已取消" if rc == 1
            else f"提醒 #{reminder_id} 無法取消（不存在 / 已完成 / 已取消）")


def list_reminders(status: str = "active", business_unit: str = "", limit: int = 30) -> str:
    db = get_db()
    try:
        q = "SELECT * FROM scheduled_reminders WHERE 1=1"
        p: list = []
        if status:
            q += " AND status = ?"; p.append(status)
        if business_unit:
            q += " AND business_unit = ?"; p.append(business_unit)
        q += " ORDER BY (status='active') DESC, next_fire_at LIMIT ?"; p.append(limit)
        rows = db.execute(q, p).fetchall()
        if not rows:
            return "沒有符合條件的提醒。"
        lines = [f"## 排程提醒（{len(rows)} 筆）"]
        for r in rows:
            tail = f" → 下次 {r['next_fire_at']}" if r["status"] == "active" else ""
            if r["fail_count"]:
                tail += f"（推失敗 {r['fail_count']} 次）"
            bu = f" [{r['business_unit']}]" if r["business_unit"] else ""
            note = f"｜{r['note']}" if r["note"] else ""
            lines.append(
                f"- [#{r['id']}] [{_STATUS_ZH.get(r['status'], r['status'])}/"
                f"{_REC_ZH.get(r['recurrence'], r['recurrence'])}]{bu} {r['title']} → {r['target_id']}{tail}{note}"
            )
        return "\n".join(lines)
    finally:
        db.close()


# ── dispatcher（OS cron 笨投遞器主迴圈）────────────────────────────────────
def flush_due_reminders(push_fn, *, limit: int = 50, now: str | None = None) -> dict:
    """笨投遞器主迴圈。push_fn(channel_id, to, text) -> bool（True=LINE API 真 ok）。

    - 撈 status='active' 且 next_fire_at <= now。
    - claim＝原子 CAS：once 設 status='done'、recurring 把 next_fire_at 前進到下個未來時點，
      WHERE 帶舊 next_fire_at + status='active' → 並發只有一路 rowcount==1（at-most-once、不雙送）。
    - 搶到才 push。成功 → last_fired_at + interaction_log（reminder_sent）。
      失敗 → fail_count+1；once 直接 status='failed'（只試一次）、recurring 留待下個時點。

    回 {'fired','failed','skipped','candidates'}。
    """
    now = now or _now()
    now_dt = _parse_dt(now)
    db = get_db()
    try:
        rows = db.execute(
            "SELECT * FROM scheduled_reminders WHERE status='active' AND next_fire_at <= ? "
            "ORDER BY next_fire_at LIMIT ?",
            (now, limit),
        ).fetchall()
    finally:
        db.close()

    stats = {"fired": 0, "failed": 0, "skipped": 0, "candidates": len(rows)}
    for row in rows:
        once = row["recurrence"] == "once"
        old_next = row["next_fire_at"]
        if once:
            claim_sql = (
                "UPDATE scheduled_reminders SET status='done', last_attempt_at=?, "
                "fire_count=fire_count+1 WHERE id=? AND status='active' AND next_fire_at=?"
            )
            claim_params = (now, row["id"], old_next)
        else:
            new_next = advance_fire(old_next, row["recurrence"], now_dt)
            claim_sql = (
                "UPDATE scheduled_reminders SET next_fire_at=?, last_attempt_at=?, "
                "fire_count=fire_count+1 WHERE id=? AND status='active' AND next_fire_at=?"
            )
            claim_params = (new_next, now, row["id"], old_next)

        with transaction() as cdb:
            won = cdb.execute(claim_sql, claim_params).rowcount
        if won != 1:
            stats["skipped"] += 1  # 並發另一路已搶走、或 row 狀態已變
            continue

        text = _format_reminder(row)
        try:
            ok = bool(push_fn(row["channel_id"], row["target_id"], text))
        except Exception:
            ok = False

        with transaction() as wdb:
            if ok:
                wdb.execute(
                    "UPDATE scheduled_reminders SET last_fired_at=?, fail_count=0 WHERE id=?",
                    (now, row["id"]),
                )
                wdb.execute(
                    "INSERT INTO interaction_log "
                    "(actor, action, target_type, target_id, detail, business_unit) VALUES (?,?,?,?,?,?)",
                    ("system", "reminder_sent", "scheduled_reminder", row["id"],
                     f"[cron→{row['target_id']}] {text}", row["business_unit"]),
                )
                stats["fired"] += 1
            else:
                new_fail = row["fail_count"] + 1
                if once:  # once 只試一次、推不出去就 failed（供開機 readout 提醒）
                    wdb.execute(
                        "UPDATE scheduled_reminders SET status='failed', fail_count=? WHERE id=?",
                        (new_fail, row["id"]),
                    )
                else:     # recurring 已前進、本次丟失只記 fail_count、下個時點再試
                    wdb.execute(
                        "UPDATE scheduled_reminders SET fail_count=? WHERE id=?",
                        (new_fail, row["id"]),
                    )
                stats["failed"] += 1
    return stats


def count_failed_reminders(db) -> int:
    """供全權限層開機 readout：回 status='failed' 的筆數（推不出去、無人知）。caller-managed（讀）。"""
    return db.execute(
        "SELECT COUNT(*) c FROM scheduled_reminders WHERE status='failed'"
    ).fetchone()["c"]
