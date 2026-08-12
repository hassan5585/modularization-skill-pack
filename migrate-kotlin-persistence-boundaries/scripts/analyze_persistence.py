#!/usr/bin/env python3
"""Audit and plan schema-preserving Kotlin persistence boundary moves."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

_PACK_ROOT = Path(__file__).resolve().parents[2]
if str(_PACK_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACK_ROOT))

from common.gradle_graph import walk_files  # type: ignore
from common.repository_evidence import (  # type: ignore
    artifact,
    layer_of,
    load_json,
    module_for,
    module_index,
    read_kotlin_sources,
    relative,
    sha256_file,
    strip_source_text,
    write_json,
)

SKILL = "migrate-kotlin-persistence-boundaries"
SCRIPT = "analyze_persistence.py"
DATABASE_START_RE = re.compile(r"@Database\s*\(")
DATABASE_VERSION_RE = re.compile(r"\bversion\s*=\s*([A-Za-z_][A-Za-z0-9_.]*|\d+)")
ROOM_CLASS_RE = re.compile(r"\b(?:public\s+|internal\s+)?(?:abstract\s+)?class\s+(\w+)\s*:\s*RoomDatabase\b")
ENTITY_START_RE = re.compile(r"@Entity\b")
TABLE_NAME_RE = re.compile(r"\btableName\s*=\s*[\"']([^\"']+)[\"']")
ENTITY_CLASS_RE = re.compile(r"\b(?:public\s+|internal\s+)?(?:data\s+)?class\s+(\w+)\b")
COLUMN_RE = re.compile(r"@ColumnInfo\s*\([^)]*?name\s*=\s*[\"']([^\"']+)[\"']")
PREFERENCE_RE = re.compile(r"(?:boolean|int|long|float|double|string|stringSet)PreferencesKey\s*\(\s*[\"']([^\"']+)[\"']")
SQL_TABLE_RE = re.compile(r"(?im)\bCREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+([A-Za-z_][A-Za-z0-9_]*)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    audit = subs.add_parser("audit")
    audit.add_argument("--root", type=Path, default=Path.cwd())
    audit.add_argument("--rules", type=Path)
    audit.add_argument("--json-out", type=Path)
    plan = subs.add_parser("plan")
    plan.add_argument("--root", type=Path, default=Path.cwd())
    plan.add_argument("--audit", type=Path, required=True)
    plan.add_argument("--rules", type=Path)
    plan.add_argument("--json-out", type=Path)
    return parser


def classify(text: str, path: str) -> list[str]:
    kinds: list[str] = []
    checks = (
        ("room-database", r"@Database\b|RoomDatabase"),
        ("room-entity", r"@Entity\b"),
        ("room-dao", r"@Dao\b"),
        ("room-migration", r"\bMigration\s*\("),
        ("sqldelight", r"SqlDriver|app.cash.sqldelight|com.squareup.sqldelight"),
        ("datastore", r"DataStore<|preferencesDataStore|PreferencesKey"),
        ("platform-driver", r"AndroidSqliteDriver|NativeSqliteDriver|RoomDatabase\.Builder|BundledSQLiteDriver"),
    )
    for kind, pattern in checks:
        if re.search(pattern, text):
            kinds.append(kind)
    if path.endswith((".sq", ".sqm")):
        kinds.append("sqldelight-schema")
    return kinds


def room_databases(text: str) -> list[tuple[str, int | str]]:
    """Return Room database names and literal/constant version expressions."""
    result: list[tuple[str, int | str]] = []
    cursor = 0
    while True:
        start = DATABASE_START_RE.search(text, cursor)
        if not start:
            break
        open_index = text.find("(", start.start())
        depth = 0
        quote: str | None = None
        close_index: int | None = None
        index = open_index
        while index < len(text):
            character = text[index]
            if quote:
                if character == "\\":
                    index += 2
                    continue
                if character == quote:
                    quote = None
            elif character in {'\"', "'"}:
                quote = character
            elif character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
                if depth == 0:
                    close_index = index
                    break
            index += 1
        if close_index is None:
            break
        body = text[open_index + 1 : close_index]
        version_match = DATABASE_VERSION_RE.search(body)
        class_match = ROOM_CLASS_RE.search(text[close_index + 1 : close_index + 4000])
        if version_match and class_match:
            expression = version_match.group(1)
            version: int | str = int(expression) if expression.isdigit() else expression
            result.append((class_match.group(1), version))
        cursor = close_index + 1
    return result


def room_entities(text: str) -> list[str]:
    """Return explicit Room table names or entity class names when implicit."""
    result: list[str] = []
    cursor = 0
    while True:
        start = ENTITY_START_RE.search(text, cursor)
        if not start:
            break
        position = start.end()
        while position < len(text) and text[position].isspace():
            position += 1
        body = ""
        close_index = position
        has_arguments = position < len(text) and text[position] == "("
        if has_arguments:
            depth = 0
            quote: str | None = None
            index = position
            while index < len(text):
                character = text[index]
                if quote:
                    if character == "\\":
                        index += 2
                        continue
                    if character == quote:
                        quote = None
                elif character in {'\"', "'"}:
                    quote = character
                elif character == "(":
                    depth += 1
                elif character == ")":
                    depth -= 1
                    if depth == 0:
                        close_index = index
                        body = text[position + 1 : close_index]
                        break
                index += 1
        tail_start = close_index + 1 if has_arguments else position
        class_match = ENTITY_CLASS_RE.search(text[tail_start : tail_start + 1200])
        if class_match:
            table_match = TABLE_NAME_RE.search(body)
            result.append(table_match.group(1) if table_match else class_match.group(1))
        cursor = close_index + 1
    return result


def audit_persistence(root: Path, rules: dict[str, Any]) -> dict[str, Any]:
    components: list[dict[str, Any]] = []
    versions: dict[str, int | str] = {}
    stored_identities: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    allowed_modules = set(rules.get("allowed_modules", []))
    for source in read_kotlin_sources(root):
        kinds = classify(source["code"], source["path"])
        if not kinds:
            continue
        record = strip_source_text(source)
        record["classifications"] = kinds
        components.append(record)
        for name, version in room_databases(source["code"]):
            versions[name] = version
        for table in room_entities(source["code"]):
            stored_identities.append({"kind": "table", "value": table, "path": source["path"]})
        for column in COLUMN_RE.findall(source["code"]):
            stored_identities.append({"kind": "column", "value": column, "path": source["path"]})
        for key in PREFERENCE_RE.findall(source["code"]):
            stored_identities.append({"kind": "preference-key", "value": key, "path": source["path"]})
        layer = layer_of(source.get("module"))
        if layer in {"domain", "ui", "navigation"}:
            findings.append({"rule": "persistence-in-portable-layer", "severity": "error", "path": source["path"], "module": source["module"]})
        if allowed_modules and source.get("module") not in allowed_modules and layer != "data":
            findings.append({"rule": "persistence-outside-approved-module", "severity": "warning", "path": source["path"], "module": source["module"]})

    _, directories = module_index(root)
    schema_files: list[dict[str, Any]] = []
    for path in walk_files(root):
        if path.suffix not in {".json", ".sq", ".sqm"}:
            continue
        relative_path = relative(path, root)
        if path.suffix == ".json" and "schema" not in relative_path.lower():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        schema_files.append({
            "path": relative_path,
            "module": module_for(path, directories),
            "sha256": sha256_file(path),
            "tables": sorted(set(SQL_TABLE_RE.findall(text))),
        })
        for table in SQL_TABLE_RE.findall(text):
            stored_identities.append({"kind": "table", "value": table, "path": relative_path})

    expected_versions = rules.get("expected_database_versions", {})
    for name, expected in expected_versions.items():
        if versions.get(name) != expected:
            findings.append({
                "rule": "database-version-mismatch",
                "severity": "error",
                "database": name,
                "expected": expected,
                "actual": versions.get(name),
            })
    existing_paths = {item["path"] for item in schema_files}
    for required in rules.get("required_schema_paths", []):
        if required not in existing_paths:
            findings.append({"rule": "required-schema-file-missing", "severity": "error", "path": required})
    unresolved = [finding for finding in findings if finding["severity"] == "error"]
    return artifact(
        root=root,
        skill=SKILL,
        script=SCRIPT,
        inputs={"rules": rules},
        unresolved=unresolved,
        gates={"schema_baseline": "fail" if unresolved else "pass"},
        components=sorted(components, key=lambda item: item["path"]),
        database_versions=dict(sorted(versions.items())),
        stored_identities=sorted(stored_identities, key=lambda item: (item["kind"], item["value"], item["path"])),
        schema_files=sorted(schema_files, key=lambda item: item["path"]),
        findings=findings,
    )


def plan_persistence(root: Path, audit: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    unresolved = list(audit.get("unresolved", []))
    target = rules.get("target_module")
    if not target:
        unresolved.append({"rule": "target-module-required", "severity": "error"})
    if rules.get("preserve_schema") is not True:
        unresolved.append({"rule": "schema-preservation-must-be-explicit", "severity": "error"})
    assignments = [
        {
            "path": component["path"],
            "from_module": component.get("module"),
            "target_module": target,
            "classifications": component["classifications"],
            "expected_sha256": component["sha256"],
        }
        for component in audit.get("components", [])
    ]
    return artifact(
        root=root,
        skill=SKILL,
        script=SCRIPT,
        inputs={"rules": rules},
        unresolved=unresolved,
        gates={"plan_ready": "fail" if unresolved else "review"},
        verification=["compare database versions", "compare schema hashes and stored identities", "run persistence tests", "construct databases on affected platforms"],
        assignments=assignments,
        database_versions=audit.get("database_versions", {}),
        stored_identities=audit.get("stored_identities", []),
        schema_files=audit.get("schema_files", []),
    )


def main() -> int:
    args = build_parser().parse_args()
    root = args.root.resolve()
    rules = load_json(args.rules, {})
    payload = audit_persistence(root, rules) if args.command == "audit" else plan_persistence(root, load_json(args.audit), rules)
    write_json(args.json_out, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
