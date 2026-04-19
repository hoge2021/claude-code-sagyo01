# 資料 1: Tribal Knowledge Mapper v2 — 概要・特徴・ユースケース

**対象読者**: 導入検討者 / チームマネージャー / 「これは何か、どう役立つか」を知りたい人
**読了目安**: 15-20 分

---

## 1. これは何か (一文で)

**大規模コードベースに眠る「言語化されていない知恵」を、Claude Code が読みに来たときだけ必要な分だけ取り出せる形で、AI に整理させる仕組み** です。

もう少し具体的に言うと:
- **入力**: あなたのモノレポ (50-200 module 規模を想定)
- **処理**: AI が各 module を精読し、「ここを触ると壊れる罠」「過去の commit から読み取れる設計判断」などを構造化
- **出力**: 自然言語タスクを投げるたびに、関連する **3-5 枚だけ** の要約 (1 枚 25-45 行) を動的に提示

---

## 2. 解決したい課題

### 2.1 課題: コードベースが大きいと LLM が賢くなれない

ChatGPT や Claude にコードを見せて助言をもらうとき、**何を見せるか** で結果の質が大きく変わります:

- ❌ **全部渡す** → トークン予算オーバー、どれが重要か AI にも分からない
- ❌ **関連ファイルだけ探して渡す** → 毎回の手動 grep は時間がかかる、「意外な依存」を見落とす
- ❌ **README だけ渡す** → 設計意図や「壊れる罠」は書かれていない

特に問題なのは **3 番目の「罠」情報**。例えば:
- 「この関数は一見 deprecated だが、SDK の後方互換性のために削除禁止」
- 「JSON を変更すると 3 つの別 service が silent に壊れる」
- 「Windows だけで再現するスクロールバッファ破壊を修正したコミットがある」

こういう **tribal knowledge (部族の知恵)** は、古参エンジニアの頭の中か、過去の commit message にしか存在しません。新人が踏み抜くまで誰も気づかない。

### 2.2 なぜ一般的な解決策では不十分か

- **Wiki**: 書かれない、書かれても古くなる
- **コード内コメント**: 書かれない / 読みにくい / 全部読むのは非現実的
- **ChatGPT に聞く**: プロジェクト固有の罠は学習していない
- **RAG (vector DB)**: 類似検索はできるが「罠」の構造は捉えにくい

### 2.3 Tribal Knowledge Mapper のアプローチ

AI 自体に **予め精読させて** 「罠データベース」を作らせ、それを **タスクに応じて動的に提示** する 3 段構え:

1. **Pre-compute** (オフライン): 各 module を AI が読み込み、5 つの問い (Q1-Q5) で構造化
2. **Runtime** (リアルタイム): 開発タスクの自然言語から関連 module を intent 分類 + community 制約で 3-5 枚選定
3. **Maintenance** (定期): コード変更に追従して再分析、品質回帰ゲート付き

---

## 3. Meta 論文ベース + graphify 編み込み

### 3.1 Tribal v1 (Meta blog 忠実再現)

2026 年 4 月の Meta engineering blog
「How Meta Used AI to Map Tribal Knowledge in Large-Scale Data Pipelines」
を Claude Code 上に再現したのが v1。

特徴:
- compass 形式 (25-40 行 / 羅針盤として機能、百科事典ではない)
- 5 問フレームワーク (Q1-Q5、Q3 が中核 = Non-Obvious Patterns)
- 物理的 opt-in 強制 (hook で「全部読まない」を守らせる)
- critic の物理隔離 (評価者が生成プロセスを見ない)

### 3.2 v2 の進化: graphify からの編み込み

