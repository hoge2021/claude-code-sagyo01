# 資料 2: セットアップと使い方

**対象読者**: Tribal v2 を自分のプロジェクトで使いたい人
**読了目安**: 20-30 分 (実施含めると 1-2 時間)

---

## 第 1 部: セットアップ

## 1. 前提

### 1.1 必須要件

| 項目 | バージョン / 備考 |
|---|---|
| Python | **3.10 以上** (3.13/3.14 でも動作、ただし graspologic なし) |
| Claude Code | **2.1 以上** (PreToolUse hook サポート) |
| Git | 任意のバージョン |
| OS | Linux / macOS / Windows (WSL 推奨) |

### 1.2 推奨要件

- **Serena MCP**: 接続されていると analyst の精度が上がる (なくても動作)
- **graspologic**: Python 3.12 以下なら community 検出品質が向上 (なくても Louvain で動作)
- **git**: HEAD SHA を cache key に混ぜるため、git repo 内での利用を推奨

### 1.3 対応言語 (AST 抽出)

| 言語 | 拡張子 |
|---|---|
| Python | `.py` |
| TypeScript | `.ts` `.tsx` |
| Go | `.go` |
| Rust | `.rs` |
| Java | `.java` |

それ以外の言語は LLM ベースの従来手順 (Grep + Read) にフォールバック。

---

## 2. インストール手順

**推奨フロー**: 配布用 tarball `tribal-v2.tar.gz` をダウンロードして解凍、必要ファイルを
あなたのプロジェクト直下に移動するだけ。Python パッケージ (pip) は **MCP server を
使う時だけ** インストールすれば OK です。

### 2.1 入手

所定の場所からダウンロード
ファイルサイズは約 100 KB、96 ファイル (skill/agent/scripts/schemas/commands + Python package)。

### 2.2 解凍 + プロジェクトへの配置

あなたのプロジェクトのルート (git repo 推奨) に tarball を置いて実行:

```bash
cd /path/to/your-project

# 1. 解凍 (tribal-v2/ というディレクトリが作られる)
tar -xzf tribal-v2.tar.gz

# 2. 必要ファイルをプロジェクト直下に移動
mv tribal-v2/.claude ./.claude                    # 13 agents + 12 scripts + 10 schemas 等
mv tribal-v2/.github/workflows ./.github/workflows 2>/dev/null || \
  mkdir -p .github && mv tribal-v2/.github/workflows ./.github/
mv tribal-v2/CLAUDE.md ./CLAUDE.md                # 既存なら手動マージ推奨
mv tribal-v2/tribal ./tribal                      # Python package (MCP/CLI 用、任意)
mv tribal-v2/pyproject.toml ./pyproject.toml      # 既存なら手動マージ
[ ! -f .gitignore ] && mv tribal-v2/.gitignore ./.gitignore || \
  cat tribal-v2/.gitignore >> .gitignore          # 既存があれば追記

# 3. テンプレート跡地をクリーンアップ
rm -rf tribal-v2 tribal-v2.tar.gz

# 4. バージョン記録
echo "2.0.0-rc1" > .claude/.tribal_version
```

### 2.3 配置確認

```bash
# 必須ファイルが揃っているか
ls .claude/scripts/       # 12 Python scripts
ls .claude/agents/        # 13 .md files
ls .claude/skills/        # tribal-mapper/, tribal-router/
ls .claude/commands/      # 4 slash commands
ls .claude/schemas/       # 10 JSON schemas

# settings.json の hook 3 重化確認
python3 -c "
import json
d = json.load(open('.claude/settings.json'))
print('hooks:', list(d['hooks'].keys()))
"
# → hooks: ['PostToolUse', 'UserPromptSubmit', 'PreToolUse']
```

### 2.4 MCP server を使う場合のみ: Python パッケージ install

MCP server や `tribal` CLI コマンドを使いたい場合のみ、以下を追加実行:

```bash
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
```

