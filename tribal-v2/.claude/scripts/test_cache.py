#!/usr/bin/env python3
"""
Tribal v2 cache.py 単体テスト (pytest 不要、`python3 test_cache.py` で完結)。

検証観点 (Phase 1 checklist 1.3):
  T1 同一内容ファイルのハッシュ一致
  T2 frontmatter 違いで hash 一致 (.md のみ)
  T3 frontmatter 違いで hash 不一致 (.py 等)
  T4 HEAD SHA 違いで hash 不一致 (mock で)
  T5 load → save → load 往復
  T6 invalid kind は ValueError
  T7 cached_modules() が現在 hash に整合する module のみ返す
  T8 clear_cache() で削除カウントと実体一致
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

# Allow running this file standalone
sys.path.insert(0, str(Path(__file__).parent))
import cache  # noqa: E402


def _setup_repo(tmp: Path) -> Path:
    """Create a fake repo with one module containing 2 files."""
    mod = tmp / "graphify" / "cache"
    mod.mkdir(parents=True)
    (mod / "__init__.py").write_text("# init\n")
    (mod / "core.py").write_text("def cached(): return 42\n")
    return tmp


def _patch_head(sha: str):
    """Mock _git_head_sha to return a deterministic value."""
    return patch.object(cache, "_git_head_sha", return_value=sha)


# ---- Tests ------------------------------------------------------------------

def t1_same_content_same_hash():
    """T1: 同一内容のファイル群で hash 一致。"""
    with tempfile.TemporaryDirectory() as d:
        root = _setup_repo(Path(d))
        with _patch_head("sha-fixed"):
            h1 = cache.module_hash("graphify/cache", repo_root=root)
            h2 = cache.module_hash("graphify/cache", repo_root=root)
        assert h1 == h2, f"hash drift: {h1} vs {h2}"
    print("  ✓ T1 same content → same hash")


def t2_md_frontmatter_ignored():
    """T2: .md の YAML frontmatter のみ違うと hash 一致。"""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        mod = root / "docs"
        mod.mkdir()
        f = mod / "x.md"
        f.write_text("---\ntags: [a]\n---\nbody content\n")
        with _patch_head("s"):
            h1 = cache.module_hash("docs", repo_root=root)
        f.write_text("---\ntags: [b, c]\nstatus: reviewed\n---\nbody content\n")
        with _patch_head("s"):
            h2 = cache.module_hash("docs", repo_root=root)
        assert h1 == h2, "frontmatter-only diff should NOT change hash"
    print("  ✓ T2 .md frontmatter-only edit → same hash")


def t3_py_content_change_invalidates():
    """T3: .py の本文変更で hash 不一致 (frontmatter ロジックは .py に適用されない)。"""
    with tempfile.TemporaryDirectory() as d:
        root = _setup_repo(Path(d))
        with _patch_head("s"):
            h1 = cache.module_hash("graphify/cache", repo_root=root)
        (root / "graphify" / "cache" / "core.py").write_text("def cached(): return 999\n")
        with _patch_head("s"):
            h2 = cache.module_hash("graphify/cache", repo_root=root)
        assert h1 != h2, "py body change MUST change hash"
    print("  ✓ T3 .py content change → hash differs")


def t4_branch_switch_invalidates():
    """T4: HEAD SHA 違いで hash 不一致 (branch 切替えシミュレート)。"""
    with tempfile.TemporaryDirectory() as d:
        root = _setup_repo(Path(d))
        with _patch_head("sha-A"):
            h1 = cache.module_hash("graphify/cache", repo_root=root)
        with _patch_head("sha-B"):
            h2 = cache.module_hash("graphify/cache", repo_root=root)
        assert h1 != h2, "different HEAD SHA MUST change hash"
    print("  ✓ T4 branch switch (HEAD diff) → hash differs")


def t5_save_load_roundtrip():
    """T5: save → load で payload が完全復元される。"""
    with tempfile.TemporaryDirectory() as d:
        root = _setup_repo(Path(d))
        payload = {"module": "graphify/cache", "Q1": "テスト", "values": [1, 2, 3]}
        with _patch_head("s"):
            cache.save_cached_artifact("graphify/cache", "analyst", payload, repo_root=root)
            loaded = cache.load_cached_artifact("graphify/cache", "analyst", repo_root=root)
        assert loaded == payload, f"roundtrip mismatch: {loaded}"
        # And after content change, load returns None
        (root / "graphify" / "cache" / "core.py").write_text("changed\n")
        with _patch_head("s"):
            stale = cache.load_cached_artifact("graphify/cache", "analyst", repo_root=root)
        assert stale is None, "stale entry should miss"
    print("  ✓ T5 save → load roundtrip + stale invalidation")


def t6_invalid_kind_raises():
    """T6: 不正な kind で ValueError。"""
    with tempfile.TemporaryDirectory() as d:
        root = _setup_repo(Path(d))
        try:
            cache.save_cached_artifact("graphify/cache", "bogus", {}, repo_root=root)  # type: ignore
        except ValueError as e:
            assert "invalid kind" in str(e)
            print("  ✓ T6 invalid kind → ValueError")
            return
        raise AssertionError("expected ValueError")


def t7_cached_modules_listing():
    """T7: cached_modules() は現在 hash に一致する entry の module のみ返す。"""
    with tempfile.TemporaryDirectory() as d:
        root = _setup_repo(Path(d))
        # Create a second module
        mod2 = root / "graphify" / "other"
        mod2.mkdir(parents=True)
        (mod2 / "x.py").write_text("pass\n")
        with _patch_head("s"):
            cache.save_cached_artifact("graphify/cache", "analyst", {"a": 1}, repo_root=root)
            cache.save_cached_artifact("graphify/other", "analyst", {"b": 2}, repo_root=root)
            mods = cache.cached_modules("analyst", repo_root=root)
        assert mods == {"graphify/cache", "graphify/other"}, f"unexpected: {mods}"
        # Invalidate one and re-check
        (root / "graphify" / "cache" / "core.py").write_text("changed\n")
        with _patch_head("s"):
            mods2 = cache.cached_modules("analyst", repo_root=root)
        assert mods2 == {"graphify/other"}, f"expected stale-filtered, got: {mods2}"
    print("  ✓ T7 cached_modules() filters stale entries")


def t8_clear_cache_counts():
    """T8: clear_cache() の戻り値と実ファイル消失が一致。"""
    with tempfile.TemporaryDirectory() as d:
        root = _setup_repo(Path(d))
        with _patch_head("s"):
            cache.save_cached_artifact("graphify/cache", "analyst", {"a": 1}, repo_root=root)
            cache.save_cached_artifact("graphify/cache", "critic", {"b": 2}, repo_root=root)
            n = cache.clear_cache("analyst", repo_root=root)
        assert n == 1, f"expected 1, got {n}"
        # critic should remain
        with _patch_head("s"):
            assert cache.is_cached("graphify/cache", "critic", repo_root=root)
            assert not cache.is_cached("graphify/cache", "analyst", repo_root=root)
            n_all = cache.clear_cache(repo_root=root)
        assert n_all == 1, f"expected 1 remaining (critic), got {n_all}"
    print("  ✓ T8 clear_cache() count matches deletions")


# ---- Runner -----------------------------------------------------------------

if __name__ == "__main__":
    tests = [t1_same_content_same_hash, t2_md_frontmatter_ignored,
             t3_py_content_change_invalidates, t4_branch_switch_invalidates,
             t5_save_load_roundtrip, t6_invalid_kind_raises,
             t7_cached_modules_listing, t8_clear_cache_counts]
    print(f"Running {len(tests)} tests for tribal-v2 cache.py:")
    failures = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failures.append((t.__name__, str(e)))
            print(f"  ✗ {t.__name__}: {e}")
        except Exception as e:
            failures.append((t.__name__, f"{type(e).__name__}: {e}"))
            print(f"  ✗ {t.__name__}: {type(e).__name__}: {e}")
    print()
    if failures:
        print(f"FAIL: {len(failures)}/{len(tests)} test(s) failed")
        raise SystemExit(1)
    print(f"PASS: {len(tests)}/{len(tests)} tests")
