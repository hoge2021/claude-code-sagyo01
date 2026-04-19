# Tribal Knowledge Mapper 改善・強化計画

**ベース**: `/home/hoge/51_mygit/output/tribal/` (Tribal Knowledge Mapper, Meta blog 再現テンプレート)
**参考**: `/home/hoge/51_mygit/graphify/` (graphifyy 0.4.23, 知識グラフ構築 skill)
**作成日**: 2026-04-19

---

## 0. このドキュメントの目的

tribal の 3層設計（Pre-compute / Runtime / Maintenance）と「opt-in 物理強制」の哲学を **完全に維持** しつつ、graphify から以下の核心要素を厳選して編み込み、シナジーを最大化する:

- **決定論的 AST 第1パス** (LLM コスト削減 + 速度向上)
- **SHA256 ベースの per-file cache** (refresh モードの高速化)
- **3-tier confidence label + confidence_score** (品質判定の精緻化)
- **Leiden community detection** (routing 精度向上)
- **god_node 検出** (primary_context 自動推薦)
- **semantic similarity / hyperedge** (Q3/Q4 の表現力拡張)
- **token reduction benchmark** (定量的価値証明)
- **security.py の path/URL 防御** (critic 隔離強化)
- **MCP serve 化** (routing-table の他 agent 共有)
- **multi-platform 配布パターン** (Claude Code 以外への展開)
- **wiki/index.md 形式の community ナビ** (router fallback)

graphify から **採用しない** もの: 25 言語フル対応 / 動画音声転写 / yt-dlp ingest / HTML viz / Obsidian vault / Neo4j/SVG/GraphML / 14 platform 全対応。tribal の用途（コードベース内 tribal knowledge のマッピング）に対して過剰なため。

---

## 1. シナジー設計の中核 5 アイデア

両者を素朴に繋げず、tribal の **既存 phase を「分解 → 注入 → 再合成」** することでシナジーを出す。

### アイデア A: `module-analyst` を AST 層と LLM 層に分解する

現在の analyst は LLM 1 発で Q1-Q5 を生成しており、Q4 (cross_module_deps) のような **構造的に決定論で取れる情報** にも LLM トークンを使っている。

→ **`module-ast-extractor`（新規 subagent）** を Phase 2 の前に挿入。tree-sitter で Q4 (deps) と Q2 (modification_patterns の候補ファイル) を **無料で** 確定させ、analyst は **Q1 / Q3 / Q5（意味的なもの）に集中** する。

### アイデア B: `dep-graph` に Leiden を走らせ、`routing-table` の intent と community を対応付ける

現在の routing-table は intent → primary_contexts を人手 + LLM で推定しているが、根拠が弱い。

→ Phase 5.5 として **`community-clusterer`（新規 subagent）** を挿入し、`_dep-graph.json` 上で Leiden を実行。各 intent の primary_contexts は **community god_node から機械的にレコメンド** され、`routing-upgrader` はそれを採用 / 却下する判定者になる。

### アイデア C: `Q3_non_obvious_patterns` に confidence_score と AMBIGUOUS ラベルを必須化する

現在の Q3 は二値（書いてある / ない）で、critic が「自明」と判定しても根拠が定性的。

→ analyst が Q3 各項目に `confidence: EXTRACTED|INFERRED|AMBIGUOUS` と `confidence_score: 0.0-1.0` を付与。AMBIGUOUS な Q3 は critic が見るまでもなく **自動で manual_review_required** に振り分けられ、reconciliation ループが短縮される。

### アイデア D: `_routing-table.json` を MCP server で公開する

現在の router は Claude Code セッション内でしか動かない。

→ `serve.py` パターンで `tribal_serve.py` を実装し、`route_query` / `get_intent` / `get_ripple` / `get_god_nodes` を MCP tool として公開。Codex / Gemini / Cursor からも tribal の routing 知識を共有でき、tribal が **「知識アセット」として横展開** 可能に。

### アイデア E: SHA256 cache を analyst / critic / writer 3 つすべてに適用する

現在の refresh は git diff / mtime で「変更モジュール」を検出するが、変更のないモジュールでも analyst を再起動するケースが多い（依存先変更による ripple 巻き込み等）。

→ `tribal/cache.py`（graphify から借用 + 改修）を導入し、analyst の入力ファイル群の集約 SHA256 を key に **JSON artifact をキャッシュ**。critic スコアも同様にキャッシュ。「ripple で巻き込まれただけで内容が変わってない module」は LLM 呼び出しゼロ。

---

## 2. 改善項目一覧（追加 / 変更 / 削除）

