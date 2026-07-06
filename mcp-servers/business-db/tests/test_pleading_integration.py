"""Task C / M2：sme→pleading 回寫 client + 編排 單元測（mock urlopen、不需 live exe）。

standalone runner（同 test_deadline_engine 的 _assert + tempfile + sys.exit）；已加 conftest collect_ignore。
契約見 bridge KB `pleading_rest_contract`（frozen v4）。真 e2e（實呼 live exe）待整合環境、本檔全 mock。

涵蓋：
- 傳輸層（pleading_client）：URL / method / Cookie auth / JSON body(None 略過) / 回應解析 /
  401·404·連線失敗·5xx → 具名例外 / 未配置擋建構。
- 編排（pleading_writeback）：configured 寫入 + 存回 calendar_event_id / 未配置 inert / 未綁定 skip /
  無 token skip / §127 互動(actor) vs 自主(assignee→lead) 選 token / 去識別化(無 issuer·subject) /
  void / 冪等 external_ref / graceful 401·404·unreachable（絕不 raise）。
- 服務接線：create_deadline / stage_deadline_intake 配置後回覆帶「已同步 pleading」、未配置靜默（inert）。
"""
import atexit
import contextlib
import io
import json
import os
import sqlite3
import sys
import tempfile
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
DB_PATH = _tmp.name
_tmp.close()
os.environ["SME_DB_PATH"] = DB_PATH
# 起始一律「未配置」（inert）；個別測用 _configured() 暫時開啟。
os.environ.pop("PLEADING_API_BASE", None)
_BASE = "http://172.19.48.1:8200"


@atexit.register
def _cleanup():
    try:
        os.unlink(DB_PATH)
    except OSError:
        pass


import server  # noqa: E402

server.DB_PATH = DB_PATH
server.init_db()

from modules.deadlines import pleading_client as pc  # noqa: E402
from modules.deadlines import pleading_writeback as wb  # noqa: E402
from modules.deadlines import service as svc  # noqa: E402
from shared.db import get_db  # noqa: E402
from shared.deadlines import STATUTORY_PERIODS  # noqa: E402

_LABEL_APPEAL = STATUTORY_PERIODS["appeal_civil"]["label"]  # 去識別化 title 的固定法定標籤

passed = 0
failed = 0
failures: list[str] = []


