#!/usr/bin/env python3
"""Discover feature scaffolding conventions from an existing modular repository.

Read-only. Emits a JSON snapshot agents can adapt into a feature-spec.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


SCHEMA_VERSION = 1
SCRIPT_VERSION = "1"
PLUGIN_RES = (
    re.compile(r"alias\(\s*libs\.plugins\.([A-Za-z0-9_.-]+)\s*\)"),
    re.compile(r"id\(\s*[\"']([^\"']+)[\"']\s*\)"),
)
PROJECT_RES = (
    re.compile(r"project\(\s*[\"'](:[^\"']+)[\"']\s*\)"),
    re.compile(r"project\(\s*path\s*[:=]\s*[\"'](:[^\"']+)[\"']"),
    re.compile(r"(?<![A-Za-z0-9_.])projects\.([A-Za-z0-9_.]+)"),
)
PACKAGE_RE = re.compile(r"(?m)^\s*package\s+([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)")
KNOWN_LAYERS = ("domain", "data", "navigation", "shared-ui", "ui", "test")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--feature-root", default="feature", help="Directory that contains features")
    parser.add_argument("--json-out", type=Path)
    return parser.parse_args()


def plugins(text: str) -> list[str]:
    found: list[str] = []
    for regex in PLUGIN_RES:
        found.extend(regex.findall(text))
    return sorted(set(found))


def project_deps(text: str) -> list[str]:
    found: list[str] = []
    for regex in PROJECT_RES:
        for match in regex.finditer(text):
            value = match.group(1)
            if not value.startswith(":"):
                segments = [
                    re.sub(r"(?<!^)(?=[A-Z])", "-", segment).lower()
                    for segment in value.split(".")
                ]
                value = ":" + ":".join(segments)
            found.append(value)
    return sorted(set(found))


def first_package(directory: Path) -> str | None:
    for path in sorted(directory.rglob("*.kt")):
        if any(part in {".modularization", "build", ".git"} for part in path.parts):
            continue
        match = PACKAGE_RE.search(path.read_text(encoding="utf-8", errors="replace"))
        if match:
            return match.group(1)
    return None


def detect_platform(feature_dir: Path) -> str:
    for path in feature_dir.rglob("*"):
        if path.name in {"build.gradle", "build.gradle.kts"}:
            text = path.read_text(encoding="utf-8", errors="replace").lower()
            if "org.jetbrains.kotlin.multiplatform" in text or "kotlin.multiplatform" in text:
                return "kmp"
            if "com.android.library" in text or "com.android.application" in text:
                return "android"
    if any((feature_dir / layer / "src" / "commonMain").exists() for layer in KNOWN_LAYERS):
        return "kmp"
    if any((feature_dir / layer / "src" / "main").exists() for layer in KNOWN_LAYERS):
        return "android"
    return "jvm"


def discover(root: Path, feature_root: str) -> dict:
    base = root / feature_root
    features = []
    layer_plugins: dict[str, list[str]] = {layer: [] for layer in KNOWN_LAYERS}
    dependency_style = "string-project"
    platforms: list[str] = []
    if base.is_dir():
        for child in sorted(base.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            layers_present = []
            for layer in KNOWN_LAYERS:
                build = None
                for name in ("build.gradle.kts", "build.gradle"):
                    candidate = child / layer / name
                    if candidate.is_file():
                        build = candidate
                        break
                if build is None:
                    continue
                text = build.read_text(encoding="utf-8", errors="replace")
                layers_present.append(layer)
                layer_plugins[layer].extend(plugins(text))
                if "projects." in text:
                    dependency_style = "type-safe-accessor"
                elif 'project("' in text or "project('" in text:
                    dependency_style = "string-project"
            platforms.append(detect_platform(child))
            package = first_package(child)
            features.append(
                {
                    "name": child.name,
                    "directory": child.relative_to(root).as_posix(),
                    "layers": layers_present,
                    "package": package,
                    "has_aggregation": any(
                        (child / name).is_file() for name in ("build.gradle.kts", "build.gradle")
                    ),
                }
            )
    platform = "kmp"
    if platforms:
        platform = max(set(platforms), key=platforms.count)
    conventions = {
        "schema_version": SCHEMA_VERSION,
        "generator": {
            "skill": "scaffold-kotlin-feature",
            "script": "discover_feature_conventions.py",
            "version": SCRIPT_VERSION,
        },
        "repository": {"root": ".", "revision": None},
        "inputs": {"feature_root": feature_root},
        "platform": platform,
        "feature_root": feature_root,
        "dependency_style": dependency_style,
        "build_file_name": "build.gradle.kts",
        "source_set": "commonMain" if platform == "kmp" else "main",
        "test_source_set": "commonTest" if platform == "kmp" else "test",
        "features": features,
        "layer_plugin_ids": {
            layer: sorted(set(values)) for layer, values in layer_plugins.items() if values
        },
        "recommended_layers": ["domain", "data", "navigation", "ui"],
        "optional_layers": ["shared-ui", "test"],
        "settings_files": [
            path.name
            for path in (root / "settings.gradle.kts", root / "settings.gradle")
            if path.is_file()
        ],
        "notes": [
            "Adapt plugin aliases and project dependencies to match this repository before scaffolding.",
            "Do not invent DI, navigation, or app wiring; leave those as reviewed manual steps when not inferable.",
        ],
    }
    return conventions


def main() -> int:
    options = parse_args()
    root = options.root.resolve()
    if not root.is_dir():
        print(f"error: root is not a directory: {root}", file=sys.stderr)
        return 2
    data = discover(root, options.feature_root)
    text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    if options.json_out:
        options.json_out.parent.mkdir(parents=True, exist_ok=True)
        options.json_out.write_text(text, encoding="utf-8")
        print(f"Wrote feature conventions to {options.json_out}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
