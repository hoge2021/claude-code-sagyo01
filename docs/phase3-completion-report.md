# Phase 3 完了報告: Confidence Label 必須化

**完了日**: 2026-04-19
**ブランチ**: `tribal-v2-migration`
**先行 commits**: `8c26495` (Phase 1), `84db546` (Phase 2)

---

## 実施内容

### 3.1 schema 更新

| Schema | 変更内容 |
|---|---|
| `analyst.schema.json` | Q3 に `confidence` `confidence_score` required 化、`Q3_hyperedges` optional 追加、`related_modules` optional 追加 |
| `critic.schema.json` | `verdict` enum に `MANUAL_REVIEW` 追加、`weighted_overall` / `confidence_consistency` 軸追加、`ambiguous_q3_count` フィールド追加 |
| `quality-log.schema.json` | `weighted_overall` / `tokens_saved_ratio` / `confidence_summary` / `ast_extraction_method` / `cache_hit` 追加 |

### 3.2 マイグレーションスクリプト

- 新規: `tribal-v2/.claude/scripts/migrate_v1_to_v2.py` (148 LOC)
  - analyst Q3 全件に `confidence=EXTRACTED, score=1.0` 充当
  - critic に `weighted_overall` 計算 + `ambiguous_q3_count=0` 初期化
  - quality-log 既存 entry に `weighted_overall` + `cache_hit=False` 充当
  - **idempotent**: 既に v2 化されたものは skip
  - `--dry-run` モードあり
- 単体テスト: `tribal-v2/.claude/scripts/test_migrate.py` (148 LOC, 6/6 PASS)

### 3.3 agent prompt 更新

- `module-analyst.md`:
  - Q3 出力例に `confidence` `confidence_score` `related_modules` を追加
  - Q3_hyperedges セクション追加 (3+ module 横断 trap)
  - **規範文**: INFERRED 0.6-0.9 / AMBIGUOUS 0.1-0.3 / EXTRACTED 1.0、デフォルト 0.5 禁止
- `context-critic.md`:
  - **6 軸目** `confidence_consistency` 追加 (隔離原則の例外として analyst.json の confidence を読んで良い)
  - **MANUAL_REVIEW verdict** 追加 (AMBIGUOUS Q3 1+ または confidence_consistency<3.0 で自動上申)
  - PASS 閾値を **`weighted_overall`** ベースに変更 (path_accuracy=2x, non_obvious_value=2x)
- `context-fixer.md`:
  - MANUAL_REVIEW verdict は **修正せず log のみ** (人手判断に格上げ)
  - confidence_consistency fix の対処パターン追加

### 3.4 quality log + CI 拡張

- `check_quality_regression.py` を `weighted_overall` 優先比較に更新 (v1 entry は `overall` fallback)

### 3.5 動作確認

| テスト | 結果 |
|---|---|
| migration unit tests | ✓ 6/6 PASS |
| baseline-target で migration 適用 (3 analyst JSON) | ✓ 3 migrated, 0 skipped |
| 2 回目 dry-run 確認 (idempotent) | ✓ 0 migrated, 3 skipped |
| 新 schema validation | ✓ 3/3 pass |
| weighted_average 数値検証 (path=5/non_obv=4.5/others=4,4,3.5 → 4.357) | ✓ T2 で確認 |

---

## Phase 3 で確立された v2 哲学

### 不確実性を隠さない (graphify 由来)

v1 の Q3 は二値 (書いてある/ない)。v2 では **3 段階 confidence** で:

- 確信があれば EXTRACTED (1.0) — 自明な事実
- 推論なら INFERRED (0.6-0.9) — 「妥当だが完全な根拠は無い」
- 怪しければ AMBIGUOUS (0.1-0.3) — **削るのではなく記録**

AMBIGUOUS な Q3 は critic が自動で MANUAL_REVIEW verdict にし、fixer はそれを
触らずに `manual_review_required: true` で log。**人間の判断ループに自動的に到達する**。

### 重要度の可視化 (weighted_overall)

`overall` (単純平均) と `weighted_overall` (重み付け) を両方記録:
- `path_accuracy` 2x: broken path は致命的
- `non_obvious_value` 2x: Q3 の質が context の中核
- 他 1x

これにより「全体スコア悪くないが path が壊れている」のような状況を gate で検出。

### v1 → v2 互換維持

migration script により v1 artifact は **追加フィールドだけ** 充当される (破壊的変更なし)。
既存 ユーザーは migration 実行で v2 移行可能、v1 のまま運用も schema validation 緩和で可。

---

## ロールバック手順

```bash
# Phase 3 のみ revert (Phase 1/2 は維持)
git -C /home/hoge/51_mygit/claude-code-sagyo01 revert <Phase 3 commit SHA>
# baseline-target の analyst JSON も migration 戻し:
# (migration は idempotent なので revert 不要、新 schema が緩和されれば動く)
```

---

## 次のステップ: Phase 4 (Community Detection + God Node)

- `community-clusterer` agent (Leiden/Louvain) 新規追加
- `god-node-detector` agent 新規追加
- routing-upgrader が「god-node 推薦の判定者」モードに
- `tribal-router` が intent → community → primary → ripple の 2 段階選定に
- `_index.md` (wiki entry, router fallback) 生成

⚠️ Python 3.14.3 で graspologic 不可確定 (Phase 0 で確認済み) → Louvain fallback で実装。
