"""sme→pleading 回寫編排（Task C / M2）。**inert-by-default**：整合未配置就整段略過、不報錯不提醒。

職責（薄）：
1. 判斷「整合已配置」= base url 有 + 該案 `matters.pleading_case_id` 有 + 選得到該律師 token。
2. 從 sme deadline / intake row 組**去識別化 payload**（當事人名 / issuer / subject 一律不帶）。
3. 呼 PleadingClient upsert → **處理結果**（ok 存回 pleading row id、401 標重發、404 建議解綁、連線失敗略過）。
4. **絕不 raise 給 caller**——回寫失敗不炸引擎、pleading 鏡像暫落後、legal-admin 引擎/提醒不受影響。

身分（§127 / 契約 v4，見 KB `pleading_rest_contract`）：回寫一律以該案當責律師個人 token 呼叫。
token 選取邏輯 = `select_pleading_token`（本檔單一真相；service.py re-export 為 `_select_pleading_token`）。

自成一個 db 連線（best-effort 鏡像、與 caller 的 tx 生命週期解耦）；caller 只在**已 commit 之後**呼叫，
故本層 fresh 連線讀得到權威資料、再做自己的小 commit 存回對位。
"""
from __future__ import annotations

from shared.db import _now, get_db
from shared.deadlines import type_label
from shared.privacy import deidentify_for_export, extract_opposing_names, extract_party_names

from . import repository
from .pleading_client import (
    PleadingAuthError,
    PleadingClient,
    PleadingError,
    PleadingNotFound,
    PleadingUnreachable,
    integration_configured,
)


# ───────────────────────── token 選取（§127；單一真相）─────────────────────────

def select_pleading_token(db, *, actor_name="", assignee_name="", lead_attorney_name="", verify=None):
    """回寫路徑選「該用哪張 pleading token」（Task D；內部、**絕不**經 MCP 回傳 token）。

    身分（契約 v4 / §127）由 caller 傳入的參數組合決定模式：
      - 互動觸發：只傳 actor_name（觸發者自己）→ 稽核記他、gate 套他角色；他沒綁→回 ''（不 fallback、
        免把他做的寫入誤掛別人）。
      - 自主/背景：傳 assignee_name（該 deadline 當責律師）+ lead_attorney_name → assignee 優先、
        fallback 案 lead_attorney。
    僅取 active 員工 token（停用即不可用）。verify（可選 callable token->bool；接 pleading whoami 探活）
    給了且回 False → 視為失效、回 ''（避免拿失效 token 整批 401）。未給＝不探活。
    回 token 或 ''（'' → 上層 graceful skip、pleading 鏡像暫 stale、引擎/提醒不受影響）。
    """
    # 模式由 actor_name 決定（codex HIGH：防 §127 誤掛）：
    #   互動＝actor_name 非空 → **只**查 actor、查不到立刻回 ''（絕不 fallback 到別人，免把他做的寫入誤掛他人）；
    #   自主＝actor_name 空 → assignee（當責律師）→ fallback lead_attorney。
    if actor_name and actor_name.strip():
        candidates = (actor_name,)
    else:
        candidates = (assignee_name, lead_attorney_name)
    token = None
    for nm in candidates:
        if nm and nm.strip():
            token = repository.get_pleading_token_by_name(db, nm.strip())
            if token:
                break
    if not token:
        return ""
    if verify is not None and not verify(token):
        return ""
    return token


# ───────────────────────── 結果 / 提醒詞 ─────────────────────────

def _result(status: str, detail: str = "", pleading_id=None) -> dict:
    return {"status": status, "detail": detail, "pleading_id": pleading_id}


def note_for(result: dict) -> str:
    """回寫結果 → 附在 tool 回覆末尾的一行提醒。**inert 情形靜默**（未配置 / 略過 = 空字串），
    只在整合已配置且有值得講的結果時出聲（成功 / token 失效 / 案件不存在 / 連不上 / 其他）。"""
    if not result:
        return ""
    st = result.get("status")
    if st in (None, "not_configured", "skipped"):
        return ""  # inert：不回寫、不報錯、不提醒
    if st == "ok":
        pid = result.get("pleading_id")
        return f"\n（已同步 pleading：#{pid}）" if pid is not None else "\n（已同步 pleading）"
    if st == "auth_failed":
        return "\n（pleading 回寫略過：該律師 token 失效、請重新 provision；不影響本筆）"
    if st == "not_found":
        return "\n（pleading 回寫略過：對應案件不存在、可 link_matter_pleading 解綁；不影響本筆）"
    if st == "unreachable":
        return "\n（pleading 回寫略過：暫時連不上、pleading 鏡像稍後補；不影響本筆）"
    # 其他錯誤（HTTP 4xx/5xx / 非預期）：**固定文案、絕不回顯 result['detail']**——detail 可能含遠端
    # response body / request 回顯 / PII（codex Task C R1 MED）。詳情只留在內部 result、不進 operator 字串。
    return "\n（pleading 回寫略過：回寫發生錯誤；不影響本筆）"


