#!/usr/bin/env python3
"""Scaffold layered feature modules from an explicit project-adapted JSON spec.

Dry-run is the default. The script never edits settings, app aggregation, DI, or
navigation registration because those are project-specific.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


SCHEMA_VERSION = 1
NAME_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
PACKAGE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
KNOWN_LAYERS = ("domain", "data", "navigation", "ui", "test")


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
    if spec.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version: {spec.get('schema_version')!r}")
    for key in ("feature", "base_directory", "package", "platform", "layers"):
        if key not in spec:
            raise ValueError(f"missing required field: {key}")
    if not NAME_RE.match(spec["feature"]):
        raise ValueError("feature must use lowercase letters, numbers, hyphen, or underscore")
    if not PACKAGE_RE.match(spec["package"]):
        raise ValueError(f"invalid package: {spec['package']}")
    if spec["platform"] not in {"kmp", "android", "jvm"}:
        raise ValueError("platform must be kmp, android, or jvm")
    unknown = set(spec["layers"]) - set(KNOWN_LAYERS)
    if unknown:
        raise ValueError(f"unknown layers: {sorted(unknown)}")
    for layer, config in spec["layers"].items():
        for field in ("plugins", "dependencies"):
            values = config.get(field, [])
            if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
                raise ValueError(f"{layer}.{field} must be a list of Gradle expressions")
    return spec


def safe(root: Path, relative: Path | str) -> Path:
    target = (root / relative).resolve()
    if target != root and root not in target.parents:
        raise ValueError(f"path escapes repository root: {relative}")
    return target


def plugins_block(plugins: list[str]) -> str:
    if not plugins:
        return "plugins {\n    // Add the target repository's verified convention plugin.\n}\n"
    return "plugins {\n" + "\n".join(f"    {line}" for line in plugins) + "\n}\n"


def dependencies_block(platform: str, source_set: str, dependencies: list[str]) -> str:
    if not dependencies:
        return ""
    body = "\n".join(f"            {line}" for line in dependencies)
    if platform == "kmp":
        return f'''\nkotlin {{
    sourceSets.{source_set}.dependencies {{
{body}
    }}
}}
'''
    flat = "\n".join(f"    {line}" for line in dependencies)
    return f'''\ndependencies {{
{flat}
}}
'''


def build_text(platform: str, source_set: str, config: dict) -> str:
    return plugins_block(config.get("plugins", [])) + dependencies_block(platform, source_set, config.get("dependencies", []))


def source_roots(spec: dict, layer: str, layer_dir: Path) -> list[Path]:
    platform = spec["platform"]
    main_source = spec.get("source_set") or ("commonMain" if platform == "kmp" else "main")
    test_source = spec.get("test_source_set") or ("commonTest" if platform == "kmp" else "test")
    package = Path(*spec["package"].split(".")) if layer == "aggregation" else Path(*spec["package"].split("."), layer)
    roots = [layer_dir / "src" / main_source / "kotlin" / package]
    if layer not in {"test", "aggregation"}:
        roots.append(layer_dir / "src" / test_source / "kotlin" / package)
    if layer == "ui" and spec.get("create_resource_directory", False):
        if platform == "kmp":
            roots.append(layer_dir / "src" / main_source / "composeResources")
        else:
            roots.append(layer_dir / "src" / main_source / "res")
    return roots


def create_plan(root: Path, spec: dict) -> tuple[list[tuple[Path, str]], list[Path], list[str]]:
    feature_dir = safe(root, Path(spec["base_directory"]) / spec["feature"])
    build_name = spec.get("build_file_name", "build.gradle.kts")
    files: list[tuple[Path, str]] = []
    directories: list[Path] = []
    module_prefix = ":" + ":".join((Path(spec["base_directory"]) / spec["feature"]).parts)

    if spec.get("aggregation_module", True):
        aggregation = spec.get("aggregation", {"plugins": [], "dependencies": []})
        files.append((feature_dir / build_name, build_text(spec["platform"], spec.get("source_set", "commonMain"), aggregation)))
        directories.extend(source_roots(spec, "aggregation", feature_dir))

    modules = [module_prefix] if spec.get("aggregation_module", True) else []
    for layer in KNOWN_LAYERS:
        config = spec["layers"].get(layer, {})
        if not config.get("enabled", False):
            continue
        layer_dir = feature_dir / layer
        source_set = spec.get("source_set") or ("commonMain" if spec["platform"] == "kmp" else "main")
        files.append((layer_dir / build_name, build_text(spec["platform"], source_set, config)))
        directories.extend(source_roots(spec, layer, layer_dir))
        modules.append(f"{module_prefix}:{layer}")
    return files, directories, modules


def main() -> int:
    options = parse_args()
    root = options.root.resolve()
    if not root.is_dir():
        print(f"error: root is not a directory: {root}", file=sys.stderr)
        return 2
    try:
        spec = load_spec(options.spec)
        files, directories, modules = create_plan(root, spec)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    conflicts = [path for path, _ in files if path.exists()]
    print(f"{'Applying' if options.apply else 'Dry run:'} feature `{spec['feature']}`")
    print("Build files:")
    for path, _ in files:
        print(f"  - {path.relative_to(root)}{' [exists]' if path.exists() else ''}")
    print("Source/resource roots:")
    for directory in directories:
        print(f"  - {directory.relative_to(root)}")
    include_args = ", ".join(f'"{module}"' for module in modules)
    print("\nAdd to settings.gradle(.kts) after review:")
    print(f"  include({include_args})")
    print("Then wire the feature root into the app and register DI/navigation/resources using the target project's existing mechanisms.")

    if not options.apply:
        return 0
    if conflicts:
        print("error: refusing to overwrite existing build files", file=sys.stderr)
        for conflict in conflicts:
            print(f"  - {conflict.relative_to(root)}", file=sys.stderr)
        return 3
    for path, content in files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
    print("Feature module scaffold written. No settings or application wiring was modified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
