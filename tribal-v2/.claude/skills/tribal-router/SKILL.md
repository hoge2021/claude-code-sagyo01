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

## 必ず読み込むファイル (Tribal v2 拡張)

- `.claude/context/_routing-table.json`
- `.claude/context/_dep-graph.json`
- `.claude/context/_communities.json`     ★v2 で追加
- `.claude/context/_god-nodes.json`       ★v2 で追加 (community_hint 解決時に必要)

## 手順 (Tribal v2: 2 段階選定 + Wiki Fallback)

### Step 1: Intent 分類 (v1 同様)

`_routing-table.json` の各 intent について:

1. `keywords` のいずれかがユーザータスクにマッチするか
2. `anti_keywords` がマッチしていないか（マッチしていたら除外）
3. score = (keywords matched) - 2 × (anti_keywords matched)

最もスコアの高い intent を採用。tie の場合は両方を候補として扱う。

### Step 2 (NEW): Community 解決

採用した intent の `community_hint` フィールドを確認:
- **community_hint が指定されている**: その community の god_node を `_god-nodes.json` の
  `per_community[<id>]` から取得し、優先候補に追加
- **community_hint が null**: Step 3 へそのまま進む (v1 互換動作)

### Step 3: Primary contexts 取得

intent の `primary_contexts` (1-3 枚) を候補に入れる。Step 2 で追加した god_node 候補と
重複していれば dedup。

### Step 4: Ripple expansion (v2: community-aware)

`_dep-graph.json` の `ripple_index` を使い、primary 由来の module から波及する module の
context を追加。**ただし v2 では同 community 内 module を優先**:

1. primary の community を特定
2. ripple 候補のうち同 community を最優先 (cohesion で連動性が高い)
3. その後、別 community の ripple 候補
4. **transitive 展開は禁止** (1 段だけ)

### Step 5: 上限カット (v1 同様)

合計が 5 枚を超えたら:
1. `secondary_contexts` のうち ripple_index で参照されていないものを落とす
2. ripple 距離が最も遠いもの
3. 別 community のもの (community_hint と異なる)
4. 最後に参照された日時が古いもの

最終的に 3〜5 枚に収める。

### Step 6 (NEW): Wiki Fallback

intent score が全て 0 (キーワードヒットなし) または明らかな match 不在の場合:

1. `_routing-table.json` の `wiki_index` を読む (= `.claude/context/_index.md`)
2. ユーザーに以下を提示:
   ```
   intent を分類できませんでした。以下のうちどれが近いですか?
     1. <community-0 label> (5 modules)
     2. <community-1 label> (5 modules)
     3. <community-2 label> (3 modules)
     ...
     - skip: ナビなしで全 context を見る (推奨しない)
     - manual: ".claude/context/_index.md" を Read してナビ
   ```
3. ユーザー選択を待ってから対応 community の god_node を Step 3 に投入

### Step 7: ロードと提示

選定した context を `Read` tool でロードし、ユーザーに以下を提示:

```
タスクを「<intent>」と分類しました (community: <hint>)。
以下の context をロードします:
  - .claude/context/<file1>.md  (primary, god_node)
  - .claude/context/<file2>.md  (primary, intent ヒット)
  - .claude/context/<file3>.md  (ripple from <module>, 同 community)
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
