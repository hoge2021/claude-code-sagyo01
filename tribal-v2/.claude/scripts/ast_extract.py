#!/usr/bin/env python3
"""
Tribal v2 — Deterministic AST extraction (Phase 2a).

graphify/extract.py の LanguageConfig パターンを 5 言語にスリム化して採用。
LLM を使わず tree-sitter で imports / calls / definitions を抽出し、
module-analyst の Q4 (deps) と Q2 (modification_patterns) を決定論で確定させる。

対応言語: python, typescript, go, rust, java
未対応言語は空 JSON を出力 (analyst 側で従来動作にフォールバック)。

Usage:
    python3 ast_extract.py <module-id> <module-path>
    python3 ast_extract.py graphify/cache graphify/cache.py
    python3 ast_extract.py mymod path/to/dir/

cache 連携:
    結果は cache.py 経由で .claude/cache/ast/ に保存される。
    同一 source content + 同一 git HEAD なら 2 回目以降は cache hit。
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# tree-sitter は optional dependency 扱い (未インストール環境では fallback)
try:
    import tree_sitter as ts
    import tree_sitter_python as tspy
    import tree_sitter_typescript as tsts
    import tree_sitter_go as tsgo
    import tree_sitter_rust as tsrs
    import tree_sitter_java as tsjava
    _TS_AVAILABLE = True
except ImportError:
    _TS_AVAILABLE = False

# v2 cache layer
sys.path.insert(0, str(Path(__file__).parent.resolve()))
try:
    import cache as _v2_cache  # noqa: E402
    _CACHE_AVAILABLE = True
except ImportError:
    _CACHE_AVAILABLE = False


# ---- Language config --------------------------------------------------------

@dataclass
class LangSpec:
    """Per-language AST extraction config (graphify/extract.py に着想)."""
    name: str
    extensions: tuple[str, ...]
    language_fn: Callable | None
    import_node_types: frozenset
    function_node_types: frozenset
    class_node_types: frozenset
    call_node_type: str = "call"
    name_field: str = "name"


def _ts_python_lang():
    return ts.Language(tspy.language()) if _TS_AVAILABLE else None


def _ts_typescript_lang():
    return ts.Language(tsts.language_typescript()) if _TS_AVAILABLE else None


def _ts_go_lang():
    return ts.Language(tsgo.language()) if _TS_AVAILABLE else None


def _ts_rust_lang():
    return ts.Language(tsrs.language()) if _TS_AVAILABLE else None


def _ts_java_lang():
    return ts.Language(tsjava.language()) if _TS_AVAILABLE else None


LANG_SPECS: dict[str, LangSpec] = {
    "python": LangSpec(
        name="python",
        extensions=(".py",),
        language_fn=_ts_python_lang,
        import_node_types=frozenset(["import_statement", "import_from_statement"]),
        function_node_types=frozenset(["function_definition"]),
        class_node_types=frozenset(["class_definition"]),
        call_node_type="call",
    ),
    "typescript": LangSpec(
        name="typescript",
        extensions=(".ts", ".tsx"),
        language_fn=_ts_typescript_lang,
        import_node_types=frozenset(["import_statement"]),
        function_node_types=frozenset(["function_declaration", "method_definition"]),
        class_node_types=frozenset(["class_declaration"]),
        call_node_type="call_expression",
    ),
    "go": LangSpec(
        name="go",
        extensions=(".go",),
        language_fn=_ts_go_lang,
        import_node_types=frozenset(["import_declaration"]),
        function_node_types=frozenset(["function_declaration", "method_declaration"]),
        class_node_types=frozenset(["type_declaration"]),
        call_node_type="call_expression",
    ),
    "rust": LangSpec(
        name="rust",
        extensions=(".rs",),
        language_fn=_ts_rust_lang,
        import_node_types=frozenset(["use_declaration"]),
        function_node_types=frozenset(["function_item"]),
        class_node_types=frozenset(["struct_item", "enum_item", "trait_item", "impl_item"]),
        call_node_type="call_expression",
    ),
    "java": LangSpec(
        name="java",
        extensions=(".java",),
        language_fn=_ts_java_lang,
        import_node_types=frozenset(["import_declaration"]),
        function_node_types=frozenset(["method_declaration", "constructor_declaration"]),
        class_node_types=frozenset(["class_declaration", "interface_declaration"]),
        call_node_type="method_invocation",
    ),
}


def _detect_lang(path: Path) -> LangSpec | None:
    suffix = path.suffix.lower()
    for spec in LANG_SPECS.values():
        if suffix in spec.extensions:
            return spec
    return None


def _read(node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _name_of(node, source: bytes, name_field: str = "name") -> str | None:
    n = node.child_by_field_name(name_field)
    if n is not None:
        return _read(n, source)
    return None


# ---- Walker -----------------------------------------------------------------

def _walk_node(node, source: bytes, file_path: str, spec: LangSpec,
               imports: list, definitions: list, calls: list,
               current_func: str | None = None):
    """Recursive AST walk to collect imports/definitions/calls.

    Each language's structure is similar enough that one walker covers all 5
    via LangSpec dispatch. graphify は言語ごとに完全分離していたが、tribal の
    用途 (Q4 集約) ではこの粗さで十分。
    """
    line = node.start_point[0] + 1

    # Imports
    if node.type in spec.import_node_types:
        text = _read(node, source).replace("\n", " ").strip()
        # Crude target extraction: take last identifier-like token
        target = text
        for kw in ("import ", "from ", "use ", "package "):
            if kw in text:
                rest = text.split(kw, 1)[1].strip()
                # Take first whitespace-delimited token, strip ; { etc.
                target = rest.split()[0].strip(";{},()").rstrip(":")
                break
        imports.append({
            "from_file": file_path,
            "to": target,
            "kind": node.type,
            "raw": text[:120],
            "line": line,
        })

    # Definitions (function/method/class)
    is_function = node.type in spec.function_node_types
    is_class = node.type in spec.class_node_types
    if is_function or is_class:
        nm = _name_of(node, source, spec.name_field)
        if nm:
            definitions.append({
                "kind": "function" if is_function else "class",
                "name": nm,
                "file": file_path,
                "line": line,
            })
            if is_function:
                current_func = nm

    # Calls
    if node.type == spec.call_node_type:
        # function field for python/ts; method_name for java; call_expression varies
        callee_node = node.child_by_field_name("function") or node.child_by_field_name("name")
        if callee_node is not None:
            callee = _read(callee_node, source).strip()
            # Trim arguments / generics
            callee = callee.split("(", 1)[0].split("<", 1)[0].strip()
            if callee and len(callee) <= 200:
                calls.append({
                    "caller": current_func or "<module>",
                    "callee": callee,
                    "line": line,
                })

    for child in node.children:
        _walk_node(child, source, file_path, spec, imports, definitions, calls, current_func)


# ---- File-level extraction --------------------------------------------------

def extract_file(path: Path) -> dict:
    """Parse one source file and return {imports, definitions, calls, lang, loc}."""
    spec = _detect_lang(path)
    if spec is None or not _TS_AVAILABLE or spec.language_fn is None:
        return {
            "path": str(path),
            "lang": "unsupported",
            "loc": _count_loc(path),
            "imports": [], "definitions": [], "calls": [],
        }
    lang = spec.language_fn()
    if lang is None:
        return {
            "path": str(path), "lang": spec.name, "loc": _count_loc(path),
            "imports": [], "definitions": [], "calls": [],
        }
    parser = ts.Parser(lang)
    try:
        source = path.read_bytes()
    except OSError:
        return {"path": str(path), "lang": spec.name, "loc": 0,
                "imports": [], "definitions": [], "calls": []}
    tree = parser.parse(source)
    imports: list = []
    definitions: list = []
    calls: list = []
    _walk_node(tree.root_node, source, str(path), spec, imports, definitions, calls)
    return {
        "path": str(path),
        "lang": spec.name,
        "loc": _count_loc(path),
        "imports": imports,
        "definitions": definitions,
        "calls": calls,
    }


def _count_loc(path: Path) -> int:
    try:
        return sum(1 for _ in path.read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError:
        return 0


def _enumerate_module_files(module_path: Path) -> list[Path]:
    """Mirror cache.py:_module_files but extension-aware for AST-supported langs."""
    ALL_EXT = tuple(ext for s in LANG_SPECS.values() for ext in s.extensions)
    if module_path.is_file():
        return [module_path] if module_path.suffix.lower() in ALL_EXT else []
    if module_path.is_dir():
        excluded = {".git", "__pycache__", "node_modules", "venv", ".venv", "dist", "build"}
        files: list[Path] = []
        for root, dirs, names in os.walk(module_path, followlinks=False):
            dirs[:] = [d for d in dirs if d not in excluded and not d.startswith(".")]
            for n in names:
                p = Path(root) / n
                if p.suffix.lower() in ALL_EXT:
                    files.append(p)
        return sorted(files)
    # Stem fallback
    for ext in ALL_EXT:
        candidate = module_path.with_suffix(ext)
        if candidate.is_file():
            return [candidate]
    return []


# ---- Module-level extraction (cache-aware) ---------------------------------

def extract_module(module_id: str, module_path: str | Path,
                   repo_root: Path = Path("."),
                   use_cache: bool = True) -> dict:
    """Extract AST for a whole module. Returns the analyst-friendly dict.

    Output schema (matches improvement-plan §4.1):
      {
        "module": ...,
        "extracted_at": ISO8601,
        "files": [{path, lang, loc}],
        "imports": [{from_file, to, kind, evidence, line}],
        "calls": [{caller, callee, evidence, confidence, confidence_score}],
        "definitions": [{kind, name, file, line}],
        "stats": {file_count, loc_total, import_count, call_count, def_count, supported_lang_files}
      }
    """
    repo_root = Path(repo_root).resolve()
    mp = Path(module_path)
    if not mp.is_absolute():
        mp = repo_root / mp

    # Cache fast path
    if use_cache and _CACHE_AVAILABLE:
        cached = _v2_cache.load_cached_artifact(module_id, "ast", repo_root=repo_root)
        if cached is not None:
            cached["_cache_hit"] = True
            return cached

    files_meta: list[dict] = []
    all_imports: list = []
    all_calls: list = []
    all_definitions: list = []
    supported = 0

    for f in _enumerate_module_files(mp):
        result = extract_file(f)
        files_meta.append({"path": str(f.relative_to(repo_root)) if f.is_relative_to(repo_root) else str(f),
                           "lang": result["lang"], "loc": result["loc"]})
        if result["lang"] != "unsupported":
            supported += 1
        all_imports.extend(result["imports"])
        all_definitions.extend(result["definitions"])
        all_calls.extend(result["calls"])

    # v2 size optimization: dedupe calls by (caller, callee) pair, keep first line.
    # Raw call list was 30x bloat for analyst's needs. We just need to know
    # "what does this caller invoke" — multiple call sites of the same callee
    # don't add Q4 signal.
    seen_pairs: set = set()
    deduped_calls: list = []
    for c in all_calls:
        key = (c["caller"], c["callee"])
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        deduped_calls.append({
            "caller": c["caller"],
            "callee": c["callee"],
            "evidence": f"L{c['line']}",
            "confidence": "EXTRACTED",
            "confidence_score": 1.0,
        })

    # v2 size optimization: drop verbose `raw` field from imports
    compact_imports = [{k: v for k, v in i.items() if k != "raw"} for i in all_imports]

    payload = {
        "module": module_id,
        "module_path": str(mp.relative_to(repo_root)) if mp.is_relative_to(repo_root) else str(mp),
        "extracted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "files": files_meta,
        "imports": compact_imports,
        "definitions": all_definitions,
        "calls": deduped_calls,
        "stats": {
            "file_count": len(files_meta),
            "loc_total": sum(f["loc"] for f in files_meta),
            "import_count": len(compact_imports),
            "call_count": len(deduped_calls),
            "call_count_raw": len(all_calls),
            "def_count": len(all_definitions),
            "supported_lang_files": supported,
        },
        "_cache_hit": False,
    }

    if use_cache and _CACHE_AVAILABLE and supported > 0:
        _v2_cache.save_cached_artifact(module_id, "ast", payload, repo_root=repo_root)

    return payload


# ---- CLI --------------------------------------------------------------------

def main() -> int:
    if len(sys.argv) < 2:
        print("usage: ast_extract.py <module-id> [module-path]", file=sys.stderr)
        return 2
    module_id = sys.argv[1]
    module_path = sys.argv[2] if len(sys.argv) > 2 else module_id

    if not _TS_AVAILABLE:
        print("warning: tree-sitter not installed, output will be empty", file=sys.stderr)

    result = extract_module(module_id, module_path)

    # If --output is supplied, write to disk (matching skill/agent pattern)
    out_idx = -1
    for i, a in enumerate(sys.argv):
        if a == "--output" and i + 1 < len(sys.argv):
            out_idx = i + 1
    if out_idx > 0:
        out_path = Path(sys.argv[out_idx])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {out_path} ({result['stats']['def_count']} defs, "
              f"{result['stats']['import_count']} imports, {result['stats']['call_count']} calls)")
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
