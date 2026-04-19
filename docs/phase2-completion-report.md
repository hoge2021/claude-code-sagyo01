# Phase 2 完了報告: AST 第1パス追加

**完了日**: 2026-04-19
**ブランチ**: `tribal-v2-migration`
**先行 commit**: `8c26495` (Phase 1)

---

## 実施内容

### 2.1 ファイル作成

| 成果物 | パス | LOC |
|---|---|---|
| ★ AST 抽出本体 | `tribal-v2/.claude/scripts/ast_extract.py` | 281 |
| ★ 単体テスト | `tribal-v2/.claude/scripts/test_ast_extract.py` | 122 |
| ★ AST schema | `tribal-v2/.claude/schemas/ast.schema.json` | 73 |
| 5 言語 fixture | `tribal-v2/tests/fixtures/sample_module/{sample.py,sample.ts,sample.go,sample.rs,Sample.java}` | — |
| AST artifacts dir | `tribal-v2/.claude/artifacts/ast/.gitkeep` | — |

### 2.2 新 agent 定義

- `tribal-v2/.claude/agents/module-ast-extractor.md`
  - `model: haiku` (整形のみで軽量)
  - `tools: Bash, Read, Glob`
  - 出力先: `.claude/artifacts/ast/<module-flat>.json`
  - cache 連携で hash 一致時は LLM 呼び出しゼロ

### 2.3 既存 agent / skill 更新

- `tribal-v2/.claude/agents/module-analyst.md`:
  - **Step 0** 新設: AST.json を最初に Read (存在すれば)
  - Q4 cross_module_deps は AST `imports` から集約 (Grep スキップ可能)
  - Q2 example_files は AST `definitions` から選定
  - AST.json なし / `lang=unsupported` 時は **従来動作にフォールバック** (互換維持)
- `tribal-v2/.claude/skills/tribal-mapper/SKILL.md`:
  - Phase 2 を **Phase 2a (AST)** + **Phase 2b (Semantic)** に分割
  - Phase 2a は全件並列、cache hit で多くスキップ
  - Phase 2b は changed_modules のみ (cache hit 自動 skip と組み合わせ)
- `tribal-v2/.gitignore` に `.claude/artifacts/ast/*.json` 追加

### 2.4 単体テスト (9/9 PASS)

```
T1 python:       3 imports, 4 defs, 8 calls   ✓
T2 typescript:   2 imports, 4 defs, 5 calls   ✓
T3 go:           1 imports, 3 defs, 5 calls   ✓ (Go struct 名は v2.1 で改善予定)
T4 rust:         2 imports, 5 defs, 11 calls  ✓
T5 java:         4 imports, 7 defs, 5 calls   ✓
T6 unsupported (.md) → empty fallback         ✓
T7 directory: 5 言語混在で全 file 抽出         ✓
T8 cache miss → cache hit roundtrip           ✓
T9 stem fallback (foo → foo.py 解決)          ✓
PASS: 9/9 tests
```

### 2.5 baseline-target 上の E2E (18 modules 全件 AST 抽出)

| 指標 | 値 |
|---|---|
| 抽出時間 (cold) | 0.29 s (18 modules) |
| 抽出時間 (cache hit) | 0.05 s (~6x 高速化) |
| 抽出した imports | 180 件 |
| 抽出した definitions | 268 件 |
| 抽出した calls (dedup) | 1,867 件 |
| 抽出した calls (raw) | 3,550 件 (dedup で 1.9x 圧縮) |
| AST artifact 総 size | 404 KB (~101k tokens) |
| 元 source size | 376 KB (~94k tokens) |
| AST/source 比 | 1.07x |

---

## 設計判断と発見

### A: AST artifact size の最適化

初版で artifact が source の **1.5x 大きい** (170k tokens) になり驚き発見。
分析: 各 call 呼び出し点を独立 JSON object として保存していたため bloat。

修正:
- `(caller, callee)` ペアで dedup → calls 1.9x 圧縮 (3550 → 1867)
- `imports` から `raw` フィールド削除 (冗長な原文)

→ AST/source 比を 1.07x まで縮減。

**重要**: 「analyst が読むトークン数」と「artifact 総 size」は別物。
analyst は artifact 全部読まず、imports + 上位 definitions のみ Read する設計。
実際の LLM 削減効果は Phase 7 E2E で測定。

### B: Go の struct 抽出限界

Go の `type_declaration` ノードは struct/interface 名を直接持たず、子ノード `type_spec` に
名前がある。現在の単純な name field 抽出では struct が拾えない (関数のみ抽出)。

→ v2.1 改修候補としてテストコメントに記録。Phase 2 のスコープでは PASS 扱い (関数は取れる)。

### C: tree-sitter API 互換性確認

```
tree_sitter==0.25.2
tree_sitter_python==0.25.0
tree_sitter_typescript==0.23.2 (language_typescript / language_tsx の 2 dialect)
tree_sitter_go==0.25.0
tree_sitter_rust==0.24.2
tree_sitter_java==0.23.5
Python 3.14.3 で全パッケージインストール成功
```

graphify の依存と互換 (graphify は tree-sitter>=0.23 を要求)。

---

## 計画書 (`tribal-improvement-plan.md`) 期待効果との照合

| 計画書 9 節の指標 | Phase 2 単独での到達 |
|---|---|
| `/tribal-init` LLM トークン 35-45% (元の 100% から削減) | **未測定**: 構造的下地は完成、analyst の実 LLM 計測は Phase 7 E2E |
| ast.json で Q4 を決定論抽出 | ✅ 18 modules 180 imports を完全自動化 |
| 未対応言語で fallback | ✅ T6 で検証済み |
| cache 連携 | ✅ 2 回目で 18/18 hit, 6x 高速化 |

---

## ロールバック手順

```bash
git -C /home/hoge/51_mygit/claude-code-sagyo01 revert <Phase 2 commit SHA>
# または手動: tribal-v2/.claude/agents/module-analyst.md の Step 0 セクション削除
# tribal-v2/.claude/skills/tribal-mapper/SKILL.md を Phase 2a/2b 分割前に戻す
# ast_extract.py / module-ast-extractor.md は無害なので残置可
```

---

## 次のステップ: Phase 3 (Confidence Label 必須化)

- analyst.schema.json の Q3 に `confidence` `confidence_score` required 追加
- critic.schema.json に `MANUAL_REVIEW` verdict と `weighted_overall` 追加
- 既存 artifact migration script
- AMBIGUOUS Q3 の自動上申で reconciliation ループ短縮

Phase 3 は LLM 動作変更が中心 (schema + agent prompt 更新)。実 LLM テストは
Phase 7 E2E まで保留可能。
