#!/usr/bin/env python3
"""Validate the modularization skill pack using only the Python standard library."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
QUOTED_YAML_RE = re.compile(r'^\s{2}([a-z_]+):\s+"(.*)"\s*$')


def scalar(value: str) -> str:
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        return bytes(value[1:-1], "utf-8").decode("unicode_escape")
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1].replace("''", "'")
    return value


def frontmatter(path: Path) -> tuple[dict[str, str], list[str]]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, [f"{path}: missing or malformed YAML frontmatter"]
    values: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line or line.startswith((" ", "\t")):
            errors.append(f"{path}: frontmatter must contain flat key/value pairs: {line!r}")
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = scalar(value)
    unexpected = set(values) - {"name", "description"}
    if unexpected:
        errors.append(f"{path}: unexpected frontmatter keys: {sorted(unexpected)}")
    if not NAME_RE.fullmatch(values.get("name", "")) or len(values.get("name", "")) > 64:
        errors.append(f"{path}: invalid skill name: {values.get('name')!r}")
    description = values.get("description", "")
    if not description or len(description) > 1024 or "<" in description or ">" in description:
        errors.append(f"{path}: description is empty, too long, or contains angle brackets")
    return values, errors


def validate_openai(skill: Path, name: str) -> list[str]:
    path = skill / "agents" / "openai.yaml"
    if not path.is_file():
        return [f"{path}: missing agents/openai.yaml"]
    fields: dict[str, str] = {}
    errors: list[str] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "interface:":
        errors.append(f"{path}: first line must be interface:")
    for line in lines[1:]:
        match = QUOTED_YAML_RE.match(line)
        if not match:
            errors.append(f"{path}: interface values must be two-space-indented quoted strings: {line!r}")
            continue
        fields[match.group(1)] = match.group(2)
    for key in ("display_name", "short_description", "default_prompt"):
        if not fields.get(key):
            errors.append(f"{path}: missing interface.{key}")
    if fields.get("short_description") and not 25 <= len(fields["short_description"]) <= 64:
        errors.append(f"{path}: short_description must be 25-64 characters")
    if fields.get("default_prompt") and f"${name}" not in fields["default_prompt"]:
        errors.append(f"{path}: default_prompt must mention ${name}")
    return errors


def validate_links(skill: Path) -> list[str]:
    errors: list[str] = []
    source = skill / "SKILL.md"
    for target in MARKDOWN_LINK_RE.findall(source.read_text(encoding="utf-8")):
        if "://" in target or target.startswith("#"):
            continue
        relative = target.split("#", 1)[0]
        if relative and not (skill / relative).is_file():
            errors.append(f"{source}: linked resource does not exist: {target}")
    return errors


def validate_pack(root: Path) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    manifest_path = root / "skill-pack.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{manifest_path}: cannot read manifest: {exc}"]
    if manifest.get("schema_version") != 1:
        errors.append(f"{manifest_path}: unsupported schema_version")
    names = manifest.get("skills")
    if not isinstance(names, list) or not names or len(set(names)) != len(names):
        errors.append(f"{manifest_path}: skills must be a non-empty unique list")
        names = []
    discovered = sorted(path.name for path in root.iterdir() if path.is_dir() and (path / "SKILL.md").is_file())
    if sorted(names) != discovered:
        errors.append(f"{manifest_path}: manifest skills {sorted(names)} do not match folders {discovered}")
    for path in root.rglob("*"):
        if path.is_symlink():
            errors.append(f"{path}: symlinks are not permitted in the transport pack")
    for name in names:
        skill = root / name
        metadata, skill_errors = frontmatter(skill / "SKILL.md")
        errors.extend(skill_errors)
        if metadata.get("name") != name:
            errors.append(f"{skill}: folder and frontmatter names differ")
        errors.extend(validate_openai(skill, name))
        errors.extend(validate_links(skill))
        if len((skill / "SKILL.md").read_text(encoding="utf-8").splitlines()) > 500:
            errors.append(f"{skill / 'SKILL.md'}: exceeds the 500-line progressive-disclosure limit")
    for path in root.rglob("*.json"):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path}: invalid JSON: {exc}")
            continue
        if path.name != "skill-pack.json" and isinstance(value, dict) and value.get("schema_version") != 1:
            errors.append(f"{path}: missing or unsupported schema_version")
    for path in list(root.rglob("*.py")):
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except (OSError, SyntaxError) as exc:
            errors.append(f"{path}: Python compilation failed: {exc}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path(__file__).resolve().parent)
    options = parser.parse_args()
    errors = validate_pack(options.root)
    if errors:
        print(f"Skill-pack validation failed with {len(errors)} error(s):", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("Skill-pack validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
