#!/usr/bin/env python3
"""Preview or create an opinionated modular Kotlin Multiplatform repository."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path


PACKAGE_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){1,}$")
APP_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .&'()-]{0,59}$")
TEXT_SUFFIXES = {
    "", ".conf", ".editorconfig", ".gitignore", ".gradle", ".kts", ".kt",
    ".md", ".plist", ".properties", ".pro", ".pbxproj", ".sh", ".swift",
    ".toml", ".xml", ".xcconfig", ".xcscheme", ".yaml", ".yml",
}
REQUIRED_PATHS = (
    "AGENTS.md",
    "settings.gradle.kts",
    "gradle/libs.versions.toml",
    "gradle/wrapper/gradle-wrapper.jar",
    "plugins/convention/build.gradle.kts",
    "androidApp/build.gradle.kts",
    "composeApp/build.gradle.kts",
    "iosApp/iosApp.xcodeproj/project.pbxproj",
    "core/domain/build.gradle.kts",
    "core/data/build.gradle.kts",
    "core/navigation/build.gradle.kts",
    "core/ui/build.gradle.kts",
    "feature/home/domain/build.gradle.kts",
    "feature/home/data/build.gradle.kts",
    "feature/home/navigation/build.gradle.kts",
    "feature/home/ui/build.gradle.kts",
    "feature/home/test/build.gradle.kts",
    "util/platform/domain/build.gradle.kts",
    "util/platform/real/build.gradle.kts",
    "test/build.gradle.kts",
    "test/core/build.gradle.kts",
    "scripts/verify_repository.py",
)
TOKEN_RE = re.compile(r"@@[A-Z0-9_]+@@|__PACKAGE_PATH__")


class UserError(RuntimeError):
    """A concise input or environment failure."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-name", required=True, help="Human-facing app display name")
    parser.add_argument("--output", required=True, type=Path, help="Full new repository path")
    parser.add_argument("--package-name", required=True, help="Reverse-DNS package/application ID")
    parser.add_argument("--apply", action="store_true", help="Create the repository; otherwise preview")
    parser.add_argument("--no-git", action="store_true", help="Do not initialize a Git repository")
    parser.add_argument("--without-skills", action="store_true", help="Do not install repository-local skills")
    return parser.parse_args()


def validate_inputs(options: argparse.Namespace) -> tuple[str, Path, str]:
    app_name = options.app_name.strip()
    package_name = options.package_name.strip()
    if not APP_NAME_RE.fullmatch(app_name):
        raise UserError(
            "app name must be 1-60 characters and contain only letters, numbers, spaces, "
            "periods, ampersands, apostrophes, parentheses, or hyphens"
        )
    if not PACKAGE_RE.fullmatch(package_name):
        raise UserError(
            "package name must be lower-case reverse-DNS notation with at least two segments, "
            "for example com.example.focusgarden"
        )
    output = options.output.expanduser()
    if not output.is_absolute():
        raise UserError("--output must be an absolute path")
    output = output.resolve(strict=False)
    home = Path.home().resolve()
    if output in {Path("/"), home}:
        raise UserError("refusing to use a filesystem root or home directory as the repository")
    if output.exists():
        raise UserError(f"destination already exists; refusing to merge or overwrite: {output}")
    if output.name in {"", ".", ".."}:
        raise UserError("destination must end in a repository directory name")
    return app_name, output, package_name


def skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def pack_root() -> Path | None:
    candidate = skill_root().parent
    return candidate if (candidate / "skill-pack.json").is_file() else None


def skill_names_to_install() -> list[str]:
    pack = pack_root()
    if pack is None:
        return [skill_root().name]
    manifest = json.loads((pack / "skill-pack.json").read_text(encoding="utf-8"))
    names = manifest.get("skills")
    if not isinstance(names, list) or not all(isinstance(item, str) for item in names):
        raise UserError(f"invalid sibling skill-pack manifest: {pack / 'skill-pack.json'}")
    return names


def replacement_map(app_name: str, output: Path, package_name: str) -> dict[str, str]:
    return {
        "@@APP_NAME@@": app_name,
        "@@APP_NAME_XML@@": html.escape(app_name, quote=True),
        "@@DEV_APP_NAME@@": f"{app_name} Dev",
        "@@DEV_APP_NAME_XML@@": html.escape(f"{app_name} Dev", quote=True),
        "@@PACKAGE@@": package_name,
        "@@PACKAGE_PATH@@": package_name.replace(".", "/"),
        "@@REPO_NAME@@": output.name,
        "@@GENERATED_DATE@@": date.today().isoformat(),
    }


