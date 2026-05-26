"""Attachments tools — @mcp.tool 薄殼，業務邏輯在 service.py、SQL 在 repository.py。

Phase 2.1 三層化（tools/service/repository pattern 試點）。
這層只負責：
1. @mcp.tool 註冊 + tool docstring（給 LLM 看的 schema 描述）
2. 把 args 透傳給 service
不做：型別轉換以外的任何邏輯、任何 DB 操作、任何格式化。
"""
from shared.mcp_instance import mcp

from . import service


@mcp.tool()
def add_attachment(
    target_type: str,
    target_id: int,
    file_path: str,
    file_name: str = "",
    description: str = "",
    uploaded_by: str = "",
) -> str:
    """為任務、訂單、客戶等附加檔案（存路徑，不存檔案本身）。

    Args:
        target_type: 附加對象類型 — task | order | customer | inventory | rule
        target_id: 對象 ID
        file_path: 檔案路徑（本地路徑或 URL）
        file_name: 檔案名稱（空白=從路徑推斷）
        description: 說明
        uploaded_by: 上傳者
    """
    return service.add(
        target_type=target_type,
        target_id=target_id,
        file_path=file_path,
        file_name=file_name,
        description=description,
        uploaded_by=uploaded_by,
    )


@mcp.tool()
def list_attachments(target_type: str, target_id: int) -> str:
    """列出某對象的所有附件。

    Args:
        target_type: 對象類型 — task | order | customer | inventory | rule
        target_id: 對象 ID
    """
    return service.list_for(target_type=target_type, target_id=target_id)
