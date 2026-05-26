"""Knowledge module — rules / decisions / interactions / context summary（11 tools）。

Cross-cutting graph 層：rule_relations + superseded_by + cross-entity refs。
Import 這個 module 會自動 register tool 到 shared mcp instance。
"""
from . import tools  # noqa: F401
