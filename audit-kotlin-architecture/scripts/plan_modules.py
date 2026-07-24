#!/usr/bin/env python3
"""Turn an audit artifact into a reviewable layered module proposal."""

from __future__ import annotations

import argparse
import collections
import fnmatch
import json
import re
import sys
from pathlib import Path


SCHEMA_VERSION = 1
PRODUCTION_LAYERS = ("domain", "data", "navigation", "shared-ui", "ui")
MODULE_PATH_RE = re.compile(r"^:[A-Za-z0-9_-]+(?::[A-Za-z0-9_-]+)*$")
FEATURE_NAME_RE = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")
ASSIGNABLE_LAYERS = {*PRODUCTION_LAYERS, "test", "aggregation", "platform"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--overrides", type=Path)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--markdown-out", type=Path)
    return parser.parse_args()


def load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version in {path}: {data.get('schema_version')!r}")
    return data


def validate_overrides(overrides: dict) -> None:
    target_layers = overrides.get("target_feature_layers", [])
    if not isinstance(target_layers, list) or any(layer not in PRODUCTION_LAYERS for layer in target_layers):
        raise ValueError(f"target_feature_layers must be a list containing only {list(PRODUCTION_LAYERS)}")
    for field in ("shared_test_modules", "foundation_modules"):
        values = overrides.get(field, [])
        if not isinstance(values, list) or any(not isinstance(value, str) or not MODULE_PATH_RE.fullmatch(value) for value in values):
            raise ValueError(f"{field} must be a list of absolute Gradle module paths such as :test or :core:domain")
    features = overrides.get("features", [])
    if not isinstance(features, list):
        raise ValueError("features must be a list")
    seen: set[str] = set()
    for feature in features:
        if not isinstance(feature, dict) or not isinstance(feature.get("name"), str) or not FEATURE_NAME_RE.fullmatch(feature["name"]):
            raise ValueError(f"every feature override needs a lowercase Gradle-safe name: {feature!r}")
        if feature["name"] in seen:
            raise ValueError(f"duplicate feature override: {feature['name']}")
        seen.add(feature["name"])
        for field in ("package_prefixes", "path_prefixes", "include_globs", "exclude_globs"):
            values = feature.get(field, [])
            if not isinstance(values, list) or not all(isinstance(value, str) and value for value in values):
                raise ValueError(f"feature {feature['name']} {field} must be a list of non-empty strings")
        target_layers = feature.get("target_layers")
        if target_layers is not None and (
            not isinstance(target_layers, list)
            or any(layer not in PRODUCTION_LAYERS for layer in target_layers)
        ):
            raise ValueError(
                f"feature {feature['name']} target_layers must contain only {list(PRODUCTION_LAYERS)}"
            )
    file_overrides = overrides.get("file_overrides", {})
    if not isinstance(file_overrides, dict):
        raise ValueError("file_overrides must be an object")
    for path, value in file_overrides.items():
        if not isinstance(path, str) or not path or not isinstance(value, dict):
            raise ValueError("file_overrides must map repository-relative paths to objects")
        if value.get("feature") is not None and (
            not isinstance(value["feature"], str) or not FEATURE_NAME_RE.fullmatch(value["feature"])
        ):
            raise ValueError(f"invalid feature in file override {path}: {value.get('feature')!r}")
        if value.get("layer") is not None and value["layer"] not in ASSIGNABLE_LAYERS:
            raise ValueError(f"invalid layer in file override {path}: {value.get('layer')!r}")
    shared = overrides.get("shared_assignments", {})
    if not isinstance(shared, dict) or any(
        not isinstance(path, str) or not path or not isinstance(target, str) or not MODULE_PATH_RE.fullmatch(target)
        for path, target in shared.items()
    ):
        raise ValueError("shared_assignments must map repository-relative paths to absolute Gradle module paths")
    shared_ui_dependencies = overrides.get("shared_ui_dependencies", [])
    if not isinstance(shared_ui_dependencies, list):
        raise ValueError("shared_ui_dependencies must be a list")
    for edge in shared_ui_dependencies:
        if not isinstance(edge, dict) or set(edge) != {"consumer", "provider"}:
            raise ValueError("shared_ui_dependencies entries require only consumer and provider")
        consumer = edge.get("consumer")
        provider = edge.get("provider")
        if (
            not isinstance(consumer, str)
            or not MODULE_PATH_RE.fullmatch(consumer)
            or not consumer.endswith(":ui")
            or not isinstance(provider, str)
            or not MODULE_PATH_RE.fullmatch(provider)
            or not provider.endswith(":shared-ui")
        ):
            raise ValueError(
                "shared_ui_dependencies require an absolute :...:ui consumer and :...:shared-ui provider"
            )


