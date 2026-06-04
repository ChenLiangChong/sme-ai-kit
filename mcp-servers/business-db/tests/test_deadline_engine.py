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
_assert("is_holiday: 2026-02-07 補班（種子 is_holiday=0、週六仍上班）=False",
        is_holiday("2026-02-07", db) is False)
_assert("is_holiday: 2026-06-20 週六（無種子→預設週末）=True", is_holiday("2026-06-20", db) is True)
_assert("is_holiday: 2026-06-22 週一（無種子→平日）=False", is_holiday("2026-06-22", db) is False)


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
_assert("bug2: calc_trace 誠實標明『辦公日曆未載入』+ 須人工複核",
        any("辦公日曆未載入" in t and "人工複核" in t for t in r12["calc_trace"]),
        detail=str(r12["calc_trace"]))
# 2026 全程（不跨年）不應誤觸日曆未載入
r12b = _calc(
    period_type="statutory", statutory_days=20, statutory_basis="民訴§440",
    service_type="normal", service_base_date="2026-06-01", has_local_agent=True, buffer_days=1,
)
_assert("bug2: 2026 全程不誤觸日曆未載入複核", r12b["needs_manual_review"] is False)


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
    court_region="taipei", party_region="kinmen", buffer_days=1,
    assignee="", assignee_line_user_id="", escalation_lead_days="", created_by="測試",
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
