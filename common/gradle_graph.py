#!/usr/bin/env python3
"""Shared Gradle/project-graph helpers used by modularization analysis scripts."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Iterable


DEFAULT_EXCLUDES = {
    ".git",
    ".gradle",
    ".idea",
    ".kotlin",
    "build",
    "out",
    "node_modules",
    "Pods",
    "DerivedData",
    ".konan",
    "vendor",
    ".swiftpm-locks",
    ".build",
    "swiftPMCheckout",
    "Carthage",
    "xcuserdata",
    ".modularization",
    "generated",
}

PROJECT_DEP_RES = (
    re.compile(r"project\(\s*[\"'](:[^\"']+)[\"']\s*\)"),
    re.compile(r"project\(\s*path\s*[:=]\s*[\"'](:[^\"']+)[\"']"),
    re.compile(r"(?<![A-Za-z0-9_.])projects\.([A-Za-z0-9_.]+)"),
)
DEPENDENCY_CALL_RE = re.compile(r"(?m)^\s*([A-Za-z][A-Za-z0-9.]*)\s*\(\s*(.+?)\s*\)\s*$")
PACKAGE_RE = re.compile(r"(?m)^\s*package\s+([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)")
IMPORT_RE = re.compile(r"(?m)^\s*import\s+([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*(?:\.\*)?)")
PUBLIC_DECL_RE = re.compile(
    r"(?m)^\s*(?:(?:public|internal|private|protected|open|abstract|final|sealed|data|inline|value|enum|annotation|expect|actual)\s+)*"
    r"(class|interface|object|fun|val|var|typealias|enum\s+class|sealed\s+class|sealed\s+interface)\s+([A-Za-z_]\w*)"
)
VISIBILITY_RE = re.compile(r"\b(public|internal|private|protected)\b")
PLATFORM_IMPORT_PREFIXES = (
    "android.",
    "androidx.",
    "java.",
    "javax.",
    "dalvik.",
    "kotlinx.cinterop",
    "platform.",
    "cocoapods.",
    "com.apple.",
    "org.jetbrains.skiko",
)
ANDROID_IMPORT_PREFIXES = ("android.", "androidx.", "dalvik.")
JVM_IMPORT_PREFIXES = ("java.", "javax.")
COCOA_IMPORT_PREFIXES = ("platform.", "cocoapods.", "com.apple.", "kotlinx.cinterop")


def gradle_accessor_segment(segment: str) -> str:
    parts = re.split(r"[-_]+", segment)
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


def gradle_project_accessor(module: str) -> str:
    return ".".join(gradle_accessor_segment(segment) for segment in module.split(":") if segment)


def normalize_project_dependency(value: str, known_modules: set[str] | None = None) -> str:
    if value.startswith(":"):
        return value
    if known_modules:
        matches = [module for module in known_modules if gradle_project_accessor(module) == value]
        if len(matches) == 1:
            return matches[0]
    segments = value.split(".")
    literal = ":" + ":".join(segments)
    kebab = ":" + ":".join(
        re.sub(r"(?<!^)(?=[A-Z])", "-", segment).lower() for segment in segments
    )
    if known_modules:
        for candidate in (literal, kebab):
            if candidate in known_modules:
                return candidate
    return kebab if "sharedUi" in segments else literal


def strip_gradle_comments(text: str) -> str:
    result: list[str] = []
    index = 0
    quote: str | None = None
    triple_quoted = False
    block_depth = 0
    while index < len(text):
        if block_depth and text.startswith("/*", index):
            block_depth += 1
            result.append("  ")
            index += 2
        elif block_depth and text.startswith("*/", index):
            block_depth -= 1
            result.append("  ")
            index += 2
        elif block_depth:
            result.append("\n" if text[index] == "\n" else " ")
            index += 1
        elif quote and triple_quoted:
            delimiter = quote * 3
            if text.startswith(delimiter, index):
                result.append(delimiter)
                index += 3
                quote = None
                triple_quoted = False
            else:
                result.append(text[index])
                index += 1
        elif quote:
            character = text[index]
            result.append(character)
            index += 1
            if character == "\\" and index < len(text):
                result.append(text[index])
                index += 1
            elif character == quote:
                quote = None
        elif text.startswith("//", index):
            while index < len(text) and text[index] != "\n":
                index += 1
        elif text.startswith("/*", index):
            block_depth = 1
            result.append("  ")
            index += 2
        elif text[index] in {'"', "'"}:
            quote = text[index]
            triple_quoted = text.startswith(quote * 3, index)
            result.append(quote * 3 if triple_quoted else quote)
            index += 3 if triple_quoted else 1
        else:
            result.append(text[index])
            index += 1
    return "".join(result)


def is_excluded(path: Path, root: Path, excludes: set[str] | None = None) -> bool:
    banned = excludes or DEFAULT_EXCLUDES
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return True
    return any(part in banned for part in parts)


def walk_files(root: Path, excludes: set[str] | None = None) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if is_excluded(path, root, excludes):
            continue
        yield path


def module_path_for(build_file: Path, root: Path) -> str:
    relative = build_file.parent.relative_to(root)
    if relative == Path("."):
        return ":"
    return ":" + ":".join(relative.parts)


def discover_modules(root: Path, excludes: set[str] | None = None) -> list[dict]:
    modules: list[dict] = []
    build_files = [
        path
        for path in walk_files(root, excludes)
        if path.name in {"build.gradle", "build.gradle.kts"}
    ]
    known = {module_path_for(path, root) for path in build_files}
    # Match configuration calls even when nested on one line inside dependencies { }
    nested_call_re = re.compile(
        r"\b([A-Za-z][A-Za-z0-9.]*)\s*\(\s*((?:project\s*\([^)]*\)|projects\.[A-Za-z0-9_.]+|[^()\n]+))\s*\)"
    )
    for build_file in build_files:
        text = strip_gradle_comments(build_file.read_text(encoding="utf-8", errors="replace"))
        path = module_path_for(build_file, root)
        production: list[dict] = []
        test: list[dict] = []
        seen: set[tuple[str, str, str]] = set()
        for match in nested_call_re.finditer(text):
            configuration = match.group(1)
            expression = match.group(2)
            lower = configuration.lower()
            if not any(
                lower == suffix or lower.endswith(suffix)
                for suffix in ("implementation", "api", "compileonly", "runtimeonly", "kapt", "ksp")
            ) and not lower.endswith(("implementation", "api")):
                # also accept commonMainApi-style helpers
                if not any(token in lower for token in ("implementation", "api", "compileonly")):
                    continue
            targets = []
            for regex in PROJECT_DEP_RES:
                for dep in regex.finditer(expression):
                    targets.append(normalize_project_dependency(dep.group(1), known))
            if not targets:
                # Try whole-expression project() forms with extra whitespace
                for regex in PROJECT_DEP_RES:
                    for dep in regex.finditer(match.group(0)):
                        targets.append(normalize_project_dependency(dep.group(1), known))
            if not targets:
                continue
            bucket = test if "test" in lower else production
            visibility = "api" if lower.endswith("api") or lower == "api" else "implementation"
            if "compileonly" in lower:
                visibility = "compileOnly"
            for target in targets:
                key = (configuration, visibility, target)
                if key in seen:
                    continue
                seen.add(key)
                bucket.append(
                    {
                        "configuration": configuration,
                        "visibility": visibility,
                        "target": target,
                        "expression": expression.strip(),
                    }
                )
        modules.append(
            {
                "path": path,
                "directory": build_file.parent.relative_to(root).as_posix() or ".",
                "build_file": build_file.relative_to(root).as_posix(),
                "project_dependencies": [item["target"] for item in production],
                "test_project_dependencies": [item["target"] for item in test],
                "declared_dependencies": production + test,
            }
        )
    return modules


def build_graph(modules: list[dict], *, include_test: bool = False) -> dict[str, list[str]]:
    graph: dict[str, list[str]] = {module["path"]: [] for module in modules}
    for module in modules:
        edges = list(module.get("project_dependencies", []))
        if include_test:
            edges.extend(module.get("test_project_dependencies", []))
        for target in edges:
            if target in graph and target not in graph[module["path"]]:
                graph[module["path"]].append(target)
        graph[module["path"]].sort()
    return graph


def strongly_connected_components(graph: dict[str, list[str]]) -> list[list[str]]:
    """Tarjan SCC; multi-node components and self-loops only, sorted deterministically."""
    index = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    components: list[list[str]] = []

    def strongconnect(node: str) -> None:
        nonlocal index
        indices[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for target in graph.get(node, []):
            if target not in graph:
                continue
            if target not in indices:
                strongconnect(target)
                lowlinks[node] = min(lowlinks[node], lowlinks[target])
            elif target in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[target])
        if lowlinks[node] == indices[node]:
            component: list[str] = []
            while True:
                member = stack.pop()
                on_stack.discard(member)
                component.append(member)
                if member == node:
                    break
            component.sort()
            if len(component) > 1 or node in graph.get(node, []):
                components.append(component)

    for node in sorted(graph):
        if node not in indices:
            strongconnect(node)
    components.sort(key=lambda item: (len(item), item))
    return components


def topological_batches(graph: dict[str, list[str]]) -> list[list[str]]:
    """Dependency-first batches (leaves first)."""
    reverse: dict[str, set[str]] = {node: set() for node in graph}
    indegree: dict[str, int] = {node: 0 for node in graph}
    for source, targets in graph.items():
        for target in targets:
            if target not in reverse:
                continue
            reverse[target].add(source)
            indegree[source] = indegree.get(source, 0)
    # indegree of node = number of dependencies it still waits on
    remaining = {node: set(targets) & set(graph) for node, targets in graph.items()}
    ready = sorted(node for node, deps in remaining.items() if not deps)
    batches: list[list[str]] = []
    placed: set[str] = set()
    while ready:
        batch = ready
        batches.append(batch)
        placed.update(batch)
        ready = []
        for node, deps in remaining.items():
            if node in placed:
                continue
            deps -= placed
            if not deps:
                ready.append(node)
        ready.sort()
    leftover = sorted(node for node in graph if node not in placed)
    if leftover:
        batches.append(leftover)
    return batches


def source_set_for_path(path: Path) -> str | None:
    parts = path.parts
    if "src" not in parts:
        return None
    index = parts.index("src")
    if index + 1 < len(parts):
        return parts[index + 1]
    return None


def platform_kind_for_import(import_path: str) -> str | None:
    cleaned = import_path.rstrip(".*")
    if cleaned.startswith(ANDROID_IMPORT_PREFIXES):
        return "android"
    if cleaned.startswith(JVM_IMPORT_PREFIXES):
        return "jvm"
    if cleaned.startswith(COCOA_IMPORT_PREFIXES):
        return "apple"
    if cleaned.startswith(PLATFORM_IMPORT_PREFIXES):
        return "platform"
    return None


def is_portable_source_set(source_set: str | None) -> bool:
    if not source_set:
        return True
    lower = source_set.lower()
    return lower in {
        "main",
        "commonmain",
        "commontest",
        "test",
        "jvmtest",
    } or lower.startswith("common")


def median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2.0
