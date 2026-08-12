#!/usr/bin/env python3
"""Audit Compose/Android resources and plan hash-guarded ownership moves."""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Any

_PACK_ROOT = Path(__file__).resolve().parents[2]
if str(_PACK_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACK_ROOT))

from common.gradle_graph import walk_files  # type: ignore
from common.repository_evidence import (  # type: ignore
    artifact,
    load_json,
    module_for,
    module_index,
    read_kotlin_sources,
    relative,
    sha256_file,
    write_json,
)

SKILL = "migrate-compose-resources"
SCRIPT = "analyze_resources.py"
ACCESSOR_RE = re.compile(r"\b(?:Res|R)\.(string|drawable|font|mipmap|color|array|plurals|raw|xml)\.([A-Za-z_][A-Za-z0-9_]*)")
GENERATED_IMPORT_RE = re.compile(r"(?:generated\.resources|resources)\.([A-Za-z_][A-Za-z0-9_]*)$")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    audit = subs.add_parser("audit")
    audit.add_argument("--root", type=Path, default=Path.cwd())
    audit.add_argument("--json-out", type=Path)
    plan = subs.add_parser("plan")
    plan.add_argument("--root", type=Path, default=Path.cwd())
    plan.add_argument("--audit", type=Path, required=True)
    plan.add_argument("--spec", type=Path, required=True)
    plan.add_argument("--json-out", type=Path)
    return parser


def resource_context(path: Path) -> tuple[str | None, str | None]:
    parts = path.parts
    for marker in ("composeResources", "res"):
        if marker not in parts:
            continue
        index = parts.index(marker)
        if index + 1 >= len(parts):
            return marker, None
        return marker, parts[index + 1]
    return None, None


