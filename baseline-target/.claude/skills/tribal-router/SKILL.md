---
name: tribal-router
description: |
  自然言語のタスク記述から、関連する context を 3〜5 枚だけ動的に選定してロードする。
  開発タスクを受け取ったら最初に必ず使う。「新しい機能を追加したい」「バグを直したい」
  「スキーマを変更したい」「リファクタしたい」などの全ての開発タスクで起動する。
---

# Tribal Router

## 起動条件

`UserPromptSubmit` hook が指示を注入した場合、または以下のいずれかに該当する場合:

- ユーザーが新規開発タスクを記述している
- `/tribal-route` slash command が呼ばれた
- 何らかの context をロードしたいが、どれを読むべきか不明

## 入力

ユーザーの自然言語タスク。

## 必ず読み込むファイル

- `.claude/context/_routing-table.json`
- `.claude/context/_dep-graph.json`

これら 2 ファイル以外を最初から読み込んではいけません。選定後にロードします。

## 手順

### Step 1: Intent 分類

`_routing-table.json` の各 intent について:

1. `keywords` のいずれかがユーザータスクにマッチするか
2. `anti_keywords` がマッチしていないか（マッチしていたら除外）

最もスコアの高い intent を採用。tie の場合は両方を候補として扱う。

### Step 2: Primary contexts 取得

採用した intent の `primary_contexts` を候補に入れる（1〜3 枚）。

### Step 3: Ripple expansion

`_dep-graph.json` の `ripple_index` を使い、primary に挙がった module から波及する module の context を `secondary_contexts` の中で重複しているもののみ追加。

**ripple の transitive 展開は禁止**。1 段だけ。see-also の連鎖追跡もしない。

### Step 4: 上限カット

合計が 5 枚を超えたら、以下の優先度で落とす:

1. `secondary_contexts` のうち ripple_index で参照されていないもの
2. ripple 距離が最も遠いもの
3. 最後に参照された日時が古いもの

最終的に 3〜5 枚に収める。

### Step 5: ロードと提示

選定した context を `Read` tool でロードし、ユーザーに以下を提示:

```
タスクを「<intent>」と分類しました。
以下の context をロードします:
  - .claude/context/<file1>.md  (primary: <理由>)
  - .claude/context/<file2>.md  (primary: <理由>)
  - .claude/context/<file3>.md  (ripple from <module>: <理由>)
よろしいですか? (Yes / 追加 / 削除 / Skip routing)
```

ユーザーの応答を待ってから先に進む。

## 不変則

- **5 枚を超えたら設計ミス**。選定戦略を見直すか、ユーザーに絞り込みを依頼。
- 不明な場合は 3 枚までに抑えてユーザー確認を取る。
- 「全部読む」は禁止。`.claude/context/*.md` を Glob でまとめてロードする行為は明確に禁止。
- see-also の連鎖で無限拡張しない（1 段で止める）。
- 該当 intent が見つからない場合は `_routing-table.json` の `fallback` ルールに従う（max 3 枚）。
- Slash command（`/` で始まる）に対しては起動しない。

## 失敗時の挙動

- `_routing-table.json` が存在しない → ユーザーに「先に `/tribal-init` を実行してください」と伝えて停止
- intent が分類不能 → ユーザーに「以下の intent から選んでください」と提示
- ロードしたいファイルが存在しない → `_coverage.json` を見て stale 判定し、ユーザーに `/tribal-refresh` を提案