| 種別 | 項目 | 内容 | 由来 |
|---|---|---|---|
| 追加 | `module-ast-extractor` agent | tree-sitter で Q2/Q4 を決定論抽出 | graphify `extract.py` |
| 追加 | `community-clusterer` agent | Leiden で dep-graph を community 化 | graphify `cluster.py` |
| 追加 | `god-node-detector` agent | degree top-N で primary_context 候補を推薦 | graphify `analyze.py` |
| 追加 | `benchmark-reporter` agent | router 経由 vs raw load の token 比を毎回計測 | graphify `benchmark.py` |
| 追加 | `tribal/cache.py` | SHA256 per-module artifact cache | graphify `cache.py` |
| 追加 | `tribal/security.py` | path traversal / URL 検証 | graphify `security.py` |
| 追加 | `tribal/serve.py` | MCP server で routing 公開 | graphify `serve.py` |
| 追加 | `tribal-init.py` 系 multi-platform installer | Claude/Codex/OpenCode 向け配布 | graphify `__main__.py` _PLATFORM_CONFIG |
| 追加 | `_communities.json` artifact | community → modules マップ | graphify community 概念 |
| 追加 | `_god-nodes.json` artifact | top-N hub modules | graphify god node |
| 追加 | `_benchmark.json` artifact | token reduction 計測ログ | graphify benchmark |
| 追加 | `.claude/context/_index.md` | community/intent ナビの wiki entry point | graphify `--wiki` |
| 変更 | `module-analyst` agent | AST が確定した Q2/Q4 を**読み込み**、Q1/Q3/Q5 に集中 | tribal + graphify 編成 |
| 変更 | `module-analyst` 出力 schema | Q3 に `confidence` `confidence_score` 追加、`Q3_hyperedges` 追加 | graphify edge schema |
| 変更 | `context-critic` 判定基準 | AMBIGUOUS Q3 を即 manual_review_required、PASS 閾値を confidence_score 加重平均に | tribal + graphify confidence |
| 変更 | `dependency-indexer` | edges に `kind` だけでなく `confidence_score` を持たせる、`semantically_similar_to` edge を追加 | graphify edge model |
| 変更 | `routing-upgrader` | 機械推薦された primary_contexts（god_node + community）を入力に取り、判定者として動作 | アイデア B |
| 変更 | `tribal-router` skill | community を考慮した 2 段階選定 (intent → community → primary → ripple) | アイデア B |
| 変更 | `tribal-mapper` skill Phase 構成 | Phase 2 を 2a (AST) + 2b (LLM analyst) に分割、Phase 5.5 (community) と Phase 8.5 (benchmark) を新設 | アイデア A + B |
| 変更 | `validate_context_file.py` hook | path 検証で `tribal/security.py` を経由（traversal 対策） | graphify security |
| 変更 | `inject_router_directive.py` hook | community fallback を提示 (`_index.md` への誘導) | アイデア B + wiki |
| 追加 | PreToolUse hook (Read/Glob/Grep) | tribal-router 未起動状態で Read/Glob/Grep が発火したら警告注入 | graphify hook 戦略 |
| 変更 | `_quality-log.jsonl` schema | `tokens_saved_ratio` フィールド追加 | benchmark 連携 |
| 変更 | GitHub Actions workflow | benchmark 結果も品質ゲートに含める（前回比 -20% 以上劣化で fail） | benchmark 連携 |
| 削除 | （なし） | tribal の既存要素は全て温存。一部 schema 拡張のみ | — |

合計 **追加 11 / 変更 9 / 削除 0**。tribal の既存挙動は **完全な superset** として維持される（既存の analyst JSON は新スキーマでも読める、新規フィールドは optional）。

---

## 3. アーキテクチャ進化: 3層 → 3層 + 横串 2 層

tribal の 3層（Pre-compute / Runtime / Maintenance）は維持。そこに **横串 2 層** を新設して synergy を物理的に表現する:

```
┌──────────────────────────────────────────────────────────────┐
│  Pre-compute Layer                                           │
│   Phase 1  Discovery        (repo-explorer)                  │
│   Phase 2a Structural       (module-ast-extractor) ★NEW     │
│   Phase 2b Semantic         (module-analyst, slim)           │
│   Phase 3  Compose          (context-writer)                 │
│   Phase 4  Quality Gate     (context-critic ⇄ context-fixer) │
│   Phase 5  Indexing         (dependency-indexer)             │
│   Phase 5.5 Clustering      (community-clusterer) ★NEW       │
│   Phase 6  Coverage Audit   (coverage-auditor)               │
│   Phase 6.5 God Detection   (god-node-detector) ★NEW         │
│   Phase 7  Routing Build    (routing-upgrader, augmented)    │
│   Phase 8  Regression Test  (prompt-tester)                  │
│   Phase 8.5 Benchmark       (benchmark-reporter) ★NEW        │
├──────────────────────────────────────────────────────────────┤
│  Runtime Layer                                               │
│   tribal-router skill (intent → community → primary → ripple)│
│   PreToolUse hook on Read/Glob/Grep ★NEW (defense-in-depth)  │
├──────────────────────────────────────────────────────────────┤
│  Maintenance Layer                                           │
│   /tribal-refresh (cache-aware diff)                         │
│   /tribal-validate (+ benchmark gate)                        │
│   GitHub Actions (quality + benchmark regression gate)       │
├──────────────────────────────────────────────────────────────┤
│  ★ Cross-cutting: Cache Layer (NEW)                          │
│   tribal/cache.py — SHA256 per-module artifact cache         │
│   analyst / critic / ast の各出力をキャッシュ                │
├──────────────────────────────────────────────────────────────┤
│  ★ Cross-cutting: Distribution Layer (NEW)                   │
│   tribal/serve.py — MCP server (route_query etc.)            │
│   tribal install --platform {claude,codex,opencode}          │
└──────────────────────────────────────────────────────────────┘
```

