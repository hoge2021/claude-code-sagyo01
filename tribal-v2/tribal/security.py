"""Tribal v2 — Security helpers (Phase 6).

graphify/security.py を tribal 用に流用 + 改修:
  - URL validation (SSRF / open-redirect 対策)
  - safe_fetch / safe_fetch_text (size cap, redirect re-validation)
  - validate_context_path (graphify-out 相当を .claude/ に)
  - sanitize_label (control char strip + length cap)

tribal の用途は ingest が無いので URL validation の使用頻度は低いが、
将来的な機能追加 (例: fetch external rationale docs) と MCP server の
入力検証に必要。

Phase 0 baseline で発見した graphify v1 の知見:
  - DNS rebinding は防げない (TOCTOU 隙間あり)
  - validate_graph_path は base 不在時に明示エラーで止まる設計
"""

from __future__ import annotations

import html
import ipaddress
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

_ALLOWED_SCHEMES = {"http", "https"}
_MAX_FETCH_BYTES = 52_428_800   # 50 MB hard cap
_MAX_TEXT_BYTES = 10_485_760    # 10 MB hard cap

_BLOCKED_HOSTS = {
    "metadata.google.internal", "metadata.google.com",
    # AWS / Azure metadata also blocked via private IP check
}


# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------

def validate_url(url: str) -> str:
    """http/https のみ許可、private/reserved IP / cloud metadata host を block.

    raises ValueError if blocked.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise ValueError(
            f"Blocked URL scheme '{parsed.scheme}' — only http/https allowed. Got: {url!r}"
        )

    hostname = parsed.hostname
    if hostname:
        if hostname.lower() in _BLOCKED_HOSTS:
            raise ValueError(f"Blocked cloud metadata endpoint '{hostname}'. Got: {url!r}")
        try:
            infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
            for info in infos:
                addr = info[4][0]
                ip = ipaddress.ip_address(addr)
                if ip.is_private or ip.is_reserved or ip.is_loopback or ip.is_link_local:
                    raise ValueError(
                        f"Blocked private/internal IP {addr} (resolved from '{hostname}'). "
                        f"Got: {url!r}"
                    )
        except socket.gaierror:
            pass  # DNS failure surfaces during fetch

    return url


class _NoFileRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Re-validate every redirect target (open-redirect SSRF 対策)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _build_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(_NoFileRedirectHandler)


# ---------------------------------------------------------------------------
# Safe fetch
# ---------------------------------------------------------------------------

def safe_fetch(url: str, max_bytes: int = _MAX_FETCH_BYTES, timeout: int = 30) -> bytes:
    """Fetch URL with size cap + redirect re-validation."""
    validate_url(url)
    opener = _build_opener()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 tribal/2.0"})
    with opener.open(req, timeout=timeout) as resp:
        status = getattr(resp, "status", None) or getattr(resp, "code", None)
        if status is not None and not (200 <= status < 300):
            raise urllib.error.HTTPError(url, status, f"HTTP {status}", {}, None)
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = resp.read(65_536)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise OSError(
                    f"Response from {url!r} exceeds size limit "
                    f"({max_bytes // 1_048_576} MB). Aborting."
                )
            chunks.append(chunk)
    return b"".join(chunks)


def safe_fetch_text(url: str, max_bytes: int = _MAX_TEXT_BYTES, timeout: int = 15) -> str:
    raw = safe_fetch(url, max_bytes=max_bytes, timeout=timeout)
    return raw.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Path validation (Tribal v2: .claude/ 配下に限定)
# ---------------------------------------------------------------------------

def validate_context_path(path: str | Path, base: Path | None = None) -> Path:
    """`.claude/` 配下に解決される path のみ許可 (path traversal 対策)。

    base default は CWD/.claude (graphify の `graphify-out/` 相当)。
    base が存在しない場合は ValueError (cold-start での悪用を防ぐ)。

    Raises:
        ValueError       — path が base を escape、または base が存在しない
        FileNotFoundError — resolved path が存在しない
    """
    if base is None:
        base = Path.cwd() / ".claude"
    base = base.resolve()
    if not base.exists():
        raise ValueError(
            f"Tribal base directory does not exist: {base}. "
            "Run /tribal-init first to initialize."
        )

    resolved = Path(path).resolve()
    try:
        resolved.relative_to(base)
    except ValueError:
        raise ValueError(
            f"Path {path!r} escapes the allowed directory {base}. "
            "Only paths inside .claude/ are permitted."
        )
    if not resolved.exists():
        raise FileNotFoundError(f"Path not found: {resolved}")
    return resolved


# ---------------------------------------------------------------------------
# Label sanitization (XSS / prompt injection 対策)
# ---------------------------------------------------------------------------

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")
_MAX_LABEL_LEN = 256


def sanitize_label(text: str) -> str:
    """Strip control chars, cap length.

    Safe for embedding in JSON. **For HTML output, additional html.escape() needed**
    (graphify v1 知見、Phase 0 baseline で記録済み)。
    """
    text = _CONTROL_CHAR_RE.sub("", text)
    if len(text) > _MAX_LABEL_LEN:
        text = text[:_MAX_LABEL_LEN]
    return text


def sanitize_label_for_html(text: str) -> str:
    """For direct HTML output, combines sanitize_label + html.escape.

    Tribal v2 の MCP serve 出力には sanitize_label が、potential web 経由出力には
    こちらが必要。
    """
    return html.escape(sanitize_label(text))
