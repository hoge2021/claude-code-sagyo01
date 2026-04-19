# 資料 3: Tribal Knowledge Mapper v2 — 仕様書 (初心者向け詳細解説)

**対象読者**: 初めて触る人 / 内部動作を理解して拡張したい人 / 用語の定義を知りたい人
**読了目安**: 1-2 時間 (章ごとに区切って読むのが楽)
**前提知識**: Python が少し書ける、JSON が読める、Git の basic 操作 — この程度でOK

---

## 目次

- 第 1 章: 基本概念 (15 分)
  - 1.1 そもそも Tribal Knowledge とは
  - 1.2 「compass 形式」とは
  - 1.3 5 つの問い (Q1-Q5) とは
  - 1.4 confidence とは
  - 1.5 community detection とは
  - 1.6 god node とは
  - 1.7 ripple_index とは
  - 1.8 SHA256 cache とは
- 第 2 章: ディレクトリ構造 (10 分)
- 第 3 章: 13 個の subagent 詳細 (30 分)
- 第 4 章: スクリプトとツール (20 分)
- 第 5 章: schema 定義 (20 分)
- 第 6 章: hook メカニズム (15 分)
- 第 7 章: 実行フロー (Phase 1-8.5) (20 分)
- 第 8 章: トラブル時の読み方 (10 分)
- 第 9 章: 用語集

---

# 第 1 章: 基本概念

## 1.1 そもそも Tribal Knowledge とは

直訳すると「部族の知恵」。ソフトウェア開発では以下を指します:

> **組織やチームに属する人が経験的に知っているが、明文化されていない知識**
>
> 例: 「この関数は一見 deprecated に見えるが SDK 互換性のため削除禁止」
> 「このコード修正時には必ず別 service の config も更新」
> 「Windows だけで再現する race condition があって workaround が入っている」

こういう知恵は:
- 古参エンジニアの頭の中にある
- 稀に commit message に断片が残る
- **新人が踏み抜くまで誰も気付かない**

Tribal Knowledge Mapper は、**AI にこれらを発見・構造化・共有させる** システムです。

### 類似概念との違い

| 概念 | 性質 | 例 |
|---|---|---|
| **tribal knowledge** | 経験的、暗黙知 | 「ここを触ると 3 service 同時に壊れる」 |
| Documentation | 書き残された形式知 | README, API reference |
| Code comments | インライン形式知 | `# FIXME: X で壊れる` (書かれれば tribal→formal) |
| Tests | 実行可能な形式知 | `assert fragility_condition()` |

Tribal Mapper は 1 行目 (暗黙知) を 2-4 行目に **昇格させる** ツールと言えます。

---

## 1.2 「compass 形式」とは

Meta 論文で提唱された形式で、**百科事典 (encyclopedia) ではなく羅針盤 (compass) として機能する
ドキュメント** を指します。

### 特徴
- **25-45 行** (約 1,000-1,200 token に収まる)
- 4 つの必須見出しを持つ
- 形容詞・副詞を排除 (「robust」「comprehensive」等 NG)
- 自明な前置き禁止 (「このモジュールは〜を提供します」NG)

### 構造 (テンプレート)
```markdown
# <Module Display Name>

> <1 文の目的記述。装飾語禁止。>

## Quick Commands

```bash
<copy-paste 可能な 3-5 コマンド>
```

## Key Files

- `<path>` — <なぜ重要か、1 行>
- ... (3-5 ファイルのみ)

## Non-Obvious Patterns

- **<Pattern Name>**: <違反時に起きる事象を 1-2 行で>
- ... (最重要セクション)

## See Also

- `.claude/context/<related>.md` — <関連の理由>
```

### なぜこの形式なのか

**「全部書きたい」誘惑に負けない** ため:
- LLM は「念のため詳しく書こう」として百科事典を作りがち
- 25-45 行という物理制約で強制的に重要情報だけに絞らせる
- 超えたら PostToolUse hook で block → writer は情報を **捨てる** しかない

### 実例

`graphify/cache` module の context.md:
```markdown
# Cache

> ファイル単位 SHA256 を key にした抽出キャッシュを管理する。

## Quick Commands

```bash
python3 -c "from graphify.cache import file_hash; ..."
python3 -c "from graphify.cache import clear_cache; clear_cache()"
ls graphify-out/cache/ | wc -l
```

## Key Files

- `graphify/cache.py` — file_hash / load_cached / save_cached の本体

## Non-Obvious Patterns

- **Markdown frontmatter は hash 対象外**: `.md` の YAML frontmatter を更新しても
  cache は無効化されない。意味的変更には別 invalidation が必要
- **hash key に relative path を混入**: portability 目的。実行 root が変わると
  cache miss が突然増える
- **Windows os.replace fallback**: PermissionError に対し copy + unlink

## See Also

- `.claude/context/graphify__extract.md` — cache を主に使う呼び出し元
```

実体行数 26。tribal ルールを満たしています。

---

## 1.3 5 つの問い (Q1-Q5) とは

module を analyst が精読する際の **観点枠組み**。Meta 論文が効果的と報告した 5 問:

| # | 質問 | 例 |
|---|---|---|
| **Q1** | このモジュールは **何を configure** しているか? | 「SHA256 キャッシュを管理するストレージ層」 |
| **Q2** | **典型的な変更パターン** は? | 「cache key 算出ロジックを変更」「拡張子別戦略の追加」 |
| **Q3** | **自明でないパターン** (罠) は? ★最重要 | 「.md frontmatter は hash 対象外」「Windows で os.replace fallback」 |
| **Q4** | **他 module への依存** は? | 「(ないので空)」「extract.py に使われる」 |
| **Q5** | **コメント/commit 由来の暗黙知** は? | 「Using relative path for portability (cache.py:23)」 |

### Q3 が最重要な理由

Q1, Q2, Q4 は **コードを読めば分かる** 情報 (AST でも取れる)。
Q5 は **commit message を grep すれば** 取れる。
**Q3 だけが「経験者が初めて言語化できる」情報** であり、LLM の価値が最も出る場所。

v2 では Q3 各項目に `confidence` が必須化されました (次節)。

### Q3 が書かれた典型例

❌ **ダメな Q3** (自明すぎ):
- 「このクラスはユーザー情報を保持する」 — 読めば分かる
- 「Python で書かれている」 — 拡張子で分かる

✅ **良い Q3** (発見価値):
- 「retry が silent に error を吞むので、upstream で tracing 消失する」
- 「このファイルは deprecated に見えるが SDK v1 互換で削除禁止」
- 「JSON schema を拡張すると codegen が無警告で壊れ、生成コードが build fail で初めて気付く」

いずれも **failure mode** を示しています。これが Q3 の核。

---

## 1.4 confidence とは (graphify 由来、v2 新規)

Q3 や dep-graph の edge に付ける **確信度ラベル** です。3 段階:

| ラベル | 意味 | confidence_score 範囲 | 扱い |
|---|---|---|---|
| `EXTRACTED` | source code や commit message に **明示** されている | **1.0 固定** | 断定形で書いてよい |
| `INFERRED` | 複数ファイルから推論した **妥当な含意** | 0.6-0.9 | 「〜の可能性」トーン |
| `AMBIGUOUS` | 怪しいが **重要で見逃せない** 仮説 | 0.1-0.3 | **自動で人間判断ループへ** |

