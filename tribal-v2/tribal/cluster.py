#!/usr/bin/env python3
"""
Tribal v2 — Community detection (Phase 4: Community + GodNode).

graphify/cluster.py を tribal の dep-graph 用に流用 + 改修:
  - Leiden (graspologic) を試す → 失敗時は Louvain (networkx 内蔵) へ fallback
  - tribal の入力は `_dep-graph.json` (nodes, edges 形式)
  - 出力は `_communities.json` (node_to_community マップ + community 別メンバー + cohesion)
  - module 数が高々数百なので graphify の「25% 超えたら再分割」ロジックは省略 (簡素化)

Phase 0 ベースライン採取で graspologic は Python 3.14 で利用不可と確認済み。
本実装は Louvain 動作を主、Leiden は今後の互換性確認用。

Usage:
    python3 cluster.py [--dep-graph PATH] [--output PATH]
    python3 cluster.py  # uses .claude/context/_dep-graph.json → _communities.json
"""

from __future__ import annotations

import argparse
import contextlib
import inspect
import io
import json
import sys
import time
from pathlib import Path

import networkx as nx


DEP_GRAPH = Path(".claude/context/_dep-graph.json")
COMMUNITIES = Path(".claude/context/_communities.json")


def _build_graph(dep_graph: dict, directed: bool = False) -> nx.Graph:
    """Build NetworkX graph from tribal dep-graph JSON."""
    G: nx.Graph = nx.DiGraph() if directed else nx.Graph()
    for node in dep_graph.get("nodes", []):
        G.add_node(node["id"], **{k: v for k, v in node.items() if k != "id"})
    for edge in dep_graph.get("edges", []):
        src = edge.get("from") or edge.get("source")
        tgt = edge.get("to") or edge.get("target")
        if src and tgt and src in G.nodes and tgt in G.nodes:
            attrs = {k: v for k, v in edge.items() if k not in ("from", "to", "source", "target")}
            G.add_edge(src, tgt, **attrs)
    return G


def _partition_leiden(G: nx.Graph) -> dict[str, int] | None:
    """Try Leiden via graspologic. Return None if unavailable.

    graphify と同じ理由で stderr の StringIO 差し替えで PowerShell 5.1
    scrollback 破壊を防御 (issue #19, Phase 0 baseline で記録済みの v1 知見)。
    """
    try:
        from graspologic.partition import leiden
    except ImportError:
        return None
    old_stderr = sys.stderr
    try:
        sys.stderr = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()):
            return leiden(G)
    finally:
        sys.stderr = old_stderr


def _partition_louvain(G: nx.Graph) -> dict[str, int]:
    """Louvain via networkx (always available since 2.7).

    inspect.signature で max_level kwarg を動的選択 — graphify の v1 知見を流用
    (古い NetworkX で TypeError 発生防止)。
    """
    kwargs: dict = {"seed": 42, "threshold": 1e-4}
    if "max_level" in inspect.signature(nx.community.louvain_communities).parameters:
        kwargs["max_level"] = 10
    communities = nx.community.louvain_communities(G, **kwargs)
    return {node: cid for cid, nodes in enumerate(communities) for node in nodes}


def cluster(G: nx.Graph) -> tuple[dict[int, list[str]], str]:
    """Run community detection. Returns ({cid: [members]}, method).

    Method order:
      1. Leiden (graspologic) — best quality
      2. Louvain (networkx) — built-in fallback

    isolate ノードは独立 community として明示的に追加 (graphify v1 知見:
    Leiden は warning + drop するため別処理が必要)。
    """
    if G.number_of_nodes() == 0:
        return ({}, "empty")
    if G.is_directed():
        G = G.to_undirected()
    if G.number_of_edges() == 0:
        # No edges → each node is its own community
        return ({i: [n] for i, n in enumerate(sorted(G.nodes))}, "no-edges")

    # Separate isolates (handled independently; Leiden drops them silently)
    isolates = [n for n in G.nodes() if G.degree(n) == 0]
    connected_nodes = [n for n in G.nodes() if G.degree(n) > 0]
    sub = G.subgraph(connected_nodes).copy() if connected_nodes else None

    raw: dict[int, list[str]] = {}
    method = "louvain"
    if sub is not None and sub.number_of_nodes() > 0:
        partition = _partition_leiden(sub)
        if partition is not None:
            method = "leiden"
        else:
            partition = _partition_louvain(sub)
        for node, cid in partition.items():
            raw.setdefault(cid, []).append(node)

    # Append isolates as single-node communities
    next_cid = max(raw.keys(), default=-1) + 1
    for node in isolates:
        raw[next_cid] = [node]
        next_cid += 1

    # Re-index communities by size descending for deterministic ordering
    sorted_communities = sorted(raw.values(), key=len, reverse=True)
    return ({i: sorted(nodes) for i, nodes in enumerate(sorted_communities)}, method)


def cohesion_score(G: nx.Graph, members: list[str]) -> float:
    """Ratio of intra-community edges to maximum possible (graphify と同じ式)."""
    n = len(members)
    if n <= 1:
        return 1.0
    sub = G.subgraph(members)
    actual = sub.number_of_edges()
    possible = n * (n - 1) / 2
    return round(actual / possible, 3) if possible > 0 else 0.0


def build_communities_json(dep_graph_path: Path, output_path: Path) -> dict:
    """Top-level: read dep-graph, run cluster, write _communities.json."""
    dep = json.loads(dep_graph_path.read_text(encoding="utf-8"))
    G = _build_graph(dep)
    communities, method = cluster(G)

    # Per-community payload with cohesion
    comm_dict: dict[str, dict] = {}
    node_to_comm: dict[str, int] = {}
    for cid, members in communities.items():
        comm_dict[str(cid)] = {
            "members": members,
            "cohesion": cohesion_score(G, members),
            "size": len(members),
            "label": None,  # to be filled by routing-upgrader
        }
        for n in members:
            node_to_comm[n] = cid

    sizes = [v["size"] for v in comm_dict.values()]
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "method": method,
        "communities": comm_dict,
        "node_to_community": node_to_comm,
        "stats": {
            "count": len(comm_dict),
            "avg_size": round(sum(sizes) / len(sizes), 2) if sizes else 0,
            "max_size": max(sizes) if sizes else 0,
            "min_size": min(sizes) if sizes else 0,
            "node_count": G.number_of_nodes(),
            "edge_count": G.number_of_edges(),
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dep-graph", default=str(DEP_GRAPH))
    parser.add_argument("--output", default=str(COMMUNITIES))
    args = parser.parse_args()

    dep_path = Path(args.dep_graph)
    if not dep_path.exists():
        print(f"error: dep-graph not found: {dep_path}", file=sys.stderr)
        return 1

    payload = build_communities_json(dep_path, Path(args.output))
    print(f"Communities ({payload['method']}): "
          f"{payload['stats']['count']} groups, "
          f"avg size {payload['stats']['avg_size']}, "
          f"max {payload['stats']['max_size']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
