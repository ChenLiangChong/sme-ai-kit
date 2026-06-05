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
_assert("種子: 刑事上訴=20 日（刑訴§349、110修正 10→20）",
        STATUTORY_PERIODS["appeal_criminal"]["statutory_days"] == 20)
_assert("種子: 訴願=30 日（訴願法§14）",
        STATUTORY_PERIODS["petition_appeal"]["statutory_days"] == 30)
_assert("種子: 支付命令異議=20 日（民訴§516）",
        STATUTORY_PERIODS["payment_order_objection"]["statutory_days"] == 20)


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
# 刑訴§349 上訴期間 2021-06-16 由 10→20。早於此日的文書 → 須人工複核。
_la349_old = compute_deadline(
    period_type="peremptory", statutory_days=20, statutory_basis="刑訴§349",
    service_type="normal", service_base_date="2020-03-01", has_local_agent=True)
_assert("法版A: 2020 刑訴§349 判決(早於2021-06-16) → needs_manual_review",
        _la349_old["needs_manual_review"] is True,
        detail=str([t for t in _la349_old["calc_trace"] if "法版" in t]))
_assert("法版A: calc_trace 誠實標明修法施行日 + 修正前 10 日(不謊報、不重算)",
        any("法版檢核" in t and "2021-06-16" in t and "10 日" in t
            for t in _la349_old["calc_trace"]))
# 邊界：恰在施行日當天 → base < eff 為 strict、不觸發（適用新法）
_la349_edge = compute_deadline(
    period_type="peremptory", statutory_days=20, statutory_basis="刑訴§349",
    service_type="normal", service_base_date="2021-06-16", has_local_agent=True)
_assert("法版A: 施行日當天(2021-06-16) → 不觸發法版複核(適用新法)",
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
    service_type="normal", service_base_date="2020-03-01", has_local_agent=True)
_assert("法版MED3: 刑訴§349之1(另一條) 舊文書 → 不誤觸發法版(無假陽性)",
        not any("法版檢核" in t for t in _la349sub["calc_trace"]))
# 全名寫法「刑事訴訟法第349條」舊文書 → 仍須命中（不可因寫法不同漏報）
_la349full = compute_deadline(
    period_type="peremptory", statutory_days=20, statutory_basis="刑事訴訟法第349條",
    service_type="normal", service_base_date="2020-03-01", has_local_agent=True)
_assert("法版MED3: 刑事訴訟法第349條(全名) 舊文書 → 仍命中法版(不漏報)",
        _la349full["needs_manual_review"] is True
        and any("法版檢核" in t for t in _la349full["calc_trace"]))

# --- HIGH-1：法版適用依「文書作成日」而非送達日（舊判決可能修法後才送達）---
# 判決作成 2021-06-10（早於 §349 修法）但 2021-07-01 才送達：給 document_date → 應命中
_la349_doc = compute_deadline(
    period_type="peremptory", statutory_days=20, statutory_basis="刑訴§349",
    service_type="normal", service_base_date="2021-07-01", has_local_agent=True,
    document_date="2021-06-10")
_assert("法版HIGH1: 文書作成日早於修法(送達在後) → 命中法版複核(用文書作成日、非送達日)",
        _la349_doc["needs_manual_review"] is True
        and any("法版檢核" in t and "文書作成日2021-06-10" in t for t in _la349_doc["calc_trace"]))
# 同送達日但未給 document_date → 以送達日(2021-07-01、在修法後)近似 → 不命中，且 trace 須誠實標明近似
_la349_nodoc = compute_deadline(
    period_type="peremptory", statutory_days=20, statutory_basis="刑訴§349",
    service_type="normal", service_base_date="2021-07-01", has_local_agent=True)
_assert("法版HIGH1: 未給文書作成日、送達在修法後 → 不誤報(以送達日近似)",
        not any("法版檢核" in t for t in _la349_nodoc["calc_trace"]))
# 未給 document_date 但送達日本身早於修法 → 命中，trace 標「送達日近似」（誠實、不謊稱精確）
_la349_nodoc_old = compute_deadline(
    period_type="peremptory", statutory_days=20, statutory_basis="刑訴§349",
    service_type="normal", service_base_date="2020-03-01", has_local_agent=True)
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
_assert("教示B: 教示非數字 → 安全退回 'not_provided'、不炸",
        _pm_bad["period_match"] == "not_provided")


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
    document_date="2021-06-10", assignee="", assignee_line_user_id="", escalation_lead_days="", created_by="測試",
)
_dDoc = db.execute(
    "SELECT document_date, needs_manual_review FROM deadlines WHERE matter_id=? ORDER BY id DESC LIMIT 1",
    (_midSN,)
).fetchone()
_assert("端到端: document_date='2021-06-10' 落欄", _dDoc and _dDoc["document_date"] == "2021-06-10",
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
