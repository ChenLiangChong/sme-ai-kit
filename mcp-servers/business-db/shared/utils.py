"""
Shared utility helpers — 純函式、無 DB schema 知識（除了 _safe_update 接 db connection 但不知 schema）。

Phase 1.2 抽出（codex review BLOCKER）：避免拆 module 時形成 server → module 逆向 import。
"""
import sqlite3


def _rows_to_str(rows: list[sqlite3.Row], max_rows: int = 50) -> str:
    if not rows:
        return "（無資料）"
    results = []
    for r in rows[:max_rows]:
        results.append(" | ".join(f"{k}={r[k]}" for k in r.keys() if r[k] is not None))
    if len(rows) > max_rows:
        results.append(f"... 還有 {len(rows) - max_rows} 筆")
    return "\n".join(results)


def _like_param(query: str) -> str:
    """將使用者輸入轉為 LIKE 查詢參數。SME 資料量小，LIKE 比 FTS5 更適合 CJK。"""
    cleaned = query.strip().replace("%", "").replace("_", "")
    return f"%{cleaned}%"


def _build_guidance(
    auto_done: list[str] | None = None,
    next_steps: list[str] | None = None,
    warnings: list[str] | None = None,
) -> str:
    """Build structured guidance block for tool returns."""
    parts: list[str] = []
    if auto_done:
        parts.append("\n已自動完成：\n" + "\n".join(f"- {s}" for s in auto_done))
    if next_steps:
        parts.append("\n下一步：\n" + "\n".join(f"{i+1}. {s}" for i, s in enumerate(next_steps)))
    if warnings:
        parts.append("\n注意：注意：\n" + "\n".join(f"- {s}" for s in warnings))
    return "\n".join(parts) if parts else ""


def _safe_update(db, table: str, allowed_columns: set[str], updates: list[str], params: list, where: str, where_params: list) -> int:
    """Execute UPDATE with column-name whitelist validation.
    updates: list of 'column = ?' or 'column = expr' strings. Each column name (before '=') is validated against allowed_columns.
    Returns rowcount."""
    for u in updates:
        col = u.split("=")[0].strip()
        if col not in allowed_columns:
            raise ValueError(f"Column '{col}' not in allowed set for {table}")
    sql = f"UPDATE {table} SET {', '.join(updates)} WHERE {where}"
    result = db.execute(sql, params + where_params)
    return result.rowcount
