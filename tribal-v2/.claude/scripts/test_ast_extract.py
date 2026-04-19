#!/usr/bin/env python3
"""
Tribal v2 ast_extract.py 単体テスト (pytest 不要、`python3 test_ast_extract.py`)。

検証観点 (Phase 2 checklist 2.4):
  T1-T5 各言語 (py, ts, go, rs, java) で imports / definitions / calls 抽出
  T6   未対応拡張子 (.md など) で空 JSON フォールバック
  T7   ディレクトリ全体抽出: 5 言語混在で files が全部出る
  T8   cache hit (2 回目で `_cache_hit: True`)
  T9   stem fallback (module_id "x" → x.py)
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import ast_extract  # noqa: E402
import cache  # noqa: E402

FIXTURE = Path(__file__).parent.parent.parent / "tests" / "fixtures" / "sample_module"


def _patch_head(sha: str = "test-sha"):
    return patch.object(cache, "_git_head_sha", return_value=sha)


def _check_lang(lang_label: str, file_name: str, min_imports: int, min_defs: int, min_calls: int):
    f = FIXTURE / file_name
    assert f.exists(), f"fixture missing: {f}"
    result = ast_extract.extract_file(f)
    assert result["lang"] == lang_label, f"lang mismatch: {result['lang']}"
    assert len(result["imports"]) >= min_imports, f"{lang_label}: imports={len(result['imports'])} < {min_imports}"
    assert len(result["definitions"]) >= min_defs, f"{lang_label}: defs={len(result['definitions'])} < {min_defs}"
    assert len(result["calls"]) >= min_calls, f"{lang_label}: calls={len(result['calls'])} < {min_calls}"
    print(f"  ✓ {lang_label}: {len(result['imports'])} imports, "
          f"{len(result['definitions'])} defs, {len(result['calls'])} calls")


def t1_python():
    _check_lang("python", "sample.py", min_imports=3, min_defs=4, min_calls=2)


def t2_typescript():
    _check_lang("typescript", "sample.ts", min_imports=2, min_defs=2, min_calls=2)


def t3_go():
    # Note: Go struct names are nested inside type_spec children of type_declaration,
    # so this min only counts the 3 function_declarations. Struct-name extraction
    # is a known limitation tracked for v2.1 (would need type_spec recursion).
    _check_lang("go", "sample.go", min_imports=1, min_defs=3, min_calls=2)


def t4_rust():
    _check_lang("rust", "sample.rs", min_imports=2, min_defs=3, min_calls=2)


def t5_java():
    _check_lang("java", "Sample.java", min_imports=3, min_defs=5, min_calls=2)


def t6_unsupported_extension():
    """T6: 未対応拡張子は空 JSON で fallback (analyst 側が処理可能)."""
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "x.md"
        f.write_text("# heading\n")
        result = ast_extract.extract_file(f)
        assert result["lang"] == "unsupported", f"expected unsupported, got {result['lang']}"
        assert result["imports"] == []
        assert result["definitions"] == []
        assert result["calls"] == []
    print(f"  ✓ T6 unsupported (.md) → empty fallback")


def t7_directory_extraction():
    """T7: ディレクトリ全体で 5 言語混在を抽出."""
    with _patch_head():
        result = ast_extract.extract_module("test/sample", FIXTURE,
                                              repo_root=FIXTURE.parent.parent,
                                              use_cache=False)
    langs = {f["lang"] for f in result["files"]}
    expected = {"python", "typescript", "go", "rust", "java"}
    assert langs >= expected, f"missing langs: {expected - langs}, got {langs}"
    assert result["stats"]["file_count"] >= 5
    assert result["stats"]["import_count"] >= 11  # sum of mins from T1-T5
    print(f"  ✓ T7 directory: {result['stats']}")


def t8_cache_hit():
    """T8: 2 回目で _cache_hit が True."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        mod = root / "test"
        mod.mkdir()
        (mod / "x.py").write_text("def f(): pass\n")
        with _patch_head():
            r1 = ast_extract.extract_module("test", "test/x.py", repo_root=root)
            r2 = ast_extract.extract_module("test", "test/x.py", repo_root=root)
        assert r1["_cache_hit"] is False, "first call should not be cache hit"
        assert r2["_cache_hit"] is True, "second call should be cache hit"
        # And contents match
        assert r1["definitions"] == r2["definitions"]
    print(f"  ✓ T8 cache miss → cache hit roundtrip")


def t9_stem_fallback():
    """T9: module_id 'foo' → 'foo.py' で resolve できる (cache.py と整合)."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "foo.py").write_text("def g(): pass\n")
        with _patch_head():
            r = ast_extract.extract_module("foo", "foo", repo_root=root, use_cache=False)
        # extract_module module_path passed as "foo" — _enumerate_module_files should fall back
        assert len(r["files"]) == 1, f"stem fallback failed: {r['files']}"
        assert r["files"][0]["lang"] == "python"
    print(f"  ✓ T9 stem fallback")


if __name__ == "__main__":
    tests = [t1_python, t2_typescript, t3_go, t4_rust, t5_java,
             t6_unsupported_extension, t7_directory_extraction, t8_cache_hit, t9_stem_fallback]
    print(f"Running {len(tests)} tests for tribal-v2 ast_extract.py:")
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
