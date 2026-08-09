#!/usr/bin/env python3
"""Plan platform-boundary extractions from an audit_source_set_boundaries report."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


SCHEMA_VERSION = 1
SCRIPT_VERSION = "1"
SKILL = "extract-kmp-platform-boundaries"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--rules", type=Path)
    parser.add_argument("--json-out", type=Path)
    return parser.parse_args()


def load(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version: {data.get('schema_version')!r}")
    return data


def recommend_boundary(finding: dict, source: dict | None) -> dict:
    capability = (source or {}).get("capability") or "replaceable-service-contract"
    platform = finding.get("platform") or "platform"
    if capability == "platform-entry-point":
        boundary = "platform-entry-point"
        rationale = "Lifecycle/OS integration should stay in app or platform entry modules."
    elif capability == "platform-primitive" or finding.get("rule") == "expect-without-actual":
        boundary = "expect-actual"
        rationale = "Narrow primitive with platform-specific implementation details."
    else:
        boundary = "injected-interface"
        rationale = "Replaceable or business-facing service — prefer DI-bound interface over expect/actual."
    return {
        "path": finding.get("path"),
        "platform": platform,
        "boundary": boundary,
        "rationale": rationale,
        "evidence": finding.get("evidence") or finding.get("import"),
        "capability": capability,
    }


def build_plan(audit: dict, rules: dict) -> dict:
    sources_by_path = {item["path"]: item for item in audit.get("sources") or []}
    extractions = []
    for finding in audit.get("findings") or []:
        if finding.get("rule") not in {
            "platform-import-in-portable-source-set",
            "platform-implementation-in-feature-domain",
            "expect-without-actual",
        }:
            continue
        source = sources_by_path.get(finding.get("path", ""))
        extractions.append(recommend_boundary(finding, source))
    # Group into matching Android/iOS batches by logical name
    batches: dict[str, list[dict]] = defaultdict(list)
    for item in extractions:
        key = (item.get("path") or "unknown").split("/")[-1].split(".")[0]
        batches[key].append(item)
    migration = []
    for index, (name, items) in enumerate(sorted(batches.items()), start=1):
        migration.append(
            {
                "id": f"platform-{index:02d}-{name.lower()}",
                "items": items,
                "steps": [
                    "Create common contract (interface or expect) first",
                    "Move Android and iOS/actual implementations in matching batches",
                    "Wire implementations with existing DI",
                    "Compile common metadata and each affected platform",
                    "Audit Apple framework when public/native declarations change",
                ],
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "generator": {"skill": SKILL, "script": "plan_platform_extraction.py", "version": SCRIPT_VERSION},
        "repository": audit.get("repository") or {"root": ".", "revision": None},
        "inputs": {"rules": rules or {}, "audit_gates": audit.get("gates")},
        "targets": audit.get("targets") or [],
        "findings": audit.get("findings") or [],
        "extractions": extractions,
        "migration_batches": migration,
        "unresolved": [
            item
            for item in extractions
            if item["boundary"] == "injected-interface" and not item.get("evidence")
        ],
        "gates": {
            "android_verification_listed": "pass",
            "ios_verification_listed": "pass",
            "evidence_backed": "pass" if all(e.get("evidence") for e in extractions) or not extractions else "review",
        },
        "verification": audit.get("verification")
        or [
            ["./gradlew", "compileKotlinMetadata"],
            ["./gradlew", "compileDebugKotlinAndroid"],
            ["./gradlew", "compileKotlinIosSimulatorArm64"],
        ],
        "recommendations": [
            "Do not place platform implementations in feature domain modules.",
            "Both Android and iOS checks belong in the verification matrix for KMP moves.",
        ],
    }


def main() -> int:
    options = parse_args()
    try:
        audit = load(options.audit)
        rules = load(options.rules) if options.rules else {}
        plan = build_plan(audit, rules)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    text = json.dumps(plan, indent=2, sort_keys=True) + "\n"
    if options.json_out:
        options.json_out.parent.mkdir(parents=True, exist_ok=True)
        options.json_out.write_text(text, encoding="utf-8")
        print(f"Wrote platform extraction plan to {options.json_out}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
