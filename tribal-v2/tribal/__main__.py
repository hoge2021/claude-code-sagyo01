"""Tribal v2 — `tribal install` CLI (Phase 6).

graphify/__main__.py の `_PLATFORM_CONFIG` パターンを 3 platform に絞って採用:
  claude   — .claude/ + UserPromptSubmit + PostToolUse + PreToolUse(Read|Glob|Grep) hook
  codex    — AGENTS.md + .codex/hooks.json (PreToolUse)
  opencode — AGENTS.md + .opencode/plugins/tribal.js (tool.execute.before)

Usage:
    tribal install --platform claude
    tribal install --platform codex
    tribal install --platform opencode
    tribal uninstall --platform claude
    tribal serve --base .claude
    tribal --version
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from importlib import resources
from pathlib import Path

from tribal import __version__


# ---------------------------------------------------------------------------
# Platform definitions
# ---------------------------------------------------------------------------

# .tribal_version key file written into platform skill dir for sync detection
_VERSION_STAMP = ".tribal_version"


def _claude_install(target_root: Path) -> list[str]:
    """Install Claude Code platform: .claude/ tree + settings.json hooks."""
    actions: list[str] = []
    template_root = _template_root()  # tribal-v2/.claude/ inside the package source

    # Copy .claude/ tree (skills, agents, scripts, schemas, commands)
    for sub in ("skills", "agents", "scripts", "schemas", "commands"):
        src = template_root / sub
        dst = target_root / ".claude" / sub
        if not src.exists():
            continue
        dst.mkdir(parents=True, exist_ok=True)
        for f in src.rglob("*"):
            if f.is_file():
                rel = f.relative_to(src)
                target = dst / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, target)
        actions.append(f"copied .claude/{sub}/")

    # Merge settings.json (don't clobber user's existing settings)
    settings_src = template_root / "settings.json"
    settings_dst = target_root / ".claude" / "settings.json"
    if settings_src.exists():
        if settings_dst.exists():
            try:
                existing = json.loads(settings_dst.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                existing = {}
            new = json.loads(settings_src.read_text(encoding="utf-8"))
            merged = _merge_settings(existing, new)
            settings_dst.write_text(json.dumps(merged, indent=2, ensure_ascii=False),
                                    encoding="utf-8")
            actions.append("merged .claude/settings.json (preserving existing keys)")
        else:
            shutil.copy2(settings_src, settings_dst)
            actions.append("wrote .claude/settings.json")

    # CLAUDE.md section
    claude_md = target_root / "CLAUDE.md"
    section = _claude_md_section()
    if claude_md.exists():
        existing = claude_md.read_text(encoding="utf-8")
        if "## Tribal Knowledge Mapper" not in existing:
            claude_md.write_text(existing.rstrip() + "\n\n" + section, encoding="utf-8")
            actions.append("appended Tribal section to CLAUDE.md")
        else:
            actions.append("CLAUDE.md already has Tribal section (skipped)")
    else:
        claude_md.write_text(section, encoding="utf-8")
        actions.append("created CLAUDE.md with Tribal section")

    # Version stamp
    (target_root / ".claude" / _VERSION_STAMP).write_text(__version__, encoding="utf-8")
    actions.append(f"stamped {_VERSION_STAMP} = {__version__}")

    return actions


def _codex_install(target_root: Path) -> list[str]:
    """Codex: AGENTS.md + .codex/hooks.json with PreToolUse hook."""
    actions: list[str] = []
    agents_md = target_root / "AGENTS.md"
    section = _agents_md_section()
    if agents_md.exists():
        existing = agents_md.read_text(encoding="utf-8")
        if "## Tribal Knowledge Mapper" not in existing:
            agents_md.write_text(existing.rstrip() + "\n\n" + section, encoding="utf-8")
            actions.append("appended Tribal section to AGENTS.md")
        else:
            actions.append("AGENTS.md already has Tribal section (skipped)")
    else:
        agents_md.write_text(section, encoding="utf-8")
        actions.append("created AGENTS.md with Tribal section")

    # Codex hook
    hook_dir = target_root / ".codex"
    hook_dir.mkdir(exist_ok=True)
    hook_path = hook_dir / "hooks.json"
    hook_content = {
        "preToolUse": [
            {"matcher": "Bash",
             "command": "python3 .claude/scripts/check_router_state.py"}
        ]
    }
    hook_path.write_text(json.dumps(hook_content, indent=2), encoding="utf-8")
    actions.append("wrote .codex/hooks.json (PreToolUse)")

    return actions


def _opencode_install(target_root: Path) -> list[str]:
    """OpenCode: AGENTS.md + .opencode/plugins/tribal.js (tool.execute.before)."""
    actions: list[str] = []
    agents_md = target_root / "AGENTS.md"
    section = _agents_md_section()
    if agents_md.exists():
        existing = agents_md.read_text(encoding="utf-8")
        if "## Tribal Knowledge Mapper" not in existing:
            agents_md.write_text(existing.rstrip() + "\n\n" + section, encoding="utf-8")
            actions.append("appended Tribal section to AGENTS.md")
        else:
            actions.append("AGENTS.md already has Tribal section (skipped)")
    else:
        agents_md.write_text(section, encoding="utf-8")
        actions.append("created AGENTS.md with Tribal section")

    plugin_dir = target_root / ".opencode" / "plugins"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    plugin_path = plugin_dir / "tribal.js"
    plugin_path.write_text(_opencode_plugin_js(), encoding="utf-8")
    actions.append("wrote .opencode/plugins/tribal.js (tool.execute.before)")

    return actions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _template_root() -> Path:
    """Locate the .claude/ template tree.

    When installed via pip, templates are bundled in tribal package data.
    During development, they live at <repo-root>/tribal-v2/.claude/.
    """
    # Dev mode: walk up from this file
    here = Path(__file__).resolve().parent  # tribal/
    candidates = [
        here.parent / ".claude",                      # tribal-v2/.claude
        here.parent.parent / "tribal-v2" / ".claude", # repo/tribal-v2/.claude
    ]
    for c in candidates:
        if c.exists():
            return c
    # Production: bundled package data
    try:
        bundled = resources.files("tribal").joinpath("templates/.claude")
        if bundled.is_dir():
            return Path(str(bundled))
    except Exception:
        pass
    raise FileNotFoundError("Could not locate .claude/ template tree")


def _merge_settings(existing: dict, new: dict) -> dict:
    """Merge hooks arrays without dropping existing entries."""
    merged = dict(existing)
    for hook_event, hook_list in new.get("hooks", {}).items():
        merged.setdefault("hooks", {})
        existing_list = merged["hooks"].setdefault(hook_event, [])
        # Dedup by matcher + command
        seen = {(h.get("matcher"), tuple(c.get("command", "")
                for c in h.get("hooks", []))) for h in existing_list}
        for h in hook_list:
            key = (h.get("matcher"), tuple(c.get("command", "") for c in h.get("hooks", [])))
            if key not in seen:
                existing_list.append(h)
    return merged


def _claude_md_section() -> str:
    return """## Tribal Knowledge Mapper v2

