#!/usr/bin/env python3
"""
Tribal v2 Phase 5 単体テスト: benchmark.py + check_router_state.py

検証観点:
  T1 estimate_tokens: 4 chars/token 近似
  T2 naive_baseline_tokens: 全 .md 集計、_ から始まるものは除外
  T3 routed_tokens: 指定 file のみ集計
  T4 run_benchmark dry-run: 標準サンプルで動作
  T5 ratio 計算: baseline / routed
  T6 check_router_state: opted_out → passthrough
  T7 check_router_state: 直近 routing → passthrough
  T8 check_router_state: stale + context Read → warning 出力
  T9 check_router_state: routing-table.json 等 index file は warning 対象外
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import benchmark as bm  # noqa: E402
import check_router_state as crs  # noqa: E402


def _setup_context_dir(tmp: Path) -> Path:
    cdir = tmp / ".claude/context"
    cdir.mkdir(parents=True)
    (cdir / "mod_a.md").write_text("# A\n" + "x" * 400)  # ~100 tokens
    (cdir / "mod_b.md").write_text("# B\n" + "y" * 800)  # ~200 tokens
    (cdir / "mod_c.md").write_text("# C\n" + "z" * 200)  # ~50 tokens
    (cdir / "_repo-map.json").write_text("{}")  # should be excluded
    return cdir


def t1_estimate_tokens():
    assert bm.estimate_tokens("") == 1, "min 1 token"
    assert bm.estimate_tokens("x" * 4) == 1
    assert bm.estimate_tokens("x" * 400) == 100
    print("  ✓ T1 estimate_tokens (4 chars/token)")


def t2_naive_baseline():
    with tempfile.TemporaryDirectory() as d:
        cdir = _setup_context_dir(Path(d))
        total = bm.naive_baseline_tokens(cdir)
        # mod_a (~101 tok) + mod_b (~201 tok) + mod_c (~51 tok); _repo-map excluded
        assert 340 <= total <= 360, f"baseline = {total}, expected ~350"
    print(f"  ✓ T2 naive_baseline excludes _-prefixed files ({total} tokens)")


def t3_routed_tokens():
    with tempfile.TemporaryDirectory() as d:
        cdir = _setup_context_dir(Path(d))
        # Only mod_a + mod_c
        total = bm.routed_tokens(["mod_a.md", "mod_c.md"], cdir)
        assert 145 <= total <= 160, f"routed = {total}, expected ~150"
    print(f"  ✓ T3 routed_tokens (subset only, {total} tokens)")


def t4_run_benchmark_dry_run():
    with tempfile.TemporaryDirectory() as d:
        cdir = _setup_context_dir(Path(d))
        rt_path = Path(d) / "routing.json"
        rt_path.write_text(json.dumps({
            "intents": [
                {"name": "feature-add", "primary_contexts": ["mod_a.md"], "secondary_contexts": []},
                {"name": "schema-change", "primary_contexts": ["mod_b.md", "mod_c.md"], "secondary_contexts": []},
                {"name": "bug-fix", "primary_contexts": ["mod_a.md"], "secondary_contexts": []},
                {"name": "ops-investigation", "primary_contexts": ["mod_b.md"], "secondary_contexts": []},
                {"name": "validation-change", "primary_contexts": ["mod_c.md"], "secondary_contexts": []},
            ],
            "fallback": {"primary_contexts": ["mod_a.md"]}
        }))
        result = bm.run_benchmark(Path(d) / "missing.json", cdir,
                                   rt_path, dry_run=True)
        assert result["summary"]["total_cases"] == 5
        assert result["summary"]["baseline_tokens"] > 0
        assert result["summary"]["avg_ratio"] is not None and result["summary"]["avg_ratio"] > 1.0
    print(f"  ✓ T4 dry-run: 5 cases, avg_ratio={result['summary']['avg_ratio']}x")


def t5_ratio_calculation():
    """baseline 1000 / routed 100 = 10.0x."""
    with tempfile.TemporaryDirectory() as d:
        cdir = Path(d) / "ctx"
        cdir.mkdir()
        # 1 large + 1 small
        (cdir / "big.md").write_text("x" * 3600)  # ~900 tokens
        (cdir / "small.md").write_text("x" * 400)  # ~100 tokens
        # baseline = 1000, routed (small only) = 100, ratio = 10.0
        baseline = bm.naive_baseline_tokens(cdir)
        routed = bm.routed_tokens(["small.md"], cdir)
        ratio = baseline / routed
        assert 9.0 <= ratio <= 11.0, f"ratio={ratio}"
    print(f"  ✓ T5 ratio = baseline/routed = {ratio:.1f}x")


def _run_hook(tool_name: str, tool_input: dict, session_state: dict | None = None) -> tuple[int, str]:
    """check_router_state を直接呼び出して exit code と stdout 取得."""
    payload = json.dumps({"tool_name": tool_name, "tool_input": tool_input})
    captured = io.StringIO()
    old_stdin = sys.stdin
    old_stdout = sys.stdout
    sys.stdin = io.StringIO(payload)
    sys.stdout = captured
    # patch session loader
    with patch.object(crs, "load_session_state", return_value=(session_state or {})):
        try:
            ec = crs.main()
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout
    return ec, captured.getvalue()


def t6_opted_out():
    ec, out = _run_hook("Read", {"file_path": "/proj/.claude/context/foo.md"},
                         session_state={"opted_out": True})
    assert ec == 0
    assert json.loads(out) == {}, "opted_out should produce empty passthrough"
    print("  ✓ T6 opted_out → passthrough")


def t7_recent_routing():
    ec, out = _run_hook("Read", {"file_path": "/proj/.claude/context/foo.md"},
                         session_state={"last_routing_ts": time.time() - 60})
    assert json.loads(out) == {}
    print("  ✓ T7 recent routing (60s ago) → passthrough")


def t8_stale_session_warning():
    ec, out = _run_hook("Read", {"file_path": "/proj/.claude/context/foo.md"},
                         session_state={"last_routing_ts": time.time() - 3601})
    parsed = json.loads(out)
    assert "hookSpecificOutput" in parsed, f"expected warning, got: {parsed}"
    msg = parsed["hookSpecificOutput"]["additionalContext"]
    assert "router 未起動" in msg or "router state warning" in msg
    print("  ✓ T8 stale session + context Read → warning injected")


def t9_index_file_not_warned():
    ec, out = _run_hook("Read", {"file_path": "/proj/.claude/context/_routing-table.json"},
                         session_state={})
    assert json.loads(out) == {}, "index file Read should NOT trigger warning"
    print("  ✓ T9 _routing-table.json read → no warning (index file allowed)")


if __name__ == "__main__":
    tests = [t1_estimate_tokens, t2_naive_baseline, t3_routed_tokens,
             t4_run_benchmark_dry_run, t5_ratio_calculation,
             t6_opted_out, t7_recent_routing, t8_stale_session_warning,
             t9_index_file_not_warned]
    print(f"Running {len(tests)} tests for tribal-v2 Phase 5:")
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
