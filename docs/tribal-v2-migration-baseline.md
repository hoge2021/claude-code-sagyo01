# Tribal v2 Migration — Baseline 採取記録

**作成日**: 2026-04-19
**ブランチ**: `tribal-v2-migration`
**初回コミット**: `451c209`
**target**: `baseline-target/` (graphify 0.4.23 source + tribal v1 install)

---

## Phase 0 環境チェック結果

| 項目 | 結果 | 備考 |
|---|---|---|
| Python バージョン | **3.14.3** | ⚠️ graspologic 非対応 (3.13+ 不可)。Phase 4 は Louvain fallback 確定 |
| Claude Code バージョン | **2.1.114** | OK |
| Git 状態 | clean | tribal-v2-migration ブランチ作成済み |
| target サイズ | 18 modules / 9156 LOC / 940KB | mid-size、適切 |

---

## 採取した baseline 値

### 構造メトリクス (Phase 1, 5, 6, 7 を実 artifact で測定)

| 指標 | 値 | 算出元 |
|---|---|---|
| total_modules | 18 | `_repo-map.json` (graphify ARCHITECTURE.md に基づく分割) |
| total_loc | 9,156 | wc -l |
| dep-graph nodes | 18 | `_dep-graph.json` |
| dep-graph edges | 20 | `_dep-graph.json` (cross-module imports のみ) |
| avg_ripple_size | 1.11 | dep-graph stats |
| max_ripple_module | `graphify/analyze` | ripple size 4 (report, export, serve, watch が依存) |
| seed intents | 8 | `_routing-table.json` (feature-add, bug-fix, ..., test-add) |
| coverage_ratio (構築前) | 0.0 | 18/18 missing |

### Compass 品質メトリクス (Phase 2-3 サンプル: cache, security, cluster)

| Module | LOC | context 行数 | context ~tokens | 必須 heading | Q3 件数 | Q5 件数 |
|---|---|---|---|---|---|---|
| graphify/cache | 169 | 26 | 313 | 4/4 ✓ | 3 | 3 |
| graphify/security | 203 | 28 | 398 | 4/4 ✓ | 4 | 3 |
| graphify/cluster | 137 | 26 | 356 | 4/4 ✓ | 4 | 4 |
| **avg** | 170 | 27 | 356 | 4/4 | 3.7 | 3.3 |

→ **compass 形式遵守**: 25-45 行制約 / 4 heading / 1.2k token cap 全 PASS

### サンプル Q3 の代表例 (tribal v1 の到達点を示す)

