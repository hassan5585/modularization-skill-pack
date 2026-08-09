#!/usr/bin/env python3
"""Inventory public Kotlin declarations and Gradle api/implementation visibility.

Produces review candidates only — does not rewrite visibility.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


SCHEMA_VERSION = 1
SCRIPT_VERSION = "1"
SKILL = "harden-kotlin-module-apis"

_PACK_ROOT = Path(__file__).resolve().parents[2]
if str(_PACK_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACK_ROOT))
from common.gradle_graph import (  # type: ignore
    IMPORT_RE,
    PACKAGE_RE,
    discover_modules,
    walk_files,
)

DECL_RE = re.compile(
    r"(?m)^(?P<indent>\s*)(?P<mods>(?:(?:public|internal|private|protected|open|abstract|final|sealed|data|inline|value|enum|annotation|expect|actual|suspend|override|tailrec|operator|infix)\s+)*)"
    r"(?P<kind>class|interface|object|fun|val|val|var|typealias|enum\s+class|sealed\s+class|sealed\s+interface)\s+(?P<name>[A-Za-z_]\w*)"
)
GENERATED_MARKERS = ("build/", "generated/", "ksp/", "build/generated")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--json-out", type=Path)
    return parser.parse_args()


def visibility_of(mods: str) -> str:
    for token in ("private", "protected", "internal", "public"):
        if re.search(rf"\b{token}\b", mods):
            return token
    return "public"  # Kotlin default


def classify_declaration(name: str, kind: str, path: str, module: str | None) -> str:
    lower = name.lower()
    path_l = path.lower()
    role = (module or "").split(":")[-1].lower() if module else ""
    if any(marker in path_l for marker in GENERATED_MARKERS):
        return "generated-api"
    if "iosappbridge" in lower or path_l.endswith("iosappbridge.kt"):
        return "swift-facing-bridge"
    if name.startswith("Real") or name.endswith("Impl") or name.endswith("Implementation"):
        return "implementation-detail"
    if kind == "interface" or name.endswith("Repository") or name.endswith("UseCase"):
        return "stable-contract"
    if (
        ("response" in lower or "request" in lower or lower.endswith("dto") or lower.endswith("entity"))
        and ("class" in kind or kind == "object")
    ):
        return "wire-persistence-dto"
    if role == "data" and ("class" in kind or kind == "object") and not name.startswith("Real"):
        # Public data-layer types without Impl naming are DTO leakage candidates
        if any(token in lower for token in ("dto", "entity", "response", "request", "model")):
            return "wire-persistence-dto"
    if role in {"", module} and module and module.count(":") <= 2 and role not in {
        "domain",
        "data",
        "ui",
        "navigation",
        "test",
        "real",
    }:
        if kind in {"class", "object", "interface"}:
            # aggregation facade heuristic
            if path.endswith("Module.kt") or "Facade" in name:
                return "aggregation-facade"
    if kind in {"class", "object"} and role in {"data", "real"}:
        return "implementation-detail"
    return "unresolved"


def module_for(path: Path, root: Path, modules: list[dict]) -> str | None:
    dirs = {(root / m["directory"]).resolve(): m["path"] for m in modules}
    current = path.parent.resolve()
    root = root.resolve()
    while True:
        if current in dirs:
            return dirs[current]
        if current == root or root not in current.parents:
            return None
        current = current.parent


def audit(root: Path) -> dict:
    modules = discover_modules(root)
    declarations = []
    findings = []
    api_edges = []
    for module in modules:
        for dep in module.get("declared_dependencies") or []:
            if dep.get("visibility") == "api" and "test" not in dep.get("configuration", "").lower():
                api_edges.append(
                    {
                        "source": module["path"],
                        "target": dep["target"],
                        "configuration": dep["configuration"],
                        "expression": dep.get("expression"),
                    }
                )
    # Public declarations + consumers via imports
    package_owners: dict[str, str] = {}
    for path in walk_files(root):
        if path.suffix not in {".kt", ".java"}:
            continue
        rel = path.relative_to(root).as_posix()
        if any(marker in rel for marker in GENERATED_MARKERS):
            continue
        module = module_for(path, root, modules)
        text = path.read_text(encoding="utf-8", errors="replace")
        package_match = PACKAGE_RE.search(text)
        package = package_match.group(1) if package_match else None
        if package and module:
            package_owners[package] = module
        for match in DECL_RE.finditer(text):
            mods = match.group("mods") or ""
            kind = match.group("kind").replace("  ", " ")
            name = match.group("name")
            visibility = visibility_of(mods)
            classification = classify_declaration(name, kind, rel, module)
            decl = {
                "module": module,
                "path": rel,
                "package": package,
                "name": name,
                "kind": kind,
                "visibility": visibility,
                "classification": classification,
            }
            declarations.append(decl)
            if visibility == "public" and classification == "implementation-detail":
                findings.append(
                    {
                        "rule": "public-implementation",
                        "severity": "warning",
                        "module": module,
                        "path": rel,
                        "symbol": name,
                        "evidence": f"public {kind} {name} classified as implementation detail",
                    }
                )
            if visibility == "public" and classification == "wire-persistence-dto" and module and module.endswith(":data"):
                findings.append(
                    {
                        "rule": "dto-leakage-candidate",
                        "severity": "warning",
                        "module": module,
                        "path": rel,
                        "symbol": name,
                        "evidence": "public data-layer DTO may leak through domain APIs",
                    }
                )
    # Cross-module consumers of packages
    consumers: dict[str, set[str]] = defaultdict(set)
    for path in walk_files(root):
        if path.suffix not in {".kt", ".java"}:
            continue
        module = module_for(path, root, modules)
        if not module:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for imported in IMPORT_RE.findall(text):
            cleaned = imported.rstrip(".*")
            for package, owner in package_owners.items():
                if cleaned == package or cleaned.startswith(package + "."):
                    if owner != module:
                        consumers[f"{owner}:{package}"].add(module)
    for edge in api_edges:
        # Unjustified if target is not aggregation facade child pattern and no rule yet
        source_role = edge["source"].split(":")[-1]
        target_role = edge["target"].split(":")[-1]
        justified = False
        if source_role not in {"domain", "data", "ui", "navigation", "test", "real"} and edge["target"].startswith(
            edge["source"] + ":"
        ):
            justified = True  # aggregation re-export of own children
        if target_role in {"navigation"} and "navigation" in edge["source"]:
            justified = True
        findings.append(
            {
                "rule": "api-project-dependency",
                "severity": "info" if justified else "warning",
                "source": edge["source"],
                "target": edge["target"],
                "justified_heuristic": justified,
                "evidence": edge.get("expression") or edge["configuration"],
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "generator": {"skill": SKILL, "script": "audit_module_apis.py", "version": SCRIPT_VERSION},
        "repository": {"root": ".", "revision": None},
        "inputs": {},
        "modules": [
            {
                "path": m["path"],
                "api_dependencies": [
                    d["target"]
                    for d in m.get("declared_dependencies") or []
                    if d.get("visibility") == "api" and "test" not in d.get("configuration", "").lower()
                ],
                "implementation_dependencies": [
                    d["target"]
                    for d in m.get("declared_dependencies") or []
                    if d.get("visibility") != "api" and "test" not in d.get("configuration", "").lower()
                ],
            }
            for m in modules
        ],
        "declarations": declarations,
        "api_edges": api_edges,
        "cross_module_package_consumers": {
            key: sorted(values) for key, values in sorted(consumers.items())
        },
        "findings": findings,
        "unresolved": [d for d in declarations if d["classification"] == "unresolved"][:100],
        "gates": {
            "public_implementations": "review"
            if any(f["rule"] == "public-implementation" for f in findings)
            else "pass",
            "api_edges_reviewed": "review" if api_edges else "pass",
        },
        "recommendations": [
            "Treat static classifications as review candidates, not automatic rewrites.",
            "Change one module at a time and compile all known consumers.",
            "Keep Swift-facing bridges explicit; hide non-bridge Kotlin from the framework header.",
        ],
    }


def main() -> int:
    options = parse_args()
    root = options.root.resolve()
    if not root.is_dir():
        print(f"error: root is not a directory: {root}", file=sys.stderr)
        return 2
    report = audit(root)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if options.json_out:
        options.json_out.parent.mkdir(parents=True, exist_ok=True)
        options.json_out.write_text(text, encoding="utf-8")
        print(f"Wrote API surface report to {options.json_out}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
