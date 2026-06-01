"""Shared escalation helper — REPORT 硬接線（決策 #162「REPORT 必硬」/ #173 重設計版）。

模型「部門硬牆 / 角色軟(上報為主)」的「上報」那一半：員工 / 有權幹部做了「主管該知道的事」，
service 層在「真正執行那支 tool 的同一個 transaction 內」無條件寫一筆 pending_escalations
（agent 看不到、跳不過），再由「笨投遞器」flusher（OS cron 獨立腳本 / line-channel owner
inbound 搭便車、非 setInterval daemon）讀 status='pending' 推給主管。

放 shared/（非 server.py、非某 module）理由同 auth.py：所有觸發 service（accounting / orders /
hr + auth 本身）都要 call enqueue_escalation，放 module 會在拆 module 時形成 import cycle。
本檔只依賴 shared.*（db / auth / floor_policy / floor_map），不 import 任何 module——收件人 /
設定 / BU / channel 全走直接 SQL（仿 auth._check_permission；部門層 floor gate 移除了
list_employees 等工具，但 service/shared 直接 SQL 不受工具移除影響）。

語意（別跟 approvals「閘」混用）：escalation = 只通知、不擋業務、不需參數比對、不綁 record，
狀態機只有 pending → sent / failed。

對抗審查（wks27te3k）收斂的硬約束：
- actor 與 target_line_user_id 一律在「enqueue 當下」（service in-tx、active-request 還在）
  解析寫死；flusher 是純「讀 row → push → UPDATE」的 dumb 投遞器、不重算身份 / 收件人。
- enqueue 是 caller-managed-tx（接 db、不 commit、不可 nested），與業務寫入同一原子 commit
  ＝硬接線不可略過。enqueue 內部正常路徑不該拋例外（否則會 rollback 整個業務寫入）。
- 觸發開關 onboarding 可設定（settings『escalation_triggers』）、預設只開低頻高風險、
  cross_bu_access 預設關（高頻、無 dedup、會洗版主管）。
"""
import json

# MVP 上報「目標層」＝老闆 / 全權限層（is_full_access：SME_FLOOR='' 或 'confidential'）。
# 存「目標層」而非「觸發層」：部門層 session 不該從 get_context_summary 撈到自己被上報的事。
BOSS_TARGET_FLOOR = "confidential"

# 預設啟用的觸發事件（決策 #173：低頻高風險預設開）。
DEFAULT_ENABLED_EVENTS = frozenset({
    "approval_pending",                       # #178：審核請求一建立就通知簽核人（HITL 核心）
    "transaction_recorded_over_threshold",
    "order_cancelled_shipped",
    "transaction_deleted",
    "employee_permissions_changed",
    "qc_failed",
})
# 已知但「預設關」的高頻事件（onboarding 想開要自行加進 settings、並接受洗版風險 / 未來補 dedup）。
DEFAULT_DISABLED_EVENTS = frozenset({"cross_bu_access"})
KNOWN_EVENTS = DEFAULT_ENABLED_EVENTS | DEFAULT_DISABLED_EVENTS


def _enabled_events(db) -> set:
    """讀 settings『escalation_triggers』決定啟用哪些 event_type；缺設定 → 安全預設。
    支援兩種格式：JSON list（["a","b"]）或 JSON dict（{"a": true, "cross_bu_access": false}）。"""
    row = db.execute(
        "SELECT content FROM business_rules WHERE category='settings' "
        "AND title='escalation_triggers' AND superseded_by IS NULL"
    ).fetchone()
    content = row["content"] if row else None
    if not content:
        return set(DEFAULT_ENABLED_EVENTS)
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return set(DEFAULT_ENABLED_EVENTS)
    if isinstance(data, list):
        return {str(x) for x in data}
    if isinstance(data, dict):
        return {str(k) for k, v in data.items() if v}
    return set(DEFAULT_ENABLED_EVENTS)


def is_escalation_enabled(db, event_type: str) -> bool:
    """該 event_type 是否要上報（讀 settings、預設安全集合）。"""
    return event_type in _enabled_events(db)


def _looks_like_line_user_id(value: str) -> bool:
    """LINE user_id 慣例：'U' + 32 hex。用來分辨 floor_map.escalation_target 是直接收件人
    還是 'boss' / floor 名 sentinel。"""
    if not value or len(value) != 33 or value[0] != "U":
        return False
    try:
        int(value[1:], 16)
        return True
    except ValueError:
        return False


