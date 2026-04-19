#!/usr/bin/env python3
"""
Detect which modules have changed since the last successful tribal-mapper run.

Output (stdout): JSON list of module IDs that need re-analysis.

Resolution order (v2: cache-aware):
  0. Check SHA256 cache (.claude/cache/analyst/) — modules with a current-hash
     match are listed as `cached_modules` and excluded from re-analysis,
     regardless of git diff results. This is the v2 fast path.
  1. If `.claude/context/_coverage.json` has a `last_success_sha`, use
     `git diff <sha> HEAD --name-only` to find changed files.
  2. Otherwise, fall back to mtime comparison between source files and
     their corresponding analyst artifacts.
  3. Always include modules whose dependency edges (per `_dep-graph.json`
     ripple_index) point to a directly-changed module — UNLESS the rippled
     module is already cache-hit (its content hasn't changed).

Usage:
    python .claude/scripts/detect_changed_modules.py
    python .claude/scripts/detect_changed_modules.py --since-sha <sha>
    python .claude/scripts/detect_changed_modules.py --no-cache  # disable cache fast path
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


REPO_MAP = Path(".claude/context/_repo-map.json")
COVERAGE = Path(".claude/context/_coverage.json")
DEP_GRAPH = Path(".claude/context/_dep-graph.json")
ANALYST_DIR = Path(".claude/artifacts/analyst")

# v2: cache.py を sys.path 経由で import 可能にする
sys.path.insert(0, str(Path(__file__).parent.resolve()))
try:
    import cache as _v2_cache  # noqa: E402
    _CACHE_AVAILABLE = True
except ImportError:
    _CACHE_AVAILABLE = False


def flatten(module_id: str) -> str:
    """Match flatten_module_path.py logic; kept inline to avoid import dependency."""
    import hashlib
    flat = module_id.replace("/", "__").replace("\\", "__")
    if len(flat) > 60:
        digest = hashlib.sha1(module_id.encode("utf-8")).hexdigest()[:8]
        flat = flat[:50] + "__" + digest
    return flat


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def git_changed_files(since_sha: str) -> list[str]:
    try:
        out = subprocess.run(
            ["git", "diff", "--name-only", since_sha, "HEAD"],
            capture_output=True, text=True, check=True,
        )
        return [line.strip() for line in out.stdout.splitlines() if line.strip()]
    except subprocess.CalledProcessError:
        return []


def modules_for_files(files: list[str], modules: list[dict]) -> set[str]:
    """Map each changed file to the module(s) it belongs to."""
    hits: set[str] = set()
    # Sort modules by path-length descending so deeper paths win
    sorted_mods = sorted(modules, key=lambda m: -len(m["path"]))
    for f in files:
        for m in sorted_mods:
            mp = m["path"].rstrip("/") + "/"
            if f.startswith(mp) or f == m["path"]:
                hits.add(m["id"])
                break
    return hits


def mtime_based_changes(modules: list[dict]) -> set[str]:
    """Fallback: compare module file mtimes against analyst artifact mtime.

    v2 fix: tribal v1 にあった「単一ファイル module で rglob('*') が空集合を
    返し検出漏れ」バグを修正。`mod_path.is_file()` の場合は当該ファイル自体を
    比較対象にする。
    """
    hits: set[str] = set()
    for m in modules:
        artifact = ANALYST_DIR / f"{flatten(m['id'])}.json"
        if not artifact.exists():
            hits.add(m["id"])
            continue
        artifact_mtime = artifact.stat().st_mtime
        mod_path = Path(m["path"])
        if not mod_path.exists():
            continue
        # v2 fix: single-file module case
        if mod_path.is_file():
            if mod_path.stat().st_mtime > artifact_mtime:
                hits.add(m["id"])
            continue
        for f in mod_path.rglob("*"):
            if f.is_file() and f.stat().st_mtime > artifact_mtime:
                hits.add(m["id"])
                break
    return hits


def expand_with_ripple(direct_changes: set[str], dep_graph: dict) -> set[str]:
    ripple = dep_graph.get("ripple_index", {})
    expanded = set(direct_changes)
    for mod in direct_changes:
        for impacted in ripple.get(mod, []):
            expanded.add(impacted)
    return expanded


def cache_hit_modules(modules: list[dict], repo_root: Path) -> set[str]:
    """v2: SHA256 cache に analyst 結果が現在 hash で存在する module 群を返す。

    返り値の module は再分析不要 (cache 復元で済む)。cache.py が
    無い / cache dir が空なら空集合。
    """
    if not _CACHE_AVAILABLE:
        return set()
    hits: set[str] = set()
    for m in modules:
        if _v2_cache.is_cached(m["id"], "analyst", repo_root=repo_root):
            hits.add(m["id"])
    return hits


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--since-sha", default=None,
                        help="Override baseline commit SHA")
    parser.add_argument("--include-ripple", action="store_true", default=True,
                        help="Expand changes via dep-graph ripple_index")
    parser.add_argument("--no-cache", action="store_true", default=False,
                        help="Disable v2 SHA256 cache fast path (force re-analysis)")
    args = parser.parse_args()

    repo_map = load_json(REPO_MAP, {"repos": []})
    all_modules: list[dict] = []
    for repo in repo_map.get("repos", []):
        all_modules.extend(repo.get("modules", []))

    if not all_modules:
        print(json.dumps({"changed_modules": [], "reason": "no repo-map"}))
        return 0

    coverage = load_json(COVERAGE, {})
    since_sha = args.since_sha or coverage.get("last_success_sha")

    if since_sha:
        changed_files = git_changed_files(since_sha)
        direct = modules_for_files(changed_files, all_modules)
        method = f"git-diff from {since_sha}"
    else:
        direct = mtime_based_changes(all_modules)
        method = "mtime fallback"

    if args.include_ripple:
        dep_graph = load_json(DEP_GRAPH, {})
        final = expand_with_ripple(direct, dep_graph)
    else:
        final = direct

    # v2 cache fast path: cache-hit modules は内容変化なしなので再分析対象から除外
    repo_root = Path.cwd()
    if args.no_cache or not _CACHE_AVAILABLE:
        cached = set()
        cache_status = "disabled" if args.no_cache else "unavailable"
    else:
        cached = cache_hit_modules(all_modules, repo_root)
        cache_status = "active"

    needs_reanalysis = sorted(final - cached)
    cache_skipped = sorted(final & cached)

    print(json.dumps({
        "changed_modules": needs_reanalysis,
        "direct_changes": sorted(direct),
        "ripple_added": sorted(final - direct),
        "cached_modules": sorted(cached),
        "cache_skipped_from_changes": cache_skipped,
        "cache_status": cache_status,
        "method": method,
        "since_sha": since_sha,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
