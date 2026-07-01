"""legal-admin 時限計算引擎單元測試（命脈、算錯=執業過失）。

standalone runner（仿 test_smoke_all 的 _assert 框架 + tempfile + sys.exit）；
已加進 conftest.py collect_ignore（避免 pytest collection 撞 sys.exit）。

跑法：
    cd mcp-servers/business-db
    SME_DB_PATH=/tmp/_t_dl.db /abs/.venv/bin/python3 tests/test_deadline_engine.py

涵蓋（依任務要求）：
- 翌日起算（民法§120Ⅱ 始日不算入）
- 末日遇週末/國定假日順延（民法§122）
- 寄存送達 +10（民訴§138Ⅱ）
- 不變期間不可延（引擎不給延長選項——驗 period_type=peremptory 仍正常算 hard）
- buffer 內部期限（hard − buffer，落假日往前對齊上班日）
- needs_manual_review 路徑（囑託送達 / 無當地代理人查無在途）
- 跨假日不停止計算（中間假日全計入、不跳過）
- 限期補正（type=correction / period_type=court_set）：裁定期間強制人工複核 + 缺天數/裁定文號防呆
與 2-3 個司法院試算邏輯 golden cases 交叉驗證（含 01 §2 calc_trace 範例案）。
"""
import atexit
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

# temp DB（office_calendar 種子靠 init_db 套 migration 012）
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
DB_PATH = _tmp.name
_tmp.close()
os.environ["SME_DB_PATH"] = DB_PATH


@atexit.register
def _cleanup():
    try:
        os.unlink(DB_PATH)
    except OSError:
        pass


import server  # noqa: E402

server.DB_PATH = DB_PATH
server.init_db()

# 辦公日曆改由匯入器灌真實整年檔（migration 不再種半套年度、見 012 / codex r4 HIGH）。
# 末日順延 golden case 依賴 2026 真實假日 → 在 setup 匯入 2025+2026 完整 fixture（各 365 天）。
import import_office_calendar as _impcal  # noqa: E402
from shared.db import transaction as _txn0  # noqa: E402

_FIXTURES = os.path.join(HERE, "fixtures")
with _txn0() as _db0:
    _impcal.import_file(_db0, os.path.join(_FIXTURES, "taiwan_calendar_2025.json"))
    _impcal.import_file(_db0, os.path.join(_FIXTURES, "taiwan_calendar_2026.json"))

from shared.db import get_db  # noqa: E402
from shared.deadlines import compute_deadline, is_holiday, STATUTORY_PERIODS  # noqa: E402

passed = 0
failed = 0
failures: list[str] = []


def _assert(name: str, cond: bool, detail: str = ""):
    global passed, failed
    if cond:
        print(f"OK    {name}")
        passed += 1
    else:
        print(f"FAIL  {name}{('  → ' + detail) if detail else ''}")
        failed += 1
        failures.append(name)


db = get_db()


def _calc(**kw):
    kw.setdefault("db", db)
    return compute_deadline(**kw)


# === 0. is_holiday（office_calendar + 預設週末規則）===
print("\n=== is_holiday ===")
_assert("is_holiday: 2026-01-01 元旦（種子平日國定假日）=True", is_holiday("2026-01-01", db) is True)
_assert("is_holiday: 2026-06-19 端午（種子）=True", is_holiday("2026-06-19", db) is True)
_assert("is_holiday: 2026-06-20 週六（無種子→預設週末）=True", is_holiday("2026-06-20", db) is True)
_assert("is_holiday: 2026-06-22 週一（無種子→平日）=False", is_holiday("2026-06-22", db) is False)
# 補班分支（週末 + is_holiday=0 → 上班日）以 synthetic fixture 覆核——migration 不再硬種錯誤的
# 2026 補班（2026 經 ruyut 對賬全年無補班；原 2026-02-07 補班為臆測已移除）。日期用程式算下一個
# 週六/週一、不硬猜星期，明標 test fixture（非真實 DGPA 資料）。
import datetime as _dt0  # noqa: E402
_b0 = _dt0.date(2099, 1, 1)
_syn_sat = (_b0 + _dt0.timedelta(days=(5 - _b0.weekday()) % 7)).isoformat()
_syn_mon = (_dt0.date.fromisoformat(_syn_sat) + _dt0.timedelta(days=2)).isoformat()
db.execute(
    "INSERT OR REPLACE INTO office_calendar (date,is_holiday,description,source) VALUES (?,?,?,?)",
    (_syn_sat, 0, "synthetic 補班（測試 fixture）", "test"))
db.execute(
    "INSERT OR REPLACE INTO office_calendar (date,is_holiday,description,source) VALUES (?,?,?,?)",
    (_syn_mon, 1, "synthetic 平日國定假日（測試 fixture）", "test"))
db.commit()
_assert("is_holiday: synthetic 補班（週六+is_holiday=0）→False（office_calendar 覆寫週末預設）",
        is_holiday(_syn_sat, db) is False)
_assert("is_holiday: synthetic 平日國定假日（週一+is_holiday=1）→True（覆寫平日預設）",
        is_holiday(_syn_mon, db) is True)
# 2026-02-07（週六、移除錯誤補班後無種子）→ 退回週末預設＝True（與 ruyut 2026 一致）
_assert("is_holiday: 2026-02-07 週六（已移除錯誤補班、退週末預設）=True",
        is_holiday("2026-02-07", db) is True)


# === 1. Golden Case 1：民事上訴 normal、翌日起算 + 末日週末順延 ===
print("\n=== Golden 1: 民事上訴 normal（翌日起算 + 末日順延）===")
r1 = _calc(
    period_type="peremptory", statutory_days=20, statutory_basis="民訴§440",
    service_type="normal", service_base_date="2026-03-02", has_local_agent=True, buffer_days=1,
)
_assert("g1: 無 error", "error" not in r1, detail=str(r1.get("error")))
_assert("g1: 送達生效=送達當日 2026-03-02", r1["effective_date"] == "2026-03-02")
_assert("g1: 起算=生效翌日 2026-03-03（民法§120Ⅱ）", r1["start_date"] == "2026-03-03")
_assert("g1: 在途=0（有當地代理人 §162但書）", r1["in_transit_days"] == 0)
# 理論末日 03-22(日)→順延 03-23(一)
_assert("g1: 法定末日=2026-03-23（理論末日 03-22 週日順延）", r1["statutory_deadline"] == "2026-03-23")
# internal = 03-23 - 1 = 03-22(日) → 前移至上班日 03-20(五)
_assert("g1: 內部期限=2026-03-20（hard−1 落週日、前移至上班日）", r1["internal_deadline"] == "2026-03-20")
_assert("g1: 不變期間不需人工複核", r1["needs_manual_review"] is False)
_assert("g1: calc_trace 含『始日不算入』", any("始日不算入" in t for t in r1["calc_trace"]))
_assert("g1: calc_trace 含『末日順延』", any("末日順延" in t for t in r1["calc_trace"]))
_assert("g1: legal_basis 含 民法§120Ⅱ", "民法§120Ⅱ" in r1["legal_basis"])


# === 2. Golden Case 2：寄存送達 +10（01 §2 calc_trace 範例案，對照司法院）===
print("\n=== Golden 2: 寄存送達+10（民訴§138Ⅱ）===")
r2 = _calc(
    period_type="peremptory", statutory_days=20, statutory_basis="刑訴§349",
    service_type="registered_deposit", service_base_date="2026-06-01",
    has_local_agent=True, buffer_days=1,
)
_assert("g2: 無 error", "error" not in r2, detail=str(r2.get("error")))
_assert("g2: 送達生效=寄存日+10=2026-06-11（民訴§138Ⅱ）", r2["effective_date"] == "2026-06-11")
_assert("g2: 起算=生效翌日 2026-06-12", r2["start_date"] == "2026-06-12")
# 理論末日 07-01(三)非假日→不順延（= 01 §2 範例的法定 7/1）
_assert("g2: 法定末日=2026-07-01（07-01 週三非假日、不順延）", r2["statutory_deadline"] == "2026-07-01")
# 內部=07-01 − 1 = 06-30(二)非假日（= 01 §2 範例的內部 6/30）
_assert("g2: 內部期限=2026-06-30（= 01 §2 calc_trace 範例案）", r2["internal_deadline"] == "2026-06-30")
_assert("g2: calc_trace 含寄存生效法條（民訴§138Ⅱ）",
        any("§138" in t for t in r2["calc_trace"]))
# 刑事案 → 回復原狀走刑訴§67
_assert("g2: 刑事案 recovery_window 走 刑訴§67", r2["recovery_window"]["basis"] == "刑訴§67")


# === 3. Golden Case 3：民事抗告 10 日 + 跨國定假日不停止計算 ===
print("\n=== Golden 3: 民事抗告 10 日（跨 228 假日不停止計算）===")
r3 = _calc(
    period_type="peremptory", statutory_days=10, statutory_basis="民訴§487",
    service_type="normal", service_base_date="2026-02-26", has_local_agent=True, buffer_days=1,
)
_assert("g3: 無 error", "error" not in r3, detail=str(r3.get("error")))
_assert("g3: 起算=2026-02-27", r3["start_date"] == "2026-02-27")
# 中間經 02-27(和平紀念日彈休)/02-28(和平紀念日)→照常計入，理論末日 03-08(日)→順延 03-09(一)
_assert("g3: 法定末日=2026-03-09（中間 228 假日全計入、末日週日順延）",
        r3["statutory_deadline"] == "2026-03-09")
_assert("g3: 內部期限=2026-03-06（hard−1 落週日、前移至上班日五）",
        r3["internal_deadline"] == "2026-03-06")
_assert("g3: calc_trace 標明中間假日連續計算",
        any("全計入" in t or "連續計算" in t for t in r3["calc_trace"]))


# === 4. 不變期間不可延：引擎不提供延長、period_type=peremptory 正常算 hard ===
print("\n=== 不變期間（peremptory）===")
r4 = _calc(
    period_type="peremptory", statutory_days=20, statutory_basis="民訴§440",
    service_type="normal", service_base_date="2026-03-02", has_local_agent=True, buffer_days=0,
)
_assert("不變期間: buffer=0 → 內部期限=法定期限（不退讓、無延長機制）",
        r4["internal_deadline"] == r4["statutory_deadline"] == "2026-03-23")


# === 5. buffer 內部期限：buffer=3 ===
print("\n=== buffer 內部期限 ===")
r5 = _calc(
    period_type="statutory", statutory_days=30, statutory_basis="訴願法§14",
    service_type="normal", service_base_date="2026-06-01", has_local_agent=True, buffer_days=3,
)
_assert("buffer: 無 error", "error" not in r5, detail=str(r5.get("error")))
_assert("buffer: buffer_days=3 落欄", r5["buffer_days"] == 3)
# 內部期限應比法定期限早（hard − 3、再對齊上班日）
_assert("buffer: 內部期限 ≤ 法定期限", r5["internal_deadline"] <= r5["statutory_deadline"])
_assert("buffer: 內部期限為上班日（對齊後）", is_holiday(r5["internal_deadline"], db) is False)


# === 6. needs_manual_review 路徑 ===
print("\n=== needs_manual_review ===")
# 6a 囑託送達 → 強制人工複核
r6a = _calc(
    period_type="statutory", statutory_days=20, statutory_basis="民訴§440",
    service_type="commissioned", service_base_date="2026-06-01", has_local_agent=True,
)
_assert("review: 囑託送達 → needs_manual_review=True", r6a["needs_manual_review"] is True)
# 6b 無當地代理人 + 查無在途組合 → 人工複核（在途暫 0）
r6b = _calc(
    period_type="peremptory", statutory_days=20, statutory_basis="民訴§440",
    service_type="normal", service_base_date="2026-06-01",
    has_local_agent=False, court_region="taipei", party_region="kinmen",
)
_assert("review: 無當地代理人+查無在途組合 → needs_manual_review=True",
        r6b["needs_manual_review"] is True)
_assert("review: 查無在途 → 在途暫 0、trace 標明需人工複核在途",
        r6b["in_transit_days"] == 0 and "人工複核" in r6b["in_transit_source"])


# === 7. 在途手動指定（MVP 第二條路）影響 hard ===
print("\n=== 在途手動指定 ===")
r7 = _calc(
    period_type="peremptory", statutory_days=20, statutory_basis="民訴§440",
    service_type="normal", service_base_date="2026-06-01",
    has_local_agent=False, in_transit_days_override=15,
)
_assert("在途: 手動 15 日落欄（不需人工複核）",
        r7["in_transit_days"] == 15 and r7["needs_manual_review"] is False)
# 在途進步驟3（影響 hard）：比無在途晚
r7_no = _calc(
    period_type="peremptory", statutory_days=20, statutory_basis="民訴§440",
    service_type="normal", service_base_date="2026-06-01", has_local_agent=True,
)
_assert("在途: 15 日在途 → 法定末日晚於無在途（在途進 hard 計算、非 buffer）",
        r7["statutory_deadline"] > r7_no["statutory_deadline"])


# === 8. 反捏造：空 statutory_basis 擋下 ===
print("\n=== 反捏造參數驗證 ===")
r8 = _calc(
    period_type="peremptory", statutory_days=20, statutory_basis="",
    service_type="normal", service_base_date="2026-06-01", has_local_agent=True,
)
_assert("反捏造: 空 statutory_basis → error（不算出黑箱期限）", "error" in r8)
r8b = _calc(
    period_type="peremptory", statutory_days=20, statutory_basis="民訴§440",
    service_type="normal", service_base_date="not-a-date", has_local_agent=True,
)
_assert("反捏造: 壞日期格式 → error", "error" in r8b)
r8c = _calc(
    period_type="invalid_type", statutory_days=20, statutory_basis="民訴§440",
    service_type="normal", service_base_date="2026-06-01", has_local_agent=True,
)
_assert("反捏造: 非法 period_type → error", "error" in r8c)


# === 9. 法定期間種子完整性（反捏造：每筆都有 basis）===
print("\n=== 法定期間種子 ===")
for k, v in STATUTORY_PERIODS.items():
    _assert(f"種子 {k}: statutory_basis 非空", bool(v["statutory_basis"].strip()))
    _assert(f"種子 {k}: statutory_days > 0", v["statutory_days"] > 0)
    _assert(f"種子 {k}: period_type 合法",
            v["period_type"] in ("peremptory", "statutory", "court_set", "directory"))
# 抽查關鍵天數（修法版本鎖定）
_assert("種子: 民事上訴=20 日（民訴§440）",
        STATUTORY_PERIODS["appeal_civil"]["statutory_days"] == 20)
_assert("種子: 民事抗告=10 日（民訴§487）",
        STATUTORY_PERIODS["abjection_civil"]["statutory_days"] == 10)
_assert("種子: 刑事上訴=20 日（刑訴§349、109.01.15修正 10→20）",
        STATUTORY_PERIODS["appeal_criminal"]["statutory_days"] == 20)
_assert("種子: 訴願=30 日（訴願法§14）",
        STATUTORY_PERIODS["petition_appeal"]["statutory_days"] == 30)
_assert("種子: 支付命令異議=20 日（民訴§516）",
        STATUTORY_PERIODS["payment_order_objection"]["statutory_days"] == 20)
# 家事：上訴 20 日（訴訟事件）與抗告 10 日（非訟事件）分開、勿混同一 key（workflow MED-6）
_assert("種子: 家事訴訟上訴=20 日（家事§44準用民訴§440）",
        STATUTORY_PERIODS["appeal_family"]["statutory_days"] == 20)
_assert("種子: 家事非訟抗告=10 日不變期間（家事§93）、與上訴 20 日分開",
        STATUTORY_PERIODS["abjection_family"]["statutory_days"] == 10
        and STATUTORY_PERIODS["abjection_family"]["period_type"] == "peremptory"
        and "家事事件法§93" in STATUTORY_PERIODS["abjection_family"]["statutory_basis"])


# === 10. BUG1 回歸：春節緩衝塌陷（連假整段落在 (start, hard] 區間、無上班日可前移）===
# 重現：base 2026-02-13、民事抗告 10 日、buffer=3 → hard=2026-02-23（正確）。
# 修前：internal 靜默停在 2026-02-14（假日）且 calc_trace 謊稱「前移至上班日 2026-02-14」。
# 修後要求：internal 非假日 或 needs_manual_review=True；calc_trace 不得出現「前移至上班日 <某假日>」。
print("\n=== BUG1: 春節緩衝塌陷 ===")
import re  # noqa: E402

r10 = _calc(
    period_type="peremptory", statutory_days=10, statutory_basis="民訴§487",
    service_type="normal", service_base_date="2026-02-13", has_local_agent=True, buffer_days=3,
)
_assert("bug1: 無 error", "error" not in r10, detail=str(r10.get("error")))
_assert("bug1: 法定末日=2026-02-23（不受影響、正確）", r10["statutory_deadline"] == "2026-02-23")
_assert(
    "bug1: internal 非假日 或 needs_manual_review=True（不靜默停在假日）",
    (is_holiday(r10["internal_deadline"], db) is False) or (r10["needs_manual_review"] is True),
    detail=f"internal={r10['internal_deadline']} review={r10['needs_manual_review']}",
)
# fail-toward 設計：緩衝收 0、internal=hard、needs_manual_review=True
_assert("bug1: fail-toward → internal=法定末日（緩衝收0）",
        r10["internal_deadline"] == r10["statutory_deadline"] == "2026-02-23")
_assert("bug1: fail-toward → needs_manual_review=True", r10["needs_manual_review"] is True)
_assert("bug1: internal ≤ hard 恆成立", r10["internal_deadline"] <= r10["statutory_deadline"])
# 反捏造：calc_trace 不得謊稱「前移至上班日 <假日>」
_bad_claims = []
for t in r10["calc_trace"]:
    for m in re.finditer(r"前移至上班日\s*(\d{4}-\d{2}-\d{2})", t):
        d_claimed = m.group(1)
        if is_holiday(d_claimed, db):
            _bad_claims.append((d_claimed, t))
_assert("bug1: calc_trace 無『前移至上班日 <假日>』謊報",
        not _bad_claims, detail=str(_bad_claims))
_assert("bug1: calc_trace 誠實標明緩衝落連假 / 須人工複核",
        any("連假" in t and "人工複核" in t for t in r10["calc_trace"]),
        detail=str(r10["calc_trace"]))


