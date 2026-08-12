#!/usr/bin/env python3
"""Audit and plan Kotlin data-layer ownership moves."""

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
    layer_of,
    load_json,
    read_kotlin_sources,
    strip_source_text,
    write_json,
)

SKILL = "migrate-kotlin-data-boundaries"
SCRIPT = "analyze_data_boundaries.py"
SERIAL_NAME_RE = re.compile(r"@SerialName\(\s*[\"']([^\"']+)[\"']\s*\)")
REPOSITORY_CONTRACT_RE = re.compile(r"\binterface\s+\w*Repository\b")
REPOSITORY_IMPL_RE = re.compile(r"\b(?:class|object)\s+(?:Real\w*Repository|\w*RepositoryImpl)\b")
WIRE_RE = re.compile(r"\b(?:data\s+)?class\s+\w*(?:Request|Response|Dto|DTO)\b")
SERIALIZER_RE = re.compile(r"@Serializable\b|\bKSerializer\s*<|\bSerializersModule\b")
MAPPER_RE = re.compile(r"\bfun\s+\w+\.(?:toDomain|toResponse|toRequest|toDto|toDTO)\s*\(")
NETWORK_RE = re.compile(r"\b(HttpClient|safeCall|Retrofit|Ktor|@GET|@POST|@PUT|@DELETE)\b")
CACHE_RE = re.compile(r"\b(Cache|DataStore|MutableStateFlow|invalidate|timeToLive|TTL)\b")
PERSISTENCE_RE = re.compile(r"@(Database|Entity|Dao|Query|Insert|Update|Delete)\b|\b(SqlDriver|RoomDatabase|DataStore<)")


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


def classifications(text: str) -> list[str]:
    result: list[str] = []
    for name, pattern in (
        ("repository-contract", REPOSITORY_CONTRACT_RE),
        ("repository-implementation", REPOSITORY_IMPL_RE),
        ("wire-dto", WIRE_RE),
        ("serializer", SERIALIZER_RE),
        ("mapper", MAPPER_RE),
        ("network", NETWORK_RE),
        ("cache", CACHE_RE),
        ("persistence", PERSISTENCE_RE),
    ):
        if pattern.search(text):
            result.append(name)
    return result


def allowed_shared(path: str, rules: dict[str, Any]) -> bool:
    return any(re.search(item.get("path_pattern", r"a^"), path) for item in rules.get("shared_model_allowances", []))


def audit_data(root: Path, rules: dict[str, Any]) -> dict[str, Any]:
    components: list[dict[str, Any]] = []
    wire_contracts: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    allowed_data_modules = set(rules.get("allowed_data_modules", []))
    for source in read_kotlin_sources(root):
        kinds = classifications(source["code"])
        if not kinds:
            continue
        record = strip_source_text(source)
        record["classifications"] = kinds
        components.append(record)
        layer = layer_of(source["module"])
        if "repository-contract" in kinds and layer != "domain":
            findings.append({
                "rule": "repository-contract-outside-domain",
                "severity": "warning",
                "path": source["path"],
                "module": source["module"],
            })
        implementation_kinds = {"repository-implementation", "network", "mapper"}
        if implementation_kinds.intersection(kinds) and layer == "domain" and not allowed_shared(source["path"], rules):
            findings.append({
                "rule": "data-implementation-in-domain",
                "severity": "error",
                "path": source["path"],
                "module": source["module"],
                "classifications": kinds,
            })
        if "wire-dto" in kinds and layer == "domain" and not allowed_shared(source["path"], rules):
            findings.append({
                "rule": "wire-dto-in-domain-review",
                "severity": "warning",
                "path": source["path"],
                "module": source["module"],
            })
        if allowed_data_modules and implementation_kinds.intersection(kinds) and source["module"] not in allowed_data_modules and layer != "data":
            findings.append({
                "rule": "data-component-outside-approved-module",
                "severity": "warning",
                "path": source["path"],
                "module": source["module"],
            })
        if "wire-dto" in kinds or ("serializer" in kinds and layer == "data"):
            wire_contracts.append({
                "path": source["path"],
                "module": source["module"],
                "sha256": source["sha256"],
                "serial_names": sorted(set(SERIAL_NAME_RE.findall(source["code"]))),
            })
        if "persistence" in kinds:
            findings.append({
                "rule": "persistence-specialist-review",
                "severity": "info",
                "path": source["path"],
                "module": source["module"],
            })
    unresolved = [finding for finding in findings if finding["severity"] == "error"]
    return artifact(
        root=root,
        skill=SKILL,
        script=SCRIPT,
        inputs={"rules": rules},
        unresolved=unresolved,
        gates={"layering": "fail" if unresolved else "pass"},
        components=sorted(components, key=lambda item: item["path"]),
        wire_contracts=sorted(wire_contracts, key=lambda item: item["path"]),
        findings=sorted(findings, key=lambda item: (item["severity"], item["path"])),
    )


def target_for(component: dict[str, Any], rules: dict[str, Any]) -> str | None:
    kinds = set(component["classifications"])
    if kinds == {"serializer"} and layer_of(component.get("module")) != "data":
        return component.get("module")
    if "repository-contract" in kinds and not kinds.intersection({"network", "wire-dto", "repository-implementation"}):
        return rules.get("target_domain_module")
    if "persistence" in kinds:
        return None
    return rules.get("target_data_module")


def plan_data(root: Path, audit: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    assignments: list[dict[str, Any]] = []
    delegated: list[dict[str, Any]] = []
    for component in audit.get("components", []):
        target = target_for(component, rules)
        record = {"path": component["path"], "from_module": component.get("module"), "classifications": component["classifications"]}
        if target:
            record["target_module"] = target
            record["action"] = "retain" if target == component.get("module") else "review-move"
            record["expected_sha256"] = component["sha256"]
            assignments.append(record)
        else:
            record["delegate_to"] = "migrate-kotlin-persistence-boundaries"
            delegated.append(record)
    unresolved = list(audit.get("unresolved", []))
    if not rules.get("target_data_module"):
        unresolved.append({"rule": "target-data-module-required", "severity": "error"})
    return artifact(
        root=root,
        skill=SKILL,
        script=SCRIPT,
        inputs={"rules": rules},
        unresolved=unresolved,
        gates={"plan_ready": "fail" if unresolved else "review"},
        verification=["serialization contract tests", "mapper tests", "repository tests", "compile all known consumers"],
        assignments=assignments,
        delegated=delegated,
        wire_contracts=audit.get("wire_contracts", []),
        preserved_contracts=["serial names", "defaults and nullability", "endpoint paths", "error mapping", "cache keys and invalidation"],
    )


def main() -> int:
    args = build_parser().parse_args()
    root = args.root.resolve()
    rules = load_json(args.rules, {})
    payload = audit_data(root, rules) if args.command == "audit" else plan_data(root, load_json(args.audit), rules)
    write_json(args.json_out, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
