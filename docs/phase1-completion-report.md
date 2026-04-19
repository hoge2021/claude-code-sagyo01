# Phase 1 完了報告: Cache Layer 単独導入

**完了日**: 2026-04-19
**ブランチ**: `tribal-v2-migration`
**作業ディレクトリ**: `tribal-v2/` (tribal v1 immutable 保全のため別 dir で作業)

---

## 実施内容

### 1.1 ファイル作成

| 成果物 | パス | LOC |
|---|---|---|
| ★ cache layer 本体 | `tribal-v2/.claude/scripts/cache.py` | 234 |
| ★ 単体テスト | `tribal-v2/.claude/scripts/test_cache.py` | 165 |
| ★ cache 配置 | `tribal-v2/.claude/cache/.gitkeep` | — |
| .gitignore 更新 | `tribal-v2/.gitignore` | +5 行 |

### 1.2 既存 script への組み込み

- `tribal-v2/.claude/scripts/detect_changed_modules.py` を更新:
  - cache.py を import (graceful import で v1 互換性維持)
  - 新関数 `cache_hit_modules()` で SHA256 cache をチェック
  - 出力 JSON に `cached_modules` `cache_skipped_from_changes` `cache_status` を追加
  - `--no-cache` フラグで cache fast path を無効化可能
  - **副次的 fix**: 単一ファイル module で `rglob('*')` が空集合を返す v1 バグを修正
- `tribal-v2/.claude/commands/tribal-refresh.md` を更新:
  - 「v2 cache の働き」セクションを追加
  - 完了報告に cache hit 件数を含める指示

### 1.3 単体テスト (8 ケース全 PASS)

```
T1 same content → same hash                     ✓
T2 .md frontmatter-only edit → same hash        ✓
T3 .py content change → hash differs            ✓
T4 branch switch (HEAD diff) → hash differs     ✓
T5 save → load roundtrip + stale invalidation   ✓
T6 invalid kind → ValueError                    ✓
T7 cached_modules() filters stale entries       ✓
T8 clear_cache() count matches deletions        ✓
PASS: 8/8 tests
```

### 1.4 動作確認 (E2E on baseline-target)

| テスト | 結果 |
|---|---|
| Test 1: 空 cache 状態で detect 実行 | ✓ cache_status=active, cached=0 |
| Test 2: 3 sample populate → detect | ✓ cached=3 (cache, security, cluster) |
| Test 3 (バグ修正後): hash が module ごとに異なる | ✓ 3 module で hash distinct |
| Test 4: cache active 状態の出力検証 | ✓ cached_modules 正常出力 |
| Test 5: cache.py 編集 → cache miss | ✓ cached=2 (cache.py が外れる) |
| Test 6: 元に戻して cache hit 復活 | ✓ cached=3 |
| Test 7: --no-cache flag | ✓ cache_status=disabled, cached=0 |
| Test 8 (mtime fix 後): single-file 変更検出 | ✓ changed_modules に正しく登録 |
| Test 9: 全状態の整合性 | ✓ 15 changed + 3 cached = 18 total |
| Regression: baseline-target を v1 に restore | ✓ v1 出力 schema を維持 |

---

## Phase 1 で副次的に発見・修正した tribal v1 バグ

### v1 バグ #4: 単一ファイル module で mtime 検出漏れ

**症状**: `mtime_based_changes()` が `mod_path.rglob("*")` で iterate しているため、`mod_path` がディレクトリではなくファイル (例: `graphify/cache.py`) の場合、空集合になり変更が検出されない。

**影響**: graphify のような flat package で、ファイル変更が `/tribal-refresh` に反映されない。

**修正**: `tribal-v2/.claude/scripts/detect_changed_modules.py:79-95` で `mod_path.is_file()` の場合に当該ファイル自体を比較対象にする分岐を追加。

### v2 バグ (自分で混入し即修正): module path 解決の fallback 漏れ

**症状**: `_module_files()` が `module_id="graphify/cache"` を渡されても `graphify/cache` というディレクトリは存在せず空リストを返していた。結果、3 module 全てが同じ hash になっていた。

**修正**: `cache.py:_module_files()` に「stem fallback」を追加 (`graphify/cache` → `graphify/cache.py` を試す)。

---

## 計画書 (`tribal-improvement-plan.md`) 期待効果との照合

| 計画書 9 節の指標 | Phase 1 単独での到達 |
|---|---|
| `/tribal-refresh` 平均所要時間 25-40% に短縮 | **Phase 1 で部分達成**: cache hit module の analyst 呼び出しを完全スキップ可能 (実際の短縮率は Phase 7 統合 E2E で計測) |
| (その他の指標) | Phase 2-6 で別途達成 |

---

## ロールバック手順 (もし Phase 2 で問題が出たら)

```bash
git -C /home/hoge/51_mygit/claude-code-sagyo01 revert <Phase 1 commit SHA>
# tribal-v2/.claude/scripts/cache.py と test_cache.py は無害なので残しても可
# detect_changed_modules.py だけ v1 から再 copy:
cp tribal/.claude/scripts/detect_changed_modules.py tribal-v2/.claude/scripts/detect_changed_modules.py
```

---

## 次のステップ: Phase 2 (AST 第1パス)

- `module-ast-extractor` agent 新規追加
- tree-sitter 5 言語 (py, ts, go, rs, java) で Q2/Q4 を決定論抽出
- `module-analyst` を Q1/Q3/Q5 集中型にスリム化
- 期待トークン削減: 50-60% per module

⚠️ Python 3.14.3 で tree-sitter package のインストール可否を Phase 2 開始時に再確認 (PyPI access が必要)。