# === 11. BUG1 正常情形不變：回退路徑有上班日 → 照常前移、不誤觸 fail-toward ===
print("\n=== BUG1: 正常情形（回退有上班日）行為不變 ===")
r11 = _calc(
    period_type="peremptory", statutory_days=20, statutory_basis="民訴§440",
    service_type="normal", service_base_date="2026-03-02", has_local_agent=True, buffer_days=1,
)
# 與 Golden 1 同案：hard=03-23、internal=03-20（前移至上班日五）、不需複核
_assert("bug1-normal: 法定末日=2026-03-23", r11["statutory_deadline"] == "2026-03-23")
_assert("bug1-normal: internal=2026-03-20（前移至上班日、非 fail-toward）",
        r11["internal_deadline"] == "2026-03-20")
_assert("bug1-normal: internal 非假日", is_holiday(r11["internal_deadline"], db) is False)
_assert("bug1-normal: 不誤觸 needs_manual_review", r11["needs_manual_review"] is False)


# === 12. BUG2 回歸：跨年（末日落 2027、該年日曆未載入）→ needs_manual_review ===
# base 2026-12-31 normal 1 日 → 生效翌日 2027-01-01 為理論末日（2027 office_calendar 完全無紀錄）。
print("\n=== BUG2: 跨年日曆未載入 ===")
r12 = _calc(
    period_type="statutory", statutory_days=1, statutory_basis="民訴§440",
    service_type="normal", service_base_date="2026-12-31", has_local_agent=True, buffer_days=0,
)
_assert("bug2: 無 error", "error" not in r12, detail=str(r12.get("error")))
_assert("bug2: 末日落 2027（跨年）", r12["statutory_deadline"][:4] == "2027",
        detail=r12["statutory_deadline"])
_assert("bug2: 2027 日曆未載入 → needs_manual_review=True", r12["needs_manual_review"] is True)
_assert("bug2: calc_trace 誠實標明『辦公日曆未完整載入(0/365)』+ 須人工複核",
        any("辦公日曆未完整載入" in t and "0/365" in t and "人工複核" in t for t in r12["calc_trace"]),
        detail=str(r12["calc_trace"]))
# 2026 全程（不跨年）不應誤觸日曆未載入
r12b = _calc(
    period_type="statutory", statutory_days=20, statutory_basis="民訴§440",
    service_type="normal", service_base_date="2026-06-01", has_local_agent=True, buffer_days=1,
)
_assert("bug2: 2026 全程不誤觸日曆未載入複核", r12b["needs_manual_review"] is False)

# 半套年度（legacy DB 殘留）：trace 須據實標「未完整載入（n/365）」、不可謊稱「完全無紀錄」（codex r5 MED）
import datetime as _dt12  # noqa: E402
for _i in range(5):  # 只塞 5 天 2031（半套）
    _d = _dt12.date(2031, 3, 1) + _dt12.timedelta(days=_i)
    db.execute(
        "INSERT OR REPLACE INTO office_calendar (date,is_holiday,description,source) VALUES (?,?,?,?)",
        (_d.isoformat(), 1 if _d.weekday() >= 5 else 0, "", "synthetic-partial"))
db.commit()
r12c = _calc(
    period_type="peremptory", statutory_days=20, statutory_basis="民訴§440",
    service_type="normal", service_base_date="2031-03-10", has_local_agent=True, buffer_days=1,
)
_assert("bug2: 半套 2031 → needs_manual_review=True", r12c["needs_manual_review"] is True)
_assert("bug2: 半套年度 trace 標『未完整載入(5/365)』、不謊稱『完全無紀錄』(反捏造)",
        any("未完整載入" in t and "5/365" in t for t in r12c["calc_trace"])
        and not any("完全無紀錄" in t for t in r12c["calc_trace"]),
        detail=str([t for t in r12c["calc_trace"] if "辦公日曆" in t]))


# === 13. 不變量：凡 calc_trace 聲稱為上班日的日期、用 is_holiday 斷言確實非假日 ===
# 一批 buffer×base 隨機輸入，掃描所有 trace、抓「前移至上班日 X」「X 為上班日」的宣稱、逐一驗。
print("\n=== 不變量：calc_trace 宣稱的上班日必非假日 ===")
import random  # noqa: E402

random.seed(42)
_invariant_violations = []
_invariant_checked = 0
_workday_claim = re.compile(r"(?:前移至上班日|為上班日)\s*(\d{4}-\d{2}-\d{2})")
_base_pool = [
    "2026-02-10", "2026-02-13", "2026-02-23", "2026-03-02", "2026-04-01",
    "2026-04-30", "2026-06-15", "2026-09-20", "2026-10-05", "2026-12-20",
]
for _bd in _base_pool:
    for _buf in range(0, 6):
        for _sd in (10, 20, 30):
            rr = _calc(
                period_type="peremptory", statutory_days=_sd, statutory_basis="民訴§440",
                service_type="normal", service_base_date=_bd,
                has_local_agent=True, buffer_days=_buf,
            )
            if "error" in rr:
                continue
            # 恆等式：internal ≤ hard 永遠成立
            if rr["internal_deadline"] > rr["statutory_deadline"]:
                _invariant_violations.append(
                    (_bd, _buf, _sd, "internal>hard", rr["internal_deadline"], rr["statutory_deadline"])
                )
            for t in rr["calc_trace"]:
                for m in _workday_claim.finditer(t):
                    _invariant_checked += 1
                    dc = m.group(1)
                    if is_holiday(dc, db):
                        _invariant_violations.append((_bd, _buf, _sd, "claimed-workday-is-holiday", dc, t))
_assert(
    f"不變量: calc_trace 宣稱的上班日全部非假日（驗 {_invariant_checked} 筆宣稱）+ internal≤hard",
    not _invariant_violations,
    detail=str(_invariant_violations[:5]),
)


# === 14. MED-3 回歸：在途查表（transit_period）路徑命中 ===
# 修前：create_deadline 把 court_region/party_region 硬塞空字串 → lookup_transit_days 永遠 miss，
#       transit_period 表形同死資料。修後：無當地代理人 + 帶 region 且查得到表 → 在途天數正確進計算。
print("\n=== MED-3: 在途查表 transit_period 路徑命中 ===")
# 種一筆在途列（temp DB；不碰主庫）：金門當事人 → 台北地院 12 日
db.execute(
    "INSERT OR REPLACE INTO transit_period (court_region, party_region, days, basis_version, note) "
    "VALUES ('taipei', 'kinmen', 12, '司法院在途期間標準 B0010020 v107.7.1（測試種子）', 'MED-3 test')"
)
db.commit()

# (a) has_local_agent=False + 有 region 且查得到 → 在途=12 命中、無需人工複核
r14 = _calc(
    period_type="peremptory", statutory_days=20, statutory_basis="民訴§440",
    service_type="normal", service_base_date="2026-06-01",
    has_local_agent=False, court_region="taipei", party_region="kinmen", buffer_days=1,
)
_assert("med3: 無 error", "error" not in r14, detail=str(r14.get("error")))
_assert("med3: 在途查表命中=12 日（非空字串 miss）", r14["in_transit_days"] == 12,
        detail=f"in_transit_days={r14['in_transit_days']}")
_assert("med3: 查得到 → 不需人工複核", r14["needs_manual_review"] is False,
        detail=str(r14.get("in_transit_source")))
_assert("med3: in_transit_source 標查表依據+版本",
        "查表" in (r14["in_transit_source"] or "") and "B0010020" in (r14["in_transit_source"] or ""),
        detail=str(r14.get("in_transit_source")))
_assert("med3: calc_trace 含在途查表步驟",
        any("在途=12" in t for t in r14["calc_trace"]), detail=str(r14["calc_trace"]))
# 在途 12 日確實進 hard 計算：比無在途版本晚
r14_no = _calc(
    period_type="peremptory", statutory_days=20, statutory_basis="民訴§440",
    service_type="normal", service_base_date="2026-06-01", has_local_agent=True, buffer_days=1,
)
_assert("med3: 在途 12 日進 hard 計算（法定末日晚於無在途）",
        r14["statutory_deadline"] > r14_no["statutory_deadline"],
        detail=f"{r14['statutory_deadline']} vs {r14_no['statutory_deadline']}")

# (b) 查不到組合 → 維持既有 fail-toward（needs_manual_review + 在途暫 0）
r14b = _calc(
    period_type="peremptory", statutory_days=20, statutory_basis="民訴§440",
    service_type="normal", service_base_date="2026-06-01",
    has_local_agent=False, court_region="taipei", party_region="不存在的區域XYZ", buffer_days=1,
)
_assert("med3: 查不到 region 組合 → fail-toward needs_manual_review",
        r14b["needs_manual_review"] is True and r14b["in_transit_days"] == 0,
        detail=str(r14b.get("in_transit_source")))

# (c) 經 service.create_deadline 端到端：在途值正確落欄（證明 tool→service→compute 接通、非死資料）
import json as _json14  # noqa: E402
from modules.deadlines import service as _svc14  # noqa: E402

_mid14 = db.execute(
    "INSERT INTO matters (matter_no, title, status, has_local_agent, confidential) "
    "VALUES ('2026-med3-001', 'MED-3 在途案', 'open', 0, 0)"
).lastrowid
db.commit()
_r14e = _svc14.create_deadline(
    matter_id=_mid14, type="appeal_civil", description="", trigger_event="一審判決送達",
    service_base_date="2026-06-01", service_type="normal",
    statutory_days=0, statutory_basis="", statutory_basis_version="", period_type="",
    severity="", has_local_agent=0, in_transit_days=0,
    court_region="taipei", party_region="kinmen", buffer_days=1, stated_period_days=0,
    document_date="", assignee="", assignee_line_user_id="", escalation_lead_days="", created_by="測試",
)
_assert("med3: service.create_deadline 端到端成功", "時限" in _r14e and "已建立" in _r14e,
        detail=_r14e)
_d14 = db.execute(
    "SELECT in_transit_days, in_transit_source, needs_manual_review FROM deadlines "
    "WHERE matter_id=? ORDER BY id DESC LIMIT 1", (_mid14,)
).fetchone()
_assert("med3: 端到端在途天數正確落欄=12（非硬塞空字串 miss 的 0）",
        _d14 and _d14["in_transit_days"] == 12,
        detail=str(dict(_d14)) if _d14 else "None")
_assert("med3: 端到端查得到 → 不誤標人工複核",
        _d14 and _d14["needs_manual_review"] == 0)


# === 安全網 A：法版檢核（判決日 vs 修法施行日，反捏造、不臆測重算舊法）===
print("\n=== 安全網 A：法版檢核（刑訴§349 / §406 修法日）===")
# 刑訴§349 上訴期間 2020-01-15 由 10→20。早於此日的文書 → 須人工複核。
_la349_old = compute_deadline(
    period_type="peremptory", statutory_days=20, statutory_basis="刑訴§349",
    service_type="normal", service_base_date="2019-03-01", has_local_agent=True)
_assert("法版A: 2020 刑訴§349 判決(早於2020-01-15) → needs_manual_review",
        _la349_old["needs_manual_review"] is True,
        detail=str([t for t in _la349_old["calc_trace"] if "法版" in t]))
_assert("法版A: calc_trace 誠實標明修法施行日 + 修正前 10 日(不謊報、不重算)",
        any("法版檢核" in t and "2020-01-15" in t and "10 日" in t
            for t in _la349_old["calc_trace"]))
# 邊界：恰在施行日當天 → base < eff 為 strict、不觸發（適用新法）
_la349_edge = compute_deadline(
    period_type="peremptory", statutory_days=20, statutory_basis="刑訴§349",
    service_type="normal", service_base_date="2020-01-15", has_local_agent=True)
_assert("法版A: 施行日當天(2020-01-15) → 不觸發法版複核(適用新法)",
        not any("法版檢核" in t for t in _la349_edge["calc_trace"]))
# 現行文書 → 不觸發
_la349_new = compute_deadline(
    period_type="peremptory", statutory_days=20, statutory_basis="刑訴§349",
    service_type="normal", service_base_date="2024-03-01", has_local_agent=True)
_assert("法版A: 2024 刑訴§349 → 不誤觸發法版複核",
        not any("法版檢核" in t for t in _la349_new["calc_trace"]))
# 刑訴§406 抗告 2023-06-21 由 5→10。2022 文書 → 須複核。
_la406_old = compute_deadline(
    period_type="peremptory", statutory_days=10, statutory_basis="刑訴§406",
    service_type="normal", service_base_date="2022-08-01", has_local_agent=True)
_assert("法版A: 2022 刑訴§406 抗告(早於2023-06-21) → needs_manual_review",
        _la406_old["needs_manual_review"] is True
        and any("法版檢核" in t and "5 日" in t for t in _la406_old["calc_trace"]))
# 民訴§440 不在沿革表 → 舊文書不誤報法版（反捏造：寧缺勿錯、未查證的不亂標）
_civ_old = compute_deadline(
    period_type="peremptory", statutory_days=20, statutory_basis="民訴§440",
    service_type="normal", service_base_date="2015-03-01", has_local_agent=True)
_assert("法版A: 民訴§440(未編沿革) 舊文書 → 不誤報法版複核",
        not any("法版檢核" in t for t in _civ_old["calc_trace"]))

# --- MED-3：精準條號比對（不可裸子字串誤命中 / 漏報）---
# 刑訴§349之1 是另一條（非上訴期間）→ 舊文書不可被當 §349 誤觸發法版（假陽性）
_la349sub = compute_deadline(
    period_type="peremptory", statutory_days=20, statutory_basis="刑訴§349之1",
    service_type="normal", service_base_date="2019-03-01", has_local_agent=True)
_assert("法版MED3: 刑訴§349之1(另一條) 舊文書 → 不誤觸發法版(無假陽性)",
        not any("法版檢核" in t for t in _la349sub["calc_trace"]))
# 全名寫法「刑事訴訟法第349條」舊文書 → 仍須命中（不可因寫法不同漏報）
_la349full = compute_deadline(
    period_type="peremptory", statutory_days=20, statutory_basis="刑事訴訟法第349條",
    service_type="normal", service_base_date="2019-03-01", has_local_agent=True)
_assert("法版MED3: 刑事訴訟法第349條(全名) 舊文書 → 仍命中法版(不漏報)",
        _la349full["needs_manual_review"] is True
        and any("法版檢核" in t for t in _la349full["calc_trace"]))

# --- HIGH-1：法版適用依「文書作成日」而非送達日（舊判決可能修法後才送達）---
# 判決作成 2020-01-10（早於 §349 修法）但 2021-07-01 才送達：給 document_date → 應命中
_la349_doc = compute_deadline(
    period_type="peremptory", statutory_days=20, statutory_basis="刑訴§349",
    service_type="normal", service_base_date="2021-07-01", has_local_agent=True,
    document_date="2020-01-10")
_assert("法版HIGH1: 文書作成日早於修法(送達在後) → 命中法版複核(用文書作成日、非送達日)",
        _la349_doc["needs_manual_review"] is True
        and any("法版檢核" in t and "文書作成日2020-01-10" in t for t in _la349_doc["calc_trace"]))
# 同送達日但未給 document_date → 以送達日(2021-07-01、在修法後)近似 → 不命中，且 trace 須誠實標明近似
_la349_nodoc = compute_deadline(
    period_type="peremptory", statutory_days=20, statutory_basis="刑訴§349",
    service_type="normal", service_base_date="2021-07-01", has_local_agent=True)
_assert("法版HIGH1: 未給文書作成日、送達在修法後 → 不誤報(以送達日近似)",
        not any("法版檢核" in t for t in _la349_nodoc["calc_trace"]))
# 未給 document_date 但送達日本身早於修法 → 命中，trace 標「送達日近似」（誠實、不謊稱精確）
_la349_nodoc_old = compute_deadline(
    period_type="peremptory", statutory_days=20, statutory_basis="刑訴§349",
    service_type="normal", service_base_date="2019-03-01", has_local_agent=True)
_assert("法版HIGH1: 未給文書作成日、送達日早於修法 → 命中且 trace 標『送達日近似』(反捏造)",
        _la349_nodoc_old["needs_manual_review"] is True
        and any("法版檢核" in t and "送達日" in t and "近似" in t
                for t in _la349_nodoc_old["calc_trace"]))
# document_date 格式錯誤 → 回 error（不靜默退回送達日近似、不繞過法版、不落髒資料，codex R2 HIGH）
_la_baddoc = compute_deadline(
    period_type="peremptory", statutory_days=20, statutory_basis="刑訴§349",
    service_type="normal", service_base_date="2021-07-01", has_local_agent=True,
    document_date="2021/06/10")
_assert("法版HIGH1: 壞格式 document_date → 回 error(不靜默近似、反捏造)",
        "error" in _la_baddoc and "document_date" in _la_baddoc["error"],
        detail=str(_la_baddoc))


# === 安全網 B：教示比對（判決書上訴教示天數 vs 引擎採用天數）===
print("\n=== 安全網 B：教示比對 ===")
_pm_match = compute_deadline(
    period_type="peremptory", statutory_days=20, statutory_basis="民訴§440",
    service_type="normal", service_base_date="2026-06-01", has_local_agent=True,
    stated_period_days=20)
_assert("教示B: 教示20=引擎20 → period_match='match'",
        _pm_match["period_match"] == "match" and _pm_match["stated_period_days"] == 20)
_pm_mis = compute_deadline(
    period_type="peremptory", statutory_days=20, statutory_basis="民訴§440",
    service_type="normal", service_base_date="2026-06-01", has_local_agent=True,
    stated_period_days=10)
_assert("教示B: 教示10≠引擎20 → period_match='mismatch' + needs_manual_review",
        _pm_mis["period_match"] == "mismatch" and _pm_mis["needs_manual_review"] is True,
        detail=str([t for t in _pm_mis["calc_trace"] if "教示" in t]))
_pm_none = compute_deadline(
    period_type="peremptory", statutory_days=20, statutory_basis="民訴§440",
    service_type="normal", service_base_date="2026-06-01", has_local_agent=True)
_assert("教示B: 未提供教示 → 'not_provided'、不影響 needs_manual_review",
        _pm_none["period_match"] == "not_provided"
        and _pm_none["needs_manual_review"] is False
        and _pm_none["stated_period_days"] is None)
_pm_bad = compute_deadline(
    period_type="peremptory", statutory_days=20, statutory_basis="民訴§440",
    service_type="normal", service_base_date="2026-06-01", has_local_agent=True,
    stated_period_days="非數字")
_assert("教示B: 教示非數字（如OCR「二十日」）→ 'unparseable' + needs_manual_review（安全網不靜默旁路，codex MED）",
        _pm_bad["period_match"] == "unparseable" and _pm_bad["needs_manual_review"] is True
        and any("無法解析" in t for t in _pm_bad["calc_trace"]))


