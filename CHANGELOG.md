# Changelog

All notable changes for Tribal Knowledge Mapper.

## [2.0.0-rc1] - 2026-04-19

### Added — graphify-derived synergy (Tribal v2)

#### Phase 1 — Cache Layer
- `tribal/cache.py` — SHA256 per-module artifact cache
- module_hash 算出: sorted(file body SHA256) + git HEAD SHA + cache schema version
- `.md` ファイルは YAML frontmatter を hash 対象外 (graphify 由来、metadata-only 編集で cache invalidation を防ぐ)
- `detect_changed_modules.py` を cache-aware に拡張 (`cached_modules`, `cache_skipped_from_changes`, `--no-cache` flag)
- 副次的修正: tribal v1 の単一ファイル module の mtime 検出漏れバグ (`rglob('*')` 空集合問題)

#### Phase 2 — AST 第1パス
- `tribal/ast_extract.py` — tree-sitter 5 言語 (Python/TypeScript/Go/Rust/Java) の決定論的抽出
- `module-ast-extractor` agent (model=haiku, LLM 呼び出しゼロ)
- `module-analyst` を Step 0 (AST.json Read) → Q1/Q3/Q5 集中型にスリム化
- AST.json 不在時は従来動作に graceful fallback
- artifact size 圧縮: calls dedup + imports `raw` 削除で source 比 1.07x に

#### Phase 3 — Confidence Label 必須化
- analyst Q3 に `confidence` (EXTRACTED/INFERRED/AMBIGUOUS) + `confidence_score` (0.0-1.0) 必須化
- `Q3_hyperedges` フィールド追加 (3+ module 横断 trap)
- critic に 6 軸目 `confidence_consistency` + `MANUAL_REVIEW` verdict + `weighted_overall`
- AMBIGUOUS Q3 が 1 件以上で **自動 MANUAL_REVIEW** → fixer は触らず人間判断ループへ
- `migrate_v1_to_v2.py` (idempotent + dry-run) で v1 artifact を v2 互換化

#### Phase 4 — Community Detection + God Node Recommendation
- `tribal/cluster.py` — Leiden (graspologic) → Louvain (networkx) 自動 fallback
- `tribal/god_nodes.py` — degree top-N + per-community + intent ごとの primary 機械推薦
- `community-clusterer` + `god-node-detector` agents (haiku)
- routing-upgrader を「機械推薦の判定者」モードに変更 (採否を理由付きで記録)
- tribal-router skill を 7 step 化: intent → community 解決 → primary → community-aware ripple → wiki fallback
- `_communities.json` / `_god-nodes.json` / `_index.md` artifacts 新規

#### Phase 5 — Token Reduction Benchmark + PreToolUse Hook
- `tribal/benchmark.py` — naive vs router の token 削減比を case 毎に計測
- `benchmark-reporter` agent + Phase 8.5 を skill に追加
- `_quality-log.jsonl` に `tokens_saved_ratio` 自動追記
- `tribal/check_router_state.py` — PreToolUse(Read|Glob|Grep) hook で defense-in-depth 3 重化
- CI workflow に benchmark step + ratio < 5.0 で warning

#### Phase 6 — MCP Server + Multi-Platform Distribution
- `pyproject.toml` (PyPI: `tribal-knowledge-mapper`, import: `tribal`)
- `tribal/security.py` — graphify 由来の URL/path/label 検証 (SSRF + open-redirect + traversal + XSS 対策)
- `tribal/serve.py` — 6 MCP tools (route_query / get_intent / get_ripple / get_god_nodes / get_community / get_quality_history)
- `tribal/__main__.py` — `tribal install --platform {claude,codex,opencode}` で 3 platform 配布
- `validate_context_file.py` を `tribal.security.validate_context_path` 経由に強化

### Changed — Schemas (v2 拡張、v1 互換維持)

- `analyst.schema.json`: Q3 に confidence/score required、Q3_hyperedges/related_modules optional
- `critic.schema.json`: verdict に MANUAL_REVIEW、weighted_overall + confidence_consistency
- `dep-graph.schema.json`: edge に confidence/score、kind に semantically_similar_to / rationale_for
- `routing-table.schema.json`: community_hint / god_node_recommended / rejected_recommendations / wiki_index
- `quality-log.schema.json`: weighted_overall / tokens_saved_ratio / confidence_summary / cache_hit / ast_extraction_method

### Tribal v1 のバグ発見と修正 (副次的成果)

| # | バグ | 修正 |
|---|---|---|
| 1 | 単独拡張子 backtick (例 `` `.md` ``) を path として誤判定 | Phase 7 で対応予定 |
| 2 | See Also 未作成参照で部分構築が validation fail | community-aware で論理リンク化 |
| 3 | repo-explorer が ARCHITECTURE.md ヒントを無視 | Phase 7 で対応予定 |
| 4 | `mtime_based_changes()` が単一ファイル module で `rglob('*')` 空集合 | Phase 1 で修正済み |

### 哲学的シナジー

| graphify 哲学 | tribal v2 での編み込み |
|---|---|
| 不確実性を隠さない | AMBIGUOUS Q3 → 自動 MANUAL_REVIEW → 人間判断ループ |
| confidence を edge 単位で持つ | analyst Q3 / dep-graph edges 両方に confidence_score |
| 構造を semantic と分離 | AST (決定論) + analyst (LLM) の Phase 2a/2b 分割 |
| 計量で価値を証明 | benchmark で token 削減を毎回数値化 |
| MCP で他 agent と知識共有 | serve.py で 6 tools を公開 |
| defense-in-depth | hook 3 重化 (UserPromptSubmit + PostToolUse + PreToolUse) |

---

## [1.0.0] - tribal v1 (Meta blog 再現テンプレート baseline)

- 9 subagents / 2 skills / 4 slash commands / 5 hook scripts / 6 schemas
- 3 層構造 (Pre-compute / Runtime / Maintenance)
- compass 形式 25-40 行 context
- intent ベース routing で 3-5 枚動的選定
- critic 物理隔離 (`.claude/critic-workspace/`)
- ripple_index 1 段展開
- hook 強制 (UserPromptSubmit + PostToolUse)
- GitHub Actions による 14 日ごとリコンサイル + 品質回帰ゲート