### デフォルト値禁止

graphify の規範 (v2 で踏襲):
> edge ごとに reasoning を行うこと。`confidence_score = 0.5` を機械的に使ってはならない。

つまり analyst は **毎回考えて** confidence を決める必要があります。

### AMBIGUOUS の特別扱い

AMBIGUOUS な Q3 が 1 件でも analyst JSON にあると、critic が自動で verdict を
`MANUAL_REVIEW` に格上げ。fixer は触らず、ログに `manual_review_required: true` で記録。

これは **「自信ないなら削除」を禁止** する設計:
- v1: 自信ないなら書かない → 情報ロス
- v2: 自信なくても AMBIGUOUS として記録 → 人間が最終判断

### 具体例

```json
{
  "name": "Windows os.replace race condition",
  "trap": "短時間ファイルロックで PermissionError",
  "evidence_file": "graphify/cache.py:79-89",
  "why_non_obvious": "Linux では再現しない",
  "confidence": "EXTRACTED",
  "confidence_score": 1.0
}
```

↑ コード + コメントに **明示** されているので EXTRACTED (1.0)。

```json
{
  "name": "DNS rebinding の TOCTOU 隙間",
  "trap": "validate_url 成功後の実 fetch で private IP に化ける攻撃",
  "evidence_file": "graphify/security.py:50-62",
  "why_non_obvious": "getaddrinfo の時系列に依存",
  "confidence": "AMBIGUOUS",
  "confidence_score": 0.2
}
```

↑ 攻撃成立は「理論上」の話で再現確認はしていない → AMBIGUOUS。

---

## 1.5 community detection とは (v2 新規)

dep-graph (module 間の依存関係グラフ) を **意味的なグループに自動分割** する手法。

### 使うアルゴリズム

- **Leiden** (graspologic library): より高品質、Python 3.12 以下でのみ利用可
- **Louvain** (networkx 内蔵): Leiden 不可時の fallback

両者とも **edge 密度** ベース:
- 同じ group 内: 多くの edge がある (密結合)
- 異なる group 間: edge が少ない (疎結合)

### なぜ必要か

module 数が増えると router の選択肢が爆発:
- 100 modules で intent 分類 → 10 primary 候補 → ripple で 30 modules... → 上限 5 枚に絞るのに情報ロス

community で先に絞ると:
- 100 modules → 8-10 communities → 該当 community だけで選ぶ → 精度向上

### 実例 (graphify 18 modules を Louvain で分割)

| Community | size | cohesion | members | 人が見た解釈 |
|---|---|---|---|---|
| C0 | 5 | 0.600 | analyze, cluster, hooks, report, watch | 解析・実行制御 |
| C1 | 5 | 0.400 | export, ingest, security, serve, transcribe | I/O・外部連携 |
| C2 | 3 | 0.667 | cache, detect, extract | 入力 pipeline |
| C3 | 2 | 1.000 | build, validate | graph 組立 (密結合) |

ARCHITECTURE.md に人が書いた pipeline 分類と **一致**。LLM ゼロで意味的クラスタリング成立。

### cohesion (結束度)

各 community の「内部 edge 密度」:
- `1.0` = 完全密結合 (全ペアに edge)
- `0.5` = 半分のペアに edge
- `0.0` = 全く edge なし (本来 community にならない)

高 cohesion = 「この group は本当に 1 つのテーマ」
低 cohesion = 「group 分割がやや強引、再検討の余地」

---

## 1.6 god node とは (v2 新規)

「**他の multiple module から多数参照されている hub module**」。degree (接続数) top-N で抽出。

### 使い道

routing で primary_contexts を選ぶとき:
- **god node は "動脈"** — 変更すれば広範囲に波及、変更調査の起点
- **各 community の god node** はその group の「中心的 module」= primary 候補として優秀

### filter 規則 (graphify 知見)

- **file-level hub を除外**: label が source filename そのもの → 機械的に edge が集まるだけ
- **method stub を除外**: `.method()` 形の AST 由来 node → 構造的に孤立

### 実例

graphify での top 5 god nodes:
```
graphify/watch     degree=8  (他の 8 module から参照)
graphify/analyze   degree=6
graphify/detect    degree=3
graphify/extract   degree=3
graphify/export    degree=3
```

watch が圧倒的な hub (多くの処理を orchestrate する動脈)。

### intent ごとの推薦

v2 は degree だけでなく **intent との親和性 (kind_weight)** も掛けて推薦:

| intent | kind_weight table (抜粋) |
|---|---|
| `validation-change` | `validation` kind = 1.8x, `library` = 1.0x |
| `schema-change` | `validation` = 1.5x, `config` = 1.3x |
| `ops-investigation` | `service` = 1.5x, `automation` = 1.3x |

score = `degree × kind_weight`、降順 top 3 が `recommended_primaries`。
routing-upgrader が採否を判定。

---

## 1.7 ripple_index とは

「module X を変更すると影響を受ける可能性がある module 群」を事前計算したテーブル。

### 構造
```json
{
  "graphify/analyze": [
    "graphify/report",
    "graphify/export",
    "graphify/serve",
    "graphify/watch"
  ]
}
```

= 「analyze を変更すると report, export, serve, watch が壊れる可能性あり」

### 生成ルール

dep-graph の edge を **逆引き** して、以下の kind を最大 2 段まで辿る:
- `serialization`: 互換性が壊れる → 2 段
- `schema`: 型不整合 → 2 段
- `config`: 設定参照漏れ → 2 段
- `runtime`: 実行時依存 → 2 段
- `import`, `build`: 1 段のみ (爆発を避ける)

10 module を超えたら fragility 順に絞り込み。

### なぜ 1 段 or 2 段なのか

3 段まで辿ると「何でも影響する」になって実用性がない。
「同じ community 内 + ripple 1 段」で通常十分な影響範囲をカバーできます。

### 使われる場面

1. `/tribal-refresh` の change detection (変更 module の ripple を全部再分析対象に追加)
2. `tribal-router` の ripple expansion (primary から 1 段 ripple を secondary に追加)
3. `get_ripple` MCP tool

---

## 1.8 SHA256 cache とは (v2 新規、横串 Cache Layer)

**ファイル内容が変わっていない module は LLM を呼ばない** ための仕組み。

### cache key の作り方

```
hash = SHA256(
  sorted(SHA256(file body) for file in module),  # file 内容
  git HEAD SHA,                                    # branch 識別
  cache schema version                             # 仕様変更検出
)
```

3 要素すべてが一致したら cache hit。1 つでも違うと miss。

### なぜ 3 要素?

| 要素 | 目的 |
|---|---|
| file body SHA256 | 内容変更で hash 変化 (当然) |
| git HEAD SHA | **branch 切替えで自動 invalidate** — 別 branch の cache を誤って使わない |
| schema version | `cache.py` 自体のバージョンアップで全 entry invalidate |

### `.md` ファイルの特別扱い (graphify 由来)

Markdown の **YAML frontmatter は hash 対象外**:

