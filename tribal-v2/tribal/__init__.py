"""Tribal Knowledge Mapper v2 — Python package.

Provides the same functionality as `.claude/scripts/*.py` runtime files, but
importable as a Python package after `pip install tribal-knowledge-mapper`.

Module layout (mirrors .claude/scripts/):
    tribal.cache              — SHA256 module artifact cache (Phase 1)
    tribal.ast_extract        — tree-sitter AST extraction (Phase 2)
    tribal.cluster            — Leiden/Louvain community detection (Phase 4)
    tribal.god_nodes          — degree-based hub detection (Phase 4)
    tribal.benchmark          — token reduction measurement (Phase 5)
    tribal.check_router_state — PreToolUse hook (Phase 5)
    tribal.security           — URL/path/label validation (Phase 6, from graphify)
    tribal.serve              — MCP stdio server (Phase 6)
    tribal.__main__           — `tribal install --platform <name>` CLI (Phase 6)
"""

__version__ = "2.0.0-rc1"
