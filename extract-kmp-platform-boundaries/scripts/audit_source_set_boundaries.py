#!/usr/bin/env python3
"""Audit platform imports and source-set ownership in a Kotlin/Gradle repository.

Read-only. Flags Android/Java/Cocoa/native imports living in portable layers.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


SCHEMA_VERSION = 1
SCRIPT_VERSION = "1"
SKILL = "extract-kmp-platform-boundaries"

_PACK_ROOT = Path(__file__).resolve().parents[2]
if str(_PACK_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACK_ROOT))
from common.gradle_graph import (  # type: ignore
    IMPORT_RE,
    PACKAGE_RE,
    discover_modules,
    is_portable_source_set,
    platform_kind_for_import,
    source_set_for_path,
    walk_files,
)

EXPECT_RE = re.compile(r"(?m)^\s*expect\s+")
ACTUAL_RE = re.compile(r"(?m)^\s*actual\s+")
EXPECT_NAME_RE = re.compile(
    r"(?m)^\s*expect\s+(?:class|interface|object|fun|val|var)\s+([A-Za-z_]\w*)"
)
ACTUAL_NAME_RE = re.compile(
    r"(?m)^\s*actual\s+(?:class|interface|object|fun|val|var)\s+([A-Za-z_]\w*)"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--json-out", type=Path)
    return parser.parse_args()


def targets_from_build(text: str) -> list[str]:
    found = []
    for name in (
        "androidTarget",
        "android()",
        "jvm()",
        "iosArm64",
        "iosSimulatorArm64",
        "iosX64",
        "macosArm64",
        "js(",
        "wasmJs",
    ):
        if name.rstrip("(") in text or name in text:
            found.append(name.rstrip("()"))
    return sorted(set(found))


def classify_capability(path: str, source_set: str | None, platform_kind: str | None, text: str) -> str:
    lower = path.lower()
    if "iosappbridge" in lower or "mainactivity" in lower or lower.endswith("app.kt"):
        return "platform-entry-point"
    if EXPECT_RE.search(text):
        return "platform-primitive"
    if platform_kind in {"android", "apple", "jvm"} and not is_portable_source_set(source_set):
        return "native-interop" if platform_kind == "apple" else "platform-primitive"
    if platform_kind and is_portable_source_set(source_set):
        return "replaceable-service-contract"
    return "pure-common-logic"


def audit(root: Path) -> dict:
    modules = discover_modules(root)
    findings = []
    sources = []
    expects: dict[str, list[str]] = {}
    actuals: dict[str, list[str]] = {}
    targets = set()
    for module in modules:
        build = root / module["build_file"]
        if build.is_file():
            targets.update(targets_from_build(build.read_text(encoding="utf-8", errors="replace")))
    for path in walk_files(root):
        if path.suffix not in {".kt", ".java"}:
            continue
        rel = path.relative_to(root)
        rel_s = rel.as_posix()
        if any(part in rel.parts for part in ("generated", "build")):
            continue
        source_set = source_set_for_path(rel)
        text = path.read_text(encoding="utf-8", errors="replace")
        package_match = PACKAGE_RE.search(text)
        imports = IMPORT_RE.findall(text)
        platform_imports = []
        for item in imports:
            kind = platform_kind_for_import(item)
            if kind:
                platform_imports.append({"import": item, "kind": kind})
                if is_portable_source_set(source_set):
                    findings.append(
                        {
                            "rule": "platform-import-in-portable-source-set",
                            "severity": "error",
                            "path": rel_s,
                            "source_set": source_set,
                            "import": item,
                            "platform": kind,
                            "evidence": f"{kind} import in portable source set {source_set or 'unknown'}",
                        }
                    )
        for name in EXPECT_NAME_RE.findall(text):
            expects.setdefault(name, []).append(rel_s)
        for name in ACTUAL_NAME_RE.findall(text):
            actuals.setdefault(name, []).append(rel_s)
        # platform impl in feature domain
        if "/domain/" in rel_s and platform_imports and source_set and not is_portable_source_set(source_set):
            findings.append(
                {
                    "rule": "platform-implementation-in-feature-domain",
                    "severity": "warning",
                    "path": rel_s,
                    "source_set": source_set,
                    "evidence": "Platform implementation appears under a domain path",
                }
            )
        capability = classify_capability(
            rel_s,
            source_set,
            platform_imports[0]["kind"] if platform_imports else None,
            text,
        )
        sources.append(
            {
                "path": rel_s,
                "package": package_match.group(1) if package_match else None,
                "source_set": source_set,
                "platform_imports": platform_imports,
                "capability": capability,
                "portable": is_portable_source_set(source_set),
            }
        )
    for name, locations in sorted(expects.items()):
        if name not in actuals:
            findings.append(
                {
                    "rule": "expect-without-actual",
                    "severity": "error",
                    "symbol": name,
                    "path": locations[0],
                    "evidence": f"expect {name} has no matching actual in scanned sources",
                }
            )
    # Valid platform imports in matching source sets are not findings — recorded as observed
    valid_platform = [
        s
        for s in sources
        if s["platform_imports"] and not s["portable"]
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "generator": {"skill": SKILL, "script": "audit_source_set_boundaries.py", "version": SCRIPT_VERSION},
        "repository": {"root": ".", "revision": None},
        "inputs": {},
        "targets": sorted(targets),
        "modules": [m["path"] for m in modules],
        "sources": sources,
        "findings": findings,
        "expect_actual": {
            "expects": {k: v for k, v in sorted(expects.items())},
            "actuals": {k: v for k, v in sorted(actuals.items())},
        },
        "observed": {
            "valid_platform_source_files": len(valid_platform),
            "portable_files_with_platform_imports": sum(
                1 for s in sources if s["platform_imports"] and s["portable"]
            ),
        },
        "gates": {
            "portable_platform_imports": "fail"
            if any(f["rule"] == "platform-import-in-portable-source-set" for f in findings)
            else "pass",
            "expect_actual_pairs": "fail"
            if any(f["rule"] == "expect-without-actual" for f in findings)
            else "pass",
        },
        "unresolved": [],
        "recommendations": [
            "Prefer injected interfaces for replaceable business-facing services.",
            "Use expect/actual only for narrow platform primitives with identical semantics.",
            "Keep platform entry points in app/shell modules.",
        ],
        "verification": [
            ["./gradlew", "compileKotlinMetadata", "--quiet"],
            ["./gradlew", "compileDebugKotlinAndroid", "--quiet"],
            ["./gradlew", "compileKotlinIosSimulatorArm64", "--quiet"],
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
        print(f"Wrote platform boundary audit to {options.json_out}")
    else:
        sys.stdout.write(text)
    if report["gates"]["portable_platform_imports"] == "fail":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
