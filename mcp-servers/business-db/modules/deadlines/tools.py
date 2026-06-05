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
    stated_period_days: int = 0,
    document_date: str = "",
    assignee: str = "",
    assignee_line_user_id: str = "",
    escalation_lead_days: str = "",
    created_by: str = "",
    confirm_intake_id: int = 0,
    period_unit: str = "day",
    period_value: int = 0,
) -> str:
    """建立時限（deadline）並由 service 層確定性計算法定/內部雙日期。

    天數絕不 LLM 心算：service 呼叫 compute_deadline 純函式（民法§120翌日起算 + 法定期間 + 在途
    + 民法§122末日順延 − buffer），每筆附 statutory_basis 法條依據（反捏造）、calc_trace 供律師覆核。

    若 type 在常用法定期間種子內（appeal_civil/abjection_civil/appeal_criminal/abjection_criminal/
    appeal_admin/appeal_family/appeal_reason/petition_appeal/payment_order_objection），會自動回填
    statutory_days / statutory_basis / period_type / description（律師仍可覆寫）。
    type 不在種子表 → **必須**手動帶 statutory_days + statutory_basis + period_type，否則擋下。

    裁定期間類（type='correction' 限期補正等）：自動帶 period_type=court_set / severity=orange / 描述 /
    觸發語，但 statutory_days **絕不回填**——裁定期間是法院在裁定當下載明（「於本裁定送達後 ○ 日內補正」），
    律師必須讀裁定填 ○ 日；statutory_basis 填補正裁定文號（非法條）。凡最終 period_type=court_set 一律
    強制 needs_manual_review（天數純人讀、無固定法定種子可交叉驗證＝反捏造風險最高，須律師覆核）。

    消滅時效類（type='limitation' 或 statute_125/126/127/197_2y/197_10y、period_unit='year'/'month'）：
    與訴訟期間根本不同——期間是「年/月」（用 period_value 非 statutory_days）、依民§121 曆法（相當日
    之前一日/無相當日→該月末日）+ §123 連續依曆，**不可硬轉天數**（閏年）；起算點是民§128「請求權可
    行使時」＝法律判斷（非送達日這種確定事實）→ service_base_date 填「請求權可行使日」、**一律強制人工
    複核**；無在途、無送達加算、不適用回復原狀。§197 侵權是「雙時鐘」（知悉起2年 statute_197_2y + 行為
    時起10年 statute_197_10y）→ 各建一筆、各帶不同起算日（不自動雙建）。statute_* 種子自動回填
    period_unit/period_value/period_type/basis/描述；起算日仍須律師給。

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
        stated_period_days: 判決書「上訴教示」所載期間天數（安全網，0=未提供）。律師確認送達日時
            一併把判決書教示的天數抓回——引擎會與採用的 statutory_days 交叉比對，不符即標需人工複核
            （反捏造：引擎不靜默蓋過判決書教示；可揪出法定期間判斷有誤或屬特別期間）
        document_date: 文書作成日（判決/裁定日 YYYY-MM-DD，法版檢核用，空=未提供）。法版適用版本依
            「文書作成日」而非送達日（舊判決可能修法後才送達）——刑事案件、再審/回復原狀翻出的舊案
            尤其要帶；未提供則引擎以送達日近似並於 calc_trace 標明
        assignee: 負責律師（空白=沿用案件主辦）
        assignee_line_user_id: 承辦律師 LINE user_id（MVP「全所一份」提醒下不作收件對象、保留供未來 per-assignee 分送；收件人一律走 boss/全所 coalesce）
        escalation_lead_days: T-N 提醒節點 JSON（如「[14,7,3,1,0]」；空白=依 severity 預設）
        created_by: 建立者
        confirm_intake_id: 對應的「待確認暫存」id（先 stage_deadline_intake 暫存、人確認後入庫時帶回）。
            >0 時本次入庫成功會同 tx 關閉該待確認跟催 backlog（不再被 scan_unconfirmed_intake 催）；
            0=不對位（無暫存的直接入庫）。查無/已非待確認不擋入庫、僅在回覆註記
        period_unit: 期間單位 day（預設、日數路徑、讀 statutory_days）/ year / month（消滅時效曆法路徑、
            讀 period_value、依民§121）。statute_* 種子會自動帶；自訂消滅時效須明確指定 year/month
        period_value: 年/月期間數（period_unit=year/month 時必填且 > 0，如 §125=15、§126=5、§127/§197=2）。
            period_unit=day 時忽略（期間數仍讀 statutory_days）
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
        stated_period_days=stated_period_days,
        document_date=document_date,
        assignee=assignee,
        assignee_line_user_id=assignee_line_user_id,
        escalation_lead_days=escalation_lead_days,
        created_by=created_by,
        confirm_intake_id=confirm_intake_id,
        period_unit=period_unit,
        period_value=period_value,
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


@mcp.tool()
def mark_deadline_calendared(
    deadline_id: int,
    calendar_event_id: str,
    calendar_provider: str = "",
    marked_by: str = "",
) -> str:
    """回填時限的外部行事曆對位（SPEC「寫兩處」：時限確認後寫進事務所慣用行事曆，存回 event_id）。

    calendar-agnostic 流程：時限確認入庫後，agent 用現場配置的行事曆 MCP（Google Calendar 或律所
    慣用的其他行事曆）建立 event（去識別化：只放「案件代號 + 期限類型 + 日期」、不放當事人名/案由），
    再用本 tool 把回傳的 event_id 存回時限——供每日彙整去重、後續更新對位。不綁死特定行事曆軟體。

    Args:
        deadline_id: 時限 ID
        calendar_event_id: 外部行事曆建立 event 後回傳的 id（必填）
        calendar_provider: 行事曆來源標記（如 'google'/'internal'）
        marked_by: 操作者
    """
    return service.mark_deadline_calendared(
        deadline_id=deadline_id,
        calendar_event_id=calendar_event_id,
        calendar_provider=calendar_provider,
        marked_by=marked_by,
    )


@mcp.tool()
def stage_deadline_intake(
    extracted_summary: str,
    matter_id: int = 0,
    matter_label: str = "",
    doc_type: str = "",
    service_base_date: str = "",
    stated_period_days: int = 0,
    document_date: str = "",
    submitted_by: str = "",
) -> str:
    """把『抽出但尚未確認』的時限事實暫存成可掃描的待確認 backlog（時限收件流程步驟2：把抽出的事實
    推回 LINE 請人一鍵確認的「當下」呼叫，不要等人回了才存）。

    為什麼要存：核心 loop 刻意「一鍵確認才入」把人擋中間（律師業必須人擋中間）。副作用＝丟了檔、
    AI 推確認、人忘了回 → 時限沒進 deadlines → 一般掃描掃不到 → 隱形漏掉（漏期＝執業過失）。
    本暫存讓「待確認」變成 scan_unconfirmed_intake.py 能跟催的 backlog、不再靜默漏掉。

    只存事實、不算天數、不建 deadline。人確認後請呼叫 create_deadline(..., confirm_intake_id=<本 id>)
    入庫（引擎才確定性算雙日期）；確定不算了用 resolve_deadline_intake(<id>, action='discarded')。

    Args:
        extracted_summary: 一行人話摘要（推回 LINE 請人確認的那條，如「王案一審民事判決 6/1 送達、教示20日」）（必填）
        matter_id: 所屬案件 ID（0=案件還沒建、可之後補；給了會驗存在 + 機密軸 gate）
        matter_label: 顯示用案件標籤快照（案號 / 案件代號 / 案由；去識別化、勿放當事人姓名）
        doc_type: 文書類型（人話或 create_deadline 的 type 代碼，如 appeal_civil）
        service_base_date: 抽出的送達日 YYYY-MM-DD（事實、未經引擎計算）
        stated_period_days: 判決書上訴教示所載天數（事實；0=未提供）
        document_date: 文書作成日（裁判日 YYYY-MM-DD；空=未提供）
        submitted_by: 誰丟的檔 / 誰要算（逾時跟催時點名回頭催誰）
    """
    return service.stage_deadline_intake(
        matter_id=matter_id,
        matter_label=matter_label,
        doc_type=doc_type,
        service_base_date=service_base_date,
        stated_period_days=stated_period_days,
        document_date=document_date,
        extracted_summary=extracted_summary,
        submitted_by=submitted_by,
    )


@mcp.tool()
def resolve_deadline_intake(
    intake_id: int, action: str = "discarded", note: str = "", resolved_by: str = ""
) -> str:
    """收掉待確認暫存（停止 scan_unconfirmed_intake 跟催）。

    一般「確認入庫」請改走 create_deadline(confirm_intake_id=...) 自動關閉、不必呼叫本工具；
    本工具給「不入庫就收掉」用：action='discarded'（誤判 / 重複 / 不算了）或
    'confirmed'（已用別的途徑入庫、僅標記關閉、不連 deadline）。

    Args:
        intake_id: 待確認暫存 ID
        action: 'discarded'（捨棄、預設）或 'confirmed'（已另行入庫）
        note: 收掉原因備註（落稽核 log）
        resolved_by: 操作者
    """
    return service.resolve_deadline_intake(
        intake_id=intake_id, action=action, note=note, resolved_by=resolved_by
    )


@mcp.tool()
def list_pending_intakes(limit: int = 50) -> str:
    """列出待確認（尚未入庫）的時限暫存（最舊在前、附等待時數），供律師主動查 backlog。

    只列抽出的事實（送達日 / 文書類型 / 教示天數 / 等待時數）——刻意不端出引擎 computed deadline
    （待確認階段根本還沒算、不存在權威日期）。確認入庫請帶 create_deadline(confirm_intake_id=)。

    Args:
        limit: 最多顯示幾筆（預設 50）
    """
    return service.list_pending_intakes(limit=limit)