# === 安全網端到端（service.create_deadline 落欄）+ 行事曆回填 ===
print("\n=== 安全網端到端 + 行事曆回填 ===")
from modules.deadlines import service as _svcSN  # noqa: E402

_midSN = db.execute(
    "INSERT INTO matters (matter_no, title, status, has_local_agent, confidential) "
    "VALUES ('2026-sn-001', '安全網案', 'open', 1, 0)"
).lastrowid
db.commit()
# 教示不符端到端 → stated_period_days 落欄 + needs_manual_review=1
_rSN = _svcSN.create_deadline(
    matter_id=_midSN, type="appeal_civil", description="", trigger_event="一審判決送達",
    service_base_date="2026-06-01", service_type="normal",
    statutory_days=0, statutory_basis="", statutory_basis_version="", period_type="",
    severity="", has_local_agent=-1, in_transit_days=0,
    court_region="", party_region="", buffer_days=1, stated_period_days=15,
    document_date="", assignee="", assignee_line_user_id="", escalation_lead_days="", created_by="測試",
)
_assert("端到端: create_deadline 教示15≠20 仍建立成功", "已建立" in _rSN, detail=_rSN)
_dSN = db.execute(
    "SELECT id, stated_period_days, needs_manual_review, calendar_event_id "
    "FROM deadlines WHERE matter_id=? ORDER BY id DESC LIMIT 1", (_midSN,)
).fetchone()
_assert("端到端: stated_period_days=15 落欄", _dSN and _dSN["stated_period_days"] == 15,
        detail=str(dict(_dSN)) if _dSN else "None")
_assert("端到端: 教示不符 → needs_manual_review=1", _dSN and _dSN["needs_manual_review"] == 1)
_assert("端到端: 行事曆未同步時 calendar_event_id 為空", _dSN and _dSN["calendar_event_id"] is None)

# 行事曆回填（calendar-agnostic）
_rcal = _svcSN.mark_deadline_calendared(
    deadline_id=_dSN["id"], calendar_event_id="gcal_evt_abc123",
    calendar_provider="google", marked_by="測試")
_assert("行事曆: mark_deadline_calendared 成功", "已回填行事曆對位" in _rcal, detail=_rcal)
_dcal = db.execute(
    "SELECT calendar_event_id, calendar_provider, calendar_synced_at FROM deadlines WHERE id=?",
    (_dSN["id"],)
).fetchone()
_assert("行事曆: event_id/provider/synced_at 落欄",
        _dcal and _dcal["calendar_event_id"] == "gcal_evt_abc123"
        and _dcal["calendar_provider"] == "google" and _dcal["calendar_synced_at"],
        detail=str(dict(_dcal)) if _dcal else "None")
_assert("行事曆: 空 event_id 被擋",
        "ERROR" in _svcSN.mark_deadline_calendared(
            deadline_id=_dSN["id"], calendar_event_id="", calendar_provider="", marked_by="x"))

# document_date 端到端落欄（法版檢核基準、審計留底）
_rDoc = _svcSN.create_deadline(
    matter_id=_midSN, type="appeal_criminal", description="", trigger_event="一審判決送達",
    service_base_date="2021-07-01", service_type="normal",
    statutory_days=0, statutory_basis="", statutory_basis_version="", period_type="",
    severity="", has_local_agent=-1, in_transit_days=0,
    court_region="", party_region="", buffer_days=1, stated_period_days=0,
    document_date="2020-01-10", assignee="", assignee_line_user_id="", escalation_lead_days="", created_by="測試",
)
_dDoc = db.execute(
    "SELECT document_date, needs_manual_review FROM deadlines WHERE matter_id=? ORDER BY id DESC LIMIT 1",
    (_midSN,)
).fetchone()
_assert("端到端: document_date='2020-01-10' 落欄", _dDoc and _dDoc["document_date"] == "2020-01-10",
        detail=str(dict(_dDoc)) if _dDoc else "None")
_assert("端到端: 文書作成日早於修法 → needs_manual_review=1（用 document_date 非送達日）",
        _dDoc and _dDoc["needs_manual_review"] == 1)
# 壞格式 document_date → service 擋下、不建單、不落髒資料（codex R2 HIGH）
_cnt_before_bad = db.execute(
    "SELECT COUNT(*) FROM deadlines WHERE matter_id=?", (_midSN,)).fetchone()[0]
_rBadDoc = _svcSN.create_deadline(
    matter_id=_midSN, type="appeal_criminal", description="", trigger_event="一審判決送達",
    service_base_date="2021-07-01", service_type="normal",
    statutory_days=0, statutory_basis="", statutory_basis_version="", period_type="",
    severity="", has_local_agent=-1, in_transit_days=0,
    court_region="", party_region="", buffer_days=1, stated_period_days=0,
    document_date="2021/06/10", assignee="", assignee_line_user_id="", escalation_lead_days="", created_by="測試",
)
_assert("端到端: 壞格式 document_date → create_deadline 回 ERROR", "ERROR" in _rBadDoc, detail=_rBadDoc)
_cnt_after_bad = db.execute(
    "SELECT COUNT(*) FROM deadlines WHERE matter_id=?", (_midSN,)).fetchone()[0]
_assert("端到端: 壞格式 document_date → 未落髒資料(count 不變)",
        _cnt_before_bad == _cnt_after_bad,
        detail=f"before={_cnt_before_bad} after={_cnt_after_bad}")


# === 限期補正（type=correction / period_type=court_set）：裁定期間強制人工複核 ===
# 反捏造命脈：補正期間天數由法院在裁定當下載明、非法定固定值（無種子可交叉驗證、教示比對不適用），
# 故 create_deadline 對 court_set 一律強制 needs_manual_review；缺天數/裁定文號給「讀裁定」針對性防呆。
# 漏補正＝駁回起訴，是小所最高頻時限之一。
print("\n=== 限期補正：裁定期間(court_set) 強制複核 ===")
from shared.deadlines import COURT_SET_PERIODS as _CSP  # noqa: E402

# 登記表完整性 + 反捏造結構（與固定天數表本質不同：絕不含 statutory_days 欄）
_assert("補正: correction 已登記於 COURT_SET_PERIODS", "correction" in _CSP)
_corr_seed = _CSP["correction"]
_assert("補正: period_type=court_set", _corr_seed["period_type"] == "court_set")
_assert("補正: severity=orange", _corr_seed["severity"] == "orange")
_assert("補正: label/basis_hint/default_trigger 皆非空",
        bool(_corr_seed.get("label")) and bool(_corr_seed.get("basis_hint"))
        and bool(_corr_seed.get("default_trigger")))
_assert("補正: 結構性無 statutory_days 欄（裁定天數絕不預設、反捏造）",
        "statutory_days" not in _corr_seed)
_assert("補正: COURT_SET_PERIODS 與 STATUTORY_PERIODS 零重疊（兩表本質不同）",
        not (set(_CSP) & set(STATUTORY_PERIODS)))

_midCorr = db.execute(
    "INSERT INTO matters (matter_no, title, status, has_local_agent, confidential) "
    "VALUES ('2026-corr-001', '限期補正案', 'open', 1, 0)"
).lastrowid
db.commit()

# (a) 缺 statutory_days → 針對性 ERROR（讀裁定填、不臆測）、不建單
_cnt_corr0 = db.execute(
    "SELECT COUNT(*) FROM deadlines WHERE matter_id=?", (_midCorr,)).fetchone()[0]
_rNoDays = _svcSN.create_deadline(
    matter_id=_midCorr, type="correction", description="", trigger_event="",
    service_base_date="2026-06-15", service_type="normal",
    statutory_days=0, statutory_basis="臺北地院114年度補字第123號裁定", statutory_basis_version="",
    period_type="", severity="", has_local_agent=-1, in_transit_days=0,
    court_region="", party_region="", buffer_days=1, stated_period_days=0,
    document_date="", assignee="", assignee_line_user_id="", escalation_lead_days="", created_by="王律師",
)
_assert("補正(a): 缺天數 → ERROR 且指引讀裁定", "ERROR" in _rNoDays and "讀裁定" in _rNoDays,
        detail=_rNoDays)
_assert("補正(a): 缺天數 → 不建單（反捏造不臆測）",
        db.execute("SELECT COUNT(*) FROM deadlines WHERE matter_id=?",
                   (_midCorr,)).fetchone()[0] == _cnt_corr0)

# (b) 缺 statutory_basis（裁定文號）→ 針對性 ERROR
_rNoBasis = _svcSN.create_deadline(
    matter_id=_midCorr, type="correction", description="", trigger_event="",
    service_base_date="2026-06-15", service_type="normal",
    statutory_days=10, statutory_basis="", statutory_basis_version="",
    period_type="", severity="", has_local_agent=-1, in_transit_days=0,
    court_region="", party_region="", buffer_days=1, stated_period_days=0,
    document_date="", assignee="", assignee_line_user_id="", escalation_lead_days="", created_by="王律師",
)
_assert("補正(b): 缺裁定文號 → ERROR 且指引填裁定文號",
        "ERROR" in _rNoBasis and "裁定文號" in _rNoBasis, detail=_rNoBasis)

# (c) 帶齊 → court_set/orange 自動回填、強制 needs_manual_review、in_transit=0、算對
_rCorr = _svcSN.create_deadline(
    matter_id=_midCorr, type="correction", description="", trigger_event="",
    service_base_date="2026-06-15", service_type="normal",
    statutory_days=10, statutory_basis="臺北地院114年度補字第123號裁定", statutory_basis_version="",
    period_type="", severity="", has_local_agent=-1, in_transit_days=0,
    court_region="", party_region="", buffer_days=1, stated_period_days=0,
    document_date="", assignee="", assignee_line_user_id="", escalation_lead_days="", created_by="王律師",
)
_assert("補正(c): 帶齊建立成功", "已建立" in _rCorr, detail=_rCorr)
_assert("補正(c): 回覆含需人工複核提示", "需人工複核" in _rCorr)
_dCorr = db.execute(
    "SELECT type, period_type, severity, needs_manual_review, in_transit_days, statutory_days, "
    "description, statutory_deadline, internal_deadline, calc_trace "
    "FROM deadlines WHERE matter_id=? ORDER BY id DESC LIMIT 1", (_midCorr,)
).fetchone()
_assert("補正(c): period_type 自動回填 court_set", _dCorr and _dCorr["period_type"] == "court_set")
_assert("補正(c): severity 自動 orange", _dCorr and _dCorr["severity"] == "orange")
_assert("補正(c): 強制 needs_manual_review=1（裁定天數純人讀、無交叉驗證）",
        _dCorr and _dCorr["needs_manual_review"] == 1)
_assert("補正(c): in_transit=0（裁定期間不適用在途·§162）", _dCorr and _dCorr["in_transit_days"] == 0)
_assert("補正(c): statutory_days=10 落欄（律師讀裁定值、未被回填覆蓋）",
        _dCorr and _dCorr["statutory_days"] == 10)
_assert("補正(c): description 自動填『限期補正』", _dCorr and "限期補正" in (_dCorr["description"] or ""))
_assert("補正(c): calc_trace 記裁定期間強制複核理由（反捏造留痕）",
        _dCorr and "裁定期間" in _dCorr["calc_trace"] and "強制人工複核" in _dCorr["calc_trace"])
# 日期：base 06-15 normal → 生效06-15、起算翌日06-16、span10、理論末日06-25；末日順延只增不減
_assert("補正(c): statutory_deadline ≥ 理論末日 2026-06-25（court_set 算對、順延只增）",
        _dCorr and _dCorr["statutory_deadline"] >= "2026-06-25",
        detail=str(dict(_dCorr)) if _dCorr else "None")
_assert("補正(c): internal ≤ statutory（恆等式）",
        _dCorr and _dCorr["internal_deadline"] <= _dCorr["statutory_deadline"])

# (d) force_review 看 period_type 非 type：自訂 type + period_type=court_set 亦強制複核
_rCustomCS = _svcSN.create_deadline(
    matter_id=_midCorr, type="some_ruling_period", description="法院另定期間",
    trigger_event="裁定送達", service_base_date="2026-06-15", service_type="normal",
    statutory_days=15, statutory_basis="某地院裁定字號", statutory_basis_version="",
    period_type="court_set", severity="", has_local_agent=-1, in_transit_days=0,
    court_region="", party_region="", buffer_days=1, stated_period_days=0,
    document_date="", assignee="", assignee_line_user_id="", escalation_lead_days="", created_by="王律師",
)
_assert("補正(d): 自訂 type + court_set 仍建立", "已建立" in _rCustomCS, detail=_rCustomCS)
_dCustom = db.execute(
    "SELECT needs_manual_review, in_transit_days FROM deadlines "
    "WHERE matter_id=? ORDER BY id DESC LIMIT 1", (_midCorr,)
).fetchone()
_assert("補正(d): force_review 看 period_type（非 type）→ 自訂 type 仍強制複核",
        _dCustom and _dCustom["needs_manual_review"] == 1)
_assert("補正(d): 自訂 court_set 在途亦=0", _dCustom and _dCustom["in_transit_days"] == 0)

# (e) 純函式：court_set in_transit=0 + source 註明裁定期間（引擎分支明確驗）
_csPure = compute_deadline(
    period_type="court_set", statutory_days=10, statutory_basis="北補字第1號",
    service_type="normal", service_base_date="2026-06-15", has_local_agent=True, db=db)
_assert("補正(e): 純函式 court_set in_transit=0", _csPure["in_transit_days"] == 0)
_assert("補正(e): 純函式 in_transit_source 註明裁定期間",
        "裁定期間" in (_csPure["in_transit_source"] or ""))
_assert("補正(e): 純函式 court_set 仍算出 statutory_deadline", bool(_csPure["statutory_deadline"]))

# (f) HIGH 修補：已知 correction 不容 caller 改標 period_type（防法律性質錯置/繞過強制複核）
_cnt_corr_f = db.execute(
    "SELECT COUNT(*) FROM deadlines WHERE matter_id=?", (_midCorr,)).fetchone()[0]
_rPerempt = _svcSN.create_deadline(
    matter_id=_midCorr, type="correction", description="", trigger_event="",
    service_base_date="2026-06-15", service_type="normal",
    statutory_days=10, statutory_basis="北補字第9號", statutory_basis_version="",
    period_type="peremptory", severity="", has_local_agent=-1, in_transit_days=0,
    court_region="", party_region="", buffer_days=1, stated_period_days=0,
    document_date="", assignee="", assignee_line_user_id="", escalation_lead_days="", created_by="王律師",
)
_assert("補正(f): correction 被改標 peremptory → ERROR（裁定期間法律性質固定）",
        "ERROR" in _rPerempt and "court_set" in _rPerempt, detail=_rPerempt)
_assert("補正(f): 被擋 → 不建單",
        db.execute("SELECT COUNT(*) FROM deadlines WHERE matter_id=?",
                   (_midCorr,)).fetchone()[0] == _cnt_corr_f)

# (g) correction 被改標 statutory + 無當地代理人（想偷走在途加算）→ 一樣擋
_rStat = _svcSN.create_deadline(
    matter_id=_midCorr, type="correction", description="", trigger_event="",
    service_base_date="2026-06-15", service_type="normal",
    statutory_days=10, statutory_basis="北補字第9號", statutory_basis_version="",
    period_type="statutory", severity="", has_local_agent=0, in_transit_days=0,
    court_region="taipei", party_region="kinmen", buffer_days=1, stated_period_days=0,
    document_date="", assignee="", assignee_line_user_id="", escalation_lead_days="", created_by="王律師",
)
_assert("補正(g): correction 被改標 statutory（想偷走在途）→ ERROR", "ERROR" in _rStat, detail=_rStat)

# (h) correction 帶教示天數：純函式仍跑教示比對；trace 不得宣稱「教示比對不適用」（codex MED 反不實軌跡）
_rStated = _svcSN.create_deadline(
    matter_id=_midCorr, type="correction", description="", trigger_event="",
    service_base_date="2026-06-15", service_type="normal",
    statutory_days=10, statutory_basis="北補字第10號", statutory_basis_version="",
    period_type="", severity="", has_local_agent=-1, in_transit_days=0,
    court_region="", party_region="", buffer_days=1, stated_period_days=10,
    document_date="", assignee="", assignee_line_user_id="", escalation_lead_days="", created_by="王律師",
)
_assert("補正(h): correction 帶教示天數仍建立", "已建立" in _rStated, detail=_rStated)
_dStated = db.execute(
    "SELECT calc_trace, stated_period_days FROM deadlines WHERE matter_id=? ORDER BY id DESC LIMIT 1",
    (_midCorr,)
).fetchone()
_assert("補正(h): stated_period_days=10 落欄（教示比對確有執行、非跳過）",
        _dStated and _dStated["stated_period_days"] == 10)
_assert("補正(h): calc_trace 不宣稱『教示比對不適用』（純函式仍跑、反不實軌跡）",
        _dStated and "教示比對不適用" not in _dStated["calc_trace"])
_assert("補正(h): calc_trace 仍有強制複核說明", _dStated and "強制人工複核" in _dStated["calc_trace"])

# (i) custom court_set 的 trace 用中性措辭、不誤標「補正期間」（codex MED）
_dCustomTrace = db.execute(
    "SELECT calc_trace FROM deadlines WHERE matter_id=? AND type='some_ruling_period' "
    "ORDER BY id DESC LIMIT 1", (_midCorr,)
).fetchone()
_assert("補正(i): 自訂 court_set trace 不誤標『補正期間』（force_review 涵蓋所有 court_set、措辭中性）",
        _dCustomTrace and "補正期間" not in _dCustomTrace["calc_trace"])
_assert("補正(i): 自訂 court_set trace 仍有強制複核說明",
        _dCustomTrace and "強制人工複核" in _dCustomTrace["calc_trace"])

# (j) 顯式傳合法 period_type='court_set' → 不誤擋、正常建（codex R2：校驗不可誤殺合法）
_rExplicit = _svcSN.create_deadline(
    matter_id=_midCorr, type="correction", description="", trigger_event="",
    service_base_date="2026-06-15", service_type="normal",
    statutory_days=10, statutory_basis="北補字第11號", statutory_basis_version="",
    period_type="court_set", severity="", has_local_agent=-1, in_transit_days=0,
    court_region="", party_region="", buffer_days=1, stated_period_days=0,
    document_date="", assignee="", assignee_line_user_id="", escalation_lead_days="", created_by="王律師",
)
_assert("補正(j): 顯式傳 period_type=court_set（合法）→ 不誤擋、正常建", "已建立" in _rExplicit, detail=_rExplicit)

