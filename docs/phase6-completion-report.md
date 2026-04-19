# Phase 6 完了報告: MCP Server + Multi-Platform Distribution

**完了日**: 2026-04-19
**ブランチ**: `tribal-v2-migration`
**先行 commits**: P1 `8c26495`, P2 `84db546`, P3 `b705aa1`, P4 `905efad`, P5 `e4f97de`

---

## 実施内容

### 6.1 Python パッケージ化

| 成果物 | パス |
|---|---|
| ★ pyproject.toml 本格定義 | `tribal-v2/pyproject.toml` |
| ★ tribal パッケージ本体 | `tribal-v2/tribal/` (8 modules) |
| ★ `__init__.py` (version) | `tribal-v2/tribal/__init__.py` |

PyPI name: `tribal-knowledge-mapper`, import name: `tribal`.
optional dependencies: `[ast]` (tree-sitter), `[leiden]` (graspologic), `[mcp]`, `[schema]`, `[all]`.

既存 6 scripts (cache, ast_extract, cluster, god_nodes, benchmark, check_router_state)
を `tribal/` 配下にコピー。`.claude/scripts/` は runtime 用として維持、両方動作確認済み。

### 6.2 security モジュール (graphify 由来)

`tribal/security.py` (148 LOC):
- `validate_url` — http/https のみ、private/reserved IP block、cloud metadata host block
- `_NoFileRedirectHandler` — redirect 毎に re-validation (open-redirect SSRF 対策)
- `safe_fetch` / `safe_fetch_text` — size cap (50 MB / 10 MB)
- `validate_context_path` — `.claude/` 配下に限定 (graphify の `graphify-out/` 相当)
- `sanitize_label` — control char strip + 256 char cap
- `sanitize_label_for_html` — 上記 + html.escape (callsite 責任を明確化)

`validate_context_file.py` hook に組み込み:
- `extract_target_path` で `tribal.security.validate_context_path` を経由
- 失敗時は v1 動作に fallback (graceful)

### 6.3 MCP server (serve.py)

`tribal/serve.py` (235 LOC) — graphify/serve.py ベース。6 MCP tools:

| Tool | 用途 |
|---|---|
| `route_query(query)` | 自然言語 → intent 分類 + primary contexts (router skill 相当を決定論で) |
| `get_intent(name)` | intent 定義取得 (keywords / primary / community_hint) |
| `get_ripple(module)` | 影響範囲 (ripple_index) 取得 |
| `get_god_nodes(community?, top_n?)` | global / 特定 community の hub module |
| `get_community(id)` | community member + cohesion + label |
| `get_quality_history(module)` | `_quality-log.jsonl` の履歴 |

全 tool 出力は `sanitize_label` で prompt injection 防御 (graphify 知見)。
`mcp` package 未 install 時は明確なエラーで起動拒否、standalone CLI は動作可能。

### 6.4 multi-platform installer (__main__.py)

`tribal/__main__.py` (257 LOC) — graphify `_PLATFORM_CONFIG` パターンを 3 platform に絞り:

| Platform | 設置先 | always-on 機構 |
|---|---|---|
| `claude` | `.claude/` tree + `CLAUDE.md` + `settings.json` | UserPromptSubmit + PostToolUse + **PreToolUse(Read\|Glob\|Grep) (v2 新規)** |
| `codex` | `AGENTS.md` + `.codex/hooks.json` | PreToolUse hook |
| `opencode` | `AGENTS.md` + `.opencode/plugins/tribal.js` | tool.execute.before plugin |

`settings.json` のマージは hook 重複検出付き (既存ユーザー設定を破壊しない)。
`.tribal_version` でインストール済みバージョン追跡。

### 6.5 ドキュメント整備

- `README.md` 更新 (使い方 + 進捗表 + ディレクトリ構成)
- `phase6-completion-report.md` (本ファイル)

### 6.6 単体テスト + E2E (10/10 PASS)

`tribal/test_phase6.py`:
```
T1 validate_url: http/https only                         ✓
T2 validate_url: private IP blocked                       ✓
T3 validate_url: cloud metadata host blocked              ✓
T4 validate_context_path: allowed inside .claude/         ✓
T5 validate_context_path: traversal blocked               ✓
T6 sanitize_label: control chars + length                 ✓
T7 serve.route_query: 追加 → feature-add                  ✓
T8 serve.get_ripple: 該当 module 返却                     ✓
T9 serve.call_tool: unknown → error + available list      ✓
T10 install --platform claude: 構造 + CLAUDE.md + stamp   ✓
```

**E2E on baseline-target**:
- `pip install -e .` 成功 (2.0.0-rc1)
- `tribal --version` / `tribal --help` 動作
- `tribal install --platform claude --target /tmp/test` で完全な `.claude/` tree + `CLAUDE.md` + hook 統合 settings.json 展開
- `python3 -m tribal.serve --call route_query --args '{"query":"スキーマフィールドを追加したい"}'` →
  feature-add intent + primary contexts 返却
- `get_ripple graphify/analyze` → 4 impacted modules 正確

---

## v1 → v2 比較 (Phase 6 時点)

| 観点 | v1 tribal | v2 tribal |
|---|---|---|
| 配布形式 | tar.gz + 手動 cp | `pip install tribal-knowledge-mapper` |
| platform 対応 | Claude Code のみ | Claude / Codex / OpenCode |
| MCP 統合 | なし | 6 MCP tools (tribal serve) |
| path 検証 | なし | `validate_context_path` で traversal block |
| URL 検証 | なし (未使用) | graphify 相当の SSRF 対策 |
| CLAUDE.md 統合 | 手動 | `tribal install` が自動追記 (dedup 付き) |

---

## 残された課題 (Phase 7 で対応)

1. **serve.py の base traversal**: `--base ../../etc` 指定時の検証が弱い (現状 resolve のみ)。
   Phase 7 で `validate_context_path` を CLI 入口に入れる
2. **.claude/scripts と tribal/ の二重メンテ**: 今は両方にコピー。Phase 7 で sync 方針確定
   (symlink / shim / 片方に統一)
3. **Codex / OpenCode の実機動作検証**: baseline-target は Claude Code 想定なので未検証

---

## 計画書 (`tribal-improvement-plan.md`) 期待効果との照合

| 計画書 指標 | Phase 6 到達 |
|---|---|
| MCP server で他 platform に routing 公開 | ✅ 6 tools 実装 + mcp 起動動作確認 |
| 3 platform 配布 | ✅ Claude/Codex/OpenCode の installer 動作 |
| path traversal 防御 | ✅ validate_context_path で block、T5 で検証 |
| 全 scripts を Python パッケージ化 | ✅ tribal/ 配下 8 modules |

---

## 次のステップ: Phase 7 (統合 E2E + リリース)

- baseline-target 上で `/tribal-init` を実機 Claude Code で完走させ、6 定量指標を計測
- Phase 1-6 の相互作用検証 (部分 rollback テスト)
- `README.md` / `CHANGELOG.md` / `docs/MIGRATION_v1_to_v2.md` / `docs/ARCHITECTURE.md` 整備
- v2.0.0-rc1 → v2.0.0 昇格検討
- PyPI 公開準備 (任意)

⚠️ Phase 7 は **実 LLM 実行が中心** のため、現セッションでの E2E は再帰問題で不可。
別セッションでの `/tribal-init` 実行結果を `docs/tribal-v2-migration-baseline.md` に
追記する形で baseline vs v2 比較を完成させる。
