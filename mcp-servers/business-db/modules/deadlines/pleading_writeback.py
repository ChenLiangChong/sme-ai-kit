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
    return f"法定期限（{t}）" if t else "法定期限提醒"


def _deadline_payload(d: dict) -> dict:
    """sme deadline row → DeadlineIn。external_ref=sme deadline id（不透明）；source/computed_by 標
    sme 引擎自動回寫（不偽裝律師手填）；title=type 推得的去識別化法定標籤（**非**自由文字 description）。"""
    payload = {
        "external_system": "sme",
        "external_ref": str(d["id"]),
        "source": "sme_engine",
        "computed_by": "sme_engine",
        "title": _safe_title(d),
    }
    for f in _DEADLINE_FIELDS:
        payload[f] = d.get(f)
    return payload


def _correspondence_payload(it: dict, *, linked_deadline_ref=None, void: bool = False) -> dict:
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
    return payload


def _extract_id(view):
    return view.get("id") if isinstance(view, dict) else None


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
                return _result("skipped", "選不到律師 token")
            view = PleadingClient(token).upsert_deadline(pcid, _deadline_payload(d))
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
                return _result("skipped", "選不到律師 token")
            view = PleadingClient(token).upsert_correspondence(
                pcid, _correspondence_payload(it, linked_deadline_ref=linked_deadline_ref, void=void)
            )
            return _result("ok", "correspondence", pleading_id=_extract_id(view))
        finally:
            db.close()

    return _dispatch(_do)