---

## 4. 新規コンポーネント詳細

### 4.1 `module-ast-extractor` agent（Phase 2a）

**目的**: LLM を使わず tree-sitter で構造的事実を確定させ、analyst の作業を軽量化する。

```yaml
name: module-ast-extractor
description: tree-sitter で module の構造（imports, calls, classes, functions）を決定論的に抽出
tools: Bash, Read, Glob
model: haiku  # AST 結果の整形だけなので haiku で十分
```

**入力**: module の path
**処理**:
1. `python tribal/scripts/ast_extract.py <module-path> > artifacts/ast/<module-flat>.json`
   - graphify の `extract.py` を **5 言語版に絞った** スリム実装（py, ts, go, rs, java）
2. 出力 schema:
   ```json
   {
     "module": "<id>",
     "extracted_at": "<ISO8601>",
     "files": [{"path": "...", "lang": "py", "loc": 0}],
     "imports": [{"from_file": "...", "to": "...", "kind": "import|from", "evidence": "L42"}],
     "calls": [{"caller": "func_a", "callee": "func_b", "evidence": "L58", "confidence": "EXTRACTED", "confidence_score": 1.0}],
     "definitions": [{"kind": "class|function", "name": "...", "file": "...", "line": 0}],
     "stats": {"file_count": 0, "loc_total": 0, "import_count": 0}
   }
   ```
**効果**:
- module-analyst の Q4 は **「ast.json を読んで集約するだけ」** に縮退、トークン 60% 削減見込み
- Q4 が決定論で取れるので fragility 推定（壊れる条件）に LLM 思考を集中できる

### 4.2 `community-clusterer` agent（Phase 5.5）

**目的**: dep-graph を Leiden で分割し、後段の routing が「intent ↔ community」を扱えるようにする。

```yaml
name: community-clusterer
description: dep-graph に Leiden を実行し、module の community ID と cohesion を計算
tools: Bash, Read, Write
model: haiku
```

**処理**:
1. `python tribal/scripts/cluster.py .claude/context/_dep-graph.json` 実行
   - graphify の `cluster.py` をそのまま借用（graspologic → Louvain fallback）
2. 出力: `.claude/context/_communities.json`
   ```json
   {
     "generated_at": "<ISO8601>",
     "method": "leiden|louvain",
     "communities": {
       "0": {"members": ["<module>", ...], "cohesion": 0.78, "label": null},
       "1": {...}
     },
     "node_to_community": {"<module>": 0, ...},
     "stats": {"count": 0, "avg_size": 0.0, "max_size": 0}
   }
   ```
3. community label は次の `god-node-detector` 完了後に `routing-upgrader` が命名

**効果**:
- `tribal-router` が intent → community → primary という 2 段階選定可能になり、ripple 暴発を抑制
- ripple_index も community-aware にすると（同 community 内 module 優先）誤爆減

### 4.3 `god-node-detector` agent（Phase 6.5）

**目的**: degree top-N の hub module を抽出し、routing の primary_contexts を機械推薦。

```yaml
name: god-node-detector
description: dep-graph と community から各 community の god node を算出、primary_contexts 候補を生成
tools: Bash, Read, Write
model: haiku
```

**処理**:
1. graphify `analyze.py` の `god_nodes()` パターンを移植
   - **重要**: file-level hub と method stub の除外ルールも借用
2. 各 community 内で degree トップ 1-2 個を `god_node` として記録
3. 出力: `.claude/context/_god-nodes.json`
   ```json
   {
     "global_top_n": [{"module": "...", "degree": 0, "community": 0}],
     "per_community": {
       "0": [{"module": "...", "degree": 0, "context_file": ".claude/context/<flat>.md"}]
     },
     "recommended_primaries": {
       "schema-change": ["<module-flat>.md", ...],
       "ops-investigation": [...]
     }
   }
   ```
4. `recommended_primaries` は intent と community の親和性スコアで生成（heuristic + analyst Q1 のキーワードマッチ）

**効果**:
- `routing-upgrader` の入力が「真っ白から作る」→「god-node-detector の推薦を採否する」になる
- routing-table の正確性が機械的に裏打ちされる

