#!/usr/bin/env python3
"""
Tribal v2 — PreToolUse hook for Read|Glob|Grep (Phase 5: defense-in-depth).

UserPromptSubmit hook が router 起動指示を注入しても、subagent 経由の
Read/Glob/Grep がそれをスキップできてしまう。本 hook はそれを補完する:

- TASK_WINDOW (30 分) 内で router が走っていれば素通し
- opt-out フラグが立っていれば素通し
- それ以外で .claude/context/ への直接アクセス検出 → 警告 additionalContext を注入

注意: hook は **block しない** (warning only)。tribal の opt-in 哲学は強制ではなく
誘導 — 強制 block は実装ミスを増やすだけ。

Hook spec:
  matcher: "Read|Glob|Grep"
  入力: stdin に Claude Code の hook payload (tool_input 含む)
  出力: stdout に additionalContext を含む JSON, exit 0
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path


SESSION_DIR = Path(".claude/.session-state")
SESSION_FILE = SESSION_DIR / "router-state.json"

# UserPromptSubmit hook と共通の TASK_WINDOW
TASK_WINDOW_SEC = 30 * 60


def read_payload() -> dict:
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, OSError):
        return {}


def load_session_state() -> dict:
    if not SESSION_FILE.exists():
        return {}
    try:
        return json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def is_context_access(tool_name: str, tool_input: dict) -> bool:
    """この tool 呼び出しが .claude/context/ を読もうとしているか判定."""
    if tool_name == "Read":
        path = tool_input.get("file_path") or tool_input.get("path") or ""
        return ".claude/context/" in str(path) and not str(path).endswith(("_routing-table.json", "_dep-graph.json", "_communities.json", "_god-nodes.json", "_repo-map.json"))
    if tool_name == "Glob":
        pattern = tool_input.get("pattern") or ""
        return ".claude/context/" in pattern
    if tool_name == "Grep":
        path = tool_input.get("path") or ""
        return ".claude/context/" in str(path)
    return False


def emit_passthrough() -> int:
    print(json.dumps({}))
    return 0


def emit_warning(reason: str) -> int:
    """Inject a warning into the model context. Does NOT block (additionalContext only)."""
    msg = (
        "[Tribal v2 router state warning]\n"
        f"検出: {reason}\n"
        "router 未起動のまま .claude/context/ にアクセスしようとしています。\n"
        "推奨: まず /tribal-route <task description> で関連 context を 3-5 枚に絞り込んでください。\n"
        "全 context.md の一括ロードは tribal opt-in 原則違反です (Meta 論文 arxiv 2602.11988 の失敗モード)。\n"
        "明示的に「ルーター不要」「全部読んで」と指示された場合は無視可。"
    )
    response = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": msg,
        }
    }
    print(json.dumps(response))
    return 0


def main() -> int:
    payload = read_payload()
    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})

    # Only proceed if this looks like a context access
    if not is_context_access(tool_name, tool_input):
        return emit_passthrough()

    state = load_session_state()
    # Opt-out always wins
    if state.get("opted_out"):
        return emit_passthrough()
    last_routing_ts = state.get("last_routing_ts", 0)
    now = time.time()
    # Active routing window — recently routed
    if last_routing_ts > 0 and (now - last_routing_ts) < TASK_WINDOW_SEC:
        return emit_passthrough()
    # Cold session or stale → warn
    return emit_warning(f"{tool_name} on .claude/context/ without recent router invocation")


if __name__ == "__main__":
    raise SystemExit(main())
