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
    "Pods", "DerivedData", ".konan", "vendor", ".swiftpm-locks", ".build",
    "swiftPMCheckout", "Carthage", "xcuserdata", ".modularization",
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
    re.compile(r"project\(\s*path\s*[:=]\s*[\"'](:[^\"']+)[\"']"),
    re.compile(r"\bprojects\.([A-Za-z0-9_.]+)"),
]
PLUGIN_PATTERNS = [
    re.compile(r"alias\(\s*libs\.plugins\.([A-Za-z0-9_.-]+)\s*\)"),
    re.compile(r"id\(\s*[\"']([^\"']+)[\"']\s*\)"),
    re.compile(r"\bid\s+[\"']([^\"']+)[\"']"),
    re.compile(r"apply\s+plugin\s*:\s*[\"']([^\"']+)[\"']"),
    re.compile(r"kotlin\(\s*[\"']([^\"']+)[\"']\s*\)"),
]
DEPENDENCY_CALL_RE = re.compile(r"(?m)^\s*([A-Za-z][A-Za-z0-9.]*)\s*\(\s*(.+?)\s*\)\s*$")
DEPENDENCY_GROOVY_RE = re.compile(r"(?m)^\s*([A-Za-z][A-Za-z0-9.]*)\s+([^={}].+?)\s*$")
DEPENDENCY_SUFFIXES = ("implementation", "api", "compileonly", "runtimeonly", "processor", "kapt", "ksp")
INCLUDE_BUILD_RE = re.compile(r"includeBuild\s*(?:\(\s*)?[\"']([^\"']+)[\"']")
CAPABILITY_IMPORT_PREFIXES = {
    "ui": ("androidx.compose", "org.jetbrains.compose", "android.view", "android.widget", "javafx"),
    "navigation": ("androidx.navigation", "com.arkivanov.decompose", "cafe.adriel.voyager"),
    "dependency_injection": ("dagger", "javax.inject", "jakarta.inject", "org.koin", "dev.zacsweers.metro"),
    "networking": ("io.ktor", "retrofit2", "okhttp3", "com.apollographql"),
    "serialization": ("kotlinx.serialization", "com.squareup.moshi", "com.google.gson"),
    "persistence": ("androidx.room", "app.cash.sqldelight", "io.realm", "androidx.datastore"),
    "async": ("kotlinx.coroutines", "io.reactivex", "reactor.core"),
    "testing": ("kotlin.test", "org.junit", "app.cash.turbine", "io.mockk", "org.mockito"),
}
CAPABILITY_DEPENDENCY_TOKENS = {
    "ui": ("compose", "appcompat", "androidx.core", "material"),
    "navigation": ("navigation", "decompose", "voyager"),
    "dependency_injection": ("dagger", "hilt", "koin", "metro", "inject"),
    "networking": ("ktor", "retrofit", "okhttp", "apollo"),
    "serialization": ("serialization", "moshi", "gson"),
    "persistence": ("room", "sqldelight", "realm", "datastore"),
    "async": ("coroutines", "rxjava", "reactor"),
    "testing": ("junit", "kotlin-test", "turbine", "mock", "test"),
}
ARTIFACT_SUFFIX_KINDS = {
    ".sq": "database-schema",
    ".sqm": "database-migration",
    ".graphql": "network-schema",
    ".graphqls": "network-schema",
    ".proto": "serialization-schema",
    ".def": "native-interop",
    ".plist": "platform-resource",
    ".entitlements": "platform-resource",
    ".pro": "shrinker-rules",
    ".rules": "shrinker-rules",
    ".swift": "platform-source",
    ".m": "platform-source",
    ".mm": "platform-source",
    ".h": "native-header",
    ".storyboard": "platform-resource",
    ".xib": "platform-resource",
    ".strings": "platform-resource",
}


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


