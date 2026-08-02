#!/usr/bin/env python3
"""Audit a built Kotlin/Native Apple framework without rebuilding it."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
OBJC_DECLARATION_RE = re.compile(r"(?m)^\s*@(interface|protocol)\b")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", required=True, type=Path, help="A .framework directory or generated .h header")
    parser.add_argument("--rules", type=Path, help="Repository-specific JSON thresholds and symbol patterns")
    parser.add_argument("--check", action="store_true", help="Exit nonzero when a configured rule fails")
    parser.add_argument("--json-out", type=Path, help="Optional machine-readable audit output")
    return parser.parse_args()


def positive_int(value: object, key: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{key} must be a positive integer")
    return value


def load_rules(path: Path | None, check: bool) -> dict:
    if path is None:
        if check:
            raise ValueError("--check requires --rules; do not enforce unreviewed universal thresholds")
        return {
            "schema_version": 1,
            "max_header_lines": None,
            "max_objc_declarations": None,
            "required_symbol_patterns": [],
            "forbidden_symbol_patterns": [],
        }
    try:
        rules = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read rules: {exc}") from exc
    if rules.get("schema_version") != 1:
        raise ValueError(f"unsupported schema_version: {rules.get('schema_version')!r}")
    for key in ("max_header_lines", "max_objc_declarations"):
        if rules.get(key) is not None:
            positive_int(rules[key], key)
    required = rules.get("required_symbol_patterns", [])
    forbidden = rules.get("forbidden_symbol_patterns", [])
    if not isinstance(required, list) or any(not isinstance(item, str) or not item for item in required):
        raise ValueError("required_symbol_patterns must be a list of non-empty regular expressions")
    if not isinstance(forbidden, list) or any(
        not isinstance(item, dict)
        or not isinstance(item.get("label"), str)
        or not item.get("label")
        or not isinstance(item.get("pattern"), str)
        or not item.get("pattern")
        for item in forbidden
    ):
        raise ValueError("forbidden_symbol_patterns must contain label/pattern objects")
    try:
        for pattern in required:
            re.compile(pattern)
        for item in forbidden:
            re.compile(item["pattern"])
    except re.error as exc:
        raise ValueError(f"invalid symbol regular expression: {exc}") from exc
    return rules


def resolve_input(path: Path) -> tuple[Path | None, Path, Path | None]:
    value = path.expanduser().resolve()
    if not value.exists():
        raise ValueError(f"framework/header path does not exist: {value}")
    framework: Path | None = None
    if value.is_dir() and value.name.endswith(".framework"):
        framework = value
        expected = value / "Headers" / f"{value.stem}.h"
        if expected.is_file():
            header = expected
        else:
            headers = sorted((value / "Headers").glob("*.h"))
            if len(headers) != 1:
                raise ValueError(f"could not select one framework header under {value / 'Headers'}")
            header = headers[0]
    elif value.is_file() and value.suffix.lower() == ".h":
        header = value
        candidate = value.parent.parent
        if candidate.is_dir() and candidate.name.endswith(".framework"):
            framework = candidate
    else:
        raise ValueError(f"expected a .framework directory or .h header: {value}")
    binary = None
    if framework is not None:
        candidate = framework / framework.stem
        if candidate.is_file():
            binary = candidate
    return framework, header, binary


def line_count(text: str) -> int:
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def audit(path: Path, rules: dict) -> dict:
    framework, header, binary = resolve_input(path)
    header_text = header.read_text(encoding="utf-8", errors="replace")
    identifiers = sorted(set(IDENTIFIER_RE.findall(header_text)))
    required = [
        {"pattern": pattern, "present": re.search(pattern, header_text) is not None}
        for pattern in rules.get("required_symbol_patterns", [])
    ]
    forbidden = []
    for item in rules.get("forbidden_symbol_patterns", []):
        expression = re.compile(item["pattern"])
        matches = [identifier for identifier in identifiers if expression.search(identifier)]
        forbidden.append({"label": item["label"], "pattern": item["pattern"], "matches": matches})
    result = {
        "schema_version": 1,
        "framework": str(framework) if framework else None,
        "header": str(header),
        "binary": str(binary) if binary else None,
        "binary_bytes": binary.stat().st_size if binary else None,
        "header_lines": line_count(header_text),
        "objc_declarations": len(OBJC_DECLARATION_RE.findall(header_text)),
        "required_symbols": required,
        "forbidden_symbols": forbidden,
        "violations": [],
    }
    maximum = rules.get("max_header_lines")
    if maximum is not None and result["header_lines"] > maximum:
        result["violations"].append(f"header has {result['header_lines']} lines; maximum is {maximum}")
    maximum = rules.get("max_objc_declarations")
    if maximum is not None and result["objc_declarations"] > maximum:
        result["violations"].append(f"header has {result['objc_declarations']} Objective-C declarations; maximum is {maximum}")
    for item in required:
        if not item["present"]:
            result["violations"].append(f"required symbol pattern is absent: {item['pattern']}")
    for item in forbidden:
        if item["matches"]:
            examples = ", ".join(item["matches"][:8])
            result["violations"].append(f"{item['label']} matched forbidden exported symbols: {examples}")
    return result


def main() -> int:
    options = parse_args()
    try:
        rules = load_rules(options.rules, options.check)
        result = audit(options.path, rules)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"Framework: {result['framework'] or 'header only'}")
    print(f"Header: {result['header']}")
    print(f"Header lines: {result['header_lines']}")
    print(f"Objective-C declarations: {result['objc_declarations']}")
    if result["binary_bytes"] is not None:
        print(f"Framework binary bytes: {result['binary_bytes']}")
    for item in result["required_symbols"]:
        print(f"Required /{item['pattern']}/: {'present' if item['present'] else 'MISSING'}")
    for item in result["forbidden_symbols"]:
        print(f"Forbidden {item['label']}: {len(item['matches'])} match(es)")
    if result["violations"]:
        print("Violations:")
        for violation in result["violations"]:
            print(f"  - {violation}")
    if options.json_out:
        options.json_out.parent.mkdir(parents=True, exist_ok=True)
        options.json_out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Wrote JSON audit: {options.json_out}")
    if options.check:
        if result["violations"]:
            print("CHECK FAILED")
            return 1
        print("CHECK PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
