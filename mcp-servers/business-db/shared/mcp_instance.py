"""
Shared FastMCP instance — modules 透過 `from shared.mcp_instance import mcp` 取得後
用 `@mcp.tool()` 註冊。Server.py 也從這裡 import，避免重複建立 instance。

抽離原因（Phase 1 拆 module）：tool 散到 modules/*/tools.py 後仍須註冊到同一個 mcp，
否則 FastMCP server 起來會找不到 tool。
"""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("business-db")
