#!/usr/bin/env python3
"""Audit, plan, and check evidence-backed Kotlin module consolidation."""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

_PACK_ROOT = Path(__file__).resolve().parents[2]
if str(_PACK_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACK_ROOT))

from common.gradle_graph import build_graph, strongly_connected_components, walk_files  # type: ignore
from common.repository_evidence import (  # type: ignore
    artifact,
    included_modules,
    layer_of,
    load_json,
    module_for,
    module_index,
    read_kotlin_sources,
    relative,
    sha256_file,
    write_json,
)

SKILL = "consolidate-kotlin-modules"
SCRIPT = "consolidate_modules.py"
CONCERN_MARKERS = {
    "di": ("@DependencyGraph", "@Contributes", "@Inject", "startKoin", "@Component"),
    "navigation": ("Destination", "NavKey", "NavGraph", "NavHost", "NavDisplay"),
    "persistence": ("@Database", "@Entity", "@Dao", "SqlDriver", "DataStore<"),
    "serialization": ("@Serializable", "@SerialName", "SerializersModule"),
    "native": ("@HiddenFromObjC", "@ObjCName", "IosAppBridge", "cocoapods."),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    for command in ("audit", "check"):
        child = subs.add_parser(command)
        child.add_argument("--root", type=Path, default=Path.cwd())
        child.add_argument("--spec", type=Path, required=True)
        child.add_argument("--json-out", type=Path)
    plan = subs.add_parser("plan")
    plan.add_argument("--root", type=Path, default=Path.cwd())
    plan.add_argument("--audit", type=Path, required=True)
    plan.add_argument("--spec", type=Path, required=True)
    plan.add_argument("--json-out", type=Path)
    return parser


def simulate_graph(graph: dict[str, list[str]], sources: set[str], target: str) -> dict[str, list[str]]:
    result: dict[str, set[str]] = {}
    for module, dependencies in graph.items():
        if module in sources and module != target:
            continue
        new_module = target if module in sources else module
        result.setdefault(new_module, set())
        for dependency in dependencies:
            replacement = target if dependency in sources else dependency
            if replacement != new_module:
                result[new_module].add(replacement)
    combined_dependencies = set()
    for source in sources:
        for dependency in graph.get(source, []):
            replacement = target if dependency in sources else dependency
            if replacement != target:
                combined_dependencies.add(replacement)
    result.setdefault(target, set()).update(combined_dependencies)
    return {module: sorted(dependencies) for module, dependencies in sorted(result.items())}


def audit_consolidation(root: Path, spec: dict[str, Any]) -> dict[str, Any]:
    modules, directories = module_index(root)
    module_by_path = {module["path"]: module for module in modules}
    sources = set(spec.get("source_modules", []))
    target = spec.get("target_module")
    findings: list[dict[str, Any]] = []
    if len(sources) < 2:
        findings.append({"rule": "at-least-two-source-modules-required", "severity": "error"})
    if target not in sources:
        findings.append({"rule": "target-must-be-one-of-source-modules", "severity": "error", "target": target})
    for missing in sorted(sources - set(module_by_path)):
        findings.append({"rule": "source-module-not-found", "severity": "error", "module": missing})
    if not spec.get("reason") or not spec.get("evidence"):
        findings.append({"rule": "consolidation-evidence-required", "severity": "error"})
    if spec.get("preserve_public_api") is not True:
        findings.append({"rule": "public-api-preservation-required", "severity": "error"})

    graph = build_graph(modules)
    simulated = simulate_graph(graph, sources, target) if target else graph
    cycles = strongly_connected_components(simulated)
    if cycles:
        findings.append({"rule": "consolidation-introduces-cycle", "severity": "error", "cycles": cycles})

    inventories: dict[str, dict[str, Any]] = {}
    for module in sorted(sources):
        build_file = root / module_by_path.get(module, {}).get("build_file", "missing")
        inventories[module] = {
            "build_file": relative(build_file, root) if build_file.is_file() else None,
            "build_file_sha256": sha256_file(build_file) if build_file.is_file() else None,
            "source_files": [],
            "resource_files": [],
            "concerns": Counter(),
        }
    for path in walk_files(root):
        module = module_for(path, directories)
        if module not in inventories:
            continue
        relative_path = relative(path, root)
        bucket = "resource_files" if "composeResources" in path.parts or "res" in path.parts else "source_files"
        inventories[module][bucket].append({"path": relative_path, "sha256": sha256_file(path)})
    for source in read_kotlin_sources(root):
        if source.get("module") not in inventories:
            continue
        for concern, markers in CONCERN_MARKERS.items():
            if any(marker in source["code"] for marker in markers):
                inventories[source["module"]]["concerns"][concern] += 1
    for inventory in inventories.values():
        inventory["source_files"].sort(key=lambda item: item["path"])
        inventory["resource_files"].sort(key=lambda item: item["path"])
        inventory["concerns"] = dict(sorted(inventory["concerns"].items()))

    unresolved = [finding for finding in findings if finding["severity"] == "error"]
    incoming = [
        {"source": module, "target": dependency}
        for module, dependencies in graph.items()
        for dependency in dependencies if dependency in sources and module not in sources
    ]
    return artifact(
        root=root,
        skill=SKILL,
        script=SCRIPT,
        inputs={"spec": spec},
        unresolved=unresolved,
        gates={"evidence": "fail" if any(item["rule"] == "consolidation-evidence-required" for item in unresolved) else "pass", "simulated_graph": "fail" if cycles else "pass"},
        source_modules=sorted(sources),
        target_module=target,
        graph_before=graph,
        graph_after=simulated,
        incoming_edges=incoming,
        inventories=inventories,
        findings=findings,
    )


def plan_consolidation(root: Path, audit: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    unresolved = list(audit.get("unresolved", []))
    target = audit.get("target_module")
    retired = [module for module in audit.get("source_modules", []) if module != target]
    actions = [
        {"order": 1, "action": "compile baseline and capture public/resource/schema snapshots"},
        {"order": 2, "action": "move source sets and resources with expected hashes", "modules": retired},
        {"order": 3, "action": "merge only required Gradle capabilities and dependencies into target", "target": target},
        {"order": 4, "action": "replace incoming project dependencies with target", "edges": audit.get("incoming_edges", [])},
        {"order": 5, "action": "update DI, navigation, serializer, and app registrations"},
        {"order": 6, "action": "remove retired settings entries and empty module directories", "modules": retired},
        {"order": 7, "action": "run final check, architecture verification, and matching build metrics"},
    ]
    return artifact(
        root=root,
        skill=SKILL,
        script=SCRIPT,
        inputs={"spec": spec},
        unresolved=unresolved,
        gates={"plan_ready": "fail" if unresolved else "review"},
        verification=["compile target and all incoming consumers", "run architecture checks", "compare public/resource/schema snapshots", "repeat build metrics"],
        source_modules=audit.get("source_modules", []),
        target_module=target,
        actions=actions,
        inventories=audit.get("inventories", {}),
        expected_graph=audit.get("graph_after", {}),
    )


def check_consolidation(root: Path, spec: dict[str, Any]) -> dict[str, Any]:
    modules, _ = module_index(root)
    present = {module["path"] for module in modules}
    target = spec.get("target_module")
    retired = set(spec.get("source_modules", [])) - {target}
    dangling = [
        {"source": module["path"], "target": dependency}
        for module in modules for dependency in module.get("project_dependencies", [])
        if dependency in retired
    ]
    settings_retired = sorted(retired & included_modules(root))
    findings: list[dict[str, Any]] = []
    for module in sorted(retired & present):
        findings.append({"rule": "retired-module-still-present", "severity": "error", "module": module})
    if target not in present:
        findings.append({"rule": "target-module-missing", "severity": "error", "module": target})
    if dangling:
        findings.append({"rule": "dangling-retired-module-dependency", "severity": "error", "edges": dangling})
    if settings_retired:
        findings.append({"rule": "retired-settings-entry", "severity": "error", "modules": settings_retired})
    return artifact(
        root=root,
        skill=SKILL,
        script=SCRIPT,
        inputs={"spec": spec},
        unresolved=findings,
        gates={"retirement": "fail" if findings else "pass"},
        findings=findings,
        target_module=target,
        retired_modules=sorted(retired),
    )


def main() -> int:
    args = build_parser().parse_args()
    root = args.root.resolve()
    spec = load_json(args.spec)
    if args.command == "audit":
        payload = audit_consolidation(root, spec)
        exit_code = 0
    elif args.command == "plan":
        payload = plan_consolidation(root, load_json(args.audit), spec)
        exit_code = 0
    else:
        payload = check_consolidation(root, spec)
        exit_code = 1 if payload["unresolved"] else 0
    write_json(args.json_out, payload)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
