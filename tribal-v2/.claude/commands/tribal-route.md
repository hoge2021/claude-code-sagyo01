# /tribal-route

現在のユーザー要求を `tribal-router` skill で分類し、関連 context を 3〜5 枚に絞ってロードしてください。

## 引数

このコマンドの直後に続くテキストを「ユーザー要求」として router に渡します。

例:

```
/tribal-route 新しいデータフィールドを pipeline に追加したい
```

## 期待動作

1. `tribal-router` skill を起動
2. router が分類・選定・提示
3. ユーザーの承認確認待ち

## 出力フォーマット

router skill が以下を返します:

- 分類された intent
- 選定された context のリスト（3〜5 枚）
- 各 context を選んだ理由（primary / ripple from <module> / ...）
- 追加・削除・skip routing の確認

## 注意

- router が「intent 不明」と返した場合、ユーザーに intent カテゴリの選択肢を提示
- `_routing-table.json` が存在しない場合、「先に `/tribal-init` を実行してください」と返す
