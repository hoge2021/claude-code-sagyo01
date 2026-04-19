# Tribal Knowledge Mapper 移行チェックシート

**対応計画書**: `/home/hoge/51_mygit/output/tribal-improvement-plan.md`
**対象ベース**: `/home/hoge/51_mygit/output/tribal/`
**作成日**: 2026-04-19

---

## このチェックシートの使い方

- 各 Phase は **独立した PR** として完結するように構成
- 各 Phase の終わりに **動作確認セクション** を必ず実施
- 動作確認で問題があれば、**ロールバック手順** に従って差し戻し
- Phase 間で `last_success_sha` や cache の互換性が保てるよう、order を変えない
- `[ ]` を `[x]` に変えながら進める

凡例:
- 📝 ファイル作成/変更
- 🧪 動作テスト
- 🔍 検証/確認
- ⏪ ロールバック手順
- ⚠️ 注意事項

---

## Phase 0: 準備 (前提整備)

### 0.1 環境確認

- [ ] 🔍 Python 3.10+ がインストール済み (`python3 --version`)
- [ ] 🔍 Claude Code 最新版 (`claude --version`)
- [ ] 🔍 Git リポジトリのクリーン状態を確認 (`git status`)
- [ ] 🔍 既存の `.claude/` ディレクトリのバックアップ (`cp -r .claude .claude.bak.20260419`)
- [ ] 🔍 既存 tribal で `/tribal-init` が完走することを確認（baseline 採取）

### 0.2 作業ブランチ作成

- [ ] 📝 ベースブランチからフィーチャーブランチを作成 (`git checkout -b tribal-v2-migration`)
- [ ] 📝 `tribal-improvement-plan.md` をリポジトリの `docs/` 配下にコピー（参照用）

### 0.3 依存パッケージの先行確認

- [ ] 🔍 後続で使うパッケージの利用可否を確認:
  ```bash
  pip install --dry-run tree-sitter tree-sitter-python tree-sitter-typescript \
    tree-sitter-go tree-sitter-rust tree-sitter-java \
    networkx graspologic mcp jsonschema
  ```
- [ ] 📝 `pyproject.toml` をリポジトリ直下に新規作成（後続 Phase で本格定義）
- [ ] ⚠️ Python 3.13 利用者は graspologic 不可。Phase 4 で Louvain fallback を確認

### 0.4 Phase 0 動作確認

- [ ] 🧪 `git log --oneline -5` で baseline commit を記録
- [ ] 🧪 `/tribal-init` 実行 → 完走を確認 → `cat .claude/context/_coverage.json` で `coverage_ratio` を baseline 値として記録
- [ ] 🧪 `/tribal-route 既存のスキーマに新フィールドを追加したい` → router が 3-5 枚を選定して提示することを確認
- [ ] 📝 baseline 値を `docs/tribal-v2-migration-baseline.md` に保存:
  - coverage_ratio
  - average quality score
  - prompt test pass_rate
  - `/tribal-init` 所要時間
  - 概算トークン消費

⏪ **ロールバック**: ブランチ削除 (`git checkout main && git branch -D tribal-v2-migration`)

---

## Phase 1: Cache Layer 単独導入 (最小リスク)

**目的**: SHA256 ベースの per-module cache を導入。既存挙動は不変、refresh が高速化されるだけ。

### 1.1 ファイル作成

- [x] 📝 `.claude/scripts/cache.py` を新規作成
  - graphify `cache.py` をベースに、`module_hash()` `load_cached_artifact(module_id, kind)` `save_cached_artifact(module_id, kind, payload)` を実装
  - `kind` パラメータは `"ast" | "analyst" | "critic" | "context"` を受け付ける
  - hash key には repo HEAD SHA も混ぜる（branch 切替えで stale を防ぐ）
  - `.md` ファイルの YAML frontmatter は除外して hash（graphify 流儀）
- [x] 📝 `.claude/cache/` ディレクトリを作成、`.gitkeep` を配置
- [x] 📝 `.gitignore` に `.claude/cache/*.json` と `!.claude/cache/.gitkeep` を追加

### 1.2 既存 script への組み込み

