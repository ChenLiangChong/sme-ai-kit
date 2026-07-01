"""薄 pleading REST client（Task C / M2）— sme→pleading 單向回寫的傳輸層。

契約見 bridge KB `pleading_rest_contract`（frozen v4，pleading_coder 維護、已讀 api.py 驗證）。
本檔只做「帶身分的 HTTP 轉 REST」這一層薄殼、不含任何業務判斷：

- **auth = per-request `Cookie: pm_session=<律師個人 token>`**（§127 當責律師；非 service account）。
  （裸 Bearer 是 MCP adapter :8210 那條的傳輸層、與此 REST 直連無關。）
- **base url = env `PLEADING_API_BASE`**（未設 = 整合未配置 = inert；由 writeback 層判斷、client 建構時擋下）。
- **stdlib urllib**（無新依賴、鏡像 flush_escalations.py 的 HTTP 殼）。純 HTTP、無 TLS（自簽=exe
  code-signing、與 REST 呼叫無關）。
- 錯誤一律轉成**具名例外**，writeback 層 graceful degrade、**絕不讓回寫炸掉引擎**。

去識別化：本 client 只轉發 caller 給的欄位、不看內容；當事人姓名 / 來文機關(issuer) / 完整主旨(subject)
一律由 caller 不帶（None）。詳見 references/pleading-sync.md。
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

# 回寫是 best-effort 鏡像、不可長時間卡住 sme tool（引擎/提醒不等它）。
DEFAULT_TIMEOUT_SEC = 8


class PleadingError(Exception):
    """pleading 回寫錯誤基類（writeback 層一律吞、轉成結構化結果、不外拋炸引擎）。"""


class PleadingNotConfigured(PleadingError):
    """整合未配置（PLEADING_API_BASE 未設）→ inert、整段回寫略過。"""


class PleadingAuthError(PleadingError):
    """401：該律師 token 失效 / 撤銷 → 略過本次、標記請該律師重新 provision。"""


class PleadingNotFound(PleadingError):
    """404：對應 pleading 案件不存在（被刪）→ 建議 link_matter_pleading 解綁、回純單機。"""


class PleadingUnreachable(PleadingError):
    """連線失敗 / timeout（exe 沒起 / 防火牆 / 網路）→ 略過、pleading 鏡像暫落後。"""


class PleadingHTTPError(PleadingError):
    """其他 4xx / 5xx。**不帶遠端 body**——response body 可能回顯 request 內容 / debug / PII，
    只留 status code（codex Task C R1 MED：防遠端 body 經 note 洩漏到 operator）。"""

    def __init__(self, status: int):
        self.status = status
        super().__init__(f"pleading REST {status}")


def pleading_base_url() -> str:
    """回 PLEADING_API_BASE（去尾斜線）；未設回 ''（=整合未配置）。"""
    return os.environ.get("PLEADING_API_BASE", "").strip().rstrip("/")


def integration_configured() -> bool:
    """整合是否已配置（有 base url）。未配置 → writeback 層 inert 略過、不報錯不提醒。"""
    return bool(pleading_base_url())


def _prune_none(payload: dict) -> dict:
    """只送有值的欄（契約：None 略過）。空字串保留（是有意義的清空、非未提供）。"""
    return {k: v for k, v in (payload or {}).items() if v is not None}


class PleadingClient:
    """一個 client 綁一把律師 token（§127 當責身分）；每次請求 per-request 塞 Cookie。"""

    def __init__(self, token: str, *, base_url: str | None = None, timeout: int = DEFAULT_TIMEOUT_SEC):
        self._base = (base_url if base_url is not None else pleading_base_url()).rstrip("/")
        self._token = (token or "").strip()
        self._timeout = timeout
        if not self._base:
            raise PleadingNotConfigured("PLEADING_API_BASE 未設（整合未配置）")

    def _request(self, method: str, path: str, payload: dict | None = None):
        url = f"{self._base}{path}"
        headers = {"Accept": "application/json"}
        if self._token:
            # §127：per-request Cookie 帶該律師個人 token（非裸 Bearer）。
            headers["Cookie"] = f"pm_session={self._token}"
        data = None
        if payload is not None:
            data = json.dumps(_prune_none(payload), ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read()
                if not raw:
                    return None
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as e:
            # 遠端 response body 可能回顯 request 內容 / debug / PII → 一律不帶進例外訊息
            # （防洩漏到 operator note；codex Task C R1 MED）。只依 status code 分類。
            if e.code == 401:
                raise PleadingAuthError("token 失效（401）") from None
            if e.code == 404:
                raise PleadingNotFound("案件不存在（404）") from None
            raise PleadingHTTPError(e.code) from None
        except urllib.error.URLError as e:
            # 連線層失敗（DNS / refused / timeout）→ 統一 Unreachable
            raise PleadingUnreachable(str(getattr(e, "reason", e))) from None
        except (TimeoutError, OSError) as e:
            raise PleadingUnreachable(str(e)) from None

    # ── 末日 ──────────────────────────────────────────────
    def upsert_deadline(self, case_id, payload: dict):
        """POST /api/cases/{case_id}/deadlines → 201，回 `_deadline_view`（含 pleading row `id`）。
        external_ref 非空 → 以 (external_system, external_ref) 冪等 merge upsert（只動有給的欄）。"""
        return self._request("POST", f"/api/cases/{_seg(case_id)}/deadlines", payload)

    def get_deadlines(self, case_id):
        return self._request("GET", f"/api/cases/{_seg(case_id)}/deadlines")

    # ── 收發文 ────────────────────────────────────────────
    def upsert_correspondence(self, case_id, payload: dict):
        return self._request("POST", f"/api/cases/{_seg(case_id)}/correspondence", payload)

    def get_correspondence(self, case_id):
        return self._request("GET", f"/api/cases/{_seg(case_id)}/correspondence")

    # ── 探活 ──────────────────────────────────────────────
    def whoami(self):
        """GET /api/me（token 探活：回 authenticated/kind/username…；本機略過回 kind:local）。"""
        return self._request("GET", "/api/me")


def _seg(case_id) -> str:
    """pleading_case_id 是 sme 側視為不透明的 TEXT；url-quote 成安全的 path segment。"""
    return urllib.parse.quote(str(case_id), safe="")


def token_is_live(token: str, *, base_url: str | None = None, timeout: int = DEFAULT_TIMEOUT_SEC) -> bool:
    """探活 callback（餵 select_pleading_token 的 verify）：token 打 whoami 成功=True。
    連不上 / 未配置一律 False（不阻塞、由上層 graceful skip）。**絕不拋**。"""
    try:
        PleadingClient(token, base_url=base_url, timeout=timeout).whoami()
        return True
    except Exception:
        return False