def substitute_tree(root: Path, replacements: dict[str, str], package_name: str) -> None:
    package_parts = package_name.split(".")
    marker_dirs = sorted(
        (path for path in root.rglob("__PACKAGE_PATH__") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for marker in marker_dirs:
        destination = marker.parent.joinpath(*package_parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise UserError(f"template package path collision: {destination}")
        shutil.move(str(marker), str(destination))

    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        updated = content
        for token, value in replacements.items():
            updated = updated.replace(token, value)
        if updated != content:
            path.write_text(updated, encoding="utf-8")


def copy_local_skills(destination: Path) -> list[str]:
    names = skill_names_to_install()
    source_pack = pack_root()
    skills_destination = destination / ".agents" / "skills"
    skills_destination.mkdir(parents=True, exist_ok=True)
    for name in names:
        source = (source_pack / name) if source_pack else skill_root()
        if not (source / "SKILL.md").is_file():
            raise UserError(f"skill listed for installation is missing: {source}")
        shutil.copytree(
            source,
            skills_destination / name,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    if source_pack and (source_pack / "common").is_dir():
        shutil.copytree(
            source_pack / "common",
            skills_destination / "common",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    return names


def write_bootstrap_manifest(
    destination: Path,
    app_name: str,
    package_name: str,
    root_project_name: str,
    installed_skills: list[str],
) -> None:
    manifest = {
        "schema_version": 1,
        "generator": "create-kmp-repository",
        "generated_on": date.today().isoformat(),
        "app_name": app_name,
        "root_project_name": root_project_name,
        "package_name": package_name,
        "platforms": ["android", "ios"],
        "environments": ["dev", "prod"],
        "build_types": ["debug", "release"],
        "modules": [
            ":androidApp", ":composeApp", ":core", ":core:domain", ":core:data",
            ":core:navigation", ":core:ui", ":feature:home", ":feature:home:domain",
            ":feature:home:data", ":feature:home:navigation", ":feature:home:ui",
            ":feature:home:test", ":util:platform", ":util:platform:domain",
            ":util:platform:real", ":test", ":test:core",
        ],
        "installed_skills": installed_skills,
        "first_commands": [
            "python3 scripts/verify_repository.py",
            "./gradlew projects",
            "./gradlew :plugins:convention:build",
            "./gradlew testAndroidHostTest",
            "./gradlew :androidApp:assembleDevDebug",
        ],
    }
    (destination / "bootstrap-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )


def verify_staged_repository(root: Path) -> None:
    missing = [relative for relative in REQUIRED_PATHS if not (root / relative).is_file()]
    if missing:
        raise UserError("generated repository is missing required paths: " + ", ".join(missing))
    unresolved: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if ".agents" in path.relative_to(root).parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        match = TOKEN_RE.search(text)
        if match:
            unresolved.append(f"{path.relative_to(root)}:{match.group(0)}")
    if unresolved:
        raise UserError("unresolved template tokens: " + ", ".join(unresolved[:10]))
    if any(
        path.name == "__PACKAGE_PATH__" and ".agents" not in path.relative_to(root).parts
        for path in root.rglob("*")
    ):
        raise UserError("unresolved package path marker")


def initialize_git(root: Path) -> None:
    try:
        result = subprocess.run(
            ["git", "init", "-b", "main"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
    except OSError as exc:
        raise UserError(f"Git initialization failed: {exc}") from exc
    if result.returncode != 0:
        raise UserError(f"Git initialization failed: {result.stdout.strip()}")


def preview(app_name: str, output: Path, package_name: str, install_skills: bool) -> None:
    variants = "devDebug, devRelease, prodDebug, prodRelease"
    modules = "18 Gradle modules plus the included :plugins:convention build"
    print("KMP repository creation preview")
    print(f"  App name: {app_name}")
    print(f"  Destination: {output}")
    print(f"  Package/application ID: {package_name}")
    print(f"  Android variants: {variants}")
    print("  iOS configurations: DevDebug, DevRelease, ProdDebug, ProdRelease")
    print(f"  Structure: {modules}")
    print("  Stack: Compose Multiplatform, Metro, Navigation 3, Ktor, Room, DataStore, Coil")
    print("  Tests: kotlin.test, coroutines-test, Turbine, Ktor MockEngine, Android host tests")
    if install_skills:
        print("  Repository-local skills: " + ", ".join(skill_names_to_install()))
    else:
        print("  Repository-local skills: disabled")
    print("  Existing destinations are never overwritten; use --apply to create this repository.")


def create_repository(
    app_name: str,
    output: Path,
    package_name: str,
    initialize_repository_git: bool,
    install_skills: bool,
) -> None:
    template = skill_root() / "assets" / "repository-template"
    if not template.is_dir():
        raise UserError(f"repository template is missing: {template}")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}-bootstrap-", dir=output.parent))
    try:
        shutil.copytree(template, staging, dirs_exist_ok=True)
        substitute_tree(staging, replacement_map(app_name, output, package_name), package_name)
        installed = copy_local_skills(staging) if install_skills else []
        write_bootstrap_manifest(staging, app_name, package_name, output.name, installed)
        for relative in ("gradlew", "scripts/verify_repository.py"):
            path = staging / relative
            path.chmod(path.stat().st_mode | 0o111)
        verify_staged_repository(staging)
        if initialize_repository_git:
            initialize_git(staging)
        if output.exists():
            raise UserError(f"destination appeared during generation; refusing to overwrite: {output}")
        staging.replace(output)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    print(f"Created Kotlin Multiplatform repository: {output}")
    print(f"Next: cd {output}")
    print("Then run: python3 scripts/verify_repository.py")
    print("Then run: ./gradlew projects :plugins:convention:build testAndroidHostTest")


def main() -> int:
    try:
        options = parse_args()
        app_name, output, package_name = validate_inputs(options)
        if not options.apply:
            preview(app_name, output, package_name, not options.without_skills)
            return 0
        create_repository(
            app_name=app_name,
            output=output,
            package_name=package_name,
            initialize_repository_git=not options.no_git,
            install_skills=not options.without_skills,
        )
        return 0
    except (UserError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