- [x] 📝 `.claude/scripts/detect_changed_modules.py` を更新:
  - `mtime_based_changes()` の前に `cache.py` の hash 比較を追加
  - cache hit module は `changed_modules` から除外
  - 出力 JSON に `cached_modules` フィールドを追加
  - **副次的 fix**: 単一ファイル module の mtime 検出漏れバグ修正
- [x] 📝 `.claude/commands/tribal-refresh.md` の「変更なしの場合」セクションに cache hit 数の報告を追記

### 1.3 単体テスト

- [x] 📝 `.claude/scripts/test_cache.py` を作成（pytest 不要、`python test_cache.py` で完結）
  - 同一内容ファイルのハッシュ一致
  - frontmatter 違いで hash 一致（.md のみ）
  - frontmatter 違いで hash 不一致（.py 等）
  - HEAD SHA 違いで hash 不一致
  - load → save → load 往復
  - 追加: invalid kind / cached_modules / clear_cache の 3 ケース

### 1.4 Phase 1 動作確認

- [x] 🧪 単体テスト実行 → **8/8 PASS**
- [x] 🧪 `python .claude/scripts/detect_changed_modules.py` → cache 関連フィールド出力確認
- [x] 🧪 cache populate → detect で cache hit 認識 (Test 2,4)
- [x] 🧪 ファイル編集 → cache miss → 再 changed_modules 入り (Test 5,8)
- [x] 🧪 `--no-cache` flag で cache fast path 無効化 (Test 7)
- [x] 🧪 baseline-target を v1 restore → regression なし
- [ ] 🧪 `/tribal-refresh` の実 LLM 実行は実機で別途 (Phase 7 統合 E2E)

⏪ **ロールバック**: `git revert <Phase 1 commits>` でいい。既存挙動への影響は最小限なので破壊リスクはほぼ無い。

✅ **Phase 1 完了**: cache layer 動作、tribal v1 バグ #4 (single-file mtime) も副次的に修正、regression なし。詳細は `docs/phase1-completion-report.md`。

---

## Phase 2: AST 第1パス追加

**目的**: tree-sitter で Q2/Q4 を決定論抽出し、`module-analyst` のトークン消費を削減。

### 2.1 AST 抽出スクリプト

- [x] 📝 `.claude/scripts/ast_extract.py` を新規作成 (281 LOC)
- [x] 📝 `.claude/schemas/ast.schema.json` を新規作成

### 2.2 新 agent 定義

- [x] 📝 `.claude/agents/module-ast-extractor.md` を新規作成

### 2.3 既存 agent の更新

- [x] 📝 `.claude/agents/module-analyst.md` を更新 (Step 0 で AST.json を Read)
- [x] 📝 `.claude/skills/tribal-mapper/SKILL.md` を Phase 2a/2b 分割
- [x] 📝 `.claude/artifacts/ast/.gitkeep` を作成
- [x] 📝 `.gitignore` に `.claude/artifacts/ast/*.json` 追加

### 2.4 単体テスト

- [x] 📝 `tests/fixtures/sample_module/` を作成 (py/ts/go/rs/java)
- [x] 🧪 9/9 PASS (5 言語 + unsupported fallback + cache + stem fallback)

### 2.5 Phase 2 動作確認

- [x] 🧪 単体テスト 5 言語全 PASS
- [x] 🧪 baseline-target で 18 modules AST 抽出 → 0.29s / cache hit 後 0.05s
- [x] 🧪 ast.json 内容確認 (180 imports, 268 defs, 1867 calls)
- [x] 🧪 fallback 動作確認 (unsupported 拡張子で empty JSON)
- [ ] 🧪 module-analyst の出力比較 (実 LLM 比較 → Phase 7 E2E)
- [ ] 🧪 トークン 30% 削減確認 (実 LLM 計測 → Phase 7 E2E)

**重要発見**: AST artifact size は最初 source の 1.5x に bloat。calls 重複排除と
imports `raw` 削除で 1.07x まで圧縮。実 LLM トークン削減効果は analyst が
artifact 全部読まず selective Read する設計に依存 (Phase 7 で実測)。

⏪ **ロールバック**: `module-analyst.md` の変更を revert すれば従来動作に戻る。

✅ **Phase 2 完了**: AST 抽出 5 言語動作、cache 連携 OK、構造的下地完成。
詳細は `docs/phase2-completion-report.md`。実 LLM トークン検証は Phase 7。