```markdown
---
tags: [foo, bar]    ← この部分は hash に含めない
status: reviewed
---
# 本文                ← ここから hash
```

理由: tags を付け替えただけで cache 無効化されるのは手間。
本文が変わったときだけ再処理。

### 効果

refresh 実行時:
- 初回: 18 modules 全件 LLM → 30-60 分
- 2 回目 (変更なし): 18 modules 全件 cache hit → **数秒で完了**
- 3 modules だけ変更: 3 modules + ripple module のみ LLM → 5-10 分

運用 2 回目以降は大幅短縮。

---

# 第 2 章: ディレクトリ構造

## 2.1 プロジェクト側に配置されるもの (tribal install で)

```
your-project/
├── CLAUDE.md                             ← Tribal 使用ルール (追記される)
├── .tribal_version                       ← インストール済み version 記録
└── .claude/
    ├── settings.json                     ← hook 登録 (3 重)
    ├── skills/
    │   ├── tribal-mapper/SKILL.md        ← オフライン構築の orchestrator
    │   └── tribal-router/SKILL.md        ← ランタイムの 3-5 枚選定
    ├── agents/                           ← 13 個の subagent 定義
    │   ├── repo-explorer.md
    │   ├── module-ast-extractor.md       ★v2
    │   ├── module-analyst.md
    │   ├── context-writer.md
    │   ├── context-critic.md
    │   ├── context-fixer.md
    │   ├── dependency-indexer.md
    │   ├── community-clusterer.md        ★v2
    │   ├── coverage-auditor.md
    │   ├── god-node-detector.md          ★v2
    │   ├── routing-upgrader.md
    │   ├── prompt-tester.md
    │   └── benchmark-reporter.md         ★v2
    ├── scripts/                          ← 12 個のランタイム script
    │   ├── inject_router_directive.py    (UserPromptSubmit hook)
    │   ├── validate_context_file.py      (PostToolUse hook)
    │   ├── check_router_state.py         (PreToolUse hook, ★v2)
    │   ├── detect_changed_modules.py     (refresh 用)
    │   ├── check_quality_regression.py   (CI gate)
    │   ├── flatten_module_path.py        (共通 utility)
    │   ├── cache.py                      (★v2: SHA256 cache)
    │   ├── ast_extract.py                (★v2: tree-sitter)
    │   ├── cluster.py                    (★v2: Leiden/Louvain)
    │   ├── god_nodes.py                  (★v2: degree + kind_weight)
    │   ├── benchmark.py                  (★v2: token reduction)
    │   └── migrate_v1_to_v2.py           (★v2: 既存 v1 → v2 変換)
    ├── commands/                         ← 4 個の slash command 定義
    │   ├── tribal-init.md
    │   ├── tribal-refresh.md
    │   ├── tribal-route.md
    │   └── tribal-validate.md
    ├── schemas/                          ← 10 個の JSON schema
    │   ├── analyst.schema.json
    │   ├── critic.schema.json
    │   ├── coverage.schema.json
    │   ├── dep-graph.schema.json
    │   ├── routing-table.schema.json
    │   ├── quality-log.schema.json
    │   ├── ast.schema.json               ★v2
    │   ├── communities.schema.json       ★v2
    │   ├── god-nodes.schema.json         ★v2
    │   └── benchmark.schema.json         ★v2
    ├── context/                          ← /tribal-init で生成される成果物
    │   ├── _repo-map.json                (Phase 1 出力)
    │   ├── _dep-graph.json               (Phase 5 出力)
    │   ├── _communities.json             (Phase 5.5 出力, ★v2)
    │   ├── _coverage.json                (Phase 6 出力)
    │   ├── _god-nodes.json               (Phase 6.5 出力, ★v2)
    │   ├── _routing-table.json           (Phase 7 出力)
    │   ├── _index.md                     (Phase 7 末, wiki entry ★v2)
    │   ├── _quality-log.jsonl            (履歴、追記のみ)
    │   └── <module-flat>.md              (各 module の compass ×N 枚)
    ├── artifacts/                        ← 中間成果物 (gitignore 対象)
    │   ├── analyst/<flat>.json
    │   ├── critic/<flat>.json
    │   ├── tests/prompt-tests.json
    │   ├── ast/<flat>.json               ★v2
    │   └── benchmark.json                ★v2
    ├── cache/                            ← ★v2: SHA256 cache (gitignore)
    ├── critic-workspace/                 ← critic の隔離 dir (gitignore)
    └── .session-state/                   ← hook の状態追跡 (gitignore)
```

合計ファイル数 (install 直後):
- skills: 2
- agents: 13
- scripts: 12
- commands: 4
- schemas: 10
- settings.json + CLAUDE.md
- → **43 files** 配置される

## 2.2 Python パッケージ側 (pip install で)

```
tribal/                                   (Python package, import name)
├── __init__.py                           (version)
├── __main__.py                           (CLI entry: tribal install/uninstall/serve)
├── cache.py
├── ast_extract.py
├── cluster.py
├── god_nodes.py
├── benchmark.py
├── check_router_state.py
├── security.py                           (★v2: SSRF/traversal 防御)
└── serve.py                              (★v2: MCP stdio server 本体)
```

`.claude/scripts/` にある同名ファイルとほぼ同じ内容 (現状は重複、将来 shim 化検討)。

---

# 第 3 章: 13 個の subagent 詳細

subagent = **Claude Code の Task tool が起動する「専門 AI アシスタント」**。
各 subagent は独立の context で動き、責務を限定することで精度と並列性を両立します。

## 3.1 repo-explorer (v1)

- **model**: sonnet
- **tools**: Glob, Grep, Read, Bash
- **責務**: リポジトリ全体を俯瞰し、分析対象 module 一覧を抽出
- **入力**: リポジトリのルートパス
- **出力**: `.claude/context/_repo-map.json`

### module 判定ルール (5 つのいずれかで module 候補)

1. 3 ファイル以上のソースファイルを持つ
2. 設定/生成/登録/ルーティング の責務 (config, registry, router, schema 等のキーワード)
3. 他 module から参照されている
4. ビルドマニフェストを持つ (package.json, pyproject.toml 等)
5. README または説明コメントがディレクトリ内にある

### 除外対象

- `node_modules`, `vendor`, `third_party`
- `dist`, `build`, `out`, `target`
- `.git`, `.venv`, `__pycache__`
- generated ファイルのみの dir
- `.claude/`, `.github/` 自身

## 3.2 module-ast-extractor (★v2)

- **model**: haiku (整形のみで軽量)
- **tools**: Bash, Read, Glob
- **責務**: tree-sitter で imports/calls/definitions を決定論抽出
- **入力**: module_id, module_path
- **出力**: `.claude/artifacts/ast/<module-flat>.json`

### 対応言語 5 種

Python / TypeScript (.ts, .tsx) / Go / Rust / Java

未対応言語は empty JSON を返し、後段の analyst が fallback 動作。

## 3.3 module-analyst (v1 + ★v2 slim)

- **model**: sonnet
- **tools**: Read, Glob, Grep, Bash, Serena MCP (optional)
- **責務**: 単一 module を精読し、5 問フレームワーク (Q1-Q5) で構造化
- **入力**: module_id, module_path (+ ast.json があれば Read)
- **出力**: `.claude/artifacts/analyst/<module-flat>.json`

