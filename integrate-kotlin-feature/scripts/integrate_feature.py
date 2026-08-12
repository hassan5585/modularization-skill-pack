#!/usr/bin/env python3
"""Audit, plan, and check Kotlin feature integration surfaces."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

_PACK_ROOT = Path(__file__).resolve().parents[2]
if str(_PACK_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACK_ROOT))

from common.repository_evidence import (  # type: ignore
    artifact,
    feature_of,
    included_modules,
    layer_of,
    load_json,
    module_index,
    read_kotlin_sources,
    write_json,
)

SKILL = "integrate-kotlin-feature"
SCRIPT = "integrate_feature.py"
DI_MARKERS = re.compile(r"@(DependencyGraph|Contributes\w*|BindingContainer|Binds|Provides|Inject)\b|\b(startKoin|module\s*\{)")
NAV_MARKERS = re.compile(r"\b\w*(?:Destination|NavGraph|NavHost|NavDisplay)\b|\b(?:NavKey|composable|navigation)\b")
SERIALIZER_MARKERS = re.compile(r"\b(?:serializer\s*\(|subclass\s*\(|SerializersModule)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("audit", "check"):
        child = subparsers.add_parser(command)
        child.add_argument("--root", type=Path, default=Path.cwd())
        child.add_argument("--feature", required=True)
        child.add_argument("--rules", type=Path)
        child.add_argument("--json-out", type=Path)
    plan = subparsers.add_parser("plan")
    plan.add_argument("--root", type=Path, default=Path.cwd())
    plan.add_argument("--audit", type=Path, required=True)
    plan.add_argument("--rules", type=Path)
    plan.add_argument("--json-out", type=Path)
    return parser


def likely_app_modules(modules: list[dict[str, Any]], feature_modules: set[str], configured: list[str]) -> list[str]:
    if configured:
        return sorted(set(configured))
    consumers = {
        module["path"] for module in modules
        if module["path"] not in feature_modules
        and set(module.get("project_dependencies", [])) & feature_modules
    }
    named = {
        module["path"] for module in modules
        if module["path"].split(":")[-1].lower() in {"app", "androidapp", "composeapp", "desktopapp"}
    }
    return sorted(consumers | named)


def audit_feature(root: Path, feature: str, rules: dict[str, Any]) -> dict[str, Any]:
    modules, _ = module_index(root)
    module_by_path = {module["path"]: module for module in modules}
    configured_modules = set(rules.get("feature_modules", []))
    feature_modules = configured_modules or {module["path"] for module in modules if feature_of(module["path"]) == feature}
    app_modules = likely_app_modules(modules, feature_modules, rules.get("app_modules", []))
    included = included_modules(root)
    sources = read_kotlin_sources(root)
    feature_sources = [source for source in sources if source["module"] in feature_modules]
    app_sources = [source for source in sources if source["module"] in app_modules]

    di_required = bool(rules.get("require_di", any(DI_MARKERS.search(source["code"]) for source in feature_sources)))
    nav_required = bool(rules.get("require_navigation", any(NAV_MARKERS.search(source["code"]) for source in feature_sources)))
    serializer_required = bool(rules.get("require_serializer_registration", False))
    app_dependency_required = bool(rules.get("require_app_dependency", True))

    missing_settings = sorted(feature_modules - included)
    app_edges = sorted(
        (app, target)
        for app in app_modules
        for target in module_by_path.get(app, {}).get("project_dependencies", [])
        if target in feature_modules
    )
    feature_token = feature.lower().replace("-", "")
    di_evidence = sorted(
        source["path"] for source in app_sources
        if feature_token in source["code"].lower().replace("-", "") and DI_MARKERS.search(source["code"])
    )
    navigation_evidence = sorted(
        source["path"] for source in app_sources
        if feature_token in source["code"].lower().replace("-", "") and NAV_MARKERS.search(source["code"])
    )
    serializer_evidence = sorted(
        source["path"] for source in app_sources
        if feature_token in source["code"].lower().replace("-", "") and SERIALIZER_MARKERS.search(source["code"])
    )
    explicit_patterns = rules.get("app_entry_patterns", [])
    missing_patterns = [
        pattern for pattern in explicit_patterns
        if not any(pattern in source["code"] for source in app_sources)
    ]

    required_layers = set(rules.get("required_layers", []))
    actual_layers = {layer_of(module) for module in feature_modules}
    missing_layers = sorted(layer for layer in required_layers if layer not in actual_layers)
    gates = {
        "modules_discovered": "pass" if feature_modules else "fail",
        "required_layers": "pass" if not missing_layers else "fail",
        "settings": "pass" if not missing_settings else "fail",
        "app_dependency": "pass" if (not app_dependency_required or app_edges) else "fail",
        "di": "pass" if (not di_required or di_evidence) else "fail",
        "navigation": "pass" if (not nav_required or navigation_evidence) else "fail",
        "serializer_registration": "pass" if (not serializer_required or serializer_evidence) else "fail",
        "app_entry_patterns": "pass" if not missing_patterns else "fail",
    }
    findings: list[dict[str, Any]] = []
    for gate, status in gates.items():
        if status == "fail":
            findings.append({"rule": f"missing-{gate.replace('_', '-')}", "severity": "error", "feature": feature})
    unresolved = list(findings)
    return artifact(
        root=root,
        skill=SKILL,
        script=SCRIPT,
        inputs={"feature": feature, "rules": rules},
        unresolved=unresolved,
        gates=gates,
        feature=feature,
        feature_modules=sorted(feature_modules),
        app_modules=app_modules,
        evidence={
            "app_project_dependencies": [{"source": source, "target": target} for source, target in app_edges],
            "di_registration": di_evidence,
            "navigation_registration": navigation_evidence,
            "serializer_registration": serializer_evidence,
        },
        missing={
            "settings_modules": missing_settings,
            "required_layers": missing_layers,
            "app_entry_patterns": missing_patterns,
        },
        findings=findings,
    )


def plan_integration(root: Path, audit: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    action_by_gate = {
        "modules_discovered": "correct feature name or explicit feature_modules before editing",
        "required_layers": "create only the reviewed missing feature layers",
        "settings": "register every physical feature module in Gradle settings",
        "app_dependency": "add the established feature aggregation or leaf dependency to the app owner",
        "di": "register bindings/graph contributions using the detected DI framework",
        "navigation": "register the feature graph/destinations in the existing host",
        "serializer_registration": "register each route serializer explicitly without changing serial names",
        "app_entry_patterns": "add the approved app-shell entry-point wiring",
    }
    actions = [
        {"surface": gate, "action": action_by_gate[gate]}
        for gate, status in audit.get("gates", {}).items() if status == "fail"
    ]
    blocking = [item for item in audit.get("unresolved", []) if item.get("rule") == "missing-modules-discovered"]
    return artifact(
        root=root,
        skill=SKILL,
        script=SCRIPT,
        inputs={"feature": audit.get("feature"), "rules": rules},
        unresolved=blocking,
        gates={"plan_ready": "fail" if blocking else "pass"},
        verification=[
            "compile each changed feature module",
            "compile the app and platform graph owners",
            "run verify-kotlin-modules",
        ],
        feature=audit.get("feature"),
        feature_modules=audit.get("feature_modules", []),
        app_modules=audit.get("app_modules", []),
        actions=actions,
        preserved_contracts=["route IDs", "serial names", "deep links", "DI keys and scopes", "app entry behavior"],
    )


def main() -> int:
    args = build_parser().parse_args()
    root = args.root.resolve()
    rules = load_json(args.rules, {})
    if args.command == "plan":
        payload = plan_integration(root, load_json(args.audit), rules)
        exit_code = 0
    else:
        payload = audit_feature(root, args.feature, rules)
        exit_code = 1 if args.command == "check" and "fail" in payload["gates"].values() else 0
    write_json(args.json_out, payload)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
