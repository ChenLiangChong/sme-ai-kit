"""Deadlines module — legal-admin 案件（matters）+ 時限（deadlines）管理。

Import 這個 module 會自動 register tool 到 shared mcp instance。
計算引擎在 shared/deadlines.py（純函式、service 與 cron 共用）。
"""
from . import tools  # noqa: F401
