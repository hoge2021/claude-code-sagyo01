# Security

> 外部入力 (URL/path/label) を全て通す validation 集約点。SSRF, traversal, XSS の前線。

## Quick Commands

```bash
python3 -c "from graphify.security import validate_url; validate_url('https://example.com')"
python3 -c "from graphify.security import safe_fetch_text; print(len(safe_fetch_text('https://example.com')))"
python3 -c "from graphify.security import sanitize_label; print(sanitize_label('foo\x00bar'))"
```

## Key Files

- `graphify/security.py` — validate_url / safe_fetch / validate_graph_path / sanitize_label
- `SECURITY.md` — threat model 全体像

## Non-Obvious Patterns

- **Redirect 先の re-validation**: safe_fetch を経由しない urlopen を直接呼ぶと open-redirect SSRF が成立。新 fetch 経路は必ず safe_fetch_text を経由する (`graphify/security.py:67-80`)
- **DNS rebinding の隙間**: validate_url の getaddrinfo 解決と実 fetch の間に時間差があり、後解決が private IP に化けるケースは防げない (`graphify/security.py:50-62`)
- **validate_graph_path が base 存在を要求**: graph 未構築で MCP serve 起動時に「base 不在」エラーで止まる (`graphify/security.py:165-169`)
- **sanitize_label は HTML escape しない**: 名前から「全 sanitize 済み」と誤解しがち。HTML 出力 callsite が html.escape を忘れると XSS 復活 (`graphify/security.py:194-203`)

## See Also

- `.claude/context/graphify__ingest.md` — safe_fetch を URL ingest で使う
- `.claude/context/graphify__serve.md` — validate_graph_path を MCP path 検証で使う
