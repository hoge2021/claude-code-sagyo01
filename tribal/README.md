# Tribal Knowledge Mapper for Claude Code

Meta engineering blog 「How Meta Used AI to Map Tribal Knowledge in Large-Scale Data Pipelines」 (2026/04/06) の構造を Claude Code 上に高い忠実度で再現するための完成版テンプレートです。

このパッケージは以下を提供します。

- 9 種類の subagent（repo-explorer / module-analyst / context-writer / context-critic / context-fixer / dependency-indexer / coverage-auditor / routing-upgrader / prompt-tester）
- 2 つの skill（tribal-mapper / tribal-router）
- 4 つの slash command（/tribal-init / /tribal-refresh / /tribal-route / /tribal-validate）
- 4 つの hook 連動スクリプト（Hook stdin 仕様に準拠、UserPromptSubmit で router を強制起動）
- GitHub Actions による 2 週ごとの自動リコンサイル + 品質回帰ゲート
- 全成果物の JSON Schema 定義

---

## 設計の3層（厳守）

| 層 | 役割 | ここでやってはいけないこと |
|---|---|---|
| Pre-compute | コードベース全体を先読みし、モジュール単位の compass 形式 context を生成 | 後付けの即興分析 |
| Runtime | ユーザーの自然言語タスクから関連 context を 3〜5 枚だけ動的ロード | `.claude/context/*.md` を一括 import すること |
| Maintenance | 定期的に再批評・再生成・パス検証・カバレッジ補完 | 失敗を握り潰して PR を出すこと |

