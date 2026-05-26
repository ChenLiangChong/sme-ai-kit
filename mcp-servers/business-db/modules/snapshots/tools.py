"""Snapshots tools — @mcp.tool 薄殼，業務邏輯在 service.py、SQL 在 repository.py。

Phase 2.2 三層化（套 P2.1 attachments 驗證過的 pattern）。
"""
from shared.mcp_instance import mcp

from . import service


@mcp.tool()
def save_daily_snapshot() -> str:
    """擷取今日所有營運指標存入快照（全域 + 各事業體）。CLAUDE.md 啟動流程觸發。"""
    return service.save_daily()