### 2.6 他プラットフォームへの配置 (Codex / OpenCode 用、任意)

tarball 展開直後の構成は Claude Code 向け。Codex / OpenCode で使うには `tribal` CLI で
後処理:

```bash
# Python パッケージを install 済みなら
tribal install --platform codex --target .
# → AGENTS.md + .codex/hooks.json が追加配置

tribal install --platform opencode --target .
# → AGENTS.md + .opencode/plugins/tribal.js が追加配置
```

pip install なしで手動配置したい場合は、`.claude/` 内容を見て AGENTS.md を手作成 →
`docs/MIGRATION_v1_to_v2.md` のセクション「MCP Server (任意)」を参考に。

1 つのプロジェクトで複数 platform 同時 install 可 (Claude Code + Codex 混在チーム向け)。

### 2.7 インストール確認 (smoke test)

```bash
# 配置物側 (必要ファイルが揃っているか)
ls .claude/scripts/
# cache.py  ast_extract.py  cluster.py  god_nodes.py  benchmark.py
# check_router_state.py  check_quality_regression.py  detect_changed_modules.py
# flatten_module_path.py  inject_router_directive.py  migrate_v1_to_v2.py
# validate_context_file.py

ls .claude/agents/
# 13 個の .md ファイル

ls .claude/context/  # 初期は空 (/tribal-init で生成される)
```

---

## 第 2 部: 初回ビルド (`/tribal-init`)

## 3. /tribal-init の実行

### 3.1 Claude Code セッション起動

```bash
cd /path/to/your-project
claude  # Claude Code CLI 起動
```

### 3.2 初回ビルドコマンド

Claude Code 内で:

```
/tribal-init
```

これで **Phase 1 〜 Phase 8.5** が順次実行されます。mid-size repo (50-200 modules) で
所要時間は **20-60 分**、LLM トークン消費は平均 100-300k tokens。

### 3.3 Phase の流れ

| Phase | 名前 | 動作 |
|---|---|---|
| 1 | Discovery | repo-explorer が `_repo-map.json` 生成 |
| 2a | Structural | AST extractor が `artifacts/ast/*.json` 生成 (LLM ゼロ) |
| 2b | Semantic | analyst が Q1-Q5 JSON を生成 (8 並列) |
| 3 | Compose | writer が 25-45 行の context.md 生成 |
| 4 | Quality Gate | critic ⇄ fixer ループ (最大 3 round) |
| 5 | Indexing | dependency-indexer が dep-graph 生成 |
| 5.5 | Clustering | community-clusterer が Leiden/Louvain で分割 |
| 6 | Coverage | coverage-auditor が `_coverage.json` 生成 |
| 6.5 | God Node | god-node-detector が推薦生成 |
| 7 | Routing | routing-upgrader が routing-table + `_index.md` 生成 |
| 8 | Test | prompt-tester が router を実 invoke して regression test |
| 8.5 | Benchmark | benchmark-reporter が token 削減率を計測 |

### 3.4 完了確認

成功したら Claude Code が以下のような完了報告を出します:

```
[tribal-mapper] 完了報告
  total modules: 18
  coverage_ratio: 1.0
  average quality score: 4.35
  prompt test pass_rate: 0.92
  benchmark avg_ratio: 12.3x
  manual_review_required contexts: 2
    - context/<x>.md: analyst Q3 に AMBIGUOUS 1 件 (人手判断要)
    - ...
  Next actions:
    - 2 件の MANUAL_REVIEW 対象を確認して下さい
    - 次の refresh は 14 日後自動実行 (GitHub Actions)
```

`_coverage.json` と `_quality-log.jsonl` が生成されていることを確認:
```bash
cat .claude/context/_coverage.json | python3 -m json.tool | head -10
tail -3 .claude/context/_quality-log.jsonl
```

---

## 第 3 部: 日常の使い方

## 4. 開発タスクを投げる (自動 routing)

### 4.1 基本フロー

Tribal 導入後は、**何も意識せず自然言語でタスクを投げる** だけ:

