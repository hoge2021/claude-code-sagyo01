# claude-code-sagyo01

Tribal Knowledge Mapper の改善・強化作業リポジトリ。

## 概要

- **ベース**: [Tribal Knowledge Mapper](./tribal/) — Meta engineering blog「How Meta Used AI to Map Tribal Knowledge in Large-Scale Data Pipelines」(2026/04/06) の Claude Code 再現テンプレート
- **目的**: graphify (knowledge graph 構築 skill) の決定論性・計量性を編み込み、tribal の compass + opt-in 哲学を強化する v2.0 の構築

## ディレクトリ構成

```
claude-code-sagyo01/
├── docs/
│   ├── tribal-improvement-plan.md       # 改善計画書
│   ├── tribal-migration-checklist.md    # 移行チェックシート
│   └── phase{0-7}-completion-report.md  # 各 Phase 完了報告
├── tribal/                              # v1 baseline (不変)
├── tribal-v2/                           # ★v2 開発ディレクトリ
│   ├── .claude/                         # ランタイム hook scripts + skills
│   ├── tribal/                          # Python パッケージ (pip install 可)
│   ├── tests/                           # 5 言語 AST fixture
│   └── pyproject.toml                   # PyPI 配布設定
├── baseline-target/                     # graphify 0.4.23 + tribal v1 適用 (比較用)
└── README.md
```

## 使い方 (v2 が動くようになった Phase 6 以降)

```bash
# Python パッケージとして install
cd tribal-v2
pip install -e .

# 対象プロジェクトに展開
cd /path/to/your-project
tribal install --platform claude   # or codex, opencode

# Claude Code で
/tribal-init       # 初回フル構築
/tribal-route <query>  # 関連 context を 3-5 枚動的選定

# MCP server として起動 (他 platform から tribal 知識を共有)
tribal serve --base .claude --mcp
```

## 進捗

| Phase | 内容 | 状態 | commit |
|---|---|---|---|
| 0 | baseline 採取 | ✅ | `ce3153b` |
| 1 | Cache Layer | ✅ | `8c26495` |
| 2 | AST 5 言語 | ✅ | `84db546` |
| 3 | Confidence Label | ✅ | `b705aa1` |
| 4 | Community + GodNode | ✅ | `905efad` |
| 5 | Benchmark + PreToolUse | ✅ | `e4f97de` |
| 6 | MCP + Multi-platform | ✅ | (本 commit) |
| 7 | 統合 E2E + Release | ⏳ | — |

## 注意

- `tribal/` は v1 baseline として不変、改善は `tribal-v2/` 側で進行
- Phase ごとに単体テスト + 動作確認 + ロールバック手順あり (checklist 参照)
- `baseline-target/` は比較測定用、各 Phase で v2 scripts を被せて E2E 検証→ restore
