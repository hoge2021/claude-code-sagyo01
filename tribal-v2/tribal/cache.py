#!/usr/bin/env python3
"""
Tribal v2 — Module-level SHA256 artifact cache.

graphify.cache を tribal 用に拡張: per-FILE ではなく per-MODULE で集約 hash を計算し、
analyst / critic / context / ast の中間成果物をキャッシュする。

Cache key の構成 (v1 比の改善点):
  H = SHA256(
        sorted(SHA256(module file body) for file in module),
        repo HEAD SHA,
        cache schema version
      )

  - body hash: .md は YAML frontmatter を除外 (graphify 由来)
  - sorted(): ファイル列挙順序の差で hash がブレないように
  - repo HEAD SHA: branch 切替えで stale を防ぐ (graphify には無い tribal 固有の強化)
  - schema version: cache.py 自身の仕様変更で全 invalidation できるように

Usage:
    from cache import module_hash, load_cached_artifact, save_cached_artifact

    h = module_hash("graphify/cache", repo_root=Path("."))
    cached = load_cached_artifact("graphify/cache", "analyst")
    if cached is None:
        result = run_analyst(...)
        save_cached_artifact("graphify/cache", "analyst", result)
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Literal

ArtifactKind = Literal["ast", "analyst", "critic", "context"]
_VALID_KINDS: tuple[ArtifactKind, ...] = ("ast", "analyst", "critic", "context")

# Schema version: bump when cache layout/key format changes to invalidate all entries
CACHE_SCHEMA_VERSION = "v2.0"

# Cache root inside .claude/
CACHE_ROOT = Path(".claude/cache")


def _body_content(content: bytes, suffix: str) -> bytes:
    """For .md files, strip YAML frontmatter so metadata-only edits don't bust cache.

    Mirrors graphify/cache.py:_body_content (Phase 0 baseline で確認済みの設計)。
    """
    if suffix.lower() != ".md":
        return content
    text = content.decode(errors="replace")
    if not text.startswith("---"):
        return content
    end = text.find("\n---", 3)
    if end == -1:
        return content
    return text[end + 4:].encode()


def _file_body_hash(path: Path) -> str:
    """SHA256 of a single file's body (frontmatter-stripped for .md)."""
    raw = path.read_bytes()
    body = _body_content(raw, path.suffix)
    return hashlib.sha256(body).hexdigest()


