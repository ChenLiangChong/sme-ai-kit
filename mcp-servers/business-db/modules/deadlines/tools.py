"""Deadlines tools — @mcp.tool 薄殼，業務邏輯在 service.py、計算在 shared/deadlines.py。

legal-admin vertical：案件（matters）+ 時限（deadlines）。
時限天數一律 service 層確定性計算、附 statutory_basis 法條依據（反捏造、絕不 LLM 心算）。
"""
from shared.mcp_instance import mcp

from . import service


@mcp.tool()
def create_matter(
    title: str,
    matter_no: str = "",
    client_name: str = "",
    practice_area: str = "",
    court: str = "",
    court_case_no: str = "",
    stage: str = "",
    lead_attorney: str = "",
    has_local_agent: int = 1,
    confidential: int = 0,
    created_by: str = "",
) -> str:
    """建立案件（matter）。律所案件主檔，是時限（deadline）的父鍵。

    Args:
        title: 案由（必填，如「○○股份有限公司請求給付貨款」）
        matter_no: 事務所內部案號（如 2026-民-001），唯一
        client_name: 委任人名字（輕量、不做完整 CRM）
        practice_area: 法律領域 — civil/criminal/admin/family/ip/labor/non_litigation
        court: 繫屬法院（如「臺灣臺北地方法院」）
        court_case_no: 法院案號（如「112年度訴字第XXX號」）
        stage: 審級 — first_instance/second_instance/third_instance/execution
        lead_attorney: 主辦律師
        has_local_agent: 是否有住法院所在地之代理人（§162但書，律所自辦常為 1=在途歸零）
        confidential: 是否機密案件（1=僅機密/全權限層可見）
        created_by: 建立者
    """
    return service.create_matter(
        title=title,
        matter_no=matter_no,
        client_name=client_name,
        practice_area=practice_area,
        court=court,
        court_case_no=court_case_no,
        stage=stage,
        lead_attorney=lead_attorney,
        has_local_agent=has_local_agent,
        confidential=confidential,
        created_by=created_by,
    )


@mcp.tool()
def list_matters(status: str = "", lead_attorney: str = "", limit: int = 20) -> str:
    """列出案件。

    Args:
        status: 篩選狀態（open/on_hold/closed/archived），空白=全部
        lead_attorney: 篩選主辦律師
        limit: 最多顯示幾筆
    """
    return service.list_matters(status=status, lead_attorney=lead_attorney, limit=limit)


@mcp.tool()
def get_matter(matter_id: int) -> str:
    """查看單筆案件完整資訊（含該案所有時限摘要）。

    Args:
        matter_id: 案件 ID
    """
    return service.get_matter(matter_id)


@mcp.tool()
def find_matter_by_party(party_name: str, limit: int = 20) -> str:
    """用當事人/委任人名字查案件（模糊比對 client_name，也比對案由/案號）。

    例：「林先生的案子是哪件」「幫我找王曉明的案件」。
    進行中（open）案件排前面。

    Args:
        party_name: 當事人/委任人名字（或案由/案號關鍵字）
        limit: 最多顯示幾筆
    """
    return service.find_matter_by_party(party_name=party_name, limit=limit)


