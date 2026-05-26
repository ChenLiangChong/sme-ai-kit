"""Orders items helper — _parse_items_json（純 helper、no @mcp.tool）。

Phase 1.4.4 抽出。Init_db backfill 也 import 這個 helper。
"""
import json


def _parse_items_json(raw) -> list:
    """Safely parse order items JSON. Returns [] on None, empty string, or invalid JSON."""
    if not raw:
        return []
    try:
        result = json.loads(raw) if isinstance(raw, str) else raw
        return result if isinstance(result, list) else []
    except (json.JSONDecodeError, TypeError):
        return []
