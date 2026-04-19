# Phase 4 完了報告: Community Detection + God Node Recommendation

**完了日**: 2026-04-19
**ブランチ**: `tribal-v2-migration`
**先行 commits**: `8c26495` (P1), `84db546` (P2), `b705aa1` (P3)

---

## 実施内容

### 4.1 cluster スクリプトと agent

| 成果物 | パス | LOC |
|---|---|---|
| ★ cluster 本体 | `tribal-v2/.claude/scripts/cluster.py` | 154 |
| ★ schema | `tribal-v2/.claude/schemas/communities.schema.json` | 48 |
| ★ agent | `tribal-v2/.claude/agents/community-clusterer.md` | 47 |

特徴:
- Leiden (graspologic) を試行 → 不可なら Louvain (networkx) 自動 fallback
- isolate ノードを drop せず独立 community 化 (graphify v1 の知見流用)
- `_dep-graph.json` 入力 / `_communities.json` 出力 (cohesion 同梱)

### 4.2 god-node スクリプトと agent

| 成果物 | パス | LOC |
|---|---|---|
| ★ god-node 本体 | `tribal-v2/.claude/scripts/god_nodes.py` | 158 |
| ★ schema | `tribal-v2/.claude/schemas/god-nodes.schema.json` | 60 |
| ★ agent | `tribal-v2/.claude/agents/god-node-detector.md` | 50 |

特徴:
- degree top-N で global / per_community を抽出
- intent ごとの kind_weight heuristic で primary 推薦 (validation kind 1.8x boost 等)
- routing-upgrader が判定者として採否する素材を提供

### 4.3 dep-graph schema 拡張

- `dep-graph.schema.json` の edge:
  - `kind` enum に `semantically_similar_to` `rationale_for` 追加
  - `confidence` `confidence_score` フィールド追加 (graphify と同じ規範)
- `dependency-indexer.md` agent に v2 セクション追加:
  - semantically_similar_to: Q1+Q3 キーワードベクトル (TF-IDF/Jaccard) で 0.7 以上のペアに edge
  - rationale_for: Q5 の commit_message 由来 why を node 化、対象 module へ edge

### 4.4 routing 強化

- `routing-table.schema.json`:
  - intent に `community_hint` `god_node_recommended` `rejected_recommendations` 追加
  - top-level に `wiki_index` 追加
- `routing-upgrader.md`: 「ゼロから生成」→「機械推薦の判定者」に動作モード変更
  - 入力に `_communities.json` `_god-nodes.json` 追加
  - 採用/却下を理由付きで記録 (説明可能性 +1)
- `tribal-router/SKILL.md`: 7 step に拡張
  - Step 2 (NEW): community 解決
  - Step 4 (改): ripple expansion を community-aware (同 community 内優先)
  - Step 6 (NEW): wiki fallback (intent 不明時の `_index.md` 誘導)

### 4.5 wiki entry / Phase 5.5 + 6.5 追加

- `tribal-mapper/SKILL.md` に Phase 5.5 (Clustering) と Phase 6.5 (God Detection) 挿入
- Phase 7 末尾で `_index.md` 生成を routing-upgrader に追加

### 4.7 単体テスト + E2E

**単体テスト** (`test_cluster.py`, 9/9 PASS):
```
T1 empty graph → empty result                                ✓
T2 no edges → 3 single-node communities                      ✓
T3 barbell → 2 communities (louvain)                         ✓
T4 isolate node → 独立 community 化 (drop されない)           ✓
T5 cohesion: full mesh = 1.0, no edges = 0.0                 ✓
T6 directed graph → undirected で正常処理                      ✓
T7 god_nodes degree compute                                   ✓
T8 god_nodes full pipeline (top + recommendations)            ✓
T9 kind_weight (validation kind が validation-change で boost) ✓
```

**E2E** (baseline-target で 18 modules):

`cluster.py` 出力 (Louvain method):
| Community | size | cohesion | members |
|---|---|---|---|
| C0 | 5 | 0.600 | analyze, cluster, hooks, report, watch |
| C1 | 5 | 0.400 | export, ingest, security, serve, transcribe |
| C2 | 3 | 0.667 | cache, detect, extract |
| C3 | 2 | 1.000 | build, validate |
| C4 | 1 | 1.000 | benchmark |
| C5 | 1 | 1.000 | wiki |
| C6 | 1 | 1.000 | cli |

→ **graphify ARCHITECTURE.md の pipeline と一致**:
- C2 (cache/detect/extract) = 入力パイプライン
- C3 (build/validate) = グラフ組立 (cohesion 1.0、密結合)
- C0 (analyze/cluster/report/watch/hooks) = 解析・実行制御
- C1 (export/ingest/security/serve/transcribe) = I/O・外部連携

LLM 不要で **意味的にコヒーレントな** クラスタリングを達成。

`god_nodes.py` 出力:
- global_top: graphify/watch (deg 8) → graphify/analyze (deg 6) → ...
- recommended_primaries は 8 intent 全てカバー

---

## 設計判断と発見

### A: Leiden 不可は計画通り

Phase 0 で Python 3.14.3 → graspologic 不可と確認済み。Louvain で代替動作問題なし。
ただし future Python での Leiden 復活時は automatic switch (cluster.py 内で try)。

### B: god_node 推薦の偏り発見

baseline-target で「8 intent すべてが watch/analyze を上位推薦」する偏りが出た。
原因: graphify は flat dependency なので degree 差が大きく、kind_weight (1.8x 程度)
では覆らない。

→ Phase 5/6 で routing-upgrader が手動判定する余地として `rejected_recommendations`
スキーマを既に用意。Phase 7 routing build で「validation 系は validate.py を
primary、watch は却下」のような判断ができる。

### C: cohesion で community 品質を可視化

C3 (build+validate) は cohesion 1.0 で密結合だと判明、これは ripple_index で
最優先する根拠になる。低 cohesion (C1=0.4) は分割候補として記録できるが、
tribal v2 では小規模 dep-graph 想定で再分割は省略 (graphify は 25%超で再分割)。

### D: semantically_similar_to / rationale_for は Phase 7 で実装

dependency-indexer agent prompt には v2 仕様を記載済みだが、実コード生成は
analyst Q1+Q3 のキーワード抽出が必要 (LLM 利用)。ここは Phase 7 E2E 時に
実 LLM で動作させて検証する。

---

## 計画書 (`tribal-improvement-plan.md`) 期待効果との照合

| 計画書 9 節の指標 | Phase 4 単独での到達 |
|---|---|
| router 選定平均 context 数 4.5 → 3.0-3.5 枚 | 構造的下地完成、community 制約で ripple 暴発抑制可。実測は Phase 7 |
| routing intent 誤分類率 < 5% | god_node 推薦と community_hint が裏取りに使える、実測 Phase 7 |
| coverage_ratio == 1.0 | 既に達成 (Phase 0 baseline) |

---

## 次のステップ: Phase 5 (Benchmark + PreToolUse Hook)

- `benchmark-reporter` agent (token reduction 計測)
- `check_router_state.py` PreToolUse hook (router 未起動で Read/Glob/Grep 警告)
- `_quality-log.jsonl` に `tokens_saved_ratio` 自動記録
- CI gate に benchmark 回帰条件追加
