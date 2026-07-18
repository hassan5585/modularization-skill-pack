#!/usr/bin/env python3
"""Preview or install every skill in this transport folder into a repository."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

from validate_skill_pack import validate_pack


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=Path.cwd(), help="Target repository root")
    parser.add_argument("--destination", default=".agents/skills", help="Destination relative to target")
    parser.add_argument("--apply", action="store_true", help="Copy skills; otherwise preview only")
    return parser.parse_args()


def main() -> int:
    options = parse_args()
    source_root = Path(__file__).resolve().parent
    validation_errors = validate_pack(source_root)
    if validation_errors:
        print("error: refusing to install an invalid skill pack", file=sys.stderr)
        for error in validation_errors:
            print(f"  - {error}", file=sys.stderr)
        return 2
    manifest = json.loads((source_root / "skill-pack.json").read_text(encoding="utf-8"))
    target_root = options.target.resolve()
    if not target_root.is_dir():
        print(f"error: target is not a directory: {target_root}", file=sys.stderr)
        return 2
    destination = (target_root / options.destination).resolve()
    if destination != target_root and target_root not in destination.parents:
        print("error: destination escapes target repository", file=sys.stderr)
        return 2
    skills = [source_root / name for name in manifest["skills"]]
    if not skills:
        print("error: no skill folders found beside installer", file=sys.stderr)
        return 2
    conflicts = [destination / skill.name for skill in skills if (destination / skill.name).exists()]
    print(f"{'Installing' if options.apply else 'Dry run:'} {len(skills)} skill(s) into {destination}")
    for skill in skills:
        target = destination / skill.name
        print(f"  - {skill.name}{' [exists]' if target.exists() else ''}")
    if not options.apply:
        return 0
    if conflicts:
        print("error: refusing to overwrite existing skills", file=sys.stderr)
        for conflict in conflicts:
            print(f"  - {conflict}", file=sys.stderr)
        return 3
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".skill-pack-install-", dir=destination.parent))
    installed: list[Path] = []
    try:
        for skill in skills:
            shutil.copytree(skill, staging / skill.name)
        destination.mkdir(parents=True, exist_ok=True)
        for skill in skills:
            target = destination / skill.name
            (staging / skill.name).replace(target)
            installed.append(target)
    except Exception as exc:
        for target in reversed(installed):
            shutil.rmtree(target, ignore_errors=True)
        print(f"error: installation failed and copied skills were rolled back: {exc}", file=sys.stderr)
        return 4
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    print("Skill pack installed. Start with `$modularize-kotlin-codebase` in the target repository.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
