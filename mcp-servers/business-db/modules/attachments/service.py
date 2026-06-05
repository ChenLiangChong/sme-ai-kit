"""Attachments service — 業務邏輯（檔案類型推斷、列表格式化）。

層次邊界：
- 進來：使用者層級參數（從 tool 薄殼透傳）
- 出去：給人看的字串
- 知道業務（type_map / icon_map / display 規則）但不知道 MCP
- DB 透過 get_db() + repository 拿，不直接寫 SQL
- **transaction ownership 在這層**：service 開 db、呼叫 N 次 repository、commit、close。
  repository 只 execute、不 commit；這樣 cross-table 寫入時 rollback 才完整。
"""
import os

from shared.db import get_db, transaction

from . import repository

_TYPE_MAP = {
    ".jpg": "image", ".jpeg": "image", ".png": "image", ".gif": "image",
    ".pdf": "pdf",
    ".doc": "document", ".docx": "document",
    ".xls": "spreadsheet", ".xlsx": "spreadsheet",
    ".mp4": "video",
    ".m4a": "audio", ".mp3": "audio",
}

_TYPE_ICON = {
    "image": "[圖]",
    "pdf": "[PDF]",
    "document": "[文件]",
    "spreadsheet": "[試算]",
    "video": "[影片]",
    "audio": "[音訊]",
    "other": "[其他]",
}


# target_type → 對應實體表（驗證 target 真存在、防 dangling 附件；codex MED）。
# 只允許白名單內的 target_type，未知類型一律擋下（不放行去建孤兒附件）。
_TARGET_TABLE = {
    "task": "tasks",
    "order": "orders",
    "customer": "customers",
    "inventory": "inventory",
    "rule": "business_rules",
}


def _infer_file_type(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    return _TYPE_MAP.get(ext, "other")


def add(
    target_type: str,
    target_id: int,
    file_path: str,
    file_name: str = "",
    description: str = "",
    uploaded_by: str = "",
) -> str:
    resolved_name = file_name or os.path.basename(file_path)
    file_type = _infer_file_type(file_path)
    table = _TARGET_TABLE.get(target_type)
    if table is None:
        return (
            f"ERROR: 不支援的附件對象類型「{target_type}」"
            f"（可用：{', '.join(_TARGET_TABLE)}）"
        )
    with transaction() as db:
        # 驗證 target 真存在、否則回 ERROR（防孤兒附件指向不存在的 task/order/...）。
        # table 名取自上面寫死的白名單、非使用者輸入 → 拼接安全；target_id 仍 parameterized。
        if not repository.target_exists(db, table, target_id):
            return f"ERROR: 找不到 {target_type} #{target_id}，無法附加檔案"
        attachment_id = repository.insert(
            db,
            target_type=target_type,
            target_id=target_id,
            file_path=file_path,
            file_type=file_type,
            file_name=resolved_name,
            description=description or None,
            uploaded_by=uploaded_by or None,
        )
    return f"附件 #{attachment_id} 已新增 → {target_type} #{target_id}（{resolved_name}）"


def list_for(target_type: str, target_id: int) -> str:
    db = get_db()
    try:
        rows = repository.list_by_target(db, target_type, target_id)
        if not rows:
            return f"{target_type} #{target_id} 沒有附件。"
        lines = [f"## {target_type} #{target_id} 的附件（{len(rows)} 個）"]
        for a in rows:
            icon = _TYPE_ICON.get(a["file_type"], "[其他]")
            lines.append(
                f"- {icon} [#{a['id']}] {a['file_name']} — {a['description'] or '無說明'}"
            )
            lines.append(f"  路徑：{a['file_path']}")
        return "\n".join(lines)
    finally:
        db.close()