def xml_definitions(path: Path, root: Path, module: str | None, directory: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    try:
        tree = ET.parse(path)
    except ET.ParseError:
        return result
    for element in tree.getroot():
        key = element.attrib.get("name")
        if not key:
            continue
        resource_type = "array" if element.tag in {"string-array", "integer-array"} else element.tag
        result.append({
            "type": resource_type,
            "key": key,
            "path": relative(path, root),
            "module": module,
            "variant": directory,
            "sha256": sha256_file(path),
            "value": "".join(element.itertext()).strip(),
        })
    return result


def scan_definitions(root: Path) -> list[dict[str, Any]]:
    _, directories = module_index(root)
    definitions: list[dict[str, Any]] = []
    for path in walk_files(root):
        marker, directory = resource_context(path)
        if not marker or not directory:
            continue
        module = module_for(path, directories)
        if path.suffix == ".xml" and directory.startswith("values"):
            definitions.extend(xml_definitions(path, root, module, directory))
            continue
        if directory.startswith("values"):
            continue
        definitions.append({
            "type": directory.split("-")[0],
            "key": path.stem,
            "path": relative(path, root),
            "module": module,
            "variant": directory,
            "sha256": sha256_file(path),
            "value": None,
        })
    return sorted(definitions, key=lambda item: (item["type"], item["key"], item["path"]))


def module_hint_from_import(imported: str, modules: list[str]) -> str | None:
    prefix = imported.split(".generated.resources", 1)[0]
    matches: list[str] = []
    for module in modules:
        parts = [part for part in module.split(":") if part]
        variants = {
            ".".join(parts),
            ".".join(part.replace("-", "") for part in parts),
            ".".join(piece for part in parts for piece in part.split("-")),
        }
        prefix_lower = prefix.lower()
        if any(prefix_lower == variant.lower() or prefix_lower.endswith("." + variant.lower()) for variant in variants):
            matches.append(module)
    return max(matches, key=len) if matches else None


def scan_usages(root: Path) -> list[dict[str, Any]]:
    modules, _ = module_index(root)
    module_paths = [module["path"] for module in modules]
    usages: list[dict[str, Any]] = []
    for source in read_kotlin_sources(root):
        explicit: dict[str, dict[str, Any]] = {}
        for imported in source["imports"]:
            match = GENERATED_IMPORT_RE.search(imported)
            if match:
                explicit[match.group(1)] = {
                    "type": None,
                    "key": match.group(1),
                    "path": source["path"],
                    "module": source["module"],
                    "import": imported,
                    "owner_hint": module_hint_from_import(imported, module_paths),
                }
        used_explicit: set[str] = set()
        for resource_type, key in ACCESSOR_RE.findall(source["code"]):
            if key in explicit:
                usage = dict(explicit[key])
                usage["type"] = resource_type
                usages.append(usage)
                used_explicit.add(key)
            else:
                usages.append({"type": resource_type, "key": key, "path": source["path"], "module": source["module"]})
        usages.extend(explicit[key] for key in sorted(set(explicit) - used_explicit))
    seen: set[tuple[Any, ...]] = set()
    result: list[dict[str, Any]] = []
    for usage in sorted(usages, key=lambda item: (item["path"], item.get("type") or "", item["key"])):
        identity = (usage.get("type"), usage["key"], usage["path"], usage.get("module"))
        if identity not in seen:
            seen.add(identity)
            result.append(usage)
    return result


def audit_resources(root: Path) -> dict[str, Any]:
    definitions = scan_definitions(root)
    usages = scan_usages(root)
    by_identity: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for definition in definitions:
        by_identity[(definition["type"], definition["key"])].append(definition)
    findings: list[dict[str, Any]] = []
    cross_module: list[dict[str, Any]] = []
    for usage in usages:
        candidates = [
            definition for (resource_type, key), values in by_identity.items()
            if key == usage["key"] and (usage.get("type") in {None, resource_type})
            for definition in values
        ]
        if usage.get("owner_hint"):
            hinted = [definition for definition in candidates if definition.get("module") == usage["owner_hint"]]
            if hinted:
                candidates = hinted
        owners = sorted({item["module"] for item in candidates if item.get("module")})
        if not candidates:
            findings.append({"rule": "resource-definition-not-found", "severity": "warning", "usage": usage})
        elif len(owners) > 1:
            findings.append({"rule": "ambiguous-resource-owner", "severity": "error", "usage": usage, "owners": owners})
        elif owners and usage.get("module") and usage["module"] != owners[0]:
            cross_module.append({"usage": usage, "owner_module": owners[0]})
    unresolved = [finding for finding in findings if finding["severity"] == "error"]
    return artifact(
        root=root,
        skill=SKILL,
        script=SCRIPT,
        unresolved=unresolved,
        gates={"unambiguous_ownership": "fail" if unresolved else "pass"},
        definitions=definitions,
        usages=usages,
        cross_module_usages=cross_module,
        findings=findings,
    )


def plan_resources(root: Path, audit: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    definitions = audit.get("definitions", [])
    planned: list[dict[str, Any]] = []
    unresolved = list(audit.get("unresolved", []))
    for move in spec.get("moves", []):
        if move.get("preserve_key") is not True:
            unresolved.append({"rule": "resource-key-preservation-required", "severity": "error", "move": move})
            continue
        matches = [
            item for item in definitions
            if item["type"] == move.get("type") and item["key"] == move.get("key") and item.get("module") == move.get("from_module")
        ]
        if not matches:
            unresolved.append({"rule": "resource-move-source-not-found", "severity": "error", "move": move})
            continue
        if not move.get("to_module"):
            unresolved.append({"rule": "resource-target-module-required", "severity": "error", "move": move})
            continue
        consumers = [
            item for item in audit.get("usages", [])
            if item["key"] == move["key"] and item.get("type") in {None, move["type"]}
        ]
        planned.append({
            "type": move["type"],
            "key": move["key"],
            "from_module": move["from_module"],
            "to_module": move["to_module"],
            "definitions": matches,
            "consumers": consumers,
            "operations": [
                {
                    "path": definition["path"],
                    "expected_sha256": definition["sha256"],
                    "operation": "extract-xml-entry" if definition["path"].endswith(".xml") and definition["variant"].startswith("values") else "move-file",
                }
                for definition in matches
            ],
        })
    return artifact(
        root=root,
        skill=SKILL,
        script=SCRIPT,
        inputs={"spec": spec},
        unresolved=unresolved,
        gates={"plan_ready": "fail" if unresolved else "review"},
        verification=["compile target resource module", "compile every recorded consumer", "verify all locale/qualifier variants"],
        moves=planned,
        preserved_contracts=["resource type/key", "locale and qualifier variants", "file content hashes", "generated accessor identity"],
    )


def main() -> int:
    args = build_parser().parse_args()
    root = args.root.resolve()
    payload = audit_resources(root) if args.command == "audit" else plan_resources(root, load_json(args.audit), load_json(args.spec))
    write_json(args.json_out, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
