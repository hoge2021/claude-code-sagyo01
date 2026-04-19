# /tribal-init

`tribal-mapper` skill を **init モード** で実行してください。

## 要件

1. Phase 1 (Discovery) → Phase 2 (Analysis) → Phase 3 (Compose) → Phase 4 (Quality Gate) → Phase 5 (Indexing) → Phase 6 (Coverage Audit) → Phase 7 (Routing Build) → Phase 8 (Regression Test) を順次実行

2. 並列度は最大 8、バッチ間に 30 秒スリープを挟む

3. 全ての analyst / critic / test 中間成果物を `.claude/artifacts/` に保存

4. 3 ラウンドで PASS にならない context は `_quality-log.jsonl` に `manual_review_required: true` で記録

5. 完了時に `_coverage.json` の `last_success_sha` を `git rev-parse HEAD` で更新

## 完了報告

最後に以下を簡潔に報告:

- total modules / covered modules / coverage_ratio
- average quality score
- failed contexts (manual_review_required リスト)
- routing test pass_rate
- 次のアクション（refresh タイミング、レビュー必要箇所）

## 注意

- 既存の context があっても上書き（init は完全構築）
- Serena MCP が接続されていれば自動で使う
- API レートリミットに到達した場合はバッチを縮小して継続