def included_build_roots(root: Path) -> set[Path]:
    settings = next((root / name for name in ("settings.gradle.kts", "settings.gradle") if (root / name).is_file()), None)
    if not settings:
        return set()
    text, _ = read_text(settings)
    result = set()
    for relative in INCLUDE_BUILD_RE.findall(text):
        candidate = (root / relative).resolve()
        if candidate != root and root in candidate.parents:
            result.add(candidate)
    return result


def walk_files(root: Path, excludes: set[str]) -> Iterable[Path]:
    included_builds = included_build_roots(root)
    for current, dirs, files in os.walk(root):
        current_path = Path(current)
        if current_path != root and any((current_path / name).is_file() for name in ("settings.gradle", "settings.gradle.kts")):
            if current_path.resolve() not in included_builds:
                dirs[:] = []
                continue
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


def project_dependencies(text: str) -> tuple[list[str], list[str]]:
    matches = sorted(
        ((match.start(), match.group(1)) for regex in PROJECT_DEP_RES for match in regex.finditer(text)),
        key=lambda item: item[0],
    )
    production: set[str] = set()
    tests: set[str] = set()
    for position, dependency in matches:
        if not dependency.startswith(":"):
            dependency = ":" + dependency.replace(".", ":")
        stack: list[str] = []
        last_boundary = 0
        for index, char in enumerate(text[:position]):
            if char == "{" and (index == 0 or text[index - 1] != "$"):
                stack.append(text[last_boundary:index].strip()[-160:])
                last_boundary = index + 1
            elif char == "}":
                if stack:
                    stack.pop()
                last_boundary = index + 1
            elif char == "\n" and not text[last_boundary:index].strip():
                last_boundary = index + 1
        line_prefix = text[text.rfind("\n", 0, position) + 1:position]
        context = " ".join(stack + [line_prefix]).lower()
        (tests if "test" in context else production).add(dependency)
    return sorted(production), sorted(tests)


def plugin_ids(text: str) -> list[str]:
    plugins: set[str] = set()
    for pattern in PLUGIN_PATTERNS:
        for match in pattern.finditer(text):
            line_end = text.find("\n", match.end())
            trailer = text[match.end():line_end if line_end >= 0 else len(text)].lower()
            if re.search(r"\bapply\s+false\b", trailer):
                continue
            plugins.add(match.group(1))
    return sorted(plugins)


def declared_dependencies(text: str) -> list[dict]:
    values: set[tuple[str, str]] = set()
    for pattern in (DEPENDENCY_CALL_RE, DEPENDENCY_GROOVY_RE):
        for match in pattern.finditer(text):
            configuration = match.group(1)
            if not configuration.lower().endswith(DEPENDENCY_SUFFIXES):
                continue
            expression = re.sub(r"\s+", " ", match.group(2).strip())
            quoted = re.search(r"[\"']([^\"']+)[\"']", expression)
            catalog = re.search(r"\blibs\.([A-Za-z0-9_.-]+)", expression)
            project = next((regex.search(expression) for regex in PROJECT_DEP_RES if regex.search(expression)), None)
            if project:
                value = project.group(1)
                if not value.startswith(":"):
                    value = ":" + value.replace(".", ":")
            elif catalog:
                value = "libs." + catalog.group(1)
            elif quoted:
                value = quoted.group(1)
            else:
                value = expression[:200]
            values.add((configuration, value))
    return [{"configuration": configuration, "value": value} for configuration, value in sorted(values)]


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
            "activity", "fragment", "viewmodel", "presenter", "uistate", "swiftui",
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


def feature_from_module(module: str | None) -> str | None:
    if not module:
        return None
    parts = [part.lower() for part in module.split(":") if part]
    for marker in ("feature", "features"):
        if marker in parts:
            index = parts.index(marker)
            if index + 1 < len(parts):
                return parts[index + 1]
    return None


def feature_from_explicit_path(path: Path) -> str | None:
    parts = [part.lower() for part in path.parts]
    for marker in ("feature", "features"):
        if marker in parts:
            index = parts.index(marker)
            if index + 1 < len(parts) and parts[index + 1] not in TECHNICAL_SEGMENTS:
                return parts[index + 1]
    return None