このプロジェクトは Tribal Knowledge Mapper v2 を導入しています。

- 開発タスクを受け取ったら、最初に `tribal-router` skill で context を 3-5 枚に絞り込む
- `.claude/context/*.md` の一括 import は禁止 (Meta arxiv 2602.11988 の失敗モード回避)
- 3 重 hook 強制: UserPromptSubmit + PostToolUse(Write|Edit) + PreToolUse(Read|Glob|Grep)

slash commands: `/tribal-init` `/tribal-refresh` `/tribal-route` `/tribal-validate`

例外: ユーザーが「ルーター不要」「全部読んで」と明示した場合のみ skip 可。
"""


def _agents_md_section() -> str:
    return """## Tribal Knowledge Mapper v2

このプロジェクトは Tribal Knowledge Mapper v2 を導入しています。

ルール:
- 開発タスク受領時、まず `tribal-router` で関連 context を 3-5 枚に絞る
- `.claude/context/*.md` 一括 import 禁止 (opt-in 原則)
- 開発タスクを処理する前に `.claude/scripts/check_router_state.py` の警告を尊重

slash/skill commands: `/tribal-init` `/tribal-refresh` `/tribal-route` `/tribal-validate`
"""


def _opencode_plugin_js() -> str:
    return """// Tribal v2 — OpenCode tool.execute.before plugin
// graph (graph.json 相当) があれば router 経由を促すリマインダーを注入
const { existsSync } = require('fs');
const { join } = require('path');

