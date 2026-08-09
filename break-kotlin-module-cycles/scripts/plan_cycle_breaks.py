#!/usr/bin/env python3
"""Rank reviewed candidate edges to cut for module cycle remediation.

Produces a plan only — never invents or applies architectural abstractions.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


SCHEMA_VERSION = 1
SCRIPT_VERSION = "1"
SKILL = "break-kotlin-module-cycles"

PATTERN_HINTS = (
    ("ui", "data", "dependency-inversion", "UI depending on data often wants a domain port"),
    ("data", "ui", "dependency-inversion", "Data must not depend on UI; invert via domain"),
    ("feature", "feature", "domain-contract-extraction", "Cross-feature cycles need shared contracts or app-shell orchestration"),
    ("navigation", "ui", "navigation-contract", "Keep navigation contracts below UI runtime"),
    ("shared-ui", "shared-ui", "feature-owned-shared-ui", "Never fix cycles with shared-UI chains"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True, help="cycle-report.json from detect_module_cycles.py")
    parser.add_argument("--rules", type=Path, help="Optional cycle-rules JSON")
    parser.add_argument("--json-out", type=Path)
    return parser.parse_args()


def load(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version: {data.get('schema_version')!r}")
    return data


def role(path: str) -> str:
    parts = [p for p in path.split(":") if p]
    return parts[-1].lower() if parts else path


def score_edge(edge: dict, consumer_counts: dict[str, int], component: list[str]) -> dict:
    source = edge["from"]
    target = edge["to"]
    source_role = role(source)
    target_role = role(target)
    score = 0
    reasons = []
    # Prefer cutting edges into unstable / high-level modules
    if source_role in {"ui", "data"} and target_role in {"ui", "data"} and source_role != target_role:
        score += 30
        reasons.append("layer-direction-violation-candidate")
    if source_role == "ui" and target_role == "data":
        score += 20
        reasons.append("ui-to-data")
    if source_role == "data" and target_role == "ui":
        score += 40
        reasons.append("data-to-ui-hard-violation")
    if "shared-ui" in source or "shared-ui" in target:
        if source_role == "shared-ui" and target_role == "shared-ui":
            score -= 100
            reasons.append("reject-shared-ui-chain-fix")
        else:
            score += 10
            reasons.append("involves-shared-ui")
    # Prefer cutting low consumer fan-out of the edge target's reverse
    consumers = consumer_counts.get(target, 0)
    score += max(0, 15 - consumers)
    reasons.append(f"target_consumers={consumers}")
    # Prefer edges with file evidence
    if edge.get("file"):
        score += 5
        reasons.append("has-source-evidence")
    pattern = "dependency-inversion"
    rationale = "Invert the dependency through a stable domain or navigation contract."
    for left, right, name, text in PATTERN_HINTS:
        if left in source_role and right in target_role:
            pattern = name
            rationale = text
            break
    if "core" in source and "core" in target:
        pattern = "domain-contract-extraction"
        rationale = "Split unstable core dumping grounds; do not grow catch-all core."
    return {
        "from": source,
        "to": target,
        "component": component,
        "score": score,
        "pattern": pattern,
        "rationale": rationale,
        "reasons": reasons,
        "evidence": {
            "file": edge.get("file"),
            "import": edge.get("import"),
            "kind": edge.get("kind", "gradle-production"),
        },
        "rejected": score < 0 or pattern == "feature-owned-shared-ui" and "chain" in rationale.lower(),
    }


def plan_breaks(report: dict, rules: dict) -> dict:
    consumer_counts: dict[str, int] = defaultdict(int)
    for source, targets in (report.get("build_graph") or {}).items():
        for target in targets:
            consumer_counts[target] += 1
    candidates = []
    for component in report.get("strongly_connected_components") or []:
        modules = component.get("modules") or []
        edges = component.get("edges") or []
        if not edges:
            # synthesize from build graph
            graph = report.get("build_graph") or {}
            edges = [
                {"from": source, "to": target, "kind": "gradle-production"}
                for source in modules
                for target in graph.get(source, [])
                if target in modules
            ]
        for edge in edges:
            candidates.append(score_edge(edge, consumer_counts, modules))
    # Also consider pure source cycles without gradle cycle
    for component in report.get("source_strongly_connected_components") or []:
        modules = component.get("modules") or []
        build_components = {
            tuple(item.get("modules") or [])
            for item in report.get("strongly_connected_components") or []
        }
        if tuple(modules) in build_components:
            continue
        for edge in component.get("edges") or []:
            scored = score_edge(edge, consumer_counts, modules)
            scored["reasons"].append("source-cycle-without-gradle-cycle")
            candidates.append(scored)
    candidates.sort(key=lambda item: (-item["score"], item["from"], item["to"]))
    # Filter rejected patterns that would create shared-UI chains or core dumps
    rejected = [c for c in candidates if c.get("rejected") or c["pattern"] == "feature-owned-shared-ui" and "chain" in str(c)]
    accepted = [
        c
        for c in candidates
        if not c.get("rejected")
        and c["pattern"] != "feature-owned-shared-ui"
        and "catch-all" not in c["rationale"]
    ]
    # Enforce rule: never recommend shared-ui chains or core dumping grounds
    safe = []
    for item in accepted:
        if item["from"].endswith(":shared-ui") and item["to"].endswith(":shared-ui"):
            rejected.append({**item, "rejected": True, "reasons": item["reasons"] + ["shared-ui-chain"]})
            continue
        if any(token in item["to"].split(":") for token in ("common", "shared", "misc")) and "core" in item["to"]:
            rejected.append({**item, "rejected": True, "reasons": item["reasons"] + ["core-dumping-ground"]})
            continue
        safe.append(item)
    max_candidates = int((rules or {}).get("max_candidates", 20))
    return {
        "schema_version": SCHEMA_VERSION,
        "generator": {"skill": SKILL, "script": "plan_cycle_breaks.py", "version": SCRIPT_VERSION},
        "repository": report.get("repository") or {"root": ".", "revision": None},
        "inputs": {"report_gates": report.get("gates"), "rules": rules or {}},
        "candidate_cuts": safe[:max_candidates],
        "rejected_cuts": rejected[:50],
        "recommended_sequence": [
            {
                "order": index + 1,
                "cut": {
                    "from": item["from"],
                    "to": item["to"],
                },
                "pattern": item["pattern"],
                "steps": [
                    "Review evidence files and ownership",
                    "Apply one edge cut or introduce a reviewed contract",
                    "Compile both modules and dependents",
                    "Remove temporary adapters after consumers migrate",
                    "Re-run detect_module_cycles.py and verify-kotlin-modules",
                ],
            }
            for index, item in enumerate(safe[:5])
        ],
        "unresolved": report.get("unresolved") or [],
        "gates": {
            "has_actionable_cut": "pass" if safe else ("pass" if not (report.get("strongly_connected_components") or report.get("source_strongly_connected_components")) else "fail"),
            "no_shared_ui_chain_recommendation": "pass",
            "no_core_dump_recommendation": "pass",
        },
        "recommendations": [
            "Do not autonomously invent event buses or catch-all modules.",
            "Prefer dependency inversion and domain contracts over new shared layers.",
        ],
    }


def main() -> int:
    options = parse_args()
    try:
        report = load(options.report)
        rules = load(options.rules) if options.rules else {}
        plan = plan_breaks(report, rules)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    text = json.dumps(plan, indent=2, sort_keys=True) + "\n"
    if options.json_out:
        options.json_out.parent.mkdir(parents=True, exist_ok=True)
        options.json_out.write_text(text, encoding="utf-8")
        print(f"Wrote cycle-break plan to {options.json_out}")
    else:
        sys.stdout.write(text)
    return 0 if plan["gates"].get("has_actionable_cut") != "fail" else 1


if __name__ == "__main__":
    raise SystemExit(main())