def resolve_escalation_target(db, business_unit: str = "", triggering_floor=None):
    """解析（收件人 line_user_id, 用哪個 OA channel_id, 儲存的目標層）。直接 SQL、不走工具。

    收件人 coalesce 鏈（fail-toward-有人收、決策 #173 / #162「fallback 老闆」）：
      0. 觸發層的 floor_map.escalation_target 若是直接 line_user_id（U+32hex）→ 用它（#6 keystone）
      1. role='boss' 且 active 的員工 line_user_id
      2. permissions='admin' 且 active 的員工 line_user_id
      3. company.boss_line_id
      4. 全空 → 收件人 None（caller 仍寫 pending、不靜默丟；全權限層開機 readout 會提醒設老闆 id）

    channel_id：觸發 BU 對應的 business_entities.channel_id（來源 OA），否則 None（flusher fallback default）。
    """
    if triggering_floor is None:
        try:
            from shared.floor_policy import get_floor
            triggering_floor = get_floor()
        except Exception:
            triggering_floor = ""

    # channel：BU → OA
    channel_id = None
    if business_unit:
        erow = db.execute(
            "SELECT channel_id FROM business_entities WHERE id = ?", (business_unit,)
        ).fetchone()
        if erow and erow["channel_id"]:
            channel_id = erow["channel_id"]

    # 0) floor_map.escalation_target 直接指定 line_user_id
    try:
        from shared.floor_map import get_floor_config
        etgt = (get_floor_config(triggering_floor).escalation_target or "").strip()
    except Exception:
        etgt = ""
    if _looks_like_line_user_id(etgt):
        return (etgt, channel_id, BOSS_TARGET_FLOOR)

    # 1) role='boss' → 2) permissions='admin' → 3) company.boss_line_id
    for sql in (
        "SELECT line_user_id FROM employees WHERE active=1 AND line_user_id IS NOT NULL AND role='boss' ORDER BY id LIMIT 1",
        "SELECT line_user_id FROM employees WHERE active=1 AND line_user_id IS NOT NULL AND permissions='admin' ORDER BY id LIMIT 1",
    ):
        row = db.execute(sql).fetchone()
        if row and row["line_user_id"]:
            return (row["line_user_id"], channel_id, BOSS_TARGET_FLOOR)
    crow = db.execute("SELECT boss_line_id FROM company WHERE id=1").fetchone()
    if crow and crow["boss_line_id"]:
        return (crow["boss_line_id"], channel_id, BOSS_TARGET_FLOOR)
    return (None, channel_id, BOSS_TARGET_FLOOR)


