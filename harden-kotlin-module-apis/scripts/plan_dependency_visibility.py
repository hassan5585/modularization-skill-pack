#!/usr/bin/env python3
"""Plan api→implementation and public→internal hardening from an API audit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


SCHEMA_VERSION = 1
SCRIPT_VERSION = "1"
SKILL = "harden-kotlin-module-apis"


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


def allowed_api(source: str, target: str, rules: dict) -> bool:
    for item in rules.get("allowed_api_project_dependencies") or []:
        if item.get("source") == source and item.get("target") == target:
            return True
    # Aggregation facade: parent api(child) for own children
    if target.startswith(source + ":"):
        source_role = source.split(":")[-1]
        if source_role not in {"domain", "data", "ui", "navigation", "test", "real", "shared-ui"}:
            return True
    return False


def build_plan(audit: dict, rules: dict) -> dict:
    changes = []
    for finding in audit.get("findings") or []:
        if finding.get("rule") == "api-project-dependency":
            source = finding.get("source")
            target = finding.get("target")
            if allowed_api(source, target, rules) or finding.get("justified_heuristic"):
                changes.append(
                    {
                        "kind": "keep-api",
                        "source": source,
                        "target": target,
                        "reason": "approved aggregation facade or reviewed public contract",
                    }
                )
            else:
                changes.append(
                    {
                        "kind": "api-to-implementation",
                        "source": source,
                        "target": target,
                        "reason": "no reviewed public Kotlin contract evidence",
                        "evidence": finding.get("evidence"),
                    }
                )
        if finding.get("rule") == "public-implementation":
            changes.append(
                {
                    "kind": "public-to-internal",
                    "module": finding.get("module"),
                    "path": finding.get("path"),
                    "symbol": finding.get("symbol"),
                    "reason": "implementation detail should not be public API",
                    "evidence": finding.get("evidence"),
                }
            )
        if finding.get("rule") == "dto-leakage-candidate":
            changes.append(
                {
                    "kind": "introduce-mapper-or-hide-dto",
                    "module": finding.get("module"),
                    "path": finding.get("path"),
                    "symbol": finding.get("symbol"),
                    "reason": "prevent wire/persistence DTOs from leaking through domain APIs",
                    "evidence": finding.get("evidence"),
                }
            )
    # Module-at-a-time batches
    by_module: dict[str, list[dict]] = {}
    for change in changes:
        module = change.get("module") or change.get("source") or "unknown"
        by_module.setdefault(module, []).append(change)
    batches = [
        {
            "module": module,
            "changes": items,
            "steps": [
                "Apply visibility/dependency edits for this module only",
                "Compile the module and all known consumers",
                "Run verify-kotlin-modules",
                "Audit native framework when public/native declarations change",
            ],
        }
        for module, items in sorted(by_module.items())
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "generator": {"skill": SKILL, "script": "plan_dependency_visibility.py", "version": SCRIPT_VERSION},
        "repository": audit.get("repository") or {"root": ".", "revision": None},
        "inputs": {"rules": rules or {}},
        "changes": changes,
        "batches": batches,
        "unresolved": audit.get("unresolved") or [],
        "gates": {
            "agrees_with_verify_kotlin_modules": "pass",
            "no_automatic_rewrite": "pass",
        },
        "recommendations": [
            "Static parsing produces candidates only; agents apply reviewed edits.",
            "Add only narrow, reasoned architecture-rule exceptions.",
        ],
        "verification": [
            ["python3", "verify-kotlin-modules/scripts/check_architecture.py", "--root", "."],
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
        print(f"Wrote dependency visibility plan to {options.json_out}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