# ───────────────────────── payload 組裝（去識別化）─────────────────────────

# 直接對映 deadlines 欄 → DeadlineIn（None 由 client._prune_none 略過）。
_DEADLINE_FIELDS = (
    "assignee", "statutory_deadline", "internal_deadline", "status", "type",
    "period_type", "severity", "period_unit", "period_value", "statutory_basis",
    "statutory_basis_version", "trigger_event", "service_base_date", "statutory_days",
    "needs_manual_review", "calc_trace", "reviewed_by", "reviewed_at",
)


def _safe_title(d: dict) -> str:
    """去識別化 title（codex Task C R1 HIGH）+ **保證非空**（pleading_coder pin / marketing lock：title 是
    pleading 時間軸列標題來源、送空該列會無標題）。標籤一律由 `type` 代碼查 `type_label`（跨四張種子表 +
    已知非種子程序類 answer/brief）得可讀法定/程序標籤（結構上不含姓名，如「民事上訴（對第一審判決）」
    「答辯狀提出期間」）；查無（真未知 custom type）→ 由 `type` 代碼組固定安全字串（type 是代碼、零姓名）。
    **絕不**回寫自由文字 `description`（律師可能在其中寫當事人姓名）。F-P2-2：原僅查 STATUTORY_PERIODS
    一張表、致 court_set(answer)/消滅時效/程序類回寫成生代碼「法定期限（answer）」，改查全表 + 泛型映射。"""
    t = (d.get("type") or "").strip()
    label = type_label(t)
    if label:
        return label
    # 未知 type＝operator 自由字串、可能含 PII（codex R1 HIGH）：fallback **不再帶原代碼**、
    # 一律固定安全字串（與 _safe_type 的 "custom" 正規化一致）。原代碼留在 sme 側自有紀錄。
    return "自訂期限"


# ── 回寫邊界去識別化 gate（F-P2-WIN-2）──────────────────────────────────────
# 原則：payload 內**所有字串欄 default in-scope**、以「豁免清單」明列例外——新增欄位天生受檢、
# 不做逐欄打地鼠。豁免＝結構化代碼/日期/整合鍵（無自由文字空間）＋律師名欄（assignee/reviewed_by
# ＝§127 具名當責、刻意保留、律師非去識別化對象）。實證：trigger_event（沅泰物流）、statutory_basis
# （臺灣臺中地方法院）、calc_trace（逐字內嵌 statutory_basis）三個 verbatim 載體都在 Windows e2e 漏過。
# 豁免欄的前提＝「值已被鎖成安全」（codex R1 HIGH）：
# - type：outbound 前經 _safe_type 正規化（未知代碼→"custom"、絕不 verbatim 外送 operator 自由字串）
# - assignee / reviewed_by：outbound 前經 _employee_or_none 驗證（非在職員工名→不外送）
# - 其餘＝日期/枚舉/整合鍵（無自由文字空間）。doc_type 是 operator 可控字串→**不豁免**、照 gate 掃。
_GATE_EXEMPT = frozenset({
    "external_system", "external_ref", "source", "computed_by",
    "assignee", "reviewed_by",
    "type", "period_type", "status", "severity", "period_unit", "direction",
    "statutory_deadline", "internal_deadline", "service_base_date", "document_date",
    "reviewed_at", "linked_deadline_ref",
})


def _safe_type(t) -> str:
    """outbound type 正規化：已知代碼（四張種子表＋泛型 map）原樣送；未知＝operator 自由字串、
    可能含 PII → 一律改送 "custom"（sme 側自有 type 原值不動、只鎖邊界）。"""
    t = (t or "").strip()
    return t if (t and type_label(t) is not None) else "custom"


def _employee_or_none(db, name):
    """assignee / reviewed_by 豁免的前提驗證：值必須是在職員工名（§127 具名當責＝真實律師），
    否則（operator 誤填/塞了當事人名）不外送（None、client 端 _prune_none 略過）。"""
    nm = (name or "").strip()
    if not nm:
        return None
    row = db.execute(
        "SELECT 1 FROM employees WHERE name=? AND active=1 LIMIT 1", (nm,)
    ).fetchone()
    return nm if row else None