### 4.4 `benchmark-reporter` agent（Phase 8.5）

**目的**: 「全 context を読む naive ベースライン vs router 経由」の token 比を毎回計測。

```yaml
name: benchmark-reporter
description: router 経由ロード vs raw load の token 数を比較し、reduction ratio を出力
tools: Bash, Read, Write
model: haiku
```

**処理**:
1. graphify `benchmark.py` の `_estimate_tokens` (4 chars/token) を流用
2. `prompt-tester` の各テストケースについて:
   - **naive baseline** = `.claude/context/*.md` 全件の文字数 / 4
   - **routed** = router が選定した context の文字数 / 4
3. 出力: `.claude/artifacts/benchmark.json`
   ```json
   {
     "executed_at": "<ISO8601>",
     "router_version_hash": "<sha1>",
     "per_case": [
       {"case_id": "...", "baseline_tokens": 0, "routed_tokens": 0, "ratio": 0.0}
     ],
     "summary": {
       "avg_ratio": 0.0,
       "median_ratio": 0.0,
       "p95_ratio": 0.0,
       "baseline_avg_tokens": 0,
       "routed_avg_tokens": 0
     }
   }
   ```
4. `_quality-log.jsonl` にも `tokens_saved_ratio` を追記

**効果**:
- tribal の価値が **数値で証明される**（graphify の「71.5x」のような訴求）
- CI の品質ゲートに「baseline 比 -20% 劣化で fail」を加えて、router の質が静かに落ちるのを防ぐ

### 4.5 `tribal/cache.py`（横串 Cache Layer）

graphify `cache.py` をベースに、tribal 用に **module 単位のキー設計** で改修:

```python
# tribal/scripts/cache.py
def module_hash(module_path: Path, repo_root: Path = Path(".")) -> str:
    """module 配下の全 source file を集約して SHA256。
    - .gitignore / .tribalignore で除外されるものは含めない
    - mtime ではなく content で hash するので branch 切り替えに強い
    - .md の YAML frontmatter は除外（graphify と同様）
    """
    ...

def load_cached_artifact(module_id: str, kind: str) -> dict | None:
    """kind ∈ {ast, analyst, critic, context}"""
    ...

def save_cached_artifact(module_id: str, kind: str, payload: dict) -> None:
    ...
```

**効果**:
- refresh モードで「ripple で巻き込まれたが内容変化なし」の module は LLM ゼロで完了
- critic スコアも復元可能なので、品質ログの連続性が保たれる
- artifact retention（30 日）も graphify 同様に CI の prune step で実装

### 4.6 `tribal/serve.py`（横串 Distribution Layer）

graphify `serve.py` をベースに、tribal 専用 MCP tool を公開:

| MCP tool | 入力 | 出力 |
|---|---|---|
| `route_query` | `{query: string}` | `{intent, primary_contexts, secondary_contexts, community}` |
| `get_intent` | `{name: string}` | intent 定義（keywords / anti_keywords / contexts） |
| `get_ripple` | `{module: string}` | ripple_index の該当エントリ |
| `get_god_nodes` | `{community?: int, top_n?: int}` | god node リスト |
| `get_community` | `{id: int}` | community メンバーと cohesion |
| `get_quality_history` | `{module: string}` | `_quality-log.jsonl` の該当 module 履歴 |

**効果**:
- Claude Desktop / Codex / Cursor から tribal の知識を共有可能
- tribal が「Claude Code 内 skill」から「**チームの routing intelligence**」に格上げされる

### 4.7 multi-platform installer

graphify `__main__.py` の `_PLATFORM_CONFIG` パターンを **3 platform に絞って** 採用:

| Platform | always-on 機構 |
|---|---|
| Claude Code | UserPromptSubmit hook + PostToolUse hook + PreToolUse(Read\|Glob\|Grep) hook + CLAUDE.md |
| Codex | AGENTS.md + .codex/hooks.json (PreToolUse) |
| OpenCode | AGENTS.md + .opencode/plugins/tribal.js (tool.execute.before) |

`tribal install --platform {claude,codex,opencode}` で配布。tribal の opt-in 強制機構が **3 platform 横断** で効くようになる。

---

## 5. 既存コンポーネントの強化

### 5.1 `module-analyst` のスリム化

**変更前**: Q1-Q5 全部を LLM で生成（Q4 の `Grep` import 集計も LLM が手動）

**変更後**:
1. 起動時に `.claude/artifacts/ast/<module-flat>.json` を必ず Read
2. Q4 (cross_module_deps) は ast.json の `imports` + `calls` から **集約するだけ**
3. Q2 (modification_patterns) も ast.json の `definitions` から候補ファイルを取得
4. analyst の主作業は **Q1 / Q3 / Q5** に集中
5. Q3 各項目に以下を必須化:
   ```json
   {
     "name": "...",
     "trap": "...",
     "evidence_file": "file:line",
     "why_non_obvious": "...",
     "confidence": "EXTRACTED|INFERRED|AMBIGUOUS",
     "confidence_score": 0.0,
     "related_modules": ["..."]   // semantic similarity 用
   }
   ```