- **cache**: 「Markdown frontmatter は hash 対象外」(意図的だが直感に反する)
- **security**: 「Redirect 先の re-validation」(safe_fetch 経由しないと open-redirect 成立)
- **cluster**: 「graspologic ANSI が PowerShell 5.1 scrollback を破壊」(issue #19 由来)

→ いずれも **「コードを読んでも自明でない failure mode」** で Q3 の質基準を満たす

---

## Phase 0 で発見した tribal v1 の問題 (v2 で改善対象)

### 問題 1: 単独拡張子 backtick が path 扱いされる (バグ)

**症状**: context.md 内で `\`.md\`` のような bare extension を backtick で囲むと、`validate_context_file.py` が path として解釈し、存在しないため validation fail。

**再現**:
```
$ echo '{"tool_input":{"file_path":"...graphify__cache.md"}}' | python3 .claude/scripts/validate_context_file.py
context validation failed for ...:
  - referenced path does not exist: .md
```

**原因**: `is_path_like()` が `token.endswith(PATH_SUFFIXES)` を最終 fallback にしているため、`.md`/`.py`/`.json` 単独でも match。

**v2 改善案**: `is_path_like()` に「`/` を含まない単独拡張子は path 扱いしない」を追加。

### 問題 2: See Also 参照先が未作成だと validation fail

**症状**: 部分構築 (refresh で 1 module だけ再生成等) で、See Also 参照先がまだ無いと毎回 fail。

**回避策**: tribal v1 では full /tribal-init を要求。

**v2 改善案**: routing-upgrader が `_communities.json` 経由で参照解決し、See Also の妥当性を **論理リンクとして** チェック (file 存在ではなく)。

### 問題 3 (Phase 0 コンセプト不一致): 単一フラット package で「1 module」になる

**症状**: graphify は flat package で repo-explorer の rule 1-5 を厳密適用すると 1 module 扱い。

**回避策**: ARCHITECTURE.md を読んで file 単位 module として認識 (今回の baseline 採取の判断)。

**v2 改善案**: repo-explorer に「ARCHITECTURE.md / docs/ARCHITECTURE.md 等の存在 → 記載モジュールを優先採用」を追加。

---

## LLM-heavy フェーズの参考値 (実機 /tribal-init で測定推奨)

ここまでの baseline は **LLM 呼び出しゼロ** で構造的事実のみ採取。
以下は `/tribal-init` を本物の Claude Code セッションで走らせる際に必ず控える項目:

```markdown
## v1 LLM Baseline 値 (実機採取)

- 実行日時:
- Phase 2 (analyst) 全 18 modules の合計入力トークン:
- Phase 2 全 18 modules の合計出力トークン:
- Phase 3 (writer) 合計トークン:
- Phase 4 (critic + fixer) 合計トークン (3 ラウンド最大):
- Phase 7 (routing-upgrader) トークン:
- Phase 8 (prompt-tester) トークン:
- ──────
- /tribal-init 総 LLM トークン (input + output):
- /tribal-init 総所要時間:                分
- critic 平均ラウンド (PASS 到達まで):
- prompt test pass_rate:
- router 選定平均枚数 (10 サンプル):
```

10 サンプルクエリ:
1. 新しい言語 (Dart) の AST 抽出を追加したい
2. cache hit 率が低い、調査
3. validate_url のホスト解決ロジックを変更
4. Leiden の閾値をリポジトリ別に変えたい
5. report の god_node セクションフォーマットを変更
6. ingest で twitter URL の対応を追加
7. watch のデバウンス時間を環境変数化
8. MCP serve に新 tool を追加
9. PowerShell 出力崩れの再発調査
10. graph.html が大きい時の splitting 戦略を実装

---

## Phase 0 完了判定

| 完了条件 | 状態 |
|---|---|
| 環境確認 (Python / Claude Code / git) | ✅ |
| 作業ブランチ作成 | ✅ |
| baseline 構造 artifact 採取 (Phase 1, 5, 6, 7 相当) | ✅ |
| compass 品質 baseline 採取 (3 module sample) | ✅ |
| tribal v1 hook 動作確認 (validator 起動 OK) | ✅ |
| tribal v1 の問題発見と記録 | ✅ (3 件) |
| LLM フェーズの全件 baseline | ⏸️ 実機 /tribal-init で別途採取 |

→ **Phase 0 は構造的・部分的 baseline として成立**。Phase 1 (Cache Layer 単独導入) に進める。
LLM 全件 baseline は Phase 7 統合 E2E までに実機計測で補完。

---

## 採取済み artifact 一覧 (`baseline-target/.claude/`)

```
context/
  _repo-map.json           # 18 modules
  _dep-graph.json          # 18 nodes, 20 edges
  _coverage.json           # baseline (0/18 covered)
  _routing-table.json      # 8 seed intents
  _deps_raw.json           # 中間ファイル
  graphify__cache.md       # sample compass (26 lines)
  graphify__security.md    # sample compass (28 lines)
  graphify__cluster.md     # sample compass (26 lines)
artifacts/analyst/
  graphify__cache.json     # 5 問完備
  graphify__security.json  # 5 問完備
  graphify__cluster.json   # 5 問完備
```

→ Phase 1 では `cache.py` を新規追加し、これらの artifact が SHA256 cache hit するか確認する。
