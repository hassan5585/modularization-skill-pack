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
EXCLUDED = {".git", ".gradle", ".idea", ".kotlin", "build", "out", "node_modules", "vendor"}
PLUGIN_RES = [
    re.compile(r"alias\(\s*libs\.plugins\.([A-Za-z0-9_.-]+)\s*\)"),
    re.compile(r"id\(\s*[\"']([^\"']+)[\"']\s*\)"),
    re.compile(r"kotlin\(\s*[\"']([^\"']+)[\"']\s*\)"),
]
DEPENDENCY_RE = re.compile(r"(?m)^\s*([A-Za-z][A-Za-z0-9.]*)\s*\(\s*(.+?)\s*\)\s*$")
DEPENDENCY_SUFFIXES = ("implementation", "api", "compileonly", "runtimeonly", "processor", "kapt", "ksp")
PROJECT_RE = re.compile(r"project\(\s*[\"'](:[^\"']+)[\"']\s*\)")
ASSIGNMENT_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_.\[\]\"']*)\s*(?:=|\+=)\s*(.+?)\s*$")


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


def build_files(root: Path, extra: set[str]) -> list[Path]:
    result = []
    for current, dirs, files in os.walk(root):
        base = Path(current)
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
    if last in {"domain", "data", "navigation", "ui"}:
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


def normalize_dependency(expr: str) -> str:
    expr = re.sub(r"\s+", " ", expr.strip())
    project = PROJECT_RE.search(expr)
    if project:
        return f"project({project.group(1)})"
    alias = re.search(r"libs\.([A-Za-z0-9_.-]+)", expr)
    if alias:
        return f"libs.{alias.group(1)}"
    quoted = re.search(r"[\"']([^\"']+)[\"']", expr)
    return quoted.group(1) if quoted else expr[:160]


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
    for file in build_files(root, excludes):
        try:
            text = file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = file.read_text(encoding="utf-8", errors="replace")
            warnings.append({"path": file.relative_to(root).as_posix(), "warning": "invalid UTF-8 replaced"})
        plugins = sorted({m.group(1) for regex in PLUGIN_RES for m in regex.finditer(text)})
        dependencies = [
            {"configuration": m.group(1), "dependency": normalize_dependency(m.group(2))}
            for m in DEPENDENCY_RE.finditer(text)
            if m.group(1).lower().endswith(DEPENDENCY_SUFFIXES)
        ]
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
    return {
        "schema_version": SCHEMA_VERSION,
        "root": str(root),
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
    lines = ["# Gradle convention audit", "", f"Analyzed {data['module_count']} build files.", "", "## Patterns by module role", ""]
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
