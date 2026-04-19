#!/usr/bin/env python3
"""
PostToolUse hook for Write/Edit/MultiEdit on .claude/context/*.md files.

Reads tool invocation details from stdin (Claude Code hook spec) and validates:
  - Meaningful line count (25-40, excluding blank lines and code fence delimiters)
  - Required headings present
  - All file paths referenced in the context actually exist on disk

Exits 0 on pass, 1 on validation failure (which surfaces to Claude as an error).
Exits 0 (silent) for files outside .claude/context/ to avoid disrupting other writes.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Iterable


REQUIRED_HEADINGS = [
    "## Quick Commands",
    "## Key Files",
    "## Non-Obvious Patterns",
    "## See Also",
]

# Meta paper specifies "25-35 lines (~1,000 tokens)" measured as raw lines
# (including blanks and code-fence delimiters). We allow a slight relaxation
# to 25-45 to accommodate slightly more Q3 patterns while keeping the
# "compass, not encyclopedia" principle.
MIN_LINES = 25
MAX_LINES = 45

# Hard token-budget guard (rough char-based estimate; tiktoken would be more
# precise but we avoid the dependency). Approximately 1.2k tokens ceiling.
MAX_CHARS = 4800

PATH_SUFFIXES = (
    ".py", ".cpp", ".cc", ".c", ".h", ".hpp", ".md", ".json", ".yaml",
    ".yml", ".ts", ".tsx", ".js", ".jsx", ".java", ".go", ".rs", ".php",
    ".hack", ".sh", ".rb", ".kt", ".swift", ".scala", ".tf", ".hcl",
    ".sql", ".proto", ".graphql", ".toml", ".ini",
)

LANGUAGE_TOKENS = {
    "bash", "python", "sh", "json", "yaml", "yml", "ts", "tsx", "js",
    "jsx", "go", "rust", "java", "cpp", "c", "html", "css", "diff",
    "text", "plain", "markdown", "md",
}


def read_hook_payload() -> dict:
    """Read JSON payload from stdin per Claude Code hook spec."""
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return {}
        return json.loads(raw)
    except (json.JSONDecodeError, OSError):
        return {}


def extract_target_path(payload: dict) -> Path | None:
    """Extract the file path being written from the hook payload."""
    tool_input = payload.get("tool_input") or {}
    for key in ("file_path", "path", "filename"):
        if key in tool_input and tool_input[key]:
            return Path(tool_input[key]).resolve()
    return None


def is_context_file(target: Path, repo_root: Path) -> bool:
    """Only validate files under .claude/context/."""
    try:
        rel = target.relative_to(repo_root)
    except ValueError:
        return False
    parts = rel.parts
    return (
        len(parts) >= 3
        and parts[0] == ".claude"
        and parts[1] == "context"
        and rel.suffix == ".md"
        and not parts[-1].startswith("_")  # Index files (_repo-map etc) are not contexts
    )


def validate_line_count(lines: list[str], total_chars: int) -> list[str]:
    errors: list[str] = []
    count = len(lines)  # Raw line count, matching Meta spec
    if count < MIN_LINES:
        errors.append(f"too sparse: {count} lines, minimum {MIN_LINES} (Meta spec: 25-35)")
    if count > MAX_LINES:
        errors.append(f"too verbose: {count} lines, maximum {MAX_LINES} (Meta spec: 25-35, encyclopedia not allowed)")
    if total_chars > MAX_CHARS:
        errors.append(
            f"too large: {total_chars} chars (~{total_chars // 4} tokens), "
            f"maximum {MAX_CHARS} (~1.2k tokens). Trim aggressively."
        )
    return errors


def validate_headings(text: str) -> list[str]:
    errors: list[str] = []
    for heading in REQUIRED_HEADINGS:
        if heading not in text:
            errors.append(f"missing required heading: {heading}")
    return errors


def is_path_like(token: str) -> bool:
    if not token or " " in token or "\t" in token:
        return False
    if token.startswith(("http://", "https://", "//", "#", "@")):
        return False
    if token.lower() in LANGUAGE_TOKENS:
        return False
    if token.startswith(".claude/") or token.startswith(".github/"):
        return True
    if token.startswith("/"):
        return False  # Absolute paths are suspicious in a project context file
    if "/" in token and not token.endswith("/"):
        return True
    return token.endswith(PATH_SUFFIXES)


def extract_candidate_paths(text: str) -> list[str]:
    candidates: set[str] = set()

    # Backticked tokens
    for token in re.findall(r"`([^`\n]+)`", text):
        token = token.strip()
        # Strip line:col suffix like "foo.py:42" or "foo.py:42-50"
        token = re.sub(r":\d+(-\d+)?$", "", token)
        if is_path_like(token):
            candidates.add(token)

    # Bullet lines: "- path/to/file — why"  (em-dash or en-dash or double-hyphen)
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith(("- ", "* ")):
            continue
        body = stripped[2:].strip()
        # Try several separators
        for sep in (" — ", " – ", " -- ", " — ", " - "):
            if sep in body:
                left = body.split(sep, 1)[0].strip().strip("`")
                left = re.sub(r":\d+(-\d+)?$", "", left)
                if is_path_like(left):
                    candidates.add(left)
                break

    return sorted(candidates)


def validate_paths(repo_root: Path, paths: Iterable[str]) -> list[str]:
    errors: list[str] = []
    for raw in paths:
        candidate = (repo_root / raw).resolve()
        if not candidate.exists():
            errors.append(f"referenced path does not exist: {raw}")
    return errors


def main() -> int:
    payload = read_hook_payload()
    target = extract_target_path(payload)
    if target is None:
        return 0  # No file path → nothing to validate

    repo_root = Path.cwd().resolve()
    if not is_context_file(target, repo_root):
        return 0  # Not a context file → silent pass

    if not target.exists():
        # Write may have failed; let Claude handle that error path
        return 0

    text = target.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    errors: list[str] = []
    errors.extend(validate_line_count(lines, len(text)))
    errors.extend(validate_headings(text))
    errors.extend(validate_paths(repo_root, extract_candidate_paths(text)))

    if errors:
        rel = target.relative_to(repo_root)
        print(f"context validation failed for {rel}:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        # Return JSON to give Claude actionable feedback
        feedback = {
            "decision": "block",
            "reason": (
                f"Context file {rel} failed validation. Fix these issues and rewrite:\n"
                + "\n".join(f"  - {e}" for e in errors)
            ),
        }
        print(json.dumps(feedback))
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
