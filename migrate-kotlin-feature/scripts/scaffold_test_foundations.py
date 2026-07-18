#!/usr/bin/env python3
"""Scaffold explicit shared test-foundation modules from a reviewed JSON spec.

These modules hold reusable fakes/fixtures in their production source set but must
only be consumed from test configurations. Dry-run is the default.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


SCHEMA_VERSION = 1
MODULE_RE = re.compile(r"^:[A-Za-z0-9_-]+(?::[A-Za-z0-9_-]+)*$")
PACKAGE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def load_spec(path: Path) -> dict:
    try:
        spec = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read spec: {exc}") from exc
    if not isinstance(spec, dict) or spec.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version: {spec.get('schema_version') if isinstance(spec, dict) else None!r}")
    if spec.get("platform") not in {"kmp", "android", "jvm"}:
        raise ValueError("platform must be kmp, android, or jvm")
    if spec.get("build_file_name", "build.gradle.kts") not in {"build.gradle.kts", "build.gradle"}:
        raise ValueError("build_file_name must be build.gradle.kts or build.gradle")
    if spec.get("source_set") is not None and not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", spec["source_set"]):
        raise ValueError("source_set must be a simple Gradle source-set name")
    modules = spec.get("modules")
    if not isinstance(modules, list) or not modules:
        raise ValueError("modules must be a non-empty list")
    seen: set[str] = set()
    for module in modules:
        if not isinstance(module, dict):
            raise ValueError("every module must be an object")
        path_value = module.get("path")
        if not isinstance(path_value, str) or not MODULE_RE.fullmatch(path_value):
            raise ValueError(f"invalid Gradle module path: {path_value!r}")
        if path_value in seen:
            raise ValueError(f"duplicate Gradle module path: {path_value}")
        seen.add(path_value)
        if not PACKAGE_RE.fullmatch(module.get("package", "")):
            raise ValueError(f"invalid package for {path_value}: {module.get('package')!r}")
        for field in ("plugins", "dependencies"):
            values = module.get(field, [])
            if not isinstance(values, list) or not all(isinstance(value, str) and value for value in values):
                raise ValueError(f"{path_value} {field} must be a list of non-empty Gradle expressions")
    return spec


def safe(root: Path, relative: Path) -> Path:
    target = (root / relative).resolve()
    if target != root and root not in target.parents:
        raise ValueError(f"module path escapes repository root: {relative}")
    return target


def build_text(spec: dict, module: dict) -> str:
    plugins = module.get("plugins", [])
    plugin_block = "plugins {\n" + "\n".join(f"    {value}" for value in plugins) + "\n}\n"
    dependencies = module.get("dependencies", [])
    if not dependencies:
        return plugin_block
    if spec["platform"] == "kmp":
        source_set = spec.get("source_set") or "commonMain"
        body = "\n".join(f"            {value}" for value in dependencies)
        return plugin_block + f'''\nkotlin {{
    sourceSets.{source_set}.dependencies {{
{body}
    }}
}}
'''
    body = "\n".join(f"    {value}" for value in dependencies)
    return plugin_block + f"\ndependencies {{\n{body}\n}}\n"


def create_plan(root: Path, spec: dict) -> tuple[list[tuple[Path, str]], list[Path]]:
    files: list[tuple[Path, str]] = []
    directories: list[Path] = []
    build_name = spec.get("build_file_name", "build.gradle.kts")
    source_set = spec.get("source_set") or ("commonMain" if spec["platform"] == "kmp" else "main")
    for module in spec["modules"]:
        relative = Path(*[part for part in module["path"].split(":") if part])
        directory = safe(root, relative)
        files.append((directory / build_name, build_text(spec, module)))
        directories.append(directory / "src" / source_set / "kotlin" / Path(*module["package"].split(".")))
    return files, directories


def main() -> int:
    options = parse_args()
    root = options.root.resolve()
    if not root.is_dir():
        print(f"error: root is not a directory: {root}", file=sys.stderr)
        return 2
    try:
        spec = load_spec(options.spec)
        files, directories = create_plan(root, spec)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    conflicts = [path for path, _ in files if path.exists()]
    print(f"{'Applying' if options.apply else 'Dry run:'} {len(files)} shared test-foundation module(s)")
    for path, _ in files:
        print(f"  - {path.relative_to(root)}{' [exists]' if path.exists() else ''}")
    print("\nAdd these exact modules to settings after review:")
    print("  include(" + ", ".join(json.dumps(module["path"]) for module in spec["modules"]) + ")")
    print("Consume them only from test source sets/configurations; never from app or production aggregation modules.")
    if not options.apply:
        return 0
    if conflicts:
        print("error: refusing to overwrite existing build files", file=sys.stderr)
        return 3
    for path, content in files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
    print("Shared test-foundation modules scaffolded. Add reusable helpers/fakes only after confirming consumers and dependency direction.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
