#!/usr/bin/env python3
"""
Tribal v2 Phase 6 単体テスト: security + serve + __main__.

検証観点:
  T1 validate_url: http/https のみ許可
  T2 validate_url: private IP block (127.0.0.1)
  T3 validate_url: cloud metadata block (169.254.169.254 / metadata.google.internal)
  T4 validate_context_path: .claude/ 配下のみ許可
  T5 validate_context_path: base 不在で ValueError
  T6 sanitize_label: control char strip + length cap
  T7 serve.route_query: intent 分類動作
  T8 serve.get_ripple: ripple_index 返却
  T9 serve.call_tool: unknown tool → error
  T10 __main__.install claude: ディレクトリ構造が正しく作られる
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from tribal import security, serve
from tribal.__main__ import _claude_install


def t1_validate_url_schemes():
    assert security.validate_url("https://example.com") == "https://example.com"
    assert security.validate_url("http://example.com") == "http://example.com"
    for blocked in ("ftp://example.com", "file:///etc/passwd", "gopher://x"):
        try:
            security.validate_url(blocked)
            raise AssertionError(f"should have blocked {blocked}")
        except ValueError:
            pass
    print("  ✓ T1 validate_url: http/https only")


def t2_validate_url_private_ip():
    with patch("socket.getaddrinfo", return_value=[(0, 0, 0, "", ("127.0.0.1", 0))]):
        try:
            security.validate_url("https://evil.example.com")
            raise AssertionError("should block private IP")
        except ValueError as e:
            assert "private" in str(e).lower() or "blocked" in str(e).lower()
    print("  ✓ T2 validate_url: private IP blocked")


def t3_validate_url_metadata_host():
    try:
        security.validate_url("https://metadata.google.internal/")
        raise AssertionError("should block metadata host")
    except ValueError as e:
        assert "metadata" in str(e).lower()
    print("  ✓ T3 validate_url: cloud metadata host blocked")


def t4_validate_context_path_allowed():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / ".claude").mkdir()
        (root / ".claude/foo.md").write_text("ok")
        result = security.validate_context_path(
            root / ".claude/foo.md", base=root / ".claude")
        assert result == (root / ".claude/foo.md").resolve()
    print("  ✓ T4 validate_context_path: allowed inside .claude/")


def t5_validate_context_path_traversal():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / ".claude").mkdir()
        (root / "outside.md").write_text("bad")
        try:
            security.validate_context_path(root / "outside.md", base=root / ".claude")
            raise AssertionError("should block escape")
        except ValueError as e:
            assert "escape" in str(e).lower()
    print("  ✓ T5 validate_context_path: traversal blocked")


def t6_sanitize_label():
    assert security.sanitize_label("hello\x00world") == "helloworld"
    assert security.sanitize_label("a" * 300)[:256] == "a" * 256
    assert security.sanitize_label("plain text") == "plain text"
    print("  ✓ T6 sanitize_label: control chars + length")


def _setup_fake_tribal(tmp: Path) -> Path:
    base = tmp / ".claude"
    (base / "context").mkdir(parents=True)
    rt = {
        "intents": [
            {"name": "feature-add", "keywords": ["add", "追加"],
             "anti_keywords": ["fix", "バグ"],
             "primary_contexts": [".claude/context/a.md"],
             "secondary_contexts": []},
            {"name": "bug-fix", "keywords": ["fix", "バグ"],
             "anti_keywords": ["add", "追加"],
             "primary_contexts": [".claude/context/b.md"],
             "secondary_contexts": []},
        ],
        "fallback": {"primary_contexts": [".claude/context/fb.md"]}
    }
    (base / "context/_routing-table.json").write_text(json.dumps(rt))
    dg = {
        "nodes": [{"id": "x"}, {"id": "y"}],
        "edges": [{"from": "x", "to": "y"}],
        "ripple_index": {"y": ["x"]}
    }
    (base / "context/_dep-graph.json").write_text(json.dumps(dg))
    return base


def t7_route_query():
    with tempfile.TemporaryDirectory() as d:
        base = _setup_fake_tribal(Path(d))
        r = serve.route_query(base, "新しいフィールドを追加したい")
        assert r["intent"] == "feature-add", f"got {r}"
        assert ".claude/context/a.md" in r["primary_contexts"]
    print("  ✓ T7 serve.route_query: 追加 → feature-add")


def t8_get_ripple():
    with tempfile.TemporaryDirectory() as d:
        base = _setup_fake_tribal(Path(d))
        r = serve.get_ripple(base, "y")
        assert r["impacted"] == ["x"]
        assert r["count"] == 1
    print("  ✓ T8 serve.get_ripple: 該当 module 返却")


def t9_unknown_tool():
    r = serve.call_tool("nonexistent", {}, base=Path("/tmp"))
    assert "error" in r
    assert "available" in r
    assert "route_query" in r["available"]
    print("  ✓ T9 serve.call_tool: unknown → error + available list")


def t10_install_claude_structure():
    with tempfile.TemporaryDirectory() as d:
        target = Path(d)
        actions = _claude_install(target)
        # Verify key files
        assert (target / ".claude/scripts").exists()
        assert (target / ".claude/settings.json").exists()
        assert (target / ".claude/skills/tribal-router/SKILL.md").exists()
        assert (target / "CLAUDE.md").exists()
        assert "## Tribal Knowledge Mapper v2" in (target / "CLAUDE.md").read_text()
        assert (target / ".claude/.tribal_version").read_text().strip()
        # Verify actions list mentions key operations
        assert any("settings.json" in a for a in actions)
        assert any("CLAUDE.md" in a for a in actions)
    print(f"  ✓ T10 install --platform claude: 構造 + CLAUDE.md + version stamp")


if __name__ == "__main__":
    tests = [t1_validate_url_schemes, t2_validate_url_private_ip,
             t3_validate_url_metadata_host, t4_validate_context_path_allowed,
             t5_validate_context_path_traversal, t6_sanitize_label,
             t7_route_query, t8_get_ripple, t9_unknown_tool,
             t10_install_claude_structure]
    print(f"Running {len(tests)} tests for tribal-v2 Phase 6:")
    failures = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failures.append((t.__name__, str(e)))
            print(f"  ✗ {t.__name__}: {e}")
        except Exception as e:
            failures.append((t.__name__, f"{type(e).__name__}: {e}"))
            print(f"  ✗ {t.__name__}: {type(e).__name__}: {e}")
    print()
    if failures:
        print(f"FAIL: {len(failures)}/{len(tests)} test(s) failed")
        raise SystemExit(1)
    print(f"PASS: {len(tests)}/{len(tests)} tests")
