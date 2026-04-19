# /tribal-validate

`tribal-mapper` skill を **validate モード** で実行してください。

## 要件

context の **再生成は行わず**、以下の検証だけを実行:

1. **Path validity チェック**
   - 全 `.claude/context/*.md` を順に PostToolUse hook の検証スクリプトに通す:

     ```bash
     for f in .claude/context/*.md; do
       echo "{\"tool_input\":{\"file_path\":\"$f\"}}" \
         | python .claude/scripts/validate_context_file.py
     done
     ```

2. **Critic 再実行**
   - 全 context について `context-critic` を再起動
   - スコアを `_quality-log.jsonl` に追記（`round` フィールドに `validation` と記録）

3. **Coverage Audit**
   - `coverage-auditor` を起動して `_coverage.json` を最新化

4. **Regression Test**
   - `prompt-tester` を起動して prompt-tests.json を最新化

5. **Tribal v2: Token Reduction Benchmark**
   - `benchmark-reporter` を起動して `_benchmark.json` を最新化:

     ```bash
     python3 .claude/scripts/benchmark.py \
         --prompt-tests .claude/artifacts/tests/prompt-tests.json \
         --context-dir .claude/context \
         --routing-table .claude/context/_routing-table.json \
         --output .claude/artifacts/benchmark.json
     ```

   - `summary.avg_ratio < 5.0` なら **要注意** (router 効果が薄い)
   - `_quality-log.jsonl` に `tokens_saved_ratio` が自動追記される

6. **Quality + Benchmark Regression Check（オプション）**
   - main ブランチがある場合:

     ```bash
     python .claude/scripts/check_quality_regression.py \
       --baseline-ref main --threshold 0.3
     ```

   - `weighted_overall` 比較が自動で benchmark token_saved_ratio も検出

## 完了報告

優先度順に列挙:

1. **Critical**: broken paths, manual_review_required な context
2. **High**: スコア < 4.0 の context、benchmark avg_ratio < 5.0
3. **Medium**: prompt test failures
4. **Low**: orphan contexts, stale 候補

各項目について「どう直すか」の提案をセットで提示。

## 注意

- 本コマンドは `last_success_sha` を更新しない（再生成していないため）
- 失敗があっても自動修復しない（ユーザーが `/tribal-refresh` を判断する）