def _assert(name: str, cond: bool, detail: str = ""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        failures.append(f"{name}  [{detail}]")
        print(f"FAIL: {name}  [{detail}]")


# ───────────────────────── mock urlopen 基建 ─────────────────────────

class _FakeResp:
    def __init__(self, status, body):
        self.status = status
        self._body = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


_cap: dict = {}


def _make_urlopen(*, status=200, body=None, raise_exc=None):
    def _fake(req, timeout=None):
        _cap["url"] = req.full_url
        _cap["method"] = req.get_method()
        _cap["headers"] = {k.lower(): v for k, v in req.header_items()}
        _cap["body"] = json.loads(req.data.decode("utf-8")) if req.data else None
        _cap["timeout"] = timeout
        if raise_exc is not None:
            raise raise_exc
        return _FakeResp(status, body if body is not None else {})
    return _fake


@contextlib.contextmanager
def _patch_urlopen(**kw):
    orig = urllib.request.urlopen
    urllib.request.urlopen = _make_urlopen(**kw)
    try:
        yield
    finally:
        urllib.request.urlopen = orig


@contextlib.contextmanager
def _configured(base=_BASE):
    prev = os.environ.get("PLEADING_API_BASE")
    os.environ["PLEADING_API_BASE"] = base
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop("PLEADING_API_BASE", None)
        else:
            os.environ["PLEADING_API_BASE"] = prev


def _http_error(code, detail="err"):
    return urllib.error.HTTPError(
        _BASE, code, "x", {}, io.BytesIO(json.dumps({"detail": detail}).encode("utf-8"))
    )


# ───────────────────────── 種子 ─────────────────────────

_db = get_db()
# 三個律師：actor(觸發者) / assignee(承辦) / lead(主辦)，token 各異 → 驗 §127 選誰
for _nm, _uid in (("C律師", "a"), ("C承辦", "b"), ("C主辦", "c"), ("C無token", "d")):
    _db.execute(
        "INSERT OR IGNORE INTO employees (name, role, active, line_user_id) VALUES (?, 'lawyer', 1, ?)",
        (_nm, "U" + _uid * 32),
    )
_db.commit()
svc.bind_pleading_token("C律師", "tok-actor", "操作者")
svc.bind_pleading_token("C承辦", "tok-assignee", "操作者")
svc.bind_pleading_token("C主辦", "tok-lead", "操作者")

# 綁定案（pleading_case_id=PLD-100、lead=C主辦）+ 一筆 deadline（assignee=C承辦）
_db.execute(
    "INSERT INTO matters (title, status, lead_attorney, pleading_case_id, has_local_agent, confidential) "
    "VALUES ('整合測試案','open','C主辦','PLD-100',0,0)"
)
_MID = _db.execute("SELECT id FROM matters WHERE pleading_case_id='PLD-100'").fetchone()["id"]


def _mk_deadline(assignee="C承辦", status="pending"):
    _db.execute(
        "INSERT INTO deadlines (matter_id, type, description, period_type, severity, trigger_event, "
        "service_type, service_base_date, statutory_days, statutory_basis, statutory_basis_version, "
        "statutory_deadline, internal_deadline, status, assignee, period_unit, period_value, "
        "needs_manual_review, calc_trace) VALUES (?, 'appeal_civil','對一審判決提起上訴','peremptory','red',"
        "'判決送達','normal','2026-06-01',20,'民訴§440','民訴§440 現行','2026-06-22','2026-06-21',?,?,"
        "'day',NULL,0,'[]')",
        (_MID, status, assignee),
    )
    _db.commit()
    return _db.execute("SELECT MAX(id) m FROM deadlines").fetchone()["m"]


def _mk_intake(matter_id=_MID, summary="收到一審判決、教示上訴20日"):
    _db.execute(
        "INSERT INTO pending_intakes (matter_id, matter_label, doc_type, service_base_date, "
        "stated_period_days, document_date, extracted_summary, status) "
        "VALUES (?, '案件代號X', '判決', '2026-06-01', 20, '2026-05-28', ?, 'awaiting')",
        (matter_id, summary),
    )
    _db.commit()
    return _db.execute("SELECT MAX(id) m FROM pending_intakes").fetchone()["m"]


# ═════════════════════ A. 傳輸層 pleading_client ═════════════════════

# A1：未配置 → 建構擋下
_raisedA1 = False
try:
    pc.PleadingClient("tok", base_url="")
except pc.PleadingNotConfigured:
    _raisedA1 = True
_assert("A1 client 未配置(base='') → PleadingNotConfigured", _raisedA1)

# A2：POST 帶 Cookie auth + 正確 URL/method + None 略過
with _patch_urlopen(status=201, body={"id": 777, "status": "pending"}):
    _v = pc.PleadingClient("tok-xyz", base_url=_BASE).upsert_deadline(
        "PLD-100", {"external_ref": "5", "title": "x", "severity": None}
    )
_assert("A2 回應解析（回 dict 含 id）", isinstance(_v, dict) and _v.get("id") == 777, detail=str(_v))
_assert("A2 URL 正確", _cap["url"] == f"{_BASE}/api/cases/PLD-100/deadlines", detail=_cap.get("url"))
_assert("A2 method=POST", _cap["method"] == "POST")
_assert("A2 Cookie pm_session auth（非 Bearer）",
        _cap["headers"].get("cookie") == "pm_session=tok-xyz" and "authorization" not in _cap["headers"],
        detail=str(_cap["headers"]))
_assert("A2 None 欄位略過（severity 不送）",
        "severity" not in _cap["body"] and _cap["body"].get("external_ref") == "5", detail=str(_cap["body"]))

# A3：401 / 404 / 連線失敗 / 5xx → 具名例外
def _expect(exc_type, **kw):
    with _patch_urlopen(**kw):
        try:
            pc.PleadingClient("t", base_url=_BASE).get_deadlines("PLD-100")
            return False
        except exc_type:
            return True
        except Exception:
            return False


_assert("A3 401 → PleadingAuthError", _expect(pc.PleadingAuthError, raise_exc=_http_error(401)))
_assert("A3 404 → PleadingNotFound", _expect(pc.PleadingNotFound, raise_exc=_http_error(404)))
_assert("A3 500 → PleadingHTTPError", _expect(pc.PleadingHTTPError, raise_exc=_http_error(500)))
_assert("A3 連線失敗(URLError) → PleadingUnreachable",
        _expect(pc.PleadingUnreachable, raise_exc=urllib.error.URLError("refused")))

# A4：token_is_live 探活（whoami 成功=True、失敗=False、絕不拋）
with _patch_urlopen(status=200, body={"kind": "local"}):
    _live = pc.token_is_live("tok", base_url=_BASE)
_assert("A4 token_is_live whoami 成功 → True", _live is True)
with _patch_urlopen(raise_exc=urllib.error.URLError("down")):
    _dead = pc.token_is_live("tok", base_url=_BASE)
_assert("A4 token_is_live 連不上 → False（不拋）", _dead is False)


# ═════════════════════ B. 編排 pleading_writeback（deadline）═════════════════════

_dl = _mk_deadline(assignee="C承辦")

# B1：未配置 → inert（not_configured、完全不打 HTTP）
_cap.clear()
_rB1 = wb.writeback_deadline(_dl, actor_name="C律師")
_assert("B1 未配置 → not_configured（inert）", _rB1["status"] == "not_configured", detail=str(_rB1))
_assert("B1 未配置 → note 靜默（空字串）", wb.note_for(_rB1) == "")
_assert("B1 未配置 → 完全沒發 HTTP", _cap == {})

# B2：configured + 綁定 + 有 token → ok、存回 pleading id 到 calendar_event_id、payload 正確
with _configured(), _patch_urlopen(status=201, body={"id": 900, "status": "pending"}):
    _rB2 = wb.writeback_deadline(_dl, actor_name="C律師")
_assert("B2 configured 寫入成功 → ok + pleading_id", _rB2["status"] == "ok" and _rB2["pleading_id"] == 900,
        detail=str(_rB2))
_row = get_db().execute("SELECT calendar_event_id, calendar_provider FROM deadlines WHERE id=?", (_dl,)).fetchone()
_assert("B2 存回 calendar_event_id=pleading row id、provider=pleading",
        _row["calendar_event_id"] == "900" and _row["calendar_provider"] == "pleading", detail=str(dict(_row)))
_assert("B2 payload：external_system=sme / external_ref=deadline_id / source=sme_engine / computed_by=sme_engine",
        _cap["body"].get("external_system") == "sme" and _cap["body"].get("external_ref") == str(_dl)
        and _cap["body"].get("source") == "sme_engine" and _cap["body"].get("computed_by") == "sme_engine",
        detail=str(_cap["body"]))
_assert("B2 payload 帶 assignee（§127 當責）+ 去識別化 title（type 標籤、非自由文字 description）",
        _cap["body"].get("assignee") == "C承辦" and _cap["body"].get("title") == _LABEL_APPEAL
        and _cap["body"].get("title") != "對一審判決提起上訴", detail=str(_cap["body"]))
_assert("B2 note 出聲（已同步 pleading #900）", "已同步 pleading" in wb.note_for(_rB2) and "900" in wb.note_for(_rB2))

# B3：§127 互動(actor) 用觸發者 token；自主(actor 空) 用 assignee token
with _configured(), _patch_urlopen(status=201, body={"id": 1}):
    wb.writeback_deadline(_dl, actor_name="C律師")
_assert("B3 互動 actor=C律師 → Cookie=tok-actor", _cap["headers"]["cookie"] == "pm_session=tok-actor",
        detail=_cap["headers"].get("cookie"))
with _configured(), _patch_urlopen(status=201, body={"id": 1}):
    wb.writeback_deadline(_dl, actor_name="")
_assert("B3 自主(actor 空) → assignee C承辦 → Cookie=tok-assignee",
        _cap["headers"]["cookie"] == "pm_session=tok-assignee", detail=_cap["headers"].get("cookie"))

# B3b：自主 + assignee 無 token → fallback lead_attorney（C主辦）
_dl_noassignee = _mk_deadline(assignee="C無token")
with _configured(), _patch_urlopen(status=201, body={"id": 2}):
    wb.writeback_deadline(_dl_noassignee, actor_name="")
_assert("B3b 自主 assignee 無 token → fallback lead C主辦 → Cookie=tok-lead",
        _cap["headers"]["cookie"] == "pm_session=tok-lead", detail=_cap["headers"].get("cookie"))

# B4：graceful degrade — 401 / 404 / unreachable 皆回結構化結果、不 raise、不動 store-back
with _configured(), _patch_urlopen(raise_exc=_http_error(401)):
    _rB4a = wb.writeback_deadline(_dl, actor_name="C律師")
_assert("B4 401 → auth_failed（graceful、不 raise）", _rB4a["status"] == "auth_failed", detail=str(_rB4a))
with _configured(), _patch_urlopen(raise_exc=_http_error(404)):
    _rB4b = wb.writeback_deadline(_dl, actor_name="C律師")
_assert("B4 404 → not_found", _rB4b["status"] == "not_found", detail=str(_rB4b))
with _configured(), _patch_urlopen(raise_exc=urllib.error.URLError("refused")):
    _rB4c = wb.writeback_deadline(_dl, actor_name="C律師")
_assert("B4 連線失敗 → unreachable", _rB4c["status"] == "unreachable", detail=str(_rB4c))
_assert("B4 note：401/404/unreachable 皆出「略過·不影響本筆」提醒",
        all("略過" in wb.note_for(r) and "不影響" in wb.note_for(r) for r in (_rB4a, _rB4b, _rB4c)))

# B4b：遠端 error body 絕不回顯到 operator note / result（codex R1 MED；body 可能含 request 回顯 / PII / token）
_SENTINEL = "SENTINEL_LEAK_pm_session_deadbeef"
with _configured(), _patch_urlopen(raise_exc=_http_error(500, detail=_SENTINEL)):
    _rB4d = wb.writeback_deadline(_dl, actor_name="C律師")
_assert("B4b 500 → error（graceful、不 raise）", _rB4d["status"] == "error", detail=str(_rB4d))
_assert("B4b 遠端 body sentinel 不出現在 operator note（固定文案、不回顯遠端 body）",
        _SENTINEL not in wb.note_for(_rB4d), detail=wb.note_for(_rB4d))
_assert("B4b 遠端 body sentinel 也不進 result（client 不讀 error body）",
        _SENTINEL not in json.dumps(_rB4d, ensure_ascii=False), detail=str(_rB4d))

# B5：未綁定案（無 pleading_case_id）→ skipped（configured 也不寫）
_db.execute("INSERT INTO matters (title, status, lead_attorney, has_local_agent, confidential) "
            "VALUES ('未綁定案','open','C主辦',0,0)")
_mid_nolink = _db.execute("SELECT id FROM matters WHERE title='未綁定案'").fetchone()["id"]
_db.execute("INSERT INTO deadlines (matter_id, type, description, period_type, trigger_event, service_type, "
            "service_base_date, statutory_days, statutory_basis, statutory_deadline, internal_deadline, status, "
            "assignee, period_unit, needs_manual_review, calc_trace) VALUES (?, 'appeal_civil','x','peremptory',"
            "'判決送達','normal','2026-06-01',20,'民訴§440','2026-06-22','2026-06-21','pending','C承辦','day',0,'[]')",
            (_mid_nolink,))
_db.commit()
_dl_nolink = _db.execute("SELECT MAX(id) m FROM deadlines").fetchone()["m"]
_cap.clear()
with _configured(), _patch_urlopen(status=201, body={"id": 9}):
    _rB5 = wb.writeback_deadline(_dl_nolink, actor_name="C律師")
_assert("B5 案未綁定 pleading → skipped（不寫、靜默）", _rB5["status"] == "skipped" and wb.note_for(_rB5) == "",
        detail=str(_rB5))
_assert("B5 skipped → 沒發 HTTP", _cap == {})

# B6：去識別化 — description 含當事人名 → title 為 type 標籤、payload 全文絕無姓名（codex R1 HIGH）
_dl_pii = _mk_deadline(assignee="C承辦")
_db.execute("UPDATE deadlines SET description=? WHERE id=?", ("王小明對一審判決提起上訴（極機密）", _dl_pii))
_db.commit()
with _configured(), _patch_urlopen(status=201, body={"id": 3}):
    wb.writeback_deadline(_dl_pii, actor_name="C律師")
_pii_dl = json.dumps(_cap["body"], ensure_ascii=False)
_assert("B6 去識別化：description 含姓名 → title=type 標籤、且 payload 全文無「王小明」",
        _cap["body"].get("title") == _LABEL_APPEAL and "王小明" not in _pii_dl, detail=_pii_dl)

# B7：title 保證非空 — custom/未知 type → 仍送固定安全標籤（非空、零姓名）（pleading_coder pin / marketing lock）
_dl_custom = _mk_deadline(assignee="C承辦")
_db.execute("UPDATE deadlines SET type='custom', description=? WHERE id=?", ("王小明的自訂期限", _dl_custom))
_db.commit()
with _configured(), _patch_urlopen(status=201, body={"id": 4}):
    wb.writeback_deadline(_dl_custom, actor_name="C律師")
_t_custom = _cap["body"].get("title")
_assert("B7 custom type → title 非空、固定安全字串、無自由文字姓名",
        bool(_t_custom) and "王小明" not in json.dumps(_cap["body"], ensure_ascii=False), detail=str(_t_custom))


# ═════════════════════ C. 編排 writeback（correspondence · 去識別化 · void）═════════════════════

_ik = _mk_intake()

# C1：收文回寫 — direction=in、去識別化（無 issuer / subject / 當事人名）、帶去識別化摘要
with _configured(), _patch_urlopen(status=201, body={"id": 555}):
    _rC1 = wb.writeback_correspondence(_ik, actor_name="C律師")
_assert("C1 收文回寫成功 → ok", _rC1["status"] == "ok", detail=str(_rC1))
_assert("C1 direction=in / external_ref=intake_id / source=sme_engine",
        _cap["body"].get("direction") == "in" and _cap["body"].get("external_ref") == str(_ik)
        and _cap["body"].get("source") == "sme_engine", detail=str(_cap["body"]))
_assert("C1 去識別化：payload 絕無 issuer / subject / extracted_summary（自由文字/當事人身分不外送）",
        all(k not in _cap["body"] for k in ("issuer", "subject", "extracted_summary")),
        detail=str(list(_cap["body"].keys())))
_assert("C1 仍送結構化非識別欄（doc_type / stated_period_days）",
        _cap["body"].get("doc_type") == "判決" and _cap["body"].get("stated_period_days") == 20,
        detail=str(_cap["body"]))
_assert("C1 URL 走 correspondence 端點", _cap["url"] == f"{_BASE}/api/cases/PLD-100/correspondence")

# C2：linked_deadline_ref 二次補件（收文先入、deadline 後生）
with _configured(), _patch_urlopen(status=201, body={"id": 556}):
    wb.writeback_correspondence(_ik, actor_name="C律師", linked_deadline_ref=_dl)
_assert("C2 linked_deadline_ref = deadline external_ref（str）", _cap["body"].get("linked_deadline_ref") == str(_dl),
        detail=str(_cap["body"]))

# C3：void（整合撤回）→ status='void'（update 非 delete）
with _configured(), _patch_urlopen(status=201, body={"id": 557}):
    wb.writeback_correspondence(_ik, actor_name="C律師", void=True)
_assert("C3 void → status='void'", _cap["body"].get("status") == "void", detail=str(_cap["body"]))

# C4：intake 未建案（matter_id NULL）→ skipped（無 pleading 對應）
_ik_nomatter = _mk_intake(matter_id=None)
_cap.clear()
with _configured(), _patch_urlopen(status=201, body={"id": 1}):
    _rC4 = wb.writeback_correspondence(_ik_nomatter, actor_name="C律師")
_assert("C4 intake 未建案 → skipped（不寫）", _rC4["status"] == "skipped" and _cap == {}, detail=str(_rC4))

# C5：去識別化 — extracted_summary 含姓名/機關 → 整個自由文字欄不外送、payload 全文無識別資訊（codex R1 HIGH）
_ik_pii = _mk_intake(summary="臺北地院來文：王小明侵權損害賠償上訴案")
with _configured(), _patch_urlopen(status=201, body={"id": 559}):
    wb.writeback_correspondence(_ik_pii, actor_name="C律師")
_pii_co = json.dumps(_cap["body"], ensure_ascii=False)
_assert("C5 去識別化：summary 含姓名/機關 → payload 全文無「王小明」「臺北地院」、且無 extracted_summary",
        "王小明" not in _pii_co and "臺北地院" not in _pii_co and "extracted_summary" not in _cap["body"],
        detail=_pii_co)


# ═════════════════════ D. 服務接線（create_deadline / stage_deadline_intake）═════════════════════

# D1：未配置 → create_deadline 回覆不帶 pleading note（inert、對既有行為零影響）
_r_unconf = svc.create_deadline(
    matter_id=_MID, type="appeal_civil", description="上訴", trigger_event="判決送達",
    service_base_date="2026-06-01", service_type="normal", statutory_days=0, statutory_basis="",
    statutory_basis_version="", period_type="", severity="", has_local_agent=1, in_transit_days=0,
    court_region="", party_region="", buffer_days=1, stated_period_days=0, document_date="",
    assignee="C承辦", assignee_line_user_id="", escalation_lead_days="", created_by="C律師",
)
_assert("D1 未配置 → create_deadline 靜默（回覆不含 pleading 字樣）",
        "時限 #" in _r_unconf and "pleading" not in _r_unconf, detail=_r_unconf[-60:])

# D2：configured → create_deadline 回覆帶「已同步 pleading」（接線真的觸發）
with _configured(), _patch_urlopen(status=201, body={"id": 8001}):
    _r_conf = svc.create_deadline(
        matter_id=_MID, type="appeal_civil", description="上訴2", trigger_event="判決送達",
        service_base_date="2026-06-01", service_type="normal", statutory_days=0, statutory_basis="",
        statutory_basis_version="", period_type="", severity="", has_local_agent=1, in_transit_days=0,
        court_region="", party_region="", buffer_days=1, stated_period_days=0, document_date="",
        assignee="C承辦", assignee_line_user_id="", escalation_lead_days="", created_by="C律師",
    )
_assert("D2 configured → create_deadline 接線觸發、回覆帶「已同步 pleading」",
        "已同步 pleading" in _r_conf, detail=_r_conf[-80:])
_assert("D2 接線走 deadline 端點 + external_ref=新 deadline id",
        _cap["url"].endswith("/deadlines") and _cap["body"].get("external_system") == "sme", detail=_cap.get("url"))

# D3：configured → stage_deadline_intake 回覆帶「已同步 pleading」（收文接線）
with _configured(), _patch_urlopen(status=201, body={"id": 8100}):
    _r_stage = svc.stage_deadline_intake(
        matter_id=_MID, matter_label="案件代號Y", doc_type="判決", service_base_date="2026-06-01",
        stated_period_days=20, document_date="2026-05-28", extracted_summary="收到判決、上訴20日",
        submitted_by="C律師",
    )
_assert("D3 configured → stage_deadline_intake 接線觸發「已同步 pleading」+ 走 correspondence 端點",
        "已同步 pleading" in _r_stage and _cap["url"].endswith("/correspondence"), detail=_r_stage[-80:])


# ═══════════ E. F-STATUS-SYNC（狀態變更也回寫：mark_deadline_filed / mark_deadline_reviewed）═══════════
# 修前：Task C 只在 create/amend/stage/resolve(void) 接回寫；mark_filed / mark_reviewed 缺 hook →
# pleading 端 status / 覆核狀態永久 stale（e2e F-P2-1 + F-P3-1）。修後：兩者在 with 區塊 commit 後補回寫。

# E1：mark_deadline_filed configured → 回寫觸發、送 status='filed' + external_ref 對位 + 回覆帶「已同步」
_dl_e1 = _mk_deadline(assignee="C承辦", status="pending")
_cap.clear()
with _configured(), _patch_urlopen(status=200, body={"id": 9101, "status": "filed"}):
    _r_e1 = svc.mark_deadline_filed(_dl_e1, "C律師")
_assert("E1 mark_filed → 回寫觸發、送 status=filed + external_ref 對位",
        _cap.get("body") is not None and _cap["body"].get("status") == "filed"
        and _cap["body"].get("external_ref") == str(_dl_e1), detail=str(_cap.get("body")))
_assert("E1 mark_filed → 回覆帶『已同步 pleading』", "已同步 pleading" in _r_e1, detail=_r_e1[-60:])

# E2：mark_deadline_filed 未配置（inert）→ 不回寫、不報錯、回覆無「已同步」（狀態變更也遵守 inert-by-default）
_dl_e2 = _mk_deadline(assignee="C承辦", status="pending")
with _patch_urlopen(status=200, body={"id": 9102}):  # 無 _configured() → inert
    _r_e2 = svc.mark_deadline_filed(_dl_e2, "C律師")
_assert("E2 mark_filed 未配置 → inert（回覆無『已同步 pleading』、仍正常標記遞交）",
        "已同步 pleading" not in _r_e2 and "已標記為已遞交" in _r_e2, detail=_r_e2[-60:])

# E3：mark_deadline_reviewed configured → 回寫觸發、送 reviewed_by + needs_manual_review=0（覆核清除同步）
_dl_e3 = _mk_deadline(assignee="C承辦", status="pending")
_db.execute("UPDATE deadlines SET needs_manual_review=1 WHERE id=?", (_dl_e3,))
_db.commit()
_cap.clear()
with _configured(), _patch_urlopen(status=200, body={"id": 9103}):
    _r_e3 = svc.mark_deadline_reviewed(_dl_e3, "C律師", "覆核計算無誤")
_assert("E3 mark_reviewed → 回寫觸發、送 reviewed_by=C律師 + needs_manual_review=0",
        _cap.get("body") is not None and _cap["body"].get("reviewed_by") == "C律師"
        and _cap["body"].get("needs_manual_review") in (0, "0", False), detail=str(_cap.get("body")))
_assert("E3 mark_reviewed → 回覆帶『已同步 pleading』", "已同步 pleading" in _r_e3, detail=_r_e3[-60:])


# ═══════════ F. F-P2-2（type_label 跨全表解析 + 非種子已知類型泛型修正）═══════════
from shared.deadlines import (  # noqa: E402
    type_label as _type_label,
    COURT_SET_PERIODS as _CSP,
    LIMITATION_PERIODS as _LP,
    PROCEDURAL_CALENDAR_PERIODS as _PCP,
)
_assert("F1 type_label 種子(appeal_civil)=STATUTORY label", _type_label("appeal_civil") == _LABEL_APPEAL)
_assert("F2 type_label 裁定期間(correction)=COURT_SET label", _type_label("correction") == _CSP["correction"]["label"])
_assert("F3 type_label 消滅時效(statute_197_2y)=LIMITATION label",
        _type_label("statute_197_2y") == _LP["statute_197_2y"]["label"])
_assert("F4 type_label 程序月期間(admin_revocation)=PROCEDURAL label",
        _type_label("admin_revocation") == _PCP["admin_revocation"]["label"])
_assert("F5 type_label 非種子已知(answer)=答辯狀提出期間（泛型修正核心）", _type_label("answer") == "答辯狀提出期間")
_assert("F6 type_label 真未知 custom → None", _type_label("totally_unknown_xyz") is None)
_assert("F7 type_label 空/None → None", _type_label("") is None and _type_label(None) is None)

# F8：answer deadline 實際回寫 → title=可讀「答辯狀提出期間」（非生代碼「法定期限（answer）」）、且去識別化保住
_dl_ans = _mk_deadline(assignee="C承辦")
_db.execute("UPDATE deadlines SET type='answer', description=? WHERE id=?",
            ("答辯狀提出末日（原告王小明·限期答辯通知）", _dl_ans))
_db.commit()
_cap.clear()
with _configured(), _patch_urlopen(status=201, body={"id": 9200}):
    wb.writeback_deadline(_dl_ans, actor_name="C律師")
_assert("F8 answer 回寫 title=答辯狀提出期間（可讀、非生代碼）且 payload 全文無自由文字姓名",
        _cap["body"].get("title") == "答辯狀提出期間"
        and "王小明" not in json.dumps(_cap["body"], ensure_ascii=False), detail=str(_cap["body"].get("title")))


# ═══════════ G. F-P0-4（firm 內部緩衝偏好接進 create_deadline）═══════════
# 修前：create_deadline 未帶 buffer_days → 硬預設 1、不讀 firm 偏好（律師要求「法定前 3 天」被忽略）。
# 修後：未帶時讀 settings deadline_buffer_days；未設 / 非法值 → 1；明確帶值仍優先。

# G1：無設定 → 1
_db.execute("DELETE FROM business_rules WHERE category='settings' AND title='deadline_buffer_days'")
_db.commit()
_assert("G1 _firm_buffer_days 無設定 → 預設 1", svc._firm_buffer_days(_db) == 1)

# G2：設 3 → 3；非數字 → 1；負值 → 1
_db.execute("INSERT INTO business_rules (category, title, content, source_type) "
            "VALUES ('settings','deadline_buffer_days','3','observed')")
_db.commit()
_assert("G2a _firm_buffer_days 設 3 → 3", svc._firm_buffer_days(_db) == 3)
_db.execute("UPDATE business_rules SET content='abc' WHERE category='settings' AND title='deadline_buffer_days'")
_db.commit()
_assert("G2b _firm_buffer_days 非數字 → fallback 1", svc._firm_buffer_days(_db) == 1)
_db.execute("UPDATE business_rules SET content='-2' WHERE category='settings' AND title='deadline_buffer_days'")
_db.commit()
_assert("G2c _firm_buffer_days 負值 → fallback 1", svc._firm_buffer_days(_db) == 1)

# G3：create_deadline 未帶 buffer_days（-1）+ firm 偏好=3 → 建出的 deadline.buffer_days=3（接引擎、非硬 1）
_db.execute("UPDATE business_rules SET content='3' WHERE category='settings' AND title='deadline_buffer_days'")
_db.commit()
_r_g3 = svc.create_deadline(
    matter_id=_MID, type="appeal_civil", description="F-P0-4 buffer 整合測 G3", trigger_event="判決送達",
    service_base_date="2026-06-01", service_type="normal", statutory_days=20,
    statutory_basis="民訴§440", statutory_basis_version="民事訴訟法§440 現行",
    period_type="peremptory", severity="red", has_local_agent=1, in_transit_days=0,
    court_region="", party_region="", buffer_days=-1, stated_period_days=0, document_date="",
    assignee="C承辦", assignee_line_user_id="", escalation_lead_days="", created_by="C律師",
)
_assert("G3a create_deadline（未帶 buffer）無 error", "ERROR" not in _r_g3, detail=_r_g3[:80])
_g3_id = _db.execute("SELECT MAX(id) m FROM deadlines").fetchone()["m"]
_g3_bd = _db.execute("SELECT buffer_days FROM deadlines WHERE id=?", (_g3_id,)).fetchone()["buffer_days"]
_assert("G3b create_deadline 未帶 buffer + firm 偏好 3 → deadline.buffer_days=3（接引擎、非硬 1）",
        _g3_bd == 3, detail=str(_g3_bd))

# G4：明確帶 buffer_days=5 覆寫 firm 偏好 3
_r_g4 = svc.create_deadline(
    matter_id=_MID, type="appeal_civil", description="F-P0-4 明確 buffer G4", trigger_event="判決送達",
    service_base_date="2026-06-01", service_type="normal", statutory_days=20,
    statutory_basis="民訴§440", statutory_basis_version="民事訴訟法§440 現行",
    period_type="peremptory", severity="red", has_local_agent=1, in_transit_days=0,
    court_region="", party_region="", buffer_days=5, stated_period_days=0, document_date="",
    assignee="C承辦", assignee_line_user_id="", escalation_lead_days="", created_by="C律師",
)
_assert("G4a create_deadline（明確 buffer=5）無 error", "ERROR" not in _r_g4, detail=_r_g4[:80])
_g4_id = _db.execute("SELECT MAX(id) m FROM deadlines").fetchone()["m"]
_g4_bd = _db.execute("SELECT buffer_days FROM deadlines WHERE id=?", (_g4_id,)).fetchone()["buffer_days"]
_assert("G4b 明確 buffer_days=5 覆寫 firm 偏好 3", _g4_bd == 5, detail=str(_g4_bd))

# G5：codex post-run MED（同 key 多筆 active 讀到舊值）在此 schema 下的實況 + 修法驗證。
#   (a) 同 (category,title,BU) 第二筆 active 被 unique index `idx_rules_unique_active` 擋下（IntegrityError·
#       UNIQUE）→ 單一事務所（BU=NULL）永遠 ≤1 active、讀取本就確定性（codex MED「兩次 store_fact」DB-prevented）；
#   (c) 唯一能多筆 active＝跨 business_unit；ORDER BY id DESC LIMIT 1 取「最新 id」（非 max content）。
_db.execute("DELETE FROM business_rules WHERE category='settings' AND title='deadline_buffer_days'")
_db.execute("INSERT INTO business_rules (category, title, content, source_type) "
            "VALUES ('settings','deadline_buffer_days','9','observed')")
_db.commit()
# 只接 IntegrityError + 驗訊息含 UNIQUE（codex LOW：except Exception 會把 SQL typo/schema 漂移的
# OperationalError 也當成「被擋」而假綠；非 IntegrityError 應讓它炸出來、不吞）
_dup_err = ""
try:
    _db.execute("INSERT INTO business_rules (category, title, content, source_type) "
                "VALUES ('settings','deadline_buffer_days','1','observed')")
    _db.commit()
except sqlite3.IntegrityError as _e:
    _db.rollback()
    _dup_err = str(_e)
_assert("G5a 同 key 第二筆 active 被 unique index 擋（IntegrityError·UNIQUE constraint、非任意錯誤假綠）",
        "UNIQUE constraint failed" in _dup_err, detail=_dup_err or "（未觸發 IntegrityError）")
_assert("G5b 唯一 active 讀到 9", svc._firm_buffer_days(_db) == 9, detail=str(svc._firm_buffer_days(_db)))
# (c) 跨 BU：全域(較早·content 9) + brand_x(較晚·content 7)、期望 7 → 卡死「latest id wins」；
#     若實作誤成 content DESC 會回 9 而 fail（codex LOW：原 3→7 無法區分 latest-id vs max-content）。
_db.execute("INSERT INTO business_rules (category, title, content, source_type, business_unit) "
            "VALUES ('settings','deadline_buffer_days','7','observed','brand_x')")
_db.commit()
_assert("G5c 跨 BU 多筆 active → 取最新 id 7（非 max content 9；卡死 latest-id-wins、非隨機/非 content DESC）",
        svc._firm_buffer_days(_db) == 7, detail=str(svc._firm_buffer_days(_db)))

# 清理：移除測試設定（避免污染同進程後續 create_deadline）
_db.execute("DELETE FROM business_rules WHERE category='settings' AND title='deadline_buffer_days'")
_db.commit()


# ───────────────────────── H：回寫邊界去識別化 gate（F-P2-WIN-2）─────────────────────────

# gate 測試專用案：client_name + title 對造標記 + court 都有已知 PII token
_db.execute(
    "INSERT INTO matters (title, client_name, court, status, lead_attorney, pleading_case_id, "
    "has_local_agent, confidential) VALUES "
    "('G案請求返還借款（對造：測試對造商行）','測試甲','臺灣測試地方法院','open','C主辦','PLD-200',0,0)"
)
_MID_G = _db.execute("SELECT id FROM matters WHERE pleading_case_id='PLD-200'").fetchone()["id"]


def _mk_deadline_pii(matter_id=_MID_G, assignee="C承辦", needs_review=0, status="pending",
                     trigger_event="車禍侵權·知悉加害人為測試對造商行（委任人測試甲、另涉臺中地院）",
                     statutory_basis="臺灣測試地方法院命提出答辯狀通知（送達後20日內）",
                     calc_trace='["依據 臺灣測試地方法院命提出答辯狀通知 起算", "20日 依曆計算"]'):
    _db.execute(
        "INSERT INTO deadlines (matter_id, type, description, period_type, severity, trigger_event, "
        "service_type, service_base_date, statutory_days, statutory_basis, statutory_basis_version, "
        "statutory_deadline, internal_deadline, status, assignee, period_unit, period_value, "
        "needs_manual_review, calc_trace) VALUES (?, 'answer_civil','答辯狀期限','court_set','red',?,"
        "'normal','2026-07-02',20,?,?,'2026-07-22','2026-07-17',?,?,'day',NULL,?,?)",
        (matter_id, trigger_event, statutory_basis, "法院通知 現行", status, assignee, needs_review, calc_trace),
    )
    _db.commit()
    return _db.execute("SELECT MAX(id) m FROM deadlines").fetchone()["m"]


_did_g = _mk_deadline_pii()
with _configured(), _patch_urlopen(status=200, body={"id": 501}):
    _r = wb.writeback_deadline(_did_g)
_assert("H1 gate 後回寫成功", _r["status"] == "ok", str(_r))
_pl_body = _cap["body"]
_joined = json.dumps(_pl_body, ensure_ascii=False)
_assert("H2 已知當事人名被 strip", "測試甲" not in _joined, _joined[:200])
_assert("H3 對造名（title 對造標記抽取）被 strip", "測試對造商行" not in _joined, _joined[:200])
_assert("H4 已知法院名被 strip（含 statutory_basis）", "臺灣測試地方法院" not in _joined, _joined[:200])
_assert("H5 泛用法院 pattern 被 strip（臺中地院、非 matter 欄位）", "臺中地院" not in _joined, _joined[:200])
_assert("H6 calc_trace 內嵌原文一併被 strip", "測試" not in (_pl_body.get("calc_trace") or ""),
        str(_pl_body.get("calc_trace")))
_assert("H7 泛稱替換落地", "當事人" in _pl_body["trigger_event"] and "法院" in _pl_body["statutory_basis"],
        str(_pl_body.get("trigger_event")))
_assert("H8 豁免欄不動（assignee=§127 具名）", _pl_body["assignee"] == "C承辦", str(_pl_body.get("assignee")))
_assert("H9 title 仍為 type 標籤（answer_civil 已入 map）",
        _pl_body["title"] == "答辯狀提出期間（民事）", str(_pl_body.get("title")))
_row = _db.execute(
    "SELECT COUNT(*) c FROM interaction_log WHERE action='pleading_writeback_deidentified' AND target_id=?",
    (_did_g,),
).fetchone()
_assert("H10 gate 命中留 interaction_log（只記數量）", _row["c"] >= 1, str(_row["c"]))
_log_detail = _db.execute(
    "SELECT detail FROM interaction_log WHERE action='pleading_writeback_deidentified' AND target_id=? "
    "ORDER BY id DESC LIMIT 1", (_did_g,),
).fetchone()["detail"]
_assert("H11 log 不含被 strip 的名字", "測試甲" not in _log_detail and "測試對造商行" not in _log_detail, _log_detail)
# sme 側原值不動（律所自有庫、只在邊界剝）
_sme_te = _db.execute("SELECT trigger_event FROM deadlines WHERE id=?", (_did_g,)).fetchone()["trigger_event"]
_assert("H12 sme 側原值保留（只剝邊界）", "測試對造商行" in _sme_te, _sme_te)

# 乾淨 payload → gate 零命中、不留 deidentified log
_did_clean = _mk_deadline_pii(trigger_event="一審民事判決送達", statutory_basis="民訴§440",
                              calc_trace='["§440 20日", "依曆計算"]')
with _configured(), _patch_urlopen(status=200, body={"id": 502}):
    _r = wb.writeback_deadline(_did_clean)
_row = _db.execute(
    "SELECT COUNT(*) c FROM interaction_log WHERE action='pleading_writeback_deidentified' AND target_id=?",
    (_did_clean,),
).fetchone()
_assert("H13 乾淨 payload 零命中不留 log", _r["status"] == "ok" and _row["c"] == 0, f"{_r} c={_row['c']}")


# ───────────────────────── I：filed gate（F-P3-WIN-1）＋ un-file ─────────────────────────

_did_nr = _mk_deadline_pii(needs_review=1, trigger_event="法院命提出答辯狀通知送達",
                           statutory_basis="法院通知（20日）", calc_trace='["court_set 20日"]')
_out = svc.mark_deadline_filed(_did_nr, "測試者")
_st = _db.execute("SELECT status FROM deadlines WHERE id=?", (_did_nr,)).fetchone()["status"]
_assert("I1 needs_review 未覆核 → 不標記+警示", "未標記遞交" in _out and _st == "pending", _out[:80])
_out = svc.mark_deadline_filed(_did_nr, "測試者", confirm_unreviewed=True)
_row = _db.execute("SELECT status, filed_by FROM deadlines WHERE id=?", (_did_nr,)).fetchone()
_assert("I2 confirm_unreviewed=True → 標記成功", _row["status"] == "filed" and "已標記為已遞交" in _out, _out[:80])
_assert("I3 輸出帶未覆核警語", "遞交時仍未覆核" in _out, _out[:200])
_log = _db.execute(
    "SELECT detail FROM interaction_log WHERE action='deadline_filed' AND target_id=? ORDER BY id DESC LIMIT 1",
    (_did_nr,),
).fetchone()["detail"]
_assert("I4 稽核記「遞交時尚未覆核」", "遞交時尚未覆核" in _log, _log)
# 已覆核（needs_review=0）的正常路徑不受 gate 影響
_did_ok = _mk_deadline_pii(needs_review=0, trigger_event="一審判決送達", statutory_basis="民訴§440",
                           calc_trace='["§440"]')
_out = svc.mark_deadline_filed(_did_ok, "測試者")
_assert("I5 已覆核筆正常標記（gate 不誤傷）", "已標記為已遞交" in _out and "未覆核" not in _out, _out[:120])
# un-file
_out = svc.unmark_deadline_filed(_did_nr, reason="P3 探針誤標、實際未遞交", unfiled_by="測試者")
_row = _db.execute("SELECT status, filed_by, filed_at FROM deadlines WHERE id=?", (_did_nr,)).fetchone()
_assert("I6 un-file → pending+清 filed 欄", _row["status"] == "pending" and _row["filed_by"] is None
        and _row["filed_at"] is None, str(dict(_row)))
_log = _db.execute(
    "SELECT COUNT(*) c FROM interaction_log WHERE action='deadline_unfiled' AND target_id=?", (_did_nr,),
).fetchone()
_assert("I7 un-file 具名稽核留痕", _log["c"] == 1, str(_log["c"]))
_out = svc.unmark_deadline_filed(_did_nr, reason="再撤一次", unfiled_by="測試者")
_assert("I8 非 filed 不可撤", _out.startswith("ERROR") and "非已遞交" in _out, _out)
_out = svc.unmark_deadline_filed(_did_ok, reason="  ", unfiled_by="測試者")
_assert("I9 無 reason 拒絕", _out.startswith("ERROR") and "reason" in _out, _out)


# ───────────────────────── J：redact_deadline_field（PII 事後補救）─────────────────────────

_did_r = _mk_deadline_pii(needs_review=0)
_out = svc.redact_deadline_field(_did_r, find_text="測試對造商行", reason="e2e 補救演練", redacted_by="測試者")
_row = dict(_db.execute(
    "SELECT trigger_event, statutory_basis, calc_trace FROM deadlines WHERE id=?", (_did_r,),
).fetchone())
_assert("J1 redact 替換 trigger_event", "測試對造商行" not in _row["trigger_event"]
        and "當事人" in _row["trigger_event"], _row["trigger_event"])
_assert("J2 redact 回報命中欄位", "trigger_event×1" in _out, _out[:120])
_out2 = svc.redact_deadline_field(_did_r, find_text="臺灣測試地方法院", reason="法院名補救",
                                  redacted_by="測試者", replace_with="法院")
_row = dict(_db.execute(
    "SELECT statutory_basis, calc_trace FROM deadlines WHERE id=?", (_did_r,),
).fetchone())
_assert("J3 redact 法院名（statutory_basis+calc_trace 一次清）",
        "臺灣測試地方法院" not in _row["statutory_basis"] and "臺灣測試地方法院" not in _row["calc_trace"],
        str(_row))
_log = _db.execute(
    "SELECT detail FROM interaction_log WHERE action='deadline_redacted' AND target_id=? ORDER BY id LIMIT 1",
    (_did_r,),
).fetchone()["detail"]
_assert("J4 redact 稽核不含 find_text 本身", "測試對造商行" not in _log, _log)
_out = svc.redact_deadline_field(_did_r, find_text="不存在字串", reason="x", redacted_by="測試者")
_assert("J5 未命中明講不動", "未命中" in _out, _out[:80])
_out = svc.redact_deadline_field(_did_r, find_text="甲", reason="x", redacted_by="測試者")
_assert("J6 單字 find_text 拒絕", _out.startswith("ERROR"), _out[:80])
# redact 不限狀態（PII 補救不因已遞交而不可清）
_did_rf = _mk_deadline_pii(needs_review=0, status="filed")
_out = svc.redact_deadline_field(_did_rf, find_text="測試甲", reason="filed 筆補救", redacted_by="測試者")
_row = _db.execute("SELECT trigger_event FROM deadlines WHERE id=?", (_did_rf,)).fetchone()
_assert("J7 redact 對 filed 筆也生效", "測試甲" not in _row["trigger_event"], _row["trigger_event"])


# ───────────────────────── K：半配置可觀測性（F-P2-WIN-1(b)）─────────────────────────

_db.execute(
    "INSERT INTO matters (title, status, lead_attorney, pleading_case_id, has_local_agent, confidential) "
    "VALUES ('K案','open','C無token','PLD-300',0,0)"
)
_MID_K = _db.execute("SELECT id FROM matters WHERE pleading_case_id='PLD-300'").fetchone()["id"]
_did_k = _mk_deadline_pii(matter_id=_MID_K, assignee="C無token", needs_review=0,
                          trigger_event="判決送達", statutory_basis="民訴§440", calc_trace='["§440"]')
with _configured(), _patch_urlopen(status=200, body={"id": 900}):
    _r = wb.writeback_deadline(_did_k)
_assert("K1 無 token → skipped（不炸）", _r["status"] == "skipped", str(_r))
_row = _db.execute(
    "SELECT detail FROM interaction_log WHERE action='pleading_writeback_skipped' AND target_id=? "
    "ORDER BY id DESC LIMIT 1", (_did_k,),
).fetchone()
_assert("K2 半配置留一行 log 供排查", _row is not None and "選不到律師 token" in _row["detail"],
        str(_row and _row["detail"]))
# 純未配置：維持 inert、不留 log（與半配置區分）
_before = _db.execute("SELECT COUNT(*) c FROM interaction_log WHERE action='pleading_writeback_skipped'").fetchone()["c"]
_r = wb.writeback_deadline(_did_k)  # PLEADING_API_BASE 未設
_after = _db.execute("SELECT COUNT(*) c FROM interaction_log WHERE action='pleading_writeback_skipped'").fetchone()["c"]
_assert("K3 純未配置 inert 不留 log", _r["status"] == "not_configured" and _before == _after,
        f"{_r} {_before}->{_after}")


# ───────────────────────── L：type label 全量枚舉＋缺 label 即紅（F-P2-WIN-3）─────────────────────────

from shared.deadlines import (  # noqa: E402
    COURT_SET_PERIODS, LIMITATION_PERIODS, PROCEDURAL_CALENDAR_PERIODS, _GENERIC_TYPE_LABELS, type_label,
)

_all_codes = set()
for _t in (STATUTORY_PERIODS, COURT_SET_PERIODS, LIMITATION_PERIODS, PROCEDURAL_CALENDAR_PERIODS):
    _all_codes |= set(_t)
# 文件/實戰出現過的非種子代碼（新增代碼請一併入 map——本測試就是「缺 label 即紅」的守門）
_DOCUMENTED_GENERIC = {"answer", "brief", "answer_civil", "custom"}
_all_codes |= _DOCUMENTED_GENERIC
_missing = sorted(c for c in _all_codes if not type_label(c))
_assert("L1 全量 type 皆有 label（缺 label 即紅）", not _missing, str(_missing))
_assert("L2 泛型 map 涵蓋文件代碼", _DOCUMENTED_GENERIC <= set(_GENERIC_TYPE_LABELS) | _all_codes,
        str(_DOCUMENTED_GENERIC - set(_GENERIC_TYPE_LABELS)))
_assert("L3 未知代碼回 None（fallback 泛稱路徑）", type_label("zzz_unknown_9") is None, "")
_assert("L4 answer_civil 標籤正確", type_label("answer_civil") == "答辯狀提出期間（民事）",
        str(type_label("answer_civil")))


# ───────────────────────── M：豁免欄鎖安全＋gate 鑑別力（codex R1 HIGH/LOW）─────────────────────────

# M1 未知 type 含 PII → 正規化 custom、title=自訂期限、生代碼不外送
_db.execute(
    "INSERT INTO deadlines (matter_id, type, description, period_type, severity, trigger_event, "
    "service_type, service_base_date, statutory_days, statutory_basis, statutory_basis_version, "
    "statutory_deadline, internal_deadline, status, assignee, period_unit, period_value, "
    "needs_manual_review, calc_trace) VALUES (?, '測試甲專案期限','x','court_set','red','送達',"
    "'normal','2026-07-02',20,'法院通知','v','2026-07-22','2026-07-17','pending','C承辦','day',NULL,0,'[]')",
    (_MID_G,),
)
_db.commit()
_did_m1 = _db.execute("SELECT MAX(id) m FROM deadlines").fetchone()["m"]
with _configured(), _patch_urlopen(status=200, body={"id": 601}):
    _r = wb.writeback_deadline(_did_m1)
_j = json.dumps(_cap["body"], ensure_ascii=False)
_assert("M1a 未知 type 正規化為 custom", _cap["body"]["type"] == "custom", str(_cap["body"].get("type")))
_assert("M1b title=自訂期限（不帶生代碼）", _cap["body"]["title"] == "自訂期限", str(_cap["body"].get("title")))
_assert("M1c 未知 type 原字串（含 PII）不外送", "測試甲專案期限" not in _j and "測試甲" not in _j, _j[:200])

# M2 assignee 非在職員工（可能是誤填的當事人名）→ 不外送
_db.execute("UPDATE deadlines SET assignee='測試甲' WHERE id=?", (_did_m1,))
_db.commit()
with _configured(), _patch_urlopen(status=200, body={"id": 602}):
    _r = wb.writeback_deadline(_did_m1)
_assert("M2a 非員工 assignee 不外送", _cap["body"].get("assignee") is None, str(_cap["body"].get("assignee")))
_assert("M2b 在職員工 assignee 照送（對照）", True, "")  # H8 已驗 C承辦 照送
_db.execute("UPDATE deadlines SET assignee='C承辦' WHERE id=?", (_did_m1,))
_db.commit()

# M3 correspondence 的 doc_type 是 operator 可控字串 → 不豁免、照 gate 掃（已知當事人名被 strip）
_db.execute(
    "INSERT INTO pending_intakes (matter_id, matter_label, doc_type, service_base_date, "
    "stated_period_days, document_date, extracted_summary, status) "
    "VALUES (?, 'G案', '測試甲的判決書', '2026-07-01', 20, '2026-06-28', '摘要', 'awaiting')",
    (_MID_G,),
)
_db.commit()
_iid_m3 = _db.execute("SELECT MAX(id) m FROM pending_intakes").fetchone()["m"]
with _configured(), _patch_urlopen(status=200, body={"id": 603}):
    _r = wb.writeback_correspondence(_iid_m3)
_j = json.dumps(_cap["body"], ensure_ascii=False)
_assert("M3 correspondence doc_type 過 gate（當事人名被 strip）",
        _r["status"] == "ok" and "測試甲" not in _j and "當事人" in _cap["body"]["doc_type"], _j[:200])

# M4 長對造名（>20字、原 regex 截斷洞）→ 完整 strip
_db.execute(
    "INSERT INTO matters (title, client_name, status, lead_attorney, pleading_case_id, has_local_agent, confidential) "
    "VALUES ('M案（對造：超長名稱測試環球國際物流倉儲股份有限公司台中分公司）','某人','open','C主辦','PLD-400',0,0)"
)
_MID_M4 = _db.execute("SELECT id FROM matters WHERE pleading_case_id='PLD-400'").fetchone()["id"]
_did_m4 = _mk_deadline_pii(matter_id=_MID_M4,
                           trigger_event="通知（對造 超長名稱測試環球國際物流倉儲股份有限公司台中分公司 寄出）",
                           statutory_basis="民訴§440", calc_trace='["x"]')
with _configured(), _patch_urlopen(status=200, body={"id": 604}):
    _r = wb.writeback_deadline(_did_m4)
_j = json.dumps(_cap["body"], ensure_ascii=False)
_assert("M4 長對造名完整 strip（無截斷殘留）", "超長名稱測試" not in _j and "台中分公司" not in _j, _j[:250])

# M5 gate 鑑別力（mutation 抽查）：把 _gate_payload 換成 no-op、H2 類斷言必須會紅
_orig_gate = wb._gate_payload
wb._gate_payload = lambda payload, m: (payload, 0)
try:
    with _configured(), _patch_urlopen(status=200, body={"id": 605}):
        wb.writeback_deadline(_mk_deadline_pii())
    _leak = json.dumps(_cap["body"], ensure_ascii=False)
    _assert("M5 gate 拿掉時 PII 確實會漏（測試非假綠）", "測試對造商行" in _leak, _leak[:150])
finally:
    wb._gate_payload = _orig_gate


# ───────────────────────── 結果 ─────────────────────────
print("=" * 60)
print(f"Results: {passed} passed, {failed} failed out of {passed + failed}")
if failed:
    print("\nFAILURES:")
    for f in failures:
        print("  - " + f)
    sys.exit(1)
print("\nALL TESTS PASSED")
