"""Tasks service — 建立 / 更新 / 列出 / 搜尋 / 查單筆 業務邏輯。

層次邊界：transaction ownership 在這層，repository 不 commit。
"""
from shared.business_units import _validate_business_unit
from shared.db import _now, get_db, transaction

from . import repository

_STATUS_VALID = ("pending", "in_progress", "done", "cancelled")
_PRIORITY_VALID = ("urgent", "normal", "low")
_PRIORITY_ICON = {"urgent": "[急]", "normal": "[普通]", "low": "[低]"}
_STATUS_ICON = {
    "pending": "[待處理]",
    "in_progress": "[進行中]",
    "done": "[已完成]",
    "cancelled": "[已取消]",
}
_STATUS_ZH = {
    "pending": "待處理",
    "in_progress": "進行中",
    "done": "已完成",
    "cancelled": "已取消",
}
_PRIORITY_ZH = {"urgent": "急", "normal": "普通", "low": "低"}


def create_task(
    title: str,
    description: str,
    assignee: str,
    priority: str,
    category: str,
    tags: str,
    business_unit: str,
    due_date: str,
    parent_task_id: int,
    created_by: str,
) -> str:
    if priority not in _PRIORITY_VALID:
        return "ERROR: priority 必須是 urgent, normal, 或 low"

    with transaction() as db:
        if parent_task_id:
            parent = repository.get_parent_title(db, parent_task_id)
            if not parent:
                return f"ERROR: 找不到父任務 #{parent_task_id}"

        task_id = repository.insert_task(
            db,
            title=title,
            description=description or None,
            assignee=assignee or None,
            priority=priority,
            category=category,
            tags=tags or None,
            business_unit=business_unit or None,
            due_date=due_date or None,
            parent_task_id=parent_task_id or None,
            created_by=created_by or None,
        )
        repository.insert_interaction_log(
            db,
            actor=created_by or "system",
            action="task_created",
            target_id=task_id,
            detail=title,
            business_unit=business_unit or None,
        )
        bu_warn = _validate_business_unit(db, business_unit)

    pri_icon = _PRIORITY_ICON[priority]
    return (
        f"任務 #{task_id} 已建立 {pri_icon} {title}"
        + (f" → {assignee}" if assignee else "")
        + bu_warn
    )


def update_task(
    task_id: int,
    status: str,
    assignee: str,
    description: str,
    priority: str,
) -> str:
    if status and status not in _STATUS_VALID:
        return "ERROR: status 必須是 pending, in_progress, done, 或 cancelled"
    if priority and priority not in _PRIORITY_VALID:
        return "ERROR: priority 必須是 urgent, normal, 或 low"

    with transaction() as db:
        task = repository.get_task(db, task_id)
        if not task:
            return f"ERROR: 找不到任務 #{task_id}"

        updates: list[str] = []
        params: list = []
        if status:
            updates.append("status = ?"); params.append(status)
            if status == "done":
                updates.append("completed_at = ?"); params.append(_now())
        if assignee:
            updates.append("assignee = ?"); params.append(assignee)
        if description:
            updates.append("description = ?"); params.append(description)
        if priority:
            updates.append("priority = ?"); params.append(priority)

        if not updates:
            return "沒有指定要更新的欄位。"

        repository.safe_update_task(db, task_id, updates, params)
        repository.insert_interaction_log(
            db,
            actor="system",
            action="task_updated",
            target_id=task_id,
            detail=f"更新: {', '.join(updates)}",
            business_unit=task["business_unit"],
        )
    return f"任務 #{task_id} 已更新"


def list_tasks(
    status: str,
    assignee: str,
    category: str,
    business_unit: str,
    parent_task_id: int,
    limit: int,
) -> str:
    db = get_db()
    try:
        rows = repository.list_tasks(
            db,
            status=status,
            assignee=assignee,
            category=category,
            business_unit=business_unit,
            parent_task_id=parent_task_id,
            limit=limit,
        )
        if not rows:
            return "沒有符合條件的任務。"

        lines = [f"## 任務列表（{len(rows)} 項）"]
        for t in rows:
            status_icon = _STATUS_ICON.get(t["status"], "")
            pri = _PRIORITY_ICON.get(t["priority"], "")
            due = f" 截止:{t['due_date']}" if t["due_date"] else ""
            parent = f" (子任務 of #{t['parent_task_id']})" if t["parent_task_id"] else ""
            sub_count = repository.count_subtasks(db, t["id"])
            subs = f"{sub_count}子任務" if sub_count > 0 else ""
            lines.append(
                f"- {status_icon}{pri} [#{t['id']}] {t['title']} → "
                f"{t['assignee'] or '未指派'}{due}{parent}{subs}"
            )
        return "\n".join(lines)
    finally:
        db.close()


def search_tasks(query: str) -> str:
    db = get_db()
    try:
        rows = repository.search_tasks(db, query)
        if not rows:
            return f"找不到與「{query}」相關的任務。"
        lines = [f"## 搜尋結果：「{query}」"]
        for t in rows:
            status_icon = _STATUS_ICON.get(t["status"], "")
            lines.append(f"- {status_icon} [#{t['id']}] {t['title']} → {t['assignee'] or '未指派'}")
        return "\n".join(lines)
    finally:
        db.close()


def get_task(task_id: int) -> str:
    db = get_db()
    try:
        t = repository.get_task(db, task_id)
        if not t:
            return f"ERROR: 找不到任務 #{task_id}"

        status_zh = _STATUS_ZH.get(t["status"], t["status"])
        priority_zh = _PRIORITY_ZH.get(t["priority"], t["priority"] or "普通")

        parent_str = ""
        if t["parent_task_id"]:
            parent = repository.get_parent_title(db, t["parent_task_id"])
            parent_str = (
                f"\n- 父任務：[#{t['parent_task_id']}] "
                f"{parent['title'] if parent else '（已刪除）'}"
            )

        subs = repository.list_subtasks(db, task_id)
        subs_str = ""
        if subs:
            sub_lines = []
            for s in subs:
                sub_status_zh = _STATUS_ZH.get(s["status"], s["status"])
                sub_lines.append(f"  - [{sub_status_zh}] [#{s['id']}] {s['title']}")
            subs_str = f"\n- 子任務（{len(subs)} 項）：\n" + "\n".join(sub_lines)

        return (
            f"## 任務 #{task_id}：{t['title']}\n"
            f"- 狀態：{status_zh}（{t['status']}）\n"
            f"- 優先級：{priority_zh}\n"
            f"- 指派：{t['assignee'] or '未指派'}\n"
            f"- 截止：{t['due_date'] or '未設定'}\n"
            f"- 分類：{t['category'] or '無'}\n"
            f"- 標籤：{t['tags'] or '無'}\n"
            f"- 事業體：{t['business_unit'] or '全域'}\n"
            f"- 建立者：{t['created_by'] or '未知'} @ {t['created_at']}\n"
            f"- 完成時間：{t['completed_at'] or '未完成'}"
            f"{parent_str}"
            f"{subs_str}\n"
            f"\n### 描述\n{t['description'] or '（無）'}"
        )
    finally:
        db.close()