### v2 での変更

**Step 0 新設**: `.claude/artifacts/ast/<flat>.json` を最初に Read。
- Q4 (deps) は AST の imports から集約 (Grep スキップ可能)
- Q2 (example_files) は AST の definitions から選定

→ LLM トークン 50-60% 削減、Q1/Q3/Q5 の意味的分析に集中可能。

### Q3 の規範 (graphify 由来)

- INFERRED: 0.6-0.9 の間で edge ごとに判断
- AMBIGUOUS: 0.1-0.3
- EXTRACTED: 常に 1.0
- **confidence_score = 0.5 を機械的デフォルトにしてはならない**

## 3.4 context-writer (v1)

- **model**: sonnet
- **tools**: Read, Write, Bash
- **責務**: analyst JSON を compass 形式 25-45 行の context.md に変換
- **入力**: `artifacts/analyst/<flat>.json`
- **出力**: `.claude/context/<module-flat>.md`

### ソースマッピング

- `# <Title>` ← module ID の末尾を title-case に
- `> 目的` ← analyst Q1 (1-2 文を 1 文に圧縮)
- `## Quick Commands` ← analyst Q2 から copy-paste 可能な 3-5 コマンド
- `## Key Files` ← analyst の files_read から上位 3-5 ファイル
- `## Non-Obvious Patterns` ← analyst Q3 全件 (各 1-2 行に圧縮)
- `## See Also` ← analyst Q4 から関連 module 1-3 件

### 行数オーバー時の優先順位

40 行超えそうな時に情報を **捨てる** 順:
1. Quick Commands を 5 → 3 に削る
2. Key Files の説明文を短縮
3. Non-Obvious Patterns の説明を 2 行 → 1 行
4. See Also を最重要 1-2 個に絞る
5. **Non-Obvious Patterns は最後まで残す** (Q3 は中核)

## 3.5 context-critic (v1 + ★v2 6 軸)

- **model**: opus (厳密評価のため)
- **tools**: Read, Bash, Glob
- **責務**: context.md を独立採点、MANUAL_REVIEW 自動上申
- **入力**: context.md のパス
- **出力**: `.claude/artifacts/critic/<module-flat>.json`

### 独立性ルール (最重要)

critic は生成プロセスから **物理的に隔離**:
- 作業は `.claude/critic-workspace/` 内のみ
- analyst JSON, writer の system prompt, 過去 round の fixer 出力を **見ない**
- `target.md` だけを評価

例外 (★v2): `confidence_consistency` 軸の評価時のみ analyst.json の confidence を
Read してよい (断定トーンと AMBIGUOUS の矛盾検出に必要)。

### 6 評価軸 (各 0.0-5.0)

1. **Conciseness** — 行数 25-45、actionable か、形容詞排除
2. **Path Accuracy** — 全 path が実在 (1 件 broken なら 0.0)
3. **Non-Obvious Value** — Q3 が真に非自明か、failure mode が具体的か
4. **Modification Readiness** — 新人がこれだけで安全に変更できるか
5. **Cross-Reference Integrity** — See Also が実在 + 関連性高いか
6. **Confidence Consistency (★v2)** — 断定形と AMBIGUOUS の矛盾有無

### verdict 決定フロー (v2)

```
analyst.json に AMBIGUOUS Q3 が 1 件以上?
  YES → verdict = MANUAL_REVIEW
  NO → weighted_overall < 4.0 or いずれかの軸 ≤ 2.0 or path_accuracy < 5.0?
    YES → verdict = FIX
    NO  → verdict = PASS
```

### weighted_overall

```
weights = {path_accuracy: 2.0, non_obvious_value: 2.0, others: 1.0}
weighted_overall = Σ(score[k] × weights[k]) / Σ(weights.values())
```

path と non-obvious を重視した加重平均。gating は `weighted_overall` で判定、
`overall` は単純平均で履歴保存のみ。

## 3.6 context-fixer (v1 + ★v2 MANUAL_REVIEW skip)

- **model**: sonnet
- **tools**: Read, Write, Bash
- **責務**: critic 指摘を **最小修正** で反映
- **入力**: context.md + critic.json + analyst.json
- **出力**: 修正済 context.md

### v2 での変更

- verdict が `MANUAL_REVIEW` の場合、**修正せず** log のみ:
```json
{
  "fixed_file": "...",
  "skipped": true,
  "reason": "MANUAL_REVIEW verdict — AMBIGUOUS Q3 あり、人手介入要",
  "ready_for_recheck": false
}
```
- `confidence_consistency` fix 対応:
  - analyst の AMBIGUOUS 項目が context で断定形 → warn 表現に書き換え
  - 削除された AMBIGUOUS Q3 を復活
  - INFERRED に「絶対」「必ず」→ 削る

### 不変則

- critic 指摘範囲だけを直す (指摘外は触らない)
- 新規主張は **analyst JSON に根拠がある場合のみ** 追加
- 25-45 行制約を維持
- path は全て実在

## 3.7 dependency-indexer (v1 + ★v2 enriched edges)

- **model**: sonnet
- **tools**: Read, Glob, Bash, Write, Serena MCP (optional)
- **責務**: 全 analyst JSON を集約して dep-graph 構築
- **入力**: `.claude/artifacts/analyst/*.json` 全件
- **出力**: `.claude/context/_dep-graph.json`

### v2 追加 edge 種別

1. **semantically_similar_to** (INFERRED)
   - Q1+Q3 キーワードベクトル (Jaccard / TF-IDF) で類似度 0.7 以上
   - confidence_score は類似度の 0.6-0.9 にマップ
2. **rationale_for** (EXTRACTED, 1.0)
   - Q5 の commit_message 由来 why を node 化、対象 module へ edge

### ripple_index 計算

逆引きグラフで 最大 2 段遡る (kind 別):
- serialization, schema, config, runtime: 2 段
- import, build: 1 段のみ

自己ループ除外、同 from/to の複数 kind は別 edge。

## 3.8 community-clusterer (★v2)

- **model**: haiku
- **tools**: Bash, Read, Write
- **責務**: dep-graph に Leiden/Louvain 適用、cohesion 計算
- **入力**: `_dep-graph.json`
- **出力**: `_communities.json`

### メソッド自動選択

1. graspologic (Leiden) を import 試行
2. 失敗なら networkx Louvain に fallback (Python 3.13+ で必然)