module.exports = {
  'tool.execute.before': async (ctx) => {
    const root = process.cwd();
    if (!existsSync(join(root, '.claude/context/_routing-table.json'))) return;
    const tool = ctx.tool || '';
    if (!['read', 'glob', 'grep'].some(t => tool.toLowerCase().includes(t))) return;
    return {
      reminder: 'tribal: router 未起動のままですか? /tribal-route で context を絞ってください。'
    };
  }
};
"""


# ---------------------------------------------------------------------------
# Uninstall
# ---------------------------------------------------------------------------

def _claude_uninstall(target_root: Path) -> list[str]:
    actions: list[str] = []
    # Remove .claude/scripts/check_router_state.py (PreToolUse-specific to v2)
    # Keep other .claude/ files (might be user-modified) — only de-register hooks
    settings = target_root / ".claude" / "settings.json"
    if settings.exists():
        try:
            data = json.loads(settings.read_text(encoding="utf-8"))
            removed = 0
            hooks = data.get("hooks", {})
            for ev_name in list(hooks.keys()):
                hooks[ev_name] = [
                    h for h in hooks[ev_name]
                    if not any("check_router_state" in c.get("command", "")
                               or "validate_context_file" in c.get("command", "")
                               or "inject_router_directive" in c.get("command", "")
                               for c in h.get("hooks", []))
                ]
                if not hooks[ev_name]:
                    del hooks[ev_name]
            settings.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                                 encoding="utf-8")
            actions.append("removed Tribal hooks from .claude/settings.json")
        except json.JSONDecodeError:
            actions.append("settings.json invalid, skipped")
    actions.append("note: .claude/ tree retained — manually delete if desired")
    return actions


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

PLATFORMS = {
    "claude": _claude_install,
    "codex": _codex_install,
    "opencode": _opencode_install,
}

UNINSTALLERS = {
    "claude": _claude_uninstall,
    "codex": lambda r: ["codex uninstall: manual cleanup of AGENTS.md and .codex/ recommended"],
    "opencode": lambda r: ["opencode uninstall: manual cleanup of AGENTS.md and .opencode/ recommended"],
}


def cmd_install(args) -> int:
    if args.platform not in PLATFORMS:
        print(f"error: unknown platform {args.platform!r}. "
              f"Available: {list(PLATFORMS.keys())}", file=sys.stderr)
        return 1
    target = Path(args.target).resolve()
    if not target.exists():
        print(f"error: target dir does not exist: {target}", file=sys.stderr)
        return 1
    print(f"Installing tribal v{__version__} for platform={args.platform} at {target}")
    actions = PLATFORMS[args.platform](target)
    for a in actions:
        print(f"  ✓ {a}")
    print("Done. Try /tribal-init to build the knowledge graph.")
    return 0


def cmd_uninstall(args) -> int:
    if args.platform not in UNINSTALLERS:
        print(f"error: unknown platform {args.platform!r}", file=sys.stderr)
        return 1
    target = Path(args.target).resolve()
    actions = UNINSTALLERS[args.platform](target)
    for a in actions:
        print(f"  ✓ {a}")
    return 0


def cmd_serve(args) -> int:
    from tribal import serve
    base = Path(args.base).resolve()
    if args.mcp:
        serve.run_mcp_server(base)
    else:
        # Default: standalone help
        serve.main()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="tribal", description="Tribal Knowledge Mapper v2")
    parser.add_argument("--version", action="version", version=f"tribal {__version__}")
    sub = parser.add_subparsers(dest="cmd")

    p_install = sub.add_parser("install", help="Install for a platform")
    p_install.add_argument("--platform", required=True, choices=list(PLATFORMS.keys()))
    p_install.add_argument("--target", default=".", help="Target project dir (default: cwd)")
    p_install.set_defaults(func=cmd_install)

    p_uninstall = sub.add_parser("uninstall", help="Uninstall for a platform")
    p_uninstall.add_argument("--platform", required=True, choices=list(UNINSTALLERS.keys()))
    p_uninstall.add_argument("--target", default=".")
    p_uninstall.set_defaults(func=cmd_uninstall)

    p_serve = sub.add_parser("serve", help="Run MCP stdio server")
    p_serve.add_argument("--base", default=".claude")
    p_serve.add_argument("--mcp", action="store_true", default=True)
    p_serve.set_defaults(func=cmd_serve)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
