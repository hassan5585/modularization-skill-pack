#!/usr/bin/env python3
"""Suggest a narrow-to-broad Gradle verification matrix without running tasks."""

from __future__ import annotations

import argparse
import fnmatch
import os
import re
import sys
from pathlib import Path


EXCLUDED = {".git", ".gradle", ".idea", ".kotlin", "build", "out", "node_modules", "vendor", "Pods", "DerivedData", ".konan", ".swiftpm-locks", ".build", "swiftPMCheckout", "Carthage", "xcuserdata", ".modularization"}
PROJECT_RE = re.compile(r"project\(\s*(?:path\s*[:=]\s*)?[\"'](:[^\"']+)[\"']\s*\)")
TYPE_SAFE_PROJECT_RE = re.compile(r"\bprojects\.([A-Za-z0-9_.]+)")
INCLUDE_BUILD_RE = re.compile(r"includeBuild\s*(?:\(\s*)?[\"']([^\"']+)[\"']")
PLUGIN_RES = [
    re.compile(r"alias\(\s*libs\.plugins\.([A-Za-z0-9_.-]+)\s*\)"),
    re.compile(r"id\(\s*[\"']([^\"']+)[\"']\s*\)"),
    re.compile(r"\bid\s+[\"']([^\"']+)[\"']"),
    re.compile(r"apply\s+plugin\s*:\s*[\"']([^\"']+)[\"']"),
    re.compile(r"kotlin\(\s*[\"']([^\"']+)[\"']\s*\)"),
]
PLATFORMS = {"android", "kmp", "jvm"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--changed", action="append", default=[], help="Changed module path or repository-relative file/directory")
    parser.add_argument(
        "--platform-rule",
        action="append",
        default=[],
        metavar="MODULE_GLOB=PLATFORM",
        help="Override static platform inference for matching Gradle module paths; PLATFORM is android, kmp, or jvm",
    )
    return parser.parse_args()


def build_files(root: Path) -> list[Path]:
    files = []
    settings = next((root / name for name in ("settings.gradle.kts", "settings.gradle") if (root / name).is_file()), None)
    settings_text = settings.read_text(encoding="utf-8", errors="replace") if settings else ""
    included_builds = {(root / value).resolve() for value in INCLUDE_BUILD_RE.findall(settings_text)}
    for current, dirs, names in os.walk(root):
        base = Path(current)
        if base != root and any((base / name).is_file() for name in ("settings.gradle", "settings.gradle.kts")):
            if base.resolve() not in included_builds:
                dirs[:] = []
                continue
        dirs[:] = [d for d in dirs if d not in EXCLUDED]
        for name in names:
            if name in {"build.gradle", "build.gradle.kts"}:
                files.append(base / name)
    return sorted(files)


def module_path(directory: Path, root: Path) -> str:
    parts = directory.relative_to(root).parts
    return ":" + ":".join(parts) if parts else ":"


def resolve_changed(value: str, root: Path, modules: list[dict]) -> set[str]:
    if value.startswith(":"):
        return {value} if any(m["path"] == value for m in modules) else set()
    candidate = (root / value).resolve()
    exact = [module for module in modules if candidate == module["directory_abs"]]
    if exact:
        return {exact[0]["path"]} | {module["path"] for module in modules if candidate in module["directory_abs"].parents}
    containing = [module for module in modules if module["path"] != ":" and module["directory_abs"] in candidate.parents]
    if containing:
        return {max(containing, key=lambda module: len(module["directory_abs"].parts))["path"]}
    descendants = [module["path"] for module in modules if module["path"] != ":" and candidate in module["directory_abs"].parents]
    return set(descendants)


def task(module_path_value: str, name: str) -> str:
    return f":{name}" if module_path_value == ":" else f"{module_path_value}:{name}"


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


def parse_platform_rules(values: list[str]) -> list[tuple[str, str]]:
    result = []
    for value in values:
        pattern, separator, platform = value.rpartition("=")
        if not separator or not pattern or platform not in PLATFORMS:
            raise ValueError(f"invalid --platform-rule {value!r}; expected MODULE_GLOB=android|kmp|jvm")
        result.append((pattern, platform))
    return result


def module_platform(module: dict, overrides: list[tuple[str, str]]) -> str | None:
    for pattern, platform in overrides:
        if fnmatch.fnmatch(module["path"], pattern):
            return platform
    plugin_text = " ".join(module["plugins"]).lower()
    build_text = module["text"].lower()
    source_sets = module["source_sets"]
    if any(token in plugin_text for token in ("multiplatform", ".kmp", "kmp.")) or "commonmain" in build_text or "commonMain" in source_sets:
        return "kmp"
    if "android" in plugin_text or "androidMain" in source_sets or module["has_android_manifest"]:
        return "android"
    if any(token in plugin_text for token in ("kotlin.jvm", "jvm", "java-library")):
        return "jvm"
    return None


def main() -> int:
    options = parse_args()
    root = options.root.resolve()
    if not root.is_dir():
        print(f"error: root is not a directory: {root}", file=sys.stderr)
        return 2
    try:
        platform_rules = parse_platform_rules(options.platform_rule)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    modules = []
    for build_file in build_files(root):
        text = build_file.read_text(encoding="utf-8", errors="replace")
        source_root = build_file.parent / "src"
        source_sets = {path.name for path in source_root.iterdir() if path.is_dir()} if source_root.is_dir() else set()
        module = {
            "path": module_path(build_file.parent, root),
            "directory_abs": build_file.parent,
            "directory": build_file.parent.relative_to(root).as_posix() or ".",
            "dependencies": sorted(set(PROJECT_RE.findall(text)) | {":" + value.replace(".", ":") for value in TYPE_SAFE_PROJECT_RE.findall(text)}),
            "text": text,
            "plugins": applied_plugins(text),
            "source_sets": source_sets,
            "has_android_manifest": (build_file.parent / "src" / "main" / "AndroidManifest.xml").is_file(),
        }
        module["platform"] = module_platform(module, platform_rules)
        modules.append(module)
    by_path = {m["path"]: m for m in modules}
    selected = set()
    unresolved = []
    for value in options.changed:
        result = resolve_changed(value, root, modules)
        if result:
            selected.update(result)
        else:
            unresolved.append(value)
    if not selected:
        selected = {m["path"] for m in modules if any(part in m["directory"].split("/") for part in ("feature", "core", "util"))}
    dependents = {
        path
        for path, module in by_path.items()
        if path not in selected and any(dependency in selected for dependency in module["dependencies"])
    }

    print("# Suggested Gradle verification matrix")
    print("\nThese commands are advisory. Confirm task names with the target repository's CI or `./gradlew tasks`.\n")
    build_logic_dirs = sorted({m["directory"].split("/")[0] for m in modules if m["directory"].split("/")[0] in {"build-logic", "plugins", "buildSrc"}})
    if build_logic_dirs:
        print("## 1. Build logic")
        for directory in build_logic_dirs:
            print(f"- `./gradlew -p {directory} build`")
        print()

    print("## 2. Changed modules")
    if selected:
        for path in sorted(selected):
            module = by_path[path]
            print(f"- `./gradlew {task(path, 'check')}`")
            if module["platform"] == "kmp":
                print(f"  - If available: `./gradlew {task(path, 'testAndroidHostTest')}`")
                if "ios" in module["text"].lower() or any(value.lower().startswith("ios") for value in module["source_sets"]):
                    print(f"  - If available: `./gradlew {task(path, 'iosSimulatorArm64Test')}`")
            elif module["platform"] == "android":
                print(f"  - If available: `./gradlew {task(path, 'testDebugUnitTest')}`")
            else:
                print(f"  - If available: `./gradlew {task(path, 'test')}`")
                if module["platform"] is None:
                    print("  - Platform was not statically inferable; add `--platform-rule` for convention-only modules.")
    else:
        print("- No module matched the requested changed paths.")
    print()

    print("## 3. Direct dependents")
    if dependents:
        for path in sorted(dependents):
            print(f"- `./gradlew {task(path, 'check')}`")
    else:
        print("- No direct dependents were detected by static `project(...)` parsing.")
    print()

    apps = [
        module for module in modules
        if any("application" in plugin.lower() for plugin in module["plugins"])
        or module["directory"].lower().endswith(("app", "application"))
    ]
    print("## 4. Application/deliverable")
    if apps:
        for app in apps:
            if app["platform"] == "android":
                print(f"- `./gradlew {task(app['path'], 'assembleDebug')}` (or the repository's equivalent compile/package task)")
            elif app["platform"] == "kmp":
                print(f"- `./gradlew {task(app['path'], 'check')}` plus the repository's Android/iOS framework or packaging task")
            else:
                print(f"- Run the repository's application compile/package task for `{app['path']}`; use `--platform-rule` if task-family inference is required.")
    else:
        print("- Run the application/shared-framework compile used by CI.")
    print("\n## 5. Repository gates\n- Run repository lint/static analysis and the CI-required aggregate check after local checks pass.")
    if unresolved:
        print("\nUnresolved `--changed` values:")
        for value in unresolved:
            print(f"- `{value}`")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
