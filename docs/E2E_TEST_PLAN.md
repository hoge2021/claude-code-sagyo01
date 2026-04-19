# Tribal v2 — End-to-End Test Plan

実 LLM 実行が必要なテストの手順書。
本文書のテストは **本セッションでは再帰問題で実行不可**。別の Claude Code セッションで
実施してください。

## 前提環境

- Python 3.10+ (3.13/3.14 でも動作、ただし graspologic 不可)
- Claude Code 2.1+ (PreToolUse hook サポート)
- `pip install -e /path/to/tribal-v2` 済み or `pip install tribal-knowledge-mapper`

## テスト 1: クリーンインストール E2E

### 手順

```bash
# 1. テスト用ディレクトリを準備 (graphify ベース)
cp -r /home/hoge/51_mygit/claude-code-sagyo01/baseline-target /tmp/tribal-e2e
cd /tmp/tribal-e2e

# 2. tribal v2 をインストール
tribal install --platform claude --target .

# 3. v1 既存 artifact を migration
python3 .claude/scripts/migrate_v1_to_v2.py

# 4. Claude Code セッション起動
claude
```

### Claude Code 内で実行

```
/tribal-init
```

期待出力:
- Phase 1 (Discovery): 18 modules
- Phase 2a (AST): 18 ast.json 生成、`tree-sitter` で全件成功
- Phase 2b (Analysis): 18 module で analyst 実行、Q3 に confidence 必須
- Phase 3 (Compose): 18 context.md 生成、25-45 行
- Phase 4 (Critic loop): 平均 1.7 ラウンドで PASS、AMBIGUOUS あれば MANUAL_REVIEW
- Phase 5 (Indexing): dep-graph 生成、edges に confidence
- **Phase 5.5 (Cluster)**: Louvain で 5-8 community
- Phase 6 (Coverage): 18/18 covered
- **Phase 6.5 (God Node)**: top 5 + 8 intent 別推薦
- Phase 7 (Routing): god_node_recommended 採用 + `_index.md` 生成
- Phase 8 (Test): pass_rate >= 0.9
- **Phase 8.5 (Benchmark)**: avg_ratio 計測 + log 追記

### 計測項目

```bash
# 全 phase 完了後、以下を確認
cat .claude/context/_coverage.json | jq '{coverage_ratio, total_modules}'
cat .claude/artifacts/benchmark.json | jq '.summary'
cat .claude/context/_quality-log.jsonl | tail -5
ls .claude/artifacts/ast/  # 18 files
ls .claude/cache/  # populated
```

baseline (`docs/tribal-v2-migration-baseline.md`) と比較し、計画書 §9 の 6 指標を埋める:

| 指標 | baseline | v2 実測 | 達成 |
|---|---|---|---|
| /tribal-init LLM トークン (削減 35-45%) | TBD | TBD | ☐ |
| /tribal-refresh 時間 (短縮 25-40%) | TBD | TBD | ☐ |
| router 選定平均枚数 (3.0-3.5 枚) | 4.5 想定 | TBD | ☐ |
| critic 平均ラウンド (1.5-2.0) | 2.3 想定 | TBD | ☐ |
| benchmark avg_ratio (10x+) | 未計測 | TBD | ☐ |
| intent 誤分類率 (<5%) | 不明 | TBD | ☐ |

## テスト 2: 10 サンプルクエリで router 動作確認

各 query を `/tribal-route <query>` で実行し、選定 context 枚数と intent を記録:

| # | query | 期待 intent | 選定枚数 |
|---|---|---|---|
| 1 | 新しい言語 (Dart) の AST 抽出を追加したい | feature-add | 3-5 |
| 2 | cache hit 率が低い、調査 | ops-investigation | 3-5 |
| 3 | validate_url のホスト解決ロジックを変更 | validation-change | 3-4 |
| 4 | Leiden の閾値をリポジトリ別に変えたい | refactor | 3 |
| 5 | report の god_node セクションフォーマットを変更 | codegen-change | 3-4 |
| 6 | ingest で twitter URL の対応を追加 | feature-add | 3-5 |
| 7 | watch のデバウンス時間を環境変数化 | refactor | 3 |
| 8 | MCP serve に新 tool を追加 | feature-add | 3-5 |
| 9 | PowerShell 出力崩れの再発調査 | bug-fix | 3-4 |
| 10 | graph.html が大きい時の splitting 戦略を実装 | feature-add | 3-5 |

選定平均が 3.0-3.5 枚に収まれば合格。

## テスト 3: PreToolUse hook 体感

通常の開発作業を 10 分行い、以下を確認:
- router 起動済みなら hook が発火しない (passthrough)
- 明示的 opt-out (「ルーター不要」) で hook 抑止
- 警告が「うるさすぎる」と感じないか主観評価

## テスト 4: MCP Server 接続

Claude Desktop の `claude_desktop_config.json` に追加:
```json
{
  "mcpServers": {
    "tribal": {
      "command": "tribal",
      "args": ["serve", "--base", "/abs/path/.claude", "--mcp"]
    }
  }
}
```

Claude Desktop 再起動後、「tribal の god_nodes を 5 つ教えて」のような問いで MCP tool が
呼ばれることを確認。

## テスト 5: refresh の cache 効果

```bash
# 初回 refresh
time python3 .claude/scripts/detect_changed_modules.py

# 2 回目 (変更なし → cache 全 hit)
time python3 .claude/scripts/detect_changed_modules.py
# expected: changed_modules=[], cached_modules=18, 所要 < 1s
```

## テスト 6: Codex / OpenCode 動作確認 (任意)

Codex (OpenAI Code Assistant) または OpenCode 利用者向け。

```bash
tribal install --platform codex --target /path/to/project
# AGENTS.md に Tribal セクション追記、.codex/hooks.json 配置
# Codex セッションで開発タスクを試し、AGENTS.md 経由の routing 誘導を確認
```

```bash
tribal install --platform opencode --target /path/to/project
# .opencode/plugins/tribal.js プラグイン配置
# OpenCode セッションで bash tool 呼出時に reminder 表示確認
```

## テスト 7: バグレポート用 — 計画書 v1 バグ #1 検証

tribal v1 バグ「単独拡張子 backtick が path 誤判定」が v2 でも残っているか確認:

```bash
echo '{"tool_input":{"file_path":"/tmp/tribal-e2e/.claude/context/test.md"}}' | \
    python3 .claude/scripts/validate_context_file.py
```

`.md` を含む context で false positive validation fail が出れば、Phase 7 で対応必要 (v2 で未修正)。

## 結果記録

各テスト完了後、`docs/tribal-v2-migration-baseline.md` の「v1 LLM Baseline 値 (実機採取)」
セクションを v2 比較表に拡張して PR を作成してください。

## 完了判定

- ✅ テスト 1-3 全 PASS → v2.0.0-rc1 → v2.0.0 昇格可能
- ⚠️ テスト 1-3 のいずれか fail → 該当 phase の bug fix → re-run
- ✅ テスト 4-6 → optional (release blocker ではない)
- ✅ テスト 7 → 既知 bug (v1 由来)、v2.0.0 でなく v2.0.1 で修正計画