@mcp.tool()
def create_deadline(
    matter_id: int,
    type: str,
    trigger_event: str,
    service_base_date: str,
    description: str = "",
    service_type: str = "normal",
    statutory_days: int = 0,
    statutory_basis: str = "",
    statutory_basis_version: str = "",
    period_type: str = "",
    severity: str = "",
    has_local_agent: int = -1,
    in_transit_days: int = 0,
    court_region: str = "",
    party_region: str = "",
    buffer_days: int = 1,
    assignee: str = "",
    assignee_line_user_id: str = "",
    escalation_lead_days: str = "",
    created_by: str = "",
) -> str:
    """建立時限（deadline）並由 service 層確定性計算法定/內部雙日期。

    天數絕不 LLM 心算：service 呼叫 compute_deadline 純函式（民法§120翌日起算 + 法定期間 + 在途
    + 民法§122末日順延 − buffer），每筆附 statutory_basis 法條依據（反捏造）、calc_trace 供律師覆核。

    若 type 在常用法定期間種子內（appeal_civil/abjection_civil/appeal_criminal/abjection_criminal/
    appeal_admin/appeal_family/appeal_reason/petition_appeal/payment_order_objection），會自動回填
    statutory_days / statutory_basis / period_type / description（律師仍可覆寫）。
    type 不在種子表 → **必須**手動帶 statutory_days + statutory_basis + period_type，否則擋下。

    Args:
        matter_id: 所屬案件 ID（必填）
        type: 時限類型（種子 key 或 custom）
        trigger_event: 起算事件（如「一審判決送達」「裁定送達」「最後登報」）（必填）
        service_base_date: 送達/寄存/公告基準日 YYYY-MM-DD（必填，律師人工認定的事實）
        description: 時限描述（種子 type 可省、自動填）
        service_type: 送達類型 — normal(一般)/registered_deposit(寄存+10)/public_domestic(公示境內+20)/
            public_foreign(公示外國+60)/commissioned(囑託，需人工複核)
        statutory_days: 法定日數（種子 type 自動填；非種子必帶）
        statutory_basis: 法條依據（種子 type 自動填；非種子必帶，反捏造鐵律）
        statutory_basis_version: 法規版本（如「刑訴§349 110.06.16修正版」）
        period_type: peremptory(不變期間)/statutory(通常法定)/court_set(裁定期間)/directory(訓示)
        severity: red/orange/grey（空白=依 period_type 推導）
        has_local_agent: 是否有當地代理人（-1=沿用案件設定；§162但書、True→在途歸零）
        in_transit_days: 手動指定在途天數（MVP 第二條路；0=不指定走 has_local_agent/查表）
        court_region: 受訴法院所在區域代碼（如 'taipei'/'kinmen'）—— 無當地代理人且未手動指定 in_transit_days
            時，配 party_region 查 transit_period 表得在途天數（民訴§162）；查不到→需人工複核、在途暫 0
        party_region: 當事人住居地區域代碼（如 'kinmen'/'overseas_asia'）—— 同上，與 court_region 成對查表
        buffer_days: 內部安全緩衝天數（內部期限=法定期限−buffer，預設 1）
        assignee: 負責律師（空白=沿用案件主辦）
        assignee_line_user_id: 承辦律師 LINE user_id（MVP「全所一份」提醒下不作收件對象、保留供未來 per-assignee 分送；收件人一律走 boss/全所 coalesce）
        escalation_lead_days: T-N 提醒節點 JSON（如「[14,7,3,1,0]」；空白=依 severity 預設）
        created_by: 建立者
    """
    return service.create_deadline(
        matter_id=matter_id,
        type=type,
        description=description,
        trigger_event=trigger_event,
        service_base_date=service_base_date,
        service_type=service_type,
        statutory_days=statutory_days,
        statutory_basis=statutory_basis,
        statutory_basis_version=statutory_basis_version,
        period_type=period_type,
        severity=severity,
        has_local_agent=has_local_agent,
        in_transit_days=in_transit_days,
        court_region=court_region,
        party_region=party_region,
        buffer_days=buffer_days,
        assignee=assignee,
        assignee_line_user_id=assignee_line_user_id,
        escalation_lead_days=escalation_lead_days,
        created_by=created_by,
    )


@mcp.tool()
def list_deadlines(
    matter_id: int = 0, status: str = "", assignee: str = "", limit: int = 20
) -> str:
    """列出時限（含內部/法定雙日期、法條依據）。

    Args:
        matter_id: 篩選某案件（0=全部）
        status: 篩選狀態（pending/filed/extended/missed/cancelled），空白=全部
        assignee: 篩選負責律師
        limit: 最多顯示幾筆
    """
    return service.list_deadlines(
        matter_id=matter_id, status=status, assignee=assignee, limit=limit
    )


@mcp.tool()
def list_upcoming_deadlines(
    assignee: str = "", within_days: int = 0, limit: int = 50
) -> str:
    """列出所有待處理（pending）時限，按內部期限（internal_deadline）升冪——最急在前。

    供每日彙整（「今天有哪些時限要盯」）與律師個人查詢。
    每筆並陳內部期限（盯這個）與法定期限（底線）+ 法條依據；已逾內部期限者特別標示。

    Args:
        assignee: 篩選負責律師（空白=全部）
        within_days: 只看內部期限在「今起 N 個日曆日內」的（含已逾期；0=全部 pending）
        limit: 最多顯示幾筆
    """
    return service.list_upcoming_deadlines(
        assignee=assignee, within_days=within_days, limit=limit
    )


@mcp.tool()
def get_deadline(deadline_id: int) -> str:
    """查看單筆時限完整資訊（含 calc_trace 計算軌跡 + 逾期救濟備援）。

    Args:
        deadline_id: 時限 ID
    """
    return service.get_deadline(deadline_id)


@mcp.tool()
def mark_deadline_filed(deadline_id: int, filed_by: str = "") -> str:
    """標記時限已遞交（書狀已送出）→ 狀態轉 filed，cron 不再提醒。

    Args:
        deadline_id: 時限 ID
        filed_by: 遞交者
    """
    return service.mark_deadline_filed(deadline_id=deadline_id, filed_by=filed_by)
