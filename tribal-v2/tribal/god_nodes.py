#!/usr/bin/env python3
"""
Tribal v2 — God node detection (Phase 4: Community + GodNode).

graphify/analyze.py の god_nodes() を tribal の dep-graph 用に流用。
degree top-N の hub module を抽出し、各 community ごとの代表 module も出す。
さらに routing-table の intent と community の親和性スコアを heuristic で計算し、
`recommended_primaries` を生成する (routing-upgrader が判定者として採否する素材)。

Filter:
  - graphify が file-level hub と method stub を除外していたが、tribal の module 粒度では
    そういう synthetic node が無いので除外ロジックは省略 (シンプルに degree top-N)。
  - ただし repo-map の `kind` が "config" の module は intent-priming weight を上げる
    (config 系は schema-change / feature-add で primary 候補になりやすい)。

Usage:
    python3 god_nodes.py [--dep-graph] [--communities] [--routing] [--repo-map] [--output]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path


DEP_GRAPH = Path(".claude/context/_dep-graph.json")
COMMUNITIES = Path(".claude/context/_communities.json")
ROUTING_TABLE = Path(".claude/context/_routing-table.json")
REPO_MAP = Path(".claude/context/_repo-map.json")
OUTPUT = Path(".claude/context/_god-nodes.json")


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def compute_degree(dep_graph: dict) -> dict[str, int]:
    """Compute undirected degree per node from dep-graph edges."""
    deg: dict[str, int] = defaultdict(int)
    for n in dep_graph.get("nodes", []):
        deg[n["id"]] = 0  # ensure all nodes appear
    for e in dep_graph.get("edges", []):
        src = e.get("from") or e.get("source")
        tgt = e.get("to") or e.get("target")
        if src:
            deg[src] += 1
        if tgt:
            deg[tgt] += 1
    return dict(deg)


def _kind_weight(repo_map: dict, module_id: str, intent_name: str) -> float:
    """Heuristic affinity boost based on module kind and intent.

    Real graphify uses far more sophisticated logic; for tribal v2 we keep
    this as a small-table heuristic that routing-upgrader can override.
    """
    # find module kind
    kind = "library"
    for repo in repo_map.get("repos", []):
        for m in repo.get("modules", []):
            if m["id"] == module_id:
                kind = m.get("kind", "library")
                break

    table = {
        "schema-change": {"validation": 1.5, "config": 1.3, "library": 1.0},
        "feature-add": {"config": 1.4, "service": 1.2, "library": 1.0},
        "ops-investigation": {"service": 1.5, "automation": 1.3, "library": 0.8},
        "validation-change": {"validation": 1.8, "library": 1.0},
        "codegen-change": {"library": 1.2, "config": 1.0},
        "bug-fix": {"library": 1.0, "validation": 1.2, "service": 1.1},
        "refactor": {"library": 1.0},
        "test-add": {"library": 1.0, "validation": 1.1},
    }
    return table.get(intent_name, {}).get(kind, 1.0)


def detect_god_nodes(
    dep_graph: dict,
    communities: dict,
    routing_table: dict,
    repo_map: dict,
    global_top_n: int = 5,
    per_community_top_n: int = 2,
) -> dict:
    """Compute global god nodes + per-community god nodes + intent recommendations."""
    deg = compute_degree(dep_graph)

    # Build context_file lookup from repo-map
    cf_lookup: dict[str, str] = {}
    for repo in repo_map.get("repos", []):
        for m in repo.get("modules", []):
            cf_lookup[m["id"]] = m.get("context_file", "")

    # Global top-N
    sorted_global = sorted(deg.items(), key=lambda x: -x[1])
    global_top = [
        {
            "module": mid,
            "degree": d,
            "community": communities.get("node_to_community", {}).get(mid),
            "context_file": cf_lookup.get(mid, ""),
        }
        for mid, d in sorted_global[:global_top_n]
    ]

    # Per-community top-N
    per_comm: dict[str, list[dict]] = {}
    for cid, info in communities.get("communities", {}).items():
        members = info.get("members", [])
        ranked = sorted(members, key=lambda m: -deg.get(m, 0))
        per_comm[cid] = [
            {
                "module": mid,
                "degree": deg.get(mid, 0),
                "context_file": cf_lookup.get(mid, ""),
            }
            for mid in ranked[:per_community_top_n]
        ]

    # Recommended primaries per intent
    # Strategy: for each intent, score every module by (degree * kind_weight) and
    # return top 1-3 that fit. routing-upgrader judges and accepts/rejects.
    recommended: dict[str, list[str]] = {}
    intents = routing_table.get("intents", []) if routing_table else []
    for it in intents:
        name = it["name"]
        scored = sorted(
            ((mid, deg.get(mid, 0) * _kind_weight(repo_map, mid, name)) for mid in deg),
            key=lambda x: -x[1],
        )
        # Take top 3 modules with non-zero score, return their context files
        primaries = [cf_lookup.get(mid, "") for mid, s in scored[:3] if s > 0 and cf_lookup.get(mid)]
        recommended[name] = [p for p in primaries if p]

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "global_top_n": global_top,
        "per_community": per_comm,
        "recommended_primaries": recommended,
        "stats": {
            "node_count": len(deg),
            "max_degree": max(deg.values()) if deg else 0,
            "avg_degree": round(sum(deg.values()) / len(deg), 2) if deg else 0.0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dep-graph", default=str(DEP_GRAPH))
    parser.add_argument("--communities", default=str(COMMUNITIES))
    parser.add_argument("--routing", default=str(ROUTING_TABLE))
    parser.add_argument("--repo-map", default=str(REPO_MAP))
    parser.add_argument("--output", default=str(OUTPUT))
    args = parser.parse_args()

    dep = load_json(Path(args.dep_graph), {"nodes": [], "edges": []})
    comm = load_json(Path(args.communities), {"communities": {}, "node_to_community": {}})
    routing = load_json(Path(args.routing), {"intents": []})
    repo = load_json(Path(args.repo_map), {"repos": []})

    if not dep.get("nodes"):
        print("error: empty or missing dep-graph", file=sys.stderr)
        return 1

    payload = detect_god_nodes(dep, comm, routing, repo)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"God nodes: {len(payload['global_top_n'])} global, "
          f"{len(payload['per_community'])} communities, "
          f"top intent recommendations in {len(payload['recommended_primaries'])} intents")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
