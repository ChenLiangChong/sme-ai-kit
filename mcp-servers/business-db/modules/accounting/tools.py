"""Accounting tools — @mcp.tool 薄殼，業務邏輯在 service.py、SQL 在 repository.py。

Phase 2.10 三層化（套 P2.1 attachments pattern、含 codex spot-check 三點警告處理）。
"""
from shared.mcp_instance import mcp

from . import service


@mcp.tool()
def record_transaction(
    type: str,
    amount: float,
    category: str,
    description: str = "",
    transaction_date: str = "",
    related_customer_id: int = 0,
    related_order_id: int = 0,
    related_invoice: str = "",
    business_unit: str = "",
    payment_status: str = "paid",
    due_date: str = "",
    recorded_by: str = "",
    approved_id: int = 0,
) -> str:
    """記錄一筆收入或支出。

    Args:
        type: 類型 — income（收入）| expense（支出）
        amount: 金額（正數）
        category: 分類（如 sales_revenue, rent, supplies, salary, marketing, meals, transportation, other）
        description: 說明
        transaction_date: 交易日期（YYYY-MM-DD），空白=今天
        related_customer_id: 關聯客戶 ID（可選）
        related_order_id: 關聯訂單 ID（可選，用於追蹤預收款或訂單付款）
        related_invoice: 關聯發票號碼（可選）
        business_unit: 所屬事業體（如 product, design, content），留空=不分
        payment_status: 付款狀態 — paid（已付）| pending（待收/待付）| overdue（逾期）
        due_date: 帳期到期日（YYYY-MM-DD），B2B 應收應付用
        recorded_by: 記錄者
        approved_id: 已核准的審核 ID（繞過門檻檢查）
    """
    return service.record_transaction(
        type_=type,
        amount=amount,
        category=category,
        description=description,
        transaction_date=transaction_date,
        related_customer_id=related_customer_id,
        related_order_id=related_order_id,
        related_invoice=related_invoice,
        business_unit=business_unit,
        payment_status=payment_status,
        due_date=due_date,
        recorded_by=recorded_by,
        approved_id=approved_id,
    )


@mcp.tool()
def list_transactions(
    start_date: str = "",
    end_date: str = "",
    type: str = "",
    category: str = "",
    business_unit: str = "",
    related_order_id: int = 0,
    limit: int = 30,
) -> str:
    """查詢收支記錄。

    Args:
        start_date: 起始日期（YYYY-MM-DD），空白=本月 1 號（指定 related_order_id 時不限日期）
        end_date: 結束日期（YYYY-MM-DD），空白=今天
        type: 篩選類型 — income | expense，空白=全部
        category: 篩選分類，空白=全部
        business_unit: 篩選事業體（留空=全部）
        related_order_id: 篩選關聯訂單 ID（0=不篩選）
        limit: 最多顯示幾筆
    """
    return service.list_transactions(
        start_date=start_date,
        end_date=end_date,
        type_=type,
        category=category,
        business_unit=business_unit,
        related_order_id=related_order_id,
        limit=limit,
    )


@mcp.tool()
def monthly_summary(year_month: str = "", business_unit: str = "") -> str:
    """月度收支彙總。

    Args:
        year_month: 年月（YYYY-MM），空白=本月
        business_unit: 篩選事業體（留空=全部合計）
    """
    return service.monthly_summary(year_month=year_month, business_unit=business_unit)


@mcp.tool()
def get_transaction(transaction_id: int) -> str:
    """查看單筆帳目完整資訊（含關聯客戶／訂單／發票、付款狀態）。

    Args:
        transaction_id: 帳目 ID
    """
    return service.get_transaction(transaction_id)


@mcp.tool()
def delete_transaction(transaction_id: int, reason: str, actor_user_id: str = "") -> str:
    """刪除一筆帳目（需填原因，會留下審計紀錄）。

    Args:
        transaction_id: 帳目 ID
        reason: 刪除原因（必填）
        actor_user_id: 操作者 LINE user_id（用於權限驗證，留空=系統呼叫，不驗證）
    """
    return service.delete_transaction(
        transaction_id=transaction_id, reason=reason, actor_user_id=actor_user_id
    )


@mcp.tool()
def update_transaction(
    transaction_id: int,
    category: str = "",
    description: str = "",
    business_unit: str = "__SKIP__",
    payment_status: str = "",
    due_date: str = "",
    related_order_id: int = -1,
    related_customer_id: int = -1,
) -> str:
    """修正帳目欄位（不含金額，金額修正請刪除重建）。

    Args:
        transaction_id: 帳目 ID
        category: 新分類（留空=不改）
        description: 新說明（留空=不改）
        business_unit: 新事業體（'__SKIP__'=不改，空字串=清除）
        payment_status: 新付款狀態 paid|pending|overdue（留空=不改）
        due_date: 新到期日 YYYY-MM-DD（留空=不改）
        related_order_id: 關聯訂單 ID（-1=不改，0=清除）
        related_customer_id: 關聯客戶 ID（-1=不改，0=清除）
    """
    return service.update_transaction(
        transaction_id=transaction_id,
        category=category,
        description=description,
        business_unit=business_unit,
        payment_status=payment_status,
        due_date=due_date,
        related_order_id=related_order_id,
        related_customer_id=related_customer_id,
    )


@mcp.tool()
def check_overdue(business_unit: str = "") -> str:
    """檢查所有逾期帳款。自動判斷：到期日已過且未全額付清。

    Args:
        business_unit: 篩選特定事業體（如 brand_c, brand_d），留空=全部
    """
    return service.check_overdue(business_unit)


@mcp.tool()
def record_payment(
    transaction_id: int, amount: float, notes: str = "", actor_user_id: str = ""
) -> str:
    """記錄一筆付款（部分付款或全額付清）。

    Args:
        transaction_id: 帳目 ID
        amount: 本次付款金額
        notes: 備註
        actor_user_id: 操作者 LINE user_id（用於權限驗證，留空=系統呼叫，不驗證）
    """
    return service.record_payment(
        transaction_id=transaction_id,
        amount=amount,
        notes=notes,
        actor_user_id=actor_user_id,
    )
