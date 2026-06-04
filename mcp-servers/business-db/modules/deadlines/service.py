"""Deadlines service — 案件（matters）+ 時限（deadlines）業務邏輯。

層次邊界：transaction ownership 在這層，repository 不 commit。
時限天數一律呼叫 shared.deadlines.compute_deadline（純函式、確定性、附 statutory_basis），
service 不做任何天數心算（反捏造鐵律）。calc_trace 落 JSON 欄供律師逐步覆核。

回傳格式：中文 status/type 標籤、不用 emoji；錯誤回 'ERROR: <中文>' 字串（不 raise）。
"""
import json

from shared.db import _now, get_db, transaction
from shared.deadlines import (
    STATUTORY_PERIODS,
    compute_deadline,
    default_lead_days,
    default_severity,
)

from . import repository

_MATTER_STATUS_VALID = ("open", "on_hold", "closed", "archived")
_MATTER_STATUS_ZH = {
    "open": "進行中",
    "on_hold": "暫停",
    "closed": "已結案",
    "archived": "已封存",
}
_PERIOD_TYPE_VALID = ("peremptory", "statutory", "court_set", "directory")
_PERIOD_TYPE_ZH = {
    "peremptory": "不變期間",
    "statutory": "通常法定期間",
    "court_set": "裁定期間",
    "directory": "訓示期間",
}
_DEADLINE_STATUS_ZH = {
    "pending": "待處理",
    "filed": "已遞交",
    "extended": "已展延",
    "missed": "已逾期",
    "cancelled": "已取消",
}
_SERVICE_TYPE_ZH = {
    "normal": "一般送達",
    "registered_deposit": "寄存送達",
    "public_domestic": "公示送達（境內）",
    "public_foreign": "公示送達（外國）",
    "commissioned": "囑託送達",
}
_SEVERITY_ZH = {"red": "紅（失權硬倒數）", "orange": "橙（可補正）", "grey": "灰（訓示提醒）"}


# ───────────────────────── matters ─────────────────────────

def create_matter(
    title: str,
    matter_no: str,
    client_name: str,
    practice_area: str,
    court: str,
    court_case_no: str,
    stage: str,
    lead_attorney: str,
    has_local_agent: int,
    confidential: int,
    created_by: str,
) -> str:
    if not title or not title.strip():
        return "ERROR: title（案由）不可為空"

    with transaction() as db:
        if matter_no:
            dup = repository.get_matter_by_no(db, matter_no)
            if dup:
                return f"ERROR: 案號 {matter_no} 已存在（案件 #{dup['id']}）"

        matter_id = repository.insert_matter(
            db,
            matter_no=matter_no or None,
            title=title,
            client_name=client_name or None,
            practice_area=practice_area or None,
            court=court or None,
            court_case_no=court_case_no or None,
            stage=stage or None,
            status="open",
            lead_attorney=lead_attorney or None,
            has_local_agent=1 if has_local_agent else 0,
            confidential=1 if confidential else 0,
            business_unit=None,
            opened_at=_now(),
        )
        repository.insert_interaction_log(
            db,
            actor=created_by or "system",
            action="matter_created",
            target_type="matter",
            target_id=matter_id,
            detail=title,
            business_unit=None,
        )

    return (
        f"案件 #{matter_id} 已建立：{title}"
        + (f"（案號 {matter_no}）" if matter_no else "")
        + (f" 主辦：{lead_attorney}" if lead_attorney else "")
    )


def list_matters(status: str, lead_attorney: str, limit: int) -> str:
    if status and status not in _MATTER_STATUS_VALID:
        return f"ERROR: status 必須是 {', '.join(_MATTER_STATUS_VALID)}"
    from shared.floor_policy import is_full_access

    db = get_db()
    try:
        rows = repository.list_matters(
            db,
            status=status,
            lead_attorney=lead_attorney,
            limit=limit,
            include_confidential=is_full_access(),
        )
        if not rows:
            return "沒有符合條件的案件。"
        lines = [f"## 案件列表（{len(rows)} 件）"]
        for m in rows:
            st = _MATTER_STATUS_ZH.get(m["status"], m["status"])
            no = f"{m['matter_no']} " if m["matter_no"] else ""
            atty = f" 主辦:{m['lead_attorney']}" if m["lead_attorney"] else ""
            client = f" 當事人:{m['client_name']}" if m["client_name"] else ""
            lines.append(f"- [{st}] [#{m['id']}] {no}{m['title']}{client}{atty}")
        return "\n".join(lines)
    finally:
        db.close()