6. **新規**: `Q3_hyperedges` フィールド
   ```json
   "Q3_hyperedges": [
     {
       "id": "shared_validator_normalization_trap",
       "label": "全 schema validator が共通の正規化ルールを共有",
       "modules": ["mod_a", "mod_b", "mod_c"],
       "trap": "正規化順序を変えると 3 module 同時に壊れる",
       "evidence": [{"file": "...", "line": 0}, ...]
     }
   ]
   ```

**効果**:
- 1 module あたりの LLM トークン消費 約 50-60% 削減見込み
- AMBIGUOUS Q3 が機械的にトリアージされ、critic ループが短縮
- hyperedge で「3 module 横断の trap」が初めて表現可能に（graphify の哲学）

### 5.2 `context-critic` の判定基準アップグレード

**変更前**: 5 軸スコア、`overall < 4.0` で FIX、`path_accuracy < 5.0` で即 FIX

**変更後**:
1. 既存 5 軸はそのまま維持
2. **追加軸**: `confidence_consistency` (0-5)
   - context に書かれた Q3 と analyst JSON の confidence_score が整合しているか
   - AMBIGUOUS な Q3 を「断定形」で書いてないか
3. **追加判定**:
   - analyst の Q3 に `confidence: AMBIGUOUS` が 1 件以上あれば、verdict は最低でも `MANUAL_REVIEW`（FIX で消すのではなく、人手判断に upgrade）
4. PASS 閾値を **confidence_score 加重平均** に変更:
   ```
   weighted_overall = sum(score_axis * weight_axis) / sum(weight_axis)
   weight_axis: path_accuracy=2.0, non_obvious_value=2.0, others=1.0
   ```

**効果**:
- 「断定形で書かれた怪しい知識」を critic が検出可能に
- AMBIGUOUS の自動上申で reconciliation ループが平均 0.5 ラウンド短縮見込み

### 5.3 `dependency-indexer` の edge 拡張

**変更前**: edges = `{from, to, kind, fragility, evidence}`

**変更後**:
1. edge に `confidence` `confidence_score` を追加
2. **新 edge type**: `semantically_similar_to`（INFERRED）
   - 2 module の Q1 と Q3 のキーワードベクトルで類似度算出（embedding ではなく Jaccard / TF-IDF で軽量化）
   - 0.7 以上なら semantic similarity edge として記録
3. **新 edge type**: `rationale_for`（graphify からの借用）
   - Q5 の commit_message / pr_description が「why」を述べている場合、その module を `rationale_source` として接続
4. `_dep-graph.json` schema 更新（既存フィールドは維持、追加分は optional）

**効果**:
- ripple_index が「呼んでないが概念的に近い module」も拾えるように
- graphify の `semantically_similar_to` を **module 粒度** で再現

### 5.4 `tribal-router` skill の 2 段階選定

**変更前**: intent → primary_contexts → ripple expansion → 上限カット

**変更後**:
```
Step 1: Intent 分類（既存）
Step 2: Community 解決
   - intent が _routing-table.json で community ヒントを持つ場合、その community に絞る
   - god_node-recommended primaries を最優先候補に
Step 3: Primary 選定（god_node 由来 1-2 + LLM 推定 0-1）
Step 4: Ripple expansion（既存、ただし同 community 内優先）
Step 5: 上限カット（既存）
Step 6: Wiki Fallback ★NEW
   - intent 不明 / community ヒットせず → .claude/context/_index.md へ誘導
   - ユーザーに community 一覧を提示して手動選択させる
```

**効果**:
- ripple 暴発による 5 枚オーバーが減る
- intent 不明時の体験が向上（黙って fallback ではなく `_index.md` というナビ点を提示）

### 5.5 hook 三段重ね

| Hook | 既存 / 新規 | matcher | 役割 |
|---|---|---|---|
| `UserPromptSubmit` | 既存 | (all) | 開発タスク検出時に router 起動指示を注入 |
| `PostToolUse` | 既存 | `Write\|Edit\|MultiEdit` | context.md を validate（行数/heading/path） |
| `PreToolUse` | **★新規** | `Read\|Glob\|Grep` | router 未起動セッションで raw 探索が始まったら警告注入 |

PreToolUse hook 実装イメージ（graphify 由来）:
```python
# tribal/scripts/check_router_state.py
state = load_session_state()
if state.get("opted_out"):
    sys.exit(0)
if state.get("last_routing_ts", 0) + 30 * 60 > time.time():
    sys.exit(0)  # 直近で router が走っていれば素通し
# router 未起動状態で Read/Glob/Grep が来た → 注意喚起
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext": "tribal: router 未起動です。.claude/context/*.md を直接読む前に /tribal-route を検討してください。"
    }
}))
```

