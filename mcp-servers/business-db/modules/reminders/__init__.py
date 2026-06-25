"""Reminders module — 排程提醒（派工器模式、3 tools）。

Import 這個 module 會自動 register tool 到 shared mcp instance。
業務邏輯在 shared.reminders（與 standalone reminder_dispatcher.py 共用、避免 import cycle）。
"""
from . import tools  # noqa: F401
