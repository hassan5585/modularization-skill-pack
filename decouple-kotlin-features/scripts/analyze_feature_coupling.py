#!/usr/bin/env python3
"""Audit and plan remediation of cross-feature Kotlin dependencies."""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

_PACK_ROOT = Path(__file__).resolve().parents[2]
if str(_PACK_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACK_ROOT))

from common.repository_evidence import (  # type: ignore
    artifact,
    feature_of,
    layer_of,
    load_json,
    module_index,
    read_kotlin_sources,
    write_json,
)

SKILL = "decouple-kotlin-features"
SCRIPT = "analyze_feature_coupling.py"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    audit = subs.add_parser("audit")
    audit.add_argument("--root", type=Path, default=Path.cwd())
    audit.add_argument("--rules", type=Path)
    audit.add_argument("--json-out", type=Path)
    plan = subs.add_parser("plan")
    plan.add_argument("--root", type=Path, default=Path.cwd())
    plan.add_argument("--report", type=Path, required=True)
    plan.add_argument("--json-out", type=Path)
    return parser


def classify(source: str, target: str) -> tuple[str, str, str]:
    source_layer = layer_of(source)
    target_layer = layer_of(target)
    if source_layer == "shared-ui":
        return "shared-ui-cross-feature-dependency", "error", "remove dependency; shared-ui cannot compose other features"
    if target_layer == "test":
        return "production-to-test", "error", "move the dependency to a test configuration or production contract"
    if target_layer == "data":
        return "feature-data-implementation", "error", "depend on the provider domain port, not its data implementation"
    if target_layer == "ui":
        return "feature-ui-implementation", "error", "extract provider-owned shared-ui or compose at the app/consumer UI"
    if target_layer == "shared-ui" and source_layer == "ui":
        return "provider-shared-ui", "info", "retain only when this provider/consumer relationship is reviewed"
    if target_layer == "navigation":
        return "navigation-contract", "warning", "retain when launching the provider-owned flow is intentional"
    if target_layer == "domain":
        return "domain-contract", "warning", "retain only for a stable provider-owned capability"
    return "feature-aggregation", "warning", "replace broad aggregation with the narrow owned contract where practical"


def import_evidence(sources: list[dict[str, Any]], source_module: str, target_module: str) -> list[dict[str, str]]:
    target_packages = sorted({source["package"] for source in sources if source["module"] == target_module and source["package"]})
    result: list[dict[str, str]] = []
    for source in sources:
        if source["module"] != source_module:
            continue
        for imported in source["imports"]:
            if any(imported == package or imported.startswith(package + ".") for package in target_packages):
                result.append({"path": source["path"], "import": imported})
    return sorted(result, key=lambda item: (item["path"], item["import"]))


def audit_edges(root: Path, rules: dict[str, Any]) -> dict[str, Any]:
    modules, _ = module_index(root)
    sources = read_kotlin_sources(root)
    allowances = {
        (item["source"], item["target"]): item.get("reason", "")
        for item in rules.get("allowed_edges", [])
    }
    edges: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for module in modules:
        source = module["path"]
        source_feature = feature_of(source)
        if not source_feature:
            continue
        for target in sorted(module.get("project_dependencies", [])):
            target_feature = feature_of(target)
            if not target_feature or target_feature == source_feature:
                continue
            rule, severity, recommendation = classify(source, target)
            allowance = allowances.get((source, target))
            edge = {
                "source": source,
                "target": target,
                "source_feature": source_feature,
                "target_feature": target_feature,
                "classification": rule,
                "severity": "info" if allowance else severity,
                "recommendation": recommendation,
                "allowed_reason": allowance,
                "import_evidence": import_evidence(sources, source, target),
            }
            edges.append(edge)
            if not allowance and severity in {"error", "warning"}:
                findings.append({
                    "rule": rule,
                    "severity": severity,
                    "source": source,
                    "target": target,
                    "evidence": edge["import_evidence"],
                })

    observed = {(edge["source"], edge["target"]) for edge in edges}
    stale_allowances = [
        {"rule": "stale-edge-allowance", "severity": "warning", "source": source, "target": target}
        for source, target in sorted(set(allowances) - observed)
    ]
    findings.extend(stale_allowances)
    unresolved = [finding for finding in findings if finding["severity"] == "error"]
    return artifact(
        root=root,
        skill=SKILL,
        script=SCRIPT,
        inputs={"rules": rules},
        unresolved=unresolved,
        gates={"forbidden_edges": "fail" if unresolved else "pass"},
        edges=sorted(edges, key=lambda item: (item["source"], item["target"])),
        findings=sorted(findings, key=lambda item: (item["severity"], item["source"], item["target"])),
    )


def plan_edges(root: Path, report: dict[str, Any]) -> dict[str, Any]:
    batches: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in report.get("edges", []):
        if edge.get("allowed_reason"):
            continue
        batches[edge["source_feature"]].append({
            "source": edge["source"],
            "target": edge["target"],
            "strategy": edge["recommendation"],
            "classification": edge["classification"],
        })
    unresolved = list(report.get("unresolved", []))
    return artifact(
        root=root,
        skill=SKILL,
        script=SCRIPT,
        inputs={"report": "feature-coupling-report.json"},
        unresolved=unresolved,
        gates={"review_required": "review" if batches else "pass"},
        verification=["compile both endpoints after each edge cut", "run cycle detection", "run architecture verification"],
        batches=[{"feature": feature, "edges": edges} for feature, edges in sorted(batches.items())],
        preserved_contracts=["product ownership", "route identity", "event semantics", "provider resource ownership"],
    )


def main() -> int:
    args = build_parser().parse_args()
    root = args.root.resolve()
    if args.command == "audit":
        payload = audit_edges(root, load_json(args.rules, {}))
    else:
        payload = plan_edges(root, load_json(args.report))
    write_json(args.json_out, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
