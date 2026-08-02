#!/usr/bin/env python3
"""Fast standard-library structural checks for this KMP repository."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PACKAGE_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){1,}$")
FORBIDDEN_NATIVE = ("framework.export(", "transitiveExport", "-Xdisable-phases")
REQUIRED_FEATURE_LAYERS = ("domain", "data", "navigation", "ui")


def main() -> int:
    errors: list[str] = []
    manifest_path = ROOT / "bootstrap-manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"cannot read bootstrap-manifest.json: {exc}")
        manifest = {}

    package_name = manifest.get("package_name", "")
    if not PACKAGE_RE.fullmatch(package_name):
        errors.append(f"invalid manifest package: {package_name!r}")

    required = [
        "settings.gradle.kts", "gradle/libs.versions.toml", "plugins/convention/build.gradle.kts",
        "androidApp/build.gradle.kts", "composeApp/build.gradle.kts",
        "iosApp/iosApp.xcodeproj/project.pbxproj", "core/domain/build.gradle.kts",
        "core/data/build.gradle.kts", "core/navigation/build.gradle.kts", "core/ui/build.gradle.kts",
    ]
    for relative in required:
        if not (ROOT / relative).is_file():
            errors.append(f"missing required file: {relative}")

    settings = (ROOT / "settings.gradle.kts").read_text(encoding="utf-8")
    expected_root_name = manifest.get("root_project_name", "")
    if f'rootProject.name = "{expected_root_name}"' not in settings:
        errors.append(
            "settings.gradle.kts rootProject.name does not match bootstrap-manifest.json"
        )
    for feature in sorted(path.name for path in (ROOT / "feature").iterdir() if path.is_dir()):
        feature_root = ROOT / "feature" / feature
        for layer in REQUIRED_FEATURE_LAYERS:
            build = feature_root / layer / "build.gradle.kts"
            if not build.is_file():
                errors.append(f"feature/{feature} is missing {layer}/build.gradle.kts")
            gradle_path = f'":feature:{feature}:{layer}"'
            if gradle_path not in settings:
                errors.append(f"settings.gradle.kts does not register :feature:{feature}:{layer}")
        root_build = (feature_root / "build.gradle.kts").read_text(encoding="utf-8")
        if f'project(":feature:{feature}:test")' in root_build:
            errors.append(f"feature/{feature} production root aggregates its test module")

    for path in ROOT.rglob("*.kt"):
        relative = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        if "/src/commonMain/" in f"/{relative}" and re.search(
            r"^import (android\.|platform\.|java\.|swiftPMImport\.)", text, re.MULTILINE
        ):
            errors.append(f"platform import found in commonMain: {relative}")
        if "/feature/" in f"/{relative}" and "/ui/" in f"/{relative}" and "viewModelScope.launch" in text:
            errors.append(f"direct viewModelScope.launch found in feature UI: {relative}")

    for path in list(ROOT.rglob("*.gradle.kts")) + list(ROOT.rglob("*.kt")):
        text = path.read_text(encoding="utf-8")
        for forbidden in FORBIDDEN_NATIVE:
            if forbidden in text:
                errors.append(f"forbidden native export/linker pattern {forbidden!r}: {path.relative_to(ROOT)}")

    bridge = ROOT / "composeApp" / "src" / "iosMain" / "kotlin"
    bridge_files = list(bridge.rglob("IosAppBridge.kt"))
    if len(bridge_files) != 1:
        errors.append("composeApp must contain exactly one IosAppBridge.kt")

    if errors:
        print(f"Repository verification failed with {len(errors)} error(s):", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("Repository verification passed.")
    print(f"Package: {package_name}")
    print(f"Modules: {len(manifest.get('modules', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
