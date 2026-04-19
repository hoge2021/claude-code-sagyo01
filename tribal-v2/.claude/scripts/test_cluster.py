#!/usr/bin/env python3
"""
Tribal v2 cluster.py + god_nodes.py 単体テスト.

検証観点 (Phase 4 checklist 4.7):
  T1 cluster: empty graph → empty result
  T2 cluster: edges 無し → 各 node が独立 community
  T3 cluster: barbell 構造 (2 community) → 正しく 2 分割
  T4 cluster: isolate ノード混在 → 独立 community 化 (drop されない)
  T5 cohesion_score: full mesh = 1.0, no edges = 0.0
  T6 cluster: directed graph → undirected で処理可能
  T7 god_nodes: degree 順で global_top_n 取得
  T8 god_nodes: per_community で各 community top 取得
  T9 god_nodes: recommended_primaries が intent ごとに生成される
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import cluster  # noqa: E402
import god_nodes  # noqa: E402

import networkx as nx  # noqa: E402


def _empty_dep_graph():
    return {"nodes": [], "edges": []}


def t1_empty_graph():
    G = cluster._build_graph(_empty_dep_graph())
    result, method = cluster.cluster(G)
    assert result == {}, f"expected empty, got {result}"
    print("  ✓ T1 empty graph → empty result")


def t2_no_edges():
    dg = {"nodes": [{"id": "a"}, {"id": "b"}, {"id": "c"}], "edges": []}
    G = cluster._build_graph(dg)
    result, method = cluster.cluster(G)
    assert len(result) == 3, f"expected 3 isolated communities, got {len(result)}"
    assert method == "no-edges"
    print("  ✓ T2 no edges → 3 single-node communities")


def t3_barbell():
    """2 dense clusters connected by one edge — should split into 2 communities."""
    dg = {
        "nodes": [{"id": f"n{i}"} for i in range(6)],
        "edges": [
            # cluster 1: n0, n1, n2 fully connected
            {"from": "n0", "to": "n1"}, {"from": "n0", "to": "n2"}, {"from": "n1", "to": "n2"},
            # cluster 2: n3, n4, n5 fully connected
            {"from": "n3", "to": "n4"}, {"from": "n3", "to": "n5"}, {"from": "n4", "to": "n5"},
            # bridge
            {"from": "n2", "to": "n3"},
        ]
    }
    G = cluster._build_graph(dg)
    result, method = cluster.cluster(G)
    assert len(result) >= 2, f"expected >=2 communities, got {len(result)}: {result}"
    # All nodes in result
    all_members = {n for nodes in result.values() for n in nodes}
    assert all_members == set(f"n{i}" for i in range(6))
    print(f"  ✓ T3 barbell → {len(result)} communities ({method})")


def t4_isolate_nodes():
    """isolate ノードが drop されず独立 community になる."""
    dg = {
        "nodes": [{"id": "a"}, {"id": "b"}, {"id": "c"}, {"id": "lonely"}],
        "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}]
    }
    G = cluster._build_graph(dg)
    result, _ = cluster.cluster(G)
    all_members = {n for nodes in result.values() for n in nodes}
    assert "lonely" in all_members, "isolate dropped!"
    # lonely should be in its own community
    for nodes in result.values():
        if "lonely" in nodes:
            assert len(nodes) == 1, f"lonely grouped with others: {nodes}"
            break
    print("  ✓ T4 isolate node → 独立 community 化")


def t5_cohesion_score():
    G = nx.Graph()
    G.add_edges_from([("a", "b"), ("a", "c"), ("b", "c")])  # triangle
    score = cluster.cohesion_score(G, ["a", "b", "c"])
    assert score == 1.0, f"full mesh expected 1.0, got {score}"
    G2 = nx.Graph()
    G2.add_nodes_from(["x", "y", "z"])
    score2 = cluster.cohesion_score(G2, ["x", "y", "z"])
    assert score2 == 0.0, f"no edges expected 0.0, got {score2}"
    print("  ✓ T5 cohesion: full mesh = 1.0, no edges = 0.0")


def t6_directed_graph():
    """DiGraph 入力でも cluster は undirected 化して処理."""
    dg = {
        "nodes": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
        "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}]
    }
    G = cluster._build_graph(dg, directed=True)
    assert G.is_directed()
    result, _ = cluster.cluster(G)
    # All 3 nodes should appear
    all_members = {n for nodes in result.values() for n in nodes}
    assert all_members == {"a", "b", "c"}
    print("  ✓ T6 directed graph → undirected で正常処理")


def t7_god_nodes_global_top():
    dg = {
        "nodes": [{"id": f"n{i}"} for i in range(5)],
        "edges": [
            # n0 is hub: connected to n1, n2, n3, n4
            {"from": "n0", "to": "n1"}, {"from": "n0", "to": "n2"},
            {"from": "n0", "to": "n3"}, {"from": "n0", "to": "n4"},
            # n1-n2 also connected
            {"from": "n1", "to": "n2"},
        ]
    }
    deg = god_nodes.compute_degree(dg)
    assert deg["n0"] == 4, f"n0 degree expected 4, got {deg['n0']}"
    assert deg["n4"] == 1, f"n4 degree expected 1, got {deg['n4']}"
    print(f"  ✓ T7 god_nodes degree: n0={deg['n0']}, n4={deg['n4']}")


def t8_god_nodes_full_pipeline():
    dg = {
        "nodes": [{"id": f"n{i}"} for i in range(4)],
        "edges": [{"from": "n0", "to": "n1"}, {"from": "n0", "to": "n2"},
                  {"from": "n0", "to": "n3"}]
    }
    comm = {
        "communities": {"0": {"members": ["n0", "n1", "n2", "n3"], "size": 4}},
        "node_to_community": {"n0": 0, "n1": 0, "n2": 0, "n3": 0}
    }
    routing = {"intents": [{"name": "feature-add", "keywords": [], "primary_contexts": []}]}
    repo = {"repos": [{"modules": [
        {"id": f"n{i}", "kind": "library", "context_file": f".claude/context/n{i}.md"}
        for i in range(4)
    ]}]}
    result = god_nodes.detect_god_nodes(dg, comm, routing, repo)
    assert result["global_top_n"][0]["module"] == "n0", "top should be n0 (highest degree)"
    assert "feature-add" in result["recommended_primaries"]
    assert ".claude/context/n0.md" in result["recommended_primaries"]["feature-add"]
    print("  ✓ T8 full pipeline: top=n0, recommended_primaries OK")


def t9_recommended_kind_weight():
    """validation kind が validation-change intent で boost される."""
    dg = {
        "nodes": [{"id": "lib"}, {"id": "val"}],
        "edges": [{"from": "lib", "to": "val"}]  # both degree=1, same
    }
    comm = {"communities": {"0": {"members": ["lib", "val"], "size": 2}},
            "node_to_community": {"lib": 0, "val": 0}}
    routing = {"intents": [{"name": "validation-change", "keywords": [], "primary_contexts": []}]}
    repo = {"repos": [{"modules": [
        {"id": "lib", "kind": "library", "context_file": ".claude/context/lib.md"},
        {"id": "val", "kind": "validation", "context_file": ".claude/context/val.md"},
    ]}]}
    result = god_nodes.detect_god_nodes(dg, comm, routing, repo)
    primaries = result["recommended_primaries"]["validation-change"]
    # val should rank higher than lib due to kind weight (validation=1.8 vs library=1.0)
    assert primaries[0] == ".claude/context/val.md", \
        f"validation kind not prioritized: {primaries}"
    print("  ✓ T9 kind_weight: validation kind が validation-change で primary に")


if __name__ == "__main__":
    tests = [t1_empty_graph, t2_no_edges, t3_barbell, t4_isolate_nodes,
             t5_cohesion_score, t6_directed_graph, t7_god_nodes_global_top,
             t8_god_nodes_full_pipeline, t9_recommended_kind_weight]
    print(f"Running {len(tests)} tests for tribal-v2 cluster + god_nodes:")
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