---

## Phase 3: Confidence Label 必須化

**目的**: Q3 に confidence + score を必須化し、AMBIGUOUS の自動上申で reconciliation ループを短縮。

### 3.1 schema 更新

- [ ] 📝 `.claude/schemas/analyst.schema.json` を更新:
  - `Q3_non_obvious_patterns.items` の required に `confidence` `confidence_score` 追加
  - `Q3_hyperedges` フィールドを optional で追加
  - `related_modules` フィールドを optional で追加
- [ ] 📝 `.claude/schemas/critic.schema.json` を更新:
  - `verdict` enum に `MANUAL_REVIEW` を追加
  - `weighted_overall` フィールドを追加
  - `confidence_consistency` 軸を `scores` に追加
- [x] 📝 `.claude/schemas/quality-log.schema.json` を更新

### 3.2 既存 artifact のマイグレーション

- [x] 📝 `.claude/scripts/migrate_v1_to_v2.py` を新規作成 (idempotent + dry-run)
- [x] 🧪 マイグレーション baseline-target で実行 → 3 migrated, 0 skipped

### 3.3 agent 更新

- [x] 📝 `.claude/agents/module-analyst.md` 更新 (規範文 + Q3_hyperedges + related_modules)
- [x] 📝 `.claude/agents/context-critic.md` 更新 (6 軸目 + MANUAL_REVIEW + weighted_overall)
- [x] 📝 `.claude/agents/context-fixer.md` 更新 (MANUAL_REVIEW skip + confidence fix)

### 3.4 quality log 拡張

- [ ] 📝 `.claude/skills/tribal-mapper/SKILL.md` Phase 4 追記処理 (Phase 4 で対応予定)
- [x] 📝 `.claude/scripts/check_quality_regression.py` を `weighted_overall` 優先比較に

### 3.5 Phase 3 動作確認

- [x] 📝 単体テスト: `test_migrate.py` 6/6 PASS
- [x] 🧪 baseline-target で migration 実行 → エラーなく完了
- [x] 🧪 新 schema validation: 3 analyst JSON 全 PASS
- [x] 🧪 idempotent 確認 (2 回目 dry-run で 0 migrated)
- [x] 🧪 weighted_average 数値検証 (path=2x, non_obvious=2x の効果)
- [ ] 🧪 実 LLM critic で MANUAL_REVIEW verdict 動作確認 (Phase 7 E2E)
- [ ] 🧪 critic ループ短縮 (baseline 2.3 → 1.5-2.0) 計測 (Phase 7 E2E)

⏪ **ロールバック**: schema を revert すれば旧 analyst でも問題なく動く（required 緩和方向のため）

✅ **Phase 3 完了**: confidence + MANUAL_REVIEW + weighted_overall インフラ完成、migration 動作。
詳細は `docs/phase3-completion-report.md`。実 LLM 検証は Phase 7。

---

## Phase 4: Community Detection + God Node Recommendation

**目的**: dep-graph に Leiden を適用し、god_node から primary_contexts を機械推薦。

### 4.1 cluster スクリプトと agent

- [ ] 📝 `.claude/scripts/cluster.py` を新規作成
  - graphify `cluster.py` を流用
  - graspologic 利用、なければ networkx Louvain
  - 入力: `_dep-graph.json`、出力: `_communities.json`
- [ ] 📝 `.claude/schemas/communities.schema.json` を新規作成
- [ ] 📝 `.claude/agents/community-clusterer.md` を新規作成
  - `model: haiku`
  - `tools: Bash, Read, Write`

### 4.2 god-node スクリプトと agent

- [ ] 📝 `.claude/scripts/god_nodes.py` を新規作成
  - graphify `analyze.py` の `god_nodes()` を流用
  - file-level hub / method stub の除外ロジックも採用（tribal 用に調整）
  - intent と community の親和性スコアで `recommended_primaries` を生成
- [ ] 📝 `.claude/schemas/god-nodes.schema.json` を新規作成
- [ ] 📝 `.claude/agents/god-node-detector.md` を新規作成

### 4.3 dep-graph schema 拡張