# (k) court_set + in_transit_days=5（想偷塞在途）→ 仍落欄 in_transit=0（裁定期間分支早於 override、繞不過）
_rOverride = _svcSN.create_deadline(
    matter_id=_midCorr, type="correction", description="", trigger_event="",
    service_base_date="2026-06-15", service_type="normal",
    statutory_days=10, statutory_basis="北補字第12號", statutory_basis_version="",
    period_type="", severity="", has_local_agent=-1, in_transit_days=5,
    court_region="", party_region="", buffer_days=1, stated_period_days=0,
    document_date="", assignee="", assignee_line_user_id="", escalation_lead_days="", created_by="王律師",
)
_dOverride = db.execute(
    "SELECT in_transit_days FROM deadlines WHERE matter_id=? ORDER BY id DESC LIMIT 1", (_midCorr,)
).fetchone()
_assert("補正(k): court_set + in_transit_days=5 仍落欄 in_transit=0（裁定期間不可被在途 override 繞過）",
        _dOverride and _dOverride["in_transit_days"] == 0,
        detail=str(dict(_dOverride)) if _dOverride else "None")

# (l) 反捏造第二道牆：statutory_days truthy 字串 '0'/'00' 不可繞過 → ERROR 不建單（codex R2 MED）
_cnt_corr_l = db.execute(
    "SELECT COUNT(*) FROM deadlines WHERE matter_id=?", (_midCorr,)).fetchone()[0]
for _bad_days in ("0", "00"):
    _rZero = _svcSN.create_deadline(
        matter_id=_midCorr, type="correction", description="", trigger_event="",
        service_base_date="2026-06-15", service_type="normal",
        statutory_days=_bad_days, statutory_basis="北補字第13號", statutory_basis_version="",
        period_type="", severity="", has_local_agent=-1, in_transit_days=0,
        court_region="", party_region="", buffer_days=1, stated_period_days=0,
        document_date="", assignee="", assignee_line_user_id="", escalation_lead_days="", created_by="測試",
    )
    _assert(f"補正(l): statutory_days={_bad_days!r}（truthy 字串）→ 正規化後 ERROR（反捏造第二道牆）",
            "ERROR" in _rZero, detail=_rZero)
_assert("補正(l): 字串 0 天 → 不建單",
        db.execute("SELECT COUNT(*) FROM deadlines WHERE matter_id=?",
                   (_midCorr,)).fetchone()[0] == _cnt_corr_l)


# === 機密軸：mark_deadline_calendared 受限層對機密案件擋寫 ===
print("\n=== 機密軸：行事曆回填寫入端 gate ===")
_midC = db.execute(
    "INSERT INTO matters (matter_no, title, status, has_local_agent, confidential) "
    "VALUES ('2026-sn-conf', '機密安全網案', 'open', 1, 1)"
).lastrowid
db.commit()
# 全權限層先建時限（機密案件）
_rC = _svcSN.create_deadline(
    matter_id=_midC, type="appeal_civil", description="", trigger_event="一審判決送達",
    service_base_date="2026-06-01", service_type="normal",
    statutory_days=0, statutory_basis="", statutory_basis_version="", period_type="",
    severity="", has_local_agent=-1, in_transit_days=0,
    court_region="", party_region="", buffer_days=1, stated_period_days=0,
    document_date="", assignee="", assignee_line_user_id="", escalation_lead_days="", created_by="測試",
)
_assert("機密: 全權限層可對機密案件建時限", "已建立" in _rC, detail=_rC)
_dC = db.execute(
    "SELECT id FROM deadlines WHERE matter_id=? ORDER BY id DESC LIMIT 1", (_midC,)
).fetchone()
# 切到受限層（SME_FLOOR=general）→ mark_deadline_calendared 對機密案件須擋；
# 且回覆須與「不存在時限」byte 相同（codex HIGH-2：消除 ID 探測存在性 oracle）
_saved_floor = os.environ.get("SME_FLOOR")
os.environ["SME_FLOOR"] = "general"
try:
    _rblock = _svcSN.mark_deadline_calendared(
        deadline_id=_dC["id"], calendar_event_id="evt_leak", calendar_provider="google",
        marked_by="general層員工")
    # 同一受限層、對「不存在」的時限 id 呼叫 → 取得 not-found 回覆做不可區分比對
    _rNotExist = _svcSN.mark_deadline_calendared(
        deadline_id=999999, calendar_event_id="evt_x", calendar_provider="google",
        marked_by="general層員工")
    _rblock_get = _svcSN.get_deadline(_dC["id"])
    _rblock_matter = _svcSN.get_matter(_midC)
finally:
    if _saved_floor is None:
        os.environ.pop("SME_FLOOR", None)
    else:
        os.environ["SME_FLOOR"] = _saved_floor
_assert("機密: 受限層對機密案件回填行事曆被擋(寫入端 gate)",
        "ERROR" in _rblock, detail=_rblock)
# 不存在的 id 與機密 id 各自回「同一 not-found 模板」（只差 echo 的 id）→ 同 id 探測下不可區分、無 oracle
_assert("機密HIGH-2: 機密時限回覆＝not-found 模板(不洩漏機密屬性、無存在性 oracle)",
        _rblock == f"ERROR: 找不到時限 #{_dC['id']}"
        and _rNotExist == "ERROR: 找不到時限 #999999"
        and "機密" not in _rblock and "無權限" not in _rblock,
        detail=f"conf={_rblock!r} / notexist={_rNotExist!r}")
_assert("機密HIGH-2: get_deadline / get_matter 受限層對機密亦回泛化 not-found(不洩漏存在)",
        "機密" not in _rblock_get and "無權限" not in _rblock_get
        and "機密" not in _rblock_matter and "無權限" not in _rblock_matter,
        detail=f"dl={_rblock_get!r} / matter={_rblock_matter!r}")
_dCleak = db.execute(
    "SELECT calendar_event_id FROM deadlines WHERE id=?", (_dC["id"],)
).fetchone()
_assert("機密: 被擋後 calendar_event_id 未被寫入(無洩漏/無汙染)",
        _dCleak and _dCleak["calendar_event_id"] is None)
# 切回全權限層 → 可正常回填
_rok = _svcSN.mark_deadline_calendared(
    deadline_id=_dC["id"], calendar_event_id="evt_ok", calendar_provider="google", marked_by="老闆")
_assert("機密: 全權限層回填正常(gate 不誤擋全權限)", "已回填行事曆對位" in _rok)


# === 消滅時效（type=limitation / period_unit=year/month）：民§121 曆法 + §128 起算點法律判斷 ===
# 與訴訟期間根本不同：期間是「年/月」（依民§121 相當日之前一日/無相當日月末、§123 連續依曆、不可硬轉
# 天數＝閏年）、起算點是民§128「請求權可行使時」＝法律判斷 → 一律強制複核；無在途、無送達加算、不適用
# 回復原狀。§197 侵權雙時鐘（知悉2年 + 行為10年）。§122 末日順延於消滅時效見解分歧→引擎不臆測順延。
print("\n=== 消滅時效：年/月期間 民§121 曆法 ===")
import datetime as _dtL  # noqa: E402
from shared.deadlines import _statute_period_end, LIMITATION_PERIODS, limitation_type  # noqa: E402

# (純函式) §121 相當日之前一日 / 無相當日→該月末日（但書）
_assert("§121: 2010-01-02+15年→相當日前一日 2025-01-01",
        _statute_period_end(_dtL.date(2010, 1, 2), "year", 15) == (_dtL.date(2025, 1, 1), False))
_assert("§121但書: 2008-02-29(閏)+1年→無相當日→月末 2009-02-28",
        _statute_period_end(_dtL.date(2008, 2, 29), "year", 1) == (_dtL.date(2009, 2, 28), True))
_assert("§121但書: 2010-01-31+1月→無相當日→月末 2010-02-28",
        _statute_period_end(_dtL.date(2010, 1, 31), "month", 1) == (_dtL.date(2010, 2, 28), True))
_assert("§121: 2026-06-15+5年→相當日前一日 2031-06-14",
        _statute_period_end(_dtL.date(2026, 6, 15), "year", 5) == (_dtL.date(2031, 6, 14), False))

# (compute 純函式) §125 15年 golden + 消滅時效特性
_lim125 = compute_deadline(
    period_type="statutory", statutory_days=0, statutory_basis="民法§125",
    service_type="normal", service_base_date="2010-01-01", has_local_agent=True,
    period_unit="year", period_value=15, counting_regime="limitation", db=db)
_assert("§125: 無 error", "error" not in _lim125, detail=str(_lim125.get("error")))
_assert("§125: 起算2010-01-02(§120翌日)、末日2025-01-01(§121相當日前一日)",
        _lim125["start_date"] == "2010-01-02" and _lim125["statutory_deadline"] == "2025-01-01")
_assert("§125: 強制 needs_manual_review（§128 起算點法律判斷）", _lim125["needs_manual_review"] is True)
_assert("§125: 無在途（§128 直接起算）", _lim125["in_transit_days"] == 0)
_assert("§125: 不適用回復原狀（recovery_window 空）", _lim125["recovery_window"] == {})
_assert("§125: period_unit/value 回傳 year/15",
        _lim125["period_unit"] == "year" and _lim125["period_value"] == 15)
_assert("§125: calc_trace 含§121 + §122見解分歧 + §128法律判斷",
        any("§121" in t for t in _lim125["calc_trace"])
        and any("§122" in t and "見解分歧" in t for t in _lim125["calc_trace"])
        and any("§128" in t for t in _lim125["calc_trace"]))

# §122 不自動順延：末日落週六仍依曆、不推次一上班日（消滅時效見解分歧→不臆測）
# 2010-01-04→start 2010-01-05、+15年→相當日2025-01-05、前一日2025-01-04（週六）
_lim_wkend = compute_deadline(
    period_type="statutory", statutory_days=0, statutory_basis="民法§125",
    service_type="normal", service_base_date="2010-01-04", has_local_agent=True,
    period_unit="year", period_value=15, counting_regime="limitation", db=db)
_assert("§122不自動順延: 末日落週六2025-01-04 仍依曆、不順延至下週一",
        _lim_wkend["statutory_deadline"] == "2025-01-04", detail=_lim_wkend["statutory_deadline"])

# 種子完整性 + 三表零重疊
_assert("種子: §126=5年 §127=2年 §197雙=2+10",
        LIMITATION_PERIODS["statute_126"]["period_value"] == 5
        and LIMITATION_PERIODS["statute_127"]["period_value"] == 2
        and LIMITATION_PERIODS["statute_197_2y"]["period_value"] == 2
        and LIMITATION_PERIODS["statute_197_10y"]["period_value"] == 10)
_assert("種子: 消滅時效 period_unit 皆 year、period_type 皆 statutory",
        all(v["period_unit"] == "year" and v["period_type"] == "statutory"
            for v in LIMITATION_PERIODS.values()))
_assert("種子: LIMITATION 與 STATUTORY/COURT_SET 三表零重疊",
        not (set(LIMITATION_PERIODS) & set(STATUTORY_PERIODS))
        and not (set(LIMITATION_PERIODS) & set(_CSP)))

# (service 端到端) §125 種子回填 + 落欄
_midL = db.execute(
    "INSERT INTO matters (matter_no, title, status, has_local_agent, confidential) "
    "VALUES ('2026-lim-001', '消滅時效案', 'open', 1, 0)").lastrowid
db.commit()
_rL = _svcSN.create_deadline(
    matter_id=_midL, type="statute_125", description="", trigger_event="請求權可行使",
    service_base_date="2010-01-01", service_type="normal", statutory_days=0, statutory_basis="",
    statutory_basis_version="", period_type="", severity="", has_local_agent=-1, in_transit_days=0,
    court_region="", party_region="", buffer_days=30, stated_period_days=0, document_date="",
    assignee="", assignee_line_user_id="", escalation_lead_days="", created_by="王律師")
_assert("§125端到端: 建立成功 + 需人工複核提示", "已建立" in _rL and "需人工複核" in _rL, detail=_rL[:120])
_dL = db.execute(
    "SELECT type,period_unit,period_value,statutory_days,period_type,severity,"
    "statutory_deadline,needs_manual_review,in_transit_days,recovery_window "
    "FROM deadlines WHERE matter_id=? ORDER BY id DESC LIMIT 1", (_midL,)).fetchone()
_assert("§125端到端: period_unit=year/period_value=15/period_type=statutory 落欄",
        _dL and _dL["period_unit"] == "year" and _dL["period_value"] == 15
        and _dL["period_type"] == "statutory")
_assert("§125端到端: 末日2025-01-01、強制複核、無在途、recovery空",
        _dL and _dL["statutory_deadline"] == "2025-01-01" and _dL["needs_manual_review"] == 1
        and _dL["in_transit_days"] == 0 and _dL["recovery_window"] == "{}")

# §197 雙時鐘：2年(知悉)+10年(行為) 各建一筆、不同起算日
_svcSN.create_deadline(
    matter_id=_midL, type="statute_197_2y", description="", trigger_event="知有損害",
    service_base_date="2024-03-01", service_type="normal", statutory_days=0, statutory_basis="",
    statutory_basis_version="", period_type="", severity="", has_local_agent=-1, in_transit_days=0,
    court_region="", party_region="", buffer_days=14, stated_period_days=0, document_date="",
    assignee="", assignee_line_user_id="", escalation_lead_days="", created_by="王律師")
_svcSN.create_deadline(
    matter_id=_midL, type="statute_197_10y", description="", trigger_event="侵權行為時",
    service_base_date="2020-05-10", service_type="normal", statutory_days=0, statutory_basis="",
    statutory_basis_version="", period_type="", severity="", has_local_agent=-1, in_transit_days=0,
    court_region="", party_region="", buffer_days=30, stated_period_days=0, document_date="",
    assignee="", assignee_line_user_id="", escalation_lead_days="", created_by="王律師")
_d197 = db.execute(
    "SELECT type,period_value,service_base_date,statutory_deadline FROM deadlines "
    "WHERE matter_id=? AND type LIKE 'statute_197%' ORDER BY id", (_midL,)).fetchall()
_assert("§197雙時鐘: 建出兩筆(2年+10年)、起算日不同",
        len(_d197) == 2 and {r["period_value"] for r in _d197} == {2, 10}
        and len({r["service_base_date"] for r in _d197}) == 2,
        detail=str([dict(r) for r in _d197]))
_d197_map = {r["type"]: r["statutory_deadline"] for r in _d197}
_assert("§197雙時鐘: 2年末日2026-03-01(start2024-03-02+2y前一日)、10年末日2030-05-10",
        _d197_map.get("statute_197_2y") == "2026-03-01"
        and _d197_map.get("statute_197_10y") == "2030-05-10", detail=str(_d197_map))

# 防呆：limitation 改標 period_type → 拒；自訂 limitation 缺 period_value → 拒
_rBadPt = _svcSN.create_deadline(
    matter_id=_midL, type="statute_125", description="", trigger_event="x",
    service_base_date="2010-01-01", service_type="normal", statutory_days=0, statutory_basis="",
    statutory_basis_version="", period_type="peremptory", severity="", has_local_agent=-1,
    in_transit_days=0, court_region="", party_region="", buffer_days=0, stated_period_days=0,
    document_date="", assignee="", assignee_line_user_id="", escalation_lead_days="", created_by="x")
_assert("防呆: statute_125 被改標 peremptory → ERROR（消滅時效法律性質固定）",
        "ERROR" in _rBadPt, detail=_rBadPt[:80])
_rNoPv = _svcSN.create_deadline(
    matter_id=_midL, type="limitation", description="自訂時效", trigger_event="可行使",
    service_base_date="2020-01-01", service_type="normal", statutory_days=0, statutory_basis="民法§125",
    statutory_basis_version="", period_type="statutory", severity="", has_local_agent=-1,
    in_transit_days=0, court_region="", party_region="", buffer_days=0, stated_period_days=0,
    document_date="", assignee="", assignee_line_user_id="", escalation_lead_days="", created_by="x",
    period_unit="year", period_value=0)
_assert("防呆: 自訂 limitation 缺 period_value → ERROR", "ERROR" in _rNoPv, detail=_rNoPv[:80])

# 向後相容：日數路徑（上訴 day）完全不受 period_unit 影響（預設 day、走原邏輯）
_compat = compute_deadline(
    period_type="peremptory", statutory_days=20, statutory_basis="民訴§440",
    service_type="normal", service_base_date="2026-03-02", has_local_agent=True, buffer_days=1, db=db)
_assert("向後相容: day 路徑 statutory_days=20 仍走原邏輯（末日2026-03-23、period_unit=day）",
        _compat["statutory_deadline"] == "2026-03-23" and _compat["period_unit"] == "day"
        and _compat["period_value"] is None, detail=_compat["statutory_deadline"])

# === 消滅時效 codex HIGH/MED 修補回歸 ===
print("\n=== 消滅時效 codex 修補回歸 ===")
# (HIGH-1) generic type='limitation' 不可走 day 路徑 → ERROR（否則消滅時效被當訴訟期間算成 N 日）
_rGenDay = _svcSN.create_deadline(
    matter_id=_midL, type="limitation", description="自訂時效", trigger_event="可行使",
    service_base_date="2020-01-01", service_type="normal", statutory_days=20, statutory_basis="民法§125",
    statutory_basis_version="", period_type="statutory", severity="", has_local_agent=-1,
    in_transit_days=0, court_region="", party_region="", buffer_days=0, stated_period_days=0,
    document_date="", assignee="", assignee_line_user_id="", escalation_lead_days="", created_by="x")
_assert("修補HIGH1: generic limitation + period_unit=day → ERROR（不可走日數路徑）",
        "ERROR" in _rGenDay and "year" in _rGenDay, detail=_rGenDay[:90])

# (HIGH-2) seed period_unit/period_value 不可竄改：statute_125 改 month / 改 5 → ERROR
_rTamperU = _svcSN.create_deadline(
    matter_id=_midL, type="statute_125", description="", trigger_event="可行使",
    service_base_date="2020-01-01", service_type="normal", statutory_days=0, statutory_basis="",
    statutory_basis_version="", period_type="", severity="", has_local_agent=-1, in_transit_days=0,
    court_region="", party_region="", buffer_days=0, stated_period_days=0, document_date="",
    assignee="", assignee_line_user_id="", escalation_lead_days="", created_by="x",
    period_unit="month", period_value=0)
