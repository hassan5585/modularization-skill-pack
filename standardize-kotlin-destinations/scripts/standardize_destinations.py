#!/usr/bin/env python3
"""Audit, plan, scaffold, and check the Destination NavKey convention.

Deterministic inventory and Destination.kt scaffolding only. Converting
existing route types and authoring feature destinations remain agent-driven.
Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
SCRIPT_VERSION = "1"
SKILL = "standardize-kotlin-destinations"
SCRIPT_NAME = "standardize_destinations.py"

_PACK_ROOT = Path(__file__).resolve().parents[2]
if str(_PACK_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACK_ROOT))

from common.artifact_schema import envelope_fields, validate_artifact  # type: ignore
from common.gradle_graph import (  # type: ignore
    PACKAGE_RE,
    discover_modules,
    source_set_for_path,
    walk_files,
)

NAV3_MARKERS = (
    "androidx.navigation3",
    "org.jetbrains.androidx.navigation3",
    "navigation3-ui",
    "navigation3-runtime",
    "libs.androidx.navigation3",
)
NAV2_MARKERS = (
    "androidx.navigation:navigation-compose",
    "androidx.navigation:navigation-runtime",
    "org.jetbrains.androidx.navigation:navigation-compose",
    "org.jetbrains.androidx.navigation:navigation-runtime",
    "libs.androidx.navigation.compose",
    "libs.navigation.compose",
)
ROUTE_BASE_NAMES = {
    "AppRoute",
    "Route",
    "Screen",
    "NavRoute",
    "AppScreen",
    "RootRoute",
    "NavigationRoute",
}
PRIMITIVE_TYPES = {
    "String",
    "String?",
    "Int",
    "Int?",
    "Long",
    "Long?",
    "Float",
    "Float?",
    "Double",
    "Double?",
    "Boolean",
    "Boolean?",
    "Byte",
    "Byte?",
    "Short",
    "Short?",
    "Char",
    "Char?",
}
COLLECTION_PREFIXES = (
    "List",
    "MutableList",
    "Set",
    "MutableSet",
    "Map",
    "MutableMap",
    "Array",
    "ArrayList",
    "HashMap",
    "HashSet",
)
TEST_SOURCE_HINTS = ("test", "androidunittest", "androidinstrumentedtest", "hosttest")
PACKAGE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
MODULE_PATH_RE = re.compile(r"^:[A-Za-z0-9_-]+(?::[A-Za-z0-9_-]+)*$")
DECL_RE = re.compile(
    r"(?m)^(?P<indent>[ \t]*)"
    r"(?:@[A-Za-z_][\w.]*(?:\((?:[^()]|\([^()]*\))*\))?[ \t]*)*"
    r"(?P<mods>(?:(?:public|internal|private|protected|open|abstract|final|"
    r"sealed|data|value|inner|expect|actual|enum)\s+)*)"
    r"(?P<kind>interface|class|object)\s+(?P<name>[A-Za-z_]\w*)"
    r"(?:<(?:[^<>]|<[^>]*>)*>)?"
    r"(?:\((?P<params>(?:[^()]*|\([^()]*\))*)\))?"
    r"(?:\s*:\s*(?P<supers>[^{=\n]+))?"
)
SERIAL_NAME_RE = re.compile(r'@SerialName\s*\(\s*"([^"]+)"\s*\)')
DEST_ID_ASSIGN_RE = re.compile(r'destinationId\s*(?::\s*String\s*)?=\s*"([^"]+)"')
DEST_ID_WHEN_RE = re.compile(
    r'(?:is\s+)?(?P<name>[A-Za-z_]\w*)\s*(?:->|=)\s*"([^"]+)"'
)
SUBCLASS_RE = re.compile(r"subclass\s*\(\s*([A-Za-z_][\w.]*)\s*\.\s*serializer\s*\(\s*\)\s*\)")
STRING_ROUTE_RE = re.compile(r"""\bcomposable\s*\(\s*["']([^"']+)["']""")
IDENTITY_RE = re.compile(
    r"(?:destination|route)::class\.(?:qualifiedName|simpleName)"
    r"|Destination\.route\s*\(|subclassesOfSealed\s*<"
)
PARAM_RE = re.compile(r"(?:val|var)\s+([A-Za-z_]\w*)\s*:\s*([^,=]+)")
ID_FORMAT_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
DESTINATION_CONTRACT_RE = re.compile(
    r"(?m)^\s*(?:(?:public|internal)\s+)*(?:sealed\s+)?"
    r"(?:interface|class)\s+Destination\b"
)
NAV_KEY_RE = re.compile(r"\bNavKey\b")
DEST_ID_PROP_RE = re.compile(r"\bval\s+destinationId\s*:\s*String\b")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    audit = sub.add_parser("audit", help="Inspect Destination and route-key usage")
    audit.add_argument("--root", type=Path, default=Path.cwd())
    audit.add_argument("--json-out", type=Path)

    plan = sub.add_parser("plan", help="Turn an audit into destination-spec.json")
    plan.add_argument("--root", type=Path, default=Path.cwd())
    plan.add_argument("--audit", type=Path)
    plan.add_argument("--json-out", type=Path)

    scaffold = sub.add_parser("scaffold", help="Preview/apply Destination contract files")
    scaffold.add_argument("--root", type=Path, default=Path.cwd())
    scaffold.add_argument("--spec", type=Path, required=True)
    scaffold.add_argument("--apply", action="store_true")
    scaffold.add_argument(
        "--force-unresolved",
        action="store_true",
        help="Allow scaffold when plan gates still list unresolved items",
    )

    check = sub.add_parser("check", help="Report Destination convention gaps")
    check.add_argument("--root", type=Path, default=Path.cwd())
    check.add_argument("--spec", type=Path)
    check.add_argument("--json-out", type=Path)
    return parser.parse_args(argv)


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected JSON object")
    return data


def write_json(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=False))


def relative_posix(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def safe_under_root(root: Path, relative: Path) -> Path:
    target = (root / relative).resolve()
    if target != root.resolve() and root.resolve() not in target.parents:
        raise ValueError(f"path escapes repository root: {relative}")
    return target


def strip_kotlin_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"//.*?$", "", text, flags=re.MULTILINE)


def is_test_source(source_set: str | None, path: str) -> bool:
    if source_set and any(hint in source_set.lower() for hint in TEST_SOURCE_HINTS):
        return True
    lowered = path.lower()
    return any(f"/{hint}/" in f"/{lowered}/" for hint in ("commontest", "androidunittest", "/test/"))


def detect_platform(root: Path, modules: list[dict[str, Any]]) -> dict[str, Any]:
    texts: list[str] = []
    source_sets: set[str] = set()
    has_nav3 = False
    has_nav2 = False
    for path in walk_files(root):
        if path.suffix == ".kt":
            source_set = source_set_for_path(path.relative_to(root))
            if source_set:
                source_sets.add(source_set)
        if path.suffix not in {".kt", ".kts", ".toml", ".gradle"} and path.name not in {
            "build.gradle",
            "build.gradle.kts",
            "libs.versions.toml",
        }:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        texts.append(text)
        if any(marker in text for marker in NAV3_MARKERS) or "navigation3" in text:
            has_nav3 = True
        if any(marker in text for marker in NAV2_MARKERS):
            has_nav2 = True
    joined = "\n".join(texts)
    has_common = any((root / module["directory"] / "src" / "commonMain").is_dir() for module in modules)
    if "androidTarget" in joined or "iosArm64" in joined or has_common:
        platform = "kmp"
    elif "com.android" in joined or "android.library" in joined:
        platform = "android"
    else:
        platform = "unknown"
    return {
        "platform": platform,
        "source_sets": sorted(source_sets),
        "has_navigation3": has_nav3,
        "has_navigation2": has_nav2,
    }


def module_for_path(rel: str, modules: list[dict[str, Any]]) -> dict[str, Any] | None:
    matches = [
        module
        for module in modules
        if module["directory"] != "." and (rel == module["directory"] or rel.startswith(module["directory"] + "/"))
    ]
    if not matches:
        return None
    return max(matches, key=lambda item: len(item["directory"]))


def classify_param_type(raw: str) -> str:
    cleaned = re.sub(r"\s+", "", raw)
    if cleaned in PRIMITIVE_TYPES:
        return "primitive"
    head = cleaned.split("<", 1)[0].rstrip("?")
    if head in COLLECTION_PREFIXES or cleaned.startswith(COLLECTION_PREFIXES):
        return "collection"
    return "complex"


def preceding_annotations(text: str, index: int) -> str:
    start = max(0, index - 500)
    return text[start:index]


def following_body(text: str, index: int, next_index: int | None) -> str:
    end = next_index if next_index is not None else min(len(text), index + 800)
    return text[index:end]


def snake_id(name: str) -> str:
    stepped = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    return re.sub(r"[^a-zA-Z0-9]+", "_", stepped).strip("_").lower()


def suggested_id(package: str | None, owner: str | None, name: str) -> str:
    feature = None
    if owner and owner.endswith("Destination") and owner != "Destination":
        feature = snake_id(owner[: -len("Destination")])
    elif owner and owner in ROUTE_BASE_NAMES:
        feature = "app"
    if not feature and package:
        parts = package.split(".")
        for candidate in reversed(parts):
            if candidate not in {"navigation", "ui", "core", "feature", "app", "com", "org"}:
                feature = snake_id(candidate)
                break
    feature = feature or "app"
    return f"{feature}.{snake_id(name)}"


def parse_declarations(text: str) -> list[dict[str, Any]]:
    matches = list(DECL_RE.finditer(text))
    declarations: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        nxt = matches[index + 1].start() if index + 1 < len(matches) else None
        mods = match.group("mods") or ""
        kind = match.group("kind")
        name = match.group("name")
        params = match.group("params") or ""
        supers = (match.group("supers") or "").strip()
        prefix = preceding_annotations(text, match.start())
        body = following_body(text, match.end(), nxt)
        serial_names = SERIAL_NAME_RE.findall(prefix + match.group(0))
        dest_ids = DEST_ID_ASSIGN_RE.findall(body)
        declarations.append(
            {
                "name": name,
                "kind": kind,
                "mods": mods,
                "sealed": "sealed" in mods.split(),
                "data": "data" in mods.split(),
                "params": PARAM_RE.findall(params),
                "supers": [part.strip().split("<", 1)[0] for part in supers.split(",") if part.strip()],
                "serial_name": serial_names[-1] if serial_names else None,
                "destination_id": dest_ids[0] if dest_ids else None,
                "serializable": "@Serializable" in prefix or "@Serializable" in match.group(0),
                "start": match.start(),
                "indent": match.group("indent") or "",
                "when_ids": {
                    item.group("name"): item.group(2)
                    for item in DEST_ID_WHEN_RE.finditer(body)
                    if "destinationId" in body
                },
            }
        )
    return declarations


def analyze_kotlin_file(root: Path, path: Path, modules: list[dict[str, Any]]) -> dict[str, Any] | None:
    if path.suffix != ".kt":
        return None
    rel = path.relative_to(root)
    if any(part in rel.parts for part in ("generated", "build")):
        return None
    raw = path.read_text(encoding="utf-8", errors="replace")
    text = strip_kotlin_comments(raw)
    rel_s = rel.as_posix()
    source_set = source_set_for_path(rel)
    package_match = PACKAGE_RE.search(text)
    package = package_match.group(1) if package_match else None
    module = module_for_path(rel_s, modules)
    declarations = parse_declarations(text)
    subclasses = SUBCLASS_RE.findall(text)
    string_routes = STRING_ROUTE_RE.findall(text)
    identity_hits = [match.group(0) for match in IDENTITY_RE.finditer(text)]
    return {
        "path": rel_s,
        "package": package,
        "source_set": source_set,
        "module_path": module["path"] if module else None,
        "module_directory": module["directory"] if module else None,
        "test": is_test_source(source_set, rel_s),
        "declarations": declarations,
        "subclasses": subclasses,
        "string_routes": string_routes,
        "identity_hits": identity_hits,
        "has_destination_contract": bool(DESTINATION_CONTRACT_RE.search(text)),
        "has_nav_key": bool(NAV_KEY_RE.search(text)),
        "has_destination_id_prop": bool(DEST_ID_PROP_RE.search(text)),
        "text": text,
    }


def ownership_for(path: str, module_path: str | None, name: str) -> str:
    parts = path.replace("\\", "/").split("/")
    if name == "Destination" or path.endswith("/Destination.kt"):
        return "contract"
    if "/ui/" in f"/{path}/" or parts[-2:] == ["ui", Path(path).name]:
        if "navigation" not in parts:
            return "ui"
    if "navigation" in parts:
        if module_path and ":feature:" in module_path:
            return "feature-navigation"
        if module_path and (module_path.endswith(":navigation") or ":core:navigation" in module_path):
            return "core-navigation"
        return "navigation"
    if module_path and ":core:" in module_path:
        return "core"
    return "other"


def collect_enum_names(files: list[dict[str, Any]]) -> set[str]:
    names: set[str] = set()
    for item in files:
        for decl in item["declarations"]:
            if "enum" in decl["mods"].split() or (
                decl["kind"] == "class" and "enum" in decl["mods"]
            ):
                names.add(decl["name"])
    return names


def build_inventory(files: list[dict[str, Any]]) -> dict[str, Any]:
    production = [item for item in files if not item["test"]]
    contract = None
    bases: list[dict[str, Any]] = []
    leaves: list[dict[str, Any]] = []
    registered: set[str] = set()
    string_routes: list[dict[str, str]] = []
    identity: list[dict[str, str]] = []
    enum_names = collect_enum_names(production)

    by_name: dict[str, list[dict[str, Any]]] = {}
    for item in production:
        for decl in item["declarations"]:
            by_name.setdefault(decl["name"], []).append({"file": item, "decl": decl})

    destination_implementors = {"Destination"}
    for item in production:
        for decl in item["declarations"]:
            supers = set(decl["supers"])
            if "Destination" in supers or decl["name"].endswith("Destination"):
                destination_implementors.add(decl["name"])

    changed = True
    while changed:
        changed = False
        for item in production:
            for decl in item["declarations"]:
                if decl["name"] in destination_implementors:
                    continue
                if destination_implementors.intersection(decl["supers"]):
                    destination_implementors.add(decl["name"])
                    changed = True

    for item in production:
        registered.update(item["subclasses"])
        for route in item["string_routes"]:
            string_routes.append({"path": item["path"], "route": route})
        for hit in item["identity_hits"]:
            identity.append({"path": item["path"], "evidence": hit})
        if item["has_destination_contract"] and contract is None:
            contract = {
                "name": "Destination",
                "path": item["path"],
                "package": item["package"],
                "module_path": item["module_path"],
                "module_directory": item["module_directory"],
                "source_set": item["source_set"],
                "implements_nav_key": item["has_nav_key"]
                or any("NavKey" in super_name for decl in item["declarations"] if decl["name"] == "Destination" for super_name in decl["supers"]),
                "has_destination_id": item["has_destination_id_prop"]
                or any(
                    decl["name"] == "Destination" and decl["destination_id"] is not None
                    for decl in item["declarations"]
                ),
            }
        for decl in item["declarations"]:
            supers = set(decl["supers"])
            is_route_base = (
                decl["name"] in ROUTE_BASE_NAMES
                or (decl["sealed"] and decl["name"].endswith("Destination"))
                or (decl["sealed"] and "NavKey" in supers)
                or (decl["name"] != "Destination" and "Destination" in supers and decl["kind"] == "interface")
            )
            if is_route_base and decl["name"] != "Destination":
                bases.append(
                    {
                        "name": decl["name"],
                        "kind": decl["kind"],
                        "path": item["path"],
                        "package": item["package"],
                        "module_path": item["module_path"],
                        "implements_destination": "Destination" in supers,
                        "implements_nav_key": "NavKey" in supers,
                        "ownership": ownership_for(item["path"], item["module_path"], decl["name"]),
                    }
                )

    parent_when_ids: dict[str, dict[str, str]] = {}
    for item in production:
        for decl in item["declarations"]:
            if decl["when_ids"]:
                parent_when_ids[decl["name"]] = decl["when_ids"]

    for item in production:
        for decl in item["declarations"]:
            if decl["name"] == "Destination" and decl["kind"] in {"interface", "class"} and not decl["data"]:
                continue
            supers = set(decl["supers"])
            is_leaf = (
                decl["kind"] in {"object", "class"}
                and (
                    destination_implementors.intersection(supers)
                    or decl["name"] in destination_implementors and decl["kind"] == "object"
                    or any(base in ROUTE_BASE_NAMES for base in supers)
                    or any(base.endswith("Destination") for base in supers)
                )
            )
            if not is_leaf:
                continue
            if decl["sealed"] and decl["kind"] == "interface":
                continue
            owner = next((base for base in decl["supers"] if base in destination_implementors or base in ROUTE_BASE_NAMES), None)
            dest_id = decl["destination_id"]
            if dest_id is None and owner and owner in parent_when_ids:
                dest_id = parent_when_ids[owner].get(decl["name"])
            parameters = []
            forbidden = False
            for pname, ptype in decl["params"]:
                kind = classify_param_type(ptype)
                if kind == "complex" and ptype.strip().rstrip("?") in enum_names:
                    kind = "enum"
                parameters.append({"name": pname, "type": ptype.strip(), "kind": kind})
                if kind in {"collection", "complex"}:
                    forbidden = True
            leaf_name = decl["name"]
            qualified = f"{owner}.{leaf_name}" if owner else leaf_name
            registered_hit = any(
                entry == leaf_name
                or entry.endswith("." + leaf_name)
                or entry == qualified
                or entry.endswith("." + qualified)
                for entry in registered
            )
            leaves.append(
                {
                    "name": leaf_name,
                    "owner": owner,
                    "qualified": qualified,
                    "path": item["path"],
                    "package": item["package"],
                    "module_path": item["module_path"],
                    "source_set": item["source_set"],
                    "kind": "object" if decl["kind"] == "object" else "class",
                    "serializable": decl["serializable"],
                    "serial_name": decl["serial_name"],
                    "destination_id": dest_id,
                    "suggested_id": suggested_id(item["package"], owner, leaf_name),
                    "parameters": parameters,
                    "forbidden_params": forbidden,
                    "registered": registered_hit,
                    "ownership": ownership_for(item["path"], item["module_path"], leaf_name),
                    "implements_destination": bool(destination_implementors.intersection(supers))
                    or owner == "Destination",
                }
            )

    return {
        "contract": contract,
        "bases": bases,
        "leaves": leaves,
        "registered_serializers": sorted(registered),
        "string_routes": string_routes,
        "identity": identity,
    }


def finding(rule: str, severity: str, message: str, path: str | None = None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {"rule": rule, "severity": severity, "message": message}
    if path:
        payload["path"] = path
    if extra:
        payload.update(extra)
    return payload


def audit_findings(project: dict[str, Any], inventory: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    contract = inventory["contract"]
    if not project["has_navigation3"] and project["has_navigation2"]:
        findings.append(
            finding(
                "navigation3-required",
                "error",
                "Destination extends NavKey; migrate with migrate-to-navigation3 before introducing Destination.",
            )
        )
    if contract is None:
        findings.append(
            finding("missing-destination-contract", "error", "No Destination interface found.")
        )
    else:
        if not contract["implements_nav_key"]:
            findings.append(
                finding(
                    "destination-missing-navkey",
                    "error",
                    "Destination does not implement NavKey.",
                    contract["path"],
                )
            )
        if not contract["has_destination_id"]:
            findings.append(
                finding(
                    "destination-missing-id-property",
                    "error",
                    "Destination does not declare destinationId.",
                    contract["path"],
                )
            )
    if inventory["string_routes"]:
        findings.append(
            finding(
                "string-routes",
                "error",
                "String composable routes must become typed Destination keys.",
                extra={"count": len(inventory["string_routes"])},
            )
        )
    for hit in inventory["identity"]:
        findings.append(
            finding(
                "class-name-identity",
                "error",
                "Do not derive navigation identity from class names or .route().",
                hit["path"],
                {"evidence": hit["evidence"]},
            )
        )
    for base in inventory["bases"]:
        if not base["implements_destination"] and contract is not None:
            findings.append(
                finding(
                    "route-base-not-destination",
                    "warning",
                    f"{base['name']} is a route base that does not implement Destination.",
                    base["path"],
                )
            )
        if base["ownership"] == "ui":
            findings.append(
                finding(
                    "route-base-in-ui",
                    "error",
                    f"{base['name']} lives in a UI module.",
                    base["path"],
                )
            )
    for leaf in inventory["leaves"]:
        if not leaf["serializable"]:
            findings.append(
                finding("missing-serializable", "error", f"{leaf['qualified']} is not @Serializable.", leaf["path"])
            )
        if not leaf["serial_name"]:
            findings.append(
                finding(
                    "missing-serial-name",
                    "error",
                    f"{leaf['qualified']} is missing @SerialName.",
                    leaf["path"],
                    {"suggested_id": leaf["suggested_id"]},
                )
            )
        elif not ID_FORMAT_RE.fullmatch(leaf["serial_name"]):
            findings.append(
                finding(
                    "serial-name-format",
                    "warning",
                    f"{leaf['qualified']} @SerialName {leaf['serial_name']!r} is not feature.screen_name.",
                    leaf["path"],
                )
            )
        if not leaf["destination_id"]:
            findings.append(
                finding(
                    "missing-destination-id",
                    "error",
                    f"{leaf['qualified']} is missing destinationId.",
                    leaf["path"],
                    {"suggested_id": leaf["suggested_id"]},
                )
            )
        elif leaf["serial_name"] and leaf["destination_id"] != leaf["serial_name"]:
            findings.append(
                finding(
                    "id-serial-mismatch",
                    "error",
                    f"{leaf['qualified']} destinationId {leaf['destination_id']!r} != @SerialName {leaf['serial_name']!r}.",
                    leaf["path"],
                )
            )
        if leaf["forbidden_params"]:
            findings.append(
                finding(
                    "non-primitive-params",
                    "error",
                    f"{leaf['qualified']} has non-primitive route parameters.",
                    leaf["path"],
                    {"parameters": leaf["parameters"]},
                )
            )
        if not leaf["registered"]:
            findings.append(
                finding(
                    "unregistered-serializer",
                    "error",
                    f"{leaf['qualified']} has no subclass(...serializer()) registration.",
                    leaf["path"],
                )
            )
        if leaf["ownership"] == "ui":
            findings.append(
                finding(
                    "destination-in-ui",
                    "error",
                    f"{leaf['qualified']} lives in a UI module.",
                    leaf["path"],
                )
            )
        if (
            leaf["ownership"] in {"core", "core-navigation"}
            and leaf["owner"] not in {None, "Destination"}
            and leaf["owner"]
            and not leaf["owner"].startswith("Destination")
        ):
            if leaf["owner"].endswith("Destination") and leaf["owner"] != "Destination":
                findings.append(
                    finding(
                        "feature-destination-in-core",
                        "warning",
                        f"{leaf['qualified']} looks feature-owned but lives in core.",
                        leaf["path"],
                    )
                )
    return findings


def infer_nav_module(modules: list[dict[str, Any]], inventory: dict[str, Any]) -> dict[str, Any] | None:
    contract = inventory["contract"]
    if contract and contract.get("module_path"):
        for module in modules:
            if module["path"] == contract["module_path"]:
                return module
    preferred = (":core:navigation", ":shared:navigation")
    by_path = {module["path"]: module for module in modules}
    for path in preferred:
        if path in by_path:
            return by_path[path]
    foundation = [
        module
        for module in modules
        if module["path"].endswith(":navigation") and ":feature:" not in module["path"]
    ]
    if len(foundation) == 1:
        return foundation[0]
    return None


def infer_package(root: Path, module: dict[str, Any] | None, inventory: dict[str, Any]) -> str | None:
    contract = inventory["contract"]
    if contract and contract.get("package"):
        return contract["package"]
    if not module:
        return None
    for item in inventory["bases"]:
        if item.get("module_path") == module["path"] and item.get("package"):
            return item["package"]
    directory = root / module["directory"]
    for path in directory.rglob("*.kt"):
        if "test" in {part.lower() for part in path.parts}:
            continue
        match = PACKAGE_RE.search(path.read_text(encoding="utf-8", errors="replace"))
        if match:
            return match.group(1)
    return None


def infer_source_set(root: Path, module: dict[str, Any] | None, project: dict[str, Any]) -> str:
    if module and (root / module["directory"] / "src" / "commonMain").is_dir():
        return "commonMain"
    if project["platform"] == "kmp":
        return "commonMain"
    return "main"


def gate_status(ok: bool, review: bool = False) -> str:
    if review and ok:
        return "review"
    return "pass" if ok else "fail"


def build_audit(root: Path) -> dict[str, Any]:
    modules = discover_modules(root)
    project = detect_platform(root, modules)
    files: list[dict[str, Any]] = []
    for path in walk_files(root):
        analyzed = analyze_kotlin_file(root, path, modules)
        if analyzed:
            files.append(analyzed)
    inventory = build_inventory(files)
    findings = audit_findings(project, inventory)
    contract = inventory["contract"]
    unresolved: list[dict[str, str]] = []
    if not infer_nav_module(modules, inventory):
        unresolved.append(
            {
                "id": "destination-module",
                "message": "No :core:navigation (or equivalent) module found; use extract-kotlin-foundations.",
            }
        )
    if project["has_navigation2"] and not project["has_navigation3"]:
        unresolved.append(
            {
                "id": "navigation3-runtime",
                "message": "Navigation 3 / NavKey is not present; run migrate-to-navigation3 first.",
            }
        )
    payload = envelope_fields(
        skill=SKILL,
        script=SCRIPT_NAME,
        script_version=SCRIPT_VERSION,
        repository_root=".",
        unresolved=unresolved,
        gates={
            "navigation3_runtime": gate_status(project["has_navigation3"] or not project["has_navigation2"]),
            "destination_contract": gate_status(
                bool(contract and contract["implements_nav_key"] and contract["has_destination_id"])
            ),
        },
    )
    payload["kind"] = "destination-audit"
    payload["project"] = project
    payload["modules"] = [
        {"path": module["path"], "directory": module["directory"]}
        for module in modules
        if "navigation" in module["path"]
    ]
    payload["contract"] = contract
    payload["bases"] = inventory["bases"]
    payload["leaves"] = inventory["leaves"]
    payload["registered_serializers"] = inventory["registered_serializers"]
    payload["string_routes"] = inventory["string_routes"]
    payload["identity"] = inventory["identity"]
    payload["findings"] = findings
    payload["recommendations"] = recommendations_for(project, inventory, findings)
    return payload


def recommendations_for(
    project: dict[str, Any], inventory: dict[str, Any], findings: list[dict[str, Any]]
) -> list[str]:
    notes: list[str] = []
    rules = {item["rule"] for item in findings}
    if "navigation3-required" in rules:
        notes.append("Run $migrate-to-navigation3 before introducing Destination.")
    if inventory["contract"] is None:
        notes.append("Scaffold Destination in the navigation foundation module.")
    if any(base["name"] in ROUTE_BASE_NAMES and not base["implements_destination"] for base in inventory["bases"]):
        notes.append("Convert the existing app-wide route base onto Destination.")
    if any(item["rule"] == "unregistered-serializer" for item in findings):
        notes.append("Register every concrete destination with subclass(Type.serializer()).")
    if inventory["string_routes"]:
        notes.append("Replace string composable routes with typed Destination keys.")
    if not notes and not findings:
        notes.append("Destination convention already looks complete; use check after edits.")
    return notes


def build_plan(root: Path, audit: dict[str, Any] | None) -> dict[str, Any]:
    if audit is None:
        audit = build_audit(root)
    modules = discover_modules(root)
    project = audit["project"]
    inventory = {
        "contract": audit.get("contract"),
        "bases": audit.get("bases") or [],
        "leaves": audit.get("leaves") or [],
        "string_routes": audit.get("string_routes") or [],
    }
    module = infer_nav_module(modules, inventory)
    package = infer_package(root, module, inventory)
    source_set = infer_source_set(root, module, project)
    contract = inventory["contract"]
    existing_base = next((base for base in inventory["bases"] if base["name"] in ROUTE_BASE_NAMES), None)
    introduce = contract is None
    unresolved: list[dict[str, str]] = list(audit.get("unresolved") or [])
    if module is None:
        if not any(item["id"] == "destination-module" for item in unresolved):
            unresolved.append(
                {
                    "id": "destination-module",
                    "message": "No navigation foundation module found; use extract-kotlin-foundations.",
                }
            )
    if introduce and package is None:
        unresolved.append({"id": "destination-package", "message": "Could not infer Destination package."})
    conversions = []
    for base in inventory["bases"]:
        if base["implements_destination"]:
            continue
        strategy = "implement-destination" if base["name"] in ROUTE_BASE_NAMES else "feature-destination"
        conversions.append({"from": base["name"], "strategy": strategy, "path": base["path"]})
    leaves = []
    for leaf in inventory["leaves"]:
        leaves.append(
            {
                "name": leaf["name"],
                "qualified": leaf["qualified"],
                "path": leaf["path"],
                "serial_name": leaf.get("serial_name"),
                "destination_id": leaf.get("destination_id"),
                "suggested_id": leaf.get("suggested_id"),
            }
        )
    findings = audit.get("findings") or []
    rules = {item["rule"] for item in findings}
    payload = envelope_fields(
        skill=SKILL,
        script=SCRIPT_NAME,
        script_version=SCRIPT_VERSION,
        repository_root=".",
        inputs={"audit": ".modularization/destination-audit.json"} if audit else {},
        unresolved=unresolved,
        gates={
            "navigation3_runtime": gate_status(project.get("has_navigation3") or not project.get("has_navigation2")),
            "destination_module": gate_status(module is not None),
            "destination_contract": gate_status(bool(contract) and not introduce),
            "serial_names": gate_status("missing-serial-name" not in rules),
            "destination_ids": gate_status("missing-destination-id" not in rules and "id-serial-mismatch" not in rules),
            "primitive_params": gate_status("non-primitive-params" not in rules),
            "serializer_registration": gate_status("unregistered-serializer" not in rules),
            "ownership": gate_status(
                "destination-in-ui" not in rules and "route-base-in-ui" not in rules,
                review="feature-destination-in-core" in rules,
            ),
        },
    )
    payload["kind"] = "destination-spec"
    payload["project"] = {
        "platform": project.get("platform"),
        "source_sets": project.get("source_sets") or [],
        "has_navigation3": project.get("has_navigation3"),
        "has_navigation2": project.get("has_navigation2"),
    }
    payload["destination"] = {
        "exists": contract is not None,
        "introduce": introduce,
        "type_name": "Destination",
        "module_path": module["path"] if module else None,
        "module_directory": module["directory"] if module else None,
        "package": package,
        "source_set": source_set,
        "keeps_existing_name": False,
        "existing_base_type": (
            {
                "name": existing_base["name"],
                "package": existing_base.get("package"),
                "path": existing_base["path"],
            }
            if existing_base
            else None
        ),
        "files": {"destination": "Destination.kt", "serializers": "DestinationSerializers.kt"},
        "path": contract["path"] if contract else None,
    }
    payload["id_scheme"] = "feature.screen_name"
    payload["conversions"] = conversions
    payload["leaves"] = leaves
    payload["recommendations"] = audit.get("recommendations") or recommendations_for(project, inventory, findings)
    return payload


def generate_destination_kt(package: str) -> str:
    return (
        f"package {package}\n"
        "\n"
        "import androidx.navigation3.runtime.NavKey\n"
        "\n"
        "interface Destination : NavKey {\n"
        "    val destinationId: String\n"
        "}\n"
    )


def generate_serializers_kt(package: str) -> str:
    return (
        f"package {package}\n"
        "\n"
        "import kotlinx.serialization.modules.PolymorphicModuleBuilder\n"
        "\n"
        "fun PolymorphicModuleBuilder<Destination>.registerCoreDestinationSerializers() {\n"
        "}\n"
    )


def source_root_for(module_directory: str, source_set: str, package: str) -> Path:
    return Path(module_directory) / "src" / source_set / "kotlin" / Path(*package.split("."))


def load_spec(path: Path) -> dict[str, Any]:
    data = load_json(path)
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version: {data.get('schema_version')!r}")
    destination = data.get("destination")
    if not isinstance(destination, dict):
        raise ValueError("spec.destination is required")
    if destination.get("introduce"):
        package = destination.get("package")
        if not package or not PACKAGE_NAME_RE.fullmatch(str(package)):
            raise ValueError(f"invalid destination.package: {package!r}")
        module_directory = destination.get("module_directory")
        if not module_directory or not isinstance(module_directory, str):
            raise ValueError("destination.module_directory is required to introduce Destination")
        if module_directory.startswith("/") or ".." in Path(module_directory).parts:
            raise ValueError(f"invalid destination.module_directory: {module_directory!r}")
        module_path = destination.get("module_path")
        if module_path is not None and not MODULE_PATH_RE.fullmatch(str(module_path)):
            raise ValueError(f"invalid destination.module_path: {module_path!r}")
    return data


def run_scaffold(root: Path, spec: dict[str, Any], apply: bool, force: bool) -> int:
    destination = spec["destination"]
    if spec.get("project", {}).get("has_navigation2") and not spec.get("project", {}).get("has_navigation3"):
        print("error: Navigation 3 runtime is required before scaffolding Destination", file=sys.stderr)
        return 2
    if spec.get("gates", {}).get("navigation3_runtime") == "fail":
        print("error: navigation3_runtime gate failed", file=sys.stderr)
        return 2
    unresolved = spec.get("unresolved") or []
    blocking = [item for item in unresolved if item.get("id") in {"destination-module", "destination-package", "navigation3-runtime"}]
    if blocking and not force:
        print("error: unresolved plan items block scaffold:", file=sys.stderr)
        for item in blocking:
            print(f"  - {item['id']}: {item['message']}", file=sys.stderr)
        return 2
    if not destination.get("introduce"):
        print("Destination already exists; nothing to scaffold.")
        if destination.get("path"):
            print(f"  existing: {destination['path']}")
        return 0
    package = destination["package"]
    source_set = destination.get("source_set") or "commonMain"
    directory = source_root_for(destination["module_directory"], source_set, package)
    planned = [
        (directory / "Destination.kt", generate_destination_kt(package)),
        (directory / "DestinationSerializers.kt", generate_serializers_kt(package)),
    ]
    conflicts = [rel for rel, _ in planned if (root / rel).exists()]
    print(f"{'Applying' if apply else 'Dry run'}: Destination contract")
    print(f"  module: {destination.get('module_path')}")
    print(f"  package: {package}")
    for rel, _ in planned:
        print(f"  + {rel.as_posix()}")
    if conflicts:
        print("error: refusing to overwrite existing files:", file=sys.stderr)
        for rel in conflicts:
            print(f"  - {rel.as_posix()}", file=sys.stderr)
        return 3
    if apply:
        for rel, content in planned:
            target = safe_under_root(root, rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        print("Wrote Destination.kt and DestinationSerializers.kt")
    return 0


def build_check(root: Path, spec: dict[str, Any] | None) -> dict[str, Any]:
    audit = build_audit(root)
    findings = audit["findings"]
    errors = [item for item in findings if item.get("severity") == "error"]
    gates = {
        "navigation3_runtime": audit["gates"]["navigation3_runtime"],
        "destination_contract": audit["gates"]["destination_contract"],
        "serial_names": gate_status(not any(item["rule"] == "missing-serial-name" for item in findings)),
        "destination_ids": gate_status(
            not any(item["rule"] in {"missing-destination-id", "id-serial-mismatch"} for item in findings)
        ),
        "primitive_params": gate_status(not any(item["rule"] == "non-primitive-params" for item in findings)),
        "serializer_registration": gate_status(
            not any(item["rule"] == "unregistered-serializer" for item in findings)
        ),
        "ownership": gate_status(
            not any(item["rule"] in {"destination-in-ui", "route-base-in-ui"} for item in findings)
        ),
        "identity": gate_status(not any(item["rule"] == "class-name-identity" for item in findings)),
        "string_routes": gate_status(not any(item["rule"] == "string-routes" for item in findings)),
    }
    payload = envelope_fields(
        skill=SKILL,
        script=SCRIPT_NAME,
        script_version=SCRIPT_VERSION,
        repository_root=".",
        inputs={"spec": ".modularization/destination-spec.json"} if spec else {},
        unresolved=audit.get("unresolved") or [],
        gates=gates,
        verification=["python3 scripts/standardize_destinations.py check --root ."],
    )
    payload["kind"] = "destination-check"
    payload["findings"] = findings
    payload["summary"] = {
        "leaves": len(audit.get("leaves") or []),
        "bases": len(audit.get("bases") or []),
        "errors": len(errors),
        "warnings": sum(1 for item in findings if item.get("severity") == "warning"),
        "passed": not errors and all(value == "pass" for value in gates.values()),
    }
    payload["contract"] = audit.get("contract")
    return payload


def cmd_audit(options: argparse.Namespace) -> int:
    root = options.root.resolve()
    payload = build_audit(root)
    errors = validate_artifact(payload, "destination-audit")
    if errors:
        print("error: produced invalid destination-audit artifact:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 2
    write_json(options.json_out, payload)
    print("Destination convention audit")
    contract = payload.get("contract")
    print(f"  Destination: {'present' if contract else 'missing'}")
    print(f"  bases: {len(payload['bases'])}")
    print(f"  leaves: {len(payload['leaves'])}")
    print(f"  findings: {len(payload['findings'])}")
    for item in payload["findings"][:20]:
        print(f"    - {item['rule']}: {item['message']}")
    if options.json_out is None:
        print_json(payload)
    return 0


def cmd_plan(options: argparse.Namespace) -> int:
    root = options.root.resolve()
    audit = None
    if options.audit:
        try:
            audit = load_json(options.audit)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    payload = build_plan(root, audit)
    errors = validate_artifact(payload, "destination-spec")
    if errors:
        print("error: produced invalid destination-spec artifact:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 2
    write_json(options.json_out, payload)
    dest = payload["destination"]
    print("Destination convention plan")
    print(f"  introduce: {dest['introduce']}")
    print(f"  module: {dest.get('module_path')}")
    print(f"  package: {dest.get('package')}")
    print(f"  conversions: {len(payload['conversions'])}")
    print(f"  unresolved: {len(payload['unresolved'])}")
    for item in payload["unresolved"]:
        print(f"    - {item['id']}: {item['message']}")
    if options.json_out is None:
        print_json(payload)
    return 0


def cmd_scaffold(options: argparse.Namespace) -> int:
    root = options.root.resolve()
    try:
        raw = load_json(options.spec)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    project = raw.get("project") or {}
    if project.get("has_navigation2") and not project.get("has_navigation3"):
        print(
            "error: Navigation 3 runtime is required before scaffolding Destination",
            file=sys.stderr,
        )
        return 2
    if (raw.get("gates") or {}).get("navigation3_runtime") == "fail":
        print("error: navigation3_runtime gate failed", file=sys.stderr)
        return 2
    try:
        spec = load_spec(options.spec)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return run_scaffold(root, spec, options.apply, options.force_unresolved)


def cmd_check(options: argparse.Namespace) -> int:
    root = options.root.resolve()
    spec = None
    if options.spec:
        try:
            spec = load_json(options.spec)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    payload = build_check(root, spec)
    errors = validate_artifact(payload, "destination-check")
    if errors:
        print("error: produced invalid destination-check artifact:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 2
    write_json(options.json_out, payload)
    passed = payload["summary"]["passed"]
    print("CHECK PASSED" if passed else "CHECK FAILED")
    print(f"  leaves: {payload['summary']['leaves']}")
    print(f"  errors: {payload['summary']['errors']}")
    print(f"  warnings: {payload['summary']['warnings']}")
    for item in payload["findings"]:
        print(f"    - {item['rule']}: {item['message']}")
    return 0 if passed else 1


def main(argv: list[str] | None = None) -> int:
    options = parse_args(argv)
    commands = {
        "audit": cmd_audit,
        "plan": cmd_plan,
        "scaffold": cmd_scaffold,
        "check": cmd_check,
    }
    return commands[options.command](options)


if __name__ == "__main__":
    raise SystemExit(main())
