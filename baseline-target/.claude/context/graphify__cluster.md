# Cluster

> Leiden (graspologic) または Louvain (networkx) でグラフをコミュニティ分割する。

## Quick Commands

```bash
python3 -c "import graphify.cluster; print(graphify.cluster.cluster.__doc__)"
python3 -c "try:\n  import graspologic; print('leiden ok')\nexcept ImportError: print('louvain fallback')"
```

## Key Files

- `graphify/cluster.py` — cluster / cohesion_score / score_all / _split_community

## Non-Obvious Patterns

- **graspologic ANSI が Windows scrollback を破壊**: PowerShell 5.1 で stderr の StringIO 差し替えと _suppress_output() を外すと issue #19 が再発 (`graphify/cluster.py:11-19`)
- **Python 3.13+ で graspologic 不可**: ImportError → 黙って Louvain fallback。品質劣化が surface しにくいので CI で community 数の変化を計測する必要 (`graphify/cluster.py:30-43`)
- **max_level 引数は新版 NetworkX 限定**: inspect.signature で動的に kwargs を組み立てる。依存 pin が緩いと無警告で挙動が変わる (`graphify/cluster.py:46-51`)
- **Leiden は isolate を drop**: 単独 community として別途追加しないと後段の coverage / god_node で「消えたノード」発生 (`graphify/cluster.py:76-91`)

## See Also

- `.claude/context/graphify__build.md` — cluster の入力 NetworkX グラフを構築
- `.claude/context/graphify__analyze.md` — community 結果を god_node 算出で利用
