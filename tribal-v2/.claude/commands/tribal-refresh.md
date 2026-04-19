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

`detect_changed_modules.py` の出力 (`changed_modules` 配列) が空の場合:

- Phase 5/7/8 もスキップ
- ユーザーに以下を報告:
  - 「変更検出なし。前回成功 SHA: <sha>」
  - **v2**: `cache_skipped_from_changes` 件数 (cache hit で再分析回避された module 数)
  - **v2**: `cache_status` (active / disabled / unavailable)

## 完了報告

- 変更検出された module 数 (`changed_modules` の length)
- 直接変更 vs ripple 経由 の内訳 (`direct_changes` / `ripple_added`)
- **v2**: cache hit で再分析回避された数 (`cache_skipped_from_changes`)
- 再生成された context 数
- スコアの変動 (baseline 比)
- 新規 manual_review_required の有無

## v2 cache の働き

`detect_changed_modules.py` は v2 で `.claude/cache/analyst/` を最初に確認します:

- module の現在 hash (source body + git HEAD SHA + cache schema version) と一致する artifact があれば **cache hit** とみなし、`changed_modules` から除外
- ripple 経由で巻き込まれた module も cache hit なら除外 (内容変化なしのため)
- `--no-cache` フラグで cache fast path を無効化可能 (デバッグ用)

cache hit module の analyst 結果は `.claude/cache/analyst/<module-flat>/<hash>.json`
から復元され、Phase 2 の LLM 呼び出しがスキップされる。

## 注意

- `last_success_sha` が `_coverage.json` にない場合（初回 init をしていない）、エラーで停止
- artifacts/ の retention: 過去 3 世代まで保持し、それ以前は削除
- **v2**: cache invalidation は automatic (file 変更 / branch 切替えで hash 変わる)。
  手動 purge は `python .claude/scripts/cache.py --clear` (未実装、必要なら追加)
