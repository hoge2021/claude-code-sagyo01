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



### 1. このパッケージを展開
何もファイルのないディレクトリにtribal-knowledge-mapper.tar.gzを配置する。

```bash
# 確認したい複数のリポジトリをcloneする
git clone <リポジトリ>
git clone <リポジトリ>
git clone <リポジトリ>

# ローカル上でリポジトリ化
git init  #リポジトリ化が必要 ※GithubにPUSHの必要なし

#解答
tar -xzf tribal-knowledge-mapper.tar.gz

#　セットアップ
mv tribal-v2/CLAUDE.md ./CLAUDE.md   # 既存の CLAUDE.md がある場合はマージ
mv tribal-v2/.claude ./.claude
mv tribal-v2/.github ./.github
mv tribal-v2/.gitignore ./.gitignore  # 既存と差分マージ推奨
mv tribal-v2/CLAUDE.md ./CLAUDE.md                # 既存なら手動マージ推奨
mv tribal-v2/manual ./traibal-v2_manual  #マニュアル

                                            
```

### 2.4 MCP server を使う場合のみ: Python パッケージ install

MCP server や `tribal` CLI コマンドを使いたい場合のみ、以下を追加実行:

```bash
cd tribal-v2

# プロジェクト直下の Python パッケージを editable install
pip install -e .

# 成功確認
tribal --version
# → tribal 2.0.0-rc1
```

`tribal` CLI を使わず、skill / slash command / hook だけで運用する場合はこのステップは **不要**
(tarball 展開だけで Claude Code から動作)。

### 2.5 optional dependencies (用途に応じて追加)

```bash
# AST 抽出 (Python/TS/Go/Rust/Java の決定論的 deps 抽出、Phase 2a で必須)
pip install -e ".[ast]"

# Leiden clustering (Python 3.12 以下のみ、なければ Louvain fallback)
pip install -e ".[leiden]"

# MCP server
pip install -e ".[mcp]"

# schema validation (jsonschema、CI で使用)
pip install -e ".[schema]"

# すべて
pip install -e ".[all]"

# 最後にフォルダ削除
cd ../
rm -rf tribal-v2
rm tribal-knowledge-mapper.tar.gz

```
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
※時間がかなり掛かる上、何度も確認をとるので、予め
/sandboxモードの「Sandbox enabled with auto-allow」常態で設定することをお勧め。
完全に確認が不要なら、claude --dangerously-skip-permissions で実行するのも一手。

```
/tribal-init
```

完了後、以下が揃っていることを確認:

```bash
ls .claude/context/         # *.md が module 数だけ + _*.json が 5 個
cat .claude/context/_coverage.json | python -m json.tool
cat .claude/context/_quality-log.jsonl | tail -1
```

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
