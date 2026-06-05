"""Deadlines service — 案件（matters）+ 時限（deadlines）業務邏輯。

層次邊界：transaction ownership 在這層，repository 不 commit。
時限天數一律呼叫 shared.deadlines.compute_deadline（純函式、確定性、附 statutory_basis），
service 不做任何天數心算（反捏造鐵律）。calc_trace 落 JSON 欄供律師逐步覆核。

回傳格式：中文 status/type 標籤、不用 emoji；錯誤回 'ERROR: <中文>' 字串（不 raise）。
"""
import json

from shared.auth import _resolve_actor_label
from shared.db import _now, get_db, transaction
from shared.deadlines import (
    STATUTORY_PERIODS,
    compute_deadline,
    court_set_type,
    default_lead_days,
    default_severity,
    limitation_type,
    procedural_calendar_type,
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
# 需人工複核的不確定因素清單（create 回覆 + get_deadline 摘要共用一份、避免 drift，codex R2 LOW）
_REVIEW_FACTORS = "送達/在途/法版/教示比對/裁定期間"


def _period_phrase(period_unit, period_value, statutory_days):
    """期間人話：year→『N 年』、month→『N 月』、day→『N 日』。反捏造：年/月期間絕不顯示成日數
    （消滅時效 15 年若顯示成「15 日」＝把法定值偽裝、codex HIGH-4）。"""
    if period_unit == "year":
        return f"{period_value} 年"
    if period_unit == "month":
        return f"{period_value} 月"
    return f"{statutory_days} 日"


def _writer_or_error(db, actor_in):
    """解析寫入者標籤並 fail-closed（codex 全面審 / 對齊 #10）：floored session 取 line-channel verified
    員工名（忽略 agent 自填）、operator（律所無 floor）用傳入值；floored 但查無 verified LINE 脈絡 →
    _resolve_actor_label 回 '__unverified__' → 拒絕寫入（回 (None, ERROR)）。回 (actor_label, None) 表通過。
    必須在任何 repository 寫入「之前」呼叫——transaction 對 return 字串仍會 commit、寫入後才擋擋不住。"""
    a = _resolve_actor_label(db, actor_in)
    if a == "__unverified__":
        return None, ("ERROR: 無法驗證操作者身份（floored session 查無 verified LINE 脈絡）、"
                      "為防偽造拒絕寫入；請從綁定的 LINE 帳號操作。")
    return a, None


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

        _actor, _err = _writer_or_error(db, created_by)  # fail-closed：未驗證拒寫（對齊 #10）、須在 insert 前
        if _err:
            return _err
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
            actor=_actor or "system",
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
            # 機密軸 + 存在性洩漏防護（codex HIGH-2）：受限層對機密案件回「與不存在相同」的泛化錯誤，
            # 不暴露「該案存在但機密」這一位元（與 not-found 回覆 byte 相同、消除 ID 探測 oracle）。
            return f"ERROR: 找不到案件 #{matter_id}"
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
    stated_period_days: int,
    document_date: str,
    assignee: str,
    assignee_line_user_id: str,
    escalation_lead_days: str,
    created_by: str,
    confirm_intake_id: int = 0,
    period_unit: str = "day",
    period_value: int = 0,
) -> str:
    """建立時限。天數一律由 shared.deadlines.compute_deadline 確定性計算落欄。

    若 type 在 STATUTORY_PERIODS 種子內、且未自帶 statutory_days/basis/period_type → 自動回填。

    confirm_intake_id（#H2）：>0 時，本次入庫成功同 tx 把對應 pending_intakes 待確認暫存標 confirmed
    並連到本時限（關閉「待確認跟催」backlog、不再被 scan_unconfirmed_intake 催）。查無 / 非 awaiting
    不報錯（避免擋下正常入庫），但回覆會註記未對位、供操作者察覺。
    """
    # statutory_days 正規化（反捏造第二道牆，codex R2 MED）：truthiness 檢查會被 "0"/"00" 等字串
    # 繞過（非空字串 truthy）→ 後面 int() 變 0、純函式建出 0 日期間。先一律轉 int：空/壞/負 → 0
    # （代表「未提供」、交由種子回填或必填驗證擋下），確保所有 `if not statutory_days` 判斷正確。
    try:
        statutory_days = int(str(statutory_days).strip()) if str(statutory_days).strip() else 0
    except (TypeError, ValueError):
        statutory_days = 0
    if statutory_days < 0:
        statutory_days = 0
    # period_value 同等正規化（消滅時效年/月期間數）：非數字不可炸 ValueError、要轉成可審計的拒絕（codex R2 MED）
    try:
        period_value = int(str(period_value).strip()) if str(period_value).strip() else 0
    except (TypeError, ValueError):
        period_value = 0
    if period_value < 0:
        period_value = 0

    # ── 固定法定日數種子回填 + 鎖死（codex HIGH：原本只回填不鎖＝可塞假值）──
    # caller 傳的 statutory_days/statutory_basis/period_type 非空且不符 seed → ERROR（否則 appeal_civil
    # 可被塞 15 日 / 假法條＝把人輸入偽裝成可辯護法定值）。caller 只能留空讓系統回填。
    # statutory_basis_version（版本註記）/ description（顯示）不影響計算、仍允許覆寫。
    seed = STATUTORY_PERIODS.get(type)
    if seed:
        if statutory_days and statutory_days != seed["statutory_days"]:
            return (
                f"ERROR: {seed['label']}（{type}）法定日數為 {seed['statutory_days']} 日"
                f"（{seed['statutory_basis']}）、不可改為 {statutory_days}——法定固定值（反捏造），留空自動帶即可。"
            )
        if statutory_basis and statutory_basis.strip() and statutory_basis.strip() != seed["statutory_basis"]:
            return (
                f"ERROR: {seed['label']}（{type}）的 statutory_basis 為 {seed['statutory_basis']}、"
                f"不可改為 '{statutory_basis}'——法定依據固定，留空自動帶即可。"
            )
        if period_type and period_type != seed["period_type"]:
            return (
                f"ERROR: {seed['label']}（{type}）的 period_type 為 {seed['period_type']}、"
                f"不可改為 '{period_type}'——法定期間性質固定，留空自動帶即可。"
            )
        statutory_days = seed["statutory_days"]
        statutory_basis = seed["statutory_basis"]
        period_type = seed["period_type"]
        if not statutory_basis_version:
            statutory_basis_version = seed["statutory_basis_version"]
        if not description:
            description = seed["label"]

    # ── 裁定期間類回填（court_set，如限期補正）：與固定天數種子分開 ──
    # 只回填「非天數」欄（period_type/severity/描述/觸發語）；天數絕不回填——裁定期間是法院當下
    # 載明、律師必讀裁定填（反捏造：漏補正＝駁回起訴）。缺天數/依據時給「讀裁定」的具體指引，
    # 而非泛化擋下（針對性 UX）。force_review 在 period_type 定案後另算（見下），不論是否登記本表。
    cs_seed = court_set_type(type)
    if cs_seed:
        # 已知裁定期間類 type 的法律性質固定為 court_set，不容 caller 改標成別的 period_type
        # （否則 correction 被標 peremptory/statutory → compute 不走 court_set 分支、錯加在途、
        # 且 force_review 失效＝法律性質錯置 + 繞過強制複核，codex HIGH）。只補空不夠、要校驗一致。
        if period_type and period_type != cs_seed["period_type"]:
            return (
                f"ERROR: {cs_seed['label']}的 period_type 必為 {cs_seed['period_type']}（裁定期間）、"
                f"不可指定為 '{period_type}'——裁定期間的法律性質固定，留空自動帶即可。"
            )
        if not period_type:
            period_type = cs_seed["period_type"]
        if not severity:
            severity = cs_seed["severity"]
        if not description:
            description = cs_seed["label"]
        if not trigger_event:
            trigger_event = cs_seed["default_trigger"]
        if not statutory_days:
            return (
                f"ERROR: {cs_seed['label']}的補正期間日數（statutory_days）須讀裁定填寫"
                "——裁定期間非法定固定值、引擎不臆測不預設（反捏造：漏補正＝駁回起訴）。"
                "請看裁定主文「於本裁定送達後 ○ 日內補正」填入 ○ 日。"
            )
        if not statutory_basis or not statutory_basis.strip():
            return (
                f"ERROR: {cs_seed['label']}的 statutory_basis 請填{cs_seed['basis_hint']}"
                "——裁定期間的依據是該紙裁定本身、非法條。"
            )

    # ── 消滅時效類回填（limitation，period_unit=year/month）：與日數/裁定期間都不同 ──
    # 期間是年/月（用 period_value 非 statutory_days）、起算點是民§128「請求權可行使時」＝法律判斷
    # → 一律強制人工複核（force_review、見下）、起算日由律師輸入。period_type 固定（statutory）、不容改標。
    lim_seed = limitation_type(type)
    if lim_seed:
        # seed 鎖死法律性質（period_type/period_unit/period_value）——caller 只能留空讓系統回填，
        # 非空且不符 seed 一律 ERROR（否則 statute_125 可被改成 15 個月、或標 peremptory＝法律性質
        # 錯置、把消滅時效偷換成別的期間，codex HIGH-1/2）。
        if period_type and period_type != lim_seed["period_type"]:
            return (
                f"ERROR: {lim_seed['label']}的 period_type 必為 {lim_seed['period_type']}、"
                f"不可指定為 '{period_type}'——消滅時效法律性質固定，留空自動帶即可。"
            )
        if period_unit and period_unit != "day" and period_unit != lim_seed["period_unit"]:
            return (
                f"ERROR: {lim_seed['label']}的 period_unit 必為 {lim_seed['period_unit']}、"
                f"不可指定為 '{period_unit}'——消滅時效期間單位固定，留空自動帶即可。"
            )
        if period_value and int(period_value) != lim_seed["period_value"]:
            return (
                f"ERROR: {lim_seed['label']}的期間為 {lim_seed['period_value']} "
                f"{lim_seed['period_unit']}、不可改為 {period_value}——法定時效期間固定（反捏造），"
                "留空自動帶即可。"
            )
        if not severity:
            severity = lim_seed["severity"]
        if not description:
            description = lim_seed["label"]
        if not statutory_basis:
            statutory_basis = lim_seed["statutory_basis"]
        if not statutory_basis_version:
            statutory_basis_version = lim_seed["statutory_basis_version"]
        period_type = lim_seed["period_type"]      # 強制鎖死
        period_unit = lim_seed["period_unit"]      # 強制鎖死
        period_value = lim_seed["period_value"]    # 強制鎖死

    # ── 程序月/年期間回填（procedural_calendar，如行訴§106）：與消滅時效都是「月/年」但 regime 不同 ──
    # 走程序機制（送達/在途/§122 順延、起算用送達日這個確定事實）→ counting_regime='procedural'（見下）、
    # 不強制人工複核（這正是相對消滅時效可確定性自動算之處）。period_type 多為 peremptory（不變期間）、
    # 非 statutory——故與消滅時效鎖分流。seed 鎖死法律性質（period_type/unit/value）、caller 只能留空回填。
    pc_seed = procedural_calendar_type(type)
    if pc_seed:
        if period_type and period_type != pc_seed["period_type"]:
            return (
                f"ERROR: {pc_seed['label']}的 period_type 必為 {pc_seed['period_type']}、"
                f"不可指定為 '{period_type}'——法定期間性質固定，留空自動帶即可。"
            )
        if period_unit and period_unit != "day" and period_unit != pc_seed["period_unit"]:
            return (
                f"ERROR: {pc_seed['label']}的 period_unit 必為 {pc_seed['period_unit']}、"
                f"不可指定為 '{period_unit}'——期間單位固定，留空自動帶即可。"
            )
        if period_value and int(period_value) != pc_seed["period_value"]:
            return (
                f"ERROR: {pc_seed['label']}的期間為 {pc_seed['period_value']} {pc_seed['period_unit']}、"
                f"不可改為 {period_value}——法定期間固定（反捏造），留空自動帶即可。"
            )
        if not severity:
            severity = pc_seed["severity"]
        if not description:
            description = pc_seed["label"]
        if not statutory_basis:
            statutory_basis = pc_seed["statutory_basis"]
        if not statutory_basis_version:
            statutory_basis_version = pc_seed["statutory_basis_version"]
        if not trigger_event:
            trigger_event = pc_seed["default_trigger"]
        period_type = pc_seed["period_type"]       # 強制鎖死
        period_unit = pc_seed["period_unit"]       # 強制鎖死
        period_value = pc_seed["period_value"]     # 強制鎖死

    # generic type='limitation'：必須走年/月路徑、不可 day-bypass（否則消滅時效被當日數算成 N 日）
    if type == "limitation" and period_unit not in ("year", "month"):
        return (
            "ERROR: 消滅時效（type='limitation'）必須指定 period_unit='year'/'month' + period_value"
            "（民§121 曆法；§125=15年、§126=5年、§127·§197=2年），不可走日數路徑。"
        )

    # 年/月曆法分支的法律性質鎖（綁 period_unit、非 type 字面——codex+workflow 同根因：原鎖只綁
    # type=='limitation'，任意 type 或 STATUTORY/COURT_SET 種子 + period_unit=year 可繞過 → 把 15 年
    # 時效標成 directory/grey 降級提醒、或把 appeal_civil 算成多年並令 calc_trace 謊稱§128）：
    #   (a) 日數/裁定種子 type 不可指定年/月（其法律性質非月/年期間）；
    #   (b) 泛型年/月（無 pc_seed）＝消滅時效 → period_type 一律強制 statutory（caller 傳非 statutory → ERROR）；
    #   (c) 程序月期間種子（pc_seed，如行訴§106）已各自鎖好 period_type（多為 peremptory 不變期間）、不在此覆寫。
    if period_unit in ("year", "month"):
        if seed:
            return (
                f"ERROR: type='{type}' 是固定日數法定期間種子、不可指定 period_unit='{period_unit}'"
                "（年/月曆法僅適用消滅時效 type=limitation / statute_*、或程序月期間種子如 admin_revocation）。"
            )
        if cs_seed:
            return (
                f"ERROR: type='{type}' 是裁定期間種子、不可指定 period_unit='{period_unit}'"
                "（年/月曆法僅適用消滅時效 type=limitation / statute_*、或程序月期間種子如 admin_revocation）。"
            )
        if not pc_seed:
            # 無程序月期間種子＝視為消滅時效（保留既有行為）→ 強制 statutory
            if period_type and period_type != "statutory":
                return (
                    f"ERROR: 年/月期間（period_unit='{period_unit}'）的 period_type 必為 statutory、"
                    f"不可指定為 '{period_type}'——消滅時效是法定期間（非不變期間/訓示）、法律性質固定。"
                    "（程序月期間如行訴§106 請用已登記的種子 type=admin_revocation）"
                )
            period_type = "statutory"

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
    # 兩條正交軸：_is_calendar（年/月、用 period_value）vs counting_regime（限定誰是消滅時效）。
    # 消滅時效 = 年/月 且非程序月期間種子（pc_seed）；程序月期間（行訴§106）= 年/月 + procedural。
    # 機制閉合性（codex 全面審 finding#2）：非 pc_seed 的年/月一律歸 limitation＝保留既有行為，「不會誤算」
    # 因上方年/月鎖已對「無 pc_seed + period_type!=statutory（如想自建不變期間月期間）」直接 ERROR 擋下；
    # 故未登記 seed 的『程序』月期間不可能靜默走進來——要新增此類期間必須先登 PROCEDURAL_CALENDAR_PERIODS 種子。
    _is_calendar = period_unit in ("year", "month")
    _is_limitation = _is_calendar and not pc_seed
    counting_regime = "limitation" if _is_limitation else "procedural"
    if _is_calendar:
        if not period_value or int(period_value) <= 0:
            return (
                f"ERROR: 年/月期間數（period_value）必須 > 0"
                f"（type='{type}'、period_unit='{period_unit}'；消滅時效§125=15/§126=5/§127·§197=2、行訴§106=2月）"
            )
    elif not statutory_days:
        return f"ERROR: statutory_days（法定日數）不可為 0/空（type='{type}' 不在種子表、請手動帶）"
    if not service_base_date:
        return "ERROR: service_base_date（送達/寄存/公告基準日 YYYY-MM-DD）不可為空"
    if not trigger_event:
        return "ERROR: trigger_event（起算事件）不可為空"
    if not description:
        return "ERROR: description（時限描述）不可為空"
    svc = service_type or "normal"
    if _is_limitation:
        svc = "normal"  # 消滅時效無送達加算（民§128 直接起算）→ 強制 normal、避免 service_type 落欄誤導
        # 注意：程序月期間（行訴§106）仍有送達（訴願決定書送達）→ 不強制 normal、保留 caller 的 service_type
    sev = severity or default_severity(period_type)
    # 裁定期間（court_set）天數純由律師讀裁定填、無固定法定種子可交叉驗證＝反捏造
    # 風險最高一類 → 強制人工複核（不論 type 是否登記在 COURT_SET_PERIODS、只看最終 period_type）。
    # 律師覆核後走 mark_deadline_reviewed（#6，未實作）清旗標；MVP 一律標、不給關閉選項。
    # 消滅時效（limitation）起算點是民§128「請求權可行使時」＝法律判斷 → 一律強制複核。
    # 程序月期間（行訴§106、_is_calendar 但非 limitation）起算用送達日這個確定事實 → 不在此強制複核
    #（仍會因引擎內送達/在途/教示等不確定因素而個案標複核）。
    force_review = (period_type == "court_set") or _is_limitation

    from shared.floor_policy import is_full_access

    with transaction() as db:
        matter = repository.get_matter(db, matter_id)
        if not matter:
            return f"ERROR: 找不到案件 #{matter_id}"

        # 機密軸（寫入端 gate）：機密案件非全權限層不可建時限（同 get_matter 讀取 gate 訊息風格、
        # migration 006 / query_knowledge pattern）。受限層連母案件都看不到、不該對它寫入或回內容。
        if matter["confidential"] and not is_full_access():
            # 機密軸 + 存在性洩漏防護（codex HIGH-2）：受限層對機密案件回「與不存在相同」的泛化錯誤，
            # 不暴露「該案存在但機密」這一位元（與 not-found 回覆 byte 相同、消除 ID 探測 oracle）。
            return f"ERROR: 找不到案件 #{matter_id}"

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
            stated_period_days=(stated_period_days if stated_period_days else None),
            document_date=document_date or "",
            period_unit=period_unit,
            period_value=period_value,
            counting_regime=counting_regime,
            db=db,
        )
        if "error" in result:
            return f"ERROR: 計算失敗 — {result['error']}"

        # 裁定期間強制複核：calc_trace 留一筆「為何標複核」，供律師覆核卡（#6）/get_deadline 看到。
        # 一律 append（與 compute 內因送達/法版/教示標的 review 是各自獨立的理由、可並存）。
        # court_set（裁定期間，含限期補正）的強制複核理由在此補一筆中性 trace；消滅時效（year/month）的
        # 強制複核理由已由 compute 內 §121/§128 trace 充分說明、不在此重複加 court_set 文字（codex MED）。
        if force_review and period_type == "court_set":
            result["calc_trace"].append(
                f"裁定所定期間（court_set）：期間 {int(statutory_days)} 日由人工讀裁定/法院文書填寫、"
                f"非法定固定值（依據 {statutory_basis}）→ 強制人工複核"
                "（無固定法定種子可交叉驗證，反捏造）"
            )

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
            "statutory_days": result["statutory_days"],
            "period_unit": result.get("period_unit", "day"),
            "period_value": result.get("period_value"),
            "statutory_basis": statutory_basis,
            "statutory_basis_version": statutory_basis_version or None,
            "in_transit_days": result["in_transit_days"],
            "in_transit_source": result["in_transit_source"],
            "effective_date": result["effective_date"],
            "start_date": result["start_date"],
            "statutory_deadline": result["statutory_deadline"],
            "buffer_days": result["buffer_days"],
            "internal_deadline": result["internal_deadline"],
            "stated_period_days": result["stated_period_days"],
            "document_date": document_date or None,
            "calc_trace": json.dumps(result["calc_trace"], ensure_ascii=False),
            "needs_manual_review": 1 if (result["needs_manual_review"] or force_review) else 0,
            "status": "pending",
            "assignee": assignee or (matter["lead_attorney"] or None),
            "assignee_line_user_id": assignee_line_user_id or None,
            "escalation_lead_days": json.dumps(lead),
            "reminders_sent": "[]",
            "recovery_window": json.dumps(result["recovery_window"], ensure_ascii=False),
            "business_unit": None,
        }
        _actor, _err = _writer_or_error(db, created_by)  # fail-closed：未驗證拒寫（對齊 #10）、須在 insert 前
        if _err:
            return _err
        deadline_id = repository.insert_deadline(db, fields)
        repository.insert_interaction_log(
            db,
            actor=_actor or "system",
            action="deadline_created",
            target_type="deadline",
            target_id=deadline_id,
            detail=f"{description} 內部{result['internal_deadline']} 法定{result['statutory_deadline']}",
            business_unit=None,
        )

        # #H2：關閉「待確認跟催」backlog（同 tx）。先驗可見性 + 同案對位（codex#H 高）：
        # 受限層不可藉「公開案件建 deadline + 猜 intake id」關掉機密 intake（anti-oracle），
        # 也不可把別案的暫存錯連到本時限（resolved_deadline_id 完整性）。所有「未對位」情形
        # （查無 / 機密不可見 / 屬他案 / 已非待確認）回 byte 相同的 _NOMATCH、不動任何 row
        # ——成功路徑只在「可見 + 同案(或未建案的 NULL→本案) + awaiting」時發生，故機密 intake
        # 對受限層永不產生「成功」回覆＝無存在性 oracle。查無/未對位都不擋入庫（時限本身已建好）。
        intake_note = ""
        if confirm_intake_id:
            _NOMATCH = (
                f"\n（注意：待確認暫存 #{confirm_intake_id} 未對位；時限本身已建立，"
                f"請用 list_pending_intakes 核對 backlog）"
            )
            intake = repository.get_pending_intake(db, confirm_intake_id)
            if (not intake) or (intake["matter_confidential"] and not is_full_access()):
                intake_note = _NOMATCH  # 查無 / 機密不可見：同一則回覆、消除存在性 oracle
            elif intake["matter_id"] is not None and intake["matter_id"] != matter_id:
                intake_note = _NOMATCH  # 屬其他案件：不跨案連結
            elif intake["status"] != "awaiting":
                intake_note = _NOMATCH  # 已非待確認：不重複關閉
            else:
                closed = repository.resolve_pending_intake(
                    db,
                    intake_id=confirm_intake_id,
                    status="confirmed",
                    resolved_at=_now(),
                    resolved_by=_actor or "system",
                    resolved_deadline_id=deadline_id,
                )
                intake_note = (
                    f"\n（已確認入庫待確認暫存 #{confirm_intake_id}、跟催關閉）"
                    if closed else _NOMATCH
                )

    review = f"\n[需人工複核] 含不確定因素（{_REVIEW_FACTORS}之一），請律師確認後再倚賴本期限。" if (result["needs_manual_review"] or force_review) else ""
    # §197 雙時鐘提醒（不自動雙建、但提示另一本時鐘別漏，codex MED-5）
    sibling_note = ""
    if type == "statute_197_2y":
        sibling_note = "\n（§197 雙時鐘：另一本「自侵權行為時起10年」statute_197_10y 若尚未建請補、起算日填行為日；兩者先到者時效完成）"
    elif type == "statute_197_10y":
        sibling_note = "\n（§197 雙時鐘：另一本「知有損害及賠償義務人時起2年」statute_197_2y 若尚未建請補、起算日填知悉日；兩者先到者時效完成）"
    elif type == "admin_revocation":
        sibling_note = (
            "\n（行訴§106 提醒：①另注意「自訴願決定書送達後逾3年不得提起」之長期失權（另立時鐘、本筆未建）；"
            "②若為訴願人以外之利害關係人、起算改「自知悉時」＝法律判斷、請改填知悉日並人工複核；"
            "③不經訴願程序者依§106Ⅲ「自行政處分達到/公告後2個月」、起算事件不同、請另建並改 trigger）"
        )
    elif type == "provisional_litigation":
        sibling_note = (
            "\n（保全命起訴：期間以命起訴裁定主文所定為準、已強制人工複核；逾期未起訴債務人得聲請撤銷保全裁定·"
            "§529Ⅳ/§533。另注意特例§529Ⅲ：基於夫妻剩餘財產差額分配請求權之假扣押，應於宣告改用分別財產制"
            "『裁定確定之日』起10日內起訴——起算點為『裁定確定』非送達、亦走本 court_set 路徑由律師讀裁定手填10日）"
        )
    # 期間人話（反捏造：年/月不顯示成日）
    _ph = _period_phrase(period_unit, period_value, result["statutory_days"])
    return (
        f"時限 #{deadline_id} 已建立：{description}（期間 {_ph}）\n"
        f"- 內部期限（盯這個）：{result['internal_deadline']}\n"
        f"- 法定期限（底線）：{result['statutory_deadline']}（{statutory_basis}）\n"
        f"- 緩衝：{result['buffer_days']} 天\n"
        f"- 計算軌跡：\n  " + "\n  ".join(result["calc_trace"])
        + review
        + sibling_note
        + intake_note
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
            # 機密軸 + 存在性洩漏防護（codex HIGH-2）：受限層對機密時限回「與不存在相同」的泛化錯誤，
            # 不暴露「該時限存在但機密」這一位元（與 not-found 回覆 byte 相同、消除 ID 探測 oracle）。
            return f"ERROR: 找不到時限 #{deadline_id}"
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
        review = f"\n- [需人工複核]：含不確定因素（{_REVIEW_FACTORS}）、不可全自動倚賴" if d["needs_manual_review"] else ""

        # 教示比對（安全網）：有抓判決書教示天數才顯示是否與引擎相符。
        # 單位 aware（反捏造）：年/月期間比 period_value（同單位）、日期間比 statutory_days。
        stated = d["stated_period_days"]
        if stated is None:
            stated_str = ""
        else:
            _pu = d["period_unit"] or "day"
            _tgt = d["period_value"] if _pu in ("year", "month") else d["statutory_days"]
            _u = "個月" if _pu == "month" else ("年" if _pu == "year" else "日")
            if stated == _tgt:
                stated_str = f"\n- 判決書教示：{stated} {_u}（與引擎採用 {_tgt} {_u}相符）"
            else:
                stated_str = (
                    f"\n- 判決書教示：{stated} {_u}（與引擎採用 {_tgt} {_u}"
                    f"【不符，已標複核】）"
                )
        # 行事曆同步（SPEC「寫兩處」）
        if d["calendar_event_id"]:
            cal_str = (
                f"\n- 行事曆同步：已同步"
                f"（{d['calendar_provider'] or '行事曆'}:{d['calendar_event_id']}"
                f"{('@' + d['calendar_synced_at']) if d['calendar_synced_at'] else ''}）"
            )
        else:
            cal_str = "\n- 行事曆同步：未同步"

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
            f"- 文書作成日（法版檢核基準）：{d['document_date'] or '未提供（以送達日近似）'}\n"
            f"- 送達生效日：{d['effective_date']}\n"
            f"- 起算日：{d['start_date']}\n"
            f"- 法定期間：{_period_phrase(d['period_unit'], d['period_value'], d['statutory_days'])}（{d['statutory_basis']}"
            f"{('·' + d['statutory_basis_version']) if d['statutory_basis_version'] else ''}）"
            f"{stated_str}\n"
            f"- 在途：{d['in_transit_days']} 日（{d['in_transit_source'] or '無'}）\n"
            f"- 法定期限（底線，永不退讓）：{d['statutory_deadline']}\n"
            f"- 緩衝：{d['buffer_days']} 天\n"
            f"- 內部期限（盯這個）：{d['internal_deadline']}{cal_str}\n"
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
            # 機密軸 + 存在性洩漏防護（codex HIGH-2）：受限層對機密時限回「與不存在相同」的泛化錯誤，
            # 不暴露「該時限存在但機密」這一位元（與 not-found 回覆 byte 相同、消除 ID 探測 oracle）。
            return f"ERROR: 找不到時限 #{deadline_id}"
        if d["status"] != "pending":
            cur_st = _DEADLINE_STATUS_ZH.get(d["status"], d["status"])
            return f"ERROR: 時限 #{deadline_id} 目前狀態為「{cur_st}」、非待處理，無法標記遞交"
        # actor 具名 + 防偽造（codex HIGH / 對齊 #10）：floored session 取 line-channel verified 員工名、
        # 忽略 agent 自填的 filed_by；operator（律所無 floor）用傳入值。標遞交會關掉 cron 倒數、且遞交人
        # 寫進 deadlines.filed_by 與 interaction_log，不可盲信任意字串。
        _actor, _err = _writer_or_error(db, filed_by)
        if _err:
            return _err
        rows = repository.mark_filed(db, deadline_id, _now(), _actor or None)
        if rows == 0:
            return f"ERROR: 時限 #{deadline_id} 標記遞交失敗（狀態已變動）"
        repository.insert_interaction_log(
            db,
            actor=_actor or "system",
            action="deadline_filed",
            target_type="deadline",
            target_id=deadline_id,
            detail=f"{d['description']} 已遞交",
            business_unit=None,
        )
    return f"時限 #{deadline_id}（{d['description']}）已標記為已遞交，cron 不再提醒。"


def mark_deadline_calendared(
    deadline_id: int, calendar_event_id: str, calendar_provider: str, marked_by: str
) -> str:
    """落回外部行事曆 event_id（SPEC『寫兩處』：時限確認後寫進事務所慣用行事曆 MCP，回填 event_id）。

    calendar-agnostic：agent 用現場配置的行事曆 MCP（Google 或其他）建好 event 後，把回傳的
    event_id 用本 tool 存回，供每日彙整去重 / 後續更新對位。不綁死特定行事曆軟體。
    """
    if not calendar_event_id or not calendar_event_id.strip():
        return "ERROR: calendar_event_id（外部行事曆 event id）不可為空"

    from shared.floor_policy import is_full_access

    with transaction() as db:
        d = repository.get_deadline(db, deadline_id)
        if not d:
            return f"ERROR: 找不到時限 #{deadline_id}"
        # 機密軸（寫入端 gate）：時限隨母案件機密性，機密案件之時限非全權限層不可回填行事曆對位
        # （同 mark_deadline_filed gate 風格）。
        m = repository.get_matter(db, d["matter_id"])
        if m and m["confidential"] and not is_full_access():
            # 機密軸 + 存在性洩漏防護（codex HIGH-2）：受限層對機密時限回「與不存在相同」的泛化錯誤，
            # 不暴露「該時限存在但機密」這一位元（與 not-found 回覆 byte 相同、消除 ID 探測 oracle）。
            return f"ERROR: 找不到時限 #{deadline_id}"
        _actor, _err = _writer_or_error(db, marked_by)  # fail-closed：未驗證拒寫（對齊 #10）、須在寫入前
        if _err:
            return _err
        rows = repository.mark_calendared(
            db, deadline_id, calendar_event_id.strip(), calendar_provider or None, _now()
        )
        if rows == 0:
            return f"ERROR: 時限 #{deadline_id} 回填行事曆對位失敗"
        repository.insert_interaction_log(
            db,
            actor=_actor or "system",
            action="deadline_calendared",
            target_type="deadline",
            target_id=deadline_id,
            detail=f"{d['description']} 已同步行事曆（{calendar_provider or '?'}:{calendar_event_id.strip()}）",
            business_unit=None,
        )
    return (
        f"時限 #{deadline_id}（{d['description']}）已回填行事曆對位"
        f"（{calendar_provider or '行事曆'}:{calendar_event_id.strip()}）。"
    )


# ───────────────────────── pending_intakes（#H2 待確認跟催）─────────────────────────

def stage_deadline_intake(
    matter_id: int,
    matter_label: str,
    doc_type: str,
    service_base_date: str,
    stated_period_days: int,
    document_date: str,
    extracted_summary: str,
    submitted_by: str,
) -> str:
    """把『抽出但尚未確認』的時限事實暫存成可掃描的待確認 row（核心 loop 步驟2：推回 LINE 請人
    一鍵確認的當下呼叫）。只存事實、不算天數、不建 deadline——確認後才走 create_deadline。

    補 HITL 結構盲區：讓「人忘了回確認」變成 scan_unconfirmed_intake.py 能跟催的 backlog、不再隱形漏掉。
    確認入庫請帶 create_deadline(confirm_intake_id=<本 id>) 自動關閉跟催；確定不算了用
    resolve_deadline_intake(id, action='discarded')。
    """
    if not extracted_summary or not extracted_summary.strip():
        return "ERROR: extracted_summary（一行人話摘要）不可為空"

    from shared.floor_policy import is_full_access

    with transaction() as db:
        mid = matter_id if matter_id else None
        if mid:
            m = repository.get_matter(db, mid)
            if not m:
                return f"ERROR: 找不到案件 #{matter_id}"
            # 機密軸 + 存在性洩漏防護（codex HIGH-2）：機密案件對非全權限層回「與不存在相同」的泛化錯誤
            if m["confidential"] and not is_full_access():
                return f"ERROR: 找不到案件 #{matter_id}"
        # actor 具名 + 防偽造 fail-closed（對齊 #10）：floored 取 verified 員工名、operator 用傳入丟件人
        _actor_stage, _err = _writer_or_error(db, submitted_by)
        if _err:
            return _err
        fields = {
            "matter_id": mid,
            "matter_label": (matter_label or "").strip() or None,
            "doc_type": (doc_type or "").strip() or None,
            "service_base_date": (service_base_date or "").strip() or None,
            "stated_period_days": (stated_period_days if stated_period_days else None),
            "document_date": (document_date or "").strip() or None,
            "extracted_summary": extracted_summary.strip(),
            "submitted_by": _actor_stage or None,
            "status": "awaiting",
            "reminders_sent": "[]",
        }
        intake_id = repository.insert_pending_intake(db, fields)
        repository.insert_interaction_log(
            db,
            actor=_actor_stage or "system",
            action="intake_staged",
            target_type="pending_intake",
            target_id=intake_id,
            detail=extracted_summary.strip(),
            business_unit=None,
        )
    return (
        f"待確認暫存 #{intake_id} 已建立（尚未入庫、未計算任何期限）。\n"
        f"- 摘要：{extracted_summary.strip()}\n"
        f"請人確認後呼叫 create_deadline(..., confirm_intake_id={intake_id}) 入庫並算雙日期，"
        f"或 resolve_deadline_intake({intake_id}, action='discarded') 標示不算。\n"
        f"（逾時未確認 scan_unconfirmed_intake.py 會主動跟催、不會靜默漏掉）"
    )


def resolve_deadline_intake(intake_id: int, action: str, note: str, resolved_by: str) -> str:
    """收掉待確認暫存：action='discarded'（不算了 / 誤判 / 重複）或 'confirmed'（已另行入庫）。
    一般確認入庫請改走 create_deadline(confirm_intake_id=...) 自動關閉；本函式給「不入庫就收掉」用。"""
    act = (action or "").strip().lower()
    if act not in ("discarded", "confirmed"):
        return "ERROR: action 必須是 'discarded'（不算了）或 'confirmed'（已另行入庫）"

    from shared.floor_policy import is_full_access

    with transaction() as db:
        intake = repository.get_pending_intake(db, intake_id)
        if not intake:
            return f"ERROR: 找不到待確認暫存 #{intake_id}"
        # 機密軸：暫存隨母案件機密性（matter_id 為 NULL=未建案、視為非機密、可收）
        if intake["matter_confidential"] and not is_full_access():
            return f"ERROR: 找不到待確認暫存 #{intake_id}"
        _actor, _err = _writer_or_error(db, resolved_by)  # fail-closed：未驗證拒寫（對齊 #10）
        if _err:
            return _err
        rows = repository.resolve_pending_intake(
            db,
            intake_id=intake_id,
            status=act,
            resolved_at=_now(),
            resolved_by=_actor or None,
            resolved_deadline_id=None,
        )
        if rows == 0:
            cur = intake["status"]
            return f"ERROR: 待確認暫存 #{intake_id} 目前狀態為「{cur}」、非待確認，無法收掉"
        repository.insert_interaction_log(
            db,
            actor=_actor or "system",
            action=f"intake_{act}",
            target_type="pending_intake",
            target_id=intake_id,
            detail=(note or intake["extracted_summary"] or ""),
            business_unit=None,
        )
    zh = {"discarded": "已標示不算（捨棄）", "confirmed": "已標示確認（另行入庫）"}[act]
    return f"待確認暫存 #{intake_id} {zh}，scan_unconfirmed_intake 不再跟催。"


def list_pending_intakes(limit: int) -> str:
    """列出待確認（awaiting）暫存時限（最舊在前、附等待時數）。供開機 readout / 律師主動查。
    機密軸：機密案件的暫存非全權限層不列（matter_id 為 NULL=未建案、視為非機密、顯示）。"""
    from datetime import datetime

    from shared.floor_policy import is_full_access
    fa = is_full_access()

    db = get_db()
    try:
        # 機密軸過濾下推到 SQL（codex#中）：非全權限層在 LIMIT 之前就排除機密母案件的暫存，
        # 否則前 N 筆剛好都機密時，可見 backlog 會被靜默吞成「空」。
        rows = repository.list_awaiting_intakes(
            db, limit=(limit if limit and limit > 0 else 50), include_confidential=fa
        )
    finally:
        db.close()

    if not rows:
        return "目前沒有待確認的時限暫存（待確認跟催 backlog 為空）。"

    now = datetime.now()
    lines = ["## 待確認時限（尚未入庫、scan_unconfirmed_intake 跟催中）"]
    for r in rows:
        try:
            created = datetime.strptime(str(r["created_at"])[:19], "%Y-%m-%d %H:%M:%S")
            waited = f"{max(0.0, (now - created).total_seconds() / 3600.0):.0f}h"
        except (ValueError, TypeError):
            waited = "?"
        label = (r["matter_label"] or r["matter_no"] or r["matter_title"] or "（未指定案件）")
        doc = r["doc_type"] or "文書"
        svc = r["service_base_date"] or "未填"
        stated = r["stated_period_days"]
        stated_txt = f"、教示{stated}日" if stated else ""
        by = (r["submitted_by"] or "").strip()
        by_txt = f"、提交：{by}" if by else ""
        # 只列抽出的事實 + 等待時數——絕不端出未經引擎確認的權威期限（此時根本還沒算）
        lines.append(
            f"- [#{r['id']}] {label} {doc} 送達日{svc}{stated_txt}"
            f"（已等待 {waited}{by_txt}）"
        )
    lines.append(
        "\n→ 確認入庫：create_deadline(..., confirm_intake_id=<id>)；"
        "不算了：resolve_deadline_intake(<id>, action='discarded')"
    )
    return "\n".join(lines)
