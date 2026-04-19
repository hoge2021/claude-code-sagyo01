---
name: tribal-mapper
description: |
  コードベース全体から tribal knowledge を pre-compute し、
  context・依存グラフ・ルーティング表を再構築する。
  「初回構築したい」「tribal-init」「tribal-refresh」「tribal-validate」
  「context を再生成したい」「品質ゲートを再実行したい」などの場面で使う。
---

# Tribal Knowledge Mapper

## Desired State

以下を全て満たしたときのみ完了:

- カバレッジ 100%（`_coverage.json` の coverage_ratio == 1.0）
- 全 context の平均 quality score >= 4.0
- 全 file path が実在（broken_paths == 0）
- router の候補選定が常に 3〜5 枚に収まる
- regression prompt tests が pass_rate >= 0.9

これを満たさない限り、ジョブは failure を返してください。

## 生成物（厳密）

| パス | 種別 | スキーマ |
|---|---|---|
| `.claude/context/<module-flat>.md` | compass 形式 markdown | （context-writer.md 参照） |
| `.claude/context/_repo-map.json` | リポマップ | （repo-explorer.md 参照） |
| `.claude/context/_dep-graph.json` | 依存グラフ | `.claude/schemas/dep-graph.schema.json` |
| `.claude/context/_routing-table.json` | ルーティング表 | `.claude/schemas/routing-table.schema.json` |
| `.claude/context/_coverage.json` | カバレッジ状態 | `.claude/schemas/coverage.schema.json` |
| `.claude/context/_quality-log.jsonl` | 品質履歴（追記） | `.claude/schemas/quality-log.schema.json` |
| `.claude/artifacts/analyst/<module-flat>.json` | 5問分析結果 | `.claude/schemas/analyst.schema.json` |
| `.claude/artifacts/critic/<module-flat>.json` | 採点結果 | `.claude/schemas/critic.schema.json` |
| `.claude/artifacts/tests/prompt-tests.json` | 回帰テスト結果 | （prompt-tester.md 参照） |

## 実行モード

- `init` — 全フェーズ（Phase 1〜8）を順次実行
- `refresh` — `detect_changed_modules.py` の出力に該当する module のみ再分析、Phase 5/7/8 は全件再生成
- `validate` — Phase 4（critic 再実行）と Phase 8（regression）のみ

## 並列実行ルール（N7）

- subagent を Task tool で並列起動する際、**バッチサイズは 8 を上限**とする
- 1 バッチ完了 → 30 秒スリープ → 次バッチ起動
- 例外: critic と writer は独立性が高いので 10 まで許容

## フロー

### Phase 1: Discovery

1. `repo-explorer` を各リポジトリに対して起動
2. 出力を `.claude/context/_repo-map.json` に保存
3. `node_modules` `vendor` `dist` `build` `target` 等は除外

### Phase 2: Analysis

1. `_repo-map.json` の modules を 8 個ずつのバッチに分割
2. 各 module に `module-analyst` を Task で起動（5問 JSON を生成）
3. 出力先: `.claude/artifacts/analyst/<module-flat>.json`
4. `module-flat` は `.claude/scripts/flatten_module_path.py` に従う
5. **refresh モードの場合**: `detect_changed_modules.py` を Bash で実行し、`changed_modules` リストに含まれる module のみ対象

### Phase 3: Compose

1. 各 analyst JSON について `context-writer` を Task で起動
2. 出力: `.claude/context/<module-flat>.md`
3. PostToolUse hook が自動で line count / 見出し / path を検証する
4. hook が block を返した場合、writer に同じ analyst JSON を渡して再試行（最大 2 回）

### Phase 4: Quality Gate（最大 3 ラウンド）

各 context について:

1. `context-critic` を起動 → スコア取得
2. verdict が `PASS` なら次へ
3. verdict が `FIX` なら `context-fixer` に critic 結果と analyst JSON を渡して修正
4. fixer 後に再度 critic
5. 3 ラウンドで PASS にならなければ `_quality-log.jsonl` に下記を追記:
   ```json
   {"timestamp": "ISO8601", "module": "<id>", "file": "<context path>", "round": 3, "scores": {...}, "overall": <float>, "verdict": "FIX", "manual_review_required": true, "reason": "did not converge"}
   ```
6. 全ラウンドのスコアを `_quality-log.jsonl` に追記する（履歴保持）

### Phase 5: Indexing

1. `dependency-indexer` を起動
2. 全 analyst JSON を集約し `.claude/context/_dep-graph.json` を生成
3. `ripple_index` を必ず計算する（router の選定に必須）

### Phase 6: Coverage Audit

1. `coverage-auditor` を起動
2. `_repo-map.json` と `.claude/context/*.md` を突合
3. 出力: `.claude/context/_coverage.json`
4. missing_modules が 0 件でなければ Phase 2 に戻る（最大 3 回反復）

### Phase 7: Routing Build

1. `routing-upgrader` を起動
2. seed intent カテゴリ（feature-add, bug-fix, refactor, schema-change, ops-investigation, validation-change, codegen-change, test-add）から始める
3. 出力: `.claude/context/_routing-table.json`

### Phase 8: Regression Test

1. `prompt-tester` を起動
2. 各クエリに対して `tribal-router` skill を **実際に invoke**（_routing-table.json を眺めるだけは禁止）
3. 出力: `.claude/artifacts/tests/prompt-tests.json`
4. pass_rate < 0.9 なら失敗 module を特定し Phase 2-4 に戻す（最大 2 回）

### 完了処理

1. `git rev-parse HEAD` で現在の SHA を取得し、`_coverage.json` の `last_success_sha` に保存
2. Desired State の全項目を最終確認
3. ユーザーに以下を報告:
   - total modules / coverage_ratio / average score
   - manual_review_required な context のリスト
   - prompt test pass_rate
   - 次のアクション提案

## ハードルール

- `.claude/context/*.md` を全部ロードして問題を解決しようとしてはならない
- 根拠のない主張は context に書かない
- path accuracy が 5.0 未満の context は即不合格
- context は encyclopedia ではなく compass である
- 中間成果物（artifacts/）は保持する。長時間ジョブの再開を可能にする
- artifacts/ は gitignore 対象だが、CI 実行終了時に最新だけ commit する運用は許容
- critic の作業は `.claude/critic-workspace/` 内に隔離される（context-critic.md 参照）
