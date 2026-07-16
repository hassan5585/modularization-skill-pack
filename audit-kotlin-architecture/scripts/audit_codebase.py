#!/usr/bin/env python3
"""Inventory a Kotlin/Gradle repository for modularization planning.

Uses only the Python standard library. It never edits production files; requested
JSON/Markdown outputs are the only writes.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys
from pathlib import Path
from typing import Iterable


SCHEMA_VERSION = 1
DEFAULT_EXCLUDES = {
    ".git", ".gradle", ".idea", ".kotlin", "build", "out", "node_modules",
    "Pods", "DerivedData", ".konan", "vendor",
}
TECHNICAL_SEGMENTS = {
    "app", "application", "common", "shared", "core", "base", "feature", "features",
    "domain", "data", "ui", "presentation", "navigation", "nav", "di", "util", "utils",
    "model", "models", "repository", "repositories", "impl", "internal", "platform",
    "plugin", "plugins", "test", "tests",
}
PACKAGE_RE = re.compile(r"(?m)^\s*package\s+([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)")
IMPORT_RE = re.compile(r"(?m)^\s*import\s+([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*(?:\.\*)?)")
PROJECT_DEP_RES = [
    re.compile(r"project\(\s*[\"'](:[^\"']+)[\"']\s*\)"),
    re.compile(r"project\(\s*path\s*=\s*[\"'](:[^\"']+)[\"']"),
]
PLUGIN_PATTERNS = [
    re.compile(r"alias\(\s*libs\.plugins\.([A-Za-z0-9_.-]+)\s*\)"),
    re.compile(r"id\(\s*[\"']([^\"']+)[\"']\s*\)"),
    re.compile(r"kotlin\(\s*[\"']([^\"']+)[\"']\s*\)"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--root-package", help="Override inferred internal root package")
    parser.add_argument("--exclude", action="append", default=[], help="Repository-relative path or directory name")
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--markdown-out", type=Path)
    return parser.parse_args()


def is_excluded(path: Path, root: Path, excludes: set[str]) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return True
    rel_posix = rel.as_posix()
    for part in rel.parts:
        if part in DEFAULT_EXCLUDES or part in excludes:
            return True
    return any(rel_posix == item or rel_posix.startswith(item.rstrip("/") + "/") for item in excludes)


def walk_files(root: Path, excludes: set[str]) -> Iterable[Path]:
    for current, dirs, files in os.walk(root):
        current_path = Path(current)
        dirs[:] = [d for d in dirs if not is_excluded(current_path / d, root, excludes)]
        for name in files:
            path = current_path / name
            if not is_excluded(path, root, excludes):
                yield path


def read_text(path: Path) -> tuple[str, str | None]:
    try:
        return path.read_text(encoding="utf-8"), None
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="utf-8", errors="replace"), "invalid UTF-8 replaced"
        except OSError as exc:
            return "", str(exc)
    except OSError as exc:
        return "", str(exc)


def module_path_for(build_file: Path, root: Path) -> str:
    rel = build_file.parent.relative_to(root)
    return ":" + ":".join(rel.parts) if rel.parts else ":"


def owning_module(path: Path, root: Path, module_dirs: dict[Path, str]) -> str | None:
    parent = path.parent
    while parent == root or root in parent.parents:
        if parent in module_dirs:
            return module_dirs[parent]
        if parent == root:
            break
        parent = parent.parent
    return None


def infer_root_package(packages: list[str]) -> str | None:
    if not packages:
        return None
    split = [p.split(".") for p in packages]
    common: list[str] = []
    for parts in zip(*split):
        if len(set(parts)) == 1:
            common.append(parts[0])
        else:
            break
    if len(common) >= 2:
        return ".".join(common[:3])
    prefixes = collections.Counter(".".join(p[:2]) for p in split if len(p) >= 2)
    return prefixes.most_common(1)[0][0] if prefixes else None


def classify_layer(path: Path, text: str, detect_tests: bool = True) -> tuple[str, str, dict[str, int]]:
    lower_path = path.as_posix().lower()
    lower = text.lower()
    parts = {part.lower() for part in path.parts}

    if detect_tests and (any(token in parts for token in {"test", "tests", "commontest", "androidtest", "androidhosttest", "jvmtest", "iostest"}) or path.stem.lower().endswith("test")):
        return "test", "high", {"test": 10}

    scores: collections.Counter[str] = collections.Counter()
    path_terms = {
        "domain": {"domain", "usecase", "usecases", "policy", "policies"},
        "data": {"data", "remote", "local", "database", "db", "dao", "dto", "network", "cache"},
        "navigation": {"navigation", "nav", "route", "routes", "destination", "destinations", "deeplink"},
        "ui": {"ui", "presentation", "screen", "screens", "view", "views", "widget", "widgets", "theme"},
    }
    for layer, terms in path_terms.items():
        scores[layer] += 5 * len(parts.intersection(terms))

    signals = {
        "ui": [
            "androidx.compose", "@composable", "android.view.", "android.widget.",
            "fragment", "viewmodel", "presenter", "uistate", "swiftui",
        ],
        "data": [
            "io.ktor", "retrofit", "okhttp", "androidx.room", "sqldelight", "realm",
            "@entity", "@dao", "database", "datasource", "dto", "request", "response",
            "repositoryimpl", "realrepository", "remote", "localdatasource",
        ],
        "navigation": [
            "androidx.navigation", "destination", "navgraph", "deeplink", "route", "navigator",
        ],
        "domain": [
            "usecase", "repository", "policy", "domain", "sealed interface", "valueobject",
        ],
    }
    for layer, terms in signals.items():
        scores[layer] += sum(2 for term in terms if term in lower)

    if any(seg in lower_path for seg in ("/androidmain/", "/iosmain/", "/jvmmain/", "/nativemain/")):
        scores["platform"] += 2
    if any(term in lower for term in ("android.content.", "platform.foundation", "platform.uikit", "java.nio.file")):
        scores["platform"] += 3
    if "/di/" in lower_path or path.stem.lower().endswith("module") and any(term in lower for term in ("@module", "koin", "metro", "dagger", "provides")):
        scores["di"] += 4

    if not scores or scores.most_common(1)[0][1] <= 1:
        return "unknown", "low", dict(scores)
    ordered = scores.most_common()
    top, top_score = ordered[0]
    second = ordered[1][1] if len(ordered) > 1 else 0
    confidence = "high" if top_score >= 6 and top_score - second >= 3 else "medium" if top_score >= 3 and top_score > second else "low"
    return top, confidence, dict(scores)


def feature_from_package(package: str | None, root_package: str | None, path: Path) -> str | None:
    parts = [p.lower() for p in path.parts]
    for marker in ("feature", "features"):
        if marker in parts:
            index = parts.index(marker)
            if index + 1 < len(parts) and parts[index + 1] not in TECHNICAL_SEGMENTS:
                return parts[index + 1]
    if parts and parts[0] in {"core", "util", "utility", "plugins", "build-logic", "buildsrc", "test"}:
        return None
    if package and root_package and (package == root_package or package.startswith(root_package + ".")):
        remainder = package[len(root_package):].lstrip(".").split(".")
        for segment in remainder:
            if segment and segment.lower() not in TECHNICAL_SEGMENTS:
                return segment.lower()
    return None


def external_family(import_path: str) -> str:
    parts = import_path.rstrip(".*").split(".")
    return ".".join(parts[: min(3, len(parts))])


def build_inventory(root: Path, excludes: set[str], root_package_override: str | None) -> dict:
    all_files = list(walk_files(root, excludes))
    build_files = sorted(p for p in all_files if p.name in {"build.gradle", "build.gradle.kts"})
    module_dirs = {p.parent: module_path_for(p, root) for p in build_files}
    parse_warnings: list[dict] = []

    modules = []
    for build_file in build_files:
        text, error = read_text(build_file)
        if error:
            parse_warnings.append({"path": build_file.relative_to(root).as_posix(), "warning": error})
        deps = sorted({match.group(1) for regex in PROJECT_DEP_RES for match in regex.finditer(text)})
        plugins = sorted({match.group(1) for regex in PLUGIN_PATTERNS for match in regex.finditer(text)})
        modules.append({
            "path": module_dirs[build_file.parent],
            "directory": build_file.parent.relative_to(root).as_posix() or ".",
            "build_file": build_file.relative_to(root).as_posix(),
            "project_dependencies": deps,
            "plugins": plugins,
        })

    source_paths = sorted(p for p in all_files if p.suffix in {".kt", ".java"})
    raw_sources: list[dict] = []
    packages: list[str] = []
    for path in source_paths:
        text, error = read_text(path)
        rel = path.relative_to(root).as_posix()
        if error:
            parse_warnings.append({"path": rel, "warning": error})
        package_match = PACKAGE_RE.search(text)
        package = package_match.group(1) if package_match else None
        if package:
            packages.append(package)
        imports = sorted(set(IMPORT_RE.findall(text)))
        relative_path = path.relative_to(root)
        layer, confidence, scores = classify_layer(relative_path, text)
        module = owning_module(path, root, module_dirs)
        test_kind = None
        test_target_layer = None
        if layer == "test":
            if module and module.split(":")[-1].lower() in {"test", "test-support", "fixtures"}:
                test_kind = "reusable-test-support"
            else:
                test_kind = "owning-module-test"
                module_role = module.split(":")[-1].lower() if module else None
                if module_role in {"domain", "data", "navigation", "ui"}:
                    test_target_layer = module_role
                else:
                    inferred_test_layer, _, _ = classify_layer(relative_path, text, detect_tests=False)
                    test_target_layer = inferred_test_layer if inferred_test_layer in {"domain", "data", "navigation", "ui"} else None
        raw_sources.append({
            "path": rel,
            "language": path.suffix.lstrip("."),
            "module": module,
            "package": package,
            "imports": imports,
            "layer": layer,
            "layer_confidence": confidence,
            "layer_scores": scores,
            "test_kind": test_kind,
            "test_target_layer": test_target_layer,
        })

    root_package = root_package_override or infer_root_package(packages)
    feature_counts: collections.Counter[str] = collections.Counter()
    layer_counts: collections.Counter[str] = collections.Counter()
    external_imports: collections.Counter[str] = collections.Counter()
    package_owner: dict[str, str] = {}
    for source in raw_sources:
        source["feature"] = feature_from_package(source["package"], root_package, Path(source["path"]))
        if source["feature"]:
            feature_counts[source["feature"]] += 1
        layer_counts[source["layer"]] += 1
        if source["package"] and source["module"]:
            package_owner[source["package"]] = source["module"]
        for imported in source["imports"]:
            if not root_package or not (imported == root_package or imported.startswith(root_package + ".")):
                external_imports[external_family(imported)] += 1

    coupling: collections.Counter[tuple[str, str]] = collections.Counter()
    for source in raw_sources:
        source_feature = source.get("feature")
        if not source_feature:
            continue
        for imported in source["imports"]:
            target_feature = feature_from_package(imported.rstrip(".*"), root_package, Path("."))
            if target_feature and target_feature != source_feature:
                coupling[(source_feature, target_feature)] += 1

    settings_files = [p.relative_to(root).as_posix() for p in all_files if p.name in {"settings.gradle", "settings.gradle.kts"}]
    catalogs = [p.relative_to(root).as_posix() for p in all_files if p.name == "libs.versions.toml"]
    wrappers = [p.relative_to(root).as_posix() for p in all_files if p.name == "gradle-wrapper.properties"]
    plugin_ids = {plugin for module in modules for plugin in module["plugins"]}
    detected = {
        "gradle": bool(build_files or settings_files),
        "kotlin_multiplatform": any("multiplatform" in p.lower() or "kmp" in p.lower() for p in plugin_ids),
        "android": any("android" in p.lower() for p in plugin_ids) or any("/androidmain/" in s["path"].lower() for s in raw_sources),
        "compose": any("compose" in p.lower() for p in plugin_ids) or any(i.startswith(("androidx.compose", "org.jetbrains.compose")) for s in raw_sources for i in s["imports"]),
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "root": str(root),
        "project": {
            "root_package": root_package,
            "detected": detected,
            "settings_files": sorted(settings_files),
            "version_catalogs": sorted(catalogs),
            "gradle_wrappers": sorted(wrappers),
        },
        "summary": {
            "module_count": len(modules),
            "source_file_count": len(raw_sources),
            "feature_candidates": dict(feature_counts.most_common()),
            "layer_candidates": dict(layer_counts.most_common()),
            "external_import_families": dict(external_imports.most_common(100)),
        },
        "modules": modules,
        "sources": raw_sources,
        "feature_coupling": [
            {"from": source, "to": target, "import_count": count}
            for (source, target), count in sorted(coupling.items())
        ],
        "parse_warnings": parse_warnings,
    }


def markdown_report(data: dict) -> str:
    project = data["project"]
    summary = data["summary"]
    lines = [
        "# Kotlin architecture audit",
        "",
        f"- Root package: `{project.get('root_package') or 'not inferred'}`",
        f"- Modules: {summary['module_count']}",
        f"- Kotlin/Java source files: {summary['source_file_count']}",
        f"- Detected platform flags: `{json.dumps(project['detected'], sort_keys=True)}`",
        "",
        "## Candidate features",
        "",
        "| Candidate | Files |",
        "|---|---:|",
    ]
    for name, count in summary["feature_candidates"].items():
        lines.append(f"| `{name}` | {count} |")
    if not summary["feature_candidates"]:
        lines.append("| _No reliable candidates_ | 0 |")
    lines += ["", "## Candidate layers", "", "| Layer | Files |", "|---|---:|"]
    for layer, count in summary["layer_candidates"].items():
        lines.append(f"| `{layer}` | {count} |")
    lines += ["", "## Existing module graph", ""]
    for module in data["modules"]:
        deps = ", ".join(f"`{d}`" for d in module["project_dependencies"]) or "none detected"
        lines.append(f"- `{module['path']}` → {deps}")
    lines += ["", "## Cross-candidate imports", ""]
    if data["feature_coupling"]:
        for edge in sorted(data["feature_coupling"], key=lambda e: -e["import_count"]):
            lines.append(f"- `{edge['from']}` → `{edge['to']}`: {edge['import_count']} imports")
    else:
        lines.append("No cross-candidate imports detected.")
    uncertain = [s for s in data["sources"] if s["layer"] == "unknown" or s["layer_confidence"] == "low"]
    lines += ["", "## Manual review queue", "", f"{len(uncertain)} low-confidence or unknown files.", ""]
    for source in uncertain[:100]:
        lines.append(f"- `{source['path']}` — layer `{source['layer']}`, feature `{source.get('feature') or 'unknown'}`")
    if len(uncertain) > 100:
        lines.append(f"- … {len(uncertain) - 100} more in the JSON artifact")
    lines += ["", "## Parse warnings", ""]
    if data["parse_warnings"]:
        for warning in data["parse_warnings"]:
            lines.append(f"- `{warning['path']}`: {warning['warning']}")
    else:
        lines.append("None.")
    lines += [
        "",
        "> Heuristic classifications are proposals. Review them against product flows, routes, APIs, persistence, tests, and project documentation before moving code.",
        "",
    ]
    return "\n".join(lines)


def write_output(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    if not root.is_dir():
        print(f"error: root is not a directory: {root}", file=sys.stderr)
        return 2
    data = build_inventory(root, set(args.exclude), args.root_package)
    markdown = markdown_report(data)
    if args.json_out:
        write_output(args.json_out.resolve(), json.dumps(data, indent=2, sort_keys=True) + "\n")
    if args.markdown_out:
        write_output(args.markdown_out.resolve(), markdown)
    if not args.json_out and not args.markdown_out:
        print(markdown)
    else:
        if args.json_out:
            print(f"Wrote JSON audit: {args.json_out}")
        if args.markdown_out:
            print(f"Wrote Markdown audit: {args.markdown_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