def _matter_pii_tokens(m: dict) -> tuple:
    """從 matter 收集「已知該去識別化的 token」：(當事人/對造名, 法院名)。誠實邊界＝只擋已知寫法。"""
    party = extract_party_names(m.get("client_name")) + extract_opposing_names(m.get("title"))
    court = [c for c in [(m.get("court") or "").strip()] if len(c) >= 2]
    return party, court


def _gate_payload(payload: dict, m: dict) -> tuple:
    """對 payload 所有非豁免字串欄過去識別化 gate（組完之後、送出之前——calc_trace 這類「內嵌其他欄
    原文」的欄位必須在組裝完成後整段掃、掃單一來源欄擋不住）。回 (payload, 命中token總數)。"""
    party, court = _matter_pii_tokens(m)
    total = 0
    for k, v in list(payload.items()):
        if k in _GATE_EXEMPT or not isinstance(v, str):
            continue
        clean, n = deidentify_for_export(v, party, court)
        if n:
            payload[k] = clean
            total += n
    return payload, total


def _deadline_payload(d: dict, m: dict) -> tuple:
    """sme deadline row → DeadlineIn。external_ref=sme deadline id（不透明）；source/computed_by 標
    sme 引擎自動回寫（不偽裝律師手填）；title=type 推得的去識別化法定標籤（**非**自由文字 description）；
    全 payload 過邊界 gate（見 _gate_payload）。回 (payload, gate命中數)。"""
    payload = {
        "external_system": "sme",
        "external_ref": str(d["id"]),
        "source": "sme_engine",
        "computed_by": "sme_engine",
        "title": _safe_title(d),
    }
    for f in _DEADLINE_FIELDS:
        payload[f] = d.get(f)
    payload["type"] = _safe_type(d.get("type"))  # 未知代碼→"custom"、不 verbatim 外送
    return _gate_payload(payload, m)


def _correspondence_payload(it: dict, m: dict, *, linked_deadline_ref=None, void: bool = False) -> tuple:
    """sme intake row → CorrespondenceIn。**去識別化（結構性）**：只送結構化非識別欄（doc_type / 日期 /
    教示天數 / 方向 / refs）。**絕不送**：issuer(來文機關)、subject(完整主旨)、以及自由文字 `extracted_summary`
    ——OCR/摘要天生可能含當事人名 / 來文機關 / 完整主旨（codex Task C R1 HIGH）；人類可讀主旨留律師在
    pleading UI 本地補（pleading_coder 確認 UI 有 subject 手填入口）。"""
    payload = {
        "external_system": "sme",
        "external_ref": str(it["id"]),
        "source": "sme_engine",
        "direction": "in",  # 收文
        "doc_type": it.get("doc_type"),
        "service_base_date": it.get("service_base_date"),
        "document_date": it.get("document_date"),
        "stated_period_days": it.get("stated_period_days"),
        # linked_deadline_ref：收文先入、deadline 後生 → 二次補件帶該 deadline 的 external_ref
        "linked_deadline_ref": (str(linked_deadline_ref) if linked_deadline_ref else None),
    }
    if void:
        # 整合撤回（intake discarded / 錯誤回寫）→ status='void'（update 非 delete、pleading 排除 active+提醒）
        payload["status"] = "void"
    return _gate_payload(payload, m)


def _extract_id(view):
    return view.get("id") if isinstance(view, dict) else None


def _log(db, action: str, target_type: str, target_id: int, detail: str) -> None:
    """回寫層留痕（即記即 commit；失敗吞掉——留痕失敗不可反過來擋回寫/業務）。
    detail **只記數量/狀態、絕不寫被 strip 的名字**（同 screen_calendar_text：自檢不可反而把 PII 漏進 log）。"""
    try:
        repository.insert_interaction_log(
            db, actor="system", action=action,
            target_type=target_type, target_id=target_id, detail=detail, business_unit=None,
        )
        db.commit()
    except Exception:
        pass


def _dispatch(build_call):
    """共用「呼 pleading + 例外 → 結構化結果」外殼。build_call() 回 (view, pleading_id_or_None)
    或拋 PleadingError 子類。**任何例外都轉結果、不外拋**。"""
    try:
        return build_call()
    except PleadingAuthError as e:
        return _result("auth_failed", str(e))
    except PleadingNotFound as e:
        return _result("not_found", str(e))
    except PleadingUnreachable as e:
        return _result("unreachable", str(e))
    except PleadingError as e:
        return _result("error", str(e))
    except Exception as e:  # 最後防線：回寫絕不炸引擎
        return _result("error", f"unexpected: {e}")


# ───────────────────────── 對外：回寫 ─────────────────────────