def get_matter(matter_id: int) -> str:
    from shared.floor_policy import is_full_access

    db = get_db()
    try:
        m = repository.get_matter(db, matter_id)
        if not m:
            return f"ERROR: 找不到案件 #{matter_id}"
        # 機密軸：機密案件非全權限層不可見（同 query_knowledge / get_rule pattern）
        if m["confidential"] and not is_full_access():
            return f"ERROR: 案件 #{matter_id} 為機密案件，本層無權限檢視"
        st = _MATTER_STATUS_ZH.get(m["status"], m["status"])
        dls = repository.list_deadlines(db, matter_id=matter_id, limit=50)
        dl_str = ""
        if dls:
            dl_lines = []
            for d in dls:
                dst = _DEADLINE_STATUS_ZH.get(d["status"], d["status"])
                dl_lines.append(
                    f"  - [{dst}] [#{d['id']}] {d['description']}："
                    f"內部 {d['internal_deadline'] or '?'}（法定 {d['statutory_deadline'] or '?'}）"
                )
            dl_str = f"\n- 時限（{len(dls)} 筆）：\n" + "\n".join(dl_lines)
        return (
            f"## 案件 #{matter_id}：{m['title']}\n"
            f"- 案號：{m['matter_no'] or '未設定'}\n"
            f"- 當事人：{m['client_name'] or '未設定'}\n"
            f"- 法律領域：{m['practice_area'] or '未設定'}\n"
            f"- 繫屬法院：{m['court'] or '未設定'}\n"
            f"- 法院案號：{m['court_case_no'] or '未設定'}\n"
            f"- 審級：{m['stage'] or '未設定'}\n"
            f"- 狀態：{st}\n"
            f"- 主辦律師：{m['lead_attorney'] or '未指派'}\n"
            f"- 當地代理人（§162但書）：{'是' if m['has_local_agent'] else '否'}\n"
            f"- 機密：{'是' if m['confidential'] else '否'}\n"
            f"- 建立時間：{m['created_at']}"
            f"{dl_str}"
        )
    finally:
        db.close()


def find_matter_by_party(party_name: str, limit: int) -> str:
    if not party_name or not party_name.strip():
        return "ERROR: party_name（當事人/委任人名字）不可為空"
    from shared.floor_policy import is_full_access

    db = get_db()
    try:
        rows = repository.find_matter_by_party(
            db, party_name.strip(), limit=limit, include_confidential=is_full_access()
        )
        if not rows:
            return f"找不到當事人/案由含「{party_name}」的案件。"
        lines = [f"## 案件查詢：「{party_name}」（{len(rows)} 件）"]
        for m in rows:
            st = _MATTER_STATUS_ZH.get(m["status"], m["status"])
            no = f"{m['matter_no']} " if m["matter_no"] else ""
            client = f" 當事人:{m['client_name']}" if m["client_name"] else ""
            atty = f" 主辦:{m['lead_attorney']}" if m["lead_attorney"] else ""
            court = f" {m['court']}" if m["court"] else ""
            lines.append(f"- [{st}] [#{m['id']}] {no}{m['title']}{client}{atty}{court}")
        return "\n".join(lines)
    finally:
        db.close()


# ───────────────────────── deadlines ─────────────────────────