_assert("修補HIGH2: statute_125 period_unit 改 month → ERROR", "ERROR" in _rTamperU, detail=_rTamperU[:80])
_rTamperV = _svcSN.create_deadline(
    matter_id=_midL, type="statute_125", description="", trigger_event="可行使",
    service_base_date="2020-01-01", service_type="normal", statutory_days=0, statutory_basis="",
    statutory_basis_version="", period_type="", severity="", has_local_agent=-1, in_transit_days=0,
    court_region="", party_region="", buffer_days=0, stated_period_days=0, document_date="",
    assignee="", assignee_line_user_id="", escalation_lead_days="", created_by="x",
    period_unit="year", period_value=5)
_assert("修補HIGH2: statute_125 period_value 改 5 → ERROR", "ERROR" in _rTamperV, detail=_rTamperV[:80])

# (HIGH-3) limitation 不吃 service_type 加算：純函式 public_domestic 應被忽略（末日不+20）
_lim_svc = compute_deadline(
    period_type="statutory", statutory_days=0, statutory_basis="民法§125",
    service_type="public_domestic", service_base_date="2020-01-01", has_local_agent=True,
    period_unit="year", period_value=15, counting_regime="limitation", db=db)
_assert("修補HIGH3: 純函式 limitation 不吃 service_type 加算（public_domestic→末日仍2035-01-01）",
        _lim_svc["statutory_deadline"] == "2035-01-01", detail=_lim_svc["statutory_deadline"])
_svcSN.create_deadline(
    matter_id=_midL, type="statute_127", description="", trigger_event="可行使",
    service_base_date="2024-06-01", service_type="public_foreign", statutory_days=0, statutory_basis="",
    statutory_basis_version="", period_type="", severity="", has_local_agent=-1, in_transit_days=0,
    court_region="", party_region="", buffer_days=0, stated_period_days=0, document_date="",
    assignee="", assignee_line_user_id="", escalation_lead_days="", created_by="x")
_dSvc = db.execute(
    "SELECT service_type FROM deadlines WHERE matter_id=? AND type='statute_127' ORDER BY id DESC LIMIT 1",
    (_midL,)).fetchone()
_assert("修補HIGH3: service 端 limitation 強制 service_type=normal 落欄（不留 public_foreign）",
        _dSvc and _dSvc["service_type"] == "normal", detail=str(dict(_dSvc)) if _dSvc else "None")

# (HIGH-4) statutory_days 不重載期間數 + get_deadline 顯示「N 年」非「N 日」
_dSD = db.execute(
    "SELECT id,statutory_days,period_value FROM deadlines WHERE matter_id=? AND type='statute_125' "
    "ORDER BY id LIMIT 1", (_midL,)).fetchone()
_assert("修補HIGH4: §125 statutory_days 不被重載成15（year 路徑留0、period_value=15）",
        _dSD and _dSD["statutory_days"] == 0 and _dSD["period_value"] == 15,
        detail=str(dict(_dSD)) if _dSD else "None")
_getL = _svcSN.get_deadline(_dSD["id"])
_assert("修補HIGH4: get_deadline 顯示「法定期間：15 年」、不出現「15 日」",
        "15 年" in _getL and "15 日" not in _getL,
        detail=str([l for l in _getL.split(chr(10)) if "法定期間" in l]))

# (MED-5) §197 建立回覆含「另一本時鐘」提醒
_r197note = _svcSN.create_deadline(
    matter_id=_midL, type="statute_197_2y", description="", trigger_event="知悉",
    service_base_date="2025-01-01", service_type="normal", statutory_days=0, statutory_basis="",
    statutory_basis_version="", period_type="", severity="", has_local_agent=-1, in_transit_days=0,
    court_region="", party_region="", buffer_days=0, stated_period_days=0, document_date="",
    assignee="", assignee_line_user_id="", escalation_lead_days="", created_by="x")
_assert("修補MED5: §197_2y 回覆提醒另一本10年時鐘（雙時鐘防漏）",
        "statute_197_10y" in _r197note and "雙時鐘" in _r197note, detail=_r197note[-120:])

# (MED-6) month 路徑端到端（§121但書：1/31+1月→無相當日→該月末日）
_lim_month = compute_deadline(
    period_type="statutory", statutory_days=0, statutory_basis="自訂月期間",
    service_type="normal", service_base_date="2026-01-30", has_local_agent=True,
    period_unit="month", period_value=1, counting_regime="limitation", db=db)
_assert("修補MED6: month 路徑 2026-01-30→start01-31+1月→無相當日→月末2026-02-28（§121但書）",
        _lim_month["statutory_deadline"] == "2026-02-28", detail=_lim_month["statutory_deadline"])

# (R2-HIGH) generic limitation 不可改標 period_type（消滅時效必 statutory、非 peremptory/directory）
_rGenPt = _svcSN.create_deadline(
    matter_id=_midL, type="limitation", description="自訂時效", trigger_event="可行使",
    service_base_date="2020-01-01", service_type="normal", statutory_days=0, statutory_basis="民法§125",
    statutory_basis_version="", period_type="peremptory", severity="", has_local_agent=-1,
    in_transit_days=0, court_region="", party_region="", buffer_days=0, stated_period_days=0,
    document_date="", assignee="", assignee_line_user_id="", escalation_lead_days="", created_by="x",
    period_unit="year", period_value=15)
_assert("修補R2-HIGH: generic limitation 改標 peremptory → ERROR（消滅時效 period_type 必 statutory）",
        "ERROR" in _rGenPt and "statutory" in _rGenPt, detail=_rGenPt[:90])

# (R2-MED) period_value 非數字 → 正規化後可審計 ERROR（不炸 ValueError）
_rBadPv = _svcSN.create_deadline(
    matter_id=_midL, type="limitation", description="自訂時效", trigger_event="可行使",
    service_base_date="2020-01-01", service_type="normal", statutory_days=0, statutory_basis="民法§125",
    statutory_basis_version="", period_type="statutory", severity="", has_local_agent=-1,
    in_transit_days=0, court_region="", party_region="", buffer_days=0, stated_period_days=0,
    document_date="", assignee="", assignee_line_user_id="", escalation_lead_days="", created_by="x",
    period_unit="year", period_value="abc")
_assert("修補R2-MED: period_value 非數字 → 正規化後可審計 ERROR（不炸 ValueError）",
        "ERROR" in _rBadPv, detail=_rBadPv[:80])


# === 全面審 workflow/codex 測試盲區補強（#8 missed/_workdays、#9 公示送達、#10 bumped60/在途順延）===
print("\n=== 測試盲區補強（逾期路徑 / 公示送達 / bumped60 / 在途順延）===")
import datetime as _dtA  # noqa: E402
from shared.deadlines import (  # noqa: E402
    scan_and_enqueue_due_reminders, _workdays_between, _SERVICE_NEEDS_REVIEW,
)

# --- #8a _workdays_between 直接單測（逾期判斷核心、原零單測）---
_assert("_workdays_between: internal=today → 0（T-0 不誤判逾期）",
        _workdays_between(_dtA.date(2026, 6, 15), _dtA.date(2026, 6, 15), db) == 0)
_assert("_workdays_between: internal=昨天 → 負（正確判逾期）",
        _workdays_between(_dtA.date(2026, 6, 16), _dtA.date(2026, 6, 15), db) < 0)
# 跨週末：週五 06-05 → 下週一 06-08，中間週六日不計、僅週一 1 個上班日（驗正確跳週末）
_assert("_workdays_between: 跨週末（週五→下週一）= 1 個上班日（週末不計）",
        _workdays_between(_dtA.date(2026, 6, 5), _dtA.date(2026, 6, 8), db) == 1)
# 跨端午（2026-06-19 國定假日）：06-17(三)→06-22(一)，扣週六日+端午=僅 06-18、06-22 兩上班日
_assert("_workdays_between: 跨端午6/19+週末 → 正確扣國定假日（06-18、06-22）= 2 個上班日",
        _workdays_between(_dtA.date(2026, 6, 17), _dtA.date(2026, 6, 22), db) == 2)

# --- #8b deadline_missed 逾期路徑 golden（最高優先提醒分支、原零 golden）---
_midMiss = db.execute(
    "INSERT INTO matters (matter_no, title, status, has_local_agent, confidential) "
    "VALUES ('2026-miss-001', '逾期測試案', 'open', 1, 0)").lastrowid
db.commit()
_today_miss = _dtA.date(2026, 6, 15)
_yest = (_today_miss - _dtA.timedelta(days=1)).isoformat()
# 直接插一筆 internal_deadline=昨天的 pending（精確控制 internal、不靠 create_deadline 計算）
db.execute(
    "INSERT INTO deadlines (matter_id, type, description, period_type, severity, trigger_event, "
    "service_type, service_base_date, statutory_days, statutory_basis, internal_deadline, "
    "statutory_deadline, status, escalation_lead_days, reminders_sent, needs_manual_review) "
    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
    (_midMiss, "appeal_civil", "逾期上訴", "peremptory", "red", "判決送達", "normal",
     "2026-05-01", 20, "民訴§440", _yest, _yest, "pending", "[7,3,1,0]", "[]", 0))
db.commit()
_msStats = scan_and_enqueue_due_reminders(today=_today_miss.isoformat())
_assert("missed: scan 對 internal<today 的 pending → stats['missed']>=1（最高優先分支被守住）",
        _msStats["missed"] >= 1, detail=str(_msStats))
_rowMiss = db.execute(
    "SELECT summary FROM pending_escalations WHERE event_type='deadline_missed' "
    "AND summary LIKE '%逾期測試案%' ORDER BY id DESC LIMIT 1").fetchone()
_assert("missed: enqueue 一筆 deadline_missed（summary 含『逾期』『回復原狀』）",
        _rowMiss and "逾期" in _rowMiss["summary"] and "回復原狀" in _rowMiss["summary"],
        detail=str(dict(_rowMiss)) if _rowMiss else "None")
_msStats2 = scan_and_enqueue_due_reminders(today=_today_miss.isoformat())
_assert("missed: 逾期每日重推（連兩次掃都 missed、不靠 reminders_sent 去重）",
        _msStats2["missed"] >= 1, detail=str(_msStats2))

# --- #9 公示送達 +20 / +60 day-path golden + _SERVICE_NEEDS_REVIEW 反向不變量 ---
_pubD = compute_deadline(
    period_type="statutory", statutory_days=20, statutory_basis="民訴§440",
    service_type="public_domestic", service_base_date="2026-06-01", has_local_agent=True, db=db)
_assert("公示境內: effective=base+20（民訴§152）、不標複核",
        _pubD["effective_date"] == "2026-06-21" and _pubD["needs_manual_review"] is False,
        detail=f"eff={_pubD['effective_date']} review={_pubD['needs_manual_review']}")
_assert("公示境內: calc_trace 含 §152 + 20",
        any("§152" in t and "20" in t for t in _pubD["calc_trace"]))
_pubF = compute_deadline(
    period_type="statutory", statutory_days=20, statutory_basis="民訴§440",
    service_type="public_foreign", service_base_date="2026-06-01", has_local_agent=True, db=db)
_assert("公示外國: effective=base+60、不標複核",
        _pubF["effective_date"] == "2026-07-31" and _pubF["needs_manual_review"] is False,
        detail=_pubF["effective_date"])
_assert("不變量: _SERVICE_NEEDS_REVIEW 只含 commissioned（公示/寄存不被誤標強制複核、反之亦然）",
        _SERVICE_NEEDS_REVIEW == frozenset({"commissioned"}), detail=str(_SERVICE_NEEDS_REVIEW))

# --- #10a 在途 + 末日落假日順延的絕對日期 golden（原只驗相對不等式、抓不到 off-by-one）---
# base 2026-06-01(週一)→ start 06-02、in_transit=6、span=26 → nominal 06-27(週六)→ §122 順延 06-29(週一)
_trans = compute_deadline(
    period_type="peremptory", statutory_days=20, statutory_basis="民訴§440",
    service_type="normal", service_base_date="2026-06-01", has_local_agent=False,
    in_transit_days_override=6, buffer_days=1, db=db)
_assert("在途+順延 golden: 在途6→理論末日06-27(週六)→§122順延法定=2026-06-29(週一)",
        _trans["in_transit_days"] == 6 and _trans["statutory_deadline"] == "2026-06-29",
        detail=f"in_transit={_trans['in_transit_days']} hard={_trans['statutory_deadline']}")

# --- #10b bumped>=60 防呆（office_calendar 整段全假日 → needs_review + trace「辦公日曆異常」）---
for _i in range(61):
    _bd = _dtA.date(2030, 3, 1) + _dtA.timedelta(days=_i)
    db.execute(
        "INSERT OR REPLACE INTO office_calendar (date,is_holiday,description,source) VALUES (?,?,?,?)",
        (_bd.isoformat(), 1, "synthetic-all-holiday", "test-bumped60"))
db.commit()
# 末日（nominal）落 2030-03-01：base 2030-02-28 normal → start 03-01、statutory_days=1 → nominal 03-01
_bump = compute_deadline(
    period_type="peremptory", statutory_days=1, statutory_basis="民訴§440",
    service_type="normal", service_base_date="2030-02-28", has_local_agent=True, buffer_days=0, db=db)
_assert("bumped60: 末日落 61 天全假日段 → needs_manual_review（防無限迴圈/荒謬末日）",
        _bump["needs_manual_review"] is True)
_assert("bumped60: calc_trace 含『連推 60 日仍為假日』『辦公日曆異常』（誠實標下、非靜默續算）",
        any("連推 60 日仍為假日" in t and "辦公日曆異常" in t for t in _bump["calc_trace"]),
        detail=str([t for t in _bump["calc_trace"] if "順延" in t or "60" in t]))

# --- #4 fail-closed：floored 但查無 verified LINE 脈絡 → 寫入被擋（codex 複審 HIGH：不可只解析不擋）---
import os as _osFC  # noqa: E402
_saved_floor_fc = _osFC.environ.get("SME_FLOOR")
_saved_lsd_fc = _osFC.environ.get("LINE_STATE_DIR")
_osFC.environ["SME_FLOOR"] = "general"  # 模擬受限層
_osFC.environ["LINE_STATE_DIR"] = "/tmp/_no_active_request_xyz_legal"  # 指向無 active-request 的空目錄
try:
    _rFC = _svcSN.create_matter(
        "fail-closed測試案", "2026-fc-001", "", "", "", "", "", "王律師", 0, 0, "agent自填名")
    _assert("#4 fail-closed: floored 無 verified 脈絡 → create_matter 拒寫（__unverified__、防偽造）",
            "ERROR" in _rFC and "無法驗證" in _rFC, detail=_rFC[:90])
    # stage_deadline_intake（matter_id=0、actor gate 在 insert 前）同樣 fail-closed、不留髒暫存
    _rFC2 = _svcSN.stage_deadline_intake(
        matter_id=0, matter_label="fc", doc_type="", service_base_date="", stated_period_days=0,
        document_date="", extracted_summary="fail-closed intake", submitted_by="agent自填")
    _assert("#4 fail-closed: floored 無脈絡 → stage_deadline_intake 拒寫（防偽造丟件人）",
            "ERROR" in _rFC2 and "無法驗證" in _rFC2, detail=_rFC2[:90])
finally:
    if _saved_floor_fc is None:
        _osFC.environ.pop("SME_FLOOR", None)
    else:
        _osFC.environ["SME_FLOOR"] = _saved_floor_fc
    if _saved_lsd_fc is None:
        _osFC.environ.pop("LINE_STATE_DIR", None)
    else:
        _osFC.environ["LINE_STATE_DIR"] = _saved_lsd_fc


# === 保全§529 命起訴期間（court_set seed）+ 行訴§106 程序月期間（counting_regime=procedural）===
print("\n=== 保全§529 court_set + 行訴§106 程序月期間 ===")
from shared.deadlines import (  # noqa: E402
    PROCEDURAL_CALENDAR_PERIODS, procedural_calendar_type, court_set_type,
)

# --- 保全§529：登記於 COURT_SET_PERIODS、走 court_set 路徑（律師讀命起訴裁定填天數、強制複核）---
_assert("§529: provisional_litigation 已登記於 COURT_SET_PERIODS",
        "provisional_litigation" in _CSP and court_set_type("provisional_litigation") is not None)
_assert("§529: 種子無 statutory_days 欄（反捏造：期間非法定固定值、律師讀裁定填）",
        "statutory_days" not in _CSP["provisional_litigation"])
_assert("§529: severity=red（逾期未起訴→保全被撤銷、失權）",
        _CSP["provisional_litigation"]["severity"] == "red")
_mid529 = db.execute(
    "INSERT INTO matters (matter_no, title, status, has_local_agent, confidential) "
    "VALUES ('2026-bn-001', '假扣押命起訴案', 'open', 1, 0)").lastrowid
db.commit()
# 缺天數 → ERROR + 提示讀裁定（court_set 反捏造：不臆測不預設）
_r529NoDays = _svcSN.create_deadline(
    matter_id=_mid529, type="provisional_litigation", description="", trigger_event="",
    service_base_date="2026-06-01", service_type="normal", statutory_days=0, statutory_basis="",
    statutory_basis_version="", period_type="", severity="", has_local_agent=-1, in_transit_days=0,
    court_region="", party_region="", buffer_days=1, stated_period_days=0, document_date="",
    assignee="", assignee_line_user_id="", escalation_lead_days="", created_by="王律師")
_assert("§529: 缺天數 → ERROR（讀裁定填、引擎不臆測）",
        "ERROR" in _r529NoDays and "裁定" in _r529NoDays, detail=_r529NoDays[:90])
# 完整建立：律師讀命起訴裁定填 30 日 + 裁定文號 → court_set 強制複核 + sibling note §529III
_r529 = _svcSN.create_deadline(
    matter_id=_mid529, type="provisional_litigation", description="", trigger_event="",
    service_base_date="2026-06-01", service_type="normal", statutory_days=30,
    statutory_basis="北院114全字第5號裁定 + 民訴§529", statutory_basis_version="", period_type="",
    severity="", has_local_agent=-1, in_transit_days=0, court_region="", party_region="",
    buffer_days=1, stated_period_days=0, document_date="", assignee="", assignee_line_user_id="",
    escalation_lead_days="", created_by="王律師")
_assert("§529: 完整建立成功 + 強制人工複核（court_set）+ §529Ⅲ夫妻剩餘財產提醒",
        "已建立" in _r529 and "需人工複核" in _r529 and "§529Ⅲ" in _r529, detail=_r529[:140])