def matches_prefix(value: str | None, prefixes: list[str]) -> bool:
    return bool(value and any(value == prefix or value.startswith(prefix.rstrip(".") + ".") for prefix in prefixes))


def override_assignment(source: dict, overrides: dict) -> tuple[str | None, str | None, str | None]:
    path = source["path"]
    direct = overrides.get("file_overrides", {}).get(path)
    if direct:
        return direct.get("feature"), direct.get("layer"), direct.get("reason", "file override")
    for feature in overrides.get("features", []):
        excluded = any(fnmatch.fnmatch(path, pattern) for pattern in feature.get("exclude_globs", []))
        if excluded:
            continue
        included = (
            matches_prefix(source.get("package"), feature.get("package_prefixes", []))
            or any(path == prefix or path.startswith(prefix.rstrip("/") + "/") for prefix in feature.get("path_prefixes", []))
            or any(fnmatch.fnmatch(path, pattern) for pattern in feature.get("include_globs", []))
        )
        if included:
            return feature["name"], None, "feature override"
    return None, None, None


def proposed_layer(source: dict, forced: str | None) -> str:
    if forced:
        return forced
    layer = source.get("layer", "unknown")
    if layer == "test":
        if source.get("test_kind") == "reusable-test-support":
            return "test"
        return source.get("test_target_layer") or "unknown"
    if layer == "di":
        return "aggregation"
    if layer == "platform":
        return "data" if any(token in source["path"].lower() for token in ("repository", "service", "storage", "network")) else "ui" if "ui" in source["path"].lower() else "unknown"
    return layer


def source_set(path: str) -> str | None:
    parts = path.split("/")
    if "src" in parts:
        index = parts.index("src")
        if index + 1 < len(parts):
            return parts[index + 1]
    return None


def retained_target(source: dict) -> str | None:
    module = source.get("module")
    if not module:
        return None
    parts = [part for part in module.split(":") if part]
    if not parts:
        return None
    if parts[0].lower() in {"core", "util", "utility", "test", "build-logic", "buildsrc", "plugins"}:
        return module
    return None


def proposed_artifact_layer(artifact: dict, forced: str | None) -> str:
    if forced:
        return forced
    if artifact.get("module", "").endswith(":shared-ui"):
        return "shared-ui"
    kind = artifact.get("kind")
    if kind == "resource":
        return "ui"
    if kind in {"database-schema", "database-migration", "network-schema", "serialization-schema"}:
        return "data"
    return "platform"


def feature_module(path: object, feature_root: str) -> tuple[str, str] | None:
    if not isinstance(path, str):
        return None
    parts = [part for part in path.split(":") if part]
    feature_root_parts = [
        part for part in feature_root.replace("/", ":").split(":") if part
    ]
    if (
        len(parts) < len(feature_root_parts) + 1
        or parts[:len(feature_root_parts)] != feature_root_parts
    ):
        return None
    feature = parts[len(feature_root_parts)]
    remainder = parts[len(feature_root_parts) + 1:]
    return feature, "aggregation" if not remainder else remainder[-1]


def module_role(path: object, feature_root: str) -> str | None:
    feature = feature_module(path, feature_root)
    if feature:
        return feature[1]
    if not isinstance(path, str):
        return None
    parts = [part.lower() for part in path.split(":") if part]
    if parts and parts[0] in {"test", "test-support", "fixtures"}:
        return "test-support"
    last = parts[-1] if parts else ""
    if last in {"app", "androidapp", "composeapp", "application"}:
        return "app"
    return last


def shared_ui_edge_violation(
    source_path: object,
    target_path: object,
    feature_root: str,
) -> tuple[str, str] | None:
    source = feature_module(source_path, feature_root)
    target = feature_module(target_path, feature_root)
    source_role = module_role(source_path, feature_root)
    target_role = module_role(target_path, feature_root)
    if target_role == "shared-ui":
        if source_role == "shared-ui":
            return "shared-ui-to-shared-ui", "Shared UI must not depend on shared UI."
        if source_role in {"domain", "data", "navigation"}:
            return (
                "lower-layer-to-shared-ui",
                f"{source_role} must not depend on feature shared UI.",
            )
        if source_role == "aggregation":
            if source and target and source[0] == target[0]:
                return None
            return (
                "feature-root-to-foreign-shared-ui",
                "A feature root may aggregate only its own shared UI.",
            )
        if source_role == "ui" and source:
            return None
        return (
            "invalid-shared-ui-consumer",
            "Feature shared UI may be consumed only by its owner root or feature UI.",
        )
    if source_role != "shared-ui":
        return None
    if target_role in {"data", "app", "test", "test-support"}:
        return (
            "shared-ui-to-forbidden-layer",
            f"Shared UI must not depend on {target_role}.",
        )
    if target and target_role in {"ui", "aggregation"}:
        return (
            "shared-ui-to-feature-ui"
            if target_role == "ui"
            else "shared-ui-to-feature-root",
            f"Shared UI must not depend on a feature {target_role}.",
        )
    if (
        source
        and target
        and source[0] != target[0]
        and target_role in {"domain", "navigation"}
    ):
        return (
            "shared-ui-to-foreign-feature-contract",
            "Shared UI may depend only on its owner's feature contracts.",
        )
    return None


def build_plan(audit: dict, overrides: dict) -> dict:
    feature_root = overrides.get("feature_root", "feature")
    shared = overrides.get("shared_assignments", {})
    grouped: dict[str, list[dict]] = collections.defaultdict(list)
    unresolved: list[dict] = []
    shared_assignments: list[dict] = []
    retained_assignments: list[dict] = []
    artifact_assignments: list[dict] = []
    retained_artifacts: list[dict] = []
    unresolved_artifacts: list[dict] = []
    shared_artifact_assignments: list[dict] = []

    for source in audit.get("sources", []):
        if source["path"] in shared:
            shared_assignments.append({"path": source["path"], "target": shared[source["path"]]})
            continue
        forced_feature, forced_layer, reason = override_assignment(source, overrides)
        feature = forced_feature or source.get("feature")
        layer = proposed_layer(source, forced_layer)
        assignment = {
            "path": source["path"],
            "current_module": source.get("module"),
            "current_package": source.get("package"),
            "source_set": source_set(source["path"]),
            "layer": layer,
            "confidence": "approved" if forced_layer or forced_feature else source.get("layer_confidence", "low"),
            "reason": reason or "audit heuristic",
            "test_kind": source.get("test_kind"),
        }
        retained = retained_target(source)
        ambiguous_feature = bool(feature and not forced_feature and source.get("feature_confidence") == "low")
        if not feature and retained:
            assignment["target"] = retained
            assignment["reason"] = "existing non-feature module ownership"
            retained_assignments.append(assignment)
        elif not feature or layer == "unknown" or ambiguous_feature:
            assignment["feature"] = feature
            if ambiguous_feature:
                assignment["reason"] = source.get("feature_reason", "ambiguous feature candidate")
            unresolved.append(assignment)
        else:
            grouped[feature].append(assignment)

    for artifact in audit.get("artifacts", []):
        if artifact["path"] in shared:
            shared_artifact_assignments.append({"path": artifact["path"], "target": shared[artifact["path"]], "kind": artifact.get("kind")})
            continue
        forced_feature, forced_layer, reason = override_assignment(artifact, overrides)
        feature = forced_feature or artifact.get("feature")
        layer = proposed_artifact_layer(artifact, forced_layer)
        assignment = {
            "path": artifact["path"],
            "kind": artifact.get("kind"),
            "source_set": artifact.get("source_set"),
            "current_module": artifact.get("module"),
            "feature": feature,
            "layer": layer,
            "reason": reason or artifact.get("feature_reason", "artifact heuristic"),
        }
        retained = retained_target(artifact)
        if feature:
            artifact_assignments.append(assignment)
        elif retained:
            assignment["target"] = retained
            retained_artifacts.append(assignment)
        else:
            unresolved_artifacts.append(assignment)

    coupling_counts: collections.Counter[str] = collections.Counter()
    for edge in audit.get("feature_coupling", []):
        coupling_counts[edge["from"]] += edge["import_count"]
        coupling_counts[edge["to"]] += edge["import_count"]

    existing_modules_by_feature: dict[str, list[str]] = collections.defaultdict(list)
    existing_shared_test_modules: list[str] = []
    feature_root_parts = [part for part in feature_root.replace("/", ":").split(":") if part]
    for module in audit.get("modules", []):
        module_parts = [part for part in module.get("path", "").split(":") if part]
        if module_parts and module_parts[0].lower() in {"test", "test-support", "fixtures"}:
            existing_shared_test_modules.append(module["path"])
        if len(module_parts) > len(feature_root_parts) and module_parts[:len(feature_root_parts)] == feature_root_parts:
            existing_modules_by_feature[module_parts[len(feature_root_parts)]].append(module["path"])

    feature_overrides = {
        feature["name"]: feature for feature in overrides.get("features", [])
    }
    features = []
    for name in sorted(set(grouped) | set(existing_modules_by_feature)):
        assignments = grouped.get(name, [])
        counts = collections.Counter(a["layer"] for a in assignments)
        low_confidence = sum(a["confidence"] in {"low", "medium"} for a in assignments)
        configured_layers = feature_overrides.get(name, {}).get(
            "target_layers",
            overrides.get("target_feature_layers"),
        )
        selected_layers = [layer for layer in PRODUCTION_LAYERS if counts[layer]]
        if configured_layers:
            selected_layers = [layer for layer in configured_layers if layer in PRODUCTION_LAYERS]
        modules = [f":{feature_root.replace('/', ':')}:{name}"]
        modules += [f":{feature_root.replace('/', ':')}:{name}:{layer}" for layer in selected_layers]
        if counts["test"] or overrides.get("create_feature_test_support", False):
            modules.append(f":{feature_root.replace('/', ':')}:{name}:test")
        modules = list(dict.fromkeys([*modules, *sorted(existing_modules_by_feature.get(name, []))]))
        coverage = sum(1 for layer in PRODUCTION_LAYERS if counts[layer])
        pilot_score = abs(len(assignments) - 30) + coupling_counts[name] * 2 + low_confidence * 3 - coverage * 5
        features.append({
            "name": name,
            "target_modules": modules,
            "existing_modules": sorted(existing_modules_by_feature.get(name, [])),
            "file_count": len(assignments),
            "layer_counts": dict(counts),
            "cross_feature_import_count": coupling_counts[name],
            "low_or_medium_confidence_count": low_confidence,
            "pilot_score": pilot_score,
            "assignments": assignments,
        })

    eligible = [f for f in features if f["file_count"] >= 5 and len([x for x in PRODUCTION_LAYERS if f["layer_counts"].get(x)]) >= 2]
    pilot = min(eligible, key=lambda item: item["pilot_score"])["name"] if eligible else (features[0]["name"] if features else None)
    module_order = ["domain", "test", "data", "navigation", "shared-ui", "ui", "aggregation"]
    observed_shared_ui_dependencies = []
    shared_ui_violations = []
    for module in audit.get("modules", []):
        consumer = module.get("path")
        for provider in module.get("project_dependencies", []):
            violation = shared_ui_edge_violation(consumer, provider, feature_root)
            if violation:
                shared_ui_violations.append({
                    "source": consumer,
                    "target": provider,
                    "rule": violation[0],
                    "evidence": violation[1],
                })
            elif (
                feature_module(consumer, feature_root)
                and module_role(consumer, feature_root) == "ui"
                and module_role(provider, feature_root) == "shared-ui"
            ):
                observed_shared_ui_dependencies.append({
                    "consumer": consumer,
                    "provider": provider,
                    "source": "observed Gradle dependency",
                })
    explicit_shared_ui_dependencies = [
        {**edge, "source": "approved override"}
        for edge in overrides.get("shared_ui_dependencies", [])
    ]
    shared_ui_dependencies = []
    seen_shared_ui_dependencies = set()
    for edge in [*observed_shared_ui_dependencies, *explicit_shared_ui_dependencies]:
        key = (edge["consumer"], edge["provider"])
        if key in seen_shared_ui_dependencies:
            continue
        seen_shared_ui_dependencies.add(key)
        shared_ui_dependencies.append(edge)
    planned_modules = {
        module
        for feature in features
        for module in feature["target_modules"]
    }
    for edge in shared_ui_dependencies:
        missing = [
            endpoint
            for endpoint in (edge["consumer"], edge["provider"])
            if endpoint not in planned_modules
        ]
        if missing:
            shared_ui_violations.append({
                "source": edge["consumer"],
                "target": edge["provider"],
                "rule": "unplanned-shared-ui-endpoint",
                "evidence": (
                    "Shared-UI dependency references module(s) absent from the plan: "
                    + ", ".join(missing)
                ),
            })
    deduplicated_shared_ui_violations = []
    seen_shared_ui_violations = set()
    for item in shared_ui_violations:
        key = (item["source"], item["target"], item["rule"], item["evidence"])
        if key in seen_shared_ui_violations:
            continue
        seen_shared_ui_violations.add(key)
        deduplicated_shared_ui_violations.append(item)
    shared_ui_violations = deduplicated_shared_ui_violations
    feature_assignment_count = sum(len(feature["assignments"]) for feature in features)
    accounted_count = feature_assignment_count + len(shared_assignments) + len(retained_assignments) + len(unresolved)
    source_count = len(audit.get("sources", []))
    if accounted_count != source_count:
        raise ValueError(f"source accounting mismatch: accounted for {accounted_count} of {source_count}")
    artifact_count = len(audit.get("artifacts", []))
    accounted_artifacts = len(artifact_assignments) + len(retained_artifacts) + len(unresolved_artifacts) + len(shared_artifact_assignments)
    if accounted_artifacts != artifact_count:
        raise ValueError(f"artifact accounting mismatch: accounted for {accounted_artifacts} of {artifact_count}")
    return {
        "schema_version": SCHEMA_VERSION,
        "audit_source": str(audit.get("root", "unknown")),
        "root_package": overrides.get("root_package") or audit.get("project", {}).get("root_package"),
        "feature_root": feature_root,
        "recommended_pilot": pilot,
        "migration_layer_order": module_order,
        "shared_ui_dependencies": shared_ui_dependencies,
        "shared_ui_violations": shared_ui_violations,
        "plan_acceptance": {
            "shared_ui_graph": "fail" if shared_ui_violations else "pass",
        },
        "features": features,
        "shared_assignments": shared_assignments,
        "retained_assignments": retained_assignments,
        "unresolved": unresolved,
        "artifact_assignments": artifact_assignments,
        "retained_artifacts": retained_artifacts,
        "unresolved_artifacts": unresolved_artifacts,
        "shared_artifact_assignments": shared_artifact_assignments,
        "source_accounting": {
            "audit_sources": source_count,
            "feature_assignments": feature_assignment_count,
            "shared_assignments": len(shared_assignments),
            "retained_assignments": len(retained_assignments),
            "unresolved": len(unresolved),
            "accounted": accounted_count,
        },
        "artifact_accounting": {
            "audit_artifacts": artifact_count,
            "feature_assignments": len(artifact_assignments),
            "shared_assignments": len(shared_artifact_assignments),
            "retained_assignments": len(retained_artifacts),
            "unresolved": len(unresolved_artifacts),
            "accounted": accounted_artifacts,
        },
        "testing": {
            "shared_foundation_modules": overrides.get("shared_test_modules", sorted(existing_shared_test_modules)),
            "feature_test_support_policy": "Create one only for reusable fakes/fixtures with multiple consumers and an acyclic dependency direction.",
            "owning_tests": "Keep actual test cases in each production module's matching test source set.",
        },
        "foundation_modules": overrides.get("foundation_modules", []),
        "phases": [
            {"name": "baseline", "work": "Record current build/test behavior and pre-existing failures."},
            {"name": "build-conventions", "work": "Extract and prove platform/capability convention plugins."},
            {"name": "foundations", "work": "Create only core/utility modules required by the pilot."},
            {"name": "pilot", "work": f"Migrate {pilot or 'an approved feature'} domain-first and validate the full vertical slice."},
            {"name": "repeat", "work": "Migrate remaining features one vertical slice at a time."},
            {"name": "cleanup", "work": "Remove legacy paths/adapters and enforce architecture checks in CI."},
        ],
    }


def markdown(plan: dict) -> str:
    lines = [
        "# Proposed modularization plan", "",
        f"- Root package: `{plan.get('root_package') or 'unknown'}`",
        f"- Feature root: `{plan['feature_root']}`",
        f"- Recommended pilot: `{plan.get('recommended_pilot') or 'manual decision required'}`",
        f"- Unresolved files: {len(plan['unresolved'])}", "",
        f"- Source accounting: `{plan['source_accounting']['accounted']}/{plan['source_accounting']['audit_sources']}`", "",
        f"- Artifact accounting: `{plan['artifact_accounting']['accounted']}/{plan['artifact_accounting']['audit_artifacts']}`", "",
        "## Proposed features", "",
        "| Feature | Files | Layers | Cross-feature imports | Review count |",
        "|---|---:|---|---:|---:|",
    ]
    for feature in plan["features"]:
        layers = ", ".join(f"{k}:{v}" for k, v in sorted(feature["layer_counts"].items()))
        lines.append(f"| `{feature['name']}` | {feature['file_count']} | {layers} | {feature['cross_feature_import_count']} | {feature['low_or_medium_confidence_count']} |")
    lines += ["", "## Migration sequence", ""]
    for index, phase in enumerate(plan["phases"], 1):
        lines.append(f"{index}. **{phase['name']}** — {phase['work']}")
    lines += ["", "## Target modules", ""]
    for feature in plan["features"]:
        lines.append(f"### {feature['name']}")
        lines.append("")
        for module in feature["target_modules"]:
            lines.append(f"- `{module}`")
        lines.append("")
    lines += ["## Shared-UI dependency order", ""]
    if plan["shared_ui_dependencies"]:
        for edge in plan["shared_ui_dependencies"]:
            lines.append(
                f"- `{edge['consumer']}` depends on `{edge['provider']}` "
                f"({edge['source']})"
            )
    else:
        lines.append("No shared-UI consumer/provider edges approved or observed.")
    lines.append("")
    lines += ["## Shared-UI dependency violations", ""]
    if plan["shared_ui_violations"]:
        for item in plan["shared_ui_violations"]:
            lines.append(
                f"- **REJECT** `{item['source']}` → `{item['target']}` "
                f"(`{item['rule']}`): {item['evidence']}"
            )
    else:
        lines.append("None. Shared-UI dependency graph gate passed.")
    lines.append("")
    lines += ["## Shared assignments", ""]
    if plan["shared_assignments"]:
        for item in plan["shared_assignments"]:
            lines.append(f"- `{item['path']}` → `{item['target']}`")
    else:
        lines.append("None approved.")
    lines += ["", "## Retained non-feature modules", ""]
    if plan["retained_assignments"]:
        for item in plan["retained_assignments"][:200]:
            lines.append(f"- `{item['path']}` stays in `{item['target']}`")
        if len(plan["retained_assignments"]) > 200:
            lines.append(f"- … {len(plan['retained_assignments']) - 200} more in JSON")
    else:
        lines.append("None detected.")
    lines += ["", "## Testing architecture", ""]
    lines.append(f"- Shared foundations: {', '.join(f'`{value}`' for value in plan['testing']['shared_foundation_modules'])}")
    lines.append(f"- Feature support: {plan['testing']['feature_test_support_policy']}")
    lines.append(f"- Owning tests: {plan['testing']['owning_tests']}")
    lines += ["", "## Manifests, resources, schemas, and native artifacts", ""]
    for item in plan["artifact_assignments"]:
        lines.append(f"- `{item['path']}` → feature `{item['feature']}` layer `{item['layer']}`")
    for item in plan["retained_artifacts"]:
        lines.append(f"- `{item['path']}` stays in `{item['target']}`")
    for item in plan["shared_artifact_assignments"]:
        lines.append(f"- `{item['path']}` → `{item['target']}`")
    if plan["unresolved_artifacts"]:
        lines += ["", "Unresolved artifacts:", ""]
        for item in plan["unresolved_artifacts"]:
            lines.append(f"- `{item['path']}` — `{item['kind']}` in `{item.get('current_module') or 'no module'}`")
    lines += ["", "## Manual review queue", ""]
    for item in plan["unresolved"][:200]:
        lines.append(f"- `{item['path']}` — feature `{item.get('feature') or 'unknown'}`, layer `{item['layer']}`")
    if len(plan["unresolved"]) > 200:
        lines.append(f"- … {len(plan['unresolved']) - 200} more in JSON")
    lines += ["", "> Approve feature ownership and all low-confidence assignments before generating move manifests.", ""]
    return "\n".join(lines)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    args = parse_args()
    try:
        audit = load_json(args.audit)
        overrides = load_json(args.overrides) if args.overrides else {"schema_version": 1}
        validate_overrides(overrides)
        plan = build_plan(audit, overrides)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    report = markdown(plan)
    if args.json_out:
        write(args.json_out, json.dumps(plan, indent=2, sort_keys=True) + "\n")
    if args.markdown_out:
        write(args.markdown_out, report)
    if not args.json_out and not args.markdown_out:
        print(report)
    else:
        if args.json_out:
            print(f"Wrote JSON plan: {args.json_out}")
        if args.markdown_out:
            print(f"Wrote Markdown plan: {args.markdown_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