def enqueue_escalation(
    db,
    *,
    event_type: str,
    summary: str,
    detail=None,
    actor_user_id: str = "",
    business_unit: str = "",
    channel_id=None,
):
    """Caller-managed-tx：在觸發 service 自己的 with transaction() 內呼叫（接 db、不 commit、
    不可 nested）。寫一筆 pending_escalations + 並排一筆 interaction_log（稽核鏡像、同 tx）。

    actor 與 target_line_user_id 在此（enqueue 當下、active-request 還在）解析寫死，flusher 不重算。
    回傳 escalation id；該 event_type 未啟用 → 回 None（no-op、不寫任何 row）。

    Args:
        event_type: 觸發事件類型（見 KNOWN_EVENTS）
        summary: 一行人話摘要（推給主管的內文主體；不可空）
        detail: 完整明細，dict/list 自動 json.dumps、字串原樣、None 不存
        actor_user_id: 觸發者（會經 _resolve_trusted_actor：floored 取 verified user_id 忽略此值）
        business_unit: 觸發事件所屬事業體
        channel_id: 指定推送 OA（不給則由 BU 解析）
    """
    if not is_escalation_enabled(db, event_type):
        return None
    if not summary:
        summary = f"（{event_type}）"  # CHECK summary<>'' 保險；正常 caller 都會帶

    from shared.auth import _resolve_trusted_actor
    actor_uid = _resolve_trusted_actor(actor_user_id or "")
    # 人話 actor：由「可信 verified user_id」反查員工名（衍生自可信身份、非 agent 自填，
    # 仍守不可偽造）。查不到員工 → 用 user_id；'__unverified__' 原樣保留。給主管的訊息更可讀。
    actor = actor_uid
    if actor_uid and actor_uid != "__unverified__":
        erow = db.execute(
            "SELECT name FROM employees WHERE line_user_id=? AND active=1", (actor_uid,)
        ).fetchone()
        if erow and erow["name"]:
            actor = erow["name"]

    tgt_uid, resolved_channel, tfloor = resolve_escalation_target(db, business_unit)
    channel_id = channel_id or resolved_channel

    # 在 detail json.dumps 成字串「之前」留一份 dict 版（給 in-session 注入內容解析 approval_id / type）。
    detail_dict = detail if isinstance(detail, dict) else None
    if detail_dict is None and isinstance(detail, str):
        try:
            parsed = json.loads(detail)
            if isinstance(parsed, dict):
                detail_dict = parsed
        except (json.JSONDecodeError, TypeError, ValueError):
            detail_dict = None

    if isinstance(detail, (dict, list)):
        detail = json.dumps(detail, ensure_ascii=False)

    cur = db.execute(
        "INSERT INTO pending_escalations "
        "(event_type, summary, detail, actor, business_unit, target_floor, "
        " target_line_user_id, channel_id, status) "
        "VALUES (?,?,?,?,?,?,?,?,'pending')",
        (event_type, summary, detail, actor or None, business_unit or None,
         tfloor, tgt_uid, channel_id),
    )
    esc_id = cur.lastrowid

    # 稽核鏡像（interaction_log 是 cross-cutting audit sink，與業務寫入同 tx）
    db.execute(
        "INSERT INTO interaction_log (actor, action, target_type, target_id, detail, business_unit) "
        "VALUES (?,?,?,?,?,?)",
        (actor or None, f"escalation_{event_type}", "pending_escalation", esc_id,
         summary, business_unit or None),
    )
    # 直接觸發（#9g）：標記本 tx 寫了上報；commit 成功後 transaction() 會 fire-and-forget
    # 起 claude -p 通報投遞器（即時、非 cron 輪詢）。
    from shared.db import request_escalation_flush
    request_escalation_flush()

    # B in-session push（#25）：排一筆 channel notification，commit 成功後經 line-channel owner
    # IPC socket 注入正在跑的全權限層 session（即時推進 boss session、與 claude -p / cron 並行、
    # 後兩者仍是送達保證）。actor_text 把 __unverified__ 顯示成人話、與 LINE 通報措辭一致。
    actor_text = "未驗證身份" if actor in (None, "", "__unverified__") else actor
    if event_type == "approval_pending":
        aid = (detail_dict or {}).get("approval_id")
        # summary 已含 #id（type）：…（approvals.create_in_tx 傳入時前綴），此處不重複前綴
        content = (
            f"[待核准·主管上報] {summary}\n"
            f"操作者：{actor_text}\n"
            f"→ 確認後可在本層直接核准：resolve_approval(#{aid}) 後依該 approval 的 "
            f"resume_params 執行（如 record_transaction），或等老闆 LINE 回覆核准。\n"
            f"（上報 #{esc_id}）"
        )
        meta = {
            "target_floor": tfloor,
            "event_type": "escalation",
            "escalation_event": event_type,
            "source_type": "system",
            "escalation_id": str(esc_id),
            "approval_id": str(aid),
        }
    else:
        label = ESCALATION_LABELS.get(event_type, event_type)
        content = (
            f"[主管上報] {label}\n"
            f"{summary}\n"
            f"操作者：{actor_text}\n"
            f"（上報 #{esc_id}）"
        )
        meta = {
            "target_floor": tfloor,
            "event_type": "escalation",
            "escalation_event": event_type,
            "source_type": "system",
            "escalation_id": str(esc_id),
        }
    payload = {
        "method": "notifications/claude/channel",
        "params": {"content": content, "meta": meta},
    }
    from shared.db import queue_session_injection
    queue_session_injection(payload)

    return esc_id