def module_allows_package_feature_inference(module: str | None) -> bool:
    if not module or module == ":":
        return True
    parts = [part.lower() for part in module.split(":") if part]
    if not parts:
        return True
    first = parts[0]
    last = parts[-1]
    return first in {"app", "application", "shared", "composeapp", "androidapp"} or last.endswith("app") or last == "application"


def feature_from_package(package: str | None, root_package: str | None, path: Path, module: str | None = None) -> str | None:
    module_feature = feature_from_module(module)
    if module_feature:
        return module_feature
    explicit_path_feature = feature_from_explicit_path(path)
    if explicit_path_feature:
        return explicit_path_feature
    parts = [p.lower() for p in path.parts]
    if parts and parts[0] in {"core", "util", "utility", "plugins", "build-logic", "buildsrc", "test"}:
        return None
    if not module_allows_package_feature_inference(module):
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


def source_set_for_path(path: Path) -> str | None:
    parts = path.parts
    if "src" in parts:
        index = parts.index("src")
        if index + 1 < len(parts):
            return parts[index + 1]
    return None


def artifact_kind(path: Path) -> str | None:
    lower_parts = [part.lower() for part in path.parts]
    lower_name = path.name.lower()
    if lower_name == "androidmanifest.xml":
        return "android-manifest"
    if "res" in lower_parts or "composeresources" in lower_parts:
        return "resource"
    if any(part.endswith(".xcassets") for part in lower_parts):
        return "platform-resource"
    if "schemas" in lower_parts and path.suffix.lower() == ".json":
        return "database-schema"
    if lower_name in {"consumer-rules.pro", "proguard-rules.pro"}:
        return "shrinker-rules"
    return ARTIFACT_SUFFIX_KINDS.get(path.suffix.lower())


def detect_cycles(graph: dict[str, list[str]]) -> list[list[str]]:
    state: dict[str, int] = {}
    stack: list[str] = []
    cycles: set[tuple[str, ...]] = set()

    def visit(node: str) -> None:
        state[node] = 1
        stack.append(node)
        for target in graph.get(node, []):
            if target not in graph:
                continue
            if state.get(target, 0) == 0:
                visit(target)
            elif state.get(target) == 1:
                index = stack.index(target)
                body = stack[index:]
                rotations = [tuple(body[i:] + body[:i]) for i in range(len(body))]
                cycles.add(min(rotations))
        stack.pop()
        state[node] = 2

    for node in graph:
        if state.get(node, 0) == 0:
            visit(node)
    return [list(cycle) + [cycle[0]] for cycle in sorted(cycles)]


