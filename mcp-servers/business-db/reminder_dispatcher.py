#!/usr/bin/env python3
"""OS cron 笨投遞器 — 把到期的 scheduled_reminders 推給對象（派工器模式）。

獨立進程、host 跑（不受 LINE-runtime sandbox 管、讀得到 DB + LINE token）。鏡像 flush_escalations.py：
本檔只負責「載入 token + 真實 push + 接 cron」這層薄殼（直接重用 flush_escalations 的 _load_tokens /
_make_push），投遞政策（claim / advance / at-most-once）全在 shared.reminders.flush_due_reminders。

runtime 用 gated MCP 工具 schedule_reminder / cancel_reminder 自助排程，本投遞器定時消化——runtime
永遠碰不到 live crontab（保住 sandbox 第一道牆：cron job 跑在 sandbox 外＝host 持久化逃逸原語）。

部署（crontab，每 2 分鐘；路徑換成你的絕對路徑；token 走 data/line-channels.json 或 .mcp.json，不必放進 crontab）：
  */2 * * * * SME_DB_PATH=/abs/data/business.db \\
      /abs/.venv/bin/python3 \\
      /abs/mcp-servers/business-db/reminder_dispatcher.py >> /abs/data/reminder.log 2>&1
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
# 投遞器只照 row 推、不解析身份 → 不需要 floor；移除避免任何 floor 副作用（同 flush_escalations）。
os.environ.pop("SME_FLOOR", None)


def main() -> int:
    from flush_escalations import _load_tokens, _make_push  # 重用 token 載入 + push 薄殼（DRY）
    from shared.reminders import flush_due_reminders

    tokens, default_id = _load_tokens()
    if not tokens:
        print("reminder_dispatcher: 無 LINE token（data/line-channels.json 或 CHANNEL_ACCESS_TOKEN）、略過")
        return 0
    stats = flush_due_reminders(_make_push(tokens, default_id))
    print(f"reminder_dispatcher: {stats}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