```
新しいユーザーフィールド "role" を追加したい。validation と codegen との整合性も保ちたい。
```

すると `UserPromptSubmit` hook が router 起動指示を注入し、以下が自動で走ります:

1. `tribal-router` が intent 分類 → `schema-change`
2. routing-table から community_hint 解決 → 該当 community の god_node 特定
3. primary contexts (1-3 枚) + community 内 ripple (1-2 枚) 選定
4. ユーザーに確認:
   ```
   タスクを「schema-change」と分類しました (community: C3)。
   以下の context をロードします:
     - .claude/context/<validate>.md  (primary, god_node)
     - .claude/context/<schema-user>.md  (primary, intent ヒット)
     - .claude/context/<codegen>.md  (ripple from validate, 同 community)
   よろしいですか? (Yes / 追加 / 削除 / Skip routing)
   ```
5. Yes と返したら、その 3 枚だけをロードして実タスク実行

### 4.2 明示的に router を呼ぶ

自然言語でなく slash command で:

```
/tribal-route 認証フローで使っているトークン検証をリファクタしたい
```

### 4.3 特殊ケース: router を使わない

明示指示で router を bypass 可能 (緊急調査など):

```
ルーター不要で、全部 context を読んで包括的に調査したい
```

「ルーター不要」「全部読んで」「skip routing」のいずれかが含まれていれば 30 分間 hook が
passthrough になります。

---

## 5. コード変更後の更新 (`/tribal-refresh`)

コードを編集した後は:

```
/tribal-refresh
```

実行内容:
1. `detect_changed_modules.py` で変更 module を検出 (git diff + SHA256 cache 確認)
2. `cache_status: active` でキャッシュ済み module を自動 skip
3. 変更 module のみ Phase 2a/2b/3/4 を再実行
4. Phase 5/5.5/7 は全件再生成 (依存関係の部分更新は難しいため)
5. Phase 8.5 で benchmark 再計測

典型的な所要時間:
- **コード変更 1-3 module**: 2-5 分
- **依存関係変更 (ripple で 10+ module 巻き込み)**: 5-15 分
- **変更なし**: < 10 秒 (cache 全 hit で瞬時)

### 5.1 検出されない変更パターンの対処

以下の場合は手動で `--no-cache` で強制再実行:

```bash
# Claude Code 外で直接実行
python3 .claude/scripts/detect_changed_modules.py --no-cache
```

- `.claude/agents/*.md` (agent prompt) を変更 → 全 analyst 再実行を期待するが自動検出されない
- 設定ファイル (`.env`, `pyproject.toml` 等) を変更 → 影響範囲が module 外

---

## 6. 品質チェックのみ (`/tribal-validate`)

再生成せず既存 artifact の品質確認だけしたい時:

```
/tribal-validate
```

実行内容:
- 全 `.claude/context/*.md` を hook validator にかけて 25-45 行 / 4 heading / path 実在性確認
- critic を全 context で再実行してスコア更新
- coverage-auditor で stale / orphan / invalid 検出
- prompt-tester で router 挙動を regression test
- **Phase 8.5**: benchmark 再計測、avg_ratio < 5.0 で警告
- quality regression gate (main branch 比 -0.3 以上劣化で fail)

### 6.1 完了レポートの優先度

```
Critical:   broken paths, manual_review_required な context
High:       スコア < 4.0 の context、benchmark avg_ratio < 5.0
Medium:     prompt test failures
Low:        orphan contexts, stale 候補
```

Critical から順に対処してください。

---

## 7. MCP server として起動 (任意)

他 AI platform (Claude Desktop / Codex Desktop / Cursor 等) から tribal 知識を共有:

```bash
# stdio で MCP server 起動
tribal serve --base /abs/path/to/your-project/.claude --mcp
```

### 7.1 Claude Desktop への登録

`~/.config/claude-desktop/config.json` (macOS は `~/Library/Application Support/Claude/`):

