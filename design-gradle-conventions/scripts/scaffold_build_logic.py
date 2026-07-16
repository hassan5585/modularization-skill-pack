#!/usr/bin/env python3
"""Scaffold a thin Gradle included build from an explicit reviewed JSON spec.

Dry-run is the default. Pass --apply to write. Existing files are never replaced
unless --force is also passed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


SCHEMA_VERSION = 1
PLUGIN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]+$")
IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
PACKAGE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def load_spec(path: Path) -> dict:
    try:
        spec = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read spec: {exc}") from exc
    if spec.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version: {spec.get('schema_version')!r}")
    for key in ("directory", "group", "package", "plugins"):
        if not spec.get(key):
            raise ValueError(f"missing required spec field: {key}")
    if not PACKAGE_RE.match(spec["package"]):
        raise ValueError(f"invalid Kotlin package: {spec['package']}")
    if not isinstance(spec["plugins"], list) or not spec["plugins"]:
        raise ValueError("plugins must be a non-empty list")
    seen_ids: set[str] = set()
    seen_classes: set[str] = set()
    for plugin in spec["plugins"]:
        for key in ("registration_name", "id", "class_name"):
            if not plugin.get(key):
                raise ValueError(f"plugin is missing {key}: {plugin}")
        if not IDENT_RE.match(plugin["registration_name"]):
            raise ValueError(f"invalid registration_name: {plugin['registration_name']}")
        if not PLUGIN_ID_RE.match(plugin["id"]):
            raise ValueError(f"invalid plugin id: {plugin['id']}")
        if not IDENT_RE.match(plugin["class_name"]):
            raise ValueError(f"invalid class_name: {plugin['class_name']}")
        if plugin["id"] in seen_ids or plugin["class_name"] in seen_classes:
            raise ValueError(f"duplicate plugin id or class: {plugin}")
        seen_ids.add(plugin["id"])
        seen_classes.add(plugin["class_name"])
        if not all(isinstance(line, str) for line in plugin.get("body", [])):
            raise ValueError(f"plugin body must be a list of strings: {plugin['id']}")
    return spec


def safe_target(root: Path, relative: str) -> Path:
    target = (root / relative).resolve()
    if target != root and root not in target.parents:
        raise ValueError(f"path escapes repository root: {relative}")
    return target


def settings_text(spec: dict) -> str:
    repositories = "\n".join(f"        {repo}" for repo in spec.get("repositories", ["mavenCentral()", "gradlePluginPortal()"]))
    catalog = spec.get("version_catalog")
    catalog_block = ""
    if catalog:
        catalog_block = f'''\n    versionCatalogs {{
        create("libs") {{
            from(files("{catalog}"))
        }}
    }}'''
    return f'''pluginManagement {{
    repositories {{
{repositories}
    }}
}}

dependencyResolutionManagement {{
    repositories {{
{repositories}
    }}{catalog_block}
}}

rootProject.name = "{spec.get('project_name', 'build-logic')}"
include(":convention")
'''


def build_text(spec: dict) -> str:
    repositories = "\n".join(f"    {repo}" for repo in spec.get("repositories", ["mavenCentral()", "gradlePluginPortal()"]))
    compile_only = spec.get("compile_only", [])
    dependencies = ""
    if compile_only:
        dependencies = "\ndependencies {\n" + "\n".join(f"    compileOnly({expr})" for expr in compile_only) + "\n}\n"
    registrations = []
    for plugin in spec["plugins"]:
        registrations.append(f'''        register("{plugin['registration_name']}") {{
            id = "{plugin['id']}"
            implementationClass = "{spec['package']}.{plugin['class_name']}"
        }}''')
    return f'''plugins {{
    `kotlin-dsl`
}}

group = "{spec['group']}"

repositories {{
{repositories}
}}
{dependencies}
gradlePlugin {{
    plugins {{
{chr(10).join(registrations)}
    }}
}}
'''


def plugin_text(spec: dict, plugin: dict) -> str:
    apply_lines = [f'        pluginManager.apply("{plugin_id}")' for plugin_id in plugin.get("applies", [])]
    body_lines = ["        " + line if line else "" for line in plugin.get("body", [])]
    lines = apply_lines + body_lines
    if not lines:
        lines = ["        // Intentionally empty until target-specific configuration is added."]
    return f'''package {spec['package']}

import org.gradle.api.Plugin
import org.gradle.api.Project

class {plugin['class_name']} : Plugin<Project> {{
    override fun apply(target: Project) = with(target) {{
{chr(10).join(lines)}
    }}
}}
'''


def plans(root: Path, spec: dict) -> list[tuple[Path, str]]:
    base = safe_target(root, spec["directory"])
    package_path = Path(*spec["package"].split("."))
    result = [
        (base / "settings.gradle.kts", settings_text(spec)),
        (base / "convention" / "build.gradle.kts", build_text(spec)),
    ]
    source = base / "convention" / "src" / "main" / "kotlin" / package_path
    for plugin in spec["plugins"]:
        result.append((source / f"{plugin['class_name']}.kt", plugin_text(spec, plugin)))
    return result


def main() -> int:
    options = parse_args()
    root = options.root.resolve()
    if not root.is_dir():
        print(f"error: root is not a directory: {root}", file=sys.stderr)
        return 2
    try:
        spec = load_spec(options.spec)
        write_plans = plans(root, spec)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    existing = [path for path, _ in write_plans if path.exists()]
    print(f"{'Applying' if options.apply else 'Dry run:'} {len(write_plans)} build-logic file(s)")
    for path, _ in write_plans:
        marker = " [exists]" if path.exists() else ""
        print(f"  - {path.relative_to(root)}{marker}")
    print("\nAdd this inside the root settings.gradle(.kts) pluginManagement block after review:")
    print(f'  includeBuild("{spec["directory"]}")')
    if not options.apply:
        return 0
    if existing and not options.force:
        print("error: refusing to replace existing files; review them or pass --force", file=sys.stderr)
        return 3
    for path, content in write_plans:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    print("Scaffold written. Complete typed target-specific configuration and compile the included build before converting modules.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
