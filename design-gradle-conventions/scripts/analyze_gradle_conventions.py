#!/usr/bin/env python3
"""Analyze repeated Gradle plugin, dependency, and configuration patterns."""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys
from pathlib import Path


SCHEMA_VERSION = 1
EXCLUDED = {".git", ".gradle", ".idea", ".kotlin", "build", "out", "node_modules", "vendor", "Pods", "DerivedData", ".konan", ".swiftpm-locks", ".build", "swiftPMCheckout", "Carthage", "xcuserdata", ".modularization"}
PLUGIN_RES = [
    re.compile(r"alias\(\s*libs\.plugins\.([A-Za-z0-9_.-]+)\s*\)"),
    re.compile(r"id\(\s*[\"']([^\"']+)[\"']\s*\)"),
    re.compile(r"\bid\s+[\"']([^\"']+)[\"']"),
    re.compile(r"apply\s+plugin\s*:\s*[\"']([^\"']+)[\"']"),
    re.compile(r"kotlin\(\s*[\"']([^\"']+)[\"']\s*\)"),
]
DEPENDENCY_RE = re.compile(r"(?m)^\s*([A-Za-z][A-Za-z0-9.]*)\s*\(\s*(.+?)\s*\)\s*$")
DEPENDENCY_GROOVY_RE = re.compile(r"(?m)^\s*([A-Za-z][A-Za-z0-9.]*)\s+([^={}].+?)\s*$")
DEPENDENCY_SUFFIXES = ("implementation", "api", "compileonly", "runtimeonly", "processor", "kapt", "ksp")
PROJECT_RE = re.compile(r"project\(\s*(?:path\s*[:=]\s*)?[\"'](:[^\"']+)[\"']\s*\)")
TYPE_SAFE_PROJECT_RE = re.compile(r"(?<![A-Za-z0-9_.])projects\.([A-Za-z0-9_.]+)")
ASSIGNMENT_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_.\[\]\"']*)\s*(?:=|\+=)\s*(.+?)\s*$")
INCLUDE_BUILD_RE = re.compile(r"includeBuild\s*(?:\(\s*)?[\"']([^\"']+)[\"']")
REGISTERED_PLUGIN_RE = re.compile(r"\bid\s*=\s*[\"']([^\"']+)[\"']")


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


def args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--markdown-out", type=Path)
    return parser.parse_args()


def excluded(path: Path, root: Path, extra: set[str]) -> bool:
    rel = path.relative_to(root)
    rel_text = rel.as_posix()
    return any(part in EXCLUDED or part in extra for part in rel.parts) or any(rel_text == x or rel_text.startswith(x.rstrip("/") + "/") for x in extra)


def included_build_roots(root: Path) -> set[Path]:
    settings = next((root / name for name in ("settings.gradle.kts", "settings.gradle") if (root / name).is_file()), None)
    if not settings:
        return set()
    text = strip_gradle_comments(
        settings.read_text(encoding="utf-8", errors="replace")
    )
    result = set()
    for relative in INCLUDE_BUILD_RE.findall(text):
        candidate = (root / relative).resolve()
        if candidate != root and root in candidate.parents:
            result.add(candidate)
    return result


def build_files(root: Path, extra: set[str]) -> list[Path]:
    result = []
    included_builds = included_build_roots(root)
    for current, dirs, files in os.walk(root):
        base = Path(current)
        if base != root and any((base / name).is_file() for name in ("settings.gradle", "settings.gradle.kts")):
            if base.resolve() not in included_builds:
                dirs[:] = []
                continue
        dirs[:] = [d for d in dirs if not excluded(base / d, root, extra)]
        for name in files:
            if name in {"build.gradle", "build.gradle.kts"}:
                result.append(base / name)
    return sorted(result)


def role_for(path: Path, root: Path) -> str:
    rel = path.parent.relative_to(root)
    parts = [part.lower() for part in rel.parts]
    if not parts:
        return "root"
    last = parts[-1]
    if last in {"domain", "data", "navigation", "shared-ui", "ui"}:
        return last
    if last in {"test", "test-support", "fixtures"}:
        return "test-support"
    if last in {"app", "androidapp", "composeapp", "application"} or "application" in path.read_text(encoding="utf-8", errors="replace"):
        return "app"
    if "feature" in parts or "features" in parts:
        return "feature-aggregation"
    if "core" in parts:
        return "core-aggregation"
    if "util" in parts or "utility" in parts:
        return "utility-aggregation"
    if last in {"convention", "build-logic", "plugins", "buildsrc"}:
        return "build-logic"
    return "library"