```json
{
  "mcpServers": {
    "tribal": {
      "command": "tribal",
      "args": ["serve", "--base", "/abs/path/to/project/.claude", "--mcp"]
    }
  }
}
```

Claude Desktop を再起動すると `@tribal` で 6 tools (route_query / get_intent /
get_ripple / get_god_nodes / get_community / get_quality_history) が使えるようになります。

### 7.2 スタンドアロン呼び出し (デバッグ用)

MCP protocol を介さず CLI で試す:

```bash
python3 -m tribal.serve --base .claude --call route_query --args '{"query":"スキーマを変更したい"}'
```

出力例:
```json
{
  "intent": "schema-change",
  "community": 3,
  "primary_contexts": [".claude/context/<validate>.md", ".claude/context/<schema-user>.md"],
  "secondary_contexts": [".claude/context/<codegen>.md"],
  "god_node_recommended": [".claude/context/<validate>.md"],
  "score": 3.0
}
```

---

## 第 4 部: 継続運用

## 8. GitHub Actions による自動化

v2 installer は `.github/workflows/tribal-refresh.yml` を配置します。これが 14 日ごとに
自動実行:

1. `detect_changed_modules.py` で変更検出
2. 変更があれば `/tribal-refresh` 相当を実行
3. schema validation (jsonschema で全 JSON 検証)
4. quality regression gate (weighted_overall -0.3 劣化で fail)
5. token reduction benchmark (avg_ratio < 5.0 で warning)
6. 更新があれば PR を自動作成 (labels: `tribal-knowledge`, `automated`)

### 8.1 シークレット設定

GitHub repo の Settings → Secrets and variables → Actions:

```
ANTHROPIC_API_KEY = sk-ant-...
```

これで 14 日毎の auto-refresh PR が開く。レビュー → マージするだけ。

### 8.2 手動トリガー

GitHub Actions UI から `workflow_dispatch` で即時実行可能。`mode: init|refresh|validate` で
用途切替。

---

## 9. 日常運用のベストプラクティス

### 9.1 コミット戦略

```
# .gitignore 推奨
.claude/artifacts/analyst/*.json
.claude/artifacts/critic/*.json
.claude/artifacts/tests/*.json
.claude/artifacts/ast/*.json
.claude/cache/**/*.json
.claude/critic-workspace/
.claude/.session-state/
```

一方、**以下は commit する**:
- `.claude/context/*.md` (チームで共有する資産)
- `.claude/context/_repo-map.json` / `_dep-graph.json` / `_routing-table.json` /
  `_communities.json` / `_god-nodes.json` / `_index.md`
- `.claude/context/_coverage.json` / `_quality-log.jsonl`
- `.claude/scripts/` / `.claude/agents/` / `.claude/skills/` / `.claude/schemas/` /
  `.claude/commands/` / `.claude/settings.json`
- `CLAUDE.md`

### 9.2 チーム onboarding

1. 1 人が `/tribal-init` を実行してコミット
2. 他メンバーは `git pull` で .claude/context/ を取得 → 即座に router が使える
3. 新規参加者も同じ流れ、セットアップ 5 分

### 9.3 周期的メンテナンス

| 頻度 | 作業 |
|---|---|
| **毎日** | 自然言語タスク投入 (自動 routing で完結) |
| **コード変更後** | 必要なら `/tribal-refresh` (大抵は GitHub Actions に任せる) |
| **14 日毎** | GitHub Actions の auto-refresh PR をレビュー → マージ |
| **月 1** | `/tribal-validate` で品質チェック、manual_review リストを人手確認 |
| **四半期** | `migrate_v1_to_v2.py` 相当の v2→v2.1 migration (将来) |

### 9.4 LLM 予算監視

```bash
# 累積コスト確認 (graphify 方式で _quality-log.jsonl から抽出)
python3 -c "
import json
from pathlib import Path
lines = Path('.claude/context/_quality-log.jsonl').read_text().splitlines()
total = sum(json.loads(l).get('tokens_saved_ratio', 0) for l in lines if l.strip())
print(f'累積 token reduction ratio: {total:.1f} case-sum')
"
```