isolate ノード (degree 0) は drop せず、**独立 community として追加** (graphify v1 の
issue #19 から学んだ教訓)。

## 3.9 coverage-auditor (v1)

- **model**: sonnet
- **tools**: Read, Glob, Bash, Write
- **責務**: `_repo-map.json` と context.md の整合性検査 (検出のみ、修復しない)
- **入力**: repo-map + context.md 全件 + analyst 全件
- **出力**: `_coverage.json`

### 検出ルール

- **missing**: repo-map にあるが context.md なし
- **orphan**: context.md にあるが repo-map に対応 module なし
- **stale**: analyst artifact より新しいソースファイル / context.md が analyst より古い
- **invalid**: `validate_context_file.py` hook を通らない

### 自動修復しない理由

- module の analyst 再実行は重い → orchestrator (tribal-mapper) が並列度を制御
- orphan 削除の誤検出リスクが大
- invalid の修正は writer/critic ループの責務

## 3.10 god-node-detector (★v2)

- **model**: haiku
- **tools**: Bash, Read, Write
- **責務**: degree-based hub 抽出 + intent 推薦生成
- **入力**: dep-graph + communities + routing-table + repo-map
- **出力**: `_god-nodes.json`

### 3 種類の推薦

1. **global_top_n**: degree 全体トップ 5
2. **per_community**: 各 community 内 top 2
3. **recommended_primaries**: intent 毎に `degree × kind_weight` で top 3 推薦

routing-upgrader が判定者として採否。

## 3.11 routing-upgrader (v1 + ★v2 judge mode)

- **model**: sonnet
- **tools**: Read, Glob, Write
- **責務**: intent → context のマップを構築、v2 では **機械推薦の判定者**
- **入力**: analyst 全件 + dep-graph + communities + god-nodes
- **出力**: `_routing-table.json` + `_index.md`

### seed intent (必須 8 種、固定)

1. feature-add
2. bug-fix
3. refactor
4. schema-change
5. ops-investigation
6. validation-change
7. codegen-change
8. test-add

12 種まで追加可だが、それ以上は router の判別精度が落ちる。

### v2 での動作変化

- 旧: ゼロから推論 → ブレる
- 新: god_node 推薦を **判定者として採否**
  - 採用 → `god_node_recommended` に追加
  - 却下 → `rejected_recommendations` に `{context, reason}` 記録

### anti_keywords で誤分類防止

```json
{
  "name": "feature-add",
  "keywords": ["add", "create", "new", "追加", "新規"],
  "anti_keywords": ["fix", "bug", "修正", "バグ"]
}
```

「機能を修正したい」が feature-add に誤判定されるのを防ぐ:
```
score = (keywords matched) - 2 × (anti_keywords matched)
```

## 3.12 prompt-tester (v1)

- **model**: sonnet
- **tools**: Read, Write, Bash, Task
- **責務**: tribal-router を **実 invoke** して regression test
- **入力**: routing-table + dep-graph + context.md 全件
- **出力**: `.claude/artifacts/tests/prompt-tests.json`

### ペルソナ 3 種でテストケース生成

- `junior-engineer`: 用語が抽象的、文脈不足
- `senior-engineer`: 技術用語で影響範囲を意識
- `on-call`: 急ぎ、症状ベース

各 intent につき最低 2 ケース、合計 16-24 ケース。

### 判定基準

- 必須 context 欠落 → fail
- 6 枚以上 load → fail
- intent 誤分類 → fail
- 関連薄 context が過半数 → fail

pass_rate < 0.9 なら失敗 module を特定して Phase 2-4 に戻す (最大 2 回)。

## 3.13 benchmark-reporter (★v2)

- **model**: haiku
- **tools**: Bash, Read, Write
- **責務**: token 削減率を計測、quality-log に記録
- **入力**: prompt-tests.json + context.md 全件 + routing-table
- **出力**: `.claude/artifacts/benchmark.json`

### 計測式

```
baseline_tokens = Σ(estimate_tokens(f) for f in all .claude/context/*.md)
                  # ← router 不在の世界で全部 load した場合
routed_tokens   = Σ(estimate_tokens(f) for f in router が選定した files)

ratio = baseline_tokens / routed_tokens
```

各 case の ratio 集計で avg / median / p95 / min / max。

### estimate_tokens (graphify と同じ近似)

```python
def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)  # 4 chars/token
```

tiktoken を使わない軽量版。tribal の計測用途には十分。

---

# 第 4 章: スクリプトとツール

## 4.1 hook scripts (3 種)

Claude Code の **hook** は、特定のイベントで自動実行されるスクリプト。

### inject_router_directive.py (UserPromptSubmit)

開発タスク検出時、router 起動指示を additionalContext に注入:
```python
response = {
    "hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": "[Tribal directive] ..."
    }
}
```

### validate_context_file.py (PostToolUse)

Write/Edit で `.claude/context/*.md` が保存されたら:
- 行数 25-45 確認
- 必須 4 heading 存在確認
- 参照 path 全部 `test -f` で実在確認
- 違反があれば `{"decision": "block", "reason": "..."}` で Claude に差し戻し

### check_router_state.py (PreToolUse, ★v2)

Read/Glob/Grep が発火する前に:
- opt-out フラグ → passthrough
- 30 分 TASK_WINDOW 内に router 起動歴あり → passthrough
- それ以外で `.claude/context/*.md` 直接アクセス → 警告注入

**block しない**:
- `additionalContext` で警告するだけ
- 誘導はするが強制はしない
- 明示 opt-out (「ルーター不要」) で無効化可

## 4.2 refresh / CI scripts

### detect_changed_modules.py

variant: v2 cache-aware
```
1. `.claude/cache/analyst/` を確認 → cache hit module は cached_modules
2. git diff --name-only <last_success_sha> HEAD → 変更 file を module にマップ
3. mtime fallback (git 情報なしの場合)
4. ripple_index で 1 段展開
5. cached - changed で最終 changed_modules
```

出力:
```json
{
  "changed_modules": ["graphify/analyze", ...],
  "cached_modules": ["graphify/cache", ...],
  "cache_skipped_from_changes": [...],
  "cache_status": "active|disabled|unavailable",
  "method": "git-diff from <sha>",
  "since_sha": "<sha>"
}
```

### check_quality_regression.py

CI で呼ばれる。main branch baseline との quality 比較:
- v2 preference: `weighted_overall` > `overall` (graceful fallback)
- 平均スコア -0.3 以上劣化で fail
- per-file -0.5 以上劣化で fail
- 絶対値 < 3.5 の file が 1 件でもあれば fail

### flatten_module_path.py

`module_id` をファイル名安全な形式に:
- `"graphify/cache"` → `"graphify__cache"`
- 60 文字超えは SHA1 hash で短縮: `"long__path__aaaaaaaa"` (先頭 50 + 「__」 + hash 8)

### migrate_v1_to_v2.py (★v2)

v1 artifact を v2 schema に充当:
- analyst Q3 に `confidence=EXTRACTED, score=1.0` を既存全件に追加
- critic に `weighted_overall` 計算 + `ambiguous_q3_count=0`
- quality-log に `weighted_overall` + `cache_hit=False`

**idempotent**: 既に v2 化されたものは skip。

## 4.3 Python package scripts

詳細は第 1 章の概念説明 + 各 module の docstring 参照。

| script | 関数 |
|---|---|
| `cache.py` | module_hash, load_cached_artifact, save_cached_artifact, is_cached, cached_modules, clear_cache |
| `ast_extract.py` | extract_module, extract_file (LangSpec dispatch) |
| `cluster.py` | cluster, cohesion_score, build_communities_json |
| `god_nodes.py` | detect_god_nodes, compute_degree |
| `benchmark.py` | run_benchmark, naive_baseline_tokens, routed_tokens |
| `security.py` | validate_url, safe_fetch, validate_context_path, sanitize_label |
| `serve.py` | route_query, get_intent, get_ripple, get_god_nodes, get_community, get_quality_history |

---

# 第 5 章: schema 定義 (要点)

## 5.1 analyst.schema.json (v2 拡張)

```jsonc
{
  "module": "string",
  "Q1_what_it_configures": "1-2 文",
  "Q2_modification_patterns": [...],
  "Q3_non_obvious_patterns": [{
    "name": "string",
    "trap": "string",  // 症状ベース
    "evidence_file": "file:line",
    "why_non_obvious": "string",
    "confidence": "EXTRACTED|INFERRED|AMBIGUOUS",  // ★v2 required
    "confidence_score": 0.0,                        // ★v2 required
    "related_modules": ["optional"]
  }],
  "Q3_hyperedges": [{                              // ★v2 new optional
    "id": "snake_case",
    "modules": ["min 3 modules"],
    "trap": "共通 failure mode",
    "confidence": "...",
    "confidence_score": 0.8
  }],
  "Q3_search_log": {...},  // Q3_non_obvious_patterns の代替 (どちらか一方必須)
  "Q4_cross_module_deps": [...],
  "Q5_tribal_knowledge_from_comments": [...]
}
```

`Q3_non_obvious_patterns` or `Q3_search_log` のいずれかが必須 (oneOf 制約)。

## 5.2 critic.schema.json (v2 拡張)

```jsonc
{
  "file": "path",
  "round": 1-3,
  "scores": {
    "conciseness": 0-5,
    "path_accuracy": 0-5,
    "non_obvious_value": 0-5,
    "modification_readiness": 0-5,
    "cross_ref_integrity": 0-5,
    "confidence_consistency": 0-5  // ★v2 new
  },
  "overall": 0-5,                  // 単純平均
  "weighted_overall": 0-5,         // ★v2 加重平均
  "verdict": "PASS|FIX|MANUAL_REVIEW",  // ★v2: MANUAL_REVIEW 追加
  "manual_review_reason": "...",        // MANUAL_REVIEW 時のみ
  "ambiguous_q3_count": 0,              // ★v2
  "fixes_required": [...],
  "broken_paths": []
}
```

## 5.3 dep-graph.schema.json (v2 拡張)

```jsonc
{
  "nodes": [{"id": "module", "repo": "...", "lang": "...", "context_file": "..."}],
  "edges": [{
    "from": "module",
    "to": "module",
    "kind": "import|config|runtime|serialization|build|schema|semantically_similar_to|rationale_for",
    // ★v2 で semantically_similar_to と rationale_for 追加
    "fragility": "壊れる条件",
    "evidence": "file:line",
    "confidence": "EXTRACTED|INFERRED|AMBIGUOUS",  // ★v2
    "confidence_score": 1.0                          // ★v2
  }],
  "ripple_index": {"module": ["impacted", ...]},
  "stats": {...}
}
```

## 5.4 routing-table.schema.json (v2 拡張)

```jsonc
{
  "intents": [{
    "name": "feature-add",
    "keywords": ["add", "追加"],
    "anti_keywords": ["fix", "バグ"],
    "primary_contexts": ["1-3 枚"],
    "secondary_contexts": ["最大 4 枚"],
    "max_contexts": 3-5,
    "community_hint": 3,              // ★v2: community ID
    "god_node_recommended": [...],    // ★v2: routing-upgrader 採用したもの
    "rejected_recommendations": [     // ★v2: 却下したもの + 理由
      {"context": "...", "reason": "..."}
    ]
  }],
  "fallback": {
    "primary_contexts": ["1+"],
    "max_contexts": 1-5
  },
  "wiki_index": ".claude/context/_index.md"  // ★v2: fallback ナビ entry
}
```

## 5.5 communities.schema.json (★v2)

```jsonc
{
  "method": "leiden|louvain|no-edges|empty",
  "communities": {
    "0": {
      "members": ["module-a", "module-b"],
      "cohesion": 0.67,
      "size": 2,
      "label": null  // routing-upgrader が後で命名
    }
  },
  "node_to_community": {"module-a": 0, ...},
  "stats": {"count": 7, "avg_size": 2.57, ...}
}
```

## 5.6 god-nodes.schema.json (★v2)

```jsonc
{
  "global_top_n": [{"module": "x", "degree": 8, "community": 0, "context_file": "..."}],
  "per_community": {"0": [{"module": "x", "degree": 8, ...}]},
  "recommended_primaries": {
    "feature-add": [".claude/context/x.md", ...]
  },
  "stats": {...}
}
```

## 5.7 benchmark.schema.json (★v2)

```jsonc
{
  "router_version_hash": "sha1-12-chars",
  "per_case": [{
    "case_id": "...", "intent": "...", "query": "...",
    "routed_files": [...],
    "baseline_tokens": 848,
    "routed_tokens": 322,
    "ratio": 2.63,
    "source": "prompt-tester|dry-run-sample"
  }],
  "summary": {
    "total_cases": 5,
    "avg_ratio": 2.63,
    "median_ratio": 2.63,
    "p95_ratio": 3.1,
    ...
  }
}
```

## 5.8 quality-log.schema.json (v2 拡張)

1 行 1 JSON (JSONL 形式) の append-only log:
```jsonc
{
  "timestamp": "2026-04-19T10:00:00Z",
  "module": "graphify/cache",
  "file": ".claude/context/graphify__cache.md",
  "round": 1,  // or "validation" or "ci-check"
  "scores": {...},
  "overall": 4.2,
  "weighted_overall": 4.357,          // ★v2
  "verdict": "PASS|FIX|MANUAL_REVIEW",
  "manual_review_required": false,
  "tokens_saved_ratio": 12.3,         // ★v2
  "confidence_summary": {             // ★v2
    "extracted": 2, "inferred": 1, "ambiguous": 0
  },
  "ast_extraction_method": "ast_v2_tree_sitter",  // ★v2
  "cache_hit": false,                 // ★v2
  "git_sha": "abc123"
}
```

---

# 第 6 章: hook メカニズム (opt-in 強制の仕組み)

## 6.1 なぜ hook が必要か

LLM の自然な挙動:
> 「関連ありそうな file を念のため全部読んでおこう」

これは丁寧に見えて **害**:
- context window を食い尽くす
- 何が重要か分からなくなる
- 言語モデルの注意分散 (Meta 論文の失敗モード)

Tribal の哲学:
> 「**3-5 枚だけ** 選んで読む。ルーターに選ばせる」

これを **自己規律** で守るのは無理 → **hook で物理強制**。

## 6.2 3 層の hook 防御 (v2)

```
┌─────────────────────────────────────────────────────────┐
│  Level 1: UserPromptSubmit hook (v1)                    │
│   タスク受領 → router 起動指示を注入                     │
│   (「これから tribal-router を呼んでください」)         │
└─────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────┐
│  Level 2: PostToolUse hook (Write|Edit, v1)             │
│   context.md の保存時 → validator で 25-45 行・path 検証 │
│   (違反で block = Claude に差し戻し)                     │
└─────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────┐
│  Level 3: PreToolUse hook (Read|Glob|Grep, ★v2)         │
│   subagent 等で context を直接 Read しようとしたら警告   │
│   (router 未起動の場合のみ)                              │
└─────────────────────────────────────────────────────────┘
```

各 level が独立して opt-in 原則を守らせる。

### Level 1 の処理フロー

```python
# inject_router_directive.py 擬似コード
prompt = stdin から受け取る
if "ルーター不要" in prompt or "全部読んで" in prompt:
    opt_out = True, passthrough
if prompt.startswith("/"):  # slash command は自己処理
    passthrough
if 開発キーワード (add, fix, refactor, 追加, 修正) in prompt:
    additionalContext = "[Tribal directive] まず tribal-router を呼んで..."
    session_state に last_routing_ts = now
```

### Level 2 の処理フロー

```python
# validate_context_file.py 擬似コード
target = tool_input.file_path
if not target.is_in(".claude/context/") or target.name.startswith("_"):
    silent pass  # 他ファイルは関係ない
lines = target.read_lines()
errors = []
if not 25 <= len(lines) <= 45:
    errors.append("too sparse/verbose")
for h in REQUIRED_HEADINGS:  # Quick Commands, Key Files, Non-Obvious Patterns, See Also
    if h not in target.text:
        errors.append(f"missing heading: {h}")
for path in extract_paths(target.text):
    if not (repo_root / path).exists():
        errors.append(f"referenced path does not exist: {path}")
if errors:
    print json.dumps({"decision": "block", "reason": errors})
    exit 1
```

### Level 3 の処理フロー (★v2)

```python
# check_router_state.py 擬似コード
tool_name = stdin の tool_name
tool_input = stdin の tool_input
if tool_name not in ["Read", "Glob", "Grep"]:
    passthrough
if not is_context_access(tool_name, tool_input):
    passthrough  # .claude/context/ 以外は関係ない
if session_state.opted_out or now - session_state.last_routing_ts < 30min:
    passthrough  # 直近で router 起動済み、問題なし
# stale state + context access → warning 注入
print json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext": "[Tribal warning] router 未起動のまま Read を試行。..."
    }
})
```

## 6.3 session state の役割

```
.claude/.session-state/router-state.json
{
  "last_routing_ts": 1713500000,
  "opted_out": false
}
```

Level 1 の inject で `last_routing_ts = now` に更新され、Level 3 の check はこの値を見る。
30 分以内なら「active task window」として passthrough。

これにより、1 タスクで router を 1 回呼べば、その後の subagent 経由 Read も
うるさい警告なしで動く設計。

---

# 第 7 章: 実行フロー (Phase 1-8.5)

## 7.1 /tribal-init (初回フル構築)

tribal-mapper skill が以下を順次実行:

```
Phase 1  Discovery            repo-explorer
         ↓
         _repo-map.json (18 modules 等)

Phase 2a Structural           module-ast-extractor × N 並列 (LLM ゼロ)
         ↓
         artifacts/ast/*.json (18 files)

Phase 2b Semantic             module-analyst × N 並列 (8 並列上限)
         ↓ (Step 0 で ast.json 読み込み)
         artifacts/analyst/*.json (18 files)

Phase 3  Compose              context-writer × N 並列
         ↓
         context/<flat>.md (18 files)

Phase 4  Quality Gate         context-critic → context-fixer ループ (最大 3 round)
         ↓ (AMBIGUOUS Q3 があれば MANUAL_REVIEW)
         artifacts/critic/*.json + _quality-log.jsonl 追記

Phase 5  Indexing              dependency-indexer
         ↓
         _dep-graph.json (confidence + new edges)

Phase 5.5 Clustering           community-clusterer (LLM ゼロ)  ★v2
         ↓
         _communities.json

Phase 6  Coverage Audit        coverage-auditor
         ↓ (missing > 0 なら Phase 2 に戻る, 最大 3 回)
         _coverage.json

Phase 6.5 God Detection        god-node-detector (LLM ゼロ)  ★v2
         ↓
         _god-nodes.json

Phase 7  Routing Build         routing-upgrader (judge mode)  ★v2
         ↓
         _routing-table.json + _index.md

Phase 8  Regression Test       prompt-tester (router 実 invoke)
         ↓ (pass_rate < 0.9 なら Phase 2-4 に戻る, 最大 2 回)
         artifacts/tests/prompt-tests.json

Phase 8.5 Benchmark            benchmark-reporter (LLM ゼロ)  ★v2
         ↓
         artifacts/benchmark.json + _quality-log.jsonl 追記

完了処理:
  1. git rev-parse HEAD を _coverage.json.last_success_sha に保存
  2. Desired State の全項目を確認
  3. ユーザーに report
```

## 7.2 /tribal-refresh (差分更新)

```
1. detect_changed_modules.py で changed_modules + cache_skipped を取得
2. changed_modules が空 → Phase 5/7/8 もスキップ、「変更なし」報告
3. changed_modules に対して:
   - Phase 2a (AST 再抽出)
   - Phase 2b (analyst 再実行)
   - Phase 3 (writer 再実行)
   - Phase 4 (critic ⇄ fixer)
4. Phase 5 (dep-graph) は全件再生成 (依存関係は部分更新が難しい)
5. Phase 5.5 (community) も全件
6. Phase 7 (routing) も全件
7. Phase 8 (prompt-tester) は変更があった intent のみ優先
8. Phase 8.5 (benchmark) 再計測
```

cache hit で 80-90% の module は LLM 呼び出しゼロ → 所要時間大幅短縮。

## 7.3 /tribal-validate (再生成なし品質確認)

```
1. 全 context.md を hook validator に通す → invalid の列挙
2. 全 context を critic 再実行 (隔離 workspace で)
3. coverage-auditor で stale/orphan/invalid 検出
4. prompt-tester で router regression test
5. benchmark 再計測
6. (main branch があれば) check_quality_regression で gate
7. Critical/High/Medium/Low 優先度で報告
```

last_success_sha は更新しない (再生成していないため)。

## 7.4 /tribal-route <query> (手動 routing)

tribal-router skill を明示起動:
```
Step 1  Intent 分類                   (keywords - 2 × anti_keywords)
Step 2  Community 解決 (★v2)          (intent.community_hint → per_community god_node)
Step 3  Primary contexts 取得           (1-3 枚)
Step 4  Ripple expansion (community-aware, ★v2)  (同 community 優先)
Step 5  上限カット                      (3-5 枚に収める)
Step 6  Wiki Fallback (★v2)            (intent 不明時は _index.md)
Step 7  ロード + ユーザー確認
```

---

# 第 8 章: トラブル時の読み方

「何かおかしい」と感じたときに確認すべき順番:

## 8.1 まず確認: _coverage.json

```bash
cat .claude/context/_coverage.json | python3 -m json.tool
```

- `coverage_ratio` が 1.0 未満? → missing/invalid がある
- `missing_modules` 配列 → module 名を見て原因推測
- `invalid_contexts` → hook validation 失敗、validator を手動実行して error 確認

## 8.2 品質問題: _quality-log.jsonl の最新

```bash
tail -30 .claude/context/_quality-log.jsonl | python3 -c "
import sys, json
for line in sys.stdin:
    r = json.loads(line)
    print(f'{r.get(\"module\",\"?\"):30} {r.get(\"verdict\",\"?\"):15} w={r.get(\"weighted_overall\",\"?\")}')"
```

- `MANUAL_REVIEW` の列挙 → 人手判断案件
- `FIX` で weighted_overall が低い → analyst の質に問題あり
- `tokens_saved_ratio` が低い → routing-table の primary が多すぎるかも

## 8.3 routing 問題: _routing-table.json

```bash
cat .claude/context/_routing-table.json | python3 -m json.tool | less
```

- intent の keywords に expected なキーワードがあるか
- anti_keywords で誤除外していないか
- primary_contexts が 1-3 枚か (多すぎると benchmark 劣化)
- `rejected_recommendations` に却下理由が記録されているか

## 8.4 hook 動作確認

```bash
# Level 1 (UserPromptSubmit) - stdin 与えて JSON 出力を見る
echo '{"prompt":"新機能を追加したい"}' | python3 .claude/scripts/inject_router_directive.py

# Level 2 (PostToolUse)
echo '{"tool_input":{"file_path":".claude/context/test.md"}}' | \
  python3 .claude/scripts/validate_context_file.py
echo "exit: $?"

# Level 3 (PreToolUse)
echo '{"tool_name":"Read","tool_input":{"file_path":".claude/context/x.md"}}' | \
  python3 .claude/scripts/check_router_state.py
```

## 8.5 cache 動作確認

```bash
python3 -c "
import sys
sys.path.insert(0, '.claude/scripts')
from cache import module_hash, is_cached, cached_modules
print('cached analyst:', len(cached_modules('analyst')))
print('sample hash:', module_hash('your/module/id', '/path/to/module', repo_root='.'))
"
```

## 8.6 MCP server 動作確認

```bash
# Standalone 呼び出し (MCP 不要)
python3 -m tribal.serve --base .claude --call route_query \
  --args '{"query":"test query"}'

# MCP stdio 起動 (debug)
python3 -m tribal.serve --base .claude --mcp &
# → stdout/stderr を見て JSON-RPC handshake を確認
```

---

# 第 9 章: 用語集

| 用語 | 意味 |
|---|---|
| **agent (subagent)** | Claude Code の Task tool が起動する専門 AI アシスタント |
| **AMBIGUOUS** | confidence の 3 段階のうち最低、「怪しいが記録すべき」。自動で MANUAL_REVIEW に |
| **anti_keywords** | intent 分類で「該当しない」語 — 誤分類防止 (graphify 由来) |
| **artifact** | 中間成果物。gitignore 対象 (再生成可能) |
| **AST** | Abstract Syntax Tree — 言語の構造を木で表現 (tree-sitter で生成) |
| **benchmark_ratio** | baseline_tokens / routed_tokens — 1 超で削減、5+ で有意、10-30x で秀逸 |
| **cache hit/miss** | SHA256 hash が一致 (hit) / 違う (miss) |
| **cohesion** | community 内部の edge 密度 (0.0-1.0、1.0 = 完全密結合) |
| **compass** | 羅針盤形式 — 25-45 行の短い context.md、百科事典ではない |
| **community** | dep-graph を意味的に分割した module group |
| **confidence** | Q3 や edge の確信度 3 段階 (EXTRACTED / INFERRED / AMBIGUOUS) |
| **confidence_score** | 0.0-1.0 の数値、EXTRACTED=1.0, INFERRED=0.6-0.9, AMBIGUOUS=0.1-0.3 |
| **critic** | context.md を採点する subagent、物理隔離で独立評価 |
| **dep-graph** | module 間依存関係の有向グラフ (edges に kind/confidence) |
| **defense-in-depth** | 多層防御 — 1 つ破られても他で守る設計 (v2 hook 3 重化) |
| **EXTRACTED** | confidence 最高、source code / commit に明示。常に 1.0 |
| **fixer** | critic 指摘を最小修正する subagent、MANUAL_REVIEW は触らない (v2) |
| **god node** | degree top hub module、routing primary 推薦の核 |
| **graphify** | v2 の編み込み元となる知識グラフ構築 skill |
| **haiku** | Claude の小型モデル、haiku < sonnet < opus (軽量 agent に使用) |
| **hook** | Claude Code の自動実行スクリプト (UserPromptSubmit, PostToolUse, PreToolUse) |
| **hyperedge** | 3+ module を繋ぐ関係 (pairwise edge では表現不能) |
| **INFERRED** | confidence 中、妥当な推論。0.6-0.9 |
| **intent** | router が自然言語タスクを分類する 8 カテゴリ (feature-add 等) |
| **isolate** | 他の node と edge を持たない孤立 node (community_detection で独立扱い) |
| **Leiden** | community detection アルゴリズム、高品質だが Python 3.13+ で不可 |
| **Louvain** | community detection アルゴリズム、networkx 内蔵 fallback |
| **MANUAL_REVIEW** | critic の新 verdict (v2)、人手判断に格上げ |
| **MCP** | Model Context Protocol — AI tool/server 間の通信 protocol |
| **module** | repo-explorer が識別する分析対象単位 (通常はディレクトリ or 単一ファイル) |
| **opt-in** | 「必要な分だけ読む」原則 — Meta 論文の核心 |
| **opus** | Claude の最上位モデル、critic に使用 (高精度評価用) |
| **per_community** | god_nodes.json で各 community の top module を保持する field |
| **primary_contexts** | routing-table で intent の中核 context 1-3 枚 |
| **Q1-Q5** | module を分析する 5 問 (what configures / modification pattern / non-obvious / deps / tribal knowledge from comments) |
| **ripple_index** | 変更時の影響範囲 (逆引き 1-2 段) |
| **router** | tribal-router skill、自然言語を intent に分類して 3-5 枚選定 |
| **routing-table** | intent → primary/secondary contexts のマップ |
| **schema_version** | cache key に混ぜるバージョン識別子、仕様変更で cache 全 invalidate |
| **secondary_contexts** | intent の補助 context 最大 4 枚 (ripple 経由など) |
| **see-also** | context.md の関連 module 参照セクション (最大 1-3 件) |
| **session-state** | hook 間で共有される短期状態 (router 起動履歴など) |
| **sonnet** | Claude の中位モデル、多くの subagent で使用 |
| **stale** | 古い — source > analyst mtime など |
| **TASK_WINDOW_SEC** | hook の session window、既定 30 分 |
| **tree-sitter** | 高速 AST パーサ、v2 で 5 言語対応 |
| **tribal knowledge** | 組織の暗黙知、本プロジェクトの核心テーマ |
| **verdict** | critic の判定 (PASS / FIX / MANUAL_REVIEW) |
| **weighted_overall** | 軸ごとに重み付けした critic スコア (path_accuracy/non_obvious=2x) |

---

## 次のステップ

- **概要とユースケース**: `manual/01_overview.md`
- **セットアップと使い方**: `manual/02_setup_and_usage.md`
- **アーキテクチャ図**: `docs/ARCHITECTURE.md`
- **設計の背景**: `docs/tribal-improvement-plan.md`
- **v1 からの移行**: `docs/MIGRATION_v1_to_v2.md`
- **E2E テスト手順**: `docs/E2E_TEST_PLAN.md`