- [ ] 📝 `.claude/schemas/dep-graph.schema.json` を更新:
  - edges の required に `confidence_score` 追加
  - `kind` enum に `semantically_similar_to` `rationale_for` 追加
- [ ] 📝 `.claude/agents/dependency-indexer.md` を更新:
  - `semantically_similar_to` edge 生成ロジック (Jaccard / TF-IDF で軽量化)
  - `rationale_for` edge 生成ロジック (Q5 の category=commit_message を使う)
  - 既存 ripple 計算は変更なし

### 4.4 routing 強化

- [ ] 📝 `.claude/schemas/routing-table.schema.json` を更新:
  - `community_hint` `god_node_recommended` フィールドを追加（optional）
- [ ] 📝 `.claude/agents/routing-upgrader.md` を更新:
  - 入力に `_communities.json` `_god-nodes.json` を追加
  - 動作モードを「ゼロから生成」→「god-node 推薦の判定者」に変更
  - 推薦の採用 / 却下を理由付きで記録
- [ ] 📝 `.claude/skills/tribal-router/SKILL.md` を更新:
  - Step 2 「Community 解決」を追加
  - Step 4 「Ripple expansion」を community 内優先に変更
  - Step 6 「Wiki Fallback」を新規追加

### 4.5 wiki entry point 生成

- [ ] 📝 `.claude/skills/tribal-mapper/SKILL.md` の Phase 7 末尾に「`_index.md` を生成」を追加
- [ ] 📝 `_index.md` の生成 logic を `routing-upgrader.md` に追記:
  - community ごとの 2-5 行サマリ
  - 各 intent への jump link
  - god_node 一覧

### 4.6 mapper skill の Phase 構成更新

- [ ] 📝 `.claude/skills/tribal-mapper/SKILL.md` に Phase 5.5 (Clustering) と Phase 6.5 (God Detection) を挿入
- [ ] 📝 並列実行ルール: clustering と god_node は serial（dep-graph に依存）

### 4.7 Phase 4 動作確認

- [ ] 🧪 既存リポで `/tribal-init` を実行 → Phase 5.5 / 6.5 が完走
- [ ] 🧪 `_communities.json` が生成され、`coverage_ratio == 1.0` が成立
- [ ] 🧪 `_god-nodes.json` の `recommended_primaries` が各 intent に対して 1-3 module を提示
- [ ] 🧪 routing-upgrader が god_node 推薦を **採用 / 却下の理由付きで** 記録していること
- [ ] 🧪 `_index.md` が community 一覧として生成されていること
- [ ] 🧪 `/tribal-route 不明な intent のクエリ` → `_index.md` への fallback ナビが提示されること
- [ ] 🧪 router の選定平均枚数が 4.5 → 3.0-3.5 に減少していること（10 ケースで計測）
- [ ] 🧪 graspologic 非インストール環境で Louvain fallback 動作確認

⏪ **ロールバック**: routing-table.json を Phase 3 時点に restore、Phase 5.5/6.5 を skill から外す

✅ Phase 4 完了条件: community / god_node が生成、router 選定数 30% 減、fallback ナビが動作

---

## Phase 5: Benchmark + 新 Hook

**目的**: token reduction を毎回計測し、PreToolUse hook で opt-in 強制を defense-in-depth 化。

### 5.1 benchmark スクリプトと agent

- [ ] 📝 `.claude/scripts/benchmark.py` を新規作成
  - graphify `benchmark.py` の `_estimate_tokens` (4 chars/token) を流用
  - 入力: prompt-tester の出力 + `.claude/context/*.md`
  - 出力: `.claude/artifacts/benchmark.json`
- [ ] 📝 `.claude/schemas/benchmark.schema.json` を新規作成
- [ ] 📝 `.claude/agents/benchmark-reporter.md` を新規作成
  - `model: haiku`
  - prompt-tester 完了後に起動

### 5.2 mapper skill 更新

- [ ] 📝 `.claude/skills/tribal-mapper/SKILL.md` に Phase 8.5 (Benchmark) を追加
- [ ] 📝 `_quality-log.jsonl` に `tokens_saved_ratio` の追記処理を追加

### 5.3 PreToolUse hook 追加