**効果**:
- UserPromptSubmit hook をすり抜けて Read が走るケース（途中の subagent 起動など）を救う
- defense-in-depth で opt-in 原則の漏れが減る

### 5.6 `_quality-log.jsonl` schema 拡張

```diff
 {
   "timestamp": "ISO8601",
   "module": "<id>",
   "file": "<context path>",
   "round": 3,
   "scores": {...},
   "overall": <float>,
   "verdict": "PASS|FIX|MANUAL_REVIEW",
   "manual_review_required": false,
+  "weighted_overall": <float>,
+  "tokens_saved_ratio": <float | null>,
+  "confidence_summary": {"extracted": 0, "inferred": 0, "ambiguous": 0},
+  "ast_extraction_method": "ast_v1|ast_v2",
+  "cache_hit": true|false
 }
```

CI の `check_quality_regression.py` も `weighted_overall` を比較対象にし、加えて `tokens_saved_ratio` の前回比 -20% 以上劣化を fail 条件に追加。

---

## 6. ファイル / ディレクトリ構成 diff

```diff
 your-monorepo/
 ├── CLAUDE.md
 ├── .gitignore
 ├── .claude/
 │   ├── settings.json                    # PreToolUse(Read|Glob|Grep) 追加
 │   ├── scripts/
 │   │   ├── validate_context_file.py
 │   │   ├── inject_router_directive.py
 │   │   ├── detect_changed_modules.py
 │   │   ├── check_quality_regression.py  # benchmark gate 追加
 │   │   ├── flatten_module_path.py
+│   │   ├── check_router_state.py        # PreToolUse hook 本体
+│   │   ├── ast_extract.py               # tree-sitter wrapper (5 lang)
+│   │   ├── cluster.py                   # Leiden / Louvain wrapper
+│   │   ├── benchmark.py                 # token reduction 計測
+│   │   └── cache.py                     # SHA256 module artifact cache
 │   ├── skills/
 │   │   ├── tribal-mapper/SKILL.md       # Phase 2a/5.5/6.5/8.5 追記
 │   │   └── tribal-router/SKILL.md       # 2 段階選定に書き換え
 │   ├── agents/
 │   │   ├── repo-explorer.md
 │   │   ├── module-analyst.md            # スリム化、confidence 必須化
 │   │   ├── context-writer.md
 │   │   ├── context-critic.md            # 6 軸目 + MANUAL_REVIEW verdict
 │   │   ├── context-fixer.md
 │   │   ├── dependency-indexer.md        # semantic_similar_to / rationale_for 追加
 │   │   ├── coverage-auditor.md
 │   │   ├── routing-upgrader.md          # god-node 推薦を判定する役割に
 │   │   ├── prompt-tester.md
+│   │   ├── module-ast-extractor.md      # ★新規
+│   │   ├── community-clusterer.md       # ★新規
+│   │   ├── god-node-detector.md         # ★新規
+│   │   └── benchmark-reporter.md        # ★新規
 │   ├── commands/
 │   │   ├── tribal-init.md               # Phase 追加を反映
 │   │   ├── tribal-refresh.md            # cache 利用を反映
 │   │   ├── tribal-route.md
 │   │   └── tribal-validate.md           # benchmark step 追加
 │   ├── schemas/
 │   │   ├── analyst.schema.json          # confidence / hyperedges 追加
 │   │   ├── critic.schema.json           # MANUAL_REVIEW / weighted_overall
 │   │   ├── coverage.schema.json
 │   │   ├── dep-graph.schema.json        # confidence / similarity edge
 │   │   ├── quality-log.schema.json      # tokens_saved_ratio 等
 │   │   ├── routing-table.schema.json    # community ヒント field
+│   │   ├── ast.schema.json              # ★新規
+│   │   ├── communities.schema.json      # ★新規
+│   │   ├── god-nodes.schema.json        # ★新規
+│   │   └── benchmark.schema.json        # ★新規
 │   ├── critic-workspace/
 │   ├── .session-state/
 │   ├── artifacts/
 │   │   ├── analyst/
 │   │   ├── critic/
 │   │   ├── tests/
+│   │   ├── ast/                         # ★新規
+│   │   └── benchmark.json               # ★新規
+│   ├── cache/                           # ★新規 (SHA256 keyed)
 │   └── context/
 │       ├── _repo-map.json
 │       ├── _routing-table.json
 │       ├── _dep-graph.json
 │       ├── _coverage.json
 │       ├── _quality-log.jsonl
+│       ├── _communities.json            # ★新規
+│       ├── _god-nodes.json              # ★新規
+│       └── _index.md                    # ★新規 (wiki entry, router fallback)
+├── tribal/                              # ★新規 (Python lib, MCP server)
+│   ├── __init__.py
+│   ├── __main__.py                      # tribal install --platform ...
+│   ├── ast_extract.py
+│   ├── cluster.py
+│   ├── benchmark.py
+│   ├── cache.py
+│   ├── security.py
+│   └── serve.py                         # MCP server
+├── pyproject.toml                       # ★新規
 └── .github/workflows/
     └── tribal-refresh.yml               # benchmark gate 追加
```