def create_deadline(
    matter_id: int,
    type: str,
    description: str,
    trigger_event: str,
    service_base_date: str,
    service_type: str,
    statutory_days: int,
    statutory_basis: str,
    statutory_basis_version: str,
    period_type: str,
    severity: str,
    has_local_agent: int,
    in_transit_days: int,
    court_region: str,
    party_region: str,
    buffer_days: int,
    assignee: str,
    assignee_line_user_id: str,
    escalation_lead_days: str,
    created_by: str,
) -> str:
    """建立時限。天數一律由 shared.deadlines.compute_deadline 確定性計算落欄。

    若 type 在 STATUTORY_PERIODS 種子內、且未自帶 statutory_days/basis/period_type → 自動回填。
    """
    # ── 種子回填（未自帶時）──
    seed = STATUTORY_PERIODS.get(type)
    if seed:
        if not statutory_days:
            statutory_days = seed["statutory_days"]
        if not statutory_basis:
            statutory_basis = seed["statutory_basis"]
        if not statutory_basis_version:
            statutory_basis_version = seed["statutory_basis_version"]
        if not period_type:
            period_type = seed["period_type"]
        if not description:
            description = seed["label"]

    # ── 必填驗證（反捏造：缺法條依據直接擋）──
    if not period_type:
        return "ERROR: period_type 不可為空（peremptory/statutory/court_set/directory）"
    if period_type not in _PERIOD_TYPE_VALID:
        return f"ERROR: period_type 必須是 {', '.join(_PERIOD_TYPE_VALID)}"
    if not statutory_basis or not statutory_basis.strip():
        return (
            "ERROR: statutory_basis（法條依據）不可為空——反捏造鐵律，每個法定天數都要有依據。"
            f"未知 type='{type}' 請手動帶 statutory_days + statutory_basis"
        )
    if not statutory_days:
        return f"ERROR: statutory_days（法定日數）不可為 0/空（type='{type}' 不在種子表、請手動帶）"
    if not service_base_date:
        return "ERROR: service_base_date（送達/寄存/公告基準日 YYYY-MM-DD）不可為空"
    if not trigger_event:
        return "ERROR: trigger_event（起算事件）不可為空"
    if not description:
        return "ERROR: description（時限描述）不可為空"
    svc = service_type or "normal"
    sev = severity or default_severity(period_type)

    from shared.floor_policy import is_full_access

    with transaction() as db:
        matter = repository.get_matter(db, matter_id)
        if not matter:
            return f"ERROR: 找不到案件 #{matter_id}"

        # 機密軸（寫入端 gate）：機密案件非全權限層不可建時限（同 get_matter 讀取 gate 訊息風格、
        # migration 006 / query_knowledge pattern）。受限層連母案件都看不到、不該對它寫入或回內容。
        if matter["confidential"] and not is_full_access():
            return f"ERROR: 案件 #{matter_id} 為機密案件，本層無權限檢視"

        # has_local_agent：未明確指定（傳 -1）→ 沿用 matter 的設定
        if has_local_agent < 0:
            hla = bool(matter["has_local_agent"])
        else:
            hla = bool(has_local_agent)

        # ── 核心：確定性計算（讀同一 db 連線查 office_calendar / 在途）──
        # court_region / party_region：無當地代理人（has_local_agent=False）且未手動指定 in_transit_days
        # 時，compute_deadline 用這兩個區域代碼查 transit_period 表（民訴§162）。查得到→在途天數命中、
        # 查不到→needs_manual_review + 在途暫 0（fail-toward）。有代理人或手動指定在途時這兩值不影響計算。
        result = compute_deadline(
            period_type=period_type,
            statutory_days=int(statutory_days),
            statutory_basis=statutory_basis,
            service_type=svc,
            service_base_date=service_base_date,
            has_local_agent=hla,
            court_region=court_region or "",
            party_region=party_region or "",
            in_transit_days_override=(in_transit_days if in_transit_days else None),
            buffer_days=buffer_days if buffer_days >= 0 else 1,
            db=db,
        )
        if "error" in result:
            return f"ERROR: 計算失敗 — {result['error']}"

        # ── escalation_lead_days：未指定 → 依 severity 預設 ──
        if escalation_lead_days:
            try:
                lead = json.loads(escalation_lead_days)
                if not isinstance(lead, list):
                    lead = default_lead_days(sev)
            except (json.JSONDecodeError, TypeError):
                lead = default_lead_days(sev)
        else:
            lead = default_lead_days(sev)

        fields = {
            "matter_id": matter_id,
            "type": type or "custom",
            "description": description,
            "period_type": period_type,
            "severity": sev,
            "trigger_event": trigger_event,
            "service_type": svc,
            "service_base_date": service_base_date,
            "statutory_days": int(statutory_days),
            "statutory_basis": statutory_basis,
            "statutory_basis_version": statutory_basis_version or None,
            "in_transit_days": result["in_transit_days"],
            "in_transit_source": result["in_transit_source"],
            "effective_date": result["effective_date"],
            "start_date": result["start_date"],
            "statutory_deadline": result["statutory_deadline"],
            "buffer_days": result["buffer_days"],
            "internal_deadline": result["internal_deadline"],
            "calc_trace": json.dumps(result["calc_trace"], ensure_ascii=False),
            "needs_manual_review": 1 if result["needs_manual_review"] else 0,
            "status": "pending",
            "assignee": assignee or (matter["lead_attorney"] or None),
            "assignee_line_user_id": assignee_line_user_id or None,
            "escalation_lead_days": json.dumps(lead),
            "reminders_sent": "[]",
            "recovery_window": json.dumps(result["recovery_window"], ensure_ascii=False),
            "business_unit": None,
        }
        deadline_id = repository.insert_deadline(db, fields)
        repository.insert_interaction_log(
            db,
            actor=created_by or "system",
            action="deadline_created",
            target_type="deadline",
            target_id=deadline_id,
            detail=f"{description} 內部{result['internal_deadline']} 法定{result['statutory_deadline']}",
            business_unit=None,
        )

    review = "\n[需人工複核] 送達/在途含不確定因素，請律師確認後再倚賴本期限。" if result["needs_manual_review"] else ""
    return (
        f"時限 #{deadline_id} 已建立：{description}\n"
        f"- 內部期限（盯這個）：{result['internal_deadline']}\n"
        f"- 法定期限（底線）：{result['statutory_deadline']}（{statutory_basis}）\n"
        f"- 緩衝：{result['buffer_days']} 天\n"
        f"- 計算軌跡：\n  " + "\n  ".join(result["calc_trace"])
        + review
    )


