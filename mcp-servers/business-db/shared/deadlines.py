"""legal-admin 時限計算引擎（純函式）+ cron 掃描器。

放 shared/（非 module）理由同 escalation.py：service 層（modules/deadlines）與 cron 薄殼
（scan_deadlines.py）共用 compute_deadline / scan_and_enqueue_due_reminders，放 module 會 import cycle。

=== 鐵律（docs/legal/01-deadline-engine.md §0）===
1. 天數一律確定性程式碼算、附 statutory_basis 法條依據（反捏造、絕不 LLM 心算）。算錯=執業過失。
2. 法定末日（statutory_deadline / hard）與內部期限（internal_deadline / working）分欄並陳。
3. calc_trace 每步可逐步覆核（律師不能信黑箱）。
4. fail-toward-有人看：罕見組合 / 囑託 / 外國送達 → needs_manual_review、不自動結案。

=== 計算流程（§2，步驟順序不可調換）===
  送達基準日 →(送達生效規則)→ 生效日 →(民法§120Ⅱ 翌日)→ 起算日
    →(法定期間 + 在途)→ 理論末日 →(民法§122 末日順延)→ 法定 hard deadline
    → −buffer → 內部 working deadline
"""
import calendar
import json
import re
from datetime import date, datetime, timedelta

# ── 送達生效加算天數（§2 步驟1）：service_type → 加算日數 + 法條依據 ──
# 民訴寄存(+10) ≠ 行政程序法寄存(即生效)，按程序別分流；MVP 先做民訴口徑。
# commissioned/public_foreign 需人工複核（needs_manual_review）。
_SERVICE_EFFECT = {
    "normal":             (0,  "送達當日生效"),
    "registered_deposit": (10, "民訴§138Ⅱ 寄存送達自寄存翌日起算10日生效（110年修正）"),
    "public_domestic":    (20, "民訴§152 公示送達自最後登載日起經20日生效"),
    "public_foreign":     (60, "民訴§152 公示送達（於外國為送達者）經60日生效"),
    "commissioned":       (0,  "囑託送達：回證載明完成日為準（需人工複核）"),
}
# 這些送達類型 MVP 無法確定性自動算（須人工認定回證日 / 境外事實）→ 強制人工複核
_SERVICE_NEEDS_REVIEW = frozenset({"commissioned"})
_VALID_SERVICE_TYPES = frozenset(_SERVICE_EFFECT.keys())

_VALID_PERIOD_TYPES = frozenset({"peremptory", "statutory", "court_set", "directory"})

# period_type → 預設 severity（§4.1；caller 可覆寫）
_PERIOD_DEFAULT_SEVERITY = {
    "peremptory": "red",     # 不變期間：失權硬倒數
    "statutory":  "orange",  # 通常法定：多可補正
    "court_set":  "orange",  # 裁定期間
    "directory":  "grey",    # 訓示：僅進度提醒
}
# severity → 預設 escalation_lead_days（§4.1）
_SEVERITY_DEFAULT_LEAD_DAYS = {
    "red":    [14, 7, 3, 1, 0],
    "orange": [7, 3, 1, 0],
    "grey":   [3],
}

# ── 法定期間種子（§6.3）：核心「反捏造」命脈，放程式常數（migration 012 檔頭說明理由）──
# create_deadline 傳 type 時，若未自帶 statutory_days/basis，從這查表回填（律師仍可覆寫）。
# 每筆強制附 statutory_basis + version。修法（如刑訴上訴 10→20）直接改這、單測對照。
# 結構：type → dict(statutory_days, period_type, statutory_basis, statutory_basis_version, label)
STATUTORY_PERIODS = {
    "appeal_civil": {
        "statutory_days": 20, "period_type": "peremptory",
        "statutory_basis": "民訴§440", "statutory_basis_version": "民事訴訟法§440 現行",
        "label": "民事上訴（對第一審判決）",
    },
    "abjection_civil": {  # 抗告
        "statutory_days": 10, "period_type": "peremptory",
        "statutory_basis": "民訴§487", "statutory_basis_version": "民事訴訟法§487 現行",
        "label": "民事抗告",
    },
    "appeal_criminal": {
        "statutory_days": 20, "period_type": "peremptory",
        "statutory_basis": "刑訴§349", "statutory_basis_version": "刑事訴訟法§349 109.01.15修正版（10→20日，自公布日施行）",
        "label": "刑事上訴（對第一審判決）",
    },
    "abjection_criminal": {  # 刑事抗告
        "statutory_days": 10, "period_type": "peremptory",
        "statutory_basis": "刑訴§406", "statutory_basis_version": "刑事訴訟法§406 112.06.21修正版（5→10日）",
        "label": "刑事抗告",
    },
    "appeal_admin": {
        "statutory_days": 20, "period_type": "peremptory",
        "statutory_basis": "行政訴訟法§241", "statutory_basis_version": "行政訴訟法§241 現行",
        "label": "行政訴訟上訴",
    },
    "appeal_family": {  # 家事「訴訟事件」終局判決→上訴（準用民訴上訴 20 日）
        "statutory_days": 20, "period_type": "peremptory",
        "statutory_basis": "家事事件法§44準用民訴§440", "statutory_basis_version": "家事事件法§44 現行",
        "label": "家事訴訟事件上訴（對終局判決）",
    },
    "abjection_family": {  # 家事「非訟事件」第一審裁定→抗告（10 日，與訴訟上訴 20 日不同、勿混用）
        "statutory_days": 10, "period_type": "peremptory",
        "statutory_basis": "家事事件法§93", "statutory_basis_version": "家事事件法§93 現行（抗告10日不變期間）",
        "label": "家事非訟事件抗告（對第一審裁定）",
    },
    "appeal_reason": {  # 上訴理由書補提（三審逾期逕駁，§471/§382）
        "statutory_days": 20, "period_type": "peremptory",
        "statutory_basis": "民訴§471", "statutory_basis_version": "民事訴訟法§471 現行",
        "label": "上訴理由書補提（第三審）",
    },
    "petition_appeal": {  # 訴願
        "statutory_days": 30, "period_type": "statutory",
        "statutory_basis": "訴願法§14", "statutory_basis_version": "訴願法§14 現行",
        "label": "提起訴願",
    },
    "payment_order_objection": {  # 支付命令異議
        "statutory_days": 20, "period_type": "peremptory",
        "statutory_basis": "民訴§516", "statutory_basis_version": "民事訴訟法§516 現行",
        "label": "支付命令異議",
    },
}

# ── 裁定期間類種子（court_set）：與 STATUTORY_PERIODS「本質不同」、故獨立一張表 ──
# STATUTORY_PERIODS 是「固定法定天數」（上訴 20 / 抗告 10…），天數寫死在法律、可交叉驗證。
# 裁定期間（限期補正等）的天數是**法院在裁定當下載明**的（「於本裁定送達後 X 日內補正」），
# 不是法定固定值——X 是多少只有讀那份裁定才知道。故本表：
#   1. **絕不含 statutory_days**（律師必須讀裁定填，引擎不回填、不預設＝反捏造鐵律：漏補正→駁回起訴）
#   2. statutory_basis 不是法條而是「裁定文號」（basis_hint 提示律師填哪份裁定）
#   3. 命中本表（或任何 period_type=='court_set'）→ create_deadline 強制 needs_manual_review：
#      天數純人輸入、無固定法定種子可交叉驗證，是反捏造風險最高的一類，必須律師覆核。
# 只登記 period_type / severity / label / 觸發語 / 依據提示，不碰天數。修法不影響本表（天數本就非法定）。
COURT_SET_PERIODS = {
    "correction": {  # 限期補正（裁定命補正當事人能力/法定代理/書狀程式/繳費等程式欠缺）
        "period_type": "court_set",
        "severity": "orange",
        "label": "限期補正（裁定所定期間）",
        "default_trigger": "補正裁定送達",
        "basis_hint": "補正裁定文號（如「臺灣臺北地方法院 114 年度補字第 ○ 號裁定」）",
    },
    "provisional_litigation": {  # 保全（假扣押/假處分）命起訴期間（民訴§529Ⅰ，假處分準用§533）
        # 法條查證（taiwan-legal-db query_regulation 民訴§529/§533）：§529Ⅰ「命債權人於『一定期間』內
        # 起訴」——期間是**法院於命起訴裁定主文當下所定**、非法定固定日數（坊間「30日」是慣例非法律值＝
        # 捏造風險）。故歸 court_set：律師必讀那紙命起訴裁定填天數、引擎不臆測不預設。
        # severity=red：逾期未起訴→債務人得聲請撤銷假扣押/假處分裁定（§529Ⅳ/§533準用）＝保全盡失、
        # 無補正餘地，較限期補正(orange,可補)更失權，故 red。起算屬法律判斷(命起訴裁定送達)→court_set 強制複核。
        "period_type": "court_set",
        "severity": "red",
        "label": "保全命起訴期間（假扣押/假處分·命起訴裁定所定）",
        "default_trigger": "命起訴裁定送達",
        "basis_hint": "命起訴裁定文號 + 民訴§529（假處分準用§533）；期間為法院於裁定主文所定『一定期間』、非法定固定日數，請讀裁定填",
    },
}


def court_set_type(type_code):
    """type 是否為已登記的裁定期間類（如 correction）。回 dict（含 period_type/severity/label/
    default_trigger/basis_hint）或 None。create_deadline 用來回填非天數欄 + 觸發強制人工複核。"""
    return COURT_SET_PERIODS.get(type_code)


