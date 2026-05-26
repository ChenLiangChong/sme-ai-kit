"""HR tools — @mcp.tool 薄殼，業務邏輯在 service.py、SQL 在 repository.py。

Phase 2.7 三層化（套 P2.1 attachments pattern）。
"""
from shared.mcp_instance import mcp

from . import service


# ============================================================
# 員工管理（4 工具）
# ============================================================

@mcp.tool()
def register_employee(
    name: str,
    role: str = "staff",
    department: str = "",
    line_user_id: str = "",
    permissions: str = "basic",
    phone: str = "",
    business_units: str = "",
) -> str:
    """註冊員工並綁定 LINE 帳號。

    Args:
        name: 員工姓名
        role: 角色 — boss | manager | staff
        department: 部門
        line_user_id: LINE User ID（用於綁定 LINE 身份）
        permissions: 權限等級 — admin | manager | basic
        phone: 聯絡電話
        business_units: 所屬事業體（逗號分隔，如 'brand_d,distribution'）。留空=全部事業體
    """
    return service.register_employee(
        name=name,
        role=role,
        department=department,
        line_user_id=line_user_id,
        permissions=permissions,
        phone=phone,
        business_units=business_units,
    )


@mcp.tool()
def update_employee(
    employee_id: int,
    name: str = "",
    role: str = "",
    department: str = "",
    line_user_id: str = "__SKIP__",
    permissions: str = "",
    phone: str = "",
    business_units: str = "__SKIP__",
    active: int = -1,
    notes: str = "",
) -> str:
    """更新員工資料。只傳入要修改的欄位。

    Args:
        employee_id: 員工 ID（必填）
        name: 新姓名
        role: 新角色 — boss | manager | staff
        department: 新部門
        line_user_id: LINE User ID（傳空字串清除綁定）
        permissions: 新權限 — admin | manager | basic | none
        phone: 新電話
        business_units: 所屬事業體（逗號分隔，如 'brand_d,distribution'）。傳空字串清除（=全部事業體）
        active: 1=在職 0=離職
        notes: 備註
    """
    return service.update_employee(
        employee_id=employee_id,
        name=name,
        role=role,
        department=department,
        line_user_id=line_user_id,
        permissions=permissions,
        phone=phone,
        business_units=business_units,
        active=active,
        notes=notes,
    )


@mcp.tool()
def lookup_employee(name_or_line_id: str) -> str:
    """查詢員工資訊（用姓名或 LINE User ID）。

    Args:
        name_or_line_id: 員工姓名或 LINE User ID
    """
    return service.lookup_employee(name_or_line_id)


@mcp.tool()
def list_employees(active_only: bool = True) -> str:
    """列出所有員工。

    Args:
        active_only: True 只顯示在職員工
    """
    return service.list_employees(active_only)


# ============================================================
# 外包夥伴管理（5 工具）
# ============================================================

@mcp.tool()
def register_partner(
    name: str,
    role: str = "",
    line_user_id: str = "",
    phone: str = "",
    email: str = "",
    business_units: str = "",
    payment_terms: str = "",
    notes: str = "",
) -> str:
    """註冊外包夥伴（非員工、非客戶的協作者，如剪輯師、攝影、社群發布等）。

    Args:
        name: 夥伴姓名或公司名
        role: 職責（自由文字，如「影片剪輯」「社群發布」「外景拍攝」）
        line_user_id: LINE User ID（用於 LINE 身份辨識）
        phone: 電話
        email: Email
        business_units: 服務的事業體（逗號分隔，如 'brand_e,brand_a'；留空=全部）
        payment_terms: 付款條件（「月結」「案件計酬」「預付」等自由文字）
        notes: 備註（如多 OA LINE user_id、合約細節、費用標準）
    """
    return service.register_partner(
        name=name,
        role=role,
        line_user_id=line_user_id,
        phone=phone,
        email=email,
        business_units=business_units,
        payment_terms=payment_terms,
        notes=notes,
    )


@mcp.tool()
def update_partner(
    partner_id: int,
    name: str = "",
    role: str = "",
    line_user_id: str = "__SKIP__",
    phone: str = "",
    email: str = "",
    business_units: str = "__SKIP__",
    payment_terms: str = "",
    notes: str = "",
    active: int = -1,
) -> str:
    """更新外包夥伴資料。

    Args:
        partner_id: 夥伴 ID
        line_user_id: LINE User ID（傳空字串清除綁定）
        business_units: 服務的事業體（傳空字串清除）
        active: 1=活躍 0=停用（-1=不更新）
    """
    return service.update_partner(
        partner_id=partner_id,
        name=name,
        role=role,
        line_user_id=line_user_id,
        phone=phone,
        email=email,
        business_units=business_units,
        payment_terms=payment_terms,
        notes=notes,
        active=active,
    )


@mcp.tool()
def list_partners(active_only: bool = True, role: str = "", business_unit: str = "") -> str:
    """列出外包夥伴。

    Args:
        active_only: 只列活躍夥伴（預設 True）
        role: 篩選職責關鍵字（模糊比對）
        business_unit: 篩選服務特定事業體的夥伴
    """
    return service.list_partners(active_only=active_only, role=role, business_unit=business_unit)


@mcp.tool()
def find_partner(query: str) -> str:
    """搜尋外包夥伴（姓名、職責、電話或 LINE user ID）。

    Args:
        query: 搜尋關鍵字，或傳 LINE user_id 查身份
    """
    return service.find_partner(query)


@mcp.tool()
def get_partner(partner_id: int) -> str:
    """查看單筆外部夥伴（員工以外、配送／倉管／合作方等）完整資訊。

    Args:
        partner_id: 夥伴 ID
    """
    return service.get_partner(partner_id)
