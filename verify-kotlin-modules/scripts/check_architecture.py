#!/usr/bin/env python3
"""Check Gradle module edges and Kotlin/Java imports against layered rules."""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
from pathlib import Path


SCHEMA_VERSION = 1
DEFAULT_EXCLUDES = {".git", ".gradle", ".idea", ".kotlin", "build", "out", "node_modules", "vendor"}
PROJECT_RES = [
    re.compile(r"project\(\s*[\"'](:[^\"']+)[\"']\s*\)"),
    re.compile(r"project\(\s*path\s*=\s*[\"'](:[^\"']+)[\"']"),
]
PACKAGE_RE = re.compile(r"(?m)^\s*package\s+([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)")
IMPORT_RE = re.compile(r"(?m)^\s*import\s+([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*(?:\.\*)?)")
DEFAULT_FORBIDDEN = {
    "domain": ["data", "navigation", "ui", "app", "test-support"],
    "data": ["navigation", "ui", "app", "test-support"],
    "navigation": ["data", "ui", "app", "test-support"],
    "ui": ["data", "app", "test-support"],
    "aggregation": ["test-support"],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--rules", type=Path)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--fail-on-warning", action="store_true")
    return parser.parse_args()


def load_rules(path: Path | None) -> dict:
    if not path:
        return {
            "schema_version": 1,
            "feature_root": "feature",
            "required_feature_layers": [],
            "test_support_names": ["test", "test-support", "fixtures"],
            "module_roles": {},
            "forbidden_target_roles": DEFAULT_FORBIDDEN,
            "cross_feature": {"severity": "warning", "allowed_target_roles": ["domain", "navigation"]},
            "ignored_paths": [],
            "ignored_import_prefixes": [],
            "exceptions": [],
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read rules: {exc}") from exc
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version: {data.get('schema_version')!r}")
    return data


def is_excluded(path: Path, root: Path, ignored: list[str]) -> bool:
    rel = path.relative_to(root).as_posix()
    return any(part in DEFAULT_EXCLUDES for part in path.relative_to(root).parts) or any(
        rel == item or rel.startswith(item.rstrip("/") + "/") or fnmatch.fnmatch(rel, item)
        for item in ignored
    )


def find_build_files(root: Path, ignored: list[str]) -> list[Path]:
    found = []
    for current, dirs, files in os.walk(root):
        base = Path(current)
        if base != root and any((base / name).is_file() for name in ("settings.gradle", "settings.gradle.kts")):
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if not is_excluded(base / d, root, ignored)]
        for name in files:
            if name in {"build.gradle", "build.gradle.kts"}:
                found.append(base / name)
    return sorted(found)


def module_path(directory: Path, root: Path) -> str:
    rel = directory.relative_to(root)
    return ":" + ":".join(rel.parts) if rel.parts else ":"


def role_for(directory: Path, root: Path, rules: dict) -> str:
    rel = directory.relative_to(root).as_posix() or "."
    for pattern, role in rules.get("module_roles", {}).items():
        if fnmatch.fnmatch(rel, pattern):
            return role
    last = directory.name.lower()
    if last in {"domain", "data", "navigation", "ui"}:
        return last
    if last in set(rules.get("test_support_names", [])):
        return "test-support"
    parts = directory.relative_to(root).parts
    feature_root = Path(rules.get("feature_root", "feature")).parts
    if len(parts) == len(feature_root) + 1 and tuple(parts[:len(feature_root)]) == feature_root:
        return "aggregation"
    if last in {"app", "androidapp", "composeapp", "application"}:
        return "app"
    return "unknown"


def feature_for(directory: Path, root: Path, rules: dict) -> str | None:
    parts = directory.relative_to(root).parts
    feature_parts = Path(rules.get("feature_root", "feature")).parts
    if len(parts) > len(feature_parts) and tuple(parts[:len(feature_parts)]) == feature_parts:
        return parts[len(feature_parts)]
    return None


def owner_for(path: Path, root: Path, by_dir: dict[Path, dict]) -> dict | None:
    current = path.parent
    while current == root or root in current.parents:
        if current in by_dir:
            return by_dir[current]
        if current == root:
            break
        current = current.parent
    return None


def project_dependencies(text: str) -> tuple[list[str], list[str]]:
    """Separate project dependencies found in production and test Gradle blocks.

    This is a lightweight brace-aware parser. It deliberately reports only static
    project("...") expressions and treats any surrounding block/configuration
    containing `test` as test-only.
    """
    matches = sorted(
        ((match.start(), match.group(1)) for regex in PROJECT_RES for match in regex.finditer(text)),
        key=lambda item: item[0],
    )
    production: set[str] = set()
    tests: set[str] = set()
    for position, dependency in matches:
        stack: list[str] = []
        last_boundary = 0
        for index, char in enumerate(text[:position]):
            if char == "{" and (index == 0 or text[index - 1] != '$'):
                label = text[last_boundary:index].strip()
                stack.append(label[-160:])
                last_boundary = index + 1
            elif char == "}":
                if stack:
                    stack.pop()
                last_boundary = index + 1
            elif char == "\n" and not text[last_boundary:index].strip():
                last_boundary = index + 1
        line_prefix = text[text.rfind("\n", 0, position) + 1:position]
        context = " ".join(stack + [line_prefix]).lower()
        if "test" in context:
            tests.add(dependency)
        else:
            production.add(dependency)
    return sorted(production), sorted(tests)


