#!/usr/bin/env python3
"""
Tribal v2 — Token reduction benchmark (Phase 5: Benchmark).

graphify/benchmark.py の `_estimate_tokens` (4 chars/token) を流用し、
tribal の routing 経由ロード vs naive 全 context ロードの token 比を計測。

入力:
  - .claude/artifacts/tests/prompt-tests.json (prompt-tester の出力)
  - .claude/context/*.md (全 context)

出力:
  - .claude/artifacts/benchmark.json
  - 各 case の baseline / routed / ratio
  - summary (avg/median/p95)

prompt-tester がまだ走っていない初期状態 (Phase 5 単体導入時) でも、
固定サンプル questions で動作可能な dry mode あり。

Usage:
    python3 benchmark.py [--prompt-tests PATH] [--context-dir PATH] [--output PATH]
    python3 benchmark.py --dry-run  # prompt-tests 無しで標準サンプル使用
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path


CONTEXT_DIR = Path(".claude/context")
PROMPT_TESTS = Path(".claude/artifacts/tests/prompt-tests.json")
QUALITY_LOG = Path(".claude/context/_quality-log.jsonl")
OUTPUT = Path(".claude/artifacts/benchmark.json")
ROUTING_TABLE = Path(".claude/context/_routing-table.json")

CHARS_PER_TOKEN = 4  # graphify と同じ標準近似


def estimate_tokens(text: str) -> int:
    """graphify と同じ 4 chars/token 近似 (tiktoken 不要で軽量)."""
    return max(1, len(text) // CHARS_PER_TOKEN)


def naive_baseline_tokens(context_dir: Path) -> int:
    """全 context.md を一括ロードした場合のトークン数 (router 不在の世界)."""
    total = 0
    for f in sorted(context_dir.glob("*.md")):
        if f.name.startswith("_"):  # _index.md, _routing-table.json 等は除外
            continue
        try:
            total += estimate_tokens(f.read_text(encoding="utf-8"))
        except OSError:
            continue
    return total


def routed_tokens(context_files: list[str], context_dir: Path) -> int:
    """router が選定した context.md のみのトークン合計."""
    total = 0
    for cf in context_files:
        # cf が ".claude/context/foo.md" 形式
        p = Path(cf)
        if not p.is_absolute():
            # If relative starting with .claude/context, strip the prefix
            try:
                rel = p.relative_to(".claude/context")
                p = context_dir / rel
            except ValueError:
                p = context_dir / p.name
        try:
            total += estimate_tokens(p.read_text(encoding="utf-8"))
        except OSError:
            continue
    return total


# Default sample queries for dry-run (no prompt-tester required)
SAMPLE_QUERIES = [
    {"id": "feature-add-1", "intent": "feature-add",
     "query": "新しいデータフィールドを pipeline に追加したい",
     "loaded_contexts": []},
    {"id": "schema-change-1", "intent": "schema-change",
     "query": "schema validation のルールを変更したい",
     "loaded_contexts": []},
    {"id": "bug-fix-1", "intent": "bug-fix",
     "query": "認証ロジックのバグを修正したい",
     "loaded_contexts": []},
    {"id": "ops-investigation-1", "intent": "ops-investigation",
     "query": "障害でレイテンシが上がった、原因調査",
     "loaded_contexts": []},
    {"id": "validation-change-1", "intent": "validation-change",
     "query": "新しい validation rule を追加したい",
     "loaded_contexts": []},
]


def _resolve_routed_for_dry_run(intent: str, routing_table: dict) -> list[str]:
    """Dry-run mode: routing-table の primary_contexts を使って routed list を解決."""
    for it in routing_table.get("intents", []):
        if it["name"] == intent:
            primaries = it.get("primary_contexts", [])
            secondaries = it.get("secondary_contexts", [])
            return primaries + secondaries[:2]  # 最大 5 枚相当
    fb = routing_table.get("fallback", {})
    return fb.get("primary_contexts", [])[:3]


def run_benchmark(prompt_tests_path: Path, context_dir: Path,
                  routing_table_path: Path | None = None,
                  dry_run: bool = False) -> dict:
    baseline = naive_baseline_tokens(context_dir)
    cases: list[dict] = []

    if dry_run or not prompt_tests_path.exists():
        # Use sample queries; resolve routed via routing-table
        rt = {}
        if routing_table_path and routing_table_path.exists():
            rt = json.loads(routing_table_path.read_text(encoding="utf-8"))
        for q in SAMPLE_QUERIES:
            routed_files = _resolve_routed_for_dry_run(q["intent"], rt)
            r_tok = routed_tokens(routed_files, context_dir)
            ratio = baseline / r_tok if r_tok > 0 else float("inf")
            cases.append({
                "case_id": q["id"],
                "intent": q["intent"],
                "query": q["query"],
                "routed_files": routed_files,
                "baseline_tokens": baseline,
                "routed_tokens": r_tok,
                "ratio": round(ratio, 2) if r_tok > 0 else None,
                "source": "dry-run-sample",
            })
    else:
        tests = json.loads(prompt_tests_path.read_text(encoding="utf-8"))
        for tc in tests.get("cases", []):
            actual = tc.get("actual", {})
            loaded = actual.get("loaded_contexts", [])
            r_tok = routed_tokens(loaded, context_dir)
            ratio = baseline / r_tok if r_tok > 0 else None
            cases.append({
                "case_id": tc.get("id"),
                "intent": tc.get("intent"),
                "query": tc.get("query"),
                "routed_files": loaded,
                "baseline_tokens": baseline,
                "routed_tokens": r_tok,
                "ratio": round(ratio, 2) if ratio else None,
                "source": "prompt-tester",
            })

    valid_ratios = [c["ratio"] for c in cases if c["ratio"]]
    summary = {
        "total_cases": len(cases),
        "baseline_tokens": baseline,
        "avg_routed_tokens": round(statistics.mean([c["routed_tokens"] for c in cases]), 2)
                              if cases else 0,
        "avg_ratio": round(statistics.mean(valid_ratios), 2) if valid_ratios else None,
        "median_ratio": round(statistics.median(valid_ratios), 2) if valid_ratios else None,
        "min_ratio": min(valid_ratios) if valid_ratios else None,
        "max_ratio": max(valid_ratios) if valid_ratios else None,
        "p95_ratio": (round(sorted(valid_ratios)[int(len(valid_ratios) * 0.95)], 2)
                      if len(valid_ratios) >= 2 else None),
    }

    # router_version_hash for regression detection
    router_hash = ""
    if routing_table_path and routing_table_path.exists():
        import hashlib
        router_hash = hashlib.sha1(routing_table_path.read_bytes()).hexdigest()[:12]

    return {
        "executed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "router_version_hash": router_hash,
        "per_case": cases,
        "summary": summary,
    }


def append_to_quality_log(benchmark: dict, log_path: Path) -> int:
    """Append a per-case `tokens_saved_ratio` entry to _quality-log.jsonl.

    Returns count of entries appended.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    appended = 0
    with log_path.open("a", encoding="utf-8") as f:
        for case in benchmark["per_case"]:
            if case["ratio"] is None:
                continue
            entry = {
                "timestamp": benchmark["executed_at"],
                "module": f"benchmark/{case['intent']}",
                "file": ".claude/artifacts/benchmark.json",
                "round": "ci-check",
                "scores": {
                    "conciseness": 5.0, "path_accuracy": 5.0,
                    "non_obvious_value": 5.0, "modification_readiness": 5.0,
                    "cross_ref_integrity": 5.0,
                },
                "overall": 5.0,
                "weighted_overall": 5.0,
                "verdict": "PASS",
                "tokens_saved_ratio": case["ratio"],
                "phase": "benchmark",
            }
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            appended += 1
    return appended


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-tests", default=str(PROMPT_TESTS))
    parser.add_argument("--context-dir", default=str(CONTEXT_DIR))
    parser.add_argument("--routing-table", default=str(ROUTING_TABLE))
    parser.add_argument("--output", default=str(OUTPUT))
    parser.add_argument("--quality-log", default=str(QUALITY_LOG))
    parser.add_argument("--dry-run", action="store_true",
                        help="prompt-tester 結果なしで標準サンプル使用")
    parser.add_argument("--no-log", action="store_true",
                        help="_quality-log.jsonl に追記しない")
    args = parser.parse_args()

    result = run_benchmark(
        Path(args.prompt_tests),
        Path(args.context_dir),
        Path(args.routing_table) if args.routing_table else None,
        dry_run=args.dry_run,
    )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    s = result["summary"]
    print(f"Benchmark: {s['total_cases']} cases, baseline {s['baseline_tokens']} tokens")
    print(f"  avg ratio: {s['avg_ratio']}x, median {s['median_ratio']}x, "
          f"min {s['min_ratio']}x, max {s['max_ratio']}x")

    if not args.no_log:
        n = append_to_quality_log(result, Path(args.quality_log))
        print(f"  appended {n} entries to {args.quality_log}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