def gradle_accessor_segment(segment: str) -> str:
    parts = re.split(r"[-_]+", segment)
    return parts[0] + "".join(
        part[:1].upper() + part[1:] for part in parts[1:]
    )


def gradle_project_accessor(module: str) -> str:
    return ".".join(
        gradle_accessor_segment(segment)
        for segment in module.split(":")
        if segment
    )


def normalize_dependency(
    expr: str,
    known_modules: set[str] | None = None,
) -> str:
    expr = re.sub(r"\s+", " ", expr.strip())
    project = PROJECT_RE.search(expr)
    if project:
        return f"project({project.group(1)})"
    type_safe = TYPE_SAFE_PROJECT_RE.search(expr)
    if type_safe:
        accessor = type_safe.group(1)
        accessor_matches = [
            module
            for module in known_modules or set()
            if gradle_project_accessor(module) == accessor
        ]
        if len(accessor_matches) == 1:
            return f"project({accessor_matches[0]})"
        segments = accessor.split(".")
        literal = ":" + ":".join(segments)
        kebab = ":" + ":".join(
            re.sub(r"(?<!^)(?=[A-Z])", "-", segment).lower()
            for segment in segments
        )
        dependency = next(
            (
                candidate
                for candidate in (literal, kebab)
                if known_modules and candidate in known_modules
            ),
            kebab if "sharedUi" in segments else literal,
        )
        return f"project({dependency})"
    alias = re.search(r"libs\.([A-Za-z0-9_.-]+)", expr)
    if alias:
        return f"libs.{alias.group(1)}"
    quoted = re.search(r"[\"']([^\"']+)[\"']", expr)
    return quoted.group(1) if quoted else expr[:160]


def applied_plugins(text: str) -> list[str]:
    plugins: set[str] = set()
    for pattern in PLUGIN_RES:
        for match in pattern.finditer(text):
            line_end = text.find("\n", match.end())
            trailer = text[match.end():line_end if line_end >= 0 else len(text)].lower()
            if re.search(r"\bapply\s+false\b", trailer):
                continue
            plugins.add(match.group(1))
    return sorted(plugins)


def significant_assignments(text: str) -> list[str]:
    interesting = (
        "compilesdk", "minsdk", "targetsdk", "jvmtoolchain", "languageversion", "apiversion",
        "namespace", "buildfeatures", "compileroptions", "freecompilerargs", "optin", "schemadirectory",
        "publicresclass", "testinstrumentationrunner", "resources.excludes", "packaging",
    )
    values = []
    for line in text.splitlines():
        match = ASSIGNMENT_RE.match(line)
        if not match:
            continue
        normalized = re.sub(r"\s+", " ", f"{match.group(1)} = {match.group(2)}").strip()
        if any(term in normalized.lower() for term in interesting):
            values.append(normalized[:240])
    return sorted(set(values))