_d529 = db.execute(
    "SELECT period_type,period_unit,statutory_days,needs_manual_review,severity FROM deadlines "
    "WHERE matter_id=? ORDER BY id DESC LIMIT 1", (_mid529,)).fetchone()
_assert("§529: 落欄 period_type=court_set/period_unit=day/statutory_days=30/強制複核",
        _d529 and _d529["period_type"] == "court_set" and _d529["period_unit"] == "day"
        and _d529["statutory_days"] == 30 and _d529["needs_manual_review"] == 1,
        detail=str(dict(_d529)) if _d529 else "None")

# --- 行訴§106 純函式 golden：訴願決定書送達後2個月不變期間（送達+次日+§121+§122）---
# 送達 2026-02-02(一)→effective 2/2→start 2/3→+2月§121相當日(4/3)前一日=4/2(週四上班日、不順延)
_a106 = compute_deadline(
    period_type="peremptory", statutory_days=0, statutory_basis="行政訴訟法§106Ⅰ",
    service_type="normal", service_base_date="2026-02-02", has_local_agent=True,
    period_unit="month", period_value=2, counting_regime="procedural", buffer_days=1, db=db)
_assert("§106 golden: 送達2026-02-02→末日2026-04-02（§121相當日前一日、末日為上班日不順延）",
        _a106["statutory_deadline"] == "2026-04-02", detail=_a106["statutory_deadline"])
_assert("§106 golden: 起算=送達次日2026-02-03（民§120Ⅱ、行訴§88依民法）",
        _a106["start_date"] == "2026-02-03", detail=_a106["start_date"])
_assert("§106 golden: period_unit/value 回 month/2（反捏造：非日）",
        _a106["period_unit"] == "month" and _a106["period_value"] == 2)
_assert("§106 golden: 回復原狀=行政訴訟法§91（≠民訴§164；1個月、逾1年/逾3年不得）",
        _a106["recovery_window"].get("basis") == "行政訴訟法§91"
        and "1個月" in _a106["recovery_window"].get("condition", ""), detail=str(_a106["recovery_window"]))
_assert("§106 golden: 有當地代理人→在途0、calc_trace 標行訴§89但書（非民訴§162）",
        _a106["in_transit_days"] == 0 and any("行訴§89但書" in t for t in _a106["calc_trace"]),
        detail=str([t for t in _a106["calc_trace"] if "在途" in t]))
_assert("§106 golden: 起算用送達日(確定事實)→不因 regime 強制複核（calendar 已載入、normal 送達）",
        _a106["needs_manual_review"] is False, detail=str(_a106["calc_trace"]))
_assert("§106 golden: calc_trace 含民§121 + §123 依曆",
        any("§121" in t for t in _a106["calc_trace"]) and any("§123" in t for t in _a106["calc_trace"]))

# §121但書（月期間無相當日→該月末日）+ §122 順延：送達 2025-12-30→start 12/31→+2月→2/28(週六)→順延 3/2
_a106b = compute_deadline(
    period_type="peremptory", statutory_days=0, statutory_basis="行政訴訟法§106Ⅰ",
    service_type="normal", service_base_date="2025-12-30", has_local_agent=True,
    period_unit="month", period_value=2, counting_regime="procedural", buffer_days=0, db=db)
_assert("§106 §121但書: 送達2025-12-30→起算12-31→+2月無相當日→月末2026-02-28(週六)→§122順延2026-03-02",
        _a106b["statutory_deadline"] == "2026-03-02"
        and any("§121但書" in t for t in _a106b["calc_trace"]), detail=_a106b["statutory_deadline"])

# --- 行訴§106 service 端到端：admin_revocation 種子回填、不強制複核、提醒三例外 ---
_assert("§106: admin_revocation 已登記 PROCEDURAL_CALENDAR_PERIODS",
        "admin_revocation" in PROCEDURAL_CALENDAR_PERIODS
        and procedural_calendar_type("admin_revocation") is not None)
_mid106 = db.execute(
    "INSERT INTO matters (matter_no, title, status, has_local_agent, confidential) "
    "VALUES ('2026-adm-001', '撤銷訴訟案', 'open', 1, 0)").lastrowid
db.commit()
_r106 = _svcSN.create_deadline(
    matter_id=_mid106, type="admin_revocation", description="", trigger_event="",
    service_base_date="2026-02-02", service_type="normal", statutory_days=0, statutory_basis="",
    statutory_basis_version="", period_type="", severity="", has_local_agent=-1, in_transit_days=0,
    court_region="", party_region="", buffer_days=1, stated_period_days=0, document_date="",
    assignee="", assignee_line_user_id="", escalation_lead_days="", created_by="王律師")
_assert("§106端到端: 建立成功 + 期間顯示「2 月」+ 逾3年/利害關係人/§106Ⅲ三例外提醒",
        "已建立" in _r106 and "2 月" in _r106 and "逾3年" in _r106 and "利害關係人" in _r106,
        detail=_r106[:160])
_d106 = db.execute(
    "SELECT period_type,period_unit,period_value,statutory_days,statutory_basis,"
    "needs_manual_review,statutory_deadline,severity FROM deadlines "
    "WHERE matter_id=? ORDER BY id DESC LIMIT 1", (_mid106,)).fetchone()
_assert("§106端到端: 落欄 period_type=peremptory/unit=month/value=2/statutory_days=0/basis=行訴§106",
        _d106 and _d106["period_type"] == "peremptory" and _d106["period_unit"] == "month"
        and _d106["period_value"] == 2 and _d106["statutory_days"] == 0
        and "§106" in _d106["statutory_basis"], detail=str(dict(_d106)) if _d106 else "None")
_assert("§106端到端: 末日2026-04-02、不強制複核（送達日確定事實、calendar 已載入）",
        _d106 and _d106["statutory_deadline"] == "2026-04-02" and _d106["needs_manual_review"] == 0,
        detail=str(dict(_d106)) if _d106 else "None")
_get106 = _svcSN.get_deadline(_d106 and db.execute(
    "SELECT id FROM deadlines WHERE matter_id=? ORDER BY id DESC LIMIT 1", (_mid106,)).fetchone()["id"])
_assert("§106端到端: get_deadline 顯示「法定期間：2 月」、不出現「2 日」（反捏造）",
        "2 月" in _get106 and "法定期間：2 日" not in _get106,
        detail=str([l for l in _get106.split(chr(10)) if "法定期間" in l]))

# --- 行訴§106 種子鎖（反捏造）：改 period_type / period_value → ERROR ---
_r106BadPt = _svcSN.create_deadline(
    matter_id=_mid106, type="admin_revocation", description="", trigger_event="",
    service_base_date="2026-02-02", service_type="normal", statutory_days=0, statutory_basis="",
    statutory_basis_version="", period_type="statutory", severity="", has_local_agent=-1,
    in_transit_days=0, court_region="", party_region="", buffer_days=1, stated_period_days=0,
    document_date="", assignee="", assignee_line_user_id="", escalation_lead_days="", created_by="王律師")
_assert("§106鎖: admin_revocation 改標 statutory → ERROR（§106 是不變期間 peremptory）",
        "ERROR" in _r106BadPt and "peremptory" in _r106BadPt, detail=_r106BadPt[:90])
_r106BadVal = _svcSN.create_deadline(
    matter_id=_mid106, type="admin_revocation", description="", trigger_event="",
    service_base_date="2026-02-02", service_type="normal", statutory_days=0, statutory_basis="",
    statutory_basis_version="", period_type="", severity="", has_local_agent=-1, in_transit_days=0,
    court_region="", party_region="", buffer_days=1, stated_period_days=0, document_date="",
    assignee="", assignee_line_user_id="", escalation_lead_days="", created_by="王律師", period_value=3)
_assert("§106鎖: admin_revocation period_value 改 3 → ERROR（法定2月固定）",
        "ERROR" in _r106BadVal, detail=_r106BadVal[:90])

# --- 行訴§106 教示比對 month-aware：stated=2→相符；stated=60(誤填日)→不符+複核 ---
_a106match = compute_deadline(
    period_type="peremptory", statutory_days=0, statutory_basis="行政訴訟法§106Ⅰ",
    service_type="normal", service_base_date="2026-02-02", has_local_agent=True,
    period_unit="month", period_value=2, counting_regime="procedural", stated_period_days=2, db=db)
_assert("§106教示: 教示2(月)＝引擎2月→相符（match、單位 aware 不誤判）",
        _a106match["period_match"] == "match"
        and any("教示" in t and "個月" in t and "相符" in t for t in _a106match["calc_trace"]),
        detail=str([t for t in _a106match["calc_trace"] if "教示" in t]))
_a106mis = compute_deadline(
    period_type="peremptory", statutory_days=0, statutory_basis="行政訴訟法§106Ⅰ",
    service_type="normal", service_base_date="2026-02-02", has_local_agent=True,
    period_unit="month", period_value=2, counting_regime="procedural", stated_period_days=60, db=db)
_assert("§106教示: 教示60(誤當日)≠引擎2月→不符+強制複核（揪出單位/期間誤判）",
        _a106mis["period_match"] == "mismatch" and _a106mis["needs_manual_review"] is True,
        detail=_a106mis["period_match"])

# --- 行訴§106 無當地代理人：行政在途依行訴§89Ⅱ司法院定之、引擎無表→人工複核（不臆測）---
_a106na = compute_deadline(
    period_type="peremptory", statutory_days=0, statutory_basis="行政訴訟法§106Ⅰ",
    service_type="normal", service_base_date="2026-02-02", has_local_agent=False,
    period_unit="month", period_value=2, counting_regime="procedural", db=db)
_assert("§106在途: 行政無代理人→needs_review + trace 標行訴§89Ⅱ（不臆測在途）",
        _a106na["needs_manual_review"] is True
        and any("行訴§89Ⅱ" in t for t in _a106na["calc_trace"]),
        detail=str([t for t in _a106na["calc_trace"] if "在途" in t]))

# --- counting_regime 防呆 + 四表零重疊 ---
_rRegBad = compute_deadline(
    period_type="statutory", statutory_days=20, statutory_basis="民訴§440",
    service_type="normal", service_base_date="2026-02-02", has_local_agent=True,
    counting_regime="bogus", db=db)
_assert("regime防呆: counting_regime 非法值 → error", "error" in _rRegBad, detail=str(_rRegBad.get("error")))
_rRegLimDay = compute_deadline(
    period_type="statutory", statutory_days=20, statutory_basis="民訴§440",
    service_type="normal", service_base_date="2026-02-02", has_local_agent=True,
    counting_regime="limitation", period_unit="day", db=db)
_assert("regime防呆: limitation 搭 period_unit=day → error（消滅時效必年/月）",
        "error" in _rRegLimDay, detail=str(_rRegLimDay.get("error")))
_assert("四表零重疊: PROCEDURAL_CALENDAR_PERIODS 與 STATUTORY/COURT_SET/LIMITATION 皆不重疊",
        not (set(PROCEDURAL_CALENDAR_PERIODS) & set(STATUTORY_PERIODS))
        and not (set(PROCEDURAL_CALENDAR_PERIODS) & set(_CSP))
        and not (set(PROCEDURAL_CALENDAR_PERIODS) & set(LIMITATION_PERIODS)))


# === 律師覆核留痕 mark_deadline_reviewed（信任/稽核 #6a）===
print("\n=== 律師覆核留痕 mark_deadline_reviewed ===")
# 用 _mid529 那筆 court_set（needs_manual_review=1）來測覆核
_rvId = db.execute(
    "SELECT id FROM deadlines WHERE matter_id=? ORDER BY id DESC LIMIT 1", (_mid529,)).fetchone()["id"]
_preRv = db.execute(
    "SELECT needs_manual_review, reviewed_by, reviewed_at FROM deadlines WHERE id=?", (_rvId,)).fetchone()
_assert("覆核前: needs_manual_review=1、reviewed_by/at 皆空",
        _preRv["needs_manual_review"] == 1 and not _preRv["reviewed_by"] and not _preRv["reviewed_at"])
_rRv = _svcSN.mark_deadline_reviewed(deadline_id=_rvId, reviewed_by="王律師", note="已核對命起訴裁定主文30日無誤")
_assert("覆核: 成功 + 回覆含覆核人 + 解除需複核旗標",
        "已由 王律師 覆核留痕" in _rRv and "解除" in _rRv, detail=_rRv[:120])
_postRv = db.execute(
    "SELECT needs_manual_review, reviewed_by, reviewed_at FROM deadlines WHERE id=?", (_rvId,)).fetchone()
_assert("覆核後: needs_manual_review=0、reviewed_by/reviewed_at 落欄",
        _postRv["needs_manual_review"] == 0 and _postRv["reviewed_by"] == "王律師"
        and _postRv["reviewed_at"], detail=str(dict(_postRv)))
_rvLog = db.execute(
    "SELECT actor,action,detail FROM interaction_log WHERE action='deadline_reviewed' "
    "AND target_id=? ORDER BY id DESC LIMIT 1", (_rvId,)).fetchone()
_assert("覆核: interaction_log 留痕 deadline_reviewed（具名+備註）",
        _rvLog and _rvLog["actor"] == "王律師" and "30日無誤" in _rvLog["detail"],
        detail=str(dict(_rvLog)) if _rvLog else "None")
_getRv = _svcSN.get_deadline(_rvId)
_assert("覆核: get_deadline 顯示「已覆核：王律師」、且不再顯示「需人工複核」",
        "已覆核：王律師" in _getRv and "[需人工複核]" not in _getRv,
        detail=str([l for l in _getRv.split(chr(10)) if "覆核" in l]))
# 找不到 / 已取消防呆
_assert("覆核防呆: 找不到時限 → ERROR", "ERROR" in _svcSN.mark_deadline_reviewed(999999, "王律師", ""))
# fail-closed：floored 無 verified 脈絡 → 拒覆核（不可盲信任意覆核人名）
_saved_fl_rv = _osFC.environ.get("SME_FLOOR")
_saved_ls_rv = _osFC.environ.get("LINE_STATE_DIR")
_osFC.environ["SME_FLOOR"] = "general"
_osFC.environ["LINE_STATE_DIR"] = "/tmp/_no_ar_review_xyz"
try:
    _rRvFC = _svcSN.mark_deadline_reviewed(deadline_id=_rvId, reviewed_by="agent自填", note="x")
    _assert("覆核 fail-closed: floored 無 verified → 拒覆核（防偽造覆核人）",
            "ERROR" in _rRvFC and "無法驗證" in _rRvFC, detail=_rRvFC[:90])
finally:
    if _saved_fl_rv is None:
        _osFC.environ.pop("SME_FLOOR", None)
    else:
        _osFC.environ["SME_FLOOR"] = _saved_fl_rv
    if _saved_ls_rv is None:
        _osFC.environ.pop("LINE_STATE_DIR", None)
    else:
        _osFC.environ["LINE_STATE_DIR"] = _saved_ls_rv


# === amend_deadline 重算 + deadline_audit 稽核（信任/稽核 #6b）===
print("\n=== amend_deadline 重算 + deadline_audit ===")
from shared.escalation import DEFAULT_ENABLED_EVENTS as _DEE  # noqa: E402
_assert("amend: deadline_amended 已註冊為預設啟用 escalation 事件",
        "deadline_amended" in _DEE)
_midAm = db.execute(
    "INSERT INTO matters (matter_no, title, status, has_local_agent, confidential) "
    "VALUES ('2026-am-001', '異動測試案', 'open', 1, 0)").lastrowid
db.commit()
# 建 appeal_civil 上訴20日 送達2026-06-01（calendar 已載入→deterministic）
_rAm = _svcSN.create_deadline(
    matter_id=_midAm, type="appeal_civil", description="", trigger_event="判決送達",
    service_base_date="2026-06-01", service_type="normal", statutory_days=0, statutory_basis="",
    statutory_basis_version="", period_type="", severity="", has_local_agent=-1, in_transit_days=0,
    court_region="", party_region="", buffer_days=1, stated_period_days=0, document_date="",
    assignee="", assignee_line_user_id="", escalation_lead_days="", created_by="王律師")
import re as _reAm  # noqa: E402
_amId = int(_reAm.search(r"#(\d+)", _rAm).group(1))
_amBefore = db.execute("SELECT statutory_deadline FROM deadlines WHERE id=?", (_amId,)).fetchone()["statutory_deadline"]
# 先覆核（待會驗證 amend 會作廢覆核）
_svcSN.mark_deadline_reviewed(_amId, "王律師", "確認")
_amRevBefore = db.execute("SELECT reviewed_by FROM deadlines WHERE id=?", (_amId,)).fetchone()["reviewed_by"]
_assert("amend 前置: 已覆核（reviewed_by=王律師）", _amRevBefore == "王律師")
# 缺 reason → ERROR
_assert("amend 防呆: 缺 reason → ERROR",
        "ERROR" in _svcSN.amend_deadline(_amId, "", "王律師", service_base_date="2026-06-10"))
# 改送達日 2026-06-01→2026-06-10 重算
_rAmend = _svcSN.amend_deadline(_amId, "送達回證更正為6/10", "王律師", service_base_date="2026-06-10")
_amAfter = db.execute(
    "SELECT statutory_deadline,reviewed_by,reviewed_at,needs_manual_review,service_base_date "
    "FROM deadlines WHERE id=?", (_amId,)).fetchone()
_assert("amend: 重算法定末日改變（送達+9日）+ 回覆含 before→after",
        _amAfter["statutory_deadline"] != _amBefore and "→" in _rAmend
        and _amAfter["service_base_date"] == "2026-06-10", detail=_rAmend[:140])
_assert("amend: 原覆核作廢（reviewed_by/at 清空、needs_manual_review 重設）",
        _amAfter["reviewed_by"] is None and _amAfter["reviewed_at"] is None,
        detail=str(dict(_amAfter)))
# deadline_audit 留痕
_amAudit = db.execute(
    "SELECT amended_by,reason,changed_fields,before_snapshot,after_snapshot FROM deadline_audit "
    "WHERE deadline_id=? ORDER BY id DESC LIMIT 1", (_amId,)).fetchone()
_assert("amend: deadline_audit 落 before/after 快照 + changed_fields + 具名 + 原因",
        _amAudit and _amAudit["amended_by"] == "王律師" and "6/10" in _amAudit["reason"]
        and "statutory_deadline" in _amAudit["changed_fields"]
        and _amBefore in _amAudit["before_snapshot"], detail=str(dict(_amAudit)) if _amAudit else "None")
