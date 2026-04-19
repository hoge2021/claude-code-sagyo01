# Tribal v2 Architecture

`tribal-improvement-plan.md` の編み込み設計を、最終実装ベースで記述する文書。

## 全体像

```
┌──────────────────────────────────────────────────────────────┐
│  Pre-compute Layer                                           │
│   Phase 1   Discovery        repo-explorer                   │
│   Phase 2a  Structural       module-ast-extractor (★v2)      │
│   Phase 2b  Semantic         module-analyst (slim, AST 連携) │
│   Phase 3   Compose          context-writer                  │
│   Phase 4   Quality Gate     context-critic ⇄ context-fixer  │
│                              (★v2: MANUAL_REVIEW verdict)     │
│   Phase 5   Indexing         dependency-indexer              │
│                              (★v2: confidence/score + new edges)│
│   Phase 5.5 Clustering       community-clusterer (★v2)       │
│   Phase 6   Coverage Audit   coverage-auditor                │
│   Phase 6.5 God Detection    god-node-detector (★v2)         │
│   Phase 7   Routing Build    routing-upgrader (judge mode)   │
│                              + _index.md 生成 (★v2)          │
│   Phase 8   Regression Test  prompt-tester                   │
│   Phase 8.5 Benchmark        benchmark-reporter (★v2)        │
├──────────────────────────────────────────────────────────────┤
│  Runtime Layer                                               │
│   tribal-router skill (intent → community → primary → ripple)│
│   PreToolUse hook on Read|Glob|Grep (★v2 defense-in-depth)   │
├──────────────────────────────────────────────────────────────┤
│  Maintenance Layer                                           │
│   /tribal-refresh (cache-aware diff)                         │
│   /tribal-validate (+ benchmark gate)                        │
│   GitHub Actions (quality + benchmark regression)            │
├──────────────────────────────────────────────────────────────┤
│  ★ Cross-cutting: Cache Layer                                │
│   tribal/cache.py — SHA256 per-module artifact cache         │
├──────────────────────────────────────────────────────────────┤
│  ★ Cross-cutting: Distribution Layer                         │
│   tribal/serve.py — 6 MCP tools                              │
│   tribal install --platform {claude,codex,opencode}          │
└──────────────────────────────────────────────────────────────┘
```

## モジュール責務一覧

### Python パッケージ (`tribal/`)

| Module | 関数 | 責務 |
|---|---|---|
| `cache.py` | `module_hash` / `load_cached_artifact` / `save_cached_artifact` | SHA256 cache の唯一の権威 |
| `ast_extract.py` | `extract_module` / `extract_file` | tree-sitter で imports / definitions / calls 抽出 |
| `cluster.py` | `cluster` / `cohesion_score` | Leiden/Louvain による community 分割 |
| `god_nodes.py` | `detect_god_nodes` / `compute_degree` | degree-based hub + intent 推薦 |
| `benchmark.py` | `run_benchmark` / `naive_baseline_tokens` / `routed_tokens` | router の実効果計測 |
| `check_router_state.py` | `main` (hook entry) | router 起動状態を監視、stale 時 warning 注入 |
| `security.py` | `validate_url` / `validate_context_path` / `sanitize_label` | SSRF / traversal / XSS 防御 |
| `serve.py` | `route_query` / `get_intent` / `get_ripple` / `get_god_nodes` / `get_community` / `get_quality_history` | MCP server (stdio) 6 tools |
| `__main__.py` | `cmd_install` / `cmd_uninstall` / `cmd_serve` | CLI エントリ |

### Hook scripts (`.claude/scripts/`)

ランタイム実行用、`tribal/` 配下と並行配置 (将来的に shim 化検討)。

| Script | hook event | 役割 |
|---|---|---|
| `inject_router_directive.py` | UserPromptSubmit | 開発タスク検出時に router 起動指示を注入 (v1) |
| `validate_context_file.py` | PostToolUse(Write/Edit) | context.md の 25-45 行・必須 heading・path 実在性検証 (v1 + v2 security 強化) |
| `check_router_state.py` | PreToolUse(Read/Glob/Grep) | router 未起動で context Read を試行したら警告 (★v2 新規) |
| `detect_changed_modules.py` | (CLI/refresh) | 変更検出 + cache hit 排除 |
| `check_quality_regression.py` | (CI) | weighted_overall + tokens_saved_ratio 比較 |
| `cluster.py` / `god_nodes.py` / `benchmark.py` / `ast_extract.py` | (Phase 2a/5.5/6.5/8.5 で agent 経由起動) | 各 phase の実装本体 |
| `migrate_v1_to_v2.py` | (one-shot) | v1 artifact を v2 schema に充当 |

### Subagents (`.claude/agents/`)