def analyze(root: Path, excludes: set[str]) -> dict:
    modules = []
    warnings = []
    files = build_files(root, excludes)
    known_modules = {
        ":" + ":".join(file.parent.relative_to(root).parts)
        if file.parent != root
        else ":"
        for file in files
    }
    for file in files:
        try:
            text = file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = file.read_text(encoding="utf-8", errors="replace")
            warnings.append({"path": file.relative_to(root).as_posix(), "warning": "invalid UTF-8 replaced"})
        text = strip_gradle_comments(text)
        plugins = applied_plugins(text)
        dependency_values = {
            (match.group(1), normalize_dependency(match.group(2), known_modules))
            for pattern in (DEPENDENCY_RE, DEPENDENCY_GROOVY_RE)
            for match in pattern.finditer(text)
            if match.group(1).lower().endswith(DEPENDENCY_SUFFIXES)
        }
        dependencies = [{"configuration": configuration, "dependency": dependency} for configuration, dependency in sorted(dependency_values)]
        modules.append({
            "path": ":" + ":".join(file.parent.relative_to(root).parts) if file.parent != root else ":",
            "directory": file.parent.relative_to(root).as_posix() or ".",
            "build_file": file.relative_to(root).as_posix(),
            "role": role_for(file, root),
            "plugins": plugins,
            "dependencies": dependencies,
            "configuration_signatures": significant_assignments(text),
        })

    by_role: dict[str, list[dict]] = collections.defaultdict(list)
    for module in modules:
        by_role[module["role"]].append(module)
    role_patterns = {}
    for role, role_modules in sorted(by_role.items()):
        plugin_counts = collections.Counter(p for module in role_modules for p in module["plugins"])
        dep_counts = collections.Counter((d["configuration"], d["dependency"]) for module in role_modules for d in module["dependencies"])
        sig_counts = collections.Counter(s for module in role_modules for s in module["configuration_signatures"])
        total = len(role_modules)
        role_patterns[role] = {
            "module_count": total,
            "plugins": [
                {"value": value, "count": count, "ratio": round(count / total, 3)}
                for value, count in plugin_counts.most_common()
            ],
            "dependencies": [
                {"configuration": config, "value": value, "count": count, "ratio": round(count / total, 3)}
                for (config, value), count in dep_counts.most_common()
            ],
            "configuration_signatures": [
                {"value": value, "count": count, "ratio": round(count / total, 3)}
                for value, count in sig_counts.most_common()
            ],
        }

    global_plugins = collections.Counter(p for module in modules for p in module["plugins"])
    global_dependencies = collections.Counter((d["configuration"], d["dependency"]) for module in modules for d in module["dependencies"])
    registered_plugins: set[str] = set()
    for module in modules:
        if module["role"] == "build-logic":
            text = strip_gradle_comments(
                (root / module["build_file"]).read_text(encoding="utf-8", errors="replace")
            )
            registered_plugins.update(REGISTERED_PLUGIN_RE.findall(text))
    return {
        "schema_version": SCHEMA_VERSION,
        "root": ".",
        "project_name": root.name,
        "included_builds": sorted(path.relative_to(root).as_posix() for path in included_build_roots(root)),
        "registered_convention_plugins": sorted(registered_plugins),
        "module_count": len(modules),
        "modules": modules,
        "role_patterns": role_patterns,
        "global_patterns": {
            "plugins": [{"value": v, "count": c} for v, c in global_plugins.most_common()],
            "dependencies": [{"configuration": k[0], "value": k[1], "count": c} for k, c in global_dependencies.most_common()],
        },
        "warnings": warnings,
    }


def markdown(data: dict) -> str:
    lines = [
        "# Gradle convention audit", "",
        f"Analyzed {data['module_count']} build files.",
        f"Included builds: `{', '.join(data['included_builds']) or 'none'}`",
        f"Registered convention plugin ids found: `{', '.join(data['registered_convention_plugins']) or 'none detected'}`",
        "", "## Patterns by module role", "",
    ]
    for role, pattern in data["role_patterns"].items():
        lines += [f"### {role} ({pattern['module_count']})", "", "Repeated plugins:", ""]
        repeated = [p for p in pattern["plugins"] if p["count"] >= 2 or p["ratio"] == 1.0]
        lines += [f"- `{p['value']}` — {p['count']}/{pattern['module_count']} ({p['ratio']:.0%})" for p in repeated] or ["- None detected."]
        lines += ["", "Repeated dependencies:", ""]
        repeated_deps = [d for d in pattern["dependencies"] if d["count"] >= 2 or d["ratio"] == 1.0]
        lines += [f"- `{d['configuration']}({d['value']})` — {d['count']}/{pattern['module_count']} ({d['ratio']:.0%})" for d in repeated_deps[:40]] or ["- None detected."]
        lines += ["", "Repeated configuration signatures:", ""]
        repeated_sigs = [s for s in pattern["configuration_signatures"] if s["count"] >= 2 or s["ratio"] == 1.0]
        lines += [f"- `{s['value']}` — {s['count']}/{pattern['module_count']} ({s['ratio']:.0%})" for s in repeated_sigs[:40]] or ["- None detected."]
        lines.append("")
    lines += [
        "## Design guidance", "",
        "- Put platform/toolchain/source-set invariants in a base plugin.",
        "- Put optional UI, data, navigation, serialization, DI/code generation, and test behavior in capability plugins.",
        "- Keep app signing, secrets, release, and distribution behavior out of library plugins.",
        "- Verify every recommendation against full Gradle blocks; line-based analysis cannot interpret arbitrary Kotlin logic.",
        "",
    ]
    return "\n".join(lines)


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> int:
    options = args()
    root = options.root.resolve()
    if not root.is_dir():
        print(f"error: root is not a directory: {root}", file=sys.stderr)
        return 2
    data = analyze(root, set(options.exclude))
    report = markdown(data)
    if options.json_out:
        write(options.json_out, json.dumps(data, indent=2, sort_keys=True) + "\n")
    if options.markdown_out:
        write(options.markdown_out, report)
    if not options.json_out and not options.markdown_out:
        print(report)
    else:
        if options.json_out:
            print(f"Wrote JSON audit: {options.json_out}")
        if options.markdown_out:
            print(f"Wrote Markdown audit: {options.markdown_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
