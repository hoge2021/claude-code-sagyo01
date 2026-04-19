#!/usr/bin/env python3
"""
UserPromptSubmit hook: ensure tribal-router is always invoked first for
development tasks, unless the user explicitly opts out.

Reads the user prompt from stdin, decides whether to inject a routing
directive, and outputs JSON via stdout per the Claude Code hook spec.

The session-state file tracks whether routing has already been performed
for the current task to avoid re-injecting on every follow-up message.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path


SESSION_DIR = Path(".claude/.session-state")
SESSION_FILE = SESSION_DIR / "router-state.json"

# How long (seconds) a single "task" lasts before we re-inject the directive.
# Follow-ups within this window inherit the prior routing.
TASK_WINDOW_SEC = 30 * 60  # 30 minutes

# Keywords that suggest the user is starting a *new* development task.
NEW_TASK_PATTERNS = re.compile(
    r"\b("
    r"add|create|build|implement|refactor|fix|debug|investigate|"
    r"change|update|modify|migrate|rename|delete|remove|"
    r"追加|作成|実装|修正|変更|削除|移行|調査|デバッグ|リファクタ"
    r")\b",
    re.IGNORECASE,
)

# Explicit opt-out phrases.
OPT_OUT_PATTERNS = re.compile(
    r"(skip[- ]?router|router unnecessary|no routing|don't route|"
    r"ルーター不要|ルータ不要|全部読んで|router skip)",
    re.IGNORECASE,
)


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


def save_session_state(state: dict) -> None:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def emit_passthrough() -> int:
    # Empty response = no additional context, prompt proceeds normally
    print(json.dumps({}))
    return 0


def emit_directive(reason: str) -> int:
    directive = (
        "[Tribal Knowledge Mapper directive]\n"
        "Before working on this task, you MUST invoke the `tribal-router` skill "
        "to select 3-5 relevant context files from .claude/context/. "
        "Do NOT proceed with the task or load any context files until routing is complete. "
        "If the user has already specified which context files to use, you may skip routing.\n"
        f"(Injected because: {reason})"
    )
    response = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": directive,
        }
    }
    print(json.dumps(response))
    return 0


def main() -> int:
    payload = read_payload()
    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        return emit_passthrough()

    # Explicit opt-out always wins
    if OPT_OUT_PATTERNS.search(prompt):
        save_session_state({"last_routing_ts": 0, "opted_out": True})
        return emit_passthrough()

    # Slash commands handle their own routing
    if prompt.startswith("/"):
        return emit_passthrough()

    # Check session state: was routing recently performed?
    state = load_session_state()
    last_ts = state.get("last_routing_ts", 0)
    now = time.time()
    is_new_task = bool(NEW_TASK_PATTERNS.search(prompt))

    # New task signal → always re-inject
    if is_new_task:
        save_session_state({"last_routing_ts": now, "opted_out": False})
        return emit_directive("new task keyword detected")

    # Within active task window and no new-task keyword → assume follow-up
    if now - last_ts < TASK_WINDOW_SEC and last_ts > 0:
        return emit_passthrough()

    # Cold start or stale session → inject for safety
    save_session_state({"last_routing_ts": now, "opted_out": False})
    return emit_directive("cold start or stale session")


if __name__ == "__main__":
    raise SystemExit(main())
