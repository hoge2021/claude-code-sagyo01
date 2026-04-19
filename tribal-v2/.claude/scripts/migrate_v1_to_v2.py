#!/usr/bin/env python3
"""
Tribal v1 → v2 artifact migration script.

実施する変換:
  1. analyst JSON: Q3 各項目に confidence=EXTRACTED, confidence_score=1.0 を充当
     (v1 では confidence の概念が無く、人手記述だったため一律 EXTRACTED 扱い)
  2. critic JSON: weighted_overall を計算して追加 (path_accuracy=2x, non_obvious=2x)
  3. critic JSON: ambiguous_q3_count を 0 で初期化
  4. _quality-log.jsonl: 既存 entry に weighted_overall / cache_hit=False を追加

idempotent: 既に v2 化されていれば skip。

Usage:
    python3 .claude/scripts/migrate_v1_to_v2.py [--dry-run] [--root <repo_root>]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ANALYST_DIR = Path(".claude/artifacts/analyst")
CRITIC_DIR = Path(".claude/artifacts/critic")
QUALITY_LOG = Path(".claude/context/_quality-log.jsonl")

AXIS_WEIGHTS = {
    "path_accuracy": 2.0,
    "non_obvious_value": 2.0,
    "conciseness": 1.0,
    "modification_readiness": 1.0,
    "cross_ref_integrity": 1.0,
    "confidence_consistency": 1.0,
}


def weighted_average(scores: dict) -> float:
    total_w = 0.0
    total_s = 0.0
    for k, v in scores.items():
        w = AXIS_WEIGHTS.get(k, 1.0)
        total_w += w
        total_s += float(v) * w
    return round(total_s / total_w, 3) if total_w > 0 else 0.0


def migrate_analyst(path: Path, dry_run: bool) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    changed = False
    q3 = data.get("Q3_non_obvious_patterns", []) or []
    for item in q3:
        if "confidence" not in item:
            item["confidence"] = "EXTRACTED"
            changed = True
        if "confidence_score" not in item:
            item["confidence_score"] = 1.0
            changed = True
    if not changed:
        return "skip"
    if not dry_run:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return "migrated"


def migrate_critic(path: Path, dry_run: bool) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    changed = False
    if "weighted_overall" not in data and "scores" in data:
        data["weighted_overall"] = weighted_average(data["scores"])
        changed = True
    if "ambiguous_q3_count" not in data:
        data["ambiguous_q3_count"] = 0
        changed = True
    if not changed:
        return "skip"
    if not dry_run:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return "migrated"


def migrate_quality_log(path: Path, dry_run: bool) -> tuple[int, int]:
    """Returns (migrated_count, skipped_count)."""
    if not path.exists():
        return (0, 0)
    text = path.read_text(encoding="utf-8")
    new_lines: list[str] = []
    migrated = 0
    skipped = 0
    for line in text.splitlines():
        s = line.strip()
        if not s:
            new_lines.append(line)
            continue
        try:
            row = json.loads(s)
        except json.JSONDecodeError:
            new_lines.append(line)
            continue
        changed = False
        if "weighted_overall" not in row and "scores" in row:
            row["weighted_overall"] = weighted_average(row["scores"])
            changed = True
        if "cache_hit" not in row:
            row["cache_hit"] = False
            changed = True
        if changed:
            migrated += 1
        else:
            skipped += 1
        new_lines.append(json.dumps(row, ensure_ascii=False))
    if migrated > 0 and not dry_run:
        path.write_text("\n".join(new_lines) + ("\n" if text.endswith("\n") else ""),
                        encoding="utf-8")
    return (migrated, skipped)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--root", default=".")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    analyst_dir = root / ANALYST_DIR
    critic_dir = root / CRITIC_DIR
    quality_log = root / QUALITY_LOG

    print(f"Migration {'DRY RUN' if args.dry_run else 'LIVE'} on {root}")
    print()

    # Analyst
    a_migrated = a_skipped = 0
    if analyst_dir.exists():
        for f in sorted(analyst_dir.glob("*.json")):
            try:
                result = migrate_analyst(f, args.dry_run)
                if result == "migrated":
                    a_migrated += 1
                else:
                    a_skipped += 1
            except (json.JSONDecodeError, OSError) as e:
                print(f"  ! analyst {f.name}: {e}", file=sys.stderr)
    print(f"analyst: {a_migrated} migrated, {a_skipped} skipped (already v2)")

    # Critic
    c_migrated = c_skipped = 0
    if critic_dir.exists():
        for f in sorted(critic_dir.glob("*.json")):
            try:
                result = migrate_critic(f, args.dry_run)
                if result == "migrated":
                    c_migrated += 1
                else:
                    c_skipped += 1
            except (json.JSONDecodeError, OSError) as e:
                print(f"  ! critic {f.name}: {e}", file=sys.stderr)
    print(f"critic:  {c_migrated} migrated, {c_skipped} skipped (already v2)")

    # Quality log
    q_migrated, q_skipped = migrate_quality_log(quality_log, args.dry_run)
    print(f"quality-log: {q_migrated} migrated, {q_skipped} skipped (already v2)")

    if args.dry_run:
        print()
        print("DRY RUN — no files written. Re-run without --dry-run to apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