def is_test_source(path: Path, root: Path) -> bool:
    parts = [part.lower() for part in path.relative_to(root).parts]
    if "src" in parts:
        index = parts.index("src")
        if index + 1 < len(parts) and "test" in parts[index + 1]:
            return True
    return any(part in {"test", "tests"} for part in parts) or path.stem.lower().endswith("test")


def exception_for(rule_id: str, source: str, target: str, rules: dict) -> dict | None:
    for item in rules.get("exceptions", []):
        if item.get("rule") == rule_id and item.get("source") == source and item.get("target") == target:
            return item
    return None


def add_finding(findings: list[dict], rules: dict, rule_id: str, severity: str, source: str, target: str, evidence: str, file: str | None = None) -> None:
    exception = exception_for(rule_id, source, target, rules)
    findings.append({
        "rule": rule_id,
        "severity": "info" if exception else severity,
        "source": source,
        "target": target,
        "file": file,
        "evidence": evidence,
        "suppressed": bool(exception),
        "exception": exception,
    })


def detect_cycles(graph: dict[str, list[str]]) -> list[list[str]]:
    state: dict[str, int] = {}
    stack: list[str] = []
    cycles: set[tuple[str, ...]] = set()

    def visit(node: str) -> None:
        state[node] = 1
        stack.append(node)
        for target in graph.get(node, []):
            if target not in graph:
                continue
            if state.get(target, 0) == 0:
                visit(target)
            elif state.get(target) == 1:
                index = stack.index(target)
                cycle = stack[index:] + [target]
                body = cycle[:-1]
                rotations = [tuple(body[i:] + body[:i]) for i in range(len(body))]
                cycles.add(min(rotations))
        stack.pop()
        state[node] = 2

    for node in graph:
        if state.get(node, 0) == 0:
            visit(node)
    return [list(cycle) + [cycle[0]] for cycle in sorted(cycles)]


