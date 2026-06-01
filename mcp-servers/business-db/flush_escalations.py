#!/usr/bin/env python3
"""OS cron 笨投遞器（#9d/#173）— 把 pending_escalations 推給主管。

獨立進程、不靠 agent / CC session（真「硬接線」：runtime 全關也照跑）。投遞政策（select→push→
sent/retry/failed、backoff、rowcount guard）全在 shared.escalation.flush_pending_escalations、
本檔只負責「載入 LINE token + 真實 push + 接 cron」這層薄殼，鏡像 line-channel 的 loadChannels/linePush。

部署（crontab，每 2 分鐘；路徑換成你的絕對路徑）：
  */2 * * * * SME_DB_PATH=/abs/data/business.db CHANNEL_ACCESS_TOKEN=xxxxx \\
      /abs/.venv/bin/python3 /abs/mcp-servers/business-db/flush_escalations.py >> /abs/data/flush.log 2>&1
多 OA：改放 data/line-channels.json（{"channels":{"id":{"access_token":...}},"default_channel_id":"id"}），
不必設 env token。cron 在 host 跑、不受 LINE-runtime sandbox 管（讀得到 DB + token）。

LINE push 限制（critic）：對「未加該 OA 好友」的主管回 200 但靜默不達＝無法在此層偵測（push API 無回條）；
硬失敗（401 invalid token / 400 bad user / 429 quota）會走 retry→failed 終態、由全權限層開機 readout 提醒。
緩解＝onboarding 要求老闆先加 OA 好友 + 設好 line_user_id。
"""
import json
import os
import sys
import urllib.error
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
# flush 只投遞「已寫死收件人」的 row、不解析身份 → 不需要 floor；移除避免任何 floor 副作用。
os.environ.pop("SME_FLOOR", None)

PROJECT_ROOT = os.path.dirname(os.path.dirname(_HERE))


def _load_tokens():
    """回 (tokens={channel_id: access_token}, default_id)。三來源優先序：
    1) data/line-channels.json（多 OA）2) env CHANNEL_ACCESS_TOKEN（單 OA）
    3) .mcp.json line server 的 CHANNEL_ACCESS_TOKEN（cron 環境：不必把 secret 放進 crontab）。"""
    # 1) data/line-channels.json
    try:
        with open(os.path.join(PROJECT_ROOT, "data", "line-channels.json"), "r", encoding="utf-8") as f:
            cfg = json.load(f)
        chans = cfg.get("channels", {}) or {}
        tokens = {cid: c.get("access_token", "") for cid, c in chans.items() if c.get("access_token")}
        if tokens:
            return tokens, (cfg.get("default_channel_id") or next(iter(tokens)))
    except Exception:
        pass
    # 2) env
    env_tok = os.environ.get("CHANNEL_ACCESS_TOKEN", "")
    if env_tok:
        return {"default": env_tok}, "default"
    # 3) .mcp.json 的 line server token（host cron 直接讀、crontab 不必帶 secret）
    try:
        with open(os.path.join(PROJECT_ROOT, ".mcp.json"), "r", encoding="utf-8") as f:
            srv = (json.load(f) or {}).get("mcpServers", {})
        for v in srv.values():
            tok = ((v or {}).get("env", {}) or {}).get("CHANNEL_ACCESS_TOKEN")
            if tok:
                return {"default": tok}, "default"
    except Exception:
        pass
    return {}, "default"


def _make_push(tokens, default_id):
    def push(channel_id, to, text) -> bool:
        token = tokens.get(channel_id) or tokens.get(default_id) or ""
        if not token or not to:
            return False
        body = json.dumps({"to": to, "messages": [{"type": "text", "text": text}]}).encode("utf-8")
        req = urllib.request.Request(
            "https://api.line.me/v2/bot/message/push", data=body, method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except urllib.error.HTTPError as e:
            # 4xx/5xx 硬失敗（401/400/429…）→ False → retry/failed 終態
            try:
                detail = e.read()[:200].decode("utf-8", "replace")
            except Exception:
                detail = ""
            sys.stderr.write(f"flush push HTTPError {e.code}: {detail}\n")
            return False
        except Exception as e:
            sys.stderr.write(f"flush push error: {e}\n")
            return False
    return push


def main() -> int:
    from shared.escalation import flush_pending_escalations
    tokens, default_id = _load_tokens()
    if not tokens:
        print("flush_escalations: 無 LINE token（data/line-channels.json 或 CHANNEL_ACCESS_TOKEN）、略過")
        return 0
    stats = flush_pending_escalations(_make_push(tokens, default_id))
    print(f"flush_escalations: {stats}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
