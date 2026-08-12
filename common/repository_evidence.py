#!/usr/bin/env python3
"""Shared repository evidence helpers for focused modularization skills."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

from common.artifact_schema import envelope_fields
from common.gradle_graph import (
    IMPORT_RE,
    PACKAGE_RE,
    PUBLIC_DECL_RE,
    discover_modules,
    source_set_for_path,
    strip_gradle_comments,
    walk_files,
)


KOTLIN_SUFFIXES = {".kt", ".kts"}
SETTINGS_NAMES = {"settings.gradle", "settings.gradle.kts"}


def relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path | None, default: Any | None = None) -> Any:
    if path is None:
        return {} if default is None else default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path | None, payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path is None:
        print(rendered, end="")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")


def artifact(
    *,
    root: Path,
    skill: str,
    script: str,
    inputs: dict[str, Any] | None = None,
    unresolved: list[Any] | None = None,
    gates: dict[str, Any] | None = None,
    verification: list[Any] | None = None,
    **fields: Any,
) -> dict[str, Any]:
    payload = envelope_fields(
        skill=skill,
        script=script,
        repository_root=".",
        inputs=inputs,
        unresolved=unresolved,
        gates=gates,
        verification=verification,
    )
    payload.update(fields)
    return payload


def module_index(root: Path) -> tuple[list[dict[str, Any]], list[tuple[Path, str]]]:
    modules = discover_modules(root)
    directories = sorted(
        ((root / item["directory"], item["path"]) for item in modules),
        key=lambda item: len(item[0].parts),
        reverse=True,
    )
    return modules, directories


def module_for(path: Path, directories: list[tuple[Path, str]]) -> str | None:
    for directory, module in directories:
        try:
            path.relative_to(directory)
            return module
        except ValueError:
            continue
    return None


def read_kotlin_sources(root: Path) -> list[dict[str, Any]]:
    _, directories = module_index(root)
    sources: list[dict[str, Any]] = []
    for path in walk_files(root):
        if path.suffix not in KOTLIN_SUFFIXES or path.name.endswith(".gradle.kts"):
            continue
        if "src" not in path.relative_to(root).parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        code = strip_gradle_comments(text)
        sources.append(
            {
                "path": relative(path, root),
                "module": module_for(path, directories),
                "source_set": source_set_for_path(path),
                "package": (PACKAGE_RE.search(code).group(1) if PACKAGE_RE.search(code) else None),
                "imports": sorted(set(IMPORT_RE.findall(code))),
                "public_declarations": [
                    {"kind": match.group(1), "name": match.group(2)}
                    for match in PUBLIC_DECL_RE.finditer(code)
                    if not _is_non_public_declaration(code, match.start())
                ],
                "text": text,
                "code": code,
                "sha256": sha256_file(path),
            }
        )
    return sources


def _is_non_public_declaration(text: str, offset: int) -> bool:
    line_start = text.rfind("\n", 0, offset) + 1
    prefix = text[line_start:offset]
    return bool(re.search(r"\b(?:internal|private|protected)\b", prefix))


def strip_source_text(source: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in source.items() if key not in {"text", "code"}}


def feature_of(module: str | None) -> str | None:
    if not module:
        return None
    parts = [part for part in module.split(":") if part]
    if len(parts) >= 2 and parts[0] in {"feature", "features"}:
        return parts[1]
    return None


def layer_of(module: str | None) -> str | None:
    if not module:
        return None
    parts = [part for part in module.split(":") if part]
    known_layers = {"domain", "data", "navigation", "ui", "shared-ui", "test", "real"}
    if parts and parts[-1] in known_layers:
        return parts[-1]
    return "aggregation" if feature_of(module) else None


def settings_text(root: Path) -> tuple[str | None, str]:
    for name in sorted(SETTINGS_NAMES):
        path = root / name
        if path.is_file():
            return name, path.read_text(encoding="utf-8", errors="replace")
    return None, ""


def included_modules(root: Path) -> set[str]:
    _, text = settings_text(root)
    return set(re.findall(r"[\"'](:[A-Za-z0-9_:\-]+)[\"']", text))


def gradle_task(module: str, task: str) -> str:
    return f"{module}:{task}" if module != ":" else f":{task}"


def stable_unique(values: Iterable[Any]) -> list[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for value in values:
        key = json.dumps(value, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result
