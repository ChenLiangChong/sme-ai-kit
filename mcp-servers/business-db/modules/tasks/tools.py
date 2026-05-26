"""Tasks tools — @mcp.tool 薄殼，業務邏輯在 service.py、SQL 在 repository.py。

Phase 2.6 三層化（套 P2.1 attachments pattern）。
"""
from shared.mcp_instance import mcp

from . import service


@mcp.tool()
def create_task(
    title: str,
    description: str = "",
    assignee: str = "",
    priority: str = "normal",
    category: str = "general",
    tags: str = "",
    business_unit: str = "",
    due_date: str = "",
    parent_task_id: int = 0,
    created_by: str = "",
) -> str:
    """建立新任務。可指定 parent_task_id 建立子任務（多階段專案）。

    Args:
        title: 任務標題
        description: 任務描述
        assignee: 指派給誰（員工姓名）
        priority: 優先級 — urgent | normal | low
        category: 分類（如 general, production, content, design, delivery, meeting, admin, rock）
        tags: 標籤（逗號分隔，可多標籤，如 q2-goal,urgent,客戶A相關）
        business_unit: 所屬事業體（如 product, design, content），留空=不分
        due_date: 截止日期（YYYY-MM-DD）
        parent_task_id: 父任務 ID（建立子任務時用，0=獨立任務）
        created_by: 建立者
    """
    return service.create_task(
        title=title,
        description=description,
        assignee=assignee,
        priority=priority,
        category=category,
        tags=tags,
        business_unit=business_unit,
        due_date=due_date,
        parent_task_id=parent_task_id,
        created_by=created_by,
    )


@mcp.tool()
def update_task(
    task_id: int,
    status: str = "",
    assignee: str = "",
    description: str = "",
    priority: str = "",
) -> str:
    """更新任務狀態或資訊。

    Args:
        task_id: 任務 ID
        status: 新狀態 — pending | in_progress | done | cancelled
        assignee: 重新指派
        description: 更新描述
        priority: 更新優先級
    """
    return service.update_task(
        task_id=task_id,
        status=status,
        assignee=assignee,
        description=description,
        priority=priority,
    )


@mcp.tool()
def list_tasks(
    status: str = "",
    assignee: str = "",
    category: str = "",
    business_unit: str = "",
    parent_task_id: int = 0,
    limit: int = 20,
) -> str:
    """列出任務。

    Args:
        status: 篩選狀態（pending, in_progress, done, cancelled），空白=全部
        assignee: 篩選指派對象
        category: 篩選分類
        business_unit: 篩選事業體（留空=全部）
        parent_task_id: 列出指定父任務的子任務（0=列出頂層任務）
        limit: 最多顯示幾筆
    """
    return service.list_tasks(
        status=status,
        assignee=assignee,
        category=category,
        business_unit=business_unit,
        parent_task_id=parent_task_id,
        limit=limit,
    )


@mcp.tool()
def search_tasks(query: str) -> str:
    """全文搜尋任務。

    Args:
        query: 搜尋關鍵字
    """
    return service.search_tasks(query)


@mcp.tool()
def get_task(task_id: int) -> str:
    """查看單筆任務完整資訊（含 description 全文、父子任務）。

    Args:
        task_id: 任務 ID
    """
    return service.get_task(task_id)
