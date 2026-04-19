# Cache

> ファイル単位 SHA256 を key にした抽出キャッシュを管理する。

## Quick Commands

```bash
python3 -c "from graphify.cache import file_hash; from pathlib import Path; print(file_hash(Path('graphify/cache.py')))"
python3 -c "from graphify.cache import clear_cache; clear_cache()"
ls graphify-out/cache/ | wc -l
```

## Key Files

- `graphify/cache.py` — file_hash / load_cached / save_cached / check_semantic_cache の本体

## Non-Obvious Patterns

- **Markdown frontmatter は hash 対象外**: `.md` の YAML frontmatter (tags, status 等) を更新しても cache は無効化されない。意味的変更には別 invalidation が必要 (`graphify/cache.py:10-17`)
- **hash key に relative path を混入**: portability 目的で repo 外ファイルは絶対パスにフォールバック。実行 root が変わると cache miss が突然増える (`graphify/cache.py:36-41`)
- **Windows os.replace fallback**: PermissionError (WinError 5) に対し copy + unlink。unlink 失敗時に tmp ファイルが残り得る (`graphify/cache.py:79-89`)

## See Also

- `.claude/context/graphify__extract.md` — cache を主に使う呼び出し元
- `.claude/context/graphify__detect.md` — file 列挙の責務分担