---

## 7. データスキーマ変更（要点のみ）

### `analyst.schema.json` diff

```diff
 "Q3_non_obvious_patterns": {
   "type": "array",
   "items": {
     "type": "object",
-    "required": ["name", "trap", "evidence_file", "why_non_obvious"],
+    "required": ["name", "trap", "evidence_file", "why_non_obvious",
+                 "confidence", "confidence_score"],
     "properties": {
       "name": {"type": "string"},
       "trap": {"type": "string"},
       "evidence_file": {"type": "string"},
       "why_non_obvious": {"type": "string"},
+      "confidence": {"enum": ["EXTRACTED", "INFERRED", "AMBIGUOUS"]},
+      "confidence_score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
+      "related_modules": {"type": "array", "items": {"type": "string"}}
     }
   }
 },
+"Q3_hyperedges": {
+  "type": "array",
+  "items": {
+    "type": "object",
+    "required": ["id", "label", "modules", "trap"],
+    "properties": {
+      "id": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
+      "label": {"type": "string"},
+      "modules": {"type": "array", "minItems": 3, "items": {"type": "string"}},
+      "trap": {"type": "string"},
+      "evidence": {"type": "array"}
+    }
+  }
+}
```

### `dep-graph.schema.json` diff

```diff
 "edges": {
   "items": {
-    "required": ["from", "to", "kind"],
+    "required": ["from", "to", "kind", "confidence_score"],
     "properties": {
       "kind": {
-        "enum": ["import", "config", "runtime", "serialization", "build", "schema"]
+        "enum": ["import", "config", "runtime", "serialization", "build", "schema",
+                 "semantically_similar_to", "rationale_for"]
       },
+      "confidence": {"enum": ["EXTRACTED", "INFERRED", "AMBIGUOUS"]},
+      "confidence_score": {"type": "number", "minimum": 0.0, "maximum": 1.0}
     }
   }
 }
```

### `routing-table.schema.json` diff

```diff
 "intents": {
   "items": {
     "properties": {
+      "community_hint": {"type": "integer", "minimum": 0},
+      "god_node_recommended": {"type": "array", "items": {"type": "string"}}
     }
   }
 }
```

---

## 8. 移行ステップ（既存 tribal 利用者向け）

既存の tribal を破壊しない段階的移行:

### ステップ 1: Cache layer 単独導入（リスク最小）
- `tribal/cache.py` だけ追加し、`detect_changed_modules.py` から呼べるようにする
- 既存挙動は不変、refresh が高速化されるだけ
- 検証: `/tribal-refresh` で cache hit 数が log に出るか

### ステップ 2: AST 第1パス追加
- `module-ast-extractor` agent と `ast_extract.py` を追加
- `module-analyst` の prompt を更新して ast.json を Read するように
- 旧 analyst 出力との互換性: ast.json が無ければ従来動作にフォールバック

### ステップ 3: Confidence label の必須化
- analyst.schema.json の Q3 に required 追加
- 既存 artifact は migration script で confidence=EXTRACTED (1.0) を埋めて互換維持

### ステップ 4: Community + god_node 導入
- Phase 5.5 / 6.5 を skill に追加
- `routing-upgrader` を「判定者」モードに更新
- routing-table 既存 intent には community_hint=null で互換維持

### ステップ 5: Benchmark + 新 hook
- `benchmark-reporter` agent と PreToolUse hook を追加
- CI gate に benchmark 回帰を組み込む

### ステップ 6: MCP server + multi-platform
- `tribal install --platform codex` 等を提供
- 既存ユーザーは `tribal install --platform claude` を 1 度叩けば現状維持

各ステップは独立して PR 化可能。tribal の哲学が壊れない順序で構成。

---

## 9. 期待効果（測定可能な指標）

| 指標 | 現状（推定） | 改善後（目標） | 算定根拠 |
|---|---|---|---|
| `/tribal-init` 1 回あたり LLM トークン | 100% | 35-45% | AST が Q4 を担当 → analyst トークン 50-60% 減 |
| `/tribal-refresh` 平均所要時間 | 100% | 25-40% | cache hit で再分析スキップ |
| router 選定平均 context 数 | 4.5 枚 | 3.0-3.5 枚 | community 制約で ripple 暴発抑制 |
| critic 平均ラウンド | 2.3 | 1.7 | AMBIGUOUS 自動上申で空回り減 |
| naive vs router token reduction | 未計測 | 10-30x（規模次第） | benchmark で毎回可視化 |
| routing intent 誤分類率 | 不明 | < 5% | god_node primary 推薦で安定化 |