def list_deadlines(matter_id: int, status: str, assignee: str, limit: int) -> str:
    from shared.floor_policy import is_full_access

    db = get_db()
    try:
        rows = repository.list_deadlines(
            db,
            matter_id=matter_id,
            status=status,
            assignee=assignee,
            limit=limit,
            include_confidential=is_full_access(),
        )
        if not rows:
            return "沒有符合條件的時限。"
        lines = [f"## 時限列表（{len(rows)} 筆）"]
        for d in rows:
            st = _DEADLINE_STATUS_ZH.get(d["status"], d["status"])
            review = " [需人工複核]" if d["needs_manual_review"] else ""
            no = d["matter_no"] or f"#{d['matter_id']}"
            lines.append(
                f"- [{st}] [#{d['id']}] {no} {d['description']}："
                f"內部 {d['internal_deadline'] or '?'}（法定 {d['statutory_deadline'] or '?'}"
                f"·{d['statutory_basis']}）{review}"
            )
        return "\n".join(lines)
    finally:
        db.close()


def list_upcoming_deadlines(assignee: str, within_days: int, limit: int) -> str:
    """每日彙整 / 查詢：所有 pending 時限按內部期限升冪（最急在前）。"""
    from shared.floor_policy import is_full_access

    db = get_db()
    try:
        rows = repository.list_upcoming_deadlines(
            db,
            assignee=assignee,
            within_days=within_days,
            limit=limit,
            include_confidential=is_full_access(),
        )
        if not rows:
            scope = f"（{within_days} 天內）" if within_days and within_days > 0 else ""
            return f"目前沒有待處理（pending）的時限{scope}。"
        from datetime import date

        today = date.today().isoformat()
        scope = f"（{within_days} 天內）" if within_days and within_days > 0 else ""
        lines = [f"## 即將到期時限{scope}（{len(rows)} 筆、按內部期限升冪）"]
        for d in rows:
            no = d["matter_no"] or f"#{d['matter_id']}"
            internal = d["internal_deadline"] or "?"
            statutory = d["statutory_deadline"] or "?"
            review = " [需人工複核]" if d["needs_manual_review"] else ""
            sev = _SEVERITY_ZH.get(d["severity"], "")
            sev_tag = f" {sev}" if sev else ""
            # 逾期標示（internal 已過今天）
            overdue = ""
            if d["internal_deadline"] and d["internal_deadline"] < today:
                overdue = " [已逾內部期限]"
            atty = d["assignee"] or d["lead_attorney"] or "未指派"
            lines.append(
                f"- [#{d['id']}] {no} {d['description']}：內部 {internal}"
                f"（法定 {statutory}·{d['statutory_basis']}）→ {atty}{sev_tag}{overdue}{review}"
            )
        return "\n".join(lines)
    finally:
        db.close()