# ── 消滅時效類種子（type='limitation'，period_unit='year'/'month'）──
# 與固定「日數」種子 STATUTORY_PERIODS、裁定期間 COURT_SET_PERIODS 都不同：消滅時效是「年」期間
# （依民§121 曆法、§123 連續依曆，不可硬轉天數＝閏年會差、反捏造），且起算點是民§128「請求權可
# 行使時」＝法律判斷（非送達日這種確定事實）→ create_deadline 對 limitation 一律強制 needs_manual_
# review、起算日（service_base_date）由律師輸入。期間數放 period_value（非 statutory_days）；
# period_type 用 'statutory'（通常法定、不改既有 CHECK）。
# §197 侵權是「雙時鐘」：知有損害及賠償義務人起 2 年 + 自侵權行為時起 10 年（兩者先到者時效完成）
# → 兩個獨立 type（statute_197_2y / statute_197_10y）、各建一筆、各自起算日，不自動雙建（避免系統
# 替律師判斷「知悉時」）。種子只登記 period_unit/period_value/period_type/severity/法條/label/起算提示。
LIMITATION_PERIODS = {
    "statute_125": {
        "period_unit": "year", "period_value": 15, "period_type": "statutory", "severity": "orange",
        "statutory_basis": "民法§125", "statutory_basis_version": "民法§125 現行",
        "label": "一般請求權消滅時效（15年）",
        "trigger_hint": "請求權可行使時（民§128；律師判斷起算日）",
    },
    "statute_126": {
        "period_unit": "year", "period_value": 5, "period_type": "statutory", "severity": "orange",
        "statutory_basis": "民法§126", "statutory_basis_version": "民法§126 現行",
        "label": "定期給付請求權消滅時效（5年；利息/租金/贍養費/退職金等）",
        "trigger_hint": "各期給付可行使時（民§128）",
    },
    "statute_127": {
        "period_unit": "year", "period_value": 2, "period_type": "statutory", "severity": "orange",
        "statutory_basis": "民法§127", "statutory_basis_version": "民法§127 現行",
        "label": "短期消滅時效（2年；旅店/運送/租賃/醫藥/律師會計師報酬等八款）",
        "trigger_hint": "請求權可行使時（民§128）",
    },
    "statute_197_2y": {
        "period_unit": "year", "period_value": 2, "period_type": "statutory", "severity": "orange",
        "statutory_basis": "民法§197前段（知悉時起2年）", "statutory_basis_version": "民法§197 現行",
        "label": "侵權損害賠償消滅時效（知有損害及賠償義務人時起2年）",
        "trigger_hint": "知有損害及賠償義務人時（民§197；律師判斷；與10年時鐘並行、先到者完成）",
    },
    "statute_197_10y": {
        "period_unit": "year", "period_value": 10, "period_type": "statutory", "severity": "orange",
        "statutory_basis": "民法§197前段（行為時起10年）", "statutory_basis_version": "民法§197 現行",
        "label": "侵權損害賠償消滅時效（自侵權行為時起10年）",
        "trigger_hint": "侵權行為時（民§197；與2年知悉時鐘並行、先到者完成）",
    },
}


def limitation_type(type_code):
    """type 是否為已登記的消滅時效類（statute_125 等）。回 dict（含 period_unit/period_value/
    period_type/severity/statutory_basis/label/trigger_hint）或 None。"""
    return LIMITATION_PERIODS.get(type_code)


# ── 程序「月/年期間」種子（counting_regime='procedural'、period_unit='month'/'year'）──
# 與消滅時效（limitation）關鍵不同：消滅時效是「實體權利」期間（民§128 自請求權可行使時起算、無送達/
# 在途/§122 順延、起算屬法律判斷強制複核）；本表是「程序期間」但以「月」定（非日），故仍要走程序機制：
#   送達生效 → 民§120Ⅱ 次日起算 → 依曆 N 個月（民§121 相當日前一日/§121但書無相當日→月末·§123依曆）
#   → 在途加計 → 民§122 末日順延。
# 法條查證（taiwan-legal-db query_regulation 行訴§88/§89/§91/§106）：行訴§88「期間之計算依民法之規定」
# ＝§120/§121/§122 全適用；§89 在途（但書同民訴§162但書概念）；§91 回復原狀「原因消滅後1個月內、逾1年
# 或§106起訴逾3年不得聲請」（≠民訴§164 之10日，寫死10日＝捏造）。
# 種子只登記 period_unit/period_value/period_type/severity/法條/label/觸發/註記；起算用送達日（確定事實、
# 非法律判斷）→ 預設**不**強制複核（這正是相對消滅時效的可確定性自動算之處），但於 trace/sibling_note
# 明示三個須律師另判的例外（逾3年長期失權、利害關係人知悉在後、不經訴願§106Ⅲ）。
PROCEDURAL_CALENDAR_PERIODS = {
    "admin_revocation": {  # 行政訴訟撤銷訴訟/課予義務訴訟 起訴期間（行訴§106Ⅰ）
        "period_unit": "month", "period_value": 2, "period_type": "peremptory", "severity": "red",
        "statutory_basis": "行政訴訟法§106Ⅰ",
        "statutory_basis_version": "行政訴訟法§106 現行（訴願決定書送達後2個月不變期間）",
        "label": "行政訴訟撤銷訴訟起訴（訴願決定書送達後2個月）",
        "default_trigger": "訴願決定書送達",
        "longstop_note": "例外須律師另判：①§106Ⅰ後段 自訴願決定書送達後逾3年不得提起（長期失權、另立時鐘）；"
                         "②利害關係人知悉在後者自知悉時起算（起算改法律判斷）；③不經訴願者依§106Ⅲ自行政處分"
                         "達到/公告後2個月（起算事件不同、請另建一筆並改 trigger）。",
    },
}


def procedural_calendar_type(type_code):
    """type 是否為已登記的程序月/年期間類（admin_revocation 等）。回 dict 或 None。
    與 limitation_type 互斥：本類走程序機制（送達/在途/§122），消滅時效類不走。"""
    return PROCEDURAL_CALENDAR_PERIODS.get(type_code)


# ── 非種子 type 的可讀標籤（去識別化 title 用；F-P2-2）──
# 已知但無固定法定天數、故不進上面四張種子表的程序類文書（答辯/準備書狀等）：期間多為 court_set/directory、
# 由律師讀法院文書填天數，種子表不登記；但仍是**已知文書類型**，給可讀中文標籤，讓回寫 pleading 的
# 去識別化 title 不致顯示成生代碼「法定期限（answer）」。type 是代碼（非自由文字 description）＝零當事人姓名。
_GENERIC_TYPE_LABELS = {
    "answer": "答辯狀提出期間",
    "brief": "準備書狀提出期間",
}


def type_label(type_code):
    """回某 deadline `type` 的可讀中文標籤，查無回 None。跨四張種子表（label 欄）+ 已知非種子程序類：
    STATUTORY_PERIODS（固定日數）/ COURT_SET_PERIODS（裁定期間）/ LIMITATION_PERIODS（消滅時效）/
    PROCEDURAL_CALENDAR_PERIODS（程序月期間）→ 皆有 label；再 fallback `_GENERIC_TYPE_LABELS`。
    供 pleading 回寫的去識別化 title 用（結構性、由 type 代碼推得、零姓名——**絕不**用自由文字 description
    當 title，律師可能在其中寫當事人名）。"""
    if not type_code:
        return None
    t = type_code.strip()
    for table in (STATUTORY_PERIODS, COURT_SET_PERIODS, LIMITATION_PERIODS, PROCEDURAL_CALENDAR_PERIODS):
        seed = table.get(t)
        if seed and seed.get("label"):
            return seed["label"]
    return _GENERIC_TYPE_LABELS.get(t)


# ── 期間「日數」修法沿革（法版檢核：反捏造安全網）──
# STATUTORY_PERIODS 編的是「現行法」日數。若**文書作成日**（判決/裁定日，非送達日）早於某法條
# 「期間日數修正施行日」，舊文書可能適用修正前日數（如刑訴§349 上訴 2020-01-15 前 10 日、後 20 日）。
# compute_deadline 對「statutory_basis 命中此表、且文書日期早於 effective」標 needs_manual_review
# + calc_trace 說明——「不臆測重算舊法、只擋下請律師確認適用版本與確切施行日」。
#
# 比對用 regex 精準鎖「法別 + 條號邊界」（codex MED-3）：避免裸子字串把『刑訴§349之1』（另一條）
# 誤命中，也涵蓋『刑事訴訟法第349條』『刑訴§349』等寫法。`(?![\d之])` 擋掉 349之1 / 3490 等延伸條號。
# 日期取「修正公布日」從寬（中央法規標準法§13 未明定者公布日起第3日生效；邊界灰區一律標複核、不漏）。
# 種子僅含已查證者（刑訴§349 / §406）；其餘法條未編＝不誤報，查證後再擴充（反捏造：寧缺勿錯）。
_PERIOD_AMENDMENTS = (
    {
        "matcher": re.compile(r"刑(?:事訴訟法|訴)\s*(?:§|第)\s*349(?![\d之])"),
        "effective": "2020-01-15", "prior_days": 10,
        "note": "刑訴§349 上訴期間 民國109.01.15修正公布由 10 日延長為 20 日（§349 不在六個月施行例外、自公布日施行；110.06.16 動的是§348 非§349）",
    },
    {
        "matcher": re.compile(r"刑(?:事訴訟法|訴)\s*(?:§|第)\s*406(?![\d之])"),
        "effective": "2023-06-21", "prior_days": 5,
        "note": "刑訴§406 抗告期間 民國112.06.21修正公布由 5 日延長為 10 日",
    },
)


