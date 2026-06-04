"""import_office_calendar.py 單元測試（offline、synthetic fixture、不連網）。

跑法：
    cd mcp-servers/business-db
    SME_DB_PATH=/tmp/_t_cal.db /abs/.venv/bin/python3 tests/test_office_calendar_import.py

涵蓋（含 codex r4 HIGH 修補）：
- 正常：整年逐日匯入、YYYYMMDD→ISO、isHoliday→is_holiday、補班（週末+false）、idempotent 重跑
- 完整年度不變量：半套年度 / 混年 / 重複日 一律 raise + 原子 rollback（不載半套、避免被誤判已載入）
- 實日期驗證：八位數但非實日（20271340）raise（不落 2027-13-40 髒資料）
- 反捏造：isHoliday 非布林 / 頂層非陣列 raise
- calendar_year_loaded：完整年度→True；半套（直接塞 <365 列）→False
"""
import atexit
import datetime as dt
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
from shared.deadlines import calendar_year_loaded  # noqa: E402
import import_office_calendar as imp  # noqa: E402

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


def _write_json(obj):
    f = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w", encoding="utf-8")
    json.dump(obj, f, ensure_ascii=False)
    f.close()
    return f.name


def _full_year(year, holidays=None, makeups=None):
    """產生某年逐日完整的 TaiwanCalendar 格式陣列（週末預設假日；holidays 強制假日、makeups 強制上班）。"""
    holidays = set(holidays or ())
    makeups = set(makeups or ())
    out = []
    d = dt.date(year, 1, 1)
    while d.year == year:
        iso = d.isoformat()
        is_wknd = d.weekday() >= 5
        ih = (is_wknd or iso in holidays) and iso not in makeups
        desc = "假日" if iso in holidays else ("補班(synthetic)" if iso in makeups else "")
        out.append({"date": d.strftime("%Y%m%d"), "week": "", "isHoliday": ih, "description": desc})
        d += dt.timedelta(days=1)
    return out


# === 1. 正常：整年逐日匯入 + 映射 + 補班 ===
_Y = 2027  # 非閏年 365 天
_sat = dt.date(_Y, 1, 1)
while _sat.weekday() != 5:  # 該年第一個週六當 synthetic 補班
    _sat += dt.timedelta(days=1)
_sat_iso = _sat.isoformat()
full = _full_year(_Y, holidays={f"{_Y}-01-01"}, makeups={_sat_iso})
p_full = _write_json(full)
with transaction() as db:
    n = imp.import_file(db, p_full)
_assert("整年匯入筆數=365", n == 365, detail=str(n))

db = get_db()
try:
    jan1 = db.execute(
        "SELECT is_holiday, description FROM office_calendar WHERE date=?", (f"{_Y}-01-01",)
    ).fetchone()
    _assert("平日國定假日 is_holiday=1 + description", jan1 and jan1[0] == 1 and jan1[1] == "假日")
    mk = db.execute("SELECT is_holiday FROM office_calendar WHERE date=?", (_sat_iso,)).fetchone()
    _assert("補班（週六 isHoliday=false）→ is_holiday=0", mk and mk[0] == 0)
    _assert("完整年度 → calendar_year_loaded=True", calendar_year_loaded(_Y, db) is True)
finally:
    db.close()

# === 2. idempotent 重跑（UPSERT、不重複、可更新）===
full2 = _full_year(_Y, holidays={f"{_Y}-01-01"}, makeups={_sat_iso})
for r in full2:
    if r["date"] == f"{_Y}0101":
        r["description"] = "元旦(更新版)"
p_full2 = _write_json(full2)
with transaction() as db:
    imp.import_file(db, p_full2)
db = get_db()
try:
    cnt = db.execute("SELECT COUNT(*) FROM office_calendar WHERE date LIKE ?", (f"{_Y}-%",)).fetchone()[0]
    _assert("idempotent：整年仍 365 列（PK UPSERT、不翻倍）", cnt == 365, detail=str(cnt))
    desc = db.execute("SELECT description FROM office_calendar WHERE date=?", (f"{_Y}-01-01",)).fetchone()[0]
    _assert("idempotent：重跑覆寫 description", desc == "元旦(更新版)", detail=desc)
finally:
    db.close()


def _expect_raise(name, obj_or_path, contains=""):
    """匯入應 raise ValueError、且原子 rollback（不留髒資料）。"""
    path = obj_or_path if isinstance(obj_or_path, str) else _write_json(obj_or_path)
    raised = False
    msg = ""
    try:
        with transaction() as db:
            imp.import_file(db, path)
    except ValueError as e:
        raised = True
        msg = str(e)
    _assert(name, raised and (contains in msg if contains else True), detail=msg)


# === 3. 完整年度不變量（codex r4 HIGH）===
_expect_raise("半套年度（364 天）→ raise（不收半套）", full[:-1], contains="逐日完整")
_mixed = _full_year(_Y) + [{"date": f"{_Y + 1}0101", "isHoliday": True, "description": ""}]
_expect_raise("混年度（2027+2028 一筆）→ raise（單一年度）", _mixed, contains="單一年度")
_dup = _full_year(_Y)
_dup[10] = dict(_dup[0])  # 製造重複日（仍 365 筆但有 dup）
_expect_raise("重複日 → raise", _dup, contains="重複")

# === 4. 實日期驗證（codex r4 HIGH）：八位數但非實日 ===
_expect_raise("20271340（八位數非實日）→ raise（不落 2027-13-40）",
              [{"date": "20271340", "isHoliday": True, "description": "非實日"}],
              contains="非實際存在")

# === 5. 反捏造其他格式 ===
_expect_raise("isHoliday 非布林（int）→ raise", [{"date": "20270301", "isHoliday": 1, "description": ""}])
_expect_raise("頂層非陣列 → raise", {"date": "20270101"})

# === 6. 原子 rollback：上面失敗檔皆不得落任何 2028 / 髒資料 ===
db = get_db()
try:
    leaked = db.execute(
        "SELECT COUNT(*) FROM office_calendar WHERE date LIKE '2028-%' OR date='2027-13-40'"
    ).fetchone()[0]
    _assert("失敗檔原子 rollback：無 2028 / 髒日期落地", leaked == 0, detail=str(leaked))
finally:
    db.close()

# === 7. calendar_year_loaded：半套（直接塞 <365 列）→ False（第二道防線）===
with transaction() as db:
    for i in range(10):
        d = dt.date(2031, 1, 1) + dt.timedelta(days=i)
        db.execute(
            "INSERT OR REPLACE INTO office_calendar (date,is_holiday,description,source) VALUES (?,?,?,?)",
            (d.isoformat(), 1 if d.weekday() >= 5 else 0, "", "synthetic-partial"))
db = get_db()
try:
    _assert("半套年度（10 列）→ calendar_year_loaded=False（不被誤判已載入）",
            calendar_year_loaded(2031, db) is False)
finally:
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
