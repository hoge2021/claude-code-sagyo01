# Migration Guide: tribal v1 → v2

既存の tribal v1 (Meta blog 再現テンプレート) ユーザー向け移行手順。

**所要時間**: 30 分 (artifact migration 含む)
**破壊性**: 低 (idempotent migration、v1 schema は superset 互換)

## 前提

- tribal v1 で `/tribal-init` を 1 回以上完走済み
- `.claude/` ディレクトリと `_quality-log.jsonl` 等の artifact が存在
- Python 3.10+

## ステップ 1: v2 パッケージインストール

```bash
pip install tribal-knowledge-mapper
```

## ステップ 2: v2 を上書きインストール (既存設定マージ)

```bash
cd /path/to/your-project
tribal install --platform claude --target .
```

これにより:
- `.claude/agents/` `.claude/scripts/` `.claude/schemas/` `.claude/skills/` `.claude/commands/` が **上書き** (v2 版)
- `.claude/settings.json` は **マージ** (既存 hook を保持しつつ PreToolUse を追加)
- `CLAUDE.md` に「## Tribal Knowledge Mapper v2」セクションを追記 (重複検出付き)
- `.claude/.tribal_version` に v2 バージョン記録

## ステップ 3: 既存 artifact の v2 schema 化

```bash
# Dry-run で影響範囲確認
python3 -m tribal.scripts.migrate_v1_to_v2 --dry-run

# 本適用
python3 -m tribal.scripts.migrate_v1_to_v2
# または:
python3 .claude/scripts/migrate_v1_to_v2.py
```

実施される変換:
- `analyst.json` の Q3 全件に `confidence: EXTRACTED, score: 1.0` を充当
- `critic.json` に `weighted_overall` 計算 + `ambiguous_q3_count: 0` 初期化
- `_quality-log.jsonl` に `weighted_overall` + `cache_hit: false` 充当

idempotent: 既に v2 化されたものは skip。

## ステップ 4: v2 機能の有効化

### Cache Layer (即有効)

`/tribal-refresh` を実行すると cache fast path が自動で有効化:
```bash
python3 .claude/scripts/detect_changed_modules.py
# 出力に cached_modules / cache_status: active が含まれる
```

### AST 第1パス (init or refresh で構築)

```bash
# tree-sitter インストール
pip install 'tribal-knowledge-mapper[ast]'

# Claude Code セッションで /tribal-refresh を実行 → Phase 2a が走り .claude/artifacts/ast/ を生成
```

### Community Detection + God Node (Phase 5.5/6.5)

```bash
# Louvain で十分なら追加 install 不要 (Python 3.10-3.12 で graspologic も可)
pip install 'tribal-knowledge-mapper[leiden]'

# /tribal-refresh または /tribal-init で Phase 5.5 / 6.5 が自動実行
# .claude/context/_communities.json と _god-nodes.json が生成される
```

### MCP Server (任意)

```bash
pip install 'tribal-knowledge-mapper[mcp]'
tribal serve --base .claude --mcp
```

Claude Desktop の `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "tribal": {
      "command": "tribal",
      "args": ["serve", "--base", "/abs/path/to/project/.claude", "--mcp"]
    }
  }
}
```

## ステップ 5: 動作確認

```bash
# 単純な smoke test
tribal --version  # tribal 2.0.0-rc1
python3 -m tribal.serve --base .claude --call route_query --args '{"query":"test"}'
```

Claude Code セッションで:
```
/tribal-validate
```

完了レポートに以下があれば成功:
- `cache_status: active` (Phase 1)
- `ast_extraction_method: ast_v2_tree_sitter` (Phase 2)
- `weighted_overall` フィールド (Phase 3)
- `_communities.json` / `_god-nodes.json` (Phase 4)
- `tokens_saved_ratio` (Phase 5)

## トラブルシューティング

### Q. `tree-sitter` インストールできない

→ `pip install 'tribal-knowledge-mapper[ast]'` を試す。失敗時は v2 でも AST 抽出を skip
(analyst が従来動作にフォールバック、トークン削減効果は得られないが互換性 OK)。

### Q. graspologic が Python 3.13+ で入らない

→ 想定通り。Tribal v2 は Louvain (networkx 内蔵) 自動 fallback。コミュニティ品質は若干落ちるが
動作問題なし。

### Q. PreToolUse hook がうるさい

→ `.session-state/router-state.json` で opt-out 可:
```json
{"opted_out": true, "last_routing_ts": 0}
```
または settings.json から PreToolUse セクション削除。

### Q. v1 の context.md が validation で fail (See Also 参照先未作成)

→ tribal v1 の既知制約。`/tribal-init` で全 module を一括再構築すると解消。
v2 の wiki fallback (`_index.md`) も参照可能に。

### Q. migration script でエラー

→ `--dry-run` で問題箇所を特定。基本的に v1 artifact は触らず追加フィールド充当のみなので、
schema 違反のある v1 artifact がある場合のみ手動修正必要。

## ロールバック

v2 から v1 に戻す:

```bash
# 1. PreToolUse hook を settings.json から削除
# 2. .claude/agents/{module-ast-extractor,community-clusterer,god-node-detector,benchmark-reporter}.md を削除
# 3. tribal package を uninstall
pip uninstall tribal-knowledge-mapper
# 4. v1 のテンプレートを再展開 (tar から)
```

v2 で追加された artifact (`_communities.json`, `_god-nodes.json`, `_index.md`,
`artifacts/ast/`, `artifacts/benchmark.json`, `.claude/cache/`) は削除して問題なし。

## 期待される効果 (mid-size monorepo, 50-200 modules 想定)

| 指標 | v1 baseline | v2 期待 |
|---|---|---|
| `/tribal-init` LLM トークン消費 | 100% | 35-45% (AST + cache) |
| `/tribal-refresh` 所要時間 | 100% | 25-40% (cache hit fast path) |
| router 選定平均 context 数 | 4.5 枚 | 3.0-3.5 枚 (community 制約) |
| critic 平均ラウンド | 2.3 | 1.7 (AMBIGUOUS 自動上申) |
| token reduction (router vs naive) | 未計測 | 10-30x (規模依存) |
| routing intent 誤分類率 | 不明 | < 5% (god_node 裏取り) |

実測は Phase 7 E2E でユーザー側にて。
