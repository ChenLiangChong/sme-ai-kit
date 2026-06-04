#!/usr/bin/env python3
"""OS cron 時限掃描器（legal-admin、鏡像 flush_escalations.py 薄殼模式）。

時間驅動寫入端：每日讀 pending deadlines → 命中 escalation_lead_days 節點 / 逾期 → enqueue 一筆
pending_escalations（接現役三層投遞，零改動複用）。獨立進程、不靠 agent / CC session
（真「硬接線」：人沒開 Claude 也在倒數）。

計算政策（讀落欄日期、不重算法律邏輯、冪等鑰 reminders_sent）全在
shared.deadlines.scan_and_enqueue_due_reminders；本檔只負責「接 cron」這層薄殼。
enqueue 後的實際 LINE 推送交給既有 flush_escalations.py（保證層）+ claude -p notifier（品質層）。

部署（crontab，每日 07:00；路徑換成你的絕對路徑）：
  0 7 * * * SME_DB_PATH=/abs/data/business.db \\
      /abs/.venv/bin/python3 /abs/mcp-servers/business-db/scan_deadlines.py >> /abs/data/scan.log 2>&1
cron 在 host 跑、不受 LINE-runtime sandbox 管（讀得到 DB）。
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
# 掃描器不解析身份、不需 floor（enqueue 內部以系統觸發蓋章 source_floor）；移除避免任何 floor 副作用。
os.environ.pop("SME_FLOOR", None)


def main() -> int:
    from shared.deadlines import scan_and_enqueue_due_reminders
    stats = scan_and_enqueue_due_reminders()
    print(f"scan_deadlines: {stats}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
