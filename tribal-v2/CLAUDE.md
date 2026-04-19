# Project Memory

## Tribal Knowledge Mapper

このプロジェクトは Tribal Knowledge Mapper を導入しています。開発タスクを処理する前に、必ず以下のルールに従ってください。

### ルール

1. 開発タスクを受け取ったら、最初に `tribal-router` skill を使って関連する context を選定してください。`UserPromptSubmit` hook が指示を注入しますが、念のため明示します。

2. `.claude/context/*.md` が事前に読み込まれている前提で推論してはいけません。ルーターが選定した 3〜5 枚だけをロードしてください。

3. `.claude/context/*.md` を全部 import するのは禁止です。Meta 論文の opt-in 原則に従ってください。

4. context の生成・更新・品質検証は `.claude/skills/tribal-mapper/SKILL.md` に従ってください。

5. 以下の slash command が利用可能です:
   - `/tribal-init` — 初回フル構築
   - `/tribal-refresh` — 変更モジュールのみ差分更新
   - `/tribal-route` — クエリベースで context を動的選定
   - `/tribal-validate` — 整合性チェックのみ

### 例外

ユーザーが明示的に「ルーター不要」「全部読んで」「特定の context だけを直接使う」と指示した場合のみ、ルーター起動をスキップしてよい。それ以外では opt-in を破ってはいけません。
