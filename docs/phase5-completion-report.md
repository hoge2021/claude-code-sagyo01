# Phase 5 完了報告: Benchmark + PreToolUse Hook

**完了日**: 2026-04-19
**ブランチ**: `tribal-v2-migration`
**先行 commits**: P1 `8c26495`, P2 `84db546`, P3 `b705aa1`, P4 `905efad`

---

## 実施内容

### 5.1 benchmark スクリプトと agent

| 成果物 | パス | LOC |
|---|---|---|
| ★ benchmark 本体 | `tribal-v2/.claude/scripts/benchmark.py` | 198 |
| ★ schema | `tribal-v2/.claude/schemas/benchmark.schema.json` | 38 |
| ★ agent | `tribal-v2/.claude/agents/benchmark-reporter.md` | 38 |

特徴:
- graphify `_estimate_tokens` (4 chars/token) を流用 — tiktoken 不要で軽量
- prompt-tester 出力を入力に取り、各 case の baseline_tokens (全 .md 集計) vs
  routed_tokens (router 選定 .md のみ) で ratio 計算
- prompt-tests 不在時の `--dry-run` モード (5 標準サンプル query)
- `_quality-log.jsonl` に `tokens_saved_ratio` 自動追記

### 5.2 mapper skill 更新

- `tribal-mapper/SKILL.md` に Phase 8.5 (Benchmark) 挿入
- 完了報告に benchmark summary を含める指示

### 5.3 PreToolUse hook 追加

| 成果物 | パス | LOC |
|---|---|---|
| ★ hook 本体 | `tribal-v2/.claude/scripts/check_router_state.py` | 96 |

特徴:
- 既存 inject_router_directive と同じ `.session-state/router-state.json` を共有
- TASK_WINDOW (30 分) 内で router が走っていれば素通し
- opt-out フラグ立ちで素通し
- それ以外で `.claude/context/*.md` への直接 Read/Glob/Grep を検出 → 警告 additionalContext
- **block しない** (warning only) — tribal の opt-in 哲学は強制ではなく誘導
- index file (`_routing-table.json` 等) は warning 対象外

`tribal-v2/.claude/settings.json` に PreToolUse hook 登録 (matcher = `Read|Glob|Grep`)。

### 5.4 CI gate 拡張

`tribal-v2/.github/workflows/tribal-refresh.yml` に benchmark step 追加:
- prompt-tests.json があれば実行、なければ `--dry-run`
- summary を CI ログに出力
- `avg_ratio < 5.0` で WARNING (将来的に fail に格上げ可)

`check_quality_regression.py` は既に Phase 3 で `weighted_overall` 優先比較済み、
benchmark の `tokens_saved_ratio` も `_quality-log.jsonl` 経由で間接的に regression 検知。

### 5.5 validate command 強化

`tribal-validate.md` に Step 5 (benchmark) 追加:
- `summary.avg_ratio < 5.0` を「要注意」項目として明示

### 5.6 単体テスト + E2E (`test_phase5.py`, 9/9 PASS)

```
T1 estimate_tokens (4 chars/token)             ✓
T2 naive_baseline excludes _-prefixed files     ✓
T3 routed_tokens (subset only)                  ✓
T4 dry-run: 5 cases, avg_ratio=3.42x            ✓
T5 ratio = baseline/routed = 10.0x              ✓
T6 opted_out → passthrough                      ✓
T7 recent routing (60s ago) → passthrough       ✓
T8 stale session + context Read → warning       ✓
T9 _routing-table.json → no warning             ✓
```

E2E (baseline-target で 3 sample contexts):
- benchmark dry-run: 5 cases, baseline 848 tokens, **avg ratio 2.63x**
- check_router_state: stale → 警告 JSON 出力, 直近 routing → empty passthrough

→ 3 contexts での 2.63x は妥当 (mid-size repo 18+ contexts なら 10-30x 想定)

---

## Phase 5 で達成した defense-in-depth

| Hook 種別 | matcher | 役割 | Phase |
|---|---|---|---|
| `UserPromptSubmit` | (all) | 開発タスク検出時に router 起動指示注入 | tribal v1 |
| `PostToolUse` | `Write\|Edit\|MultiEdit` | context.md を validate (行数/heading/path) | tribal v1 |
| `PreToolUse` | `Read\|Glob\|Grep` | router 未起動で context Read を試行したら警告 | **★Tribal v2** |

3 重の opt-in 強制 → subagent 経由のすり抜けも誘導可能に。

---

## 計画書 (`tribal-improvement-plan.md`) 期待効果との照合

| 計画書 9 節の指標 | Phase 5 単独での到達 |
|---|---|
| token reduction を毎回計測・可視化 | ✅ benchmark.py + Phase 8.5 |
| naive vs router の reduction 10-30x | 構造的下地完成、実規模は Phase 7 E2E |
| CI で benchmark 回帰検出 | ✅ workflow に benchmark step 追加 |

---

## ロールバック手順

```bash
git -C /home/hoge/51_mygit/claude-code-sagyo01 revert <Phase 5 commit SHA>
# settings.json から PreToolUse セクション削除でも可
# benchmark.py / check_router_state.py は無害なので残置可
```

---

## 次のステップ: Phase 6 (MCP Server + Multi-Platform Distribution)

- `tribal/serve.py` MCP server (route_query / get_intent / get_ripple / get_god_nodes 等)
- multi-platform installer (Claude Code / Codex / OpenCode の 3 platform)
- Python パッケージ化 (`tribal/__init__.py`, `pyproject.toml` 本格定義)
- `tribal/security.py` を graphify から借用 + `validate_context_file.py` の path 検証強化
