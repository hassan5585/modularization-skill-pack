#!/usr/bin/env python3
"""Suggest a narrow-to-broad Gradle verification matrix without running tasks."""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path


EXCLUDED = {".git", ".gradle", ".idea", ".kotlin", "build", "out", "node_modules", "vendor"}
PROJECT_RE = re.compile(r"project\(\s*[\"'](:[^\"']+)[\"']\s*\)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--changed", action="append", default=[], help="Changed module path or repository-relative file/directory")
    return parser.parse_args()


def build_files(root: Path) -> list[Path]:
    files = []
    for current, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in EXCLUDED]
        for name in names:
            if name in {"build.gradle", "build.gradle.kts"}:
                files.append(Path(current) / name)
    return sorted(files)


def module_path(directory: Path, root: Path) -> str:
    parts = directory.relative_to(root).parts
    return ":" + ":".join(parts) if parts else ":"


def resolve_changed(value: str, root: Path, modules: list[dict]) -> str | None:
    if value.startswith(":"):
        return value if any(m["path"] == value for m in modules) else None
    candidate = (root / value).resolve()
    matching = [m for m in modules if candidate == m["directory_abs"] or m["directory_abs"] in candidate.parents or candidate in m["directory_abs"].parents]
    if not matching:
        return None
    return max(matching, key=lambda m: len(m["directory_abs"].parts))["path"]


def main() -> int:
    options = parse_args()
    root = options.root.resolve()
    if not root.is_dir():
        print(f"error: root is not a directory: {root}", file=sys.stderr)
        return 2
    modules = []
    for build_file in build_files(root):
        text = build_file.read_text(encoding="utf-8", errors="replace")
        modules.append({
            "path": module_path(build_file.parent, root),
            "directory_abs": build_file.parent,
            "directory": build_file.parent.relative_to(root).as_posix() or ".",
            "dependencies": sorted(set(PROJECT_RE.findall(text))),
            "text": text,
        })
    by_path = {m["path"]: m for m in modules}
    selected = set()
    unresolved = []
    for value in options.changed:
        result = resolve_changed(value, root, modules)
        if result:
            selected.add(result)
        else:
            unresolved.append(value)
    if not selected:
        selected = {m["path"] for m in modules if any(part in m["directory"].split("/") for part in ("feature", "core", "util"))}
    dependents = {path for path, module in by_path.items() if any(dep in selected for dep in module["dependencies"])}

    print("# Suggested Gradle verification matrix")
    print("\nThese commands are advisory. Confirm task names with the target repository's CI or `./gradlew tasks`.\n")
    build_logic_dirs = sorted({m["directory"].split("/")[0] for m in modules if m["directory"].split("/")[0] in {"build-logic", "plugins", "buildSrc"}})
    if build_logic_dirs:
        print("## 1. Build logic")
        for directory in build_logic_dirs:
            print(f"- `./gradlew -p {directory} build`")
        print()

    print("## 2. Changed modules")
    for path in sorted(selected):
        module = by_path[path]
        text = module["text"].lower()
        print(f"- `./gradlew {path}:check`")
        if "multiplatform" in text or "commonmain" in text or "kmp" in text:
            print(f"  - If available: `./gradlew {path}:testAndroidHostTest`")
            if "ios" in text:
                print(f"  - If available: `./gradlew {path}:iosSimulatorArm64Test`")
        elif "com.android" in text or "android" in text:
            print(f"  - If available: `./gradlew {path}:testDebugUnitTest`")
        else:
            print(f"  - If available: `./gradlew {path}:test`")
    print()

    print("## 3. Direct dependents")
    if dependents:
        for path in sorted(dependents):
            print(f"- `./gradlew {path}:check`")
    else:
        print("- No direct dependents were detected by static `project(...)` parsing.")
    print()

    apps = [m for m in modules if any(token in m["text"] for token in ("com.android.application", "android-application", "application {")) or m["directory"].lower().endswith(("app", "application"))]
    print("## 4. Application/deliverable")
    if apps:
        for app in apps:
            print(f"- `./gradlew {app['path']}:assembleDebug` (or the repository's equivalent compile/package task)")
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