def get_deadline(deadline_id: int) -> str:
    from shared.floor_policy import is_full_access

    db = get_db()
    try:
        d = repository.get_deadline(db, deadline_id)
        if not d:
            return f"ERROR: 找不到時限 #{deadline_id}"
        m = repository.get_matter(db, d["matter_id"])
        # 機密軸：時限隨母案件機密性、機密案件之時限非全權限層不可見
        if m and m["confidential"] and not is_full_access():
            return f"ERROR: 時限 #{deadline_id} 隸屬機密案件，本層無權限檢視"
        matter_str = f"{m['matter_no'] or ''} {m['title']}" if m else f"#{d['matter_id']}（案件已刪除）"

        try:
            trace = json.loads(d["calc_trace"] or "[]")
        except (json.JSONDecodeError, TypeError):
            trace = []
        trace_str = "\n".join(f"  {i+1}. {t}" for i, t in enumerate(trace)) if trace else "  （無）"

        try:
            recovery = json.loads(d["recovery_window"] or "{}")
        except (json.JSONDecodeError, TypeError):
            recovery = {}
        recovery_str = ""
        if recovery:
            recovery_str = (
                f"\n### 逾期救濟備援（{recovery.get('basis', '')}）\n"
                f"- {recovery.get('condition', '')}"
            )

        st = _DEADLINE_STATUS_ZH.get(d["status"], d["status"])
        pt = _PERIOD_TYPE_ZH.get(d["period_type"], d["period_type"])
        svc = _SERVICE_TYPE_ZH.get(d["service_type"], d["service_type"])
        sev = _SEVERITY_ZH.get(d["severity"], d["severity"] or "未分級")
        review = "\n- [需人工複核]：送達/在途含不確定因素、不可全自動倚賴" if d["needs_manual_review"] else ""

        return (
            f"## 時限 #{deadline_id}：{d['description']}\n"
            f"- 所屬案件：{matter_str}（案件 #{d['matter_id']}）\n"
            f"- 類型：{d['type']}\n"
            f"- 期間性質：{pt}（{d['period_type']}）\n"
            f"- 嚴重度：{sev}\n"
            f"- 狀態：{st}\n"
            f"- 起算事件：{d['trigger_event']}\n"
            f"- 送達類型：{svc}\n"
            f"- 送達基準日：{d['service_base_date']}\n"
            f"- 送達生效日：{d['effective_date']}\n"
            f"- 起算日：{d['start_date']}\n"
            f"- 法定日數：{d['statutory_days']} 日（{d['statutory_basis']}"
            f"{('·' + d['statutory_basis_version']) if d['statutory_basis_version'] else ''}）\n"
            f"- 在途：{d['in_transit_days']} 日（{d['in_transit_source'] or '無'}）\n"
            f"- 法定期限（底線，永不退讓）：{d['statutory_deadline']}\n"
            f"- 緩衝：{d['buffer_days']} 天\n"
            f"- 內部期限（盯這個）：{d['internal_deadline']}\n"
            f"- 負責律師：{d['assignee'] or '未指派'}\n"
            f"- 提醒節點：{d['escalation_lead_days']}（已發：{d['reminders_sent']}）\n"
            f"- 遞交：{('已於 ' + d['filed_at'] + ' 由 ' + (d['filed_by'] or '?') + ' 遞交') if d['filed_at'] else '未遞交'}"
            f"{review}\n"
            f"\n### 計算軌跡（律師逐步覆核）\n{trace_str}"
            f"{recovery_str}"
        )
    finally:
        db.close()


def mark_deadline_filed(deadline_id: int, filed_by: str) -> str:
    from shared.floor_policy import is_full_access

    with transaction() as db:
        d = repository.get_deadline(db, deadline_id)
        if not d:
            return f"ERROR: 找不到時限 #{deadline_id}"
        # 機密軸（寫入端 gate）：時限隨母案件機密性。先讀母案件、機密案件之時限非全權限層不可
        # 標遞交（同 get_deadline 讀取 gate 訊息風格）。不執行寫入、不回內容。
        m = repository.get_matter(db, d["matter_id"])
        if m and m["confidential"] and not is_full_access():
            return f"ERROR: 時限 #{deadline_id} 隸屬機密案件，本層無權限檢視"
        if d["status"] != "pending":
            cur_st = _DEADLINE_STATUS_ZH.get(d["status"], d["status"])
            return f"ERROR: 時限 #{deadline_id} 目前狀態為「{cur_st}」、非待處理，無法標記遞交"
        rows = repository.mark_filed(db, deadline_id, _now(), filed_by or None)
        if rows == 0:
            return f"ERROR: 時限 #{deadline_id} 標記遞交失敗（狀態已變動）"
        repository.insert_interaction_log(
            db,
            actor=filed_by or "system",
            action="deadline_filed",
            target_type="deadline",
            target_id=deadline_id,
            detail=f"{d['description']} 已遞交",
            business_unit=None,
        )
    return f"時限 #{deadline_id}（{d['description']}）已標記為已遞交，cron 不再提醒。"
