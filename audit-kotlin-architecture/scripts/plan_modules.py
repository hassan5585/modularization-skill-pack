#!/usr/bin/env python3
"""Turn an audit artifact into a reviewable layered module proposal."""

from __future__ import annotations

import argparse
import collections
import fnmatch
import json
import sys
from pathlib import Path


SCHEMA_VERSION = 1
PRODUCTION_LAYERS = ("domain", "data", "navigation", "ui")


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


def build_plan(audit: dict, overrides: dict) -> dict:
    feature_root = overrides.get("feature_root", "feature")
    shared = overrides.get("shared_assignments", {})
    grouped: dict[str, list[dict]] = collections.defaultdict(list)
    unresolved: list[dict] = []
    shared_assignments: list[dict] = []

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
        if not feature or layer == "unknown":
            assignment["feature"] = feature
            unresolved.append(assignment)
        else:
            grouped[feature].append(assignment)

    coupling_counts: collections.Counter[str] = collections.Counter()
    for edge in audit.get("feature_coupling", []):
        coupling_counts[edge["from"]] += edge["import_count"]
        coupling_counts[edge["to"]] += edge["import_count"]

    features = []
    for name, assignments in sorted(grouped.items()):
        counts = collections.Counter(a["layer"] for a in assignments)
        low_confidence = sum(a["confidence"] in {"low", "medium"} for a in assignments)
        modules = [f":{feature_root.replace('/', ':')}:{name}"]
        modules += [f":{feature_root.replace('/', ':')}:{name}:{layer}" for layer in PRODUCTION_LAYERS if counts[layer]]
        if counts["test"]:
            modules.append(f":{feature_root.replace('/', ':')}:{name}:test")
        coverage = sum(1 for layer in PRODUCTION_LAYERS if counts[layer])
        pilot_score = abs(len(assignments) - 30) + coupling_counts[name] * 2 + low_confidence * 3 - coverage * 5
        features.append({
            "name": name,
            "target_modules": modules,
            "file_count": len(assignments),
            "layer_counts": dict(counts),
            "cross_feature_import_count": coupling_counts[name],
            "low_or_medium_confidence_count": low_confidence,
            "pilot_score": pilot_score,
            "assignments": assignments,
        })

    eligible = [f for f in features if f["file_count"] >= 5 and len([x for x in PRODUCTION_LAYERS if f["layer_counts"].get(x)]) >= 2]
    pilot = min(eligible, key=lambda item: item["pilot_score"])["name"] if eligible else (features[0]["name"] if features else None)
    module_order = ["domain", "test", "data", "navigation", "ui", "aggregation"]
    return {
        "schema_version": SCHEMA_VERSION,
        "audit_source": str(audit.get("root", "unknown")),
        "root_package": overrides.get("root_package") or audit.get("project", {}).get("root_package"),
        "feature_root": feature_root,
        "recommended_pilot": pilot,
        "migration_layer_order": module_order,
        "features": features,
        "shared_assignments": shared_assignments,
        "unresolved": unresolved,
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
    lines += ["## Shared assignments", ""]
    if plan["shared_assignments"]:
        for item in plan["shared_assignments"]:
            lines.append(f"- `{item['path']}` → `{item['target']}`")
    else:
        lines.append("None approved.")
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
