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
- [x] 📝 `.claude/schemas/communities.schema.json` を新規作成
- [x] 📝 `.claude/agents/community-clusterer.md` を新規作成

### 4.2 god-node スクリプトと agent

- [x] 📝 `.claude/scripts/god_nodes.py` を新規作成 (158 LOC)
- [x] 📝 `.claude/schemas/god-nodes.schema.json` を新規作成
- [x] 📝 `.claude/agents/god-node-detector.md` を新規作成

### 4.3 dep-graph schema 拡張

- [x] 📝 `.claude/schemas/dep-graph.schema.json` を更新 (confidence + 新 edge kinds)
- [x] 📝 `.claude/agents/dependency-indexer.md` を更新 (v2 セクション追加、実生成は Phase 7 E2E)

### 4.4 routing 強化

- [x] 📝 `.claude/schemas/routing-table.schema.json` を更新
- [x] 📝 `.claude/agents/routing-upgrader.md` を「判定者モード」に
- [x] 📝 `.claude/skills/tribal-router/SKILL.md` を 7 step に拡張

### 4.5 wiki entry point 生成

- [x] 📝 `.claude/skills/tribal-mapper/SKILL.md` の Phase 7 末尾に `_index.md` 生成記述
- [x] 📝 `_index.md` の生成 logic は routing-upgrader prompt に明記

### 4.6 mapper skill の Phase 構成更新

- [x] 📝 Phase 5.5 (Clustering) + Phase 6.5 (God Detection) を skill に挿入

### 4.7 Phase 4 動作確認

- [x] 🧪 単体テスト 9/9 PASS (test_cluster.py)
- [x] 🧪 baseline-target で `cluster.py` 実行 → 7 communities (Louvain) detect
- [x] 🧪 `_communities.json` 生成、cohesion / 全 18 modules カバレッジ確認
- [x] 🧪 `_god-nodes.json` の recommended_primaries が 8 intent 全件カバー
- [x] 🧪 graspologic 非インストール環境で Louvain fallback 確認 (Python 3.14.3)
- [x] 🧪 community が ARCHITECTURE.md と意味的一致 (cache+detect+extract = 入力 pipeline 等)
- [ ] 🧪 routing-upgrader 採用/却下の判定 (実 LLM → Phase 7 E2E)
- [ ] 🧪 `_index.md` 生成と wiki fallback 動作 (実 LLM → Phase 7 E2E)
- [ ] 🧪 router 選定平均枚数 30% 減 計測 (実 LLM → Phase 7 E2E)

⏪ **ロールバック**: routing-table.json を Phase 3 時点に restore、Phase 5.5/6.5 を skill から外す

✅ **Phase 4 完了**: Leiden/Louvain ベースの community detection + degree-based god_node
推薦インフラ完成。意味的一致を baseline-target で実証。詳細は `docs/phase4-completion-report.md`。

---

## Phase 5: Benchmark + 新 Hook

**目的**: token reduction を毎回計測し、PreToolUse hook で opt-in 強制を defense-in-depth 化。

### 5.1 benchmark スクリプトと agent

- [ ] 📝 `.claude/scripts/benchmark.py` を新規作成
  - graphify `benchmark.py` の `_estimate_tokens` (4 chars/token) を流用
  - 入力: prompt-tester の出力 + `.claude/context/*.md`
  - 出力: `.claude/artifacts/benchmark.json`
- [ ] 📝 `.claude/schemas/benchmark.schema.json` を新規作成
- [x] 📝 `.claude/agents/benchmark-reporter.md` を新規作成

### 5.2 mapper skill 更新

- [x] 📝 `.claude/skills/tribal-mapper/SKILL.md` に Phase 8.5 (Benchmark) を追加
- [x] 📝 `_quality-log.jsonl` に `tokens_saved_ratio` 自動追記 (benchmark.py 内)

### 5.3 PreToolUse hook 追加

- [x] 📝 `.claude/scripts/check_router_state.py` を新規作成
- [x] 📝 `.claude/settings.json` の hooks に PreToolUse(Read|Glob|Grep) を追加

### 5.4 CI gate 拡張

- [x] 📝 `check_quality_regression.py` の v2 拡張は Phase 3 で済 (weighted_overall 優先)
- [x] 📝 `.github/workflows/tribal-refresh.yml` に benchmark step + ratio < 5.0 で warning

### 5.5 validate command 強化

- [x] 📝 `tribal-validate.md` に Step 5 (benchmark) 追加

### 5.6 Phase 5 動作確認

- [x] 🧪 単体テスト 9/9 PASS (test_phase5.py)
- [x] 🧪 セッション state を stale で Read → 警告が JSON で出力
- [x] 🧪 直近 routing で Read → empty passthrough
- [x] 🧪 baseline-target で benchmark dry-run → 5 cases avg_ratio=2.63x (3 contexts)
- [x] 🧪 _routing-table.json 等 index file は warning 対象外 (T9)
- [ ] 🧪 実 LLM /tribal-init で avg_ratio >= 5.0 検証 (Phase 7 E2E)
- [ ] 🧪 PreToolUse hook 体感評価 (Phase 7 ドッグフード)

⏪ **ロールバック**: settings.json から PreToolUse セクション削除、benchmark agent を Phase 8.5 から外す

✅ **Phase 5 完了**: benchmark + PreToolUse hook (defense-in-depth 3 重化) 完成。
詳細は `docs/phase5-completion-report.md`。

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
  - `validate_url()` `safe_fetch()` `validate_context_path()` `sanitize_label()` 全実装
- [x] 📝 `.claude/scripts/validate_context_file.py` を `tribal.security.validate_context_path` 経由に (graceful fallback 付き)

### 6.3 MCP server