# 上報 deadline_amended（同 tx enqueue）
_amEsc = db.execute(
    "SELECT summary,detail FROM pending_escalations WHERE event_type='deadline_amended' "
    "AND summary LIKE '%2026-am-001%' ORDER BY id DESC LIMIT 1").fetchone()
_assert("amend: enqueue deadline_amended 上報（summary 含異動 + 覆核作廢提示）",
        _amEsc and "時限異動" in _amEsc["summary"] and "覆核已作廢" in _amEsc["summary"],
        detail=str(dict(_amEsc)) if _amEsc else "None")
# interaction_log 留痕
_amLog = db.execute(
    "SELECT actor,detail FROM interaction_log WHERE action='deadline_amended' AND target_id=? "
    "ORDER BY id DESC LIMIT 1", (_amId,)).fetchone()
_assert("amend: interaction_log 留痕 deadline_amended（具名+原因）",
        _amLog and _amLog["actor"] == "王律師" and "6/10" in _amLog["detail"],
        detail=str(dict(_amLog)) if _amLog else "None")
# 覆核作廢納入稽核（codex 稽核#6b finding#2）：reviewed_by 在 changed_fields + before/after 快照可回放
_assert("amend: 覆核作廢可回放（changed_fields 含 reviewed_by、before 有人/after None）",
        "reviewed_by" in _amAudit["changed_fields"]
        and "王律師" in _amAudit["before_snapshot"]
        and '"reviewed_by": null' in _amAudit["after_snapshot"],
        detail=_amAudit["changed_fields"])
# get_deadline_audit 列歷程
_getAud = _svcSN.get_deadline_audit(_amId)
_assert("amend: get_deadline_audit 列出異動歷程（含 王律師 + 原因）",
        "異動歷程" in _getAud and "王律師" in _getAud and "6/10" in _getAud, detail=_getAud[:120])

# 在途 provenance 忠實（codex 稽核#6b finding#1）：create 用手動 in_transit override=5、amend 改送達日，
# 在途值與來源不被 drift（仍 5、仍「手動指定」，不被謊報/重derive）
_midPv = db.execute(
    "INSERT INTO matters (matter_no, title, status, has_local_agent, confidential) "
    "VALUES ('2026-pv-001', '在途provenance案', 'open', 0, 0)").lastrowid
db.commit()
_rPv = _svcSN.create_deadline(
    matter_id=_midPv, type="appeal_civil", description="", trigger_event="判決送達",
    service_base_date="2026-06-01", service_type="normal", statutory_days=0, statutory_basis="",
    statutory_basis_version="", period_type="", severity="", has_local_agent=0, in_transit_days=5,
    court_region="", party_region="", buffer_days=1, stated_period_days=0, document_date="",
    assignee="", assignee_line_user_id="", escalation_lead_days="", created_by="王律師")
_pvId = int(_reAm.search(r"#(\d+)", _rPv).group(1))
_pvBefore = db.execute("SELECT in_transit_days,in_transit_source,compute_in_transit_override,"
                       "compute_has_local_agent FROM deadlines WHERE id=?", (_pvId,)).fetchone()
_assert("provenance 前置: create 落 compute_in_transit_override=5 + has_local_agent=0 蓋章",
        _pvBefore["compute_in_transit_override"] == 5 and _pvBefore["compute_has_local_agent"] == 0
        and _pvBefore["in_transit_days"] == 5, detail=str(dict(_pvBefore)))
_svcSN.amend_deadline(_pvId, "送達日更正", "王律師", service_base_date="2026-06-05")
_pvAfter = db.execute("SELECT in_transit_days,in_transit_source FROM deadlines WHERE id=?", (_pvId,)).fetchone()
_assert("provenance: amend 改送達日後在途仍=5、來源仍「手動指定」（不 drift、不謊報）",
        _pvAfter["in_transit_days"] == 5 and "手動指定" in _pvAfter["in_transit_source"],
        detail=str(dict(_pvAfter)))
# codex R2 finding#1：amend(in_transit_days=0) 不可把「不 override」漂成「手動 0 日」、應沿用原 override=5
_svcSN.amend_deadline(_pvId, "再改送達日、在途不動", "王律師", service_base_date="2026-06-08", in_transit_days=0)
_pv0 = db.execute("SELECT in_transit_days,compute_in_transit_override FROM deadlines WHERE id=?", (_pvId,)).fetchone()
_assert("provenance: amend(in_transit_days=0) 不漂成手動0日、沿用原 override=5（0 與 create 同語義）",
        _pv0["in_transit_days"] == 5 and _pv0["compute_in_transit_override"] == 5,
        detail=str(dict(_pv0)))
# 連鎖①：amend 改成新正值 7 → 再 amend(in_transit_days=-1) 仍沿用 7（新 override 被持久化、延續）
_svcSN.amend_deadline(_pvId, "在途改7", "王律師", in_transit_days=7)
_svcSN.amend_deadline(_pvId, "再改送達日、在途不動", "王律師", service_base_date="2026-06-09")
_pvChain = db.execute("SELECT in_transit_days,compute_in_transit_override FROM deadlines WHERE id=?", (_pvId,)).fetchone()
_assert("provenance 連鎖: amend→正值7→amend(不指定) 仍沿用 7（新 override 持久化延續）",
        _pvChain["in_transit_days"] == 7 and _pvChain["compute_in_transit_override"] == 7,
        detail=str(dict(_pvChain)))
# 連鎖②：create 無 override（has_local_agent=1→在途0、source 非手動）→ amend(0/-1) 不平白生出 override
_midNo = db.execute(
    "INSERT INTO matters (matter_no, title, status, has_local_agent, confidential) "
    "VALUES ('2026-noov-001', '無override案', 'open', 1, 0)").lastrowid
db.commit()
_rNo = _svcSN.create_deadline(
    matter_id=_midNo, type="appeal_civil", description="", trigger_event="判決送達",
    service_base_date="2026-06-01", service_type="normal", statutory_days=0, statutory_basis="",
    statutory_basis_version="", period_type="", severity="", has_local_agent=-1, in_transit_days=0,
    court_region="", party_region="", buffer_days=1, stated_period_days=0, document_date="",
    assignee="", assignee_line_user_id="", escalation_lead_days="", created_by="王律師")
_noId = int(_reAm.search(r"#(\d+)", _rNo).group(1))
_svcSN.amend_deadline(_noId, "改送達日、不碰在途", "王律師", service_base_date="2026-06-05", in_transit_days=0)
_noAfter = db.execute("SELECT in_transit_days,in_transit_source,compute_in_transit_override FROM deadlines WHERE id=?", (_noId,)).fetchone()
_assert("provenance 連鎖: create 無 override → amend(0) 不平白生出手動 override（在途仍0、source 非手動指定）",
        _noAfter["in_transit_days"] == 0 and "手動指定" not in (_noAfter["in_transit_source"] or "")
        and _noAfter["compute_in_transit_override"] is None, detail=str(dict(_noAfter)))

# === codex R2 稽核#6b 複審：amend 可更正計算根本輸入 + clear override + compute_* 納稽核 ===
print("\n=== amend 計算輸入更正（R2 複審 finding#1/#2/#3）===")
# finding#3：clear_in_transit_override 把誤設的正數 override(_pvId 現為7) 清回 NULL、改走自動來源
_svcSN.amend_deadline(_pvId, "在途 override 設錯、清回自動", "王律師", clear_in_transit_override=True)
_pvClr = db.execute("SELECT in_transit_days,in_transit_source,compute_in_transit_override "
                    "FROM deadlines WHERE id=?", (_pvId,)).fetchone()
_assert("R2#3: clear_in_transit_override 清掉誤設的人工在途(7→自動)、override 落 NULL、source 非手動",
        _pvClr["compute_in_transit_override"] is None
        and "手動指定" not in (_pvClr["in_transit_source"] or ""), detail=str(dict(_pvClr)))
# finding#3 互斥防呆：clear + in_transit_days>0 → ERROR
_assert("R2#3: clear_in_transit_override 與 in_transit_days(>0) 互斥 → ERROR",
        "ERROR" in _svcSN.amend_deadline(_pvId, "x", "王律師",
                                         clear_in_transit_override=True, in_transit_days=3))
# finding#1：amend 更正 has_local_agent（0→1）→ 重新蓋章 compute_has_local_agent=1，由引擎重算在途
_midHla = db.execute(
    "INSERT INTO matters (matter_no, title, status, has_local_agent, confidential) "
    "VALUES ('2026-hla-001', 'local_agent更正案', 'open', 0, 0)").lastrowid
db.commit()
_rHla = _svcSN.create_deadline(
    matter_id=_midHla, type="appeal_civil", description="", trigger_event="判決送達",
    service_base_date="2026-06-01", service_type="normal", statutory_days=0, statutory_basis="",
    statutory_basis_version="", period_type="", severity="", has_local_agent=0, in_transit_days=0,
    court_region="臺北", party_region="高雄", buffer_days=1, stated_period_days=0, document_date="",
    assignee="", assignee_line_user_id="", escalation_lead_days="", created_by="王律師")
_hlaId = int(_reAm.search(r"#(\d+)", _rHla).group(1))
_hlaB = db.execute("SELECT compute_has_local_agent FROM deadlines WHERE id=?", (_hlaId,)).fetchone()
_svcSN.amend_deadline(_hlaId, "其實有委任在途代理人、更正", "王律師", has_local_agent=1)
_hlaA = db.execute("SELECT compute_has_local_agent FROM deadlines WHERE id=?", (_hlaId,)).fetchone()
_assert("R2#1: amend(has_local_agent=1) 更正並重新蓋章 compute_has_local_agent(0→1)",
        _hlaB["compute_has_local_agent"] == 0 and _hlaA["compute_has_local_agent"] == 1,
        detail=f"{dict(_hlaB)}→{dict(_hlaA)}")
# finding#1：amend 更正 court_region/party_region → 重新蓋章
_svcSN.amend_deadline(_hlaId, "法院所在地讀錯、更正", "王律師", court_region="臺中", party_region="臺南")
_hlaR = db.execute("SELECT compute_court_region,compute_party_region FROM deadlines WHERE id=?", (_hlaId,)).fetchone()
_assert("R2#1: amend(court/party_region) 更正並重新蓋章查表維度",
        _hlaR["compute_court_region"] == "臺中" and _hlaR["compute_party_region"] == "臺南",
        detail=str(dict(_hlaR)))
# finding#2：compute_* 計算輸入變更要進 deadline_audit 的 changed_fields（不只看衍生 in_transit_days）
_hlaAud = db.execute(
    "SELECT changed_fields FROM deadline_audit WHERE deadline_id=? ORDER BY id DESC LIMIT 1",
    (_hlaId,)).fetchone()
_assert("R2#2: compute_court_region 計算輸入變更進 audit changed_fields（可重建異動前提）",
        "compute_court_region" in (_hlaAud["changed_fields"] or ""), detail=str(dict(_hlaAud)))
# 另建一筆 pending 供 fail-closed 用（_amId 待會會被標 filed）
_rAm2 = _svcSN.create_deadline(
    matter_id=_midAm, type="appeal_civil", description="", trigger_event="判決送達",
    service_base_date="2026-06-01", service_type="normal", statutory_days=0, statutory_basis="",
    statutory_basis_version="", period_type="", severity="", has_local_agent=-1, in_transit_days=0,
    court_region="", party_region="", buffer_days=1, stated_period_days=0, document_date="",
    assignee="", assignee_line_user_id="", escalation_lead_days="", created_by="王律師")
_amId2 = int(_reAm.search(r"#(\d+)", _rAm2).group(1))
# 已遞交不可 amend
_svcSN.mark_deadline_filed(_amId, "王律師")
_assert("amend 防呆: 已遞交(filed)不可重算 → ERROR",
        "ERROR" in _svcSN.amend_deadline(_amId, "x", "王律師", service_base_date="2026-07-01"))
# fail-closed：floored 無 verified → 拒 amend（用仍 pending 的 _amId2）
_saved_fl_am = _osFC.environ.get("SME_FLOOR")
_saved_ls_am = _osFC.environ.get("LINE_STATE_DIR")
_osFC.environ["SME_FLOOR"] = "general"
_osFC.environ["LINE_STATE_DIR"] = "/tmp/_no_ar_amend_xyz"
try:
    _rAmFC = _svcSN.amend_deadline(_amId2, "fc", "agent自填", service_base_date="2026-07-01")
    _assert("amend fail-closed: floored 無 verified → 拒重算（防偽造異動人）",
            "ERROR" in _rAmFC and "無法驗證" in _rAmFC, detail=_rAmFC[:90])
finally:
    if _saved_fl_am is None:
        _osFC.environ.pop("SME_FLOOR", None)
    else:
        _osFC.environ["SME_FLOOR"] = _saved_fl_am
    if _saved_ls_am is None:
        _osFC.environ.pop("LINE_STATE_DIR", None)
    else:
        _osFC.environ["LINE_STATE_DIR"] = _saved_ls_am


# === 去識別化自檢閘 screen_calendar_text + privacy_audit（信任/稽核 #6c）===
print("\n=== 去識別化自檢閘 ===")
from shared.privacy import extract_party_names, scan_text_for_names  # noqa: E402
# 純函式：client_name 多名分隔 + 子字串命中
_assert("privacy 純函式: extract_party_names 分隔多名、濾掉長度<2",
        extract_party_names("王大明、李小華 / 甲") == ["王大明", "李小華"],
        detail=str(extract_party_names("王大明、李小華 / 甲")))
_assert("privacy 純函式: scan_text_for_names 子字串命中（保序去重）",
        scan_text_for_names("通知王大明開庭、王大明簽收", ["王大明", "李小華"]) == ["王大明"])
_assert("privacy 純函式: 空 text/names → 空", scan_text_for_names("", ["王"]) == [] and scan_text_for_names("x", []) == [])
_midPr = db.execute(
    "INSERT INTO matters (matter_no, title, client_name, status, has_local_agent, confidential) "
    "VALUES ('2026-pr-001', '請求給付貨款', '王大明、李小華', 'open', 1, 0)").lastrowid
db.commit()
# 命中 → 警告 + 列名 + 不宣稱不可能外流
_rHit = _svcSN.screen_calendar_text(_midPr, "王大明案 上訴期限 2026-06-22", "王律師")
_assert("screen: 命中當事人名→警告 + 列名 + 改代號建議 + 不宣稱保證不外流",
        "去識別化警告" in _rHit and "王大明" in _rHit and "2026-pr-001" in _rHit
        and "不代表保證不外流" in _rHit, detail=_rHit[:120])
# 通過（只用案件代號）
_rPass = _svcSN.screen_calendar_text(_midPr, "2026-pr-001 上訴期限 2026-06-22", "王律師")
_assert("screen: 只用案件代號→通過", "去識別化通過" in _rPass, detail=_rPass[:80])
# 留底只記數量、不把當事人名寫進 log（自檢不可反而漏 PII）
_scLog = db.execute(
    "SELECT detail FROM interaction_log WHERE action='calendar_privacy_screen' AND target_id=? "
    "ORDER BY id DESC LIMIT 1", (_midPr,)).fetchone()
_assert("screen 留底: log 只記命中數量、不含當事人名（自檢不漏 PII）",
        _scLog and "王大明" not in _scLog["detail"] and "命中" in _scLog["detail"],
        detail=str(dict(_scLog)) if _scLog else "None")
# 空文字防呆
_assert("screen 防呆: 空提議文字 → ERROR", "ERROR" in _svcSN.screen_calendar_text(_midPr, "", "王律師"))
# 無可比對 token（client_name 空）→ 不可靜默通過（codex#6c HIGH）：明示「無法自檢、不可視為安全」
_midNoName = db.execute(
    "INSERT INTO matters (matter_no, title, client_name, status, has_local_agent, confidential) "
    "VALUES ('2026-pr-002', '某案', '', 'open', 1, 0)").lastrowid
db.commit()
_rNoBasis = _svcSN.screen_calendar_text(_midNoName, "某案 上訴期限 2026-06-22", "王律師")
_assert("screen: client_name 空→無可比對 token→『無法自檢·不可視為安全』、不靜默通過",
        "無法自檢" in _rNoBasis and "不可視為" in _rNoBasis and "去識別化通過" not in _rNoBasis,
        detail=_rNoBasis[:120])
# privacy_audit：植入一筆含當事人名的 log → 掃得到、且跳過 calendar_privacy_screen 自檢列
db.execute("INSERT INTO interaction_log (actor,action,target_type,target_id,detail) "
           "VALUES ('系統','note','matter',?,?)", (_midPr, "提醒王大明的開庭日"))
db.commit()
_rAudit = _svcSN.privacy_audit(90, 200)
_assert("privacy_audit: 掃到漏進 log 的當事人名（命中王大明 + 對應案號）",
        "王大明" in _rAudit and "2026-pr-001" in _rAudit and "不證明未外流" in _rAudit,
        detail=_rAudit[:200])
_assert("privacy_audit: 不誤報自檢留底列（calendar_privacy_screen 只記數量、不算洩漏）",
        "calendar_privacy_screen" not in _rAudit)
# 同名多案歸因（codex#6c MED regression）：另建一案 client_name 也含「王大明」→ audit 命中時列出兩案
db.execute("INSERT INTO matters (matter_no, title, client_name, status, has_local_agent, confidential) "
           "VALUES ('2026-pr-003', '另案', '王大明', 'open', 1, 0)")
db.commit()
_rAudit2 = _svcSN.privacy_audit(90, 200)
_assert("privacy_audit: 同名對應多案→列出全部（2026-pr-001 與 2026-pr-003 皆現、不武斷指單案）",
        "2026-pr-001" in _rAudit2 and "2026-pr-003" in _rAudit2, detail=_rAudit2[:200])
# screen fail-closed：floored 無 verified → 拒（會寫 log → actor gate）
_saved_fl_pr = _osFC.environ.get("SME_FLOOR")
_saved_ls_pr = _osFC.environ.get("LINE_STATE_DIR")
_osFC.environ["SME_FLOOR"] = "general"
_osFC.environ["LINE_STATE_DIR"] = "/tmp/_no_ar_priv_xyz"
try:
    _rScFC = _svcSN.screen_calendar_text(_midPr, "2026-pr-001 期限", "agent自填")
    _assert("screen fail-closed: floored 無 verified → 拒（留底寫入需 verified）",
            "ERROR" in _rScFC and "無法驗證" in _rScFC, detail=_rScFC[:90])
