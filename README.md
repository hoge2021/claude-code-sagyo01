# claude-code-sagyo01

Tribal Knowledge Mapper の改善・強化作業リポジトリ。

## 概要

- **ベース**: [Tribal Knowledge Mapper](./tribal/) — Meta engineering blog「How Meta Used AI to Map Tribal Knowledge in Large-Scale Data Pipelines」(2026/04/06) の Claude Code 再現テンプレート
- **目的**: graphify (knowledge graph 構築 skill) の決定論性・計量性を編み込み、tribal の compass + opt-in 哲学を強化する v2.0 の構築

## ディレクトリ構成

```
claude-code-sagyo01/
├── docs/
│   ├── tribal-improvement-plan.md       # 改善計画書（What / Why）
│   └── tribal-migration-checklist.md    # 移行チェックシート（How / 実行順）
├── tribal/                              # ★ベースとなる v1 実装（変更しない）
│   ├── .claude/                         # subagents, skills, scripts, schemas
│   ├── CLAUDE.md
│   └── README.md
└── README.md
```

## 進め方

`docs/tribal-migration-checklist.md` の Phase 0 → Phase 7 を順次実行する。

| Phase | 内容 |
|---|---|
| 0 | 準備・baseline 採取 |
| 1 | Cache Layer 単独導入 |
| 2 | AST 第1パス |
| 3 | Confidence Label 必須化 |
| 4 | Community + GodNode |
| 5 | Benchmark + PreToolUse Hook |
| 6 | MCP Server + Multi-Platform |
| 7 | 統合 E2E + リリース |

各 Phase は独立した作業単位として完結し、末尾の動作確認を満たしてから次に進む。

## 注意

- `tribal/` ディレクトリは v1 baseline として保全。改善作業は別ディレクトリで進行する想定（Phase 1 開始時に方針確定）
- Phase ごとに動作テスト・ロールバック手順をチェックシートに従って実施
