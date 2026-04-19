# /tribal-refresh

`tribal-mapper` skill を **refresh モード** で実行してください。

## 要件

1. まず Bash で以下を実行し、変更モジュールを取得:

   ```bash
   python .claude/scripts/detect_changed_modules.py
   ```

   出力 JSON の `changed_modules` を再分析対象とする。

2. 該当 module のみ Phase 2 (Analysis) → Phase 3 (Compose) → Phase 4 (Quality Gate) を実行

3. Phase 5 (Indexing) と Phase 7 (Routing Build) は **全件再生成**（依存関係や intent マップは部分更新が難しいため）

4. Phase 8 (Regression Test) は変更があった intent に紐づくケースを優先実行

5. 完了時に `_coverage.json` の `last_success_sha` を更新

## 「変更なし」の場合

`detect_changed_modules.py` の出力が空の場合:

- Phase 5/7/8 もスキップ
- ユーザーに「変更検出なし。前回成功 SHA: <sha>」とだけ報告

## 完了報告

- 変更検出された module 数
- 直接変更 vs ripple 経由 の内訳
- 再生成された context 数
- スコアの変動（baseline 比）
- 新規 manual_review_required の有無

## 注意

- `last_success_sha` が `_coverage.json` にない場合（初回 init をしていない）、エラーで停止
- artifacts/ の retention: 過去 3 世代まで保持し、それ以前は削除
