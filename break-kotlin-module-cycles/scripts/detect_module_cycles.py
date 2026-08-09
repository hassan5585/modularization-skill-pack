#!/usr/bin/env python3
"""Detect Gradle and source-import module cycles with deterministic SCCs.

Read-only analysis. Distinguishes production, test, and source edges.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


SCHEMA_VERSION = 1
SCRIPT_VERSION = "1"
SKILL = "break-kotlin-module-cycles"

# Import shared helpers if pack-local common is available; else inline minimal copies.
_PACK_ROOT = Path(__file__).resolve().parents[2]
if str(_PACK_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACK_ROOT))
try:
    from common.gradle_graph import (  # type: ignore
        DEFAULT_EXCLUDES,
        IMPORT_RE,
        PACKAGE_RE,
        build_graph,
        discover_modules,
        is_excluded,
        source_set_for_path,
        strongly_connected_components,
        walk_files,
    )
except ImportError:  # pragma: no cover - installed skill without common/
    raise SystemExit("error: common.gradle_graph is required; install the full skill pack")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--include-test-edges", action="store_true")
    return parser.parse_args()


def module_dirs(modules: list[dict], root: Path) -> dict[Path, str]:
    mapping: dict[Path, str] = {}
    for module in modules:
        mapping[(root / module["directory"]).resolve()] = module["path"]
    return mapping


def owning_module(path: Path, root: Path, dirs: dict[Path, str]) -> str | None:
    current = path.parent.resolve()
    root = root.resolve()
    while True:
        if current in dirs:
            return dirs[current]
        if current == root or root not in current.parents:
            return None
        current = current.parent


def package_to_modules(root: Path, modules: list[dict]) -> dict[str, set[str]]:
    dirs = module_dirs(modules, root)
    packages: dict[str, set[str]] = defaultdict(set)
    for path in walk_files(root):
        if path.suffix not in {".kt", ".java"}:
            continue
        if any(part in {"generated", "build"} for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        match = PACKAGE_RE.search(text)
        if not match:
            continue
        module = owning_module(path, root, dirs)
        if module:
            packages[match.group(1)].add(module)
    return packages


def source_edges(root: Path, modules: list[dict]) -> list[dict]:
    dirs = module_dirs(modules, root)
    packages = package_to_modules(root, modules)
    edges: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for path in walk_files(root):
        if path.suffix not in {".kt", ".java"}:
            continue
        rel = path.relative_to(root).as_posix()
        if any(part in rel for part in ("/build/", "/generated/", ".modularization/")):
            continue
        source_module = owning_module(path, root, dirs)
        if not source_module:
            continue
        source_set = source_set_for_path(path.relative_to(root))
        text = path.read_text(encoding="utf-8", errors="replace")
        for imported in IMPORT_RE.findall(text):
            cleaned = imported.rstrip(".*")
            # longest package prefix match
            targets: set[str] = set()
            for package, owners in packages.items():
                if cleaned == package or cleaned.startswith(package + "."):
                    targets |= owners
            for target in sorted(targets):
                if target == source_module:
                    continue
                key = (source_module, target, rel)
                if key in seen:
                    continue
                seen.add(key)
                edges.append(
                    {
                        "from": source_module,
                        "to": target,
                        "file": rel,
                        "import": cleaned,
                        "source_set": source_set,
                        "kind": "test" if source_set and "test" in source_set.lower() else "production",
                    }
                )
    return edges


def graph_from_edges(nodes: list[str], edges: list[dict]) -> dict[str, list[str]]:
    graph = {node: [] for node in nodes}
    for edge in edges:
        source = edge["from"]
        target = edge["to"]
        if source in graph and target in graph and target not in graph[source]:
            graph[source].append(target)
    for node in graph:
        graph[node].sort()
    return graph


def scc_payload(components: list[list[str]], edges: list[dict]) -> list[dict]:
    result = []
    for component in components:
        members = set(component)
        internal = [
            edge
            for edge in edges
            if edge["from"] in members and edge["to"] in members
        ]
        result.append(
            {
                "modules": component,
                "size": len(component),
                "edges": internal[:100],
                "edge_count": len(internal),
            }
        )
    return result


def build_report(root: Path, include_test: bool) -> dict:
    modules = discover_modules(root)
    nodes = [module["path"] for module in modules]
    production_graph = build_graph(modules, include_test=False)
    full_graph = build_graph(modules, include_test=True)
    src_edges = source_edges(root, modules)
    prod_src_edges = [e for e in src_edges if e["kind"] == "production"]
    test_src_edges = [e for e in src_edges if e["kind"] == "test"]
    source_graph = graph_from_edges(nodes, prod_src_edges if not include_test else src_edges)
    build_sccs = strongly_connected_components(production_graph)
    source_sccs = strongly_connected_components(source_graph)
    test_graph = build_graph(modules, include_test=True)
    # test-only cycles: present when test edges included but not in production
    test_only_sccs = []
    if include_test:
        full_sccs = strongly_connected_components(test_graph)
        prod_keys = {tuple(c) for c in build_sccs}
        test_only_sccs = [c for c in full_sccs if tuple(c) not in prod_keys]
    return {
        "schema_version": SCHEMA_VERSION,
        "generator": {
            "skill": SKILL,
            "script": "detect_module_cycles.py",
            "version": SCRIPT_VERSION,
        },
        "repository": {"root": ".", "revision": None},
        "inputs": {"include_test_edges": include_test},
        "modules": nodes,
        "build_graph": production_graph,
        "source_graph": source_graph,
        "build_edges": [
            {"from": source, "to": target, "kind": "gradle-production"}
            for source, targets in production_graph.items()
            for target in targets
        ],
        "source_edges": prod_src_edges,
        "test_source_edges": test_src_edges,
        "strongly_connected_components": scc_payload(build_sccs, [
            {"from": s, "to": t} for s, ts in production_graph.items() for t in ts
        ]),
        "source_strongly_connected_components": scc_payload(source_sccs, prod_src_edges),
        "test_only_components": scc_payload(test_only_sccs, [
            {"from": s, "to": t} for s, ts in full_graph.items() for t in ts
        ]) if include_test else [],
        "unresolved": [],
        "gates": {
            "build_cycles": "fail" if build_sccs else "pass",
            "source_cycles": "fail" if source_sccs else "pass",
        },
        "recommendations": [
            "Use plan_cycle_breaks.py to rank candidate cut edges; do not invent abstractions automatically.",
            "Cut one reviewed edge at a time and compile both sides.",
        ],
    }


def main() -> int:
    options = parse_args()
    root = options.root.resolve()
    if not root.is_dir():
        print(f"error: root is not a directory: {root}", file=sys.stderr)
        return 2
    report = build_report(root, options.include_test_edges)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if options.json_out:
        options.json_out.parent.mkdir(parents=True, exist_ok=True)
        options.json_out.write_text(text, encoding="utf-8")
        print(f"Wrote cycle report to {options.json_out}")
    else:
        sys.stdout.write(text)
    if report["gates"]["build_cycles"] == "fail" or report["gates"]["source_cycles"] == "fail":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
