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
KNOWN_LAYERS = ("domain", "data", "navigation", "shared-ui", "ui", "test")
PROJECT_RES = (
    re.compile(r"project\(\s*[\"'](:[^\"']+)[\"']\s*\)"),
    re.compile(r"project\(\s*path\s*[:=]\s*[\"'](:[^\"']+)[\"']"),
    re.compile(r"(?<![A-Za-z0-9_.])projects\.([A-Za-z0-9_.]+)"),
)


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
    if spec.get("build_file_name", "build.gradle.kts") not in {"build.gradle.kts", "build.gradle"}:
        raise ValueError("build_file_name must be build.gradle.kts or build.gradle")
    for key in ("source_set", "test_source_set"):
        value = spec.get(key)
        if value is not None and not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", value):
            raise ValueError(f"{key} must be a simple Gradle source-set name")
    unknown = set(spec["layers"]) - set(KNOWN_LAYERS)
    if unknown:
        raise ValueError(f"unknown layers: {sorted(unknown)}")
    for layer, config in spec["layers"].items():
        if not isinstance(config, dict):
            raise ValueError(f"{layer} must be an object")
        for field in ("plugins", "dependencies", "test_dependencies"):
            values = config.get(field, [])
            if not isinstance(values, list) or not all(isinstance(item, str) and item.strip() and "\n" not in item and "\r" not in item for item in values):
                raise ValueError(f"{layer}.{field} must be a list of non-empty single-line Gradle expressions")
        package_suffix = config.get("package_suffix")
        if package_suffix is not None and not PACKAGE_RE.match(package_suffix):
            raise ValueError(f"{layer}.package_suffix must contain valid Kotlin package segments")
        if layer != "test" and any(re.search(r"project\([^\n]*:test[\"']?\s*\)", value, re.IGNORECASE) for value in config.get("dependencies", [])):
            raise ValueError(f"{layer}.dependencies must not put test-support on a production source set; use test_dependencies")
    aggregation = spec.get("aggregation", {})
    if not isinstance(aggregation, dict):
        raise ValueError("aggregation must be an object")
    for field in ("plugins", "dependencies"):
        values = aggregation.get(field, [])
        if not isinstance(values, list) or not all(isinstance(item, str) and item.strip() and "\n" not in item and "\r" not in item for item in values):
            raise ValueError(f"aggregation.{field} must be a list of non-empty single-line Gradle expressions")
    if any(re.search(r"project\([^\n]*:test[\"']?\s*\)", value, re.IGNORECASE) for value in aggregation.get("dependencies", [])):
        raise ValueError("aggregation.dependencies must not include test-support modules")
    validate_feature_dependency_edges(spec)
    return spec


def canonical_gradle_name(value: str) -> str:
    return re.sub(r"[-_]", "", value).lower()


def feature_target(path: str, base_directory: str) -> tuple[str, str] | None:
    path_parts = [part for part in path.split(":") if part]
    base_parts = list(Path(base_directory).parts)
    if (
        len(path_parts) < len(base_parts) + 1
        or any(
            canonical_gradle_name(actual) != canonical_gradle_name(expected)
            for actual, expected in zip(path_parts, base_parts)
        )
    ):
        return None
    feature = path_parts[len(base_parts)]
    remainder = path_parts[len(base_parts) + 1:]
    role = "aggregation" if not remainder else remainder[-1]
    return feature, role


def project_role(path: str, base_directory: str) -> str:
    target = feature_target(path, base_directory)
    if target:
        return target[1]
    parts = [part.lower() for part in path.split(":") if part]
    if parts and parts[0] in {"test", "test-support", "fixtures"}:
        return "test-support"
    last = parts[-1] if parts else ""
    if last in {"app", "androidapp", "composeapp", "application"}:
        return "app"
    return last


def project_dependencies(expression: str) -> list[str]:
    dependencies = []
    for regex in PROJECT_RES:
        for match in regex.finditer(expression):
            dependency = match.group(1)
            if not dependency.startswith(":"):
                segments = [
                    re.sub(r"(?<!^)(?=[A-Z])", "-", segment).lower()
                    for segment in dependency.split(".")
                ]
                dependency = ":" + ":".join(segments)
            dependencies.append(dependency)
    return dependencies


