#!/usr/bin/env python3
"""Audit Kotlin test ownership and build a source-set-aware migration plan."""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

_PACK_ROOT = Path(__file__).resolve().parents[2]
if str(_PACK_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACK_ROOT))

from common.repository_evidence import (  # type: ignore
    artifact,
    gradle_task,
    layer_of,
    load_json,
    module_index,
    read_kotlin_sources,
    strip_source_text,
    write_json,
)

SKILL = "migrate-kotlin-tests"
SCRIPT = "plan_test_migration.py"
TEST_SUFFIX_RE = re.compile(r"(?:Test|Tests|Spec|IT)$")
SUPPORT_RE = re.compile(r"(?:^|/)(?:Fake|Fixture|Fixtures|Builder)|\b(?:class|object)\s+(?:Fake\w+|\w+Fixture|\w+Builder)\b")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    audit = subs.add_parser("audit")
    audit.add_argument("--root", type=Path, default=Path.cwd())
    audit.add_argument("--rules", type=Path)
    audit.add_argument("--json-out", type=Path)
    plan = subs.add_parser("plan")
    plan.add_argument("--root", type=Path, default=Path.cwd())
    plan.add_argument("--audit", type=Path, required=True)
    plan.add_argument("--rules", type=Path)
    plan.add_argument("--json-out", type=Path)
    return parser


def is_test_source(source: dict[str, Any]) -> bool:
    source_set = (source.get("source_set") or "").lower()
    return "test" in source_set or layer_of(source.get("module")) == "test"


def subject_names(source: dict[str, Any]) -> set[str]:
    names = {item["name"] for item in source.get("public_declarations", [])}
    names.add(Path(source["path"]).stem)
    return {TEST_SUFFIX_RE.sub("", name) for name in names if name}


def audit_tests(root: Path, rules: dict[str, Any]) -> dict[str, Any]:
    modules, _ = module_index(root)
    sources = read_kotlin_sources(root)
    tests = [source for source in sources if is_test_source(source)]
    production = [source for source in sources if not is_test_source(source)]
    production_index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for source in production:
        for name in subject_names(source):
            production_index[name].append(source)
    matches: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    support: list[dict[str, Any]] = []
    for test in tests:
        candidates: dict[str, dict[str, Any]] = {}
        for name in subject_names(test):
            for candidate in production_index.get(name, []):
                candidates[candidate["path"]] = candidate
        same_package = [candidate for candidate in candidates.values() if candidate.get("package") == test.get("package")]
        selected = same_package if same_package else list(candidates.values())
        matches.append({
            "test": strip_source_text(test),
            "production_candidates": [
                {"path": item["path"], "module": item["module"], "source_set": item["source_set"]}
                for item in sorted(selected, key=lambda value: value["path"])
            ],
        })
        if not selected and not SUPPORT_RE.search(test["path"] + "\n" + test["code"]):
            findings.append({"rule": "unmatched-test-subject", "severity": "warning", "path": test["path"]})
        if SUPPORT_RE.search(test["path"] + "\n" + test["code"]):
            support.append({"path": test["path"], "module": test["module"], "source_set": test["source_set"], "package": test["package"]})

    production_test_edges: list[dict[str, str]] = []
    configured_support = set(rules.get("test_support_modules", []))
    for module in modules:
        for target in module.get("project_dependencies", []):
            if layer_of(module["path"]) != "test" and (layer_of(target) == "test" or target in configured_support):
                production_test_edges.append({"source": module["path"], "target": target})
                findings.append({
                    "rule": "production-to-test-dependency",
                    "severity": "error",
                    "source": module["path"],
                    "target": target,
                })
    unresolved = [finding for finding in findings if finding["severity"] == "error"]
    return artifact(
        root=root,
        skill=SKILL,
        script=SCRIPT,
        inputs={"rules": rules},
        unresolved=unresolved,
        gates={"production_test_edges": "fail" if production_test_edges else "pass"},
        test_sources=[strip_source_text(source) for source in tests],
        production_matches=matches,
        support_candidates=support,
        project_edges=production_test_edges,
        findings=findings,
    )


def target_source_set(production_set: str | None, current: str | None, rules: dict[str, Any]) -> str | None:
    if production_set and production_set in rules.get("source_set_map", {}):
        return rules["source_set_map"][production_set]
    if production_set and production_set.endswith("Main"):
        return production_set[:-4] + "Test"
    return current


def plan_tests(root: Path, audit: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    moves: list[dict[str, Any]] = []
    unresolved = list(audit.get("unresolved", []))
    tasks: set[str] = set()
    for match in audit.get("production_matches", []):
        candidates = match.get("production_candidates", [])
        test = match["test"]
        if len(candidates) != 1:
            if len(candidates) > 1:
                unresolved.append({"rule": "ambiguous-test-subject", "severity": "error", "path": test["path"], "candidates": candidates})
            continue
        production = candidates[0]
        target_set = target_source_set(production.get("source_set"), test.get("source_set"), rules)
        move = {
            "path": test["path"],
            "from_module": test.get("module"),
            "target_module": production.get("module"),
            "target_source_set": target_set,
            "production_path": production["path"],
            "expected_sha256": test["sha256"],
        }
        moves.append(move)
        for template in rules.get("task_templates", {}).get(target_set, []):
            tasks.add(template.format(module=production["module"]))
    return artifact(
        root=root,
        skill=SKILL,
        script=SCRIPT,
        inputs={"rules": rules},
        unresolved=unresolved,
        gates={"plan_ready": "fail" if unresolved else "review"},
        verification=sorted(tasks),
        moves=sorted(moves, key=lambda item: item["path"]),
        support_candidates=audit.get("support_candidates", []),
        production_test_edges=audit.get("project_edges", []),
    )


def main() -> int:
    args = build_parser().parse_args()
    root = args.root.resolve()
    rules = load_json(args.rules, {})
    payload = audit_tests(root, rules) if args.command == "audit" else plan_tests(root, load_json(args.audit), rules)
    write_json(args.json_out, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