def capability_inventory(modules: list[dict], sources: list[dict]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    plugins = sorted({plugin for module in modules for plugin in module["plugins"]})
    imports = sorted({imported for source in sources for imported in source["imports"]})
    dependencies = sorted({item["value"] for module in modules for item in module.get("declared_dependencies", [])})
    for capability, prefixes in CAPABILITY_IMPORT_PREFIXES.items():
        matched_imports = [value for value in imports if value.startswith(prefixes)]
        tokens = tuple(value.replace("_", "-") for value in capability.split("_"))
        matched_plugins = [value for value in plugins if any(token in value.lower() for token in tokens)]
        dependency_tokens = CAPABILITY_DEPENDENCY_TOKENS.get(capability, ())
        matched_dependencies = [value for value in dependencies if any(token in value.lower() for token in dependency_tokens)]
        if matched_imports or matched_plugins or matched_dependencies:
            result[capability] = {
                "plugins": matched_plugins[:30],
                "import_families": sorted({external_family(value) for value in matched_imports})[:30],
                "dependencies": matched_dependencies[:30],
            }
    return result


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
        deps, test_deps = project_dependencies(text)
        plugins = plugin_ids(text)
        modules.append({
            "path": module_dirs[build_file.parent],
            "directory": build_file.parent.relative_to(root).as_posix() or ".",
            "build_file": build_file.relative_to(root).as_posix(),
            "project_dependencies": deps,
            "test_project_dependencies": test_deps,
            "plugins": plugins,
            "declared_dependencies": declared_dependencies(text),
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
    artifact_paths = sorted(path for path in all_files if artifact_kind(path.relative_to(root)))
    artifacts: list[dict] = []
    for path in artifact_paths:
        relative = path.relative_to(root)
        module = owning_module(path, root, module_dirs)
        module_feature = feature_from_module(module)
        path_feature = feature_from_explicit_path(relative)
        artifacts.append({
            "path": relative.as_posix(),
            "module": module,
            "kind": artifact_kind(relative),
            "source_set": source_set_for_path(relative),
            "feature": module_feature or path_feature,
            "feature_confidence": "high" if module_feature or path_feature else "unknown",
            "feature_reason": "existing feature module path" if module_feature else "explicit feature path" if path_feature else "manual ownership required",
        })
    feature_counts: collections.Counter[str] = collections.Counter()
    ambiguous_feature_counts: collections.Counter[str] = collections.Counter()
    layer_counts: collections.Counter[str] = collections.Counter()
    external_imports: collections.Counter[str] = collections.Counter()
    package_owner: dict[str, str] = {}
    has_existing_feature_modules = any(feature_from_module(module["path"]) for module in modules)
    for source in raw_sources:
        path = Path(source["path"])
        module_feature = feature_from_module(source.get("module"))
        path_feature = feature_from_explicit_path(path)
        source["feature"] = feature_from_package(source["package"], root_package, path, source.get("module"))
        if module_feature:
            source["feature_confidence"] = "high"
            source["feature_reason"] = "existing feature module path"
        elif path_feature:
            source["feature_confidence"] = "high"
            source["feature_reason"] = "explicit feature path"
        elif source["feature"] and has_existing_feature_modules:
            source["feature_confidence"] = "low"
            source["feature_reason"] = "package candidate outside existing feature modules"
        elif source["feature"]:
            source["feature_confidence"] = "medium"
            source["feature_reason"] = "package candidate in monolithic module graph"
        else:
            source["feature_confidence"] = "unknown"
            source["feature_reason"] = "no feature evidence"
        if source["feature"] and source["feature_confidence"] != "low":
            feature_counts[source["feature"]] += 1
        elif source["feature"]:
            ambiguous_feature_counts[source["feature"]] += 1
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
    detected_plugin_ids = {plugin for module in modules for plugin in module["plugins"]}
    graph = {module["path"]: module["project_dependencies"] for module in modules}
    cycles = detect_cycles(graph)
    detected = {
        "gradle": bool(build_files or settings_files),
        "kotlin_multiplatform": any("multiplatform" in p.lower() or "kmp" in p.lower() for p in detected_plugin_ids),
        "android": any("android" in p.lower() for p in detected_plugin_ids) or any("/androidmain/" in s["path"].lower() for s in raw_sources),
        "compose": any("compose" in p.lower() for p in detected_plugin_ids) or any(i.startswith(("androidx.compose", "org.jetbrains.compose")) for s in raw_sources for i in s["imports"]),
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "root": ".",
        "project": {
            "name": root.name,
            "root_package": root_package,
            "detected": detected,
            "settings_files": sorted(settings_files),
            "version_catalogs": sorted(catalogs),
            "gradle_wrappers": sorted(wrappers),
            "included_builds": sorted(path.relative_to(root).as_posix() for path in included_build_roots(root)),
            "capabilities": capability_inventory(modules, raw_sources),
        },
        "summary": {
            "module_count": len(modules),
            "source_file_count": len(raw_sources),
            "owned_artifact_count": len(artifacts),
            "artifact_kinds": dict(collections.Counter(item["kind"] for item in artifacts).most_common()),
            "feature_candidates": dict(feature_counts.most_common()),
            "ambiguous_feature_candidates": dict(ambiguous_feature_counts.most_common()),
            "layer_candidates": dict(layer_counts.most_common()),
            "external_import_families": dict(external_imports.most_common(100)),
        },
        "modules": modules,
        "sources": raw_sources,
        "artifacts": artifacts,
        "feature_coupling": [
            {"from": source, "to": target, "import_count": count}
            for (source, target), count in sorted(coupling.items())
        ],
        "module_cycles": cycles,
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
        f"- Manifests/resources/schemas/native artifacts: {summary['owned_artifact_count']}",
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
    lines += ["", "Package-only candidates outside existing feature modules require review:", ""]
    if summary.get("ambiguous_feature_candidates"):
        for name, count in summary["ambiguous_feature_candidates"].items():
            lines.append(f"- `{name}`: {count} file(s)")
    else:
        lines.append("None.")
    lines += ["", "## Candidate layers", "", "| Layer | Files |", "|---|---:|"]
    for layer, count in summary["layer_candidates"].items():
        lines.append(f"| `{layer}` | {count} |")
    lines += ["", "## Existing module graph", ""]
    for module in data["modules"]:
        deps = ", ".join(f"`{d}`" for d in module["project_dependencies"]) or "none detected"
        lines.append(f"- `{module['path']}` → {deps}")
    lines += ["", "## Existing module cycles", ""]
    if data["module_cycles"]:
        for cycle in data["module_cycles"]:
            lines.append(f"- `{' -> '.join(cycle)}`")
    else:
        lines.append("None detected by static project dependency parsing.")
    lines += ["", "## Detected library capabilities", ""]
    if project.get("capabilities"):
        for name, evidence in sorted(project["capabilities"].items()):
            lines.append(f"- `{name}` — plugins: {evidence['plugins'] or 'none'}; dependencies: {evidence.get('dependencies') or 'none'}; imports: {evidence['import_families'] or 'none'}")
    else:
        lines.append("No capability evidence detected; inspect build files manually.")
    lines += ["", "## Cross-candidate imports", ""]
    if data["feature_coupling"]:
        for edge in sorted(data["feature_coupling"], key=lambda e: -e["import_count"]):
            lines.append(f"- `{edge['from']}` → `{edge['to']}`: {edge['import_count']} imports")
    else:
        lines.append("No cross-candidate imports detected.")
    def needs_manual_review(source: dict) -> bool:
        module_parts = [part.lower() for part in (source.get("module") or "").split(":") if part]
        stable_non_feature_owner = bool(
            module_parts and module_parts[0] in {"core", "util", "utility", "test", "build-logic", "buildsrc", "plugins"}
        )
        return (
            source.get("layer") == "unknown"
            or source.get("layer_confidence") == "low"
            or source.get("feature_confidence") == "low"
            or not stable_non_feature_owner and source.get("feature_confidence") == "unknown"
            or not stable_non_feature_owner and source.get("layer") == "platform"
        )

    uncertain = [source for source in data["sources"] if needs_manual_review(source)]
    lines += [
        "",
        "## Manual review queue",
        "",
        f"{len(uncertain)} file(s) have uncertain feature ownership, layer ownership, or platform placement.",
        "",
    ]
    for source in uncertain[:100]:
        lines.append(
            f"- `{source['path']}` — layer `{source['layer']}` ({source.get('layer_confidence', 'unknown')}), "
            f"feature `{source.get('feature') or 'unknown'}` ({source.get('feature_confidence', 'unknown')})"
        )
    if len(uncertain) > 100:
        lines.append(f"- … {len(uncertain) - 100} more in the JSON artifact")
    unresolved_artifacts = [item for item in data["artifacts"] if not item.get("feature") and not item.get("module")]
    lines += ["", "## Owned non-code artifacts", "", f"{len(data['artifacts'])} manifest/resource/schema/native artifact(s) inventoried.", ""]
    for kind, count in summary.get("artifact_kinds", {}).items():
        lines.append(f"- `{kind}`: {count}")
    if unresolved_artifacts:
        lines += ["", "Artifacts without a module or feature owner:", ""]
        for item in unresolved_artifacts[:100]:
            lines.append(f"- `{item['path']}` — `{item['kind']}`")
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