- [ ] 📝 `.claude/scripts/check_router_state.py` を新規作成
  - graphify の hook パターンを参考
  - TASK_WINDOW_SEC = 30 分は既存の inject_router_directive と共通の SESSION_FILE を読む
  - opt_out 状態 / 直近 routing 内なら exit 0
  - それ以外で Read/Glob/Grep が来たら警告を `additionalContext` で注入
- [ ] 📝 `.claude/settings.json` を更新:
  ```json
  {
    "hooks": {
      "PreToolUse": [
        {
          "matcher": "Read|Glob|Grep",
          "hooks": [
            {"type": "command", "command": "python .claude/scripts/check_router_state.py"}
          ]
        }
      ]
    }
  }
  ```
  ※ 既存 PostToolUse / UserPromptSubmit はそのまま残す

### 5.4 CI gate 拡張

- [ ] 📝 `.claude/scripts/check_quality_regression.py` を更新:
  - benchmark.json を読んで `tokens_saved_ratio` を比較
  - 前回比 -20% 以上劣化で fail 条件を追加
- [ ] 📝 `.github/workflows/tribal-refresh.yml` を更新:
  - benchmark step を追加
  - PR コメントに「token reduction: <ratio>x」を投稿

### 5.5 validate command 強化

- [ ] 📝 `.claude/commands/tribal-validate.md` を更新:
  - benchmark の再実行を Step 5 として追加
  - 完了報告に `tokens_saved_ratio` を含める

### 5.6 Phase 5 動作確認

- [ ] 🧪 単体テスト: `python .claude/scripts/check_router_state.py < /dev/null` → exit 0 が返ること
- [ ] 🧪 セッション state を強制的に古い時刻に書き換え → Read を呼ぶと警告が注入されること
- [ ] 🧪 `/tribal-init` 実行 → benchmark.json が生成、`avg_ratio` が 5.0 以上
- [ ] 🧪 同一 query を router 経由 vs naive load で比較し、token 削減を目視確認
- [ ] 🧪 `/tribal-validate` 実行 → benchmark step が走る
- [ ] 🧪 routing-table を意図的に劣化させて再 init → CI gate が fail することを確認
- [ ] 🧪 PreToolUse hook が router 起動済みセッションでは **発火しない** ことを確認
- [ ] 🧪 通常のエンジニア体験を 10 分試して、PreToolUse hook がうるさすぎないか主観評価

⏪ **ロールバック**: settings.json から PreToolUse セクションを削除、benchmark agent を Phase 8.5 から外す

✅ Phase 5 完了条件: token reduction が毎回計測される、PreToolUse hook が誤発火せず警告役を果たす

---

## Phase 6: MCP Server + Multi-Platform Distribution

**目的**: tribal の routing intelligence を MCP 経由で他 platform にも公開。

### 6.1 Python パッケージ化

- [ ] 📝 `pyproject.toml` を本格定義:
  - パッケージ名 `tribal-knowledge-mapper`
  - script entry point `tribal = "tribal.__main__:main"`
  - optional dependencies: `mcp`, `leiden` (graspologic), `ast` (tree-sitter)
- [ ] 📝 `tribal/` ディレクトリを新規作成
- [ ] 📝 `tribal/__init__.py` を作成
- [ ] 📝 既存スクリプトを `tribal/` 配下にも複製:
  - `tribal/cache.py` ← `.claude/scripts/cache.py`
  - `tribal/security.py` ← graphify を移植
  - `tribal/cluster.py` `tribal/benchmark.py` ← `.claude/scripts/` から
  - `tribal/ast_extract.py` ← 同上
  - ⚠️ `.claude/scripts/` 側は **薄い shim** に書き換え (`from tribal.cache import ...`) して二重メンテを避ける

### 6.2 security モジュール

- [ ] 📝 `tribal/security.py` を実装（graphify からほぼそのまま）
  - `validate_url()` `safe_fetch()` `validate_graph_path()` `sanitize_label()`
- [ ] 📝 `.claude/scripts/validate_context_file.py` を更新:
  - path 検証で `tribal.security.validate_graph_path()` を経由
  - `.claude/context/` 外への traversal を物理的に禁止

### 6.3 MCP server