benchmark.json の `avg_ratio` トレンドを Datadog / Grafana などに投げると運用改善が
見えるようになります (将来的に metrics export も検討)。

---

## 10. トラブルシューティング

### Q1: `/tribal-init` が途中で fail する

**原因別対処**:
- LLM API rate limit → `.claude/skills/tribal-mapper/SKILL.md` の「並列実行ルール」を 8 → 4 に下げる
- 特定 module で analyst が timeout → その module path を Bash で手動確認、空ファイルや巨大ファイルがないか
- Python 依存欠落 → `pip install "tribal-knowledge-mapper[all]"` で全 optional deps を入れる

### Q2: Hook が走っていない

```bash
# 手動で hook を発火テスト
echo '{"tool_input":{"file_path":".claude/context/test.md"}}' \
  | python3 .claude/scripts/validate_context_file.py
echo "exit: $?"
```

`Traceback` が出るなら Python パスや権限を確認。
`.claude/settings.json` に 3 hook 全て登録されているか:
```bash
python3 -c "import json; d=json.load(open('.claude/settings.json')); print(list(d['hooks'].keys()))"
# → ['PostToolUse', 'UserPromptSubmit', 'PreToolUse']
```

### Q3: PreToolUse hook がうるさい

session state を opt-out に:
```bash
mkdir -p .claude/.session-state
echo '{"opted_out": true, "last_routing_ts": 0}' > .claude/.session-state/router-state.json
```

または `.claude/settings.json` から PreToolUse セクションを削除。

### Q4: benchmark avg_ratio が低い (< 5.0)

`_routing-table.json` の primary_contexts が多すぎる可能性。routing-upgrader を再実行:
```
/tribal-validate
```
または routing-table を手動で編集して primary を 1-2 枚に絞る。

### Q5: cache が効いていない

```bash
python3 .claude/scripts/detect_changed_modules.py | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'cache_status: {d[\"cache_status\"]}')
print(f'cached: {len(d[\"cached_modules\"])}, changed: {len(d[\"changed_modules\"])}')
"
```

`cache_status: unavailable` なら `cache.py` の import が失敗している。
`cache_status: disabled` なら `--no-cache` が渡っている。
`cached_modules` が 0 なら初回実行 or cache invalidate された後。

### Q6: routing-table が変な推薦をする

```bash
# god_node 推薦を確認
cat .claude/context/_god-nodes.json | python3 -m json.tool
```

偏った推薦 (常に watch が primary 等) がある場合、`_routing-table.json` の
`rejected_recommendations` に手動で却下理由を追加し、`/tribal-refresh` で再構築。

### Q7: Claude Code が古い version で PreToolUse hook 未対応

```bash
claude --version  # 2.1 以上確認
```

古い場合は `.claude/settings.json` から PreToolUse セクションを削除すれば v1 動作になる。

### Q8: 重要な Q3 が勝手に MANUAL_REVIEW 扱いになる

それは AMBIGUOUS confidence が正しく機能している証拠。
「削除されずに人間判断ループに到達した」が目的なので、`_quality-log.jsonl` で
`manual_review_required: true` のエントリを見て、人手で context を精査・修正して下さい。

---

## 11. アンインストール

```bash
tribal uninstall --platform claude --target .
# hook から tribal 登録を除去 (ファイルは保持)

pip uninstall tribal-knowledge-mapper

# 完全削除したい場合:
rm -rf .claude/ CLAUDE.md .tribal_version
```

`.claude/context/*.md` は人手で作った知識資産扱いで残置されます。
完全クリーンするなら手動 rm -rf を。

---

## 12. 次のステップ

- **技術詳細 (初心者向け丁寧解説)**: `manual/03_specification.md`
- **概要・ユースケース**: `manual/01_overview.md`