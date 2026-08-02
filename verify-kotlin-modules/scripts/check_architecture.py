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
DEFAULT_EXCLUDES = {".git", ".gradle", ".idea", ".kotlin", "build", "out", "node_modules", "vendor", "Pods", "DerivedData", ".konan", ".swiftpm-locks", ".build", "swiftPMCheckout", "Carthage", "xcuserdata", ".modularization"}
PROJECT_RES = [
    re.compile(r"project\(\s*[\"'](:[^\"']+)[\"']\s*\)"),
    re.compile(r"project\(\s*path\s*[:=]\s*[\"'](:[^\"']+)[\"']"),
    re.compile(r"(?<![A-Za-z0-9_.])projects\.([A-Za-z0-9_.]+)"),
]
PACKAGE_RE = re.compile(r"(?m)^\s*package\s+([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)")
IMPORT_RE = re.compile(r"(?m)^\s*import\s+([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*(?:\.\*)?)")
PLUGIN_RES = [
    re.compile(r"alias\(\s*libs\.plugins\.([A-Za-z0-9_.-]+)\s*\)"),
    re.compile(r"id\(\s*[\"']([^\"']+)[\"']\s*\)"),
    re.compile(r"\bid\s+[\"']([^\"']+)[\"']"),
    re.compile(r"apply\s+plugin\s*:\s*[\"']([^\"']+)[\"']"),
    re.compile(r"kotlin\(\s*[\"']([^\"']+)[\"']\s*\)"),
]
INCLUDE_BUILD_RE = re.compile(r"includeBuild\s*(?:\(\s*)?[\"']([^\"']+)[\"']")
STATIC_MODULE_RE = re.compile(r"[\"'](:[A-Za-z0-9_:-]+)[\"']")
PLUGIN_REGISTRATION_START_RE = re.compile(r"\b(?:register|create)\s*\(\s*[\"'][^\"']+[\"']\s*\)\s*\{")
REGISTERED_PLUGIN_ID_RE = re.compile(r"\bid\s*=\s*[\"']([^\"']+)[\"']")
IMPLEMENTATION_CLASS_RE = re.compile(r"\bimplementationClass\s*=\s*[\"']([^\"']+)[\"']")
NATIVE_EXPORT_FLAG_RE = re.compile(r"\bexport\s*=\s*true\b")
TRANSITIVE_EXPORT_RE = re.compile(r"\btransitiveExport\s*=\s*true\b")
DISABLED_PHASE_RE = re.compile(r"-Xdisable-phases(?:=|\s+)[^\"'\s,)]+")
DEFAULT_FORBIDDEN = {
    "domain": ["data", "navigation", "shared-ui", "ui", "app", "test-support"],
    "data": ["navigation", "shared-ui", "ui", "app", "test-support"],
    "navigation": ["data", "shared-ui", "ui", "app", "test-support"],
    "shared-ui": ["data", "shared-ui", "app", "test-support"],
    "ui": ["data", "app", "test-support"],
    "aggregation": ["test-support"],
}
NON_SUPPRESSIBLE_RULES = {
    "shared-ui-to-shared-ui",
    "lower-layer-to-shared-ui",
    "feature-root-to-foreign-shared-ui",
    "invalid-shared-ui-consumer",
    "shared-ui-to-forbidden-layer",
    "shared-ui-to-foreign-feature-contract",
    "shared-ui-to-feature-ui",
    "shared-ui-to-feature-root",
    "disabled-native-compiler-phase",
    "transitive-native-export",
}
NATIVE_NON_SUPPRESSIBLE_RULES = {
    "disabled-native-compiler-phase",
    "transitive-native-export",
}


def strip_gradle_comments(text: str) -> str:
    result: list[str] = []
    index = 0
    quote: str | None = None
    triple_quoted = False
    block_depth = 0
    while index < len(text):
        if block_depth and text.startswith("/*", index):
            block_depth += 1
            result.append("  ")
            index += 2
        elif block_depth and text.startswith("*/", index):
            block_depth -= 1
            result.append("  ")
            index += 2
        elif block_depth:
            result.append("\n" if text[index] == "\n" else " ")
            index += 1
        elif quote and triple_quoted:
            delimiter = quote * 3
            if text.startswith(delimiter, index):
                result.append(delimiter)
                index += 3
                quote = None
                triple_quoted = False
            else:
                result.append(text[index])
                index += 1
        elif quote:
            character = text[index]
            result.append(character)
            index += 1
            if character == "\\" and index < len(text):
                result.append(text[index])
                index += 1
            elif character == quote:
                quote = None
        elif text.startswith("//", index):
            while index < len(text) and text[index] != "\n":
                index += 1
        elif text.startswith("/*", index):
            block_depth = 1
            result.append("  ")
            index += 2
        elif text[index] in {'"', "'"}:
            quote = text[index]
            triple_quoted = text.startswith(quote * 3, index)
            result.append(quote * 3 if triple_quoted else quote)
            index += 3 if triple_quoted else 1
        else:
            result.append(text[index])
            index += 1
    return "".join(result)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--rules", type=Path)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--fail-on-warning", action="store_true")
    parser.add_argument("--max-findings", type=int, default=200, help="Maximum findings printed; JSON output always contains all findings")
    return parser.parse_args()


def load_rules(path: Path | None) -> dict:
    if not path:
        return {
            "schema_version": 1,
            "feature_root": "feature",
            "required_feature_layers": [],
            "required_feature_layers_by_feature": {},
            "test_support_names": ["test", "test-support", "fixtures"],
            "module_roles": {},
            "forbidden_target_roles": DEFAULT_FORBIDDEN,
            "cross_feature": {
                "severity": "warning",
                "allowed_target_roles": ["domain", "navigation"],
                "allowed_role_edges": {"ui": ["shared-ui"]},
            },
            "ignored_paths": [],
            "ignored_import_prefixes": [],
            "exceptions": [],
            "required_test_modules": [],
            "dependency_visibility": {
                "api_project_dependency_severity": None,
                "allowed_api_project_dependencies": [],
            },
            "native_framework": {
                "exported_dependency_severity": None,
                "export_flag_severity": None,
                "transitive_export_severity": None,
                "disabled_phase_severity": None,
            },
            "conventions": {
                "included_builds": [],
                "validate_included_build_plugins": False,
                "required_registered_plugin_ids": [],
                "required_plugins_by_role": {},
                "forbidden_plugins_by_role": {},
            },
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read rules: {exc}") from exc
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version: {data.get('schema_version')!r}")
    if data.get("cross_feature", {}).get("severity", "warning") not in {"error", "warning", "info"}:
        raise ValueError("cross_feature.severity must be error, warning, or info")
    cross_feature = data.setdefault("cross_feature", {})
    allowed_role_edges = cross_feature.setdefault("allowed_role_edges", {})
    if not isinstance(allowed_role_edges, dict) or any(
        not isinstance(source, str)
        or not isinstance(targets, list)
        or any(not isinstance(target, str) for target in targets)
        for source, targets in allowed_role_edges.items()
    ):
        raise ValueError("cross_feature.allowed_role_edges must map source roles to target-role lists")
    allowed_role_edges.setdefault("ui", ["shared-ui"])
    feature_layer_overrides = data.get("required_feature_layers_by_feature", {})
    if not isinstance(feature_layer_overrides, dict) or any(not isinstance(value, list) for value in feature_layer_overrides.values()):
        raise ValueError("required_feature_layers_by_feature must map feature names (or `*`) to layer lists")
    conventions = data.get("conventions", {})
    if not isinstance(conventions.get("required_registered_plugin_ids", []), list):
        raise ValueError("conventions.required_registered_plugin_ids must be a list")
    dependency_visibility = data.get("dependency_visibility", {})
    if not isinstance(dependency_visibility, dict):
        raise ValueError("dependency_visibility must be an object")
    api_severity = dependency_visibility.get("api_project_dependency_severity")
    if api_severity not in {None, "error", "warning", "info"}:
        raise ValueError("dependency_visibility.api_project_dependency_severity must be error, warning, info, or null")
    allowed_api = dependency_visibility.get("allowed_api_project_dependencies", [])
    if not isinstance(allowed_api, list):
        raise ValueError("dependency_visibility.allowed_api_project_dependencies must be a list")
    for item in allowed_api:
        if not isinstance(item, dict) or any(not item.get(key) for key in ("source", "target", "reason")):
            raise ValueError("every allowed API project dependency must contain source, target, and reason")
        if not isinstance(item["source"], str) or not isinstance(item["target"], str) or not isinstance(item["reason"], str):
            raise ValueError("allowed API project dependency source, target, and reason must be strings")
        if not item["source"].startswith(":") or not item["target"].startswith(":"):
            raise ValueError(f"allowed API project dependency source/target must be absolute Gradle module paths: {item}")
        if any(token in item["source"] or token in item["target"] for token in ("*", "?", "[", "]")):
            raise ValueError(f"allowed API project dependencies must be exact, not wildcard patterns: {item}")
    native_framework = data.get("native_framework", {})
    if not isinstance(native_framework, dict):
        raise ValueError("native_framework must be an object")
    for key in (
        "exported_dependency_severity",
        "export_flag_severity",
        "transitive_export_severity",
        "disabled_phase_severity",
    ):
        if native_framework.get(key) not in {None, "error", "warning", "info"}:
            raise ValueError(f"native_framework.{key} must be error, warning, info, or null")
    for item in data.get("exceptions", []):
        if not isinstance(item, dict):
            raise ValueError("every exception must be an object")
        missing = [key for key in ("rule", "source", "target", "reason", "owner", "remove_when") if not item.get(key)]
        if missing:
            raise ValueError(f"exception is missing required fields {missing}: {item}")
        if any(token in item["source"] or token in item["target"] for token in ("*", "?", "[", "]")):
            raise ValueError(f"exception source/target must be exact, not wildcard patterns: {item}")
        if item["rule"] in NON_SUPPRESSIBLE_RULES:
            label = "native hard rule" if item["rule"] in NATIVE_NON_SUPPRESSIBLE_RULES else "shared-ui hard rule"
            raise ValueError(f"{label} cannot be suppressed: {item['rule']}")
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
    if last in {"domain", "data", "navigation", "shared-ui", "ui"}:
        return last
    if last in set(rules.get("test_support_names", [])):
        return "test-support"
    parts = directory.relative_to(root).parts
    if parts and parts[0].lower() in set(rules.get("test_support_names", [])):
        return "test-support"
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


def gradle_accessor_segment(segment: str) -> str:
    parts = re.split(r"[-_]+", segment)
    return parts[0] + "".join(
        part[:1].upper() + part[1:] for part in parts[1:]
    )


def gradle_project_accessor(module: str) -> str:
    return ".".join(
        gradle_accessor_segment(segment)
        for segment in module.split(":")
        if segment
    )


def normalize_project_dependency(
    value: str,
    known_modules: set[str] | None = None,
) -> str:
    if value.startswith(":"):
        return value
    if known_modules:
        accessor_matches = [
            module
            for module in known_modules
            if gradle_project_accessor(module) == value
        ]
        if len(accessor_matches) == 1:
            return accessor_matches[0]
    segments = value.split(".")
    literal = ":" + ":".join(segments)
    kebab = ":" + ":".join(
        re.sub(r"(?<!^)(?=[A-Z])", "-", segment).lower()
        for segment in segments
    )
    if known_modules:
        for candidate in (literal, kebab):
            if candidate in known_modules:
                return candidate
    return kebab if "sharedUi" in segments else literal


def dependency_configuration(line_prefix: str) -> str:
    match = re.search(r"([A-Za-z_][A-Za-z0-9_]*)\s*(?:\(\s*)?$", line_prefix)
    return match.group(1) if match else "unknown"


def project_dependency_records(
    text: str,
    known_modules: set[str] | None = None,
) -> list[dict]:
    """Return static project references with configuration and test context.

    This is a lightweight brace-aware parser. It deliberately reports only static
    project references and treats any surrounding block/configuration containing
    `test` as test-only.
    """
    matches = sorted(
        ((match.start(), match.group(1)) for regex in PROJECT_RES for match in regex.finditer(text)),
        key=lambda item: item[0],
    )
    records: list[dict] = []
    for position, dependency in matches:
        dependency = normalize_project_dependency(dependency, known_modules)
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
        records.append({
            "target": dependency,
            "configuration": dependency_configuration(line_prefix),
            "test_only": "test" in context,
        })
    unique = {
        (item["target"], item["configuration"], item["test_only"]): item
        for item in records
    }
    return [unique[key] for key in sorted(unique)]


def project_dependencies(
    text: str,
    known_modules: set[str] | None = None,
) -> tuple[list[str], list[str]]:
    records = project_dependency_records(text, known_modules)
    production = {item["target"] for item in records if not item["test_only"]}
    tests = {item["target"] for item in records if item["test_only"]}
    return sorted(production), sorted(tests)


def is_api_configuration(configuration: str) -> bool:
    lowered = configuration.lower()
    return lowered == "api" or lowered.endswith("api")


def is_export_configuration(configuration: str) -> bool:
    return configuration.lower() == "export"


def find_native_configuration_files(root: Path, ignored: list[str]) -> list[Path]:
    found: list[Path] = []
    build_logic_names = {"build-logic", "buildsrc", "plugins", "convention"}
    for current, dirs, files in os.walk(root):
        base = Path(current)
        relative_parts = {part.lower() for part in base.relative_to(root).parts}
        if (
            base != root
            and any((base / name).is_file() for name in ("settings.gradle", "settings.gradle.kts"))
            and not relative_parts.intersection(build_logic_names)
        ):
            dirs[:] = []
            continue
        dirs[:] = [directory for directory in dirs if not is_excluded(base / directory, root, ignored)]
        in_build_logic = bool(relative_parts & build_logic_names)
        for name in files:
            path = base / name
            if name == "gradle.properties" or name.endswith((".gradle", ".gradle.kts")):
                found.append(path)
            elif in_build_logic and path.suffix in {".kt", ".kts", ".groovy"}:
                found.append(path)
    return sorted(set(found))


def applied_plugins(text: str) -> list[str]:
    plugins: set[str] = set()
    for pattern in PLUGIN_RES:
        for match in pattern.finditer(text):
            line_end = text.find("\n", match.end())
            trailer = text[match.end():line_end if line_end >= 0 else len(text)].lower()
            if re.search(r"\bapply\s+false\b", trailer):
                continue
            plugins.add(match.group(1))
    return sorted(plugins)


def convention_plugin_registrations(text: str) -> list[dict]:
    """Extract statically declared Gradle plugin ids and implementation classes.

    Gradle Kotlin DSL plugin registrations are ordinary nested blocks. This
    brace-aware scan handles multiline bodies without attempting to execute the
    build script. Dynamic registrations remain a deliberate manual-review case.
    """
    registrations: list[dict] = []
    for start in PLUGIN_REGISTRATION_START_RE.finditer(text):
        body_start = start.end()
        depth = 1
        index = body_start
        while index < len(text) and depth:
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
            index += 1
        body = text[body_start:index - 1] if depth == 0 else text[body_start:]
        plugin_id = REGISTERED_PLUGIN_ID_RE.search(body)
        implementation = IMPLEMENTATION_CLASS_RE.search(body)
        if plugin_id or implementation:
            registrations.append({
                "id": plugin_id.group(1) if plugin_id else None,
                "implementation_class": implementation.group(1) if implementation else None,
            })
    return registrations


def implementation_source_exists(build_root: Path, implementation: str) -> bool:
    suffixes = (
        Path(*implementation.split(".")).with_suffix(".kt").as_posix(),
        Path(*implementation.split(".")).with_suffix(".java").as_posix(),
    )
    for current, dirs, files in os.walk(build_root):
        base = Path(current)
        dirs[:] = [directory for directory in dirs if directory not in DEFAULT_EXCLUDES]
        for name in files:
            candidate = (base / name).relative_to(build_root).as_posix()
            if candidate.endswith(suffixes):
                return True
    return False


def validate_included_build(
    root: Path,
    relative: str,
    conventions: dict,
    rules: dict,
    findings: list[dict],
) -> None:
    build_root = (root / relative).resolve()
    if build_root != root and root not in build_root.parents:
        add_finding(findings, rules, "invalid-convention-included-build", "error", ":", relative, "Configured included-build path escapes the repository root.")
        return
    if not build_root.is_dir():
        add_finding(findings, rules, "missing-convention-build-directory", "error", ":", relative, "Configured convention included-build directory does not exist.")
        return
    settings = next((build_root / name for name in ("settings.gradle.kts", "settings.gradle") if (build_root / name).is_file()), None)
    if not settings:
        add_finding(findings, rules, "missing-convention-build-settings", "error", ":", relative, "Convention included build has no settings.gradle(.kts).")
        return

    settings_text = strip_gradle_comments(
        settings.read_text(encoding="utf-8", errors="replace")
    )
    registered_modules = set(STATIC_MODULE_RE.findall(settings_text))
    build_files = find_build_files(build_root, [])
    registrations: list[dict] = []
    for build_file in build_files:
        module = module_path(build_file.parent, build_root)
        if module != ":" and module not in registered_modules:
            add_finding(
                findings,
                rules,
                "convention-settings-registration",
                "error",
                f"{relative}:{module.lstrip(':')}",
                settings.relative_to(root).as_posix(),
                "Convention included-build subproject has a build file but is not statically registered in its settings file.",
            )
        text = strip_gradle_comments(
            build_file.read_text(encoding="utf-8", errors="replace")
        )
        for registration in convention_plugin_registrations(text):
            registration["build_file"] = build_file.relative_to(root).as_posix()
            registrations.append(registration)

    by_id: dict[str, list[dict]] = {}
    for registration in registrations:
        plugin_id = registration.get("id")
        if not plugin_id:
            add_finding(findings, rules, "missing-convention-plugin-id", "error", registration["build_file"], "gradlePlugin.plugins", "Convention plugin registration has an implementationClass but no static id.")
            continue
        by_id.setdefault(plugin_id, []).append(registration)
        implementation = registration.get("implementation_class")
        if not implementation:
            add_finding(findings, rules, "missing-convention-implementation-class", "error", registration["build_file"], plugin_id, "Convention plugin registration has no static implementationClass.")
            continue
        if not implementation_source_exists(build_root, implementation):
            add_finding(
                findings,
                rules,
                "missing-convention-implementation",
                "error",
                registration["build_file"],
                implementation,
                "Registered convention plugin implementation source was not found under the included build.",
            )
    for plugin_id, matches in sorted(by_id.items()):
        if len(matches) > 1:
            add_finding(findings, rules, "duplicate-convention-plugin-registration", "error", matches[0]["build_file"], plugin_id, f"Convention plugin id is registered {len(matches)} times.")
    for plugin_id in sorted(set(conventions.get("required_registered_plugin_ids", [])) - set(by_id)):
        add_finding(findings, rules, "missing-convention-plugin-registration", "error", relative, plugin_id, "Required convention plugin id is not statically registered in the included build.")


def is_test_source(path: Path, root: Path) -> bool:
    parts = [part.lower() for part in path.relative_to(root).parts]
    if "src" in parts:
        index = parts.index("src")
        if index + 1 < len(parts) and "test" in parts[index + 1]:
            return True
    return any(part in {"test", "tests"} for part in parts) or path.stem.lower().endswith("test")


def exception_for(rule_id: str, source: str, target: str, rules: dict) -> dict | None:
    if rule_id in NON_SUPPRESSIBLE_RULES:
        return None
    for item in rules.get("exceptions", []):
        if item.get("rule") == rule_id and item.get("source") == source and item.get("target") == target:
            return item
    return None


def cross_feature_allowed(source_role: str, target_role: str, rules: dict) -> bool:
    policy = rules.get("cross_feature", {})
    if target_role in policy.get("allowed_target_roles", ["domain", "navigation"]):
        return True
    return target_role in policy.get("allowed_role_edges", {}).get(source_role, [])


def shared_ui_violation(source: dict, target: dict) -> tuple[str, str] | None:
    source_role = source.get("role")
    target_role = target.get("role")
    if target_role == "shared-ui":
        if source_role == "shared-ui":
            return (
                "shared-ui-to-shared-ui",
                "A feature shared-ui module must not depend on another shared-ui module.",
            )
        if source_role in {"domain", "data", "navigation"}:
            return (
                "lower-layer-to-shared-ui",
                f"A {source_role} module must not depend on feature shared-ui.",
            )
        if source_role == "aggregation":
            if source.get("feature") == target.get("feature"):
                return None
            return (
                "feature-root-to-foreign-shared-ui",
                "A feature root may aggregate only its own shared-ui module.",
            )
        if source_role == "ui" and source.get("feature"):
            return None
        return (
            "invalid-shared-ui-consumer",
            "Feature shared-ui may be consumed only by its owner root or a feature UI module.",
        )
    if source_role == "shared-ui" and target_role in {"data", "app", "test-support"}:
        return (
            "shared-ui-to-forbidden-layer",
            f"A feature shared-ui module must not depend on {target_role}.",
        )
    if source_role != "shared-ui" or not target.get("feature"):
        return None
    if (
        target.get("feature") != source.get("feature")
        and target_role in {"domain", "navigation"}
    ):
        return (
            "shared-ui-to-foreign-feature-contract",
            "A feature shared-ui module may depend only on its owner's feature contracts.",
        )
    if target_role == "ui":
        return (
            "shared-ui-to-feature-ui",
            "A feature shared-ui module must sit below regular feature UI modules.",
        )
    if target_role == "aggregation":
        return (
            "shared-ui-to-feature-root",
            "A feature shared-ui module must not depend on a feature aggregation root.",
        )
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
    build_files = find_build_files(root, ignored)
    known_modules = {
        module_path(build_file.parent, root)
        for build_file in build_files
    }
    for build_file in build_files:
        text = strip_gradle_comments(
            build_file.read_text(encoding="utf-8", errors="replace")
        )
        dependency_records = project_dependency_records(
            text,
            known_modules,
        )
        production_dependencies = sorted({
            item["target"] for item in dependency_records if not item["test_only"]
        })
        test_dependencies = sorted({
            item["target"] for item in dependency_records if item["test_only"]
        })
        module = {
            "path": module_path(build_file.parent, root),
            "directory": build_file.parent.relative_to(root).as_posix() or ".",
            "build_file": build_file.relative_to(root).as_posix(),
            "role": role_for(build_file.parent, root, rules),
            "feature": feature_for(build_file.parent, root, rules),
            "dependencies": production_dependencies,
            "test_dependencies": test_dependencies,
            "project_dependency_configurations": dependency_records,
            "plugins": applied_plugins(text),
        }
        modules.append(module)
        by_dir[build_file.parent] = module
    by_path = {module["path"]: module for module in modules}
    findings: list[dict] = []

    dependency_visibility = rules.get("dependency_visibility", {})
    api_severity = dependency_visibility.get("api_project_dependency_severity")
    approved_api_edges = {
        (item["source"], item["target"])
        for item in dependency_visibility.get("allowed_api_project_dependencies", [])
    }
    if api_severity:
        for module in modules:
            for dependency in module["project_dependency_configurations"]:
                edge = (module["path"], dependency["target"])
                if dependency["test_only"] or not is_api_configuration(dependency["configuration"]):
                    continue
                if edge not in approved_api_edges:
                    add_finding(
                        findings,
                        rules,
                        "unapproved-api-project-dependency",
                        api_severity,
                        module["path"],
                        dependency["target"],
                        f"Project dependency uses `{dependency['configuration']}` without an exact reviewed public-contract allowance; default to implementation.",
                        module["build_file"],
                    )

    native_framework = rules.get("native_framework", {})
    exported_dependency_severity = native_framework.get("exported_dependency_severity")
    if exported_dependency_severity:
        for module in modules:
            for dependency in module["project_dependency_configurations"]:
                if dependency["test_only"] or not is_export_configuration(dependency["configuration"]):
                    continue
                add_finding(
                    findings,
                    rules,
                    "native-exported-project-dependency",
                    exported_dependency_severity,
                    module["path"],
                    dependency["target"],
                    "Kotlin/Native framework exports a project dependency; keep implementation modules behind an app-owned Swift bridge unless this exact library API is intentional.",
                    module["build_file"],
                )
    native_patterns = (
        ("native-export-flag", native_framework.get("export_flag_severity"), NATIVE_EXPORT_FLAG_RE, "export = true"),
        ("transitive-native-export", native_framework.get("transitive_export_severity"), TRANSITIVE_EXPORT_RE, "transitiveExport = true"),
        ("disabled-native-compiler-phase", native_framework.get("disabled_phase_severity"), DISABLED_PHASE_RE, "-Xdisable-phases"),
    )
    if any(severity for _, severity, _, _ in native_patterns):
        for path in find_native_configuration_files(root, ignored):
            text = strip_gradle_comments(path.read_text(encoding="utf-8", errors="replace"))
            relative = path.relative_to(root).as_posix()
            source_module = owner_for(path, root, by_dir)
            source = source_module["path"] if source_module else relative
            for rule_id, severity, pattern, target in native_patterns:
                if severity and pattern.search(text):
                    evidence = {
                        "native-export-flag": "Build configuration enables a broad native export flag; prefer an explicit narrow Swift bridge and implementation dependencies.",
                        "transitive-native-export": "Transitive Kotlin/Native export broadens the entire Swift-facing dependency surface.",
                        "disabled-native-compiler-phase": "Build configuration disables Kotlin/Native compiler phases; do not make linker diagnostic workarounds permanent.",
                    }[rule_id]
                    add_finding(findings, rules, rule_id, severity, source, target, evidence, relative)

    conventions = rules.get("conventions", {})
    root_settings = next((root / name for name in ("settings.gradle.kts", "settings.gradle") if (root / name).is_file()), None)
    root_settings_text = (
        strip_gradle_comments(root_settings.read_text(encoding="utf-8", errors="replace"))
        if root_settings
        else ""
    )
    configured_included_builds = set(conventions.get("included_builds", []))
    observed_included_builds = set(INCLUDE_BUILD_RE.findall(root_settings_text))
    for required_build in sorted(configured_included_builds - observed_included_builds):
        add_finding(findings, rules, "missing-convention-included-build", "error", ":", required_build, "Required convention-plugin included build is not registered in root pluginManagement.")
    if conventions.get("validate_included_build_plugins", False):
        for required_build in sorted(configured_included_builds):
            validate_included_build(root, required_build, conventions, rules, findings)
    required_plugins = conventions.get("required_plugins_by_role", {})
    forbidden_plugins = conventions.get("forbidden_plugins_by_role", {})
    for module in modules:
        requirement = required_plugins.get(module["role"], {})
        any_of = requirement.get("any_of", []) if isinstance(requirement, dict) else requirement
        all_of = requirement.get("all_of", []) if isinstance(requirement, dict) else []
        if any_of and not any(value in module["plugins"] for value in any_of):
            add_finding(findings, rules, "missing-convention-plugin", "error", module["path"], "|".join(any_of), f"Role `{module['role']}` must apply one approved convention plugin; found {module['plugins']}.")
        for plugin in all_of:
            if plugin not in module["plugins"]:
                add_finding(findings, rules, "missing-convention-plugin", "error", module["path"], plugin, f"Role `{module['role']}` must apply convention plugin `{plugin}`.")
        for plugin in forbidden_plugins.get(module["role"], []):
            if plugin in module["plugins"]:
                add_finding(findings, rules, "forbidden-raw-plugin", "error", module["path"], plugin, f"Role `{module['role']}` must receive `{plugin}` through approved conventions, not apply it directly.")
    for required_path in rules.get("required_test_modules", []):
        module = by_path.get(required_path)
        if not module:
            add_finding(findings, rules, "missing-test-support-module", "error", ":", required_path, "Configured shared test-support module does not exist.")
        elif module["role"] != "test-support":
            add_finding(findings, rules, "invalid-test-support-role", "error", required_path, module["role"], "Configured shared test module is not classified as test-support.")

    if rules.get("check_settings_registration", False):
        settings = next((root / name for name in ("settings.gradle.kts", "settings.gradle") if (root / name).is_file()), None)
        if not settings:
            add_finding(findings, rules, "settings-registration", "error", ":", "settings.gradle(.kts)", "Settings registration checking is enabled but no root settings file exists.")
        else:
            settings_text = strip_gradle_comments(
                settings.read_text(encoding="utf-8", errors="replace")
            )
            registered = set(re.findall(r"[\"'](:[A-Za-z0-9_:-]+)[\"']", settings_text))
            for module in modules:
                if module["path"] != ":" and module["path"] not in registered:
                    add_finding(findings, rules, "settings-registration", "error", module["path"], settings.relative_to(root).as_posix(), "Module path was not found as a static string in root settings. Disable this rule for dynamic module discovery.")

    feature_root = root / rules.get("feature_root", "feature")
    required_layers = rules.get("required_feature_layers", [])
    required_layers_by_feature = rules.get("required_feature_layers_by_feature", {})
    if feature_root.is_dir() and (required_layers or required_layers_by_feature):
        for feature_dir in sorted(p for p in feature_root.iterdir() if p.is_dir()):
            if is_excluded(feature_dir, root, ignored):
                continue
            feature_layers = required_layers_by_feature.get(
                feature_dir.name,
                required_layers_by_feature.get("*", required_layers),
            )
            for layer in feature_layers:
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
            shared_ui_error = shared_ui_violation(source, target)
            if shared_ui_error:
                add_finding(
                    findings,
                    rules,
                    shared_ui_error[0],
                    "error",
                    source["path"],
                    target_path,
                    shared_ui_error[1],
                )
            elif source["role"] != "test-support" and target["role"] == "test-support":
                add_finding(findings, rules, "production-test-dependency", "error", source["path"], target_path, "Production module depends on test-support.")
            elif target["role"] in forbidden.get(source["role"], []):
                add_finding(findings, rules, "forbidden-layer-dependency", "error", source["path"], target_path, f"Role `{source['role']}` must not depend on `{target['role']}`.")
            if source.get("feature") and target.get("feature") and source["feature"] != target["feature"]:
                if not shared_ui_error and not cross_feature_allowed(source["role"], target["role"], rules):
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
    direct_import_severity = rules.get("direct_project_imports", {}).get("severity")
    if direct_import_severity not in {None, "error", "warning", "info"}:
        raise ValueError("direct_project_imports.severity must be error, warning, info, or omitted")
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
            shared_ui_error = shared_ui_violation(source, target)
            if shared_ui_error:
                add_finding(
                    findings,
                    rules,
                    shared_ui_error[0],
                    "error",
                    source["path"],
                    target_path,
                    f"{shared_ui_error[1]} Import: `{imported}`.",
                    file_rel,
                )
            elif target["role"] in forbidden.get(source["role"], []):
                add_finding(findings, rules, "forbidden-layer-import", "error", source["path"], target_path, f"Imports `{imported}` from forbidden role `{target['role']}`.", file_rel)
            if direct_import_severity and target_path not in source["dependencies"]:
                add_finding(findings, rules, "undeclared-project-import", direct_import_severity, source["path"], target_path, f"Imports `{imported}` without a statically detected direct production project dependency.", file_rel)
            if source.get("feature") and target.get("feature") and source["feature"] != target["feature"]:
                if not shared_ui_error and not cross_feature_allowed(source["role"], target["role"], rules):
                    add_finding(findings, rules, "cross-feature-import", rules.get("cross_feature", {}).get("severity", "warning"), source["path"], target_path, f"Imports `{imported}` from feature `{target['feature']}` role `{target['role']}`.", file_rel)

    severity_order = {"error": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda f: (severity_order.get(f["severity"], 9), f["rule"], f["source"], f["target"], f.get("file") or ""))
    return {"schema_version": 1, "root": ".", "project_name": root.name, "modules": modules, "findings": findings}


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
    if options.max_findings < 0:
        print("error: --max-findings must be zero or greater", file=sys.stderr)
        return 2
    for finding in result["findings"][:options.max_findings]:
        location = f" {finding['file']}" if finding.get("file") else ""
        suppressed = " [suppressed]" if finding["suppressed"] else ""
        print(f"{finding['severity'].upper()} {finding['rule']}{suppressed}:{location} {finding['source']} -> {finding['target']}: {finding['evidence']}")
    omitted = len(result["findings"]) - options.max_findings
    if omitted > 0:
        print(f"... {omitted} additional finding(s) omitted from stdout; use --json-out for the complete report.")
    if options.json_out:
        options.json_out.parent.mkdir(parents=True, exist_ok=True)
        options.json_out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Wrote JSON findings: {options.json_out}")
    if counts["error"] or options.fail_on_warning and counts["warning"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
