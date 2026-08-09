#!/usr/bin/env python3
"""Scaffold reviewed foundation modules (core/util/test) from a foundation plan or spec.

Dry-run is the default. Refuses empty modules, overwrites, and production→test edges.
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
CATCH_ALL = re.compile(r"(?:^|:)(common|shared|misc|helpers|base)(?::|$)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--spec", type=Path, required=True, help="foundation-spec or foundation-plan JSON")
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def load_spec(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read spec: {exc}") from exc
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version: {data.get('schema_version')!r}")
    modules = data.get("modules")
    if not isinstance(modules, list) or not modules:
        raise ValueError("modules must be a non-empty list")
    platform = data.get("platform", "kmp")
    if platform not in {"kmp", "android", "jvm"}:
        raise ValueError("platform must be kmp, android, or jvm")
    normalized = []
    for module in modules:
        if isinstance(module, str):
            module = {"path": module, "package": data.get("package", "com.example") + module.replace(":", ".")}
        if not isinstance(module, dict):
            raise ValueError("each module must be an object")
        path = module.get("path")
        if not isinstance(path, str) or not MODULE_RE.fullmatch(path):
            raise ValueError(f"invalid module path: {path!r}")
        if CATCH_ALL.search(path):
            raise ValueError(f"refusing catch-all foundation module: {path}")
        if module.get("candidate_count") == 0:
            raise ValueError(f"refusing empty foundation module with no candidates: {path}")
        package = module.get("package") or data.get("root_package")
        if package is None:
            # derive from path
            package = (data.get("root_package") or "com.example") + "".join(
                f".{part}" for part in path.split(":") if part
            )
        if not PACKAGE_RE.fullmatch(package):
            raise ValueError(f"invalid package for {path}: {package!r}")
        for field in ("plugins", "dependencies"):
            values = module.get(field, [])
            if not isinstance(values, list) or not all(isinstance(v, str) and v for v in values):
                raise ValueError(f"{path}.{field} must be a list of non-empty strings")
            if field == "dependencies":
                for value in values:
                    if re.search(r"project\([^\n]*:test", value, re.IGNORECASE):
                        raise ValueError(f"{path} production dependencies must not include test modules")
        normalized.append(
            {
                "path": path,
                "package": package,
                "plugins": module.get("plugins", []),
                "dependencies": module.get("dependencies", []),
                "kind": module.get("kind")
                or (
                    "test"
                    if path.startswith(":test")
                    else ("util" if path.startswith(":util:") else "core")
                ),
            }
        )
    data = dict(data)
    data["modules"] = normalized
    data["platform"] = platform
    return data


def safe(root: Path, relative: Path) -> Path:
    target = (root / relative).resolve()
    if target != root and root not in target.parents:
        raise ValueError(f"path escapes repository root: {relative}")
    return target


def build_text(platform: str, source_set: str, module: dict) -> str:
    plugins = module.get("plugins") or []
    plugin_block = "plugins {\n" + (
        "\n".join(f"    {p}" for p in plugins) if plugins else "    // Add verified convention plugin."
    ) + "\n}\n"
    deps = module.get("dependencies") or []
    if not deps:
        return plugin_block
    if platform == "kmp":
        body = "\n".join(f"            {d}" for d in deps)
        return plugin_block + f"\nkotlin {{\n    sourceSets.{source_set}.dependencies {{\n{body}\n    }}\n}}\n"
    body = "\n".join(f"    {d}" for d in deps)
    return plugin_block + f"\ndependencies {{\n{body}\n}}\n"


def create_plan(root: Path, spec: dict) -> tuple[list[tuple[Path, str]], list[Path], list[str]]:
    files: list[tuple[Path, str]] = []
    directories: list[Path] = []
    modules: list[str] = []
    build_name = spec.get("build_file_name", "build.gradle.kts")
    source_set = spec.get("source_set") or ("commonMain" if spec["platform"] == "kmp" else "main")
    for module in spec["modules"]:
        relative = Path(*[part for part in module["path"].split(":") if part])
        directory = safe(root, relative)
        files.append((directory / build_name, build_text(spec["platform"], source_set, module)))
        directories.append(directory / "src" / source_set / "kotlin" / Path(*module["package"].split(".")))
        modules.append(module["path"])
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
    print(f"{'Applying' if options.apply else 'Dry run:'} {len(modules)} foundation module(s)")
    for path, _ in files:
        print(f"  - {path.relative_to(root)}{' [exists]' if path.exists() else ''}")
    print("\nAdd to settings after review:")
    print("  include(" + ", ".join(f'"{m}"' for m in modules) + ")")
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
    print("Foundation modules scaffolded. Register settings and wire DI only after review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