def analyze(root: Path, rules: dict) -> dict:
    ignored = rules.get("ignored_paths", [])
    modules = []
    by_dir: dict[Path, dict] = {}
    for build_file in find_build_files(root, ignored):
        text = build_file.read_text(encoding="utf-8", errors="replace")
        production_dependencies, test_dependencies = project_dependencies(text)
        module = {
            "path": module_path(build_file.parent, root),
            "directory": build_file.parent.relative_to(root).as_posix() or ".",
            "build_file": build_file.relative_to(root).as_posix(),
            "role": role_for(build_file.parent, root, rules),
            "feature": feature_for(build_file.parent, root, rules),
            "dependencies": production_dependencies,
            "test_dependencies": test_dependencies,
        }
        modules.append(module)
        by_dir[build_file.parent] = module
    by_path = {module["path"]: module for module in modules}
    findings: list[dict] = []

    if rules.get("check_settings_registration", False):
        settings = next((root / name for name in ("settings.gradle.kts", "settings.gradle") if (root / name).is_file()), None)
        if not settings:
            add_finding(findings, rules, "settings-registration", "error", ":", "settings.gradle(.kts)", "Settings registration checking is enabled but no root settings file exists.")
        else:
            settings_text = settings.read_text(encoding="utf-8", errors="replace")
            registered = set(re.findall(r"[\"'](:[A-Za-z0-9_:-]+)[\"']", settings_text))
            for module in modules:
                if module["path"] != ":" and module["path"] not in registered:
                    add_finding(findings, rules, "settings-registration", "error", module["path"], settings.relative_to(root).as_posix(), "Module path was not found as a static string in root settings. Disable this rule for dynamic module discovery.")

    feature_root = root / rules.get("feature_root", "feature")
    required_layers = rules.get("required_feature_layers", [])
    if feature_root.is_dir() and required_layers:
        for feature_dir in sorted(p for p in feature_root.iterdir() if p.is_dir()):
            if is_excluded(feature_dir, root, ignored):
                continue
            for layer in required_layers:
                build_kts = feature_dir / layer / "build.gradle.kts"
                build_groovy = feature_dir / layer / "build.gradle"
                if not build_kts.is_file() and not build_groovy.is_file():
                    add_finding(findings, rules, "missing-feature-layer", "error", f":{rules.get('feature_root', 'feature').replace('/', ':')}:{feature_dir.name}", layer, f"Required layer `{layer}` has no build file.")

    forbidden = rules.get("forbidden_target_roles", DEFAULT_FORBIDDEN)
    graph = {module["path"]: module["dependencies"] for module in modules}
    for source in modules:
        for target_path in source["dependencies"]:
            target = by_path.get(target_path)
            if not target:
                continue
            if source["role"] != "test-support" and target["role"] == "test-support":
                add_finding(findings, rules, "production-test-dependency", "error", source["path"], target_path, "Production module depends on test-support.")
            elif target["role"] in forbidden.get(source["role"], []):
                add_finding(findings, rules, "forbidden-layer-dependency", "error", source["path"], target_path, f"Role `{source['role']}` must not depend on `{target['role']}`.")
            if source.get("feature") and target.get("feature") and source["feature"] != target["feature"]:
                allowed = rules.get("cross_feature", {}).get("allowed_target_roles", ["domain", "navigation"])
                if target["role"] not in allowed:
                    add_finding(findings, rules, "cross-feature-dependency", rules.get("cross_feature", {}).get("severity", "warning"), source["path"], target_path, f"Cross-feature dependency targets role `{target['role']}`.")

    for cycle in detect_cycles(graph):
        add_finding(findings, rules, "dependency-cycle", "error", cycle[0], cycle[-2], " -> ".join(cycle))

    package_owners: dict[str, set[str]] = {}
    source_records = []
    for current, dirs, files in os.walk(root):
        base = Path(current)
        if base != root and any((base / name).is_file() for name in ("settings.gradle", "settings.gradle.kts")):
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if not is_excluded(base / d, root, ignored)]
        for name in files:
            if not name.endswith((".kt", ".java")):
                continue
            path = base / name
            owner = owner_for(path, root, by_dir)
            if not owner:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            package_match = PACKAGE_RE.search(text)
            package = package_match.group(1) if package_match else None
            if package:
                package_owners.setdefault(package, set()).add(owner["path"])
            source_records.append((path, owner, text))

    for package, owners in package_owners.items():
        if len(owners) > 1:
            sorted_owners = sorted(owners)
            add_finding(findings, rules, "split-package", "warning", sorted_owners[0], sorted_owners[-1], f"Package `{package}` is declared in {', '.join(sorted_owners)}.")

    package_index = sorted(
        ((package, next(iter(owners))) for package, owners in package_owners.items() if len(owners) == 1),
        key=lambda item: len(item[0]), reverse=True,
    )
    ignored_imports = tuple(rules.get("ignored_import_prefixes", []))
    for path, source, text in source_records:
        if is_test_source(path, root):
            continue
        for imported in IMPORT_RE.findall(text):
            imported = imported.rstrip(".*")
            if ignored_imports and imported.startswith(ignored_imports):
                continue
            target_path = next((owner for package, owner in package_index if imported == package or imported.startswith(package + ".")), None)
            if not target_path or target_path == source["path"]:
                continue
            target = by_path.get(target_path)
            if not target:
                continue
            file_rel = path.relative_to(root).as_posix()
            if target["role"] in forbidden.get(source["role"], []):
                add_finding(findings, rules, "forbidden-layer-import", "error", source["path"], target_path, f"Imports `{imported}` from forbidden role `{target['role']}`.", file_rel)
            if source.get("feature") and target.get("feature") and source["feature"] != target["feature"]:
                allowed = rules.get("cross_feature", {}).get("allowed_target_roles", ["domain", "navigation"])
                if target["role"] not in allowed:
                    add_finding(findings, rules, "cross-feature-import", rules.get("cross_feature", {}).get("severity", "warning"), source["path"], target_path, f"Imports `{imported}` from feature `{target['feature']}` role `{target['role']}`.", file_rel)

    severity_order = {"error": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda f: (severity_order.get(f["severity"], 9), f["rule"], f["source"], f["target"], f.get("file") or ""))
    return {"schema_version": 1, "root": str(root), "modules": modules, "findings": findings}


def main() -> int:
    options = parse_args()
    root = options.root.resolve()
    if not root.is_dir():
        print(f"error: root is not a directory: {root}", file=sys.stderr)
        return 2
    try:
        rules = load_rules(options.rules)
        result = analyze(root, rules)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    counts = {severity: sum(f["severity"] == severity for f in result["findings"]) for severity in ("error", "warning", "info")}
    print(f"Architecture findings: {counts['error']} error(s), {counts['warning']} warning(s), {counts['info']} info/suppressed")
    for finding in result["findings"]:
        location = f" {finding['file']}" if finding.get("file") else ""
        suppressed = " [suppressed]" if finding["suppressed"] else ""
        print(f"{finding['severity'].upper()} {finding['rule']}{suppressed}:{location} {finding['source']} -> {finding['target']}: {finding['evidence']}")
    if options.json_out:
        options.json_out.parent.mkdir(parents=True, exist_ok=True)
        options.json_out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Wrote JSON findings: {options.json_out}")
    if counts["error"] or options.fail_on_warning and counts["warning"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