def _git_head_sha(repo_root: Path) -> str:
    """Get current HEAD SHA. Falls back to 'no-git' if not in a git repo.

    Mixed into module hash to invalidate cache on branch switch — addresses
    a real failure mode in graphify v1 where same-content-different-branch
    cache entries collided.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True, timeout=5,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return "no-git"


def _module_files(module_path: Path, repo_root: Path) -> list[Path]:
    """Enumerate source files under a module path, excluding generated/cache dirs.

    module_path can resolve to either:
      - a file (single-file module like 'graphify/cache.py')
      - a directory (multi-file module)
      - a "stem" path that doesn't exist but has a .py/.ts/etc sibling
        (e.g. module_id 'graphify/cache' → tries 'graphify/cache.py')
    """
    abs_path = (repo_root / module_path).resolve()
    if abs_path.is_file():
        return [abs_path]
    if abs_path.is_dir():
        excluded = {".git", "__pycache__", "node_modules", "venv", ".venv", "dist", "build"}
        files: list[Path] = []
        for root, dirs, names in os.walk(abs_path, followlinks=False):
            dirs[:] = [d for d in dirs if d not in excluded and not d.startswith(".")]
            for n in names:
                p = Path(root) / n
                if p.suffix.lower() in {".pyc", ".pyo", ".so", ".dll"}:
                    continue
                files.append(p)
        return sorted(files)
    # Stem fallback: try common source extensions next to the path
    for ext in (".py", ".ts", ".tsx", ".js", ".go", ".rs", ".java"):
        candidate = abs_path.with_suffix(ext)
        if candidate.is_file():
            return [candidate]
    return []


def module_hash(
    module_id: str,
    module_path: str | Path | None = None,
    repo_root: Path = Path("."),
) -> str:
    """Compute the cache key for a module.

    Combines (sorted body hashes of all module files) + (repo HEAD SHA)
    + (cache schema version). Stable across machines, sensitive to:
      - any source file content change (except .md frontmatter)
      - branch switch (via HEAD SHA)
      - cache.py spec change (via CACHE_SCHEMA_VERSION)
    """
    repo_root = Path(repo_root).resolve()
    if module_path is None:
        # Fall back to module_id as relative path
        module_path = module_id
    files = _module_files(Path(module_path), repo_root)

    h = hashlib.sha256()
    h.update(CACHE_SCHEMA_VERSION.encode())
    h.update(b"\x00")
    h.update(_git_head_sha(repo_root).encode())
    h.update(b"\x00")
    for f in files:
        try:
            h.update(_file_body_hash(f).encode())
            h.update(b"\x00")
        except OSError:
            continue
    return h.hexdigest()


def _entry_path(module_id: str, kind: ArtifactKind, repo_root: Path) -> Path:
    """Resolve the cache file path for (module, kind).

    Layout: .claude/cache/<kind>/<module-flat>/<hash>.json
    The module-flat directory groups all hash variants of one module so
    we can prune stale variants in one sweep.
    """
    if kind not in _VALID_KINDS:
        raise ValueError(f"invalid kind {kind!r}, expected one of {_VALID_KINDS}")
    flat = module_id.replace("/", "__").replace("\\", "__")
    h = module_hash(module_id, repo_root=repo_root)
    return repo_root / CACHE_ROOT / kind / flat / f"{h}.json"


def load_cached_artifact(
    module_id: str,
    kind: ArtifactKind,
    repo_root: Path = Path("."),
) -> dict | None:
    """Load a cached artifact for (module_id, kind). Returns None on miss.

    Cache is keyed on the current module hash, so a stale entry (different
    file contents or different branch) returns None automatically.
    """
    try:
        entry = _entry_path(module_id, kind, repo_root)
    except (ValueError, OSError):
        return None
    if not entry.exists():
        return None
    try:
        return json.loads(entry.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_cached_artifact(
    module_id: str,
    kind: ArtifactKind,
    payload: dict,
    repo_root: Path = Path("."),
) -> Path:
    """Save an artifact for (module_id, kind). Returns the written path.

    Atomic: writes to .tmp first, then os.replace (with copy fallback for
    Windows file-lock race — same lesson as graphify cache.py:79-89).
    """
    entry = _entry_path(module_id, kind, repo_root)
    entry.parent.mkdir(parents=True, exist_ok=True)
    tmp = entry.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        try:
            os.replace(tmp, entry)
        except PermissionError:
            import shutil
            shutil.copy2(tmp, entry)
            tmp.unlink(missing_ok=True)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return entry


def is_cached(
    module_id: str,
    kind: ArtifactKind,
    repo_root: Path = Path("."),
) -> bool:
    """Cheap check: does a cached artifact exist for (module_id, kind)?"""
    try:
        return _entry_path(module_id, kind, repo_root).exists()
    except (ValueError, OSError):
        return False


def cached_modules(
    kind: ArtifactKind,
    repo_root: Path = Path("."),
) -> set[str]:
    """Return set of module_ids that have a valid cache entry for `kind`.

    Iterates the cache directory and returns module names whose CURRENT
    hash matches a stored entry (so renamed/deleted/edited modules are
    excluded automatically).
    """
    base = (repo_root / CACHE_ROOT / kind).resolve()
    if not base.exists():
        return set()
    hits: set[str] = set()
    for flat_dir in base.iterdir():
        if not flat_dir.is_dir():
            continue
        module_id = flat_dir.name.replace("__", "/")
        if is_cached(module_id, kind, repo_root):
            hits.add(module_id)
    return hits


def clear_cache(
    kind: ArtifactKind | None = None,
    repo_root: Path = Path("."),
) -> int:
    """Delete cache entries. Returns count of files removed.

    kind=None clears all; otherwise only the named kind.
    """
    base = (repo_root / CACHE_ROOT).resolve()
    if not base.exists():
        return 0
    targets = [base / k for k in _VALID_KINDS] if kind is None else [base / kind]
    count = 0
    for t in targets:
        if not t.exists():
            continue
        for f in t.rglob("*.json"):
            f.unlink()
            count += 1
    return count


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: cache.py <module-id> [module-path]", file=sys.stderr)
        raise SystemExit(2)
    mid = sys.argv[1]
    mp = sys.argv[2] if len(sys.argv) > 2 else None
    print(module_hash(mid, mp))
