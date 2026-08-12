#!/usr/bin/env python3
"""Audit and plan Kotlin dependency-injection module boundaries."""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

_PACK_ROOT = Path(__file__).resolve().parents[2]
if str(_PACK_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACK_ROOT))

from common.repository_evidence import (  # type: ignore
    artifact,
    layer_of,
    load_json,
    read_kotlin_sources,
    strip_source_text,
    write_json,
)

SKILL = "modularize-kotlin-dependency-injection"
SCRIPT = "analyze_di.py"

FRAMEWORK_IMPORTS = {
    "metro": ("dev.zacsweers.metro",),
    "dagger-hilt": ("dagger.", "dagger.hilt"),
    "koin": ("org.koin.",),
}
FRAMEWORK_TEXT = {
    "metro": ("@DependencyGraph", "@ContributesBinding", "@BindingContainer"),
    "dagger-hilt": ("@Component", "@Subcomponent", "@HiltAndroidApp", "@AndroidEntryPoint"),
    "koin": ("startKoin", "KoinApplication", "org.koin"),
}
DECLARATION_PATTERNS = {
    "graph": re.compile(r"@(DependencyGraph|Component|Subcomponent|HiltAndroidApp)\b|\bstartKoin\s*\("),
    "binding-container": re.compile(r"@(BindingContainer|Module)\b|\bmodule\s*\{"),
    "binding": re.compile(r"@(ContributesBinding|Binds)\b|\bbind(?:s)?\s*\("),
    "provider": re.compile(r"@(Provides|BindsInstance)\b|\bprovide[A-Z]\w*\s*\("),
    "multibinding": re.compile(r"@(IntoSet|IntoMap|ContributesIntoSet|ContributesIntoMap)\b"),
    "scope": re.compile(r"@(SingleIn|Singleton|Scope|Reusable)\b"),
    "assisted": re.compile(r"@(Assisted|AssistedInject|AssistedFactory)\b"),
    "injection": re.compile(r"@(Inject|AssistedInject)\b"),
}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="command", required=True)
    audit = subparsers.add_parser("audit")
    audit.add_argument("--root", type=Path, default=Path.cwd())
    audit.add_argument("--rules", type=Path)
    audit.add_argument("--json-out", type=Path)
    plan = subparsers.add_parser("plan")
    plan.add_argument("--root", type=Path, default=Path.cwd())
    plan.add_argument("--audit", type=Path, required=True)
    plan.add_argument("--rules", type=Path)
    plan.add_argument("--json-out", type=Path)
    return result


def detect_framework(source: dict[str, Any]) -> set[str]:
    imports = source["imports"]
    text = source["code"]
    detected: set[str] = set()
    for framework, prefixes in FRAMEWORK_IMPORTS.items():
        if any(value.startswith(prefixes) for value in imports):
            detected.add(framework)
    for framework, markers in FRAMEWORK_TEXT.items():
        if any(marker in text for marker in markers):
            detected.add(framework)
    return detected