# ============================================================
# B in-session push（#25）— 經 line-channel owner IPC socket 注入正在跑的全權限層 session。
# 注入協定（LOCKED、與 server.ts 接收端一字不差）：
#   傳輸：UNIX SOCK_STREAM，路徑 <STATE_DIR>/broadcast.sock；
#         STATE_DIR = env LINE_STATE_DIR、否則 ~/.claude/channels/line。
#         絕不走 HTTP port（沙箱不隔離網路、部門 agent 可 curl localhost）；socket 在 ~/.claude
#         下、被沙箱檔案系統 + denyRead 擋住。
#   認證：每次送前重讀 <STATE_DIR>/inject.token（owner 啟動時產生的隨機 hex）；讀不到/空 → 跳過。
#   線格式：一行 UTF-8 JSON + \n：
#     {"type":"inject","token":"<hex>","notification":<payload>}
#     payload = {"method":"notifications/claude/channel","params":{"content":...,"meta":{...}}}
#   全 best-effort：connect/send 任何 OSError 都吞掉、回 False、絕不把例外丟進業務 transaction。
#   送達面：owner 收到後對 token 相符的注入呼叫 notifyAll → 送達正在跑 confidential（或 ''）的 session；
#   沒 owner / 沒 confidential session 連著就沒人 emit（LINE claude -p + cron 仍是送達保證）。
# ============================================================

def inject_to_sessions(payload: dict) -> bool:
    """經 line-channel owner IPC socket 注入一筆 channel notification 到正在跑的全權限層 session。

    讀不到 token / socket 連不上 / 任何 OSError → 回 False（靜默 best-effort、不報錯）。成功送出 → True。
    只用 stdlib（函式內 import os/socket/json）；settimeout(2.0)、connect→sendall→close。
    """
    import os
    import socket
    import json as _json

    state_dir = os.environ.get("LINE_STATE_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude", "channels", "line"
    )
    # 每次送前重讀 token（owner 單一來源）；讀不到 / 空 → 跳過、不送。
    try:
        with open(os.path.join(state_dir, "inject.token"), encoding="utf-8") as f:
            token = f.read().strip()
    except OSError:
        return False
    if not token:
        return False

    sock_path = os.path.join(state_dir, "broadcast.sock")
    # CC channel notification 規定 meta 為 Record<string,string>：非字串值（int / None…）會讓 CC
    # 靜默丟棄整筆通知（in-session push 不顯示的 live 根因）→ 送出前強制把 meta 值轉字串（None→""）。
    try:
        _params = payload.get("params")
        _meta = _params.get("meta") if isinstance(_params, dict) else None
        if isinstance(_meta, dict):
            _params["meta"] = {str(k): ("" if v is None else str(v)) for k, v in _meta.items()}
    except Exception:
        pass
    line = _json.dumps(
        {"type": "inject", "token": token, "notification": payload},
        ensure_ascii=False,
    ) + "\n"
    s = None
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(2.0)
        s.connect(sock_path)
        s.sendall(line.encode("utf-8"))
        return True
    except OSError:
        return False
    finally:
        if s is not None:
            try:
                s.close()
            except OSError:
                pass


# ============================================================
# 笨投遞器 flusher（#9d/#173）— 讀 pending → push → mark sent/retry/failed。
# 不重算身份/收件人（enqueue 當下已寫死）；非 caller-managed，自管連線（top-level op）。
# 主路＝OS cron 跑 flush_escalations.py（真硬接線、不靠 agent/session）；
# 低延遲增強＝line-channel owner inbound 搭便車（未做、policy 同此處、避免 TS 重刻）。
# ============================================================

FLUSH_MAX_RETRY = 5          # LINE push 假成功（未加好友回 200 但不達）→ 重試上限後標 failed 終態
FLUSH_BACKOFF_BASE_MIN = 3   # 線性 backoff：第 n 次重試需距上次 >= n*base 分鐘

ESCALATION_LABELS = {
    "approval_pending": "待核准審核",
    "transaction_recorded_over_threshold": "超門檻帳目已記",
    "transaction_deleted": "帳目被刪除",
    "order_cancelled_shipped": "已出貨訂單被取消/退貨",
    "qc_failed": "品檢不合格",
    "employee_permissions_changed": "員工權限/事業體/在職變更",
    "cross_bu_access": "跨事業體越權存取",
}


def format_escalation_message(row) -> str:
    """推給主管的精簡訊息：摘要 + 事件類型 + 操作者（不送全 detail，降部門機密破牆面 + 省 LINE 額度；
    完整 detail 留 DB 供事後查）。"""
    label = ESCALATION_LABELS.get(row["event_type"], row["event_type"])
    lines = [f"[主管上報] {label}", row["summary"]]
    actor = row["actor"]
    if actor and actor != "__unverified__":
        lines.append(f"操作者：{actor}")
    elif actor == "__unverified__":
        lines.append("操作者：（未驗證身份）")
    if row["business_unit"]:
        lines.append(f"事業體：{row['business_unit']}")
    lines.append(f"（上報 #{row['id']} · {row['created_at']}）")
    return "\n".join(lines)