- [ ] 📝 `tribal/serve.py` を実装（graphify `serve.py` を tribal 用に改修）
- [ ] 📝 MCP tools を実装:
  - `route_query(query)` → router skill 相当のロジック
  - `get_intent(name)` → routing-table から intent 定義返却
  - `get_ripple(module)` → dep-graph の ripple_index 返却
  - `get_god_nodes(community?, top_n?)` → god-nodes.json 返却
  - `get_community(id)` → communities.json 返却
  - `get_quality_history(module)` → quality-log.jsonl 該当行返却
- [ ] 📝 `tribal serve` コマンドで MCP stdio server 起動

### 6.4 multi-platform installer

- [ ] 📝 `tribal/__main__.py` の `_PLATFORM_CONFIG` に Claude / Codex / OpenCode を定義（graphify パターン）
- [ ] 📝 `tribal install --platform claude` 実装:
  - skill / hook / settings.json 一式を配置
  - 既存挙動と同じになることを確認
- [ ] 📝 `tribal install --platform codex` 実装:
  - AGENTS.md と `.codex/hooks.json` を配置
- [ ] 📝 `tribal install --platform opencode` 実装:
  - AGENTS.md と `.opencode/plugins/tribal.js` を配置
- [ ] 📝 `tribal uninstall --platform <name>` も対称に実装
- [ ] 📝 `.tribal_version` ファイルでバージョン同期（graphify の `.graphify_version` パターン）

### 6.5 ドキュメント整備

- [ ] 📝 `README.md` を更新:
  - インストール方法 (`pip install tribal-knowledge-mapper`)
  - multi-platform install 手順
  - MCP server の接続方法 (Claude Desktop / Codex の設定例)
- [ ] 📝 `CHANGELOG.md` を新規作成、Phase 1-6 の変更を記録

### 6.6 Phase 6 動作確認

- [ ] 🧪 `pip install -e .` でローカルインストール成功
- [ ] 🧪 `tribal --version` で version 表示
- [ ] 🧪 `tribal install --platform claude` 実行 → 既存 `.claude/` と同じ構成が再現
- [ ] 🧪 `tribal serve` 起動 → MCP stdio server が応答
- [ ] 🧪 Claude Desktop の `claude_desktop_config.json` に登録 → tribal MCP tools が見えること
- [ ] 🧪 MCP tool `route_query` を呼び出し → routing 結果が返ること
- [ ] 🧪 MCP tool `get_god_nodes` で expected の module が返ること
- [ ] 🧪 path traversal テスト: `tribal serve` に `../../../etc/passwd` 相当の入力 → `validate_graph_path()` で reject されること
- [ ] 🧪 (可能なら) Codex 環境で `tribal install --platform codex` → AGENTS.md 経由で routing が走ることを確認
- [ ] 🧪 (可能なら) OpenCode 環境で同様の動作確認
- [ ] 🧪 `tribal uninstall --platform claude` → クリーンに削除されること

⏪ **ロールバック**: `tribal/` ディレクトリ削除、`.claude/scripts/` の shim を元の実装に戻す

✅ Phase 6 完了条件: pip インストール可能、MCP server 起動成功、3 platform で installer 動作

---

## Phase 7: 統合動作確認 + 文書化

**目的**: Phase 1-6 の全機能を組み合わせた end-to-end の動作確認、リリース準備。

### 7.1 大規模 E2E テスト

- [ ] 🧪 中規模 monorepo (50-200 modules) でクリーン環境から `tribal install` → `/tribal-init` を完走
- [ ] 🧪 baseline (Phase 0) と比較:
  - [ ] `/tribal-init` トークン消費が 35-45% に削減されているか
  - [ ] `/tribal-refresh` 所要時間が 25-40% に短縮されているか
  - [ ] router 選定平均枚数が 3.0-3.5 枚に収束しているか
  - [ ] critic 平均ラウンドが 1.5-2.0 に短縮されているか
  - [ ] benchmark の `avg_ratio` が 10x 以上を達成しているか
- [ ] 🧪 7 日間のドッグフード期間を設けて実運用で問題が出ないかチェック

### 7.2 Cross-Phase regression test

