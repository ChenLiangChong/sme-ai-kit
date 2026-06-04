#!/usr/bin/env python3
"""OS cron 健康哨兵 watchdog（legal-admin #H1、極小 dead-man、鏡像 scan_deadlines.py 薄殼）。

為何要「第二支極小 cron」而非塞進 scan_deadlines：互為 dead-man。scan_deadlines 若有 bug 每次
crash，住在同一支腳本內的監看也永遠跑不到；故 watchdog 必須是另一支極簡、幾乎不會自己壞的進程。

兩件事（邏輯全在 shared.deadlines.scan_health_and_alert）：
  (1) 落自身 heartbeat＝自證活著（全權限開機 readout 才能反過來偵測「連 watchdog 都死了」）；
  (2) 偵測 scan_deadlines 失聯（heartbeat 過期 SCAN_STALE_HOURS / 從未跑但已有待處理時限）→
      enqueue scan_stalled 上報、接現役三層投遞推給老闆。時間驅動（人沒開 Claude 也照跑）。
      同一失聯期最多每 SCAN_REALERT_HOURS 告警一次（防洗版）。

部署（crontab，建議每 1~2 小時；路徑換成你的絕對路徑、分鐘數與 scan_deadlines 錯開避免搶鎖）：
  17 */2 * * * SME_DB_PATH=/abs/data/business.db \\
      /abs/.venv/bin/python3 /abs/mcp-servers/business-db/scan_heartbeat.py >> /abs/data/heartbeat.log 2>&1
cron 在 host 跑、不受 LINE-runtime sandbox 管（讀得到 DB）。
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
# watchdog 以「系統觸發」蓋章 source_floor（enqueue 內部讀）；移除 SME_FLOOR 避免任何 floor 副作用。
os.environ.pop("SME_FLOOR", None)


def main() -> int:
    from shared.deadlines import scan_health_and_alert
    stats = scan_health_and_alert()
    print(f"scan_heartbeat: {stats}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