「常時オン」設計は Meta 論文が引用した [arxiv 2602.11988](https://arxiv.org/abs/2602.11988) の失敗モードに合流するため、強制機構（hook）で物理的に opt-in を担保しています。

---

## ディレクトリ全体像

```
your-monorepo/
├── CLAUDE.md
├── .gitignore
├── .claude/
│   ├── settings.json
│   ├── scripts/
│   │   ├── validate_context_file.py     # PostToolUse hook 本体
│   │   ├── inject_router_directive.py   # UserPromptSubmit hook 本体
│   │   ├── detect_changed_modules.py    # refresh の差分検出
│   │   ├── check_quality_regression.py  # CI の品質ゲート
│   │   └── flatten_module_path.py       # モジュール名→ファイル名（共通ユーティリティ）
│   ├── skills/
│   │   ├── tribal-mapper/SKILL.md
│   │   └── tribal-router/SKILL.md
│   ├── agents/
│   │   ├── repo-explorer.md
│   │   ├── module-analyst.md
│   │   ├── context-writer.md
│   │   ├── context-critic.md
│   │   ├── context-fixer.md
│   │   ├── dependency-indexer.md
│   │   ├── coverage-auditor.md
│   │   ├── routing-upgrader.md
│   │   └── prompt-tester.md
│   ├── commands/
│   │   ├── tribal-init.md
│   │   ├── tribal-refresh.md
│   │   ├── tribal-route.md
│   │   └── tribal-validate.md
│   ├── schemas/
│   │   ├── analyst.schema.json
│   │   ├── critic.schema.json
│   │   ├── coverage.schema.json
│   │   ├── dep-graph.schema.json
│   │   ├── quality-log.schema.json
│   │   └── routing-table.schema.json
│   ├── critic-workspace/                # critic 専用の隔離ディレクトリ（physical isolation）
│   ├── .session-state/                  # router 起動状態の追跡（hook 用）
│   ├── artifacts/                       # gitignore 対象（最新のみ commit する運用も可）
│   │   ├── analyst/
│   │   ├── critic/
│   │   └── tests/
│   └── context/                         # 生成物（人手で編集しない）
│       ├── _repo-map.json
│       ├── _routing-table.json
│       ├── _dep-graph.json
│       ├── _coverage.json
│       └── _quality-log.jsonl
└── .github/workflows/
    └── tribal-refresh.yml
```

---

## セットアップ手順

### 0. 前提

- Claude Code 最新版がインストール済み（`claude --version` で確認）
- Python 3.10 以上
- Git
- （任意）Serena MCP がプロジェクトに接続済み。なくても動くが analyst の精度は落ちる

### 1. このパッケージをプロジェクトに展開

```bash
# プロジェクトのルートで
tar -xzf tribal-knowledge-mapper.tar.gz
mv tribal/CLAUDE.md ./CLAUDE.md   # 既存の CLAUDE.md がある場合はマージ
mv tribal/.claude ./.claude
mv tribal/.github ./.github
mv tribal/.gitignore ./.gitignore  # 既存と差分マージ推奨
rm -rf tribal
```

### 2. CLI フラグの確認（重要）

GitHub Actions と手元 CI で使う Claude Code の headless モードのフラグを **必ず手元で先に確認** してください。

```bash
claude --help | grep -E "print|headless|message|prompt"
```

`.github/workflows/tribal-refresh.yml` 内の `claude -p "..."` の部分は、上で確認したフラグに合わせて調整します。バージョンによって `--print` と `-p` の差や、stdin 経由が必須なケースがあります。

### 3. Hook の動作確認

```bash
# context ファイルがあったとして、validation hook を手動で起動できるか確認
echo '{"tool_input": {"file_path": ".claude/context/sample.md"}}' \
  | python .claude/scripts/validate_context_file.py
echo "exit: $?"
```

`exit: 0` または `exit: 1`（バリデーション失敗時）が返れば正常。`Traceback` が出るなら Python パスや権限を確認。

### 4. 初回フル構築

Claude Code を起動して以下を実行:

```
/tribal-init
```

完了後、以下が揃っていることを確認:

```bash
ls .claude/context/         # *.md が module 数だけ + _*.json が 5 個
cat .claude/context/_coverage.json | python -m json.tool
cat .claude/context/_quality-log.jsonl | tail -1
```

### 5. CI シークレット設定

GitHub リポジトリの Settings → Secrets and variables → Actions に以下を登録:

- `ANTHROPIC_API_KEY` — あなたの Anthropic API キー

---

## 普段の運用

### 開発タスクを投げる

そのまま自然言語で投げるだけです。`UserPromptSubmit` hook が router を起動するように指示を注入するので、`tribal-router` skill が必ず先に走ります。

```
新しいデータフィールドを pipeline に追加したい。validation と codegen との整合性も保ちたい。
```

期待動作:

1. router が `schema-change` と分類
2. registry / config / validation / codegen 系の context を 3〜5 枚提示
3. ユーザーに承認確認
4. 承認後、その context だけをロードして開発タスクに進む

### 差分更新（コード変更後）

```
/tribal-refresh
```

`detect_changed_modules.py` が直近差分を検出し、影響モジュールだけ analyst→writer→critic を再実行します。

### 品質確認だけ

```
/tribal-validate
```

context の生成は行わず、path validity / critic / prompt tests だけを再実行します。

### 自動更新

GitHub Actions が **2 週ごと** に走り、変更検出→再分析→品質ゲート→PR を自動で行います。PR は `tribal-knowledge` `automated` ラベル付きで届くので、レビューマージしてください。

品質スコアが main ブランチ平均から **0.3 以上劣化** していると CI が fail するため、auto-refresh による静かな品質劣化は防がれます。

---

## トラブルシューティング

### Q. Hook が走っていない気がする

`echo '{"tool_input":{"file_path":"x"}}' | python .claude/scripts/validate_context_file.py` で手動実行できるか確認。`.claude/settings.json` の matcher が現行の Claude Code 仕様と合っているか確認。

### Q. context が必ず 25 行で打ち切られて情報が落ちる

`validate_context_file.py` は **実体行（空行・コードフェンス除外）** で 25-40 を許容しています。それでも落ちる場合は writer が冗長記述しているので、context-writer.md の制約をさらに絞ってください。

### Q. critic のスコアが甘い気がする

critic は `.claude/critic-workspace/` 配下でしか作業できないように tools が制限されています。それでも甘い場合、`context-critic.md` の判定基準で「path_accuracy < 5.0 → 即 FIX」を「いずれかの軸が 3.0 未満で FIX」など強める方向で調整します。

### Q. router が呼ばれずに全 context が読まれている

`UserPromptSubmit` hook が動いていません。`.claude/scripts/inject_router_directive.py` を手動実行して JSON が出力されることを確認。`.claude/settings.json` の hook 登録を再確認。

### Q. `/tribal-refresh` が「変更なし」しか返さない

`detect_changed_modules.py` が `git log` を使うので、`fetch-depth: 0` でチェックアウトされていないと差分が取れません。CI 側の actions/checkout 設定を確認。

### Q. CI で品質ゲートが常に fail する

main ブランチに baseline がない初期状態では `check_quality_regression.py` は skip されます。それでも fail する場合は `--threshold` を一時的に `0.5` に緩めて段階的に運用に乗せてください。

---

## 再現度評価の 5 基準（self-check）

`/tribal-validate` 実行後、以下を満たせば Meta 論文の構造的同型が達成されています。

1. **構造同型**: Pre-compute / Runtime / Maintenance の3層が揃って動いている
2. **5問忠実**: `.claude/artifacts/analyst/*.json` の Q1〜Q5 が全件埋まっており、Q3 と Q5 が空でない
3. **Compass遵守**: 全 context が 25-40 実体行、全パス有効、形容詞排除
4. **Reconciliation収束**: critic→fixer ループが平均 3 ラウンド以内で全件 PASS
5. **opt-in原則**: prompt-tester で router 経由のロードが 3〜5 枚に収まる

---

## ライセンス・免責

このテンプレートは設計参考として配布するものです。本番投入前に各組織のセキュリティ要件、API キー管理、`--dangerously-skip-permissions` の利用可否を必ず確認してください。