# ───────────────────────── 日期工具 ─────────────────────────

def _parse_date(s: str) -> date:
    """'YYYY-MM-DD' → date；容許帶時間（取日期部分）。失敗 raise ValueError。"""
    if not s:
        raise ValueError("日期不可為空")
    return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()


def _fmt(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def _to_dt(now) -> datetime:
    """容錯把 now（None / datetime / date / 'YYYY-MM-DD[ HH:MM:SS]' 字串）→ datetime。
    供健康哨兵 / 待確認跟催做時間差（可測試注入）。"""
    if now is None:
        return datetime.now()
    if isinstance(now, datetime):
        return now
    if isinstance(now, date):
        return datetime(now.year, now.month, now.day)
    s = str(now)
    try:
        return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return datetime.strptime(s[:10], "%Y-%m-%d")


def _fmt_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


# ── 民法§121 曆法運算（年/月期間，消滅時效用；自實作不引入 dateutil、可逐行對照法條）──

def _add_years_calendar(d: date, n: int) -> date:
    """起算日 + n 年，回「相當日」。無相當日（2/29 在平年）→ clamp 該月末日（供 §121 但書判斷）。"""
    try:
        return d.replace(year=d.year + n)
    except ValueError:  # 只有 2/29 在平年會 raise
        return d.replace(year=d.year + n, day=calendar.monthrange(d.year + n, d.month)[1])


def _add_months_calendar(d: date, n: int) -> date:
    """起算日 + n 月，回「相當日」。無相當日（如 1/31+1月）→ clamp 該月末日（供 §121 但書判斷）。"""
    m0 = (d.month - 1) + n
    y = d.year + m0 // 12
    m = m0 % 12 + 1
    last = calendar.monthrange(y, m)[1]
    return date(y, m, min(d.day, last))


def _statute_period_end(start: date, unit: str, value: int):
    """民§121：以年/月定期間 → 期間末日。回 (末日 date, no_corresponding bool)。

    - 有相當日 → 末日 = 與起算日相當日「之前一日」（§121 本文）。
    - 無相當日（閏日/月末 clamp 發生）→ 末日 = 該月末日（§121 但書）、no_corresponding=True。
    （§123：稱月或年依曆計算；消滅時效連續計算用曆、非每年 365 日硬轉。）
    """
    if unit == "year":
        anchor = _add_years_calendar(start, value)
    elif unit == "month":
        anchor = _add_months_calendar(start, value)
    else:
        raise ValueError(f"_statute_period_end 僅支援 year/month，got {unit!r}")
    if anchor.day == start.day:
        return anchor - timedelta(days=1), False   # 相當日之前一日
    return anchor, True                              # 無相當日 → 該月末日（§121 但書）


def _bump_past_holidays(nominal_due: date, db):
    """民§122 末日順延：末日遇休息日→逐日推次一上班日。日數路徑與程序月期間路徑共用（避免 drift）。
    回 (statutory_deadline, bumped, trace_line, needs_review)。防呆上限 60（office_calendar 異常時擋下複核）。"""
    d = nominal_due
    bumped = 0
    while is_holiday(d, db=db) and bumped < 60:
        d = d + timedelta(days=1)
        bumped += 1
    if bumped == 0:
        return d, 0, f"末日順延：{_fmt(nominal_due)} 為上班日→不順延（民法§122）", False
    if bumped >= 60:
        return d, bumped, (
            f"末日順延：自 {_fmt(nominal_due)} 連推 60 日仍為假日（辦公日曆異常）→ 需人工複核（民法§122）"
        ), True
    return d, bumped, (
        f"末日順延：{_fmt(nominal_due)} 為假日→順延 {bumped} 日至 {_fmt(d)}（次一上班日，民法§122）"
    ), False


def is_holiday(d, db=None) -> bool:
    """某日是否「非上班日」（末日順延 §122 用）。

    判定順序（office_calendar 為權威、可覆寫預設週末規則）：
      1. office_calendar 有該日紀錄 → 直接用 is_holiday 欄（含補班=週末仍上班→0、平日國定假日→1）
      2. 無紀錄 → 預設週末規則（週六/週日為假日）

    注意：本函式只回 bool（供既有 caller 不變）。「該年度日曆是否載入」的部署安全
    偵測見 calendar_year_loaded()——compute_deadline 用它對「年份完全無紀錄」標 needs_manual_review，
    避免靜默用週末預設誤算 2027 以後國定假日（BUG2）。

    Args:
        d: date 或 'YYYY-MM-DD' 字串
        db: 可選 sqlite3 連線（caller-managed）；不給則自開（read-only、用完關）
    """
    if isinstance(d, str):
        d = _parse_date(d)
    ds = _fmt(d)
    own_db = False
    if db is None:
        from shared.db import get_db
        db = get_db()
        own_db = True
    try:
        row = db.execute(
            "SELECT is_holiday FROM office_calendar WHERE date = ?", (ds,)
        ).fetchone()
    finally:
        if own_db:
            db.close()
    if row is not None:
        # sqlite3.Row 或 tuple 都支援
        return bool(row[0])
    # 無 office_calendar 紀錄 → 預設：週六(5)/週日(6) 為假日
    return d.weekday() >= 5


def _is_leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _office_calendar_year_count(year: int, db=None) -> int:
    """該年 office_calendar 的列數（calendar_year_loaded 與 calc_trace 共用、避免「完全無紀錄」謊報）。"""
    own_db = False
    if db is None:
        from shared.db import get_db
        db = get_db()
        own_db = True
    try:
        row = db.execute(
            "SELECT COUNT(*) FROM office_calendar WHERE date >= ? AND date < ?",
            (f"{year:04d}-01-01", f"{year + 1:04d}-01-01"),
        ).fetchone()
    finally:
        if own_db:
            db.close()
    return row[0] if row else 0


def calendar_year_loaded(year: int, db=None) -> bool:
    """該年度的 office_calendar 是否「**逐日完整載入**」（部署安全偵測，BUG2 + codex r4 HIGH）。

    office_calendar 是末日順延的命脈。**半套年度比完全沒有更危險**：若某年只有幾天（如舊版 migration
    的部分種子、或半套匯入），is_holiday 會對「沒紀錄的那些天」靜默退回只看週末 → 缺的國定假日全抓不到、
    末日順延誤算。故「已載入」定義改為「該年列數達整年天數（365/366）」——**非「有任何一筆」**。
    未達 → compute_deadline 標 needs_manual_review（fail-toward），逼人跑 import_office_calendar.py
    把整年灌齊（匯入器同樣強制單一年度逐日完整、雙重把關）。

    Args:
        year: 西元年
        db: 可選連線；不給則自開
    Returns: True=該年逐日完整載入 / False=未載入或半套（須人工複核）
    """
    expected = 366 if _is_leap(year) else 365
    return _office_calendar_year_count(year, db) >= expected


def lookup_transit_days(court_region: str, party_region: str, db=None):
    """查在途期間（§162）。回傳 (days:int, source:str) 或 (None, None) 表查無組合（→ 人工複核）。

    Args:
        court_region: 受訴法院所在區域代碼
        party_region: 當事人住居地區域代碼
        db: 可選連線
    """
    if not court_region or not party_region:
        return (None, None)
    own_db = False
    if db is None:
        from shared.db import get_db
        db = get_db()
        own_db = True
    try:
        row = db.execute(
            "SELECT days, basis_version FROM transit_period "
            "WHERE court_region = ? AND party_region = ?",
            (court_region, party_region),
        ).fetchone()
    finally:
        if own_db:
            db.close()
    if row is None:
        return (None, None)
    return (int(row[0]), f"查表 {row[1]}：{party_region}→{court_region} {int(row[0])} 日")


# ───────────────────────── 核心引擎 ─────────────────────────

def compute_deadline(
    *,
    period_type: str,
    statutory_days: int,
    statutory_basis: str,
    service_type: str = "normal",
    service_base_date: str,
    has_local_agent: bool = True,
    court_region: str = "",
    party_region: str = "",
    in_transit_days_override=None,
    buffer_days: int = 1,
    stated_period_days=None,
    document_date: str = "",
    period_unit: str = "day",
    period_value=None,
    counting_regime: str = "procedural",
    db=None,
) -> dict:
    """純函式：依 §2 步驟 1~7 算出法定/內部雙日期 + calc_trace + 法條依據。

    讀 DB 僅為 is_holiday（辦公日曆，末日順延）與在途查表——兩者皆 read-only、可傳入 db 共用連線。
    天數計算本身完全確定性、不臆測（反捏造）。

    Args:
        period_type: peremptory/statutory/court_set/directory
        statutory_days: 法定日數（民事上訴=20…；court_set=裁定所載）
        statutory_basis: 法條依據（強制非空，反捏造）
        service_type: 送達類型（normal/registered_deposit/public_domestic/public_foreign/commissioned）
        service_base_date: 送達/寄存/公告基準日 'YYYY-MM-DD'
        has_local_agent: §162但書，律師住法院所在地→在途歸零（律所自辦常 True）
        court_region/party_region: 在途查表維度（無當地代理人時用）
        in_transit_days_override: 手動填在途日數（MVP 第二條路；非 None 時優先於查表）
        buffer_days: 內部安全緩衝（hard − buffer = working）
        stated_period_days: 判決書「上訴教示」所載天數（安全網）；非 None 時與 statutory_days
            交叉比對，不符 → needs_manual_review + calc_trace 記不符（反捏造：引擎不靜默蓋過教示）
        document_date: 文書作成日（判決/裁定日 YYYY-MM-DD，法版檢核用）。法版適用版本依「文書作成日」
            而非送達日（舊判決可能修法後才送達）。未提供 → 以 service_base_date 近似、calc_trace 誠實標明
        period_unit: day（日數路徑、讀 statutory_days）/ year / month（曆法路徑、讀 period_value、依民§121）
        period_value: 年/月期間數（period_unit=year/month 時必 > 0）
        counting_regime: 'procedural'（程序期間：送達+次日§120Ⅱ+在途+§122 末日順延；含日數路徑與行訴§106
            等月期間）/ 'limitation'（消滅時效：無送達/在途/§122、§128 自請求權可行使時起算、強制複核）。
            'limitation' 必搭 period_unit=year/month；year/month + 'procedural' = 程序月期間（行訴§106）
        db: 可選 read-only 連線（is_holiday / 在途查表共用）

    Returns: dict — 含 effective_date / start_date / in_transit_days / in_transit_source /
        statutory_deadline / internal_deadline / buffer_days / calc_trace(list) /
        needs_manual_review / recovery_window(dict) / legal_basis(list) / error(僅出錯時)
    """
    trace: list[str] = []
    legal_basis: list[str] = []
    needs_manual_review = False

    # ── 參數驗證（不臆測、寧可擋下）──
    if period_type not in _VALID_PERIOD_TYPES:
        return {"error": f"period_type 必須是 {sorted(_VALID_PERIOD_TYPES)}，got {period_type!r}"}
    if service_type not in _VALID_SERVICE_TYPES:
        return {"error": f"service_type 必須是 {sorted(_VALID_SERVICE_TYPES)}，got {service_type!r}"}
    if period_unit not in ("day", "year", "month"):
        return {"error": f"period_unit 必須是 day/year/month，got {period_unit!r}"}
    if counting_regime not in ("procedural", "limitation"):
        return {"error": f"counting_regime 必須是 procedural/limitation，got {counting_regime!r}"}
    # ── 兩條正交軸（codex+workflow 全面審：原把「年/月」直接當「消滅時效」是錯誤耦合）──
    #   _is_calendar：期間以年/月定 → 用民§121 曆法 + period_value（vs 日數路徑用 statutory_days）。
    #   _is_limitation：消滅時效 regime → 無送達/在途/§122、§128 起算、強制複核（與「年/月」獨立：
    #     行訴§106 是「年/月 + 程序 regime」、即月期間但仍走送達/在途/§122）。
    _is_calendar = period_unit in ("year", "month")
    _is_limitation = counting_regime == "limitation"
    # 消滅時效必為年/月期間（無「以日計的消滅時效」走本引擎）
    if _is_limitation and not _is_calendar:
        return {"error": "counting_regime='limitation'（消滅時效）必須 period_unit=year/month、不可走日數路徑"}
    # 消滅時效法律性質固定為 statutory（非不變期間/訓示）。程序月期間（行訴§106）則可為 peremptory（不變期間）
    # → 故此鎖只綁 limitation regime、不再對所有年/月強制 statutory（否則行訴§106 不變期間被錯標）。
    if _is_limitation and period_type != "statutory":
        return {"error": f"counting_regime=limitation（消滅時效）要求 period_type=statutory，got {period_type!r}"}
    if not statutory_basis or not str(statutory_basis).strip():
        return {"error": "statutory_basis 不可為空（反捏造：每個法定天數都要有法條依據）"}
    # 行政訴訟期間：在途依行訴§89、回復原狀依行訴§91（≠民訴§162/§164）——由 statutory_basis 偵測、
    # 使在途但書與逾期救濟備援標對法條（反捏造：不可對行政案誤標民訴條文）。
    # 採字串命中（與下方刑事 is_criminal 偵測『刑訴/刑事』同一既有手法）：所有行政種子（admin_revocation
    # 基準『行訴§106』、appeal_admin『行政訴訟法§241』）皆含『行訴/行政訴訟』必命中；殘留風險僅限「自訂
    # 行政時限卻把 statutory_basis 寫成不含此關鍵字」（屬使用者輸入錯誤、與刑事偵測同等限制，codex finding#1）。
    _is_admin = ("行政訴訟" in statutory_basis) or ("行訴" in statutory_basis)
    # statutory_days 僅「日數路徑（period_unit='day'）」適用且必 > 0；年/月路徑改用 period_value，
    # statutory_days 此時為 0/未提供、不可被 day 路徑的 >0 規則誤擋。
    try:
        si = int(statutory_days) if statutory_days else 0
    except (TypeError, ValueError):
        return {"error": f"statutory_days 必須是整數，got {statutory_days!r}"}
    if not _is_calendar and si <= 0:
        return {"error": f"statutory_days 必須 > 0（期間日數，0 日期間無意義），got {si}"}
    if si < 0:
        return {"error": f"statutory_days 不可為負，got {si}"}
    # period_value（年/月期間數）提前解析驗證：日數與曆法路徑、教示比對都會用到（消除分支內重複解析）。
    try:
        pv = int(period_value) if period_value else 0
    except (TypeError, ValueError):
        return {"error": f"period_value 必須是整數，got {period_value!r}"}
    if _is_calendar and pv <= 0:
        return {"error": f"period_value（{period_unit} 期間數）必須 > 0，got {period_value!r}"}
    try:
        base = _parse_date(service_base_date)
    except (ValueError, TypeError):
        return {"error": f"service_base_date 格式須為 YYYY-MM-DD，got {service_base_date!r}"}
    try:
        buf = int(buffer_days)
    except (TypeError, ValueError):
        buf = 1
    if buf < 0:
        buf = 0

    legal_basis.append(statutory_basis)

    # ── 步驟 0a：法版檢核（反捏造安全網）──
    # STATUTORY_PERIODS 編現行法日數；**文書作成日**（判決/裁定日）早於某法條「期間日數修正施行日」
    # → 舊文書可能適用修正前日數。法版適用看文書作成日、非送達日（舊判決可能修法後才送達，codex HIGH-1）。
    # 不臆測重算舊法（無舊法日曆 / 過渡條款判斷易錯），改標 needs_manual_review、請律師確認版本與施行日。
    # 文書作成日未提供 → 以 service_base_date 近似、trace 誠實標明（不謊稱精確）。
    _doc_d = None
    if document_date and str(document_date).strip():
        try:
            _doc_d = _parse_date(document_date)
        except (ValueError, TypeError):
            # 反捏造：非空 document_date 格式錯誤不可靜默退回送達日近似（會繞過法版檢核、且落欄髒資料）。
            # 比照 service_base_date 處理——回 error，service 層擋下、不寫入（codex R2 HIGH）。
            return {"error": f"document_date（文書作成日）格式須為 YYYY-MM-DD，got {document_date!r}"}
    _check_d = _doc_d if _doc_d is not None else base
    _check_src = "文書作成日" if _doc_d is not None else "送達日（未提供文書作成日、以送達日近似）"
    for _amd in _PERIOD_AMENDMENTS:
        if _amd["matcher"].search(statutory_basis):
            try:
                _amd_eff = _parse_date(_amd["effective"])
            except (ValueError, TypeError):
                continue
            if _check_d < _amd_eff:
                needs_manual_review = True
                trace.append(
                    f"法版檢核：{_check_src}{_fmt(_check_d)}早於修法施行日{_amd['effective']}"
                    f"（{_amd['note']}）；引擎採現行法 {si} 日、舊文書可能適用修正前 {_amd['prior_days']} 日"
                    f"→ 須人工確認適用版本（不臆測重算舊法）"
                )

    # ── 步驟 0b：教示比對（反捏造安全網）──
    # 判決書「上訴教示」常載期間日數（如「得於收受後二十日內上訴」）。與引擎採用的 statutory_days
    # 交叉比對：不符可能是法定期間判斷有誤、或屬特別期間 → needs_manual_review，引擎不靜默蓋過教示。
    period_match = "not_provided"
    spd = None
    # 比對標的依期間單位：日數路徑比 statutory_days（日）、年/月路徑比 period_value（同單位）。
    # 反捏造：消滅時效/月期間絕不拿「日」去比「月/年」（單位錯置會誤判相符/不符）。
    _match_target = pv if _is_calendar else si
    _unit_zh = "個月" if period_unit == "month" else ("年" if period_unit == "year" else "日")
    if stated_period_days is not None:
        try:
            spd = int(stated_period_days)
        except (TypeError, ValueError):
            spd = None
        if spd is not None:
            if spd == _match_target:
                period_match = "match"
                trace.append(f"教示比對：判決書教示 {spd} {_unit_zh}＝引擎採用 {_match_target} {_unit_zh}（相符）")
            else:
                period_match = "mismatch"
                needs_manual_review = True
                trace.append(
                    f"教示比對：判決書教示 {spd} {_unit_zh} ≠ 引擎採用 {_match_target} {_unit_zh}（不符）"
                    f"→ 須人工確認（可能法定期間判斷有誤、或屬特別期間）"
                )
        else:
            # 有帶值但無法解析為整數（如 OCR/轉錄抽到「二十日」「20日」）：教示比對是揪錯的安全網，
            # 不可靜默旁路退成 not_provided（codex MED）→ 標複核 + 把原文記進 calc_trace 供人核對
            # （反捏造：安全網默默放掉＝失去防線；stated_period_days 是 INTEGER 欄存不了原文，故落 trace）。
            period_match = "unparseable"
            needs_manual_review = True
            trace.append(
                f"教示比對：判決書教示天數原文『{stated_period_days}』無法解析為整數、無法與引擎採用 "
                f"{_match_target} {_unit_zh}交叉比對 → 須人工核對原文（反捏造：安全網不靜默旁路）"
            )

    # ── 步驟 1：送達生效日 ──
    if _is_limitation:
        # 消滅時效：無送達生效加算（民§128 自請求權可行使時直接起算）→ effective=可行使日本身、
        # 完全不看 service_type（否則 public_domestic+20 等送達規則會錯套到時效，codex HIGH-3）。
        # 注意：程序月期間（行訴§106，_is_calendar 但非 limitation）走 else、仍有送達生效（訴願決定書送達）。
        effective = base
        trace.append(f"請求權可行使日={_fmt(base)}（消滅時效自可行使時起算、無送達生效加算·民§128）")
    else:
        add_days, effect_basis = _SERVICE_EFFECT[service_type]
        if service_type in _SERVICE_NEEDS_REVIEW:
            # 囑託送達：回證日須人工認定，base_date 暫當回證日、但旗標人工複核
            needs_manual_review = True
            effective = base
            trace.append(
                f"送達生效=囑託送達以回證載明完成日為準（暫用輸入 {_fmt(base)}）→ 需人工複核（{effect_basis}）"
            )
        else:
            effective = base + timedelta(days=add_days)
            if add_days:
                trace.append(
                    f"送達生效={_fmt(base)}+{add_days}={_fmt(effective)}（{effect_basis}）"
                )
                legal_basis.append(effect_basis)
            else:
                trace.append(f"送達生效={_fmt(effective)}（{effect_basis}）")

    # ── 步驟 2：起算日（民法§120Ⅱ 始日不算入）──
    start = effective + timedelta(days=1)
    trace.append(f"起算=生效翌日{_fmt(start)}（民法§120Ⅱ 始日不算入）")
    legal_basis.append("民法§120Ⅱ")

    if _is_limitation:
        # ════ 消滅時效路徑（民§121 曆法、§128 起算點法律判斷）════
        # 步驟 3'：無在途、無送達加算（§128 自請求權可行使時直接起算）。pv 已於入口統一解析驗證。
        in_transit = 0
        in_transit_source = "消滅時效不適用在途/送達加算（§128 自請求權可行使時起算）"
        trace.append(f"在途=0（{in_transit_source}）")
        # 步驟 4'：末日依民§121（年/月→相當日之前一日；無相當日→該月末日），§123 連續依曆
        statutory_deadline, _no_corr = _statute_period_end(start, period_unit, pv)
        _uzh = "年" if period_unit == "year" else "月"
        if _no_corr:
            trace.append(
                f"末日（民§121但書）：起算日{_fmt(start)}+{pv}{_uzh}無相當日（閏日/月末）"
                f"→以該月末日{_fmt(statutory_deadline)}為期間末日"
            )
        else:
            trace.append(
                f"末日（民§121）：起算日{_fmt(start)}+{pv}{_uzh}之相當日之前一日"
                f"={_fmt(statutory_deadline)}（§123 連續依曆計算）"
            )
        legal_basis.extend(["民法§121", "民法§123", "民法§128"])
        # 步驟 5'：§122 末日順延於消滅時效有見解分歧 → 引擎不臆測順延、依曆末日為準、一律強制人工複核
        needs_manual_review = True
        trace.append(
            f"消滅時效末日{_fmt(statutory_deadline)}依曆計（民§121/§123）；§122 末日遇休息日是否順延"
            f"於消滅時效有見解分歧、引擎不臆測順延、以依曆末日為準；且§128 起算點『請求權可行使時』"
            f"屬法律判斷 → 強制人工複核（律師須確認起算日、及時效有無中斷/不完成 §129~§143）"
        )
        # statutory_days 欄「不重載」期間數：year/month 留 0（statutory_days 是「日數」語義，把 15 年
        # 塞成 15 會在顯示端變「15 日」＝反捏造，codex HIGH-4）。期間數一律由 period_value 表達。
    else:
        # ════ 程序期間路徑（訴訟/行政訴訟期間：上訴/抗告/補正/行訴§106…）════
        # 日數與月/年期間共用：送達生效(步驟1) + 次日(步驟2) + 在途 + 末日 + §122 順延。
        # 末日算法依 period_unit 二分：日→天數加法；月/年→民§121 曆法（行訴§88 期間依民法計算）。
        # ── 步驟 3：在途天數（民訴§162 / 行政訴訟§89；行政案標 §89、避免對行政案誤標民訴條文）──
        _transit_law = "行訴§89" if _is_admin else "民訴§162"
        in_transit = 0
        in_transit_source = ""
        if period_type == "court_set":
            in_transit = 0
            in_transit_source = "裁定期間不適用在途（§162）"
            trace.append(f"在途=0（{in_transit_source}）")
        elif in_transit_days_override is not None:
            try:
                in_transit = max(0, int(in_transit_days_override))
            except (TypeError, ValueError):
                in_transit = 0
            in_transit_source = f"手動指定在途 {in_transit} 日"
            trace.append(f"在途={in_transit}（{in_transit_source}）")
        elif has_local_agent:
            in_transit = 0
            in_transit_source = f"{_transit_law}但書·律師住法院所在地→在途歸零"
            trace.append(f"在途=0（{in_transit_source}）")
            legal_basis.append(f"{_transit_law}但書")
        elif _is_admin:
            # 行政訴訟在途期間（行訴§89Ⅱ「由司法院定之」）非民訴 transit_period 表口徑，引擎無該表
            # → 不臆測、人工複核、在途暫 0（fail-toward）。律師依司法院定之在途期間表手動填 in_transit_days。
            in_transit = 0
            needs_manual_review = True
            in_transit_source = "無當地代理人之行政訴訟在途（行訴§89Ⅱ 由司法院定之）→ 需人工複核並手動填在途日數"
            trace.append(f"在途=0（暫）；{in_transit_source}")
        else:
            days, src = lookup_transit_days(court_region, party_region, db=db)
            if days is None:
                # fail-toward-有人看：無當地代理人又查無在途組合 → 不臆測、人工複核、在途暫 0
                in_transit = 0
                needs_manual_review = True
                in_transit_source = (
                    f"無當地代理人且查無在途組合（court={court_region or '?'}, "
                    f"party={party_region or '?'}）→ 需人工複核在途期間（§162）"
                )
                trace.append(f"在途=0（暫）；{in_transit_source}")
            else:
                in_transit = days
                in_transit_source = src
                trace.append(f"在途={in_transit}（{in_transit_source}）")
                legal_basis.append("民訴§162")

        # ── 步驟 4：理論末日 ──
        if _is_calendar:
            # 月/年程序期間（如行訴§106 訴願決定書送達後2個月不變期間）：依民§121 曆法算末日，
            # 再「加計在途日數」、最後§122 末日順延。行訴§88 明定期間之計算依民法（§120/§121/§122）。
            period_end, _no_corr = _statute_period_end(start, period_unit, pv)
            _uzh = "年" if period_unit == "year" else "月"
            if _no_corr:
                trace.append(
                    f"末日（民§121但書）：起算日{_fmt(start)}+{pv}{_uzh}無相當日（月末）"
                    f"→以該月末日{_fmt(period_end)}為期間末日（§123 依曆）"
                )
            else:
                trace.append(
                    f"末日（民§121）：起算日{_fmt(start)}+{pv}{_uzh}之相當日之前一日"
                    f"={_fmt(period_end)}（§123 依曆計算）"
                )
            legal_basis.extend(["民法§121", "民法§123"])
            if in_transit:
                period_end = period_end + timedelta(days=in_transit)
                trace.append(f"在途加計：依曆末日 +{in_transit} 日={_fmt(period_end)}（{_transit_law}在途加計）")
            nominal_due = period_end
        else:
            # 日數路徑（中間假日全計入、不跳過）
            span = si + in_transit
            nominal_due = start + timedelta(days=span - 1) if span > 0 else start
            trace.append(
                f"理論末日={_fmt(start)}+({si}{'+' + str(in_transit) if in_transit else ''}-1)"
                f"={_fmt(nominal_due)}（中間週末/國定假日全計入、連續計算）"
            )

        # ── 步驟 5：末日順延（民法§122，只對末日；日數/月期間共用 _bump_past_holidays）──
        statutory_deadline, bumped, _bump_trace, _bump_review = _bump_past_holidays(nominal_due, db)
        trace.append(_bump_trace)
        if _bump_review:
            needs_manual_review = True
        if 0 < bumped < 60:
            legal_basis.append("民法§122")

    # ── 步驟 5b：辦公日曆完整載入偵測（部署安全，BUG2 + codex r4/r5）──
    # 末日順延（步驟5）與內部線對齊（步驟6）皆讀 office_calendar；若所需日期落在「未逐日完整
    # 載入的年度」，is_holiday 會對缺漏日靜默退回只看週末規則 → 國定假日 / 補班抓不到、可能誤算。
    # 檢查 start_date → statutory_deadline 區間涵蓋的每個年度是否「完整」載入（達 365/366）。
    # 反捏造：trace 據實標「未完整載入（current/expected）」、不謊稱「完全無紀錄」（半套也算未載入）。
    _missing_years = []  # (year, count, expected)
    # 消滅時效（limitation）不順延、末日不靠日曆，且跨年區間長（如15年）→ 跳過整區間日曆檢查（免洗版；
    # 已因起算點屬法律判斷強制複核）。程序月期間（行訴§106）末日要§122順延、仍需日曆完整→照常檢查。
    # internal 前移若落未載入年度退回週末規則、屬參考線可接受。
    if not _is_limitation:
        for _y in range(start.year, statutory_deadline.year + 1):
            if not calendar_year_loaded(_y, db=db):
                _missing_years.append(
                    (_y, _office_calendar_year_count(_y, db=db), 366 if _is_leap(_y) else 365)
                )
    if _missing_years:
        needs_manual_review = True
        _yrs = "、".join(f"{y}（{c}/{e} 天）" for y, c, e in _missing_years)
        trace.append(
            f"辦公日曆未完整載入：所需年度 {_yrs} 在 office_calendar 未達整年"
            f"（缺漏日會退回週末預設、抓不到國定假日 / 補班）→ 無法確定末日順延、須人工複核"
            f"（內部 / 法定末日為週末預設下的估值；請跑 import_office_calendar.py 灌完整年度）"
        )

    # ── 步驟 6：內部期限（working = hard − buffer）──
    internal = statutory_deadline - timedelta(days=buf)
    if buf == 0:
        # buffer=0：內部線＝法定末日（已是順延後的上班日）、不需再對齊
        trace.append(f"內部期限=法定末日（buffer=0）{_fmt(statutory_deadline)}（盯此）")
    elif not is_holiday(internal, db=db):
        # 正常情形：hard − buffer 即為上班日、行為不變
        trace.append(
            f"內部期限=法定末日−{buf}={_fmt(internal)}（盯此；底線法定{_fmt(statutory_deadline)}）"
        )
    else:
        # 內部線落假日：往前對齊到上班日呈現（避免內部線落在假日反而不提醒）。
        # 搜尋區間僅 (start_date, hard]——start_date 本身可能是假日（如連假首日），
        # 不可退到 start 或以前（會停在假日 = 謊報）。
        internal_pre_align = internal
        candidate = internal - timedelta(days=1)
        guard = 0
        while candidate > start and is_holiday(candidate, db=db) and guard < 60:
            candidate = candidate - timedelta(days=1)
            guard += 1
        if candidate > start and not is_holiday(candidate, db=db):
            # 區間內找到上班日：誠實前移
            internal = candidate
            trace.append(
                f"內部期限=法定末日−{buf}={_fmt(internal_pre_align)}，落假日→前移至上班日"
                f"{_fmt(internal)}（盯此；底線法定{_fmt(statutory_deadline)}）"
            )
        else:
            # fail-toward：緩衝期完全落在連假、(start_date, hard] 區間內無任何上班日可前移。
            # 不可靜默停在假日（謊報），改：緩衝收為 0、內部線＝法定末日（可辯護且誠實標示）+ 人工複核。
            internal = statutory_deadline
            needs_manual_review = True
            trace.append(
                f"內部期限：法定末日−{buf}={_fmt(internal_pre_align)} 落假日，"
                f"且緩衝期完全落在連假（{_fmt(start)} 後至法定末日 {_fmt(statutory_deadline)} 區間內"
                f"無任何上班日可前移）→ fail-toward：緩衝收為 0、內部期限暫設為法定末日"
                f"{_fmt(statutory_deadline)}、須人工複核（盯此；底線法定{_fmt(statutory_deadline)}）"
            )

    # ── 步驟 7：逾期救濟備援（民訴§164 / 刑訴§67 / 行政訴訟§91）──
    # 程序別不同、回復原狀法條與期間都不同（反捏造：行政案不可端出民訴§164 之10日）：
    #   刑事 刑訴§67（10日）／民事 民訴§164（10日、逾1年不得）／行政 行訴§91（1個月、逾1年或§106起訴逾3年不得）。
    is_criminal = "刑訴" in statutory_basis or "刑事" in statutory_basis
    if is_criminal:
        recovery_window = {
            "basis": "刑訴§67",
            "condition": "遲誤非因過失，於原因消滅後10日內聲請回復原狀，並同時補行期間內應為之訴訟行為",
            "deadline_after_cause_removed_days": 10,
        }
    elif _is_admin:
        # 行政訴訟回復原狀（行訴§91，taiwan-legal-db 查證）：原因消滅後「1個月」內（不變期間少於1個月者於
        # 相等日數內）；逾1年不得聲請，遲誤§106起訴期間逾3年亦不得。期間以「月」計、不寫死成日數（反捏造）。
        recovery_window = {
            "basis": "行政訴訟法§91",
            "condition": "因不應歸責於己之事由遲誤不變期間，於原因消滅後1個月內（該不變期間少於1個月者於相等日數內）"
                         "以書狀聲請回復原狀，並補行期間內應為之訴訟行為",
            "absolute_limit": "遲誤不變期間逾1年不得聲請；遲誤§106起訴期間逾3年不得聲請",
        }
    else:
        recovery_window = {
            "basis": "民訴§164",
            "condition": "遲誤非因過失，於原因消滅後10日內聲請回復原狀；距遲誤期間之末日未逾1年；須同時補行訴訟行為",
            "deadline_after_cause_removed_days": 10,
            "absolute_limit": "距遲誤期間末日逾1年不得聲請",
        }

    # 消滅時效（limitation）不適用回復原狀（民訴§164/刑訴§67/行訴§91 是訴訟程序遲誤的救濟、非實體權利消滅）。
    # 程序月期間（行訴§106、_is_calendar 但非 limitation）是不變期間、適用回復原狀（行訴§91）→ 不清空。
    if _is_limitation:
        recovery_window = {}

    return {
        "effective_date": _fmt(effective),
        "start_date": _fmt(start),
        "in_transit_days": in_transit,
        "in_transit_source": in_transit_source,
        "statutory_days": si,
        "statutory_basis": statutory_basis,
        "statutory_deadline": _fmt(statutory_deadline),
        "buffer_days": buf,
        "internal_deadline": _fmt(internal),
        "stated_period_days": spd,
        "period_match": period_match,
        "calc_trace": trace,
        "needs_manual_review": needs_manual_review,
        "recovery_window": recovery_window,
        "legal_basis": legal_basis,
        "period_unit": period_unit,
        "period_value": (pv if _is_calendar else None),
    }


def default_severity(period_type: str) -> str:
    return _PERIOD_DEFAULT_SEVERITY.get(period_type, "orange")


def default_lead_days(severity: str) -> list:
    return list(_SEVERITY_DEFAULT_LEAD_DAYS.get(severity, [7, 3, 1, 0]))


# ───────────────────────── cron 掃描器（time-driven 寫入端）─────────────────────────

def _workdays_between(start_d: date, end_d: date, db) -> int:
    """start_d → end_d 之間的「上班日」數（含 end、不含 start 當天往前算的方向）。

    回傳「從今天到 internal_deadline 還剩幾個上班日」。end < start → 負數（逾期）。
    計算：逐日走、數上班日。逾期回負（以日曆日差近似負值，足供 days_left<0 判逾期）。
    """
    if end_d < start_d:
        return -( (start_d - end_d).days )
    count = 0
    cur = start_d + timedelta(days=1)  # 不算今天本身
    while cur <= end_d:
        if not is_holiday(cur, db=db):
            count += 1
        cur += timedelta(days=1)
    return count


# ── 系統健康哨兵（#H1）+ 待確認跟催（#H2）的常數與 heartbeat action 名 ──
# heartbeat 走 interaction_log（cross-cutting audit sink、既有表、無需新 migration）。
HEARTBEAT_SCAN = "deadline_scan_heartbeat"        # scan_deadlines.py 每次成功掃描落一筆
HEARTBEAT_WATCHDOG = "health_watchdog_heartbeat"  # scan_heartbeat.py（watchdog）每次跑落一筆（自證活著）
# 失聯門檻（cross-file 單一真相：開機 readout 與 watchdog 都 import 本常數、test_smoke_all 綁死、勿在他處寫死）。
SCAN_STALE_HOURS = 26       # scan_deadlines 建議 cron 每日 07:00；+2h grace、超過視為失聯
WATCHDOG_STALE_HOURS = 6    # watchdog 建議 cron 每 1~2h；>6h 視為連監看本身都失聯
SCAN_REALERT_HOURS = 24     # 同一失聯期 scan_stalled 最多每 24h 再上報一次（防洗版）
# 待確認跟催等待節點（小時）：丟了檔、AI 推確認、人忘了回 → 時限沒入庫 = 隱形漏掉。
INTAKE_REMINDER_HOURS = (4, 24, 72)


def _record_heartbeat(db, kind: str, detail: str = "") -> None:
    """落一筆 heartbeat 到 interaction_log（caller-managed-tx）。created_at 走 schema 預設
    datetime('now','localtime')、與其他 interaction_log 一致。"""
    db.execute(
        "INSERT INTO interaction_log (actor, action, target_type, target_id, detail, business_unit) "
        "VALUES (?,?,?,?,?,?)",
        ("系統·cron", kind, "system", None, detail, None),
    )


def _heartbeat_at(db, kind: str):
    """最近一筆該類 heartbeat 的 created_at 字串（無→None）。"""
    row = db.execute(
        "SELECT created_at FROM interaction_log WHERE action=? ORDER BY id DESC LIMIT 1",
        (kind,),
    ).fetchone()
    return row["created_at"] if row and row["created_at"] else None


def _heartbeat_age_hours(db, kind: str, now: datetime):
    """距最近一筆該類 heartbeat 幾小時（無紀錄→None）。"""
    at = _heartbeat_at(db, kind)
    if not at:
        return None
    try:
        ts = datetime.strptime(str(at)[:19], "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None
    return max(0.0, (now - ts).total_seconds() / 3600.0)


def _recently_alerted(db, event_type: str, window_hours: float, now: datetime) -> bool:
    """該 event_type 是否在 window_hours 內已上報過（讀 enqueue_escalation 落的稽核鏡像
    action='escalation_<event_type>'）。用來讓 watchdog 同一失聯期不重複洗版。"""
    row = db.execute(
        "SELECT created_at FROM interaction_log WHERE action=? ORDER BY id DESC LIMIT 1",
        (f"escalation_{event_type}",),
    ).fetchone()
    if not row or not row["created_at"]:
        return False
    try:
        ts = datetime.strptime(str(row["created_at"])[:19], "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return False
    return (now - ts).total_seconds() < window_hours * 3600


def check_scan_health(db, now=None) -> dict:
    """純讀：回掃描器 / watchdog 的健康狀態（給開機 readout 與 watchdog 共用、不寫入）。

    granular 旗標（讓 caller 自己決定怎麼呈現 / 是否告警）：
    - scan_never：從未落過 scan heartbeat（全新系統 / cron 沒部署）
    - scan_overdue：曾掃過但距今 > SCAN_STALE_HOURS（曾在跑、停了＝最該警覺的失聯）
    - watchdog_never / watchdog_overdue：同義、針對 watchdog 自身
    - pending_deadlines：目前待處理時限數（scan_never 時用來判斷「有東西要掃卻沒掃」）
    """
    now = _to_dt(now)
    scan_age = _heartbeat_age_hours(db, HEARTBEAT_SCAN, now)
    wd_age = _heartbeat_age_hours(db, HEARTBEAT_WATCHDOG, now)
    pending = db.execute(
        "SELECT COUNT(*) c FROM deadlines WHERE status='pending'"
    ).fetchone()["c"]
    return {
        "now": _fmt_dt(now),
        "pending_deadlines": pending,
        "last_scan_at": _heartbeat_at(db, HEARTBEAT_SCAN),
        "scan_age_hours": scan_age,
        "scan_never": scan_age is None,
        "scan_overdue": scan_age is not None and scan_age > SCAN_STALE_HOURS,
        "last_watchdog_at": _heartbeat_at(db, HEARTBEAT_WATCHDOG),
        "watchdog_age_hours": wd_age,
        "watchdog_never": wd_age is None,
        "watchdog_overdue": wd_age is not None and wd_age > WATCHDOG_STALE_HOURS,
        "stale_threshold_hours": SCAN_STALE_HOURS,
    }


def scan_health_and_alert(now=None) -> dict:
    """watchdog cron（scan_heartbeat.py）本體：時間驅動、獨立極小進程（人沒開 Claude 也照跑）。
    兩件事：(1) 落自身 heartbeat＝自證活著（boot readout 才能反過來偵測 watchdog 死掉）；
    (2) scan 失聯（曾掃過卻停了，或從未掃過但已有待處理時限）→ enqueue scan_stalled 上報，
    接現役三層投遞推給老闆。同一失聯期最多每 SCAN_REALERT_HOURS 告警一次。"""
    from shared.db import transaction
    from shared.escalation import enqueue_escalation

    now = _to_dt(now)
    stats = {"watchdog": "alive", "scan_overdue": False, "scan_never": False,
             "scan_age_hours": None, "alerted": False}
    with transaction() as db:
        _record_heartbeat(db, HEARTBEAT_WATCHDOG, "watchdog alive")
        health = check_scan_health(db, now=now)
        stats["scan_overdue"] = health["scan_overdue"]
        stats["scan_never"] = health["scan_never"]
        stats["scan_age_hours"] = health["scan_age_hours"]
        # 告警條件：曾掃過但停了，或從未掃過但已有待處理時限（掃描器沒部署/沒在跑、卻有東西在倒數）。
        should_alert = health["scan_overdue"] or (health["scan_never"] and health["pending_deadlines"] > 0)
        if should_alert and not _recently_alerted(db, "scan_stalled", SCAN_REALERT_HOURS, now):
            if health["scan_never"]:
                age_txt = "從未成功執行"
                last_txt = "無紀錄"
            else:
                age_txt = f"約 {health['scan_age_hours']:.0f} 小時未執行"
                last_txt = health["last_scan_at"] or "無紀錄"
            enqueue_escalation(
                db,
                event_type="scan_stalled",
                summary=(
                    f"【系統異常·時限掃描失聯】時限掃描器{age_txt}"
                    f"（上次成功掃描：{last_txt}；目前 {health['pending_deadlines']} 筆待處理時限）。"
                    f"時限可能已停止倒數，請立即人工巡一次未結時限（list_upcoming_deadlines）、"
                    f"並檢查 scan_deadlines.py 的 cron 是否在跑。"
                ),
                detail={
                    "kind": "scan_stalled",
                    "last_scan_at": str(last_txt),
                    "scan_age_hours": ("" if health["scan_age_hours"] is None
                                       else f"{health['scan_age_hours']:.1f}"),
                    "pending_deadlines": str(health["pending_deadlines"]),
                },
                actor_user_id="",
                actor_label="系統·健康哨兵",
                business_unit="",
                channel_id=None,
            )
            stats["alerted"] = True
    return stats


def scan_and_enqueue_unconfirmed_intakes(now=None) -> dict:
    """cron（scan_unconfirmed_intake.py）掃 pending_intakes status='awaiting' → 命中等待節點
    即 enqueue intake_unconfirmed 跟催。補核心 loop「一鍵確認才入」的結構盲區：丟了檔、AI 推確認、
    人忘了回 → 時限沒進 deadlines 表 → 一般掃描（WHERE status='pending'）掃不到 → 隱形漏掉。

    鐵律（反捏造）：提醒文字只列『送達日 + 文書類型 + 等待時數』等「抽出的事實」，
    絕不端出引擎 computed deadline——待確認階段 create_deadline 根本還沒跑、權威日期尚不存在。
    reminders_sent 冪等鑰：同一等待節點不重推。"""
    from shared.db import transaction
    from shared.escalation import enqueue_escalation

    now = _to_dt(now)
    stats = {"awaiting": 0, "reminded": 0, "skipped": 0}
    with transaction() as db:
        rows = db.execute(
            "SELECT p.*, m.matter_no AS m_no, m.title AS m_title "
            "FROM pending_intakes p LEFT JOIN matters m ON m.id = p.matter_id "
            "WHERE p.status='awaiting'"
        ).fetchall()
        for r in rows:
            stats["awaiting"] += 1
            try:
                created = datetime.strptime(str(r["created_at"])[:19], "%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                stats["skipped"] += 1
                continue
            waited_h = max(0.0, (now - created).total_seconds() / 3600.0)
            try:
                sent = set(json.loads(r["reminders_sent"] or "[]"))
            except (json.JSONDecodeError, TypeError):
                sent = set()
            # 只推「目前該推的最高未提醒節點」（一次補推多筆無意義、徒增洗版）
            due_nodes = [h for h in INTAKE_REMINDER_HOURS if waited_h >= h and h not in sent]
            if not due_nodes:
                continue
            node = max(due_nodes)
            label = (r["matter_label"] or r["m_no"] or r["m_title"] or "（未指定案件）")
            doc = r["doc_type"] or "文書"
            svc = r["service_base_date"] or "未填"
            stated = r["stated_period_days"]
            stated_txt = f"、教示{stated}日" if stated else ""
            submitter = (r["submitted_by"] or "").strip()
            by_txt = f"、提交：{submitter}" if submitter else ""
            enqueue_escalation(
                db,
                event_type="intake_unconfirmed",
                summary=(
                    f"【待確認時限】{label} {doc} 送達日{svc}{stated_txt}"
                    f"，已等待約 {waited_h:.0f} 小時未確認入庫{by_txt}。"
                    f"請確認後走時限收件流程 create_deadline（帶 confirm_intake_id={r['id']}），"
                    f"或 resolve_deadline_intake({r['id']}, action='discarded') 標示捨棄。"
                ),
                detail={
                    "kind": "intake_unconfirmed",
                    "intake_id": str(r["id"]),
                    "service_base_date": str(svc),
                    "doc_type": str(doc),
                    "waited_hours": f"{waited_h:.1f}",
                },
                actor_user_id="",
                actor_label="系統·待確認跟催",
                business_unit="",
                channel_id=None,
            )
            sent.add(node)
            db.execute(
                "UPDATE pending_intakes SET reminders_sent=? WHERE id=?",
                (json.dumps(sorted(sent)), r["id"]),
            )
            stats["reminded"] += 1
    return stats


def scan_and_enqueue_due_reminders(today=None) -> dict:
    """cron 每日掃 pending deadlines → 命中 escalation_lead_days 節點即 enqueue（接現役三層投遞）。

    單一 transaction、enqueue 走現役 enqueue_escalation（caller-managed-tx、同原子 commit）。
    reminders_sent 冪等鑰：同一 lead_day 命中第二次不重推。
    commit 成功 → transaction() fire-and-forget 起 claude -p 品質層 + in-session 即時層（零額外接線）。

    Args:
        today: 可選 date（測試注入）；預設 date.today()

    Returns: dict — scanned / approaching / missed / skipped 計數
    """
    from shared.db import transaction
    from shared.escalation import (
        enqueue_escalation, resolve_escalation_target, _looks_like_line_user_id,
    )

    if today is None:
        today = date.today()
    elif isinstance(today, str):
        today = _parse_date(today)
    elif isinstance(today, datetime):
        today = today.date()

    stats = {"scanned": 0, "approaching": 0, "missed": 0, "skipped": 0}

    with transaction() as db:
        rows = db.execute(
            "SELECT d.*, m.matter_no AS matter_no, m.title AS matter_title, "
            "       m.lead_attorney AS lead_attorney, m.business_unit AS m_bu, "
            "       d.assignee AS d_assignee "
            "FROM deadlines d JOIN matters m ON m.id = d.matter_id "
            "WHERE d.status = 'pending'"
        ).fetchall()

        for d in rows:
            stats["scanned"] += 1
            internal = d["internal_deadline"]
            statutory = d["statutory_deadline"]
            if not internal:
                stats["skipped"] += 1
                continue
            try:
                internal_d = _parse_date(internal)
            except (ValueError, TypeError):
                stats["skipped"] += 1
                continue

            try:
                lead_days = json.loads(d["escalation_lead_days"] or "[]")
            except (json.JSONDecodeError, TypeError):
                lead_days = [7, 3, 1, 0]
            try:
                sent = set(json.loads(d["reminders_sent"] or "[]"))
            except (json.JSONDecodeError, TypeError):
                sent = set()

            days_left = _workdays_between(today, internal_d, db)
            matter_no = d["matter_no"] or f"#{d['matter_id']}"
            title = d["matter_title"] or ""
            desc = d["description"] or d["type"]
            basis = d["statutory_basis"] or ""
            severity = d["severity"] or ""
            # 承辦律師：deadline.assignee 優先、否則案件 lead_attorney（SPEC「全所一份」下放進 summary
            # 文字、讓老闆/全所看得到「承辦：某律師」；不再當 channel_id 污染 OA 欄）。
            attorney = (d["d_assignee"] or d["lead_attorney"] or "").strip()
            atty_text = f" 承辦：{attorney}" if attorney else ""
            # 承辦律師收件人（Task E：提醒歸當責律師、非只 boss）：deadline.assignee_line_user_id 優先、
            # 否則用承辦/lead_attorney 名查 active 員工 line_user_id；查無→'' → enqueue 自動 fallback boss。
            # 承辦律師收件人（Task E）。正規化（codex MED）：assignee_line_user_id 非合法 LINE id
            # （髒值/舊值/空）→ 清空、改走名字查；否則髒值會 (a) 遮蔽名字查 (b) 讓升級分支誤判
            # 「已有承辦」而多送一筆 boss row（同一 boss 收兩筆 deadline_missed）。
            atty_uid = (d["assignee_line_user_id"] or "").strip()
            if not _looks_like_line_user_id(atty_uid):
                atty_uid = ""
            if not atty_uid:
                for _nm in (d["d_assignee"], d["lead_attorney"]):
                    if _nm:
                        _er = db.execute(
                            "SELECT line_user_id FROM employees "
                            "WHERE active=1 AND name=? AND line_user_id IS NOT NULL ORDER BY id LIMIT 1",
                            (_nm,),
                        ).fetchone()
                        if _er and _looks_like_line_user_id((_er["line_user_id"] or "").strip()):
                            atty_uid = _er["line_user_id"].strip()
                            break
            bu = d["m_bu"] or ""
            # needs_manual_review 警語（codex HIGH）：未複核時限仍要推（甚至更要推），但 summary 須明示
            # 「未經律師複核、勿逕依此倒數」、detail 帶 flag——不可把未複核日期當乾淨權威倒數呈現，
            # 否則架空「不確定因素→needs_manual_review、不自動倚賴」的設計目的。
            review_note = (
                "\n[未複核·非權威] 此期限含不確定因素（送達/在途/法版/教示/裁定/消滅時效起算之一）、"
                "尚未經律師複核，請先核對計算無誤再倚賴，勿逕依此倒數。"
                if d["needs_manual_review"] else ""
            )

            changed = False

            # (a) 逾期：每日推 deadline_missed（最高優先、升級合夥人/boss）
            if days_left < 0:
                enqueue_escalation(
                    db,
                    event_type="deadline_missed",
                    summary=(
                        f"【逾期】{matter_no} {title} {desc} "
                        f"內部{internal}（法定{statutory}·{basis}）已逾期，請即啟動回復原狀評估{atty_text}"
                        f"{review_note}"
                    ),
                    detail={
                        "deadline_id": str(d["id"]),
                        "severity": str(severity),
                        "statutory_deadline": str(statutory or ""),
                        "internal_deadline": str(internal),
                        "assignee": str(attorney),
                        "needs_manual_review": str(d["needs_manual_review"] or 0),
                        "kind": "deadline_missed",
                    },
                    actor_user_id="",
                    actor_label="系統·時限掃描",
                    business_unit=bu,
                    target_user_id=atty_uid,  # Task E：承辦先收（無承辦 line→enqueue 自動 fallback boss）
                    # channel_id 留 None（由 BU→OA 解析）；承辦律師資訊進收件人欄＋summary、絕不污染 channel_id。
                    channel_id=None,
                )
                # 升級主管/合夥人監督：承辦存在且≠boss 才另送一筆（去重；boss 未設定則略，承辦那筆已是兜底）。
                _boss_uid = resolve_escalation_target(db, bu)[0] or ""
                if atty_uid and _boss_uid and atty_uid != _boss_uid:
                    enqueue_escalation(
                        db,
                        event_type="deadline_missed",
                        summary=(
                            f"【逾期·升級】{matter_no} {title} {desc} "
                            f"內部{internal}（法定{statutory}）已逾期，承辦 {attorney or '未指定'} 已通知、"
                            f"請主管/合夥人介入回復原狀評估{review_note}"
                        ),
                        detail={
                            "deadline_id": str(d["id"]),
                            "severity": str(severity),
                            "statutory_deadline": str(statutory or ""),
                            "internal_deadline": str(internal),
                            "assignee": str(attorney),
                            "needs_manual_review": str(d["needs_manual_review"] or 0),
                            "kind": "deadline_missed_escalation",
                        },
                        actor_user_id="",
                        actor_label="系統·時限掃描",
                        business_unit=bu,
                        target_user_id=_boss_uid,
                        channel_id=None,
                    )
                stats["missed"] += 1
                continue

            # (b) 命中提醒節點且未發過 → deadline_approaching
            for n in lead_days:
                try:
                    n_int = int(n)
                except (TypeError, ValueError):
                    continue
                if days_left == n_int and n_int not in sent:
                    enqueue_escalation(
                        db,
                        event_type="deadline_approaching",
                        summary=(
                            f"【{matter_no} {title}】{desc} "
                            f"內部{internal}（法定{statutory}·{basis}）剩{n_int}個工作日{atty_text}"
                            f"{review_note}"
                        ),
                        detail={
                            "deadline_id": str(d["id"]),
                            "lead_day": str(n_int),
                            "severity": str(severity),
                            "statutory_deadline": str(statutory or ""),
                            "internal_deadline": str(internal),
                            "assignee": str(attorney),
                            "needs_manual_review": str(d["needs_manual_review"] or 0),
                            "kind": "deadline_approaching",
                        },
                        actor_user_id="",
                        actor_label="系統·時限掃描",
                        business_unit=bu,
                        target_user_id=atty_uid,  # Task E：承辦收（無承辦 line→fallback boss）
                        # channel_id=None（BU→OA 解析）；承辦律師進收件人欄＋summary、不污染 channel_id（codex HIGH-2）。
                        channel_id=None,
                    )
                    sent.add(n_int)
                    changed = True
                    stats["approaching"] += 1

            if changed:
                db.execute(
                    "UPDATE deadlines SET reminders_sent = ? WHERE id = ?",
                    (json.dumps(sorted(sent)), d["id"]),
                )

        # 健康哨兵 heartbeat（#H1）：掃描跑完落一筆「活著」憑證（與本次 enqueue 同原子 commit、
        # 零 deadline 也照寫＝證明掃描器真的有在跑）。watchdog（scan_heartbeat.py）/ 全權限開機
        # readout 據此判斷掃描器是否失聯（時限是否仍在倒數）——靜默掛掉=漏期=執業過失的根因。
        _record_heartbeat(db, HEARTBEAT_SCAN, json.dumps(stats, ensure_ascii=False))

    return stats