def audit_repository(root: Path, rules: dict[str, Any]) -> dict[str, Any]:
    sources = read_kotlin_sources(root)
    declarations: list[dict[str, Any]] = []
    frameworks: Counter[str] = Counter()
    module_summary: dict[str, Counter[str]] = defaultdict(Counter)
    findings: list[dict[str, Any]] = []
    provider_allowances = rules.get("provider_allowances", [])
    framework_free = set(rules.get("framework_free_layers", []))

    for source in sources:
        detected = detect_framework(source)
        if "test" not in (source.get("source_set") or "").lower():
            for framework in detected:
                frameworks[framework] += 1
        kinds = [kind for kind, pattern in DECLARATION_PATTERNS.items() if pattern.search(source["code"])]
        if not detected and not kinds:
            continue
        record = strip_source_text(source)
        record["frameworks"] = sorted(detected)
        record["declaration_kinds"] = sorted(kinds)
        declarations.append(record)
        module = source["module"] or "<unowned>"
        for kind in kinds:
            module_summary[module][kind] += 1
        layer = layer_of(source["module"])
        if detected and layer in framework_free:
            findings.append({
                "rule": "framework-in-free-layer",
                "severity": "error",
                "path": source["path"],
                "module": source["module"],
                "evidence": f"{layer} declares or imports {', '.join(sorted(detected))} DI APIs",
            })
        if "provider" in kinds and not any(
            re.search(item.get("path_pattern", r"a^"), source["path"])
            for item in provider_allowances
        ):
            findings.append({
                "rule": "provider-review-required",
                "severity": "warning",
                "path": source["path"],
                "module": source["module"],
                "evidence": "Provider/factory boundary requires a recorded reason.",
            })

    active = sorted(frameworks)
    approved = rules.get("approved_framework")
    allowed_mixed = {tuple(sorted(item)) for item in rules.get("allowed_mixed_frameworks", [])}
    if len(active) > 1 and tuple(active) not in allowed_mixed:
        findings.append({
            "rule": "mixed-di-frameworks",
            "severity": "error",
            "frameworks": active,
            "evidence": "Multiple DI frameworks were detected without an approved coexistence rule.",
        })
    if approved and active and approved not in active:
        findings.append({
            "rule": "approved-framework-not-detected",
            "severity": "error",
            "framework": approved,
            "evidence": f"Configured framework {approved!r} was not detected.",
        })

    graph_modules = sorted({item["module"] for item in declarations if "graph" in item["declaration_kinds"] and item["module"]})
    required_graphs = set(rules.get("required_graph_modules", []))
    for missing in sorted(required_graphs - set(graph_modules)):
        findings.append({
            "rule": "required-graph-module-missing",
            "severity": "error",
            "module": missing,
            "evidence": "No graph entry point was detected in the required module.",
        })

    source_sets = {item["source_set"] for item in declarations if item["source_set"]}
    for source_set in rules.get("required_platform_source_sets", []):
        if source_set not in source_sets:
            findings.append({
                "rule": "required-platform-graph-evidence-missing",
                "severity": "warning",
                "source_set": source_set,
                "evidence": "No DI declaration was detected in this required platform source set.",
            })

    unresolved = [finding for finding in findings if finding["severity"] == "error"]
    return artifact(
        root=root,
        skill=SKILL,
        script=SCRIPT,
        inputs={"rules": rules},
        unresolved=unresolved,
        gates={"framework": "fail" if unresolved else "pass"},
        frameworks={key: frameworks[key] for key in sorted(frameworks)},
        declarations=sorted(declarations, key=lambda item: item["path"]),
        modules={key: dict(sorted(value.items())) for key, value in sorted(module_summary.items())},
        findings=sorted(findings, key=lambda item: (item["severity"], item.get("path", ""), item["rule"])),
    )


def plan_migration(root: Path, audit: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    actions: list[dict[str, Any]] = []
    for finding in audit.get("findings", []):
        rule = finding["rule"]
        if rule == "framework-in-free-layer":
            action = "move graph/framework ownership out of the framework-free layer"
        elif rule == "provider-review-required":
            action = "replace with constructor/binding injection or record the required factory reason"
        elif rule == "mixed-di-frameworks":
            action = "approve a temporary coexistence boundary or migrate to the repository framework in a separate batch"
        elif rule.startswith("required-"):
            action = "restore the required graph or platform entry-point registration"
        else:
            action = "review DI ownership"
        actions.append({"finding": finding, "action": action})
    graph_modules = sorted({
        item["module"] for item in audit.get("declarations", [])
        if item.get("module") and "graph" in item.get("declaration_kinds", [])
    })
    verification = [f"compile graph owner and direct consumers for {module}" for module in graph_modules]
    unresolved = list(audit.get("unresolved", []))
    return artifact(
        root=root,
        skill=SKILL,
        script=SCRIPT,
        inputs={"audit": str(rules.get("audit_path", "di-boundary-audit.json")), "rules": rules},
        unresolved=unresolved,
        gates={"plan_ready": "fail" if unresolved else "pass"},
        verification=verification,
        target_framework=rules.get("approved_framework") or next(iter(audit.get("frameworks", {})), None),
        graph_modules=graph_modules,
        actions=actions,
        preserved_contracts=["qualifiers", "scope lifetimes", "multibinding keys", "assisted parameters", "graph entry points"],
    )


def main() -> int:
    args = parser().parse_args()
    root = args.root.resolve()
    rules = load_json(args.rules, {})
    if args.command == "audit":
        payload = audit_repository(root, rules)
    else:
        audit = load_json(args.audit)
        rules = dict(rules)
        rules["audit_path"] = args.audit.as_posix()
        payload = plan_migration(root, audit, rules)
    write_json(args.json_out, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