def flush_pending_escalations(push_fn, *, max_retry=FLUSH_MAX_RETRY,
                              backoff_base_min=FLUSH_BACKOFF_BASE_MIN, limit=50) -> dict:
    """笨投遞器主迴圈。push_fn(channel_id, to_line_user_id, text) -> bool（True=LINE API 真 ok）。

    - 只撈 status='pending' 且 target_line_user_id 非 NULL（無收件人的留 pending、由 #9e readout 提醒）。
    - 線性 backoff 寫進 SELECT：retry_count 次的 row 需距上次 last_attempt_at >= retry_count*base 分鐘。
    - push 成功 → UPDATE status='sent'（WHERE ... status='pending' rowcount guard 防雙投）。
    - push 失敗 → retry_count+1；達 max_retry → status='failed' 終態（全權限層開機 readout 會提醒）。
    - 不在 push（網路 I/O）期間持有 write lock：先讀清單、逐筆 push 後各開短 tx 更新。

    回 {'sent','failed','retried','candidates'}。
    """
    from shared.db import _now, get_db, transaction

    db = get_db()
    try:
        rows = db.execute(
            "SELECT * FROM pending_escalations "
            "WHERE status='pending' AND target_line_user_id IS NOT NULL "
            "AND (last_attempt_at IS NULL OR "
            "     last_attempt_at <= datetime('now','localtime','-'||(retry_count*?)||' minutes')) "
            "ORDER BY id LIMIT ?",
            (backoff_base_min, limit),
        ).fetchall()
    finally:
        db.close()

    stats = {"sent": 0, "failed": 0, "retried": 0, "candidates": len(rows)}
    for row in rows:
        text = format_escalation_message(row)
        try:
            ok = bool(push_fn(row["channel_id"], row["target_line_user_id"], text))
        except Exception:
            ok = False
        with transaction() as wdb:
            if ok:
                rc = wdb.execute(
                    "UPDATE pending_escalations SET status='sent', sent_at=? "
                    "WHERE id=? AND status='pending'",
                    (_now(), row["id"]),
                ).rowcount
                if rc == 1:
                    stats["sent"] += 1
            else:
                new_count = row["retry_count"] + 1
                if new_count >= max_retry:
                    wdb.execute(
                        "UPDATE pending_escalations SET status='failed', retry_count=?, "
                        "last_attempt_at=? WHERE id=? AND status='pending'",
                        (new_count, _now(), row["id"]),
                    )
                    stats["failed"] += 1
                else:
                    wdb.execute(
                        "UPDATE pending_escalations SET retry_count=?, last_attempt_at=? "
                        "WHERE id=? AND status='pending'",
                        (new_count, _now(), row["id"]),
                    )
                    stats["retried"] += 1
    return stats


def count_stuck_escalations(db) -> dict:
    """供全權限層開機 readout（#9e）：回 {'failed': n, 'no_recipient': n}。caller-managed（讀）。"""
    failed = db.execute(
        "SELECT COUNT(*) c FROM pending_escalations WHERE status='failed'"
    ).fetchone()["c"]
    no_rcpt = db.execute(
        "SELECT COUNT(*) c FROM pending_escalations WHERE status='pending' AND target_line_user_id IS NULL"
    ).fetchone()["c"]
    return {"failed": failed, "no_recipient": no_rcpt}


# ── notifier（claude -p single-shot）介面：兩個窄 MCP 工具（list / mark）。
#    全權限層限定（floor gate 對非全權限層移除、見 floor_policy.ESCALATION_ADMIN_TOOLS）。
#    收件人在 enqueue 當下已寫死 target_line_user_id；notifier 一律照 row 推、不自決收件人。──

def list_pending_for_notifier(limit: int = 50) -> str:
    """回 JSON 字串：待投遞上報（status=pending、已解析收件人）。給 claude -p 通報投遞器讀。"""
    from shared.db import get_db
    db = get_db()
    try:
        rows = db.execute(
            "SELECT id, event_type, summary, actor, business_unit, target_line_user_id, channel_id "
            "FROM pending_escalations WHERE status='pending' AND target_line_user_id IS NOT NULL "
            "ORDER BY id LIMIT ?", (limit,),
        ).fetchall()
    finally:
        db.close()
    items = [dict(r) for r in rows]
    return json.dumps({"pending": items, "count": len(items)}, ensure_ascii=False)


