#!/usr/bin/env python3
"""
Module path flattening utility.

Converts a module path like 'repo_a/services/pipelines/validation' into a
filesystem-safe filename like 'repo_a__services__pipelines__validation'.
Long paths are truncated and suffixed with a SHA1 hash to keep filenames
under 60 characters.

Usage:
    python .claude/scripts/flatten_module_path.py <module-path>
    echo "<module-path>" | python .claude/scripts/flatten_module_path.py
"""

from __future__ import annotations

import hashlib
import sys


MAX_LEN = 60
HASH_LEN = 8


def flatten(module_id: str) -> str:
    flat = module_id.replace("/", "__").replace("\\", "__")
    if len(flat) > MAX_LEN:
        digest = hashlib.sha1(module_id.encode("utf-8")).hexdigest()[:HASH_LEN]
        # Reserve room for "__" + hash
        keep = MAX_LEN - HASH_LEN - 2
        flat = flat[:keep] + "__" + digest
    return flat


def unflatten_lookup(flat: str, repo_map: dict) -> str | None:
    """Given a flattened name and a repo-map, return the original module id."""
    for repo in repo_map.get("repos", []):
        for m in repo.get("modules", []):
            if flatten(m["id"]) == flat:
                return m["id"]
    return None


def main() -> int:
    if len(sys.argv) > 1:
        module_id = sys.argv[1]
    else:
        module_id = sys.stdin.read().strip()
    if not module_id:
        print("usage: flatten_module_path.py <module-path>", file=sys.stderr)
        return 2
    print(flatten(module_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