def validate_feature_dependency_edges(spec: dict) -> None:
    owner = spec["feature"]
    base_directory = spec["base_directory"]
    for source_role, config in spec["layers"].items():
        if not config.get("enabled", False):
            continue
        for expression in config.get("dependencies", []):
            for target_path in project_dependencies(expression):
                target = feature_target(target_path, base_directory)
                target_role = project_role(target_path, base_directory)
                if source_role == "shared-ui" and target_role == "shared-ui":
                    raise ValueError(
                        f"shared-ui must not depend on another shared-ui: {target_path}"
                    )
                if target_role == "shared-ui" and source_role != "ui":
                    raise ValueError(
                        f"{source_role} must not depend on feature shared-ui: {target_path}"
                    )
                if (
                    source_role == "shared-ui"
                    and target_role in {"data", "app", "test", "test-support", "fixtures"}
                ):
                    raise ValueError(
                        f"shared-ui must not depend on {target_role}: {target_path}"
                    )
                if not target:
                    continue
                target_feature, _ = target
                if (
                    source_role == "shared-ui"
                    and canonical_gradle_name(target_feature) != canonical_gradle_name(owner)
                    and target_role in {"domain", "navigation"}
                ):
                    raise ValueError(
                        "shared-ui may depend only on its owner's feature contracts: "
                        f"{target_path}"
                    )
                if source_role == "shared-ui" and target_role == "ui":
                    raise ValueError(
                        f"shared-ui must not depend on a feature ui module: {target_path}"
                    )
                if source_role == "shared-ui" and target_role == "aggregation":
                    raise ValueError(
                        f"shared-ui must not depend on a feature root: {target_path}"
                    )
    for expression in spec.get("aggregation", {}).get("dependencies", []):
        for target_path in project_dependencies(expression):
            target = feature_target(target_path, base_directory)
            target_role = project_role(target_path, base_directory)
            if (
                target_role == "shared-ui"
                and (
                    not target
                    or canonical_gradle_name(target[0]) != canonical_gradle_name(owner)
                )
            ):
                raise ValueError(
                    f"aggregation must not expose another feature's shared-ui: {target_path}"
                )


def safe(root: Path, relative: Path | str) -> Path:
    target = (root / relative).resolve()
    if target != root and root not in target.parents:
        raise ValueError(f"path escapes repository root: {relative}")
    return target


def plugins_block(plugins: list[str]) -> str:
    if not plugins:
        return "plugins {\n    // Add the target repository's verified convention plugin.\n}\n"
    return "plugins {\n" + "\n".join(f"    {line}" for line in plugins) + "\n}\n"


def dependencies_block(platform: str, source_set: str, test_source_set: str, dependencies: list[str], test_dependencies: list[str]) -> str:
    if not dependencies and not test_dependencies:
        return ""
    if platform == "kmp":
        sections = []
        if dependencies:
            body = "\n".join(f"            {line}" for line in dependencies)
            sections.append(f'''    sourceSets.{source_set}.dependencies {{
{body}
    }}''')
        if test_dependencies:
            test_body = "\n".join(f"            {line}" for line in test_dependencies)
            sections.append(f'''    sourceSets.{test_source_set}.dependencies {{
{test_body}
    }}''')
        return f'''\nkotlin {{
{chr(10).join(sections)}
}}
'''
    flat = "\n".join(f"    {line}" for line in dependencies + test_dependencies)
    return f'''\ndependencies {{
{flat}
}}
'''


def build_text(platform: str, source_set: str, test_source_set: str, config: dict) -> str:
    return plugins_block(config.get("plugins", [])) + dependencies_block(
        platform,
        source_set,
        test_source_set,
        config.get("dependencies", []),
        config.get("test_dependencies", []),
    )


def source_roots(spec: dict, layer: str, layer_dir: Path, config: dict) -> list[Path]:
    platform = spec["platform"]
    main_source = spec.get("source_set") or ("commonMain" if platform == "kmp" else "main")
    test_source = spec.get("test_source_set") or ("commonTest" if platform == "kmp" else "test")
    package_suffix = config.get(
        "package_suffix",
        "sharedui" if layer == "shared-ui" else layer,
    )
    package = (
        Path(*spec["package"].split("."))
        if layer == "aggregation"
        else Path(*spec["package"].split("."), *package_suffix.split("."))
    )
    roots = [layer_dir / "src" / main_source / "kotlin" / package]
    if layer not in {"test", "aggregation"}:
        roots.append(layer_dir / "src" / test_source / "kotlin" / package)
    if layer in {"shared-ui", "ui"} and spec.get("create_resource_directory", False):
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
    main_source_set = spec.get("source_set") or ("commonMain" if spec["platform"] == "kmp" else "main")
    test_source_set = spec.get("test_source_set") or ("commonTest" if spec["platform"] == "kmp" else "test")

    if spec.get("aggregation_module", True):
        aggregation = spec.get("aggregation", {"plugins": [], "dependencies": []})
        files.append((feature_dir / build_name, build_text(spec["platform"], main_source_set, test_source_set, aggregation)))
        directories.extend(source_roots(spec, "aggregation", feature_dir, aggregation))

    modules = [module_prefix] if spec.get("aggregation_module", True) else []
    for layer in KNOWN_LAYERS:
        config = spec["layers"].get(layer, {})
        if not config.get("enabled", False):
            continue
        layer_dir = feature_dir / layer
        files.append((layer_dir / build_name, build_text(spec["platform"], main_source_set, test_source_set, config)))
        directories.extend(source_roots(spec, layer, layer_dir, config))
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