| Agent | model | 入力 | 出力 |
|---|---|---|---|
| `repo-explorer` | sonnet | repo root | `_repo-map.json` |
| `module-ast-extractor` ★v2 | haiku | module_id/path | `artifacts/ast/<flat>.json` |
| `module-analyst` (v2 slim) | sonnet | module + ast.json | `artifacts/analyst/<flat>.json` |
| `context-writer` | sonnet | analyst.json | `context/<flat>.md` |
| `context-critic` (v2 6 軸) | opus | context.md (隔離) + analyst confidence | `artifacts/critic/<flat>.json` |
| `context-fixer` (v2 MANUAL_REVIEW skip) | sonnet | critic + analyst | 修正済 context.md |
| `dependency-indexer` (v2 enriched edges) | sonnet | analyst.json all | `_dep-graph.json` |
| `community-clusterer` ★v2 | haiku | dep-graph | `_communities.json` |
| `coverage-auditor` | sonnet | repo-map + context.md | `_coverage.json` |
| `god-node-detector` ★v2 | haiku | dep-graph + communities + routing-table | `_god-nodes.json` |
| `routing-upgrader` (v2 judge mode) | sonnet | analyst + dep-graph + communities + god-nodes | `_routing-table.json` + `_index.md` |
| `prompt-tester` | sonnet | routing-table | `artifacts/tests/prompt-tests.json` |
| `benchmark-reporter` ★v2 | haiku | prompt-tests + context | `artifacts/benchmark.json` + `_quality-log.jsonl` |

## データフロー

```
source code
   │
   ▼
[Phase 1] repo-explorer ─────────────► _repo-map.json
   │
   ├──► [Phase 2a] ast_extract ─────► artifacts/ast/<flat>.json
   │                                       │
   ▼                                       │
[Phase 2b] module-analyst ◄────────────────┘ (Step 0 で Read)
   │
   ▼
artifacts/analyst/<flat>.json (Q1-Q5 + confidence)
   │
   ├──► [Phase 3] context-writer ──► context/<flat>.md
   │                                       │
   │                                       ▼
   │                                 [Phase 4] critic ⇄ fixer ループ
   │                                       │
   │                                       ▼
   │                                 _quality-log.jsonl (weighted_overall)
   │
   ├──► [Phase 5] dependency-indexer ─► _dep-graph.json (confidence + new edges)
   │                                          │
   │                                          ▼
   │                                  [Phase 5.5] cluster ─► _communities.json
   │                                          │
   ├──► [Phase 6] coverage-auditor ─► _coverage.json
   │                                          │
   │                                          ▼
   │                                  [Phase 6.5] god_nodes ─► _god-nodes.json
   │                                          │
   ▼                                          ▼
[Phase 7] routing-upgrader (judge) ──► _routing-table.json + _index.md
   │
   ▼
[Phase 8] prompt-tester ──► artifacts/tests/prompt-tests.json
   │
   ▼
[Phase 8.5] benchmark-reporter ──► artifacts/benchmark.json
```

Cache layer は Phase 2a/2b/4 の各成果物に SHA256 で介入し、変更のない module は LLM ゼロで復帰。

## 拡張ポイント (Phase 7 未対応 + 将来)

- v1 バグ #1 (単独拡張子 backtick が path 誤判定) — `validate_context_file.py:is_path_like()` に「`/` を含まない単独拡張子は path 扱いしない」追加
- v1 バグ #3 (ARCHITECTURE.md ヒント未活用) — `repo-explorer.md` に「ARCHITECTURE.md / docs/ARCHITECTURE.md 等の存在 → 記載 module を優先採用」追加
- semantically_similar_to / rationale_for edge の実生成 (現在は dependency-indexer prompt に仕様のみ)
- routing-upgrader の god_node 推薦却下 logic (現在は LLM 任せ)
- Codex / OpenCode 実機検証
- `.claude/scripts` と `tribal/` の sync 戦略確定 (現在は二重コピー)

## セキュリティモデル (graphify 由来)

| 攻撃ベクトル | 防御 |
|---|---|
| URL 経由 SSRF | `validate_url`: http/https 限定、private IP block、cloud metadata block |
| open-redirect SSRF | `_NoFileRedirectHandler`: redirect 毎に re-validation |
| oversized fetch | `safe_fetch`: 50 MB cap, streaming read |
| path traversal (MCP server) | `validate_context_path`: `.claude/` 配下に限定 |
| label XSS | `sanitize_label`: control char strip + 256 char cap |
| MCP 出力 prompt injection | 全 tool 出力を `sanitize_label` で前処理 |
| eval / shell=True | 不使用 (graphify と同様) |

## 完了条件

- ✅ 9 subagents (v1) + 4 新規 (v2) = 合計 13 agents
- ✅ 6 MCP tools
- ✅ 3 platform installer
- ✅ 3 重 hook 強制 (UserPromptSubmit + PostToolUse + PreToolUse)
- ✅ benchmark で token reduction 数値化
- ✅ Cross-Phase regression 4 ケース PASS
- ⏳ 実 LLM /tribal-init での 6 定量指標 baseline 比較 (Phase 7 ユーザー実施)