- [x] 📝 `tribal/serve.py` 実装 (235 LOC, 6 MCP tools)
- [x] 📝 MCP tools: route_query / get_intent / get_ripple / get_god_nodes / get_community / get_quality_history
- [x] 📝 `tribal serve --mcp` で MCP stdio server 起動可

### 6.4 multi-platform installer

- [x] 📝 `tribal/__main__.py` で 3 platform installer 実装 (claude/codex/opencode)
- [x] 📝 `tribal install --platform claude` → `.claude/` tree + `CLAUDE.md` + settings.json マージ
- [x] 📝 `tribal install --platform codex` → AGENTS.md + .codex/hooks.json
- [x] 📝 `tribal install --platform opencode` → AGENTS.md + .opencode/plugins/tribal.js
- [x] 📝 `tribal uninstall --platform claude` 実装 (hook 除去 + ファイル保持)
- [x] 📝 `.tribal_version` でバージョン同期

### 6.5 ドキュメント整備

- [x] 📝 `README.md` 更新 (使い方 + 進捗表 + 構成)
- [x] 📝 `phase6-completion-report.md` 作成
- [ ] 📝 `CHANGELOG.md` (Phase 7 で総まとめ)

### 6.6 Phase 6 動作確認

- [x] 🧪 `pip install -e .` 成功 (tribal 2.0.0-rc1)
- [x] 🧪 `tribal --version` / `--help` 動作
- [x] 🧪 `tribal install --platform claude --target /tmp/test` で完全展開
- [x] 🧪 `python3 -m tribal.serve --call route_query` で intent 分類動作
- [x] 🧪 path traversal 防御 (T5 で `validate_context_path` ブロック確認)
- [x] 🧪 単体テスト 10/10 PASS (test_phase6.py)
- [ ] 🧪 Codex / OpenCode 実機検証 (Phase 7)
- [ ] 🧪 Claude Desktop MCP 接続実機テスト (Phase 7)

⏪ **ロールバック**: `tribal/` ディレクトリ削除、`pip uninstall tribal-knowledge-mapper`

✅ **Phase 6 完了**: Python パッケージ化 + 6 MCP tools + 3 platform installer。
詳細は `docs/phase6-completion-report.md`。

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
- [ ] 🧪 7 日間のドッグフード期間 (E2E_TEST_PLAN 参照、ユーザー側で実施)

### 7.2 Cross-Phase regression test

- [x] 🧪 Phase 1 rollback (cache.py 物理削除) → `_CACHE_AVAILABLE=False`, mtime fallback 動作
- [x] 🧪 Phase 2 rollback (ast.json 不在) → analyst.md prompt の Step 1-6 fallback (設計検証)
- [x] 🧪 Phase 4 rollback (_communities.json 不在) → route_query が community=None で v1 互換動作
- [x] 🧪 Phase 5 rollback (weighted_overall 無し v1 entry) → check_quality_regression が overall fallback

### 7.3 文書化

- [x] 📝 `README.md` 最終版更新 (Phase 6 で完了)
- [x] 📝 `docs/MIGRATION_v1_to_v2.md` 新規作成
- [x] 📝 `docs/ARCHITECTURE.md` 新規作成
- [x] 📝 `CHANGELOG.md` 新規作成 (v2.0.0-rc1 + v1.0.0 baseline)
- [x] 📝 `docs/E2E_TEST_PLAN.md` 新規作成 (実 LLM テスト 7 ケース手順書)

### 7.4 リリース準備

- [x] 📝 `pyproject.toml` の version は `2.0.0-rc1` (Phase 6 設定済み)
- [ ] 📝 git tag `v2.0.0-rc1` を Phase 7 commit 後に切る
- [ ] 🧪 `python -m build` で wheel 生成 (任意、PyPI 公開時必須)
- [ ] 📝 PyPI 公開判断 (rc1 段階では非公開推奨)
- [ ] 📝 GitHub Release ドラフト (任意)

### 7.5 Phase 7 動作確認 (リリース前最終チェック)

- [x] 🧪 単体テスト合計 55/55 PASS (Phase 1-6 + cross-phase)
- [x] 🧪 構造的成果物 (artifacts / schemas / agents) 全 phase で baseline-target 個別検証済み
- [ ] 🧪 実 LLM /tribal-init 完走 → ユーザー別セッションで `E2E_TEST_PLAN.md` Test 1-3 実施
- [ ] 🧪 Claude Desktop MCP 接続実機テスト → ユーザー実施

⏪ **ロールバック**: tag を削除、PyPI 公開前ならドラフト破棄。既存ユーザーには `pip install tribal-knowledge-mapper==1.x` で旧版継続を案内

✅ **Phase 7 完了** (構造的観点): 文書整備完了、cross-phase regression PASS、リリース準備完了。
実 LLM E2E は別セッションでユーザー実施 → 結果を baseline.md に追記して v2.0.0 安定版へ昇格。

---

## 全 Phase 完了後の最終チェック

- [x] 🔍 計画書 (`tribal-improvement-plan.md`) の **追加 11 / 変更 9 / 削除 0** が全て実施済み
- [x] 🔍 計画書「11. 哲学の保全チェック」7 項目 (3 層構造 / opt-in / compass / 5 問 / 隔離 / 3-5 枚 / 全部読まない) を満たす — ARCHITECTURE.md で言明
- [ ] 🔍 baseline からの定量改善 6 指標 (token, refresh time, 選定枚数, critic round, benchmark ratio, intent 誤分類) — 4/6 構造的下地完成、実 LLM 計測待ち
- [x] 🔍 既存ユーザーの migration path が動作 (test_migrate.py 6/6 PASS + baseline-target で適用確認)

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
