#!/usr/bin/env python3
"""
Quality regression gate for CI.

Compares the current quality scores in `.claude/context/_quality-log.jsonl`
against the baseline (typically main branch) and fails the build if average
score regression exceeds the threshold.

Usage:
    python .claude/scripts/check_quality_regression.py \
        --baseline-ref main \
        --threshold 0.3
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from pathlib import Path


QUALITY_LOG = Path(".claude/context/_quality-log.jsonl")


def parse_log(text: str) -> dict[str, float]:
    """Return {file: latest_score} from a JSONL log.

    Tribal v2: prefer `weighted_overall` over `overall` when available
    (weighted_overall reflects path_accuracy / non_obvious_value 2x weighting,
    which is the actual gating decision from critic).
    Falls back to `overall` for v1 entries.
    """
    latest: dict[str, tuple[str, float]] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        f = row.get("file") or row.get("module")
        ts = row.get("timestamp", "")
        # v2 preference: weighted_overall > overall (fallback for v1)
        score = row.get("weighted_overall")
        if score is None:
            score = row.get("overall")
        if f is None or score is None:
            continue
        if f not in latest or ts > latest[f][0]:
            latest[f] = (ts, float(score))
    return {f: v[1] for f, v in latest.items()}


def read_current() -> dict[str, float]:
    if not QUALITY_LOG.exists():
        return {}
    return parse_log(QUALITY_LOG.read_text(encoding="utf-8"))


def read_baseline(ref: str) -> dict[str, float] | None:
    """Read the quality log from the given git ref. None if unavailable."""
    try:
        out = subprocess.run(
            ["git", "show", f"{ref}:{QUALITY_LOG}"],
            capture_output=True, text=True, check=True,
        )
        return parse_log(out.stdout)
    except subprocess.CalledProcessError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-ref", default="main")
    parser.add_argument("--threshold", type=float, default=0.3,
                        help="Maximum allowed avg score drop")
    parser.add_argument("--per-file-threshold", type=float, default=0.5,
                        help="Maximum allowed per-file score drop")
    parser.add_argument("--min-absolute", type=float, default=3.5,
                        help="Hard floor: any file below this fails")
    args = parser.parse_args()

    current = read_current()
    if not current:
        print("No current quality log; skipping regression check.", file=sys.stderr)
        return 0

    baseline = read_baseline(args.baseline_ref)
    if baseline is None:
        print(f"No baseline at {args.baseline_ref}; skipping regression check.",
              file=sys.stderr)
        # Still check absolute floor
        below = [(f, s) for f, s in current.items() if s < args.min_absolute]
        if below:
            print(f"FAIL: {len(below)} files below absolute floor {args.min_absolute}:",
                  file=sys.stderr)
            for f, s in below:
                print(f"  - {f}: {s}", file=sys.stderr)
            return 1
        return 0

    cur_avg = statistics.mean(current.values())
    base_avg = statistics.mean(baseline.values()) if baseline else cur_avg

    print(f"Baseline avg: {base_avg:.3f}")
    print(f"Current avg:  {cur_avg:.3f}")
    print(f"Delta:        {cur_avg - base_avg:+.3f}")

    failures: list[str] = []

    if base_avg - cur_avg > args.threshold:
        failures.append(
            f"Average score dropped by {base_avg - cur_avg:.3f} "
            f"(threshold {args.threshold})"
        )

    for f, cur_score in current.items():
        base_score = baseline.get(f)
        if base_score is None:
            continue
        if base_score - cur_score > args.per_file_threshold:
            failures.append(
                f"  {f}: {base_score:.2f} -> {cur_score:.2f} "
                f"(drop {base_score - cur_score:.2f})"
            )

    below_floor = [(f, s) for f, s in current.items() if s < args.min_absolute]
    if below_floor:
        failures.append(f"{len(below_floor)} files below absolute floor {args.min_absolute}:")
        for f, s in below_floor:
            failures.append(f"  {f}: {s:.2f}")

    if failures:
        print("\nQuality regression detected:", file=sys.stderr)
        for msg in failures:
            print(msg, file=sys.stderr)
        return 1

    print("Quality OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