finally:
    if _saved_fl_pr is None:
        _osFC.environ.pop("SME_FLOOR", None)
    else:
        _osFC.environ["SME_FLOOR"] = _saved_fl_pr
    if _saved_ls_pr is None:
        _osFC.environ.pop("LINE_STATE_DIR", None)
    else:
        _osFC.environ["LINE_STATE_DIR"] = _saved_ls_pr


# === Wave1 整合對應鍵：matters.pleading_case_id round-trip（create / get / link / unlink）===
# legal-admin ↔ pleading-manager 對應鍵只住 sme 側、nullable（契約 contract_sme_pleading_integration v2）。
import re as _reINT  # noqa: E402
_rINT = _svcSN.create_matter(
    "整合對應測試案", "2026-int-001", "", "civil", "", "", "", "陳律師", 0, 0, "操作者",
    "PLEAD-CASE-77")
_mINT = _reINT.search(r"#(\d+)", _rINT)
_mid_int = int(_mINT.group(1)) if _mINT else 0
_assert("Wave1 整合: create_matter 帶 pleading_case_id 成功建立", _mid_int > 0, detail=_rINT[:80])
_rGet = _svcSN.get_matter(_mid_int)
_assert("Wave1 整合: get_matter 顯示已綁定的 pleading 案件對應",
        "PLEAD-CASE-77" in _rGet and "pleading 案件對應" in _rGet, detail=_rGet[:120])
_rLink = _svcSN.link_matter_pleading(_mid_int, "PLEAD-CASE-99", "操作者")
_assert("Wave1 整合: link_matter_pleading 重新綁定成功",
        "已綁定" in _rLink and "PLEAD-CASE-99" in _rLink, detail=_rLink[:80])
_assert("Wave1 整合: 重新綁定後 get_matter 反映新對應",
        "PLEAD-CASE-99" in _svcSN.get_matter(_mid_int))
_rUnlink = _svcSN.link_matter_pleading(_mid_int, "", "操作者")  # 空=解除（pleading 案件被刪、sme 偵測 404 清理）
_assert("Wave1 整合: link_matter_pleading 空字串=解除綁定（case-deleted graceful 清理）",
        "解除" in _rUnlink, detail=_rUnlink[:80])
_assert("Wave1 整合: 解除後 get_matter 顯示未綁定", "未綁定" in _svcSN.get_matter(_mid_int))
_rBadLink = _svcSN.link_matter_pleading(999999, "PLEAD-X", "操作者")
_assert("Wave1 整合: link 不存在案件 → 乾淨 ERROR（不崩）",
        "ERROR" in _rBadLink and "找不到" in _rBadLink, detail=_rBadLink[:80])
_rPlain = _svcSN.create_matter("未綁定案", "2026-int-002", "", "", "", "", "", "", 0, 0, "操作者")
_mPlain = _reINT.search(r"#(\d+)", _rPlain)
_mid_plain = int(_mPlain.group(1)) if _mPlain else 0
_assert("Wave1 整合: 不帶 pleading_case_id 建案 → 預設未綁定（純單機、解耦）",
        _mid_plain > 0 and "未綁定" in _svcSN.get_matter(_mid_plain))


# === Task E：提醒 per-承辦 routing（target_line_user_id=承辦律師、非只 boss、boss 兜底/升級）===
from shared.deadlines import scan_and_enqueue_due_reminders as _scanE  # noqa: E402
from shared.escalation import resolve_escalation_target as _resolveE  # noqa: E402
_ATTY = "U" + "a" * 32   # 承辦律師 line_user_id（U+32hex、過 _looks_like_line_user_id）
# 保證有 boss（resolve step1 查 role='boss' active 員工）；OR IGNORE 避免 line_user_id UNIQUE 衝突
db.execute("INSERT OR IGNORE INTO employees (name, role, permissions, active, line_user_id) "
           "VALUES ('E所長','boss','admin',1,?)", ("U" + "b" * 32,))
db.commit()
_BOSS = _resolveE(db, "")[0]   # 動態取「實際 resolve 出的 boss」當期望值（穩健、不寫死 coalesce 結果）
_assert("Task E setup: 有 boss 兜底且≠承辦", bool(_BOSS) and _BOSS != _ATTY, detail=str(_BOSS))
_todayE = _dtA.date(2026, 6, 15)
_yestE = (_todayE - _dtA.timedelta(days=1)).isoformat()
_COLS_E = ("matter_id, type, description, period_type, severity, trigger_event, service_type, "
           "service_base_date, statutory_days, statutory_basis, internal_deadline, statutory_deadline, "
           "status, escalation_lead_days, reminders_sent, needs_manual_review, assignee, assignee_line_user_id")
def _mk_matter_E(no, title, lead=""):
    return db.execute(
        "INSERT INTO matters (matter_no, title, status, has_local_agent, confidential, lead_attorney) "
        "VALUES (?,?, 'open',1,0,?)", (no, title, lead or None)).lastrowid
def _mk_dl_E(mid, desc, internal, lead_days, atty_name, atty_uid):
    db.execute(
        f"INSERT INTO deadlines ({_COLS_E}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (mid, "appeal_civil", desc, "peremptory", "red", "判決送達", "normal", "2026-05-01", 20,
         "民訴§440", internal, internal, "pending", lead_days, "[]", 0, atty_name or None, atty_uid or None))
    db.commit()

# E1：approaching + 有承辦 line → 收件人=承辦（非 boss）
_mk_dl_E(_mk_matter_E("2026-E1-001", "E承辦approaching", "E律師"), "E承辦上訴",
         _todayE.isoformat(), "[0]", "E律師", _ATTY)
_scanE(today=_todayE.isoformat())
_rE1 = db.execute("SELECT target_line_user_id t FROM pending_escalations WHERE event_type='deadline_approaching' "
                  "AND summary LIKE '%E承辦approaching%' ORDER BY id DESC LIMIT 1").fetchone()
_assert("Task E: approaching 有承辦 line → 收件人=承辦律師（非 boss）",
        _rE1 and _rE1["t"] == _ATTY, detail=str(dict(_rE1)) if _rE1 else "None")

# E2：approaching + 無承辦 line → fallback boss（不靜默丟）
_mk_dl_E(_mk_matter_E("2026-E2-001", "E無承辦approaching"), "E無承辦上訴",
         _todayE.isoformat(), "[0]", "", "")
_scanE(today=_todayE.isoformat())
_rE2 = db.execute("SELECT target_line_user_id t FROM pending_escalations WHERE event_type='deadline_approaching' "
                  "AND summary LIKE '%E無承辦approaching%' ORDER BY id DESC LIMIT 1").fetchone()
_assert("Task E: approaching 無承辦 line → fallback boss（不靜默丟）",
        _rE2 and _rE2["t"] == _BOSS, detail=str(dict(_rE2)) if _rE2 else "None")

# E3：missed + 有承辦 → 承辦收主通知 + boss 收升級監督（dual-send、去重）
_mk_dl_E(_mk_matter_E("2026-E3-001", "E承辦missed", "E律師"), "E承辦逾期",
         _yestE, "[7,3,1,0]", "E律師", _ATTY)
_scanE(today=_todayE.isoformat())
_rE3a = db.execute("SELECT target_line_user_id t FROM pending_escalations WHERE event_type='deadline_missed' "
                   "AND summary LIKE '%E承辦missed%' AND summary NOT LIKE '%升級%' ORDER BY id DESC LIMIT 1").fetchone()
_rE3b = db.execute("SELECT target_line_user_id t FROM pending_escalations WHERE event_type='deadline_missed' "
                   "AND summary LIKE '%E承辦missed%' AND summary LIKE '%升級%' ORDER BY id DESC LIMIT 1").fetchone()
_assert("Task E: missed 有承辦 → 承辦收主通知", _rE3a and _rE3a["t"] == _ATTY,
        detail=str(dict(_rE3a)) if _rE3a else "None")
_assert("Task E: missed 有承辦 → boss 另收升級監督（dual-send、≠承辦）",
        _rE3b and _rE3b["t"] == _BOSS and _rE3b["t"] != _ATTY, detail=str(dict(_rE3b)) if _rE3b else "None")

# E4：missed + 無承辦 → 只 boss 一筆、無升級重複行
_mk_dl_E(_mk_matter_E("2026-E4-001", "E無承辦missed"), "E無承辦逾期", _yestE, "[7,3,1,0]", "", "")
_scanE(today=_todayE.isoformat())
_cE4 = db.execute("SELECT COUNT(*) c FROM pending_escalations WHERE event_type='deadline_missed' "
                  "AND summary LIKE '%E無承辦missed%'").fetchone()["c"]
_eE4 = db.execute("SELECT COUNT(*) c FROM pending_escalations WHERE event_type='deadline_missed' "
                  "AND summary LIKE '%E無承辦missed%' AND summary LIKE '%升級%'").fetchone()["c"]
_assert("Task E: missed 無承辦 → 僅 boss 一筆（無 dual-send 重複）", _cE4 == 1 and _eE4 == 0,
        detail=f"total={_cE4} esc={_eE4}")


# === Task D：每律師 pleading token 安全存放/選取（密鑰、雙牆、無讀回、active-only、whoami）===
_TOKD = "tok-D-" + "x" * 8
db.execute("INSERT OR IGNORE INTO employees (name, role, permissions, active, line_user_id) "
           "VALUES ('D律師','lawyer','basic',1,?)", ("U" + "d" * 32,))
db.execute("INSERT OR IGNORE INTO employees (name, role, active, line_user_id) "
           "VALUES ('D主辦','lawyer',1,?)", ("U" + "e" * 32,))
db.commit()
# D1：全權限層 bind 成功、回傳/稽核不洩 token（no-echo）
_rbindD = _svcSN.bind_pleading_token("D律師", _TOKD, "操作者")
_assert("Task D: bind_pleading_token 成功", "已綁定" in _rbindD and "D律師" in _rbindD, detail=_rbindD[:80])
_assert("Task D: bind 回傳不洩 token（no-echo）", _TOKD not in _rbindD, detail=_rbindD[:80])
_logD = db.execute("SELECT detail FROM interaction_log WHERE action='pleading_token_bound' "
                   "ORDER BY id DESC LIMIT 1").fetchone()
_assert("Task D: interaction_log 不記 token 明文", _logD and _TOKD not in (_logD["detail"] or ""),
        detail=str(dict(_logD)) if _logD else "None")
# D2：select 互動（actor_name）取得該律師 token
_assert("Task D: _select 互動(actor_name) 取得綁定 token",
        _svcSN._select_pleading_token(db, actor_name="D律師") == _TOKD)
# D3：select 自主 assignee→fallback lead_attorney；assignee 有 token 則優先
_svcSN.bind_pleading_token("D主辦", "tok-主辦", "操作者")
_assert("Task D: _select 自主 assignee 無 token → fallback lead_attorney",
        _svcSN._select_pleading_token(db, assignee_name="D無此人", lead_attorney_name="D主辦") == "tok-主辦")
_assert("Task D: _select assignee 有 token 優先（不 fallback）",
        _svcSN._select_pleading_token(db, assignee_name="D律師", lead_attorney_name="D主辦") == _TOKD)
# D4：whoami verify 失敗→失效回 ''；成功→回 token
_assert("Task D: _select verify=False（whoami 探活失敗）→ '' graceful skip",
        _svcSN._select_pleading_token(db, actor_name="D律師", verify=lambda t: False) == "")
_assert("Task D: _select verify=True → 回 token",
        _svcSN._select_pleading_token(db, actor_name="D律師", verify=lambda t: True) == _TOKD)
# D5：active-only（停用律師 token 不可用、防離職滯留）
db.execute("UPDATE employees SET active=0 WHERE name='D律師'"); db.commit()
_assert("Task D: 停用員工(active=0) token 不被選取",
        _svcSN._select_pleading_token(db, actor_name="D律師") == "")
db.execute("UPDATE employees SET active=1 WHERE name='D律師'"); db.commit()
# D6：unbind 清除 → select ''
_runbD = _svcSN.unbind_pleading_token("D律師", "操作者")
_assert("Task D: unbind 解除綁定", "已解除" in _runbD, detail=_runbD[:60])
_assert("Task D: unbind 後 _select 回 ''", _svcSN._select_pleading_token(db, actor_name="D律師") == "")
# D7：完全無此員工 → select ''
_assert("Task D: 無此人 → _select 回 ''", _svcSN._select_pleading_token(db, actor_name="完全沒這人") == "")
# D8：受限層 bind 被擋（service is_full_access 第二道）+ 原 token 未被竄改
import os as _osD  # noqa: E402
_savefloorD = _osD.environ.get("SME_FLOOR")
_osD.environ["SME_FLOOR"] = "general"
try:
    _rdenD = _svcSN.bind_pleading_token("D主辦", "tok-惡意", "受限層員工")
    _assert("Task D: 受限層 bind 被擋（全權限專屬、雙牆第二道）",
            "ERROR" in _rdenD and "全權限" in _rdenD, detail=_rdenD[:80])
finally:
    if _savefloorD is None:
        _osD.environ.pop("SME_FLOOR", None)
    else:
        _osD.environ["SME_FLOOR"] = _savefloorD
_assert("Task D: 受限層 bind 被擋後原 token 未被竄改",
        _svcSN._select_pleading_token(db, actor_name="D主辦") == "tok-主辦")
# D9：第一道牆——apply_floor_policy 在受限層物理移除 bind/unbind_pleading_token（密鑰雙牆）
from shared.floor_policy import apply_floor_policy as _afp, INTEGRATION_ADMIN_TOOLS as _IAT  # noqa: E402
class _FakeMcpD:
    def __init__(self): self.removed = []
    def remove_tool(self, name): self.removed.append(name)
_savefloorD9 = _osD.environ.get("SME_FLOOR")
_osD.environ["SME_FLOOR"] = "general"
try:
    _fmD = _FakeMcpD()
    _afp(_fmD)
    _assert("Task D: 第一道牆 apply_floor_policy 受限層移除 bind/unbind_pleading_token",
            set(_IAT) <= set(_fmD.removed), detail=str([x for x in _fmD.removed if "pleading" in x]))
finally:
    if _savefloorD9 is None:
        _osD.environ.pop("SME_FLOOR", None)
    else:
        _osD.environ["SME_FLOOR"] = _savefloorD9


# === codex follow-up 回歸測（HIGH/MED/LOW fix 的敏感失敗路徑）===
# CF1：_select 互動(actor) 無 token + 傳 lead → 禁止 fallback（codex HIGH、§127）
db.execute("INSERT OR IGNORE INTO employees (name, role, active, line_user_id) "
           "VALUES ('CF無token律師','lawyer',1,?)", ("U" + "f" * 32,))
db.commit()
_assert("codex-HIGH fix: 互動 actor 無 token + 傳 lead_attorney → 不 fallback、回 ''",
        _svcSN._select_pleading_token(db, actor_name="CF無token律師", lead_attorney_name="D主辦") == "")
_assert("codex-HIGH fix: 對照組——自主(無 actor) assignee 無 token → 仍 fallback lead",
        _svcSN._select_pleading_token(db, assignee_name="CF無token律師", lead_attorney_name="D主辦") == "tok-主辦")
# CF2：同名歧義 → bind 報錯、_select 回 ''（codex MED；token=身分不可猜）
db.execute("INSERT INTO employees (name, role, active, line_user_id) VALUES ('CF雙胞','lawyer',1,?)", ("U" + "1" * 32,))
db.execute("INSERT INTO employees (name, role, active, line_user_id) VALUES ('CF雙胞','lawyer',1,?)", ("U" + "2" * 32,))
db.commit()
_rAmb = _svcSN.bind_pleading_token("CF雙胞", "tok-雙胞", "操作者")
_assert("codex-MED fix: 同名在職員工 bind 被拒（不綁錯人）", "ERROR" in _rAmb and "多位同名" in _rAmb, detail=_rAmb[:80])
_assert("codex-MED fix: 同名 _select 回 ''（不猜身分）", _svcSN._select_pleading_token(db, actor_name="CF雙胞") == "")
# CF3：malformed assignee_line_user_id 的 missed → 只 boss 一筆、無誤升級重複（codex MED dedup）
_mkCF = db.execute("INSERT INTO matters (matter_no,title,status,has_local_agent,confidential) "
                   "VALUES ('2026-CF-001','CF髒值missed','open',1,0)").lastrowid
db.execute(f"INSERT INTO deadlines ({_COLS_E}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
           (_mkCF, "appeal_civil", "CF髒值逾期", "peremptory", "red", "判決送達", "normal", "2026-05-01", 20,
            "民訴§440", _yestE, _yestE, "pending", "[7,3,1,0]", "[]", 0, "髒值律師", "NOT-A-VALID-UID"))
db.commit()
_scanE(today=_todayE.isoformat())
_cCF = db.execute("SELECT COUNT(*) c FROM pending_escalations WHERE event_type='deadline_missed' "
                  "AND summary LIKE '%CF髒值missed%'").fetchone()["c"]
_assert("codex-MED fix: 髒值 assignee_line_user_id missed → 只 boss 一筆（無誤升級重複）", _cCF == 1, detail=f"rows={_cCF}")
# CF4：link_matter_pleading 對機密案在受限層回泛化 not-found（oracle、codex LOW）
_midCFc = int(_reINT.search(r"#(\d+)", _svcSN.create_matter("CF機密案","2026-CF-002","","","","","","",0,1,"操作者")).group(1))
_saveflCF = _osD.environ.get("SME_FLOOR")
_osD.environ["SME_FLOOR"] = "general"
try:
    _rOra = _svcSN.link_matter_pleading(_midCFc, "PLEAD-X", "agent自填")
    # oracle：機密案回應＝「同一個 id 不存在」會回的字串（byte 相同、訊息只含呼叫者自傳的 id，
    # 不洩『該 id 存在但機密』這一位元）。故比對「同 id 的 not-found 字串」、非跨不同 id。
    _assert("codex-LOW fix: 受限層 link 機密案 → 與『同 id 不存在』回相同 not-found（不洩存在）",
            _rOra == f"ERROR: 找不到案件 #{_midCFc}", detail=_rOra[:60])
finally:
    if _saveflCF is None:
        _osD.environ.pop("SME_FLOOR", None)
    else:
        _osD.environ["SME_FLOOR"] = _saveflCF


db.close()


# === Summary ===
print("\n" + "=" * 60)
total = passed + failed
print(f"Results: {passed} passed, {failed} failed out of {total}")
if failed:
    print("\nFailures:")
    for name in failures:
        print(f"  - {name}")
    sys.exit(1)
else:
    print("\nALL TESTS PASSED")
    sys.exit(0)
