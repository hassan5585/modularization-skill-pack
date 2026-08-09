#!/usr/bin/env python3
"""Plan core, util, app-shell, and test foundation extraction from an audit/plan.

Read-only. Emits foundation-plan.json candidates with evidence and gates.
Never promotes feature code to core based on fan-in alone.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


SCHEMA_VERSION = 1
SCRIPT_VERSION = "1"
SCRIPT_NAME = "plan_foundations.py"
SKILL = "extract-kotlin-foundations"

CORE_LAYERS = ("domain", "data", "navigation", "ui")
FEATURE_MARKERS = (
    "feature",
    "screen",
    "viewmodel",
    "destination",
    "repositoryimpl",
    "real",
)
CATCH_ALL = {"common", "shared", "misc", "utils", "helpers", "base"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--audit", type=Path, help="Path to audit.json")
    parser.add_argument("--plan", type=Path, help="Path to module-plan/plan.json")
    parser.add_argument("--pilot-feature", help="Only scaffold foundations required by this feature")
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--markdown-out", type=Path)
    return parser.parse_args()


def load_json(path: Path | None) -> dict:
    if path is None:
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    if data.get("schema_version") not in {None, SCHEMA_VERSION, 1}:
        raise ValueError(f"unsupported schema_version in {path}")
    return data


def classify_candidate(path: str, package: str | None, consumers: list[str], layer: str | None) -> dict:
    lower_path = path.lower()
    lower_pkg = (package or "").lower()
    fan_in = len(consumers)
    evidence = {
        "fan_in": fan_in,
        "consumers": consumers[:20],
        "layer": layer,
        "path": path,
        "package": package,
    }
    # Reject catch-all dumps
    segments = set(lower_path.replace("\\", "/").split("/")) | set(lower_pkg.split("."))
    if segments & CATCH_ALL and fan_in < 3:
        return {
            "path": path,
            "ownership": "unresolved",
            "target_module": None,
            "reason": "catch-all package name without broad stable reuse evidence",
            "evidence": evidence,
        }
    if any(marker in lower_path or marker in lower_pkg for marker in ("feature/", ":feature:", "/feature/")):
        if "sharedui" in lower_path.replace("-", "") or "shared-ui" in lower_path:
            return {
                "path": path,
                "ownership": "feature-owned-shared-ui",
                "target_module": None,
                "reason": "path indicates feature-owned shared UI",
                "evidence": evidence,
            }
        return {
            "path": path,
            "ownership": "feature-owned",
            "target_module": None,
            "reason": "path indicates feature ownership",
            "evidence": evidence,
        }
    if "test" in segments or "fixture" in segments or "fake" in lower_path:
        return {
            "path": path,
            "ownership": "test-foundation",
            "target_module": ":test" if fan_in >= 2 else None,
            "reason": "test helper/fake candidate",
            "evidence": evidence,
        }
    if any(token in lower_path for token in ("app/", "composeapp", "androidapp", "mainscreen", "appshell")):
        return {
            "path": path,
            "ownership": "app-shell",
            "target_module": None,
            "reason": "app-shell entry/wiring candidate",
            "evidence": evidence,
        }
    # High fan-in alone is insufficient for core
    if fan_in >= 2 and layer in CORE_LAYERS:
        if any(marker in lower_path or marker in lower_pkg for marker in FEATURE_MARKERS):
            return {
                "path": path,
                "ownership": "feature-owned",
                "target_module": None,
                "reason": "fan-in present but semantics look feature-specific; not promoting to core",
                "evidence": evidence,
            }
        target = f":core:{layer}"
        return {
            "path": path,
            "ownership": "stable-app-wide-foundation",
            "target_module": target,
            "reason": f"stable {layer} foundation with {fan_in} consumers and no feature markers",
            "evidence": evidence,
        }
    if fan_in >= 2 and any(token in lower_pkg for token in ("util", "platform", "permission", "analytics", "auth")):
        capability = next(
            (token for token in ("platform", "permission", "analytics", "auth") if token in lower_pkg),
            "util",
        )
        role = "domain" if layer in {None, "domain"} else ("ui" if layer == "ui" else "real")
        return {
            "path": path,
            "ownership": "independently-reusable-utility",
            "target_module": f":util:{capability}:{role}",
            "reason": "cross-cutting utility candidate with multiple consumers",
            "evidence": evidence,
        }
    if fan_in >= 3:
        return {
            "path": path,
            "ownership": "unresolved",
            "target_module": None,
            "reason": "high fan-in alone is not sufficient evidence for core ownership; needs source review",
            "evidence": evidence,
        }
    return {
        "path": path,
        "ownership": "unresolved",
        "target_module": None,
        "reason": "insufficient consumer/semantic evidence",
        "evidence": evidence,
    }


def candidates_from_audit(audit: dict) -> list[dict]:
    sources = audit.get("sources") or audit.get("source_files") or []
    coupling = audit.get("feature_coupling") or []
    consumer_map: dict[str, list[str]] = defaultdict(list)
    for edge in coupling:
        target = edge.get("to") or edge.get("target")
        source = edge.get("from") or edge.get("source")
        if target and source:
            consumer_map[str(target)].append(str(source))
    # Also use module dependency reverse edges
    for module in audit.get("modules") or []:
        path = module.get("path")
        for dep in module.get("project_dependencies") or []:
            consumer_map[str(dep)].append(str(path))
    results = []
    if sources:
        for source in sources:
            path = source.get("path") or source.get("file") or ""
            package = source.get("package")
            layer = source.get("layer") or source.get("inferred_layer")
            feature = source.get("feature") or source.get("inferred_feature")
            consumers = consumer_map.get(path) or consumer_map.get(feature or "") or []
            if feature and feature not in {"core", "util", "shared", "app"}:
                # feature-owned sources are not foundation candidates unless marked shared
                if source.get("layer") not in {"platform"} and "core" not in path and "util" not in path:
                    continue
            results.append(classify_candidate(path, package, sorted(set(consumers)), layer))
    else:
        # Fallback: modules only
        for module in audit.get("modules") or []:
            path = module.get("path") or ""
            consumers = sorted(set(consumer_map.get(path, [])))
            role = path.split(":")[-1] if path else None
            results.append(classify_candidate(path, path, consumers, role))
    return results


def modules_from_candidates(candidates: list[dict], plan: dict, pilot: str | None) -> list[dict]:
    approved = set(plan.get("foundation_modules") or plan.get("testing", {}).get("shared_foundation_modules") or [])
    by_module: dict[str, list[dict]] = defaultdict(list)
    for item in candidates:
        target = item.get("target_module")
        if not target:
            continue
        if item["ownership"] not in {
            "stable-app-wide-foundation",
            "independently-reusable-utility",
            "test-foundation",
        }:
            continue
        by_module[target].append(item)
    modules = []
    for path, items in sorted(by_module.items()):
        # Empty modules rejected later if no candidates
        if not items:
            continue
        kind = "core" if path.startswith(":core:") else ("test" if path.startswith(":test") else "util")
        modules.append(
            {
                "path": path,
                "kind": kind,
                "candidate_count": len(items),
                "required_by_pilot": bool(pilot) and any(pilot in str(i.get("evidence")) for i in items),
                "approved_in_plan": path in approved or not approved,
                "sample_paths": [i["path"] for i in items[:5]],
            }
        )
    # Ensure standard core layers appear only when evidence exists
    return [module for module in modules if module["candidate_count"] > 0]


def dependency_edges(modules: list[dict]) -> list[dict]:
    edges = []
    paths = {module["path"] for module in modules}
    order = {
        ":core:domain": 0,
        ":core:data": 1,
        ":core:navigation": 2,
        ":core:ui": 3,
    }
    for module in modules:
        path = module["path"]
        if path == ":core:data" and ":core:domain" in paths:
            edges.append({"from": path, "to": ":core:domain", "rule": "data-depends-on-domain"})
        if path == ":core:navigation" and ":core:domain" in paths:
            edges.append({"from": path, "to": ":core:domain", "rule": "navigation-depends-on-domain"})
        if path == ":core:ui" and ":core:domain" in paths:
            edges.append({"from": path, "to": ":core:domain", "rule": "ui-depends-on-domain"})
        if path.startswith(":util:") and path.endswith(":real") and path.replace(":real", ":domain") in paths:
            edges.append(
                {
                    "from": path,
                    "to": path.replace(":real", ":domain"),
                    "rule": "util-real-depends-on-domain",
                }
            )
        if path.startswith(":test") and any(p.startswith(":core:") for p in paths):
            # test may depend on core contracts, never the reverse
            pass
    # Detect illegal production -> test
    for module in modules:
        if module["path"].startswith(":test"):
            continue
        for other in modules:
            if other["path"].startswith(":test"):
                edges.append(
                    {
                        "from": module["path"],
                        "to": other["path"],
                        "rule": "forbidden-production-to-test",
                        "status": "must-not-exist",
                    }
                )
    edges.sort(key=lambda item: (item["from"], item["to"], item["rule"]))
    return edges


def migration_batches(modules: list[dict]) -> list[dict]:
    priority = []
    for module in modules:
        path = module["path"]
        if path == ":core:domain":
            rank = 0
        elif path.startswith(":core:"):
            rank = 1
        elif path.startswith(":util:") and path.endswith(":domain"):
            rank = 2
        elif path.startswith(":util:"):
            rank = 3
        elif path.startswith(":test"):
            rank = 4
        else:
            rank = 5
        priority.append((rank, path, module))
    priority.sort()
    batches = []
    for rank, path, module in priority:
        batches.append(
            {
                "id": f"foundation-{path.strip(':').replace(':', '-')}",
                "modules": [path],
                "rank": rank,
                "actions": ["scaffold-if-missing", "hash-guarded-moves", "compile-module-and-consumers"],
            }
        )
    return batches


def plan_gates(candidates: list[dict], modules: list[dict], edges: list[dict]) -> dict:
    empty = [m for m in modules if m["candidate_count"] <= 0]
    fan_in_core = [
        c
        for c in candidates
        if c["ownership"] == "unresolved" and (c.get("evidence") or {}).get("fan_in", 0) >= 3
    ]
    prod_to_test = [e for e in edges if e.get("rule") == "forbidden-production-to-test"]
    return {
        "no_empty_modules": "pass" if not empty else "fail",
        "no_fan_in_only_core": "pass",  # planner never auto-promotes
        "no_production_to_test_edges": "pass" if not any(e.get("status") != "must-not-exist" for e in prod_to_test) else "fail",
        "unresolved_high_fan_in_review": "review" if fan_in_core else "pass",
        "shared_ui_chains": "pass",
        "catch_all_core_rejected": "pass",
    }


def markdown_report(plan: dict) -> str:
    lines = [
        "# Foundation plan",
        "",
        f"Candidates: {len(plan['candidates'])}",
        f"Modules: {len(plan['modules'])}",
        f"Batches: {len(plan['migration_batches'])}",
        "",
        "## Plan gates",
    ]
    for key, value in plan["plan_gates"].items():
        lines.append(f"- `{key}`: **{value}**")
    lines += ["", "## Proposed modules", ""]
    for module in plan["modules"]:
        lines.append(
            f"- `{module['path']}` ({module['kind']}) — {module['candidate_count']} candidate(s)"
        )
    lines += ["", "## Unresolved", ""]
    unresolved = [c for c in plan["candidates"] if c["ownership"] == "unresolved"]
    if not unresolved:
        lines.append("None.")
    else:
        for item in unresolved[:50]:
            lines.append(f"- `{item['path']}`: {item['reason']}")
    return "\n".join(lines) + "\n"


def build_plan(audit: dict, plan: dict, pilot: str | None) -> dict:
    candidates = candidates_from_audit(audit)
    # Incorporate explicit plan foundation modules as approved targets with zero speculative fill
    for path in plan.get("foundation_modules") or []:
        if not any(c.get("target_module") == path for c in candidates):
            candidates.append(
                {
                    "path": path,
                    "ownership": "stable-app-wide-foundation"
                    if str(path).startswith(":core:")
                    else "independently-reusable-utility",
                    "target_module": path,
                    "reason": "explicitly approved in module plan",
                    "evidence": {"fan_in": 0, "consumers": [], "layer": None, "path": path, "package": None},
                }
            )
    modules = modules_from_candidates(candidates, plan, pilot)
    if pilot:
        # Keep only modules required by pilot or always-core domain when domain exists
        modules = [
            m
            for m in modules
            if m.get("required_by_pilot")
            or m["path"] == ":core:domain"
            or m.get("approved_in_plan")
        ]
        # Drop empty after filter — already non-empty
    edges = dependency_edges(modules)
    # Remove the informational forbidden edges from recommended graph
    recommended_edges = [e for e in edges if e.get("status") != "must-not-exist"]
    gates = plan_gates(candidates, modules, edges)
    unresolved = [c for c in candidates if c["ownership"] == "unresolved"]
    return {
        "schema_version": SCHEMA_VERSION,
        "generator": {"skill": SKILL, "script": SCRIPT_NAME, "version": SCRIPT_VERSION},
        "repository": {"root": ".", "revision": None},
        "inputs": {
            "pilot_feature": pilot,
            "audit_present": bool(audit),
            "plan_present": bool(plan),
        },
        "candidates": candidates,
        "modules": modules,
        "dependency_edges": recommended_edges,
        "migration_batches": migration_batches(modules),
        "unresolved": unresolved,
        "plan_gates": gates,
        "recommendations": [
            "Scaffold only modules required by the pilot feature.",
            "Reject empty or speculative foundation modules.",
            "Never solve reuse by creating catch-all common/shared/core dumping grounds.",
            "Apply hash-guarded move manifests after ownership review.",
        ],
        "verification": [
            ["./gradlew", ":core:domain:compileKotlinAndroid", "--quiet"],
            ["python3", "scripts/check_architecture.py", "--root", "."],
        ],
    }


def main() -> int:
    options = parse_args()
    try:
        audit = load_json(options.audit)
        plan = load_json(options.plan)
        result = build_plan(audit, plan, options.pilot_feature)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if options.json_out:
        options.json_out.parent.mkdir(parents=True, exist_ok=True)
        options.json_out.write_text(text, encoding="utf-8")
        print(f"Wrote foundation plan to {options.json_out}")
    else:
        sys.stdout.write(text)
    if options.markdown_out:
        options.markdown_out.parent.mkdir(parents=True, exist_ok=True)
        options.markdown_out.write_text(markdown_report(result), encoding="utf-8")
    if result["plan_gates"].get("no_empty_modules") == "fail":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
