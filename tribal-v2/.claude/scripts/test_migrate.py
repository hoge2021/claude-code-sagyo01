#!/usr/bin/env python3
"""
Tribal v2 migrate_v1_to_v2.py 単体テスト.

検証観点 (Phase 3 checklist 3.5):
  T1 v1 analyst (Q3 に confidence なし) → migrate で confidence=EXTRACTED, score=1.0 が充当
  T2 v1 critic (overall のみ) → migrate で weighted_overall 計算
  T3 v1 quality-log → migrate で weighted_overall + cache_hit=False 充当
  T4 idempotent: 既に v2 ならば skip
  T5 weighted_average の数値検証 (path_accuracy=2x, non_obvious=2x の効果)
  T6 dry-run でファイル変更されない
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import migrate_v1_to_v2 as mig  # noqa: E402


def _setup_v1(tmp: Path) -> Path:
    """Create v1-style artifact tree."""
    (tmp / ".claude/artifacts/analyst").mkdir(parents=True)
    (tmp / ".claude/artifacts/critic").mkdir(parents=True)
    (tmp / ".claude/context").mkdir(parents=True)

    # v1 analyst: Q3 に confidence なし
    analyst_v1 = {
        "module": "test/m1",
        "module_path": "test/m1.py",
        "analyzed_at": "2026-04-19T00:00:00Z",
        "files_read": ["test/m1.py"],
        "Q1_what_it_configures": "test module",
        "Q2_modification_patterns": [],
        "Q3_non_obvious_patterns": [
            {"name": "X", "trap": "Y", "evidence_file": "f:1", "why_non_obvious": "Z"},
            {"name": "A", "trap": "B", "evidence_file": "f:2", "why_non_obvious": "C"},
        ],
        "Q4_cross_module_deps": [],
        "Q5_tribal_knowledge_from_comments": [],
        "stats": {"files_count": 1, "files_read_count": 1, "lines_of_code": 100}
    }
    (tmp / ".claude/artifacts/analyst/test__m1.json").write_text(json.dumps(analyst_v1))

    # v1 critic: weighted_overall なし
    critic_v1 = {
        "file": ".claude/context/test__m1.md",
        "evaluated_at": "2026-04-19T00:00:00Z",
        "round": 1,
        "scores": {
            "conciseness": 4.0,
            "path_accuracy": 5.0,
            "non_obvious_value": 4.5,
            "modification_readiness": 4.0,
            "cross_ref_integrity": 3.5,
        },
        "overall": 4.2,
        "verdict": "PASS"
    }
    (tmp / ".claude/artifacts/critic/test__m1.json").write_text(json.dumps(critic_v1))

    # v1 quality log
    log_lines = [
        json.dumps({"timestamp": "2026-04-19T00:00:00Z", "module": "test/m1", "file": ".claude/context/test__m1.md",
                    "round": 1, "scores": critic_v1["scores"], "overall": 4.2, "verdict": "PASS"})
    ]
    (tmp / ".claude/context/_quality-log.jsonl").write_text("\n".join(log_lines) + "\n")
    return tmp


def t1_analyst_migration():
    with tempfile.TemporaryDirectory() as d:
        root = _setup_v1(Path(d))
        mig.migrate_analyst(root / ".claude/artifacts/analyst/test__m1.json", dry_run=False)
        data = json.loads((root / ".claude/artifacts/analyst/test__m1.json").read_text())
        for q3 in data["Q3_non_obvious_patterns"]:
            assert q3["confidence"] == "EXTRACTED", f"missing confidence: {q3}"
            assert q3["confidence_score"] == 1.0, f"wrong score: {q3}"
    print("  ✓ T1 v1 analyst → confidence/score 充当")


def t2_critic_migration():
    with tempfile.TemporaryDirectory() as d:
        root = _setup_v1(Path(d))
        mig.migrate_critic(root / ".claude/artifacts/critic/test__m1.json", dry_run=False)
        data = json.loads((root / ".claude/artifacts/critic/test__m1.json").read_text())
        assert "weighted_overall" in data
        assert "ambiguous_q3_count" in data
        assert data["ambiguous_q3_count"] == 0
        # path=5.0*2 + non_obv=4.5*2 + others (4+4+3.5)*1 = 10+9+11.5 = 30.5 / 7 = 4.357
        expected = round((5.0 * 2 + 4.5 * 2 + 4.0 + 4.0 + 3.5) / 7, 3)
        assert abs(data["weighted_overall"] - expected) < 0.01, \
            f"weighted_overall = {data['weighted_overall']}, expected ~{expected}"
    print(f"  ✓ T2 v1 critic → weighted_overall 計算 ({expected})")


def t3_quality_log_migration():
    with tempfile.TemporaryDirectory() as d:
        root = _setup_v1(Path(d))
        m, s = mig.migrate_quality_log(root / ".claude/context/_quality-log.jsonl", dry_run=False)
        assert m == 1, f"expected 1 migrated, got {m}"
        text = (root / ".claude/context/_quality-log.jsonl").read_text()
        row = json.loads(text.strip().splitlines()[0])
        assert "weighted_overall" in row
        assert row["cache_hit"] is False
    print("  ✓ T3 v1 quality-log → weighted_overall + cache_hit 充当")


def t4_idempotent():
    with tempfile.TemporaryDirectory() as d:
        root = _setup_v1(Path(d))
        mig.migrate_analyst(root / ".claude/artifacts/analyst/test__m1.json", dry_run=False)
        # 2 回目は skip
        result = mig.migrate_analyst(root / ".claude/artifacts/analyst/test__m1.json", dry_run=False)
        assert result == "skip", f"expected skip, got {result}"
    print("  ✓ T4 idempotent (2 回目は skip)")


def t5_weighted_average_correctness():
    # path=5, non_obv=5, others=2 → 5*2 + 5*2 + 2+2+2 = 26 / 7 = 3.714
    scores = {
        "conciseness": 2.0, "path_accuracy": 5.0, "non_obvious_value": 5.0,
        "modification_readiness": 2.0, "cross_ref_integrity": 2.0
    }
    w = mig.weighted_average(scores)
    expected = round((5.0 * 2 + 5.0 * 2 + 2.0 * 3) / 7, 3)
    assert abs(w - expected) < 0.01, f"weighted={w}, expected={expected}"
    # Single-axis simple test
    w2 = mig.weighted_average({"path_accuracy": 5.0})
    assert abs(w2 - 5.0) < 0.01
    print(f"  ✓ T5 weighted_average 数値検証 ({expected})")


def t6_dry_run():
    with tempfile.TemporaryDirectory() as d:
        root = _setup_v1(Path(d))
        before = (root / ".claude/artifacts/analyst/test__m1.json").read_text()
        mig.migrate_analyst(root / ".claude/artifacts/analyst/test__m1.json", dry_run=True)
        after = (root / ".claude/artifacts/analyst/test__m1.json").read_text()
        assert before == after, "dry-run should not modify file"
    print("  ✓ T6 dry-run でファイル不変")


if __name__ == "__main__":
    tests = [t1_analyst_migration, t2_critic_migration, t3_quality_log_migration,
             t4_idempotent, t5_weighted_average_correctness, t6_dry_run]
    print(f"Running {len(tests)} tests for tribal-v2 migrate_v1_to_v2.py:")
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