def mark_sent_tool(escalation_id: int) -> str:
    """標記上報已送達（pending→sent、rowcount guard 防重複）。投遞器推送成功後呼叫。"""
    from shared.db import _now, transaction
    with transaction() as db:
        rc = db.execute(
            "UPDATE pending_escalations SET status='sent', sent_at=? "
            "WHERE id=? AND status='pending'", (_now(), escalation_id),
        ).rowcount
    return (f"上報 #{escalation_id} 已標記 sent" if rc == 1
            else f"上報 #{escalation_id} 無法標記（已送/不存在/非 pending）")


# ── claude -p single-shot 通報投遞器（#9g、老闆「直接觸發、聰明通報」）──
# business-db commit 成功後 fire-and-forget 起。聰明：可合併多筆、寫人話、判斷措辭。
# 護欄：收件人嚴格照 row 的 target_line_user_id（LLM 不可自決收件人）；佇列+cron 兜底＝保證。

_NOTIFIER_PROMPT = (
    "你是 SME-AI-Kit 的「主管上報投遞器」。只做這件事、做完即結束：\n"
    "1. 呼叫 list_pending_escalations 取得待投遞上報（回 JSON：pending[] 各含 "
    "id / event_type / summary / actor / business_unit / target_line_user_id / channel_id）。\n"
    "2. 若 count=0，直接結束、什麼都不做。\n"
    "3. 對每一筆，用 mcp__line__reply 推送：chat_id 一律用「該筆的 target_line_user_id」"
    "（絕不自行更改或猜測收件人）、channel_id 用該筆的 channel_id（空字串就省略走 default）、"
    "text 用該筆 summary 寫成一句給老闆的人話通報（標明事件、金額/單號、操作者 actor；"
    "actor 是 __unverified__ 時寫「未驗證身份」）。若多筆的 target_line_user_id 相同、可合併成一則"
    "精簡摘要推給該收件人；target_line_user_id 不同的【絕對不可合併】、各自一則、每則只含自己那筆內容"
    "（嚴防把 A 的金額/單號寫進給 B 的通報＝跨收件人洩密）。\n"
    "4. 每成功推一筆就呼叫 mark_escalation_sent(該筆 id)。\n"
    "限制：只用 list_pending_escalations / mcp__line__reply / mark_escalation_sent；"
    "不讀檔、不執行指令、不做別的事。"
)


_NOTIFIER_DEBOUNCE_SEC = 30   # 同窗內最多起一支 notifier（一支就 drain 全部 pending）→ 防放大


def _notifier_state_dir() -> str:
    """notifier 控制檔（debounce lock / 暫存 mcp-config）放的受保護 state dir（LINE_STATE_DIR 或
    ~/.claude/channels/line、被 floor sandbox denyWrite ~/ 擋住）。不放 /tmp——/tmp 在各 floor 的
    allowWrite 內、部門 agent 可讀改這些 host-side 控制檔（壓住 notifier、甚至劫持其 MCP 連線設定）。"""
    import os
    return os.environ.get("LINE_STATE_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude", "channels", "line"
    )


def _notifier_lock_path() -> str:
    import os
    return os.path.join(_notifier_state_dir(), "sme-notifier.lock")