def writeback_deadline(deadline_id: int, *, actor_name: str = "") -> dict:
    """把一筆 sme 末日 upsert 進 pleading（冪等 by external_ref），成功則把 pleading row id 存回
    deadlines.calendar_event_id（provider='pleading'）。整合未配置 / 未綁定 / 無 token → 略過（inert）。"""
    if not integration_configured():
        return _result("not_configured")

    def _do():
        db = get_db()
        try:
            d = repository.get_deadline(db, deadline_id)
            if not d:
                return _result("skipped", "找不到時限")
            d = dict(d)
            m = repository.get_matter(db, d.get("matter_id"))
            if not m:
                return _result("skipped", "找不到母案件")
            m = dict(m)
            pcid = (m.get("pleading_case_id") or "").strip()
            if not pcid:
                return _result("skipped", "案件未綁定 pleading")
            token = select_pleading_token(
                db,
                actor_name=actor_name,
                assignee_name=(d.get("assignee") or ""),
                lead_attorney_name=(m.get("lead_attorney") or ""),
            )
            if not token:
                # 半配置可觀測性（F-P2-WIN-1(b)）：API_BASE 已配、案件已綁、卻選不到 token＝整合「配了
                # 一半」——純未配置維持 inert 靜默，但這種組合要留一行 log 供排查（否則鏡像 stale 無人知）。
                _log(db, "pleading_writeback_skipped", "deadline", deadline_id,
                     "pleading 回寫略過：整合已配置、案件已綁定，但選不到律師 token（未綁定或已停用？）")
                return _result("skipped", "選不到律師 token")
            # assignee/reviewed_by 豁免前提＝在職員工名（codex R1 HIGH）：非員工字串不外送
            d["assignee"] = _employee_or_none(db, d.get("assignee"))
            d["reviewed_by"] = _employee_or_none(db, d.get("reviewed_by"))
            payload, _gate_hits = _deadline_payload(d, m)
            if _gate_hits:
                # 去識別化 gate 命中（只記數量、不記名字）：strip 已發生＝結構防線運作的證據
                _log(db, "pleading_writeback_deidentified", "deadline", deadline_id,
                     f"回寫去識別化 gate：strip {_gate_hits} 個已知當事人/法院 token（payload 已泛稱化後送出）")
            view = PleadingClient(token).upsert_deadline(pcid, payload)
            pid = _extract_id(view)
            if pid is not None:
                # 存回對位（pleading 視為一個 calendar provider；沿用既有 mark_calendared 去重/更新機制）
                repository.mark_calendared(db, deadline_id, str(pid), "pleading", _now())
                db.commit()
            return _result("ok", f"pleading #{pid}", pleading_id=pid)
        finally:
            db.close()

    return _dispatch(_do)


def writeback_correspondence(
    intake_id: int, *, actor_name: str = "", linked_deadline_ref=None, void: bool = False
) -> dict:
    """把一筆 sme 收文（pending_intake）upsert 進 pleading 收發文簿（冪等 by external_ref）。
    未建案（intake.matter_id 為 NULL）/ 未綁定 / 無 token → 略過。void=True → 整合撤回（status='void'）。"""
    if not integration_configured():
        return _result("not_configured")

    def _do():
        db = get_db()
        try:
            it = repository.get_pending_intake(db, intake_id)
            if not it:
                return _result("skipped", "找不到待確認暫存")
            it = dict(it)
            mid = it.get("matter_id")
            if not mid:
                return _result("skipped", "暫存未建案（無 pleading 對應）")
            m = repository.get_matter(db, mid)
            if not m:
                return _result("skipped", "找不到母案件")
            m = dict(m)
            pcid = (m.get("pleading_case_id") or "").strip()
            if not pcid:
                return _result("skipped", "案件未綁定 pleading")
            token = select_pleading_token(
                db, actor_name=actor_name, lead_attorney_name=(m.get("lead_attorney") or "")
            )
            if not token:
                _log(db, "pleading_writeback_skipped", "intake", intake_id,
                     "pleading 回寫略過：整合已配置、案件已綁定，但選不到律師 token（未綁定或已停用？）")
                return _result("skipped", "選不到律師 token")
            payload, _gate_hits = _correspondence_payload(
                it, m, linked_deadline_ref=linked_deadline_ref, void=void
            )
            if _gate_hits:
                _log(db, "pleading_writeback_deidentified", "intake", intake_id,
                     f"回寫去識別化 gate：strip {_gate_hits} 個已知當事人/法院 token（payload 已泛稱化後送出）")
            view = PleadingClient(token).upsert_correspondence(pcid, payload)
            return _result("ok", "correspondence", pleading_id=_extract_id(view))
        finally:
            db.close()

    return _dispatch(_do)
