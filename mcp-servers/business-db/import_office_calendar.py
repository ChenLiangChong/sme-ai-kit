#!/usr/bin/env python3
"""office_calendar 匯入器 — 從 TaiwanCalendar 格式 JSON 灌辦公日曆（末日順延 民法§122 的資料底）。

為何需要（legal-admin）：時限引擎末日順延（民法§122）讀 `office_calendar` 判「非上班日」——
國定假日、調整放假、補班日，**不是單純週末**（平日的國定假日要順延、補班的週末不順延）。
migration 012 只種了部分年度（MVP 2026）；未載入年度引擎會 fail-toward 標 needs_manual_review
（見 shared/deadlines.calendar_year_loaded）。本匯入器吃官方來源 JSON 一次灌任意年度。

反捏造鐵律：**不憑記憶打日期**（填錯假日＝算錯期限＝執業過失）。資料一律來自來源檔，`source`
欄記來源檔名供律師覆核。可重跑、idempotent（date 為 PK、UPSERT）。

JSON 格式（TaiwanCalendar，每筆一天、整年逐日）：
  [{"date":"YYYYMMDD","week":"四","isHoliday":true,"description":"開國紀念日"}, ...]
  isHoliday=true → 非上班日（含週末與國定假日）；false → 上班日（含補班的週末）。
  整年逐日匯入後，office_calendar 對該年「每一天」都有權威紀錄、is_holiday 不再退回週末預設。

用法：
  SME_DB_PATH=/abs/data/business.db /abs/.venv/bin/python3 import_office_calendar.py <檔1.json> [<檔2.json> ...]

取得來源檔（部署時、需網路一次；之後離線跑）：
  curl -sO https://raw.githubusercontent.com/ruyut/TaiwanCalendar/master/data/2027.json
  （或行政院人事行政總處《政府行政機關辦公日曆表》自行轉成同格式；務必與官方對賬）

原子性：所有檔在同一 transaction 內匯入，任一筆格式錯 → 全部 rollback、不半套（不留髒資料）。
"""
import json
import os
import re
import sys
from datetime import date, datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
# 純資料維護、不解析身份；移除 floor 避免任何副作用（同 scan_deadlines.py）。
os.environ.pop("SME_FLOOR", None)

_DATE_RE = re.compile(r"^\d{8}$")


def _is_leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _days_in_year(year: int) -> int:
    return 366 if _is_leap(year) else 365


def import_file(db, path: str) -> int:
    """把單一 TaiwanCalendar JSON 檔 upsert 進 office_calendar，回傳匯入筆數。

    **完整年度不變量（codex r4 HIGH）**：辦公日曆是末日順延的命脈，半套年度＝缺的國定假日會靜默退回
    週末預設＝算錯期限。故本匯入器只收「**單一年度、逐日完整覆蓋（365/366）、日期唯一**」的檔；
    任何缺日 / 混年 / 重複 / 八位數但非實日（如 20261340）一律 raise、整批 rollback、不載半套或髒資料。
    （搭配 shared.deadlines.calendar_year_loaded 也改為「該年列數達整年才算已載入」雙重把關。）

    db 為 caller-managed 連線（不在此 commit）。
    """
    with open(path, encoding="utf-8") as f:
        rows = json.load(f)
    if not isinstance(rows, list):
        raise ValueError(f"{path}: 頂層必須是陣列（TaiwanCalendar 格式）")

    parsed: list[tuple[str, int, str]] = []
    seen: set[str] = set()
    years: set[int] = set()
    for i, r in enumerate(rows):
        if not isinstance(r, dict):
            raise ValueError(f"{path}[{i}]: 每筆須為物件，got {type(r).__name__}")
        d = str(r.get("date", "")).strip()
        if not _DATE_RE.match(d):
            raise ValueError(
                f"{path}[{i}]: date 須為 YYYYMMDD 八位數字，got {d!r}（反捏造：不載髒資料）"
            )
        # 八位數還不夠——必須是「真實存在的日期」（擋 20261340 這種落 2026-13-40 的髒資料）
        try:
            dt = datetime.strptime(d, "%Y%m%d").date()
        except ValueError:
            raise ValueError(f"{path}[{i}]: {d!r} 非實際存在的日期（YYYYMMDD）")
        iso = dt.isoformat()
        if iso in seen:
            raise ValueError(f"{path}[{i}]: 日期重複 {iso}（同年不可有重複日）")
        seen.add(iso)
        years.add(dt.year)
        ih = r.get("isHoliday")
        if not isinstance(ih, bool):
            raise ValueError(f"{path}[{i}] {iso}: isHoliday 須為布林，got {ih!r}")
        desc = str(r.get("description", "") or "")
        parsed.append((iso, 1 if ih else 0, desc))

    # 完整年度把關：單一年度 + 逐日完整覆蓋（不可半套）
    if len(years) != 1:
        raise ValueError(
            f"{path}: 一個檔只能是單一年度（TaiwanCalendar 每年一檔），偵測到年度 {sorted(years)}"
        )
    yr = next(iter(years))
    expected = _days_in_year(yr)
    if len(parsed) != expected:
        raise ValueError(
            f"{path}: {yr} 年須逐日完整覆蓋 {expected} 天，實得 {len(parsed)} 天"
            f"（不收半套年度——缺日會讓末日順延誤算）"
        )

    src = f"TaiwanCalendar import:{os.path.basename(path)}"
    for iso, ih, desc in parsed:
        db.execute(
            "INSERT INTO office_calendar (date, is_holiday, description, source) "
            "VALUES (?,?,?,?) "
            "ON CONFLICT(date) DO UPDATE SET "
            "  is_holiday=excluded.is_holiday, "
            "  description=excluded.description, "
            "  source=excluded.source",
            (iso, ih, desc, src),
        )
    return len(parsed)


def main(argv) -> int:
    if len(argv) < 2:
        print(
            "用法：import_office_calendar.py <檔1.json> [<檔2.json> ...]\n"
            "  取得來源：curl -sO https://raw.githubusercontent.com/ruyut/TaiwanCalendar/master/data/<年>.json",
            file=sys.stderr,
        )
        return 2
    from shared.db import transaction

    total = 0
    with transaction() as db:  # 全檔同一 tx、任一檔錯則整批 rollback
        for path in argv[1:]:
            n = import_file(db, path)
            print(f"匯入 {path}: {n} 筆")
            total += n
    print(f"office_calendar 匯入完成：共 {total} 筆")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