def spawn_notifier() -> None:
    """post-commit fire-and-forget：起一個 claude -p single-shot 通報投遞器（品質層）。

    走 Max 訂閱（env 去 ANTHROPIC_API_KEY）、全權限（去 SME_FLOOR 才看得到 escalation）、窄工具
    （dontAsk + allowedTools）、極簡 mcp-config（只 business-db+line、PID 命名防 race）、防遞迴（SME_NOTIFIER=1）。
    這是「品質層、best-effort」——確定性保證在 cron flush_escalations.py（保證層、status 協調）。

    防放大（決策 #177）：①debounce lockfile 限速 ②無「有收件人的 pending」就不起（擋老闆不可達時每 commit 重起）。
    可觀測：stderr → data/notifier.log（不再全吞）。
    """
    import os
    import shutil
    import subprocess
    import time
    import json as _json
    from shared.db import _now, get_db

    if os.environ.get("SME_NOTIFIER"):  # 防遞迴：notifier 進程內不再起 notifier
        return

    lock_path = _notifier_lock_path()
    # 防放大①debounce：最近 _NOTIFIER_DEBOUNCE_SEC 內已起過就跳過（一支就能 drain 全部 pending）。
    # 跨進程（多 floored session 各自 business-db）用共用 lockfile 限速。
    try:
        if os.path.exists(lock_path) and (time.time() - os.path.getmtime(lock_path)) < _NOTIFIER_DEBOUNCE_SEC:
            return
    except Exception:
        pass

    # 防放大②pre-spawn guard：沒有「有收件人的 pending」就不起——擋「老闆不可達 → row 清不掉 →
    # 每筆業務 commit 都重起一支去重推」的放大（無收件人的留 pending、由全權限層開機 readout 提醒設老闆 id）。
    try:
        gdb = get_db()
        try:
            n = gdb.execute(
                "SELECT COUNT(*) FROM pending_escalations "
                "WHERE status='pending' AND target_line_user_id IS NOT NULL"
            ).fetchone()[0]
        finally:
            gdb.close()
        if not n:
            return
    except Exception:
        pass

    db_path = os.environ.get("SME_DB_PATH", "")
    project_root = os.path.dirname(os.path.dirname(db_path)) if db_path else os.getcwd()
    claude_bin = shutil.which("claude") or "claude"

    # 極簡 mcp-config：只 business-db + line。寫到受保護 state dir（非 floor-writable /tmp）、0600：
    # 此檔餵給全權限的 claude -p notifier，放 /tmp 則低權限員工可搶改、注入惡意 MCP server 劫持 notifier。
    # PID 命名 → 兩個 spawn 不互相覆寫（race）。
    mcp_cfg = None
    try:
        with open(os.path.join(project_root, ".mcp.json"), encoding="utf-8") as f:
            servers = (_json.load(f) or {}).get("mcpServers", {})
        minimal = {"mcpServers": {k: servers[k] for k in ("business-db", "line") if k in servers}}
        if minimal["mcpServers"]:
            cfg_dir = _notifier_state_dir()
            os.makedirs(cfg_dir, exist_ok=True)
            mcp_cfg = os.path.join(cfg_dir, f"sme-notifier-mcp-{os.getpid()}.json")
            fd = os.open(mcp_cfg, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                _json.dump(minimal, f)
    except Exception:
        mcp_cfg = None

    # 沒有可用 mcp-config（如單元測試：temp DB、project_root 無 .mcp.json）→ 不起、留給 cron 兜底。
    if not mcp_cfg:
        return

    # touch debounce lock（確定要 spawn 了才壓窗）
    try:
        os.makedirs(os.path.dirname(lock_path), exist_ok=True)
        with open(lock_path, "w", encoding="utf-8") as f:
            f.write(str(time.time()))
    except Exception:
        pass

    env = dict(os.environ)
    env.pop("SME_FLOOR", None)          # notifier 全權限（才看得到 escalation）
    env.pop("SME_FLOOR_MAP", None)
    env.pop("ANTHROPIC_API_KEY", None)  # 走訂閱、不走 metered API
    env["SME_NOTIFIER"] = "1"           # 防遞迴

    args = [
        claude_bin, "-p", _NOTIFIER_PROMPT, "--permission-mode", "dontAsk",
        "--mcp-config", mcp_cfg, "--strict-mcp-config",
        "--allowedTools", "ToolSearch", "mcp__line__reply", "mcp__line__reply_flex",
        "mcp__business-db__list_pending_escalations", "mcp__business-db__mark_escalation_sent",
        "--disallowedTools", "Bash", "Edit", "Write", "Read", "WebSearch", "WebFetch", "Agent",
    ]

    # 可觀測：stderr → data/notifier.log（把燈打開、不再全吞）；stdout/stdin 仍 DEVNULL。
    stderr_target = subprocess.DEVNULL
    try:
        logf = open(os.path.join(project_root, "data", "notifier.log"), "a", encoding="utf-8")
        logf.write(f"[{_now()}] spawn notifier (pid={os.getpid()}, mcp_cfg={mcp_cfg})\n")
        logf.flush()
        stderr_target = logf
    except Exception:
        stderr_target = subprocess.DEVNULL

    try:
        subprocess.Popen(
            args, cwd=project_root, env=env,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=stderr_target,
            start_new_session=True,
        )
    except Exception:
        pass
