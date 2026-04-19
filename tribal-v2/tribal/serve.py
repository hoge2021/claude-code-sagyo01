"""Tribal v2 — MCP stdio server (Phase 6).

graphify/serve.py をベースに、tribal の routing intelligence を MCP tool 経由で
公開。Claude Desktop / Codex / Cursor から tribal の知識を共有可能に。

Exposed tools (improvement plan §4.6 と一致):
  route_query(query)            — router 相当 (intent 分類 + community + primary 解決)
  get_intent(name)              — intent 定義返却
  get_ripple(module)            — ripple_index 該当エントリ
  get_god_nodes(community?, top_n?) — god node リスト
  get_community(id)             — community メンバー + cohesion
  get_quality_history(module)   — _quality-log.jsonl 該当 module

依存: pip install "tribal-knowledge-mapper[mcp]" (mcp パッケージ optional)
未インストール時は明確なエラーメッセージで起動拒否。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    from tribal.security import validate_context_path, sanitize_label
except ImportError:
    # Bootstrap when running as standalone script
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from tribal.security import validate_context_path, sanitize_label


# ---------------------------------------------------------------------------
# Tool implementations (pure functions; no MCP dep needed)
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _routing_table(base: Path) -> dict:
    return _load_json(base / "context/_routing-table.json")


def _dep_graph(base: Path) -> dict:
    return _load_json(base / "context/_dep-graph.json")


def _communities(base: Path) -> dict:
    return _load_json(base / "context/_communities.json")


def _god_nodes(base: Path) -> dict:
    return _load_json(base / "context/_god-nodes.json")


def _score_intent(query: str, intent: dict) -> float:
    """keywords matched - 2 × anti_keywords matched (router skill と同じ式)."""
    q = query.lower()
    pos = sum(1 for k in intent.get("keywords", []) if k.lower() in q)
    neg = sum(1 for k in intent.get("anti_keywords", []) if k.lower() in q)
    return float(pos - 2 * neg)


def route_query(base: Path, query: str) -> dict:
    """Tool: route_query — router skill 相当を決定論で実行.

    Returns: {intent, community, primary_contexts, secondary_contexts, score}
    """
    rt = _routing_table(base)
    if not rt.get("intents"):
        return {"error": "routing-table missing — run /tribal-init first"}

    scored = sorted(
        ((it, _score_intent(query, it)) for it in rt["intents"]),
        key=lambda x: -x[1],
    )
    if not scored or scored[0][1] <= 0:
        # Fallback
        fb = rt.get("fallback", {})
        return {
            "intent": "fallback",
            "community": None,
            "primary_contexts": fb.get("primary_contexts", []),
            "secondary_contexts": [],
            "score": 0,
            "wiki_index": rt.get("wiki_index", ".claude/context/_index.md"),
        }

    top, score = scored[0]
    return {
        "intent": top["name"],
        "community": top.get("community_hint"),
        "primary_contexts": top.get("primary_contexts", []),
        "secondary_contexts": top.get("secondary_contexts", []),
        "god_node_recommended": top.get("god_node_recommended", []),
        "score": score,
    }


def get_intent(base: Path, name: str) -> dict:
    rt = _routing_table(base)
    for it in rt.get("intents", []):
        if it["name"] == name:
            return it
    return {"error": f"intent {name!r} not found"}


def get_ripple(base: Path, module: str) -> dict:
    dg = _dep_graph(base)
    ripple = dg.get("ripple_index", {})
    return {
        "module": module,
        "impacted": ripple.get(module, []),
        "count": len(ripple.get(module, [])),
    }


def get_god_nodes(base: Path, community: int | None = None,
                   top_n: int = 5) -> dict:
    gn = _god_nodes(base)
    if community is not None:
        per = gn.get("per_community", {}).get(str(community), [])
        return {"community": community, "god_nodes": per[:top_n]}
    return {"global_top_n": gn.get("global_top_n", [])[:top_n]}


def get_community(base: Path, community_id: int) -> dict:
    comm = _communities(base)
    info = comm.get("communities", {}).get(str(community_id))
    if info is None:
        return {"error": f"community {community_id} not found"}
    return {
        "id": community_id,
        "members": info["members"],
        "cohesion": info["cohesion"],
        "size": info["size"],
        "label": info.get("label"),
    }


def get_quality_history(base: Path, module: str, limit: int = 20) -> dict:
    log_path = base / "context/_quality-log.jsonl"
    if not log_path.exists():
        return {"module": module, "history": [], "error": "no quality log yet"}
    entries: list[dict] = []
    try:
        text = log_path.read_text(encoding="utf-8")
    except OSError:
        return {"module": module, "history": [], "error": "log read failed"}
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            row = json.loads(s)
        except json.JSONDecodeError:
            continue
        if row.get("module") == module:
            entries.append(row)
    return {"module": module, "history": entries[-limit:], "count": len(entries)}


# ---------------------------------------------------------------------------
# Tool dispatch (used by both MCP and standalone CLI)
# ---------------------------------------------------------------------------

TOOLS = {
    "route_query": (route_query, ["query"]),
    "get_intent": (get_intent, ["name"]),
    "get_ripple": (get_ripple, ["module"]),
    "get_god_nodes": (get_god_nodes, []),  # all params optional
    "get_community": (get_community, ["community_id"]),
    "get_quality_history": (get_quality_history, ["module"]),
}


def call_tool(name: str, args: dict, base: Path | None = None) -> dict:
    """Dispatch a tool call. Used by MCP wrapper and standalone CLI."""
    if name not in TOOLS:
        return {"error": f"unknown tool: {name}", "available": list(TOOLS.keys())}
    base = base or (Path.cwd() / ".claude")
    fn, required = TOOLS[name]
    for r in required:
        if r not in args:
            return {"error": f"missing required arg: {r}"}
    try:
        result = fn(base, **args)
        # Sanitize string values to avoid prompt injection via labels
        return _sanitize_dict(result)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def _sanitize_dict(obj):
    """Recursively sanitize all string values in a dict/list (graphify 知見)."""
    if isinstance(obj, str):
        return sanitize_label(obj)
    if isinstance(obj, dict):
        return {k: _sanitize_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_dict(v) for v in obj]
    return obj


# ---------------------------------------------------------------------------
# MCP stdio server
# ---------------------------------------------------------------------------

def run_mcp_server(base: Path) -> None:
    """Run as MCP stdio server. Requires `pip install tribal-knowledge-mapper[mcp]`."""
    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
        from mcp.types import Tool, TextContent
    except ImportError:
        print("error: mcp package not installed. Install with: "
              "pip install 'tribal-knowledge-mapper[mcp]'", file=sys.stderr)
        sys.exit(1)

    import asyncio

    server = Server("tribal-knowledge-mapper")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(name="route_query",
                 description="自然言語タスクを intent に分類し、関連 context を返す",
                 inputSchema={"type": "object", "properties": {"query": {"type": "string"}},
                              "required": ["query"]}),
            Tool(name="get_intent",
                 description="intent 名から定義を取得 (keywords / primary_contexts 等)",
                 inputSchema={"type": "object", "properties": {"name": {"type": "string"}},
                              "required": ["name"]}),
            Tool(name="get_ripple",
                 description="module ID から ripple_index (影響範囲) を取得",
                 inputSchema={"type": "object", "properties": {"module": {"type": "string"}},
                              "required": ["module"]}),
            Tool(name="get_god_nodes",
                 description="global または特定 community の god node を取得",
                 inputSchema={"type": "object",
                              "properties": {"community": {"type": "integer"},
                                             "top_n": {"type": "integer", "default": 5}}}),
            Tool(name="get_community",
                 description="community ID から member + cohesion + label を取得",
                 inputSchema={"type": "object",
                              "properties": {"community_id": {"type": "integer"}},
                              "required": ["community_id"]}),
            Tool(name="get_quality_history",
                 description="module の _quality-log.jsonl 履歴を取得",
                 inputSchema={"type": "object",
                              "properties": {"module": {"type": "string"},
                                             "limit": {"type": "integer", "default": 20}},
                              "required": ["module"]}),
        ]

    @server.call_tool()
    async def call_tool_handler(name: str, arguments: dict) -> list[TextContent]:
        result = call_tool(name, arguments, base=base)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

    async def main_loop():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(main_loop())


# ---------------------------------------------------------------------------
# Standalone CLI (debug / scripting)
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Tribal v2 MCP server / standalone CLI")
    parser.add_argument("--base", default=".claude", help="Tribal data dir (default: .claude)")
    parser.add_argument("--call", help="Call a tool standalone (no MCP)")
    parser.add_argument("--args", help="JSON args for --call")
    parser.add_argument("--mcp", action="store_true", help="Run as MCP stdio server")
    args = parser.parse_args()

    base = Path(args.base).resolve()

    if args.mcp:
        run_mcp_server(base)
        return 0

    if args.call:
        tool_args = json.loads(args.args) if args.args else {}
        result = call_tool(args.call, tool_args, base=base)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