- [ ] 🧪 Phase 1 だけ rollback → 全体が動作するか（cache 無しでも問題ないか）
- [ ] 🧪 Phase 2 だけ rollback → analyst の fallback で完走するか
- [ ] 🧪 Phase 4 だけ rollback → router が community 無しでも動くか
- [ ] 🧪 Phase 5 だけ rollback → benchmark 無しで CI が grace fail せずに skip するか

### 7.3 文書化

- [ ] 📝 `README.md` を最終版に更新（移行計画書のセクション 9 「期待効果」を実測値で更新）
- [ ] 📝 `docs/MIGRATION_v1_to_v2.md` を新規作成（既存ユーザー向け）
- [ ] 📝 `docs/ARCHITECTURE.md` を新規作成（4 層構成図 + 各 phase 説明）
- [ ] 📝 `CHANGELOG.md` に v2.0.0 として正式リリース記載

### 7.4 リリース準備

- [ ] 📝 `pyproject.toml` の version を 2.0.0 に
- [ ] 📝 git tag `v2.0.0-rc1` を切る
- [ ] 🧪 `python -m build` で wheel 生成 → `pip install dist/*.whl` で確認
- [ ] 📝 (PyPI 公開する場合) `twine check dist/*` で検証
- [ ] 📝 GitHub Release ドラフト作成、CHANGELOG を本文に貼付

### 7.5 Phase 7 動作確認 (リリース前最終チェック)

- [ ] 🧪 完全クリーン環境 (Docker etc.) で以下を順に実行:
  ```bash
  pip install tribal-knowledge-mapper
  cd /path/to/test-repo
  tribal install --platform claude
  # Claude Code セッション開始
  /tribal-init
  /tribal-route 新しいスキーマフィールドを追加したい
  /tribal-validate
  /tribal-refresh
  ```
- [ ] 🧪 全コマンドが通り、`_quality-log.jsonl` `_benchmark.json` `_god-nodes.json` `_communities.json` `_index.md` 全て生成されていることを確認
- [ ] 🧪 `tribal serve` を別プロセスで起動 → Claude Desktop から MCP 接続成功

⏪ **ロールバック**: tag を削除、PyPI 公開前ならドラフト破棄。既存ユーザーには `pip install tribal-knowledge-mapper==1.x` で旧版継続を案内

✅ Phase 7 完了条件: E2E テスト全 PASS、ドキュメント整備完了、リリース可能状態

---

## 全 Phase 完了後の最終チェック

- [ ] 🔍 計画書 (`tribal-improvement-plan.md`) の **追加 11 / 変更 9 / 削除 0** が全て実施済み
- [ ] 🔍 計画書「11. 哲学の保全チェック」7 項目 (3 層構造 / opt-in / compass / 5 問 / 隔離 / 3-5 枚 / 全部読まない) を満たす
- [ ] 🔍 baseline からの定量改善 6 指標 (token, refresh time, 選定枚数, critic round, benchmark ratio, intent 誤分類) が計画通り
- [ ] 🔍 既存ユーザーの migration path が動作 (v1 → v2 マイグレーションスクリプト含む)

---

## Phase 別の所要時間目安

| Phase | 規模 | 想定期間 |
|---|---|---|
| Phase 0 | 準備 | 0.5 日 |
| Phase 1 | Cache | 1-2 日 |
| Phase 2 | AST | 3-5 日 |
| Phase 3 | Confidence | 2-3 日 |
| Phase 4 | Community + GodNode | 3-5 日 |
| Phase 5 | Benchmark + Hook | 2-3 日 |
| Phase 6 | MCP + Multi-platform | 5-7 日 |
| Phase 7 | E2E + Release | 3-5 日 |
| **合計** | | **約 4-5 週間** |

並列化は **Phase 5 と Phase 6 を同時進行** くらいまでは安全。Phase 1-4 は依存関係があるので serial 推奨。

---

## トラブル時の判断フロー

```
動作確認で問題発生
   ↓
問題の影響範囲は?
   ├─ 単一 Phase 内 → その Phase の ⏪ ロールバック手順を実行
   ├─ 複数 Phase に影響 → 直近の安定 Phase まで全 revert
   └─ baseline でも再現する → tribal v1 のバグ、別途 issue 化
```

各 Phase ロールバック後は **必ず baseline 動作確認 (Phase 0.4) を再実行** して、副作用が無いことを確認。