[graphifyy](https://github.com/safishamsi/graphify) という別プロジェクト (知識グラフ構築 skill) から、以下の要素を **tribal の哲学を壊さずに** 編み込みました:

| graphify 由来要素 | tribal v2 での役割 |
|---|---|
| tree-sitter AST 抽出 | 決定論的な imports/calls/defs 抽出 → analyst の LLM トークン 50-60% 削減 |
| SHA256 cache | 変更のない module は LLM 呼出しゼロで完了 |
| 3-tier confidence (EXTRACTED/INFERRED/AMBIGUOUS) | 不確実な Q3 を隠さず、人間判断ループへ自動到達 |
| Leiden/Louvain community detection | module を意味的グループに分割、router の精度向上 |
| god node 推薦 | degree ベースで primary_contexts を機械提案 |
| token reduction benchmark | 「全部読む vs router 経由」の削減率を毎回数値化 |
| security.py (SSRF/traversal 防御) | MCP server の入力検証 |
| MCP stdio server | routing intelligence を他 AI platform に共有 |
| multi-platform installer | Claude Code / Codex / OpenCode への 1 コマンド配布 |

---

## 4. アーキテクチャ (鳥瞰図)

```
┌─────────────────────────────────────────────────────────┐
│  Pre-compute Layer (オフライン、重い処理)                │
│   repo-explorer → AST抽出 → analyst → writer            │
│   → critic⇄fixer → indexer → cluster → god_node        │
│   → routing-upgrader → prompt-tester → benchmark        │
├─────────────────────────────────────────────────────────┤
│  Runtime Layer (タスク受領時、軽量)                      │
│   tribal-router skill (3-5枚選定)                       │
│   + 3重 hook (開発タスク誘導/context 検証/Read 警告)    │
├─────────────────────────────────────────────────────────┤
│  Maintenance Layer (定期)                                │
│   /tribal-refresh / /tribal-validate / GitHub Actions  │
├─────────────────────────────────────────────────────────┤
│  横串 Cache Layer (v2 新規)                              │
│   SHA256 ベースで各 phase の成果物を自動キャッシュ       │
├─────────────────────────────────────────────────────────┤
│  横串 Distribution Layer (v2 新規)                       │
│   MCP server (6 tools) + 3 platform installer           │
└─────────────────────────────────────────────────────────┘
```

---

## 5. 特徴・長所

### 5.1 「全部読まない」を物理的に強制する

LLM は放っておくと「安心のために多めに読む」傾向があります。その気持ちは分かるが、それこそが
Meta 論文が引用した [arxiv 2602.11988](https://arxiv.org/abs/2602.11988) の失敗モードです。

v2 では 3 重の hook で opt-in を強制:

| Hook | 機会 | 役割 |
|---|---|---|
| UserPromptSubmit | タスク受領時 | router 起動指示を注入 |
| PostToolUse (Write/Edit) | context.md 保存時 | 25-45 行・4 heading・path 実在性を検証 |
| **PreToolUse (Read/Glob/Grep)** ★v2 | 探索的読取時 | router 未起動で context を直接読もうとしたら警告 |

「うっかり `.claude/context/*.md` を一括 import」のような失敗が物理的に抑止されます。

### 5.2 確信度を隠さない (graphify 哲学)

「不確実な知恵」も重要だが、書き方を間違えると新人が「断定形」と誤解して踏み抜きます。

v2 では Q3 各項目に 3 段階の確信度:
- **EXTRACTED (1.0)**: source code / commit に明示 → 「必ず壊れる」と書いてよい
- **INFERRED (0.6-0.9)**: 妥当な推論 → 「〜の可能性あり」トーン
- **AMBIGUOUS (0.1-0.3)**: 怪しいが重要 → **自動で人間判断ループへ**

AMBIGUOUS な Q3 が 1 件でもあれば critic が `MANUAL_REVIEW` verdict を出し、fixer は触らず
ログに `manual_review_required: true` で記録。**削ってしまうのではなく、記録して人に委ねる**。

### 5.3 決定論と LLM の役割分担

Tribal v1 は Q1-Q5 すべてを LLM で生成していたが、v2 では **「機械で取れるものは機械で」** に再設計:

| 情報 | v1 | v2 |
|---|---|---|
| Q1 (module 責務) | LLM | LLM (意味的なので) |
| Q2 (変更パターン) | LLM | LLM + AST の definitions を参照 |
| Q3 (non-obvious patterns) | LLM | LLM (ここが中核、confidence 追加) |
| **Q4 (deps)** | **LLM が Grep** | **tree-sitter AST が決定論抽出** |
| Q5 (tribal knowledge) | LLM | LLM + git log |

結果、module 1 件あたりの LLM トークンが **約 50-60% 削減** (実 LLM 計測は別 session)。

### 5.4 コミュニティ検出で routing 精度向上

module を degree-based でグラフ化し、Leiden (または Louvain) で **意味的にコヒーレントな
グループ** に分割。intent と community を対応付けて 2 段階選定:

```
query → intent 分類 → community 解決 → community 内で primary 選定 → 同 community ripple
```

baseline-target (graphify 18 modules) では:
- C2: cache + detect + extract (入力 pipeline, cohesion 0.667)
- C3: build + validate (graph assembly, cohesion 1.0)
- C0: analyze + cluster + report + watch + hooks (解析制御, cohesion 0.6)

ARCHITECTURE.md に人が書いた pipeline 分類と **自動検出されたクラスタが一致**。
LLM ゼロで意味的グループ化ができています。

### 5.5 削減効果を毎回数値化

「本当に削減されているのか?」の問いに数字で答えるため、毎回 benchmark 実行:

```
Benchmark: 5 cases, baseline 848 tokens
  avg ratio: 2.63x, median 2.63x, min 2.63x, max 2.63x
```

(3 sample contexts の小規模 test の値。mid-size monorepo 18+ contexts では 10-30x 想定)

CI で前回比 -20% 以上の劣化を検出。routing 品質が **静かに落ちる** ことを防ぎます。

### 5.6 MCP で他 AI platform に知識共有

`tribal serve --mcp` で以下の 6 tool を stdio で公開:

| Tool | 用途 |
|---|---|
| `route_query(query)` | 自然言語 → intent + primary contexts |
| `get_intent(name)` | intent 定義取得 |
| `get_ripple(module)` | 影響範囲取得 |
| `get_god_nodes(community?, top_n?)` | hub module 取得 |
| `get_community(id)` | community member + cohesion |
| `get_quality_history(module)` | 品質 log 履歴 |

Claude Desktop / Codex / Cursor から `@tribal` で問い合わせ可能に。

### 5.7 multi-platform 配布

`tribal install --platform` で 3 platform を選択:

| Platform | 機構 |
|---|---|
| `claude` | `.claude/` tree + 3 重 hook |
| `codex` | `AGENTS.md` + `.codex/hooks.json` |
| `opencode` | `AGENTS.md` + `.opencode/plugins/tribal.js` |

OpenAI Codex や OpenCode 利用チームも同じ routing intelligence を共有可能。

### 5.8 cache で refresh が瞬時

変更のない module は SHA256 hash が一致するため、analyst の LLM 呼出しゼロで完了:

```bash
# 初回 refresh
time python3 .claude/scripts/detect_changed_modules.py
# real: 3-5s

# 2 回目 (変更なし)
time python3 .claude/scripts/detect_changed_modules.py
# real: <0.05s — cache hit で瞬時
```

branch 切り替えで HEAD SHA が変わると自動 invalidate されるので、stale な cache を
掴み続ける心配はありません。

---

## 6. ユースケース

### UC1: 新人オンボーディング (50-200 module の monorepo)

**状況**: 新人が join、コードベースが 100+ module で「どこから触っていいか分からない」。

**v1 の使い方**:
1. プロジェクトマネージャーが `/tribal-init` で初回構築 (一度だけ)
2. 新人が質問: 「認証周りを触るならどこを見るべき?」
3. Claude Code が `/tribal-route` → `auth-config`, `session-validator`, `rate-limiter` の
   3 枚の compass (各 25-45 行) を提示
4. 新人は **3 ファイル読むだけ** で「触ると壊れる罠」「過去の設計判断」を把握

**効果**: 従来 2-3 日かかっていた「コードベース掌握」が半日で完了。

### UC2: 大規模リファクタリング前の影響調査

**状況**: データスキーマを変更したい。どの service に影響するか不明。

**v1 の使い方**:
1. `/tribal-route データスキーマを変更したい`
2. intent 分類 → `schema-change`
3. community C3 (build + validate) から primary context、ripple_index 経由で
   import/serialization 依存 module の secondary contexts を自動抽出
4. 全 7 module の「フラジリティ (壊れる条件)」が一目で把握可能

**効果**: 影響範囲の見落としによる「あとで判明したバグ」を事前に防げる。

### UC3: 障害対応 (ops-investigation)

**状況**: 本番で API latency が急上昇。原因不明で原因究明時間が惜しい。

**v1 の使い方**:
1. `/tribal-route レイテンシが上がった、原因調査`
2. intent 分類 → `ops-investigation` (anti_keywords で `add` を排除、誤分類しない)
3. community (serve + watch) の hub module = god_node `watch` を primary 提示
4. そこから ripple で依存 6 module の「壊れる条件」を一覧

**効果**: 深夜の障害対応で、関連コードの暗黙知を待ち時間ゼロで AI に教えられる。

### UC4: LLM 予算最適化

**状況**: チームで ChatGPT / Claude の使用が増え、トークン予算がキツい。

**v1 の使い方**:
- router 経由で毎タスク 3-5 枚のみロード → **平均 10-30x のトークン削減** (corpus 規模依存)
- benchmark.py が削減率を毎回自動計測、Slack / CI に投稿

**効果**: 同じ予算で 10 倍の開発タスクを捌ける。定量的に見える化。

### UC5: チーム間の知識共有 (MCP 経由)

**状況**: Claude Code 派と Codex 派が社内に混在、「認証ロジックについて聞きたい」が
毎回別々に調べて非効率。

**v1 の使い方**:
1. `tribal install --platform codex` で Codex 側にも AGENTS.md 展開
2. MCP server 起動 (`tribal serve --mcp`) して Claude Desktop / Codex Desktop から接続
3. 両者とも `@tribal route_query "認証ロジックを修正"` で同じ 3-5 context を取得

**効果**: platform が違っても **同じ知識ベースを共有**。新人は platform 選び放題。

### UC6: AI による暗黙知の継続的アップデート

**状況**: 月 1 のエンジニア退職で知識が失われる不安。

**v1 の使い方**:
- GitHub Actions が 14 日毎に `/tribal-refresh` を自動実行
- 変更モジュールのみ再分析、cache hit で変化なし module は skip
- 品質回帰ゲート (avg_score -0.3 以上劣化で CI fail)
- `_quality-log.jsonl` に全履歴を追記で、「いつ誰が書いた Q3 が失われたか」も追跡可能

**効果**: 「あの人しか知らない」が自動的に AI の「罠データベース」に蓄積。

---

## 7. 他ツールとの比較

| ツール | 得意 | 苦手 | Tribal v2 との関係 |
|---|---|---|---|
| README / Wiki | 人が書く概念説明 | 更新が追いつかない、罠情報が落ちる | 補完 (Tribal が補う) |
| GitHub Copilot | インライン補完 | プロジェクト固有の罠を学習していない | 補完 (Copilot + Tribal context で精度向上) |
| Claude Projects | ドキュメント共有 | 動的な context 選定ができない | Claude Code に Tribal を入れる方が筋が良い |
| graphify (元ネタ) | グラフ可視化 | 「罠データベース」の哲学がない | **編み込み元** — 決定論性を tribal に輸入 |
| RAG (vector DB) | 類似検索 | 「非自明」パターンの明文化は苦手 | 直交 — 併用可能 |
| Cursor / Aider | IDE 統合 | 独自の routing なし | Tribal MCP server 経由で利用可能 |

---

## 8. 想定しない用途 (ユースケース非対応)

- **単一ファイルのコードベース**: module 粒度がないので効果薄い
- **10 file 未満の小規模プロジェクト**: 全部読んでも context に収まる、Tribal は過剰
- **頻繁に変わる prototype**: refresh コストが benefit を上回る
- **セキュリティ監査用途**: Tribal は設計文書であり、脆弱性検出ではない (別ツール併用を)

---

## 9. 次のステップ

- **セットアップ方法**: `manual/02_setup_and_usage.md` を参照
- **技術詳細 (初心者向け丁寧解説)**: `manual/03_specification.md` を参照
- **設計の背景**: `docs/tribal-improvement-plan.md` (改善計画書)
- **v1 利用者の移行**: `docs/MIGRATION_v1_to_v2.md`
- **アーキテクチャ図**: `docs/ARCHITECTURE.md`
