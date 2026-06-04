#!/usr/bin/env python3
"""OS cron 待確認時限跟催（legal-admin #H2、鏡像 scan_deadlines.py 薄殼）。

掃 pending_intakes status='awaiting'（抽出但人忘了確認入庫的時限）→ 命中等待節點 enqueue
intake_unconfirmed 跟催、接現役三層投遞推給老闆/全所。補核心 loop「一鍵確認才入」的結構盲區：
丟了檔、AI 推確認、人忘了回 → 時限沒進 deadlines 表 → 一般掃描（WHERE status='pending'）掃不到
→ 隱形漏掉（漏期＝執業過失）。

邏輯全在 shared.deadlines.scan_and_enqueue_unconfirmed_intakes（提醒只列『送達日 + 文書類型 +
等待時數』等抽出的事實、絕不端出引擎 computed deadline——待確認階段根本還沒算）。本檔只接 cron 薄殼。

部署（crontab，建議每數小時；路徑換成你的絕對路徑、分鐘數與其他掃描錯開）：
  37 */4 * * * SME_DB_PATH=/abs/data/business.db \\
      /abs/.venv/bin/python3 /abs/mcp-servers/business-db/scan_unconfirmed_intake.py >> /abs/data/intake.log 2>&1
cron 在 host 跑、不受 LINE-runtime sandbox 管（讀得到 DB）。
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
# 跟催以「系統觸發」蓋章 source_floor（enqueue 內部讀）；移除 SME_FLOOR 避免任何 floor 副作用。
os.environ.pop("SME_FLOOR", None)


def main() -> int:
    from shared.deadlines import scan_and_enqueue_unconfirmed_intakes
    stats = scan_and_enqueue_unconfirmed_intakes()
    print(f"scan_unconfirmed_intake: {stats}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