graphify の「71.5x」は corpus 規模依存だが、tribal が想定する mid-size monorepo（50-200 module）でも 10-30x は射程内。

---

## 10. リスクと緩和策

| リスク | 緩和策 |
|---|---|
| AST 第1パスで対応言語に依存（5 言語） | 未対応言語は従来 LLM フローにフォールバック。`ast_extract.py` の dispatch に「未対応 → skip」を実装 |
| Leiden が graspologic に依存（Python 3.13 で不可） | graphify と同様 Louvain fallback を実装。pyproject の `graspologic; python_version < '3.13'` |
| Cache invalidation バグで stale な analyst を返す | hash key に repo HEAD SHA も混ぜる、`/tribal-validate` で cache 全 purge オプション提供 |
| confidence_score の校正がバラつく | analyst prompt に「INFERRED は 0.6-0.9、AMBIGUOUS は 0.1-0.3、EXTRACTED は常に 1.0」を強制（graphify と同じ規範） |
| MCP server が複数 platform で同時起動して conflict | stdio 通信なので port conflict は無し、ただし graph.json への同時書き込みは file lock で防御 |
| PreToolUse hook が Read/Glob/Grep の度に発火してうるさい | 30 分の TASK_WINDOW 内は素通し（既存 inject_router_directive と同一ロジック流用） |
| 多 platform 配布で skill 内容のドリフト | graphify の `.tribal_version` 同期パターンを採用、skill ファイルの SHA を install 時に検証 |

---

## 11. 哲学の保全チェック

最後に、tribal の元コンセプトが守られているか自己検証:

- ✅ **3層構造**: Pre-compute / Runtime / Maintenance を維持（横串 Cache / Distribution は補助）
- ✅ **opt-in 物理強制**: hook 追加で **強化** こそすれ緩和してない
- ✅ **compass 形式**: context の 25-40 行 / 4 必須 heading は不変
- ✅ **5 問フレームワーク**: Q1-Q5 は全て残存。Q3 は confidence 拡張、Q3_hyperedges は補助 field
- ✅ **critic 物理隔離**: critic-workspace は不変
- ✅ **3-5 枚原則**: router の選定数上限は不変、community で精度向上のみ
- ✅ **「全部読まない」**: PreToolUse hook 追加で **強化**

graphify からの輸入で **tribal が graphify になる** わけではなく、tribal の compass + opt-in 哲学を **graphify の決定論性 + 計量性で支える** 関係になる。

---

## 付録 A: 採用しなかった graphify 要素と理由

| graphify 要素 | 不採用理由 |
|---|---|
| 25 言語 tree-sitter | tribal 利用者の monorepo は通常 3-5 言語。フル対応は依存爆発のコスト > 価値 |
| Whisper 動画/音声転写 | tribal の対象は code + comment + commit。動画は範囲外 |
| yt-dlp ingest | 同上 |
| HTML interactive viz (vis.js) | tribal の出力は markdown context が中心、HTML は不要 |
| Obsidian vault export | wiki/index.md で代替（より軽量） |
| Neo4j / GraphML / SVG export | 過剰、_dep-graph.json で十分 |
| 14 platform 全対応 | 初期は Claude/Codex/OpenCode の 3 platform で 80% カバー |
| Leiden の自動 community 分割（25%超） | tribal は module 数が高々数百なので、graphify ほど積極分割不要 |
| god_node の file-level hub 除外 heuristic 全部 | tribal は module 単位なので、より単純な「degree top-N + community 制約」で十分 |

## 付録 B: 用語対応表（tribal ↔ graphify）

| tribal 概念 | graphify 概念 | 編み込み後の意味 |
|---|---|---|
| module | community node の集合 | community に属する複数 module |
| context.md | GRAPH_REPORT.md (per community) | community wiki article の subset |
| Q3 (non-obvious pattern) | INFERRED / AMBIGUOUS edge | confidence + score 付きの pattern |
| Q4 (cross_module_deps) | EXTRACTED edge (imports/calls) | AST 抽出 + LLM fragility 注釈 |
| Q5 (tribal knowledge) | rationale_for node + edge | commit/comment 由来の why ノード |
| ripple_index | 1-hop neighborhood | community 内優先の 1-hop |
| primary_contexts | god nodes (degree top) | 機械推薦 + 人手承認 |
| intent | community label + keyword | community へのエイリアス |
| critic 5 軸 | confidence_score 5 dim | 同じ 5 軸 + confidence_consistency |
| `_quality-log.jsonl` | benchmark 履歴 | 品質 + token reduction の時系列 |

---

**改善案ここまで**。実装着手前に、ステップ 1（cache 単独導入）からの段階的 PR を推奨。
