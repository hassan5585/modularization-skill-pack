#!/usr/bin/env python3
"""Cross-skill `.modularization` artifact envelope validation (stdlib only)."""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = 1

# Artifact kinds and the fields they must carry beyond the common envelope.
ARTIFACT_KINDS: dict[str, set[str]] = {
    "audit": {"modules", "sources"},
    "module-plan": set(),  # plan.json may use features / testing
    "foundation-plan": {"candidates", "modules", "migration_batches", "plan_gates"},
    "cycle-report": {"build_graph", "source_graph", "strongly_connected_components"},
    "api-surface-report": {"modules", "declarations", "findings"},
    "platform-boundary-plan": {"targets", "findings", "extractions"},
    "work-state": {"chunks"},
    "build-metrics": {"scenarios", "environment"},
    "build-metrics-comparison": {"baseline", "current", "comparisons"},
    "move-manifest": {"moves"},
    "feature-spec": {"feature", "layers"},
    "navigation3-audit": {"project", "routes", "hosts", "findings"},
    "navigation3-spec": {"project", "route_model", "navigator", "migration_phases"},
    "navigation3-check": {"findings", "gates", "summary"},
    "generic": set(),
}

COMMON_REQUIRED = {
    "schema_version",
}


def envelope_fields(
    *,
    skill: str,
    script: str,
    script_version: str = "1",
    repository_root: str = ".",
    repository_revision: str | None = None,
    inputs: dict[str, Any] | None = None,
    unresolved: list[Any] | None = None,
    gates: dict[str, Any] | None = None,
    verification: list[Any] | None = None,
) -> dict[str, Any]:
    """Return the standard metadata envelope every skill should include."""
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "repository": {
            "root": repository_root,
            "revision": repository_revision,
        },
        "generator": {
            "skill": skill,
            "script": script,
            "version": script_version,
        },
        "inputs": inputs or {},
        "observed": {},
        "recommendations": [],
        "unresolved": unresolved or [],
        "gates": gates or {},
        "verification": verification or [],
    }
    return payload


def validate_artifact(payload: Any, kind: str = "generic") -> list[str]:
    """Return human-readable validation errors for a modularization artifact."""
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["artifact must be a JSON object"]
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(
            f"schema_version must be {SCHEMA_VERSION}, got {payload.get('schema_version')!r}"
        )
    for key in COMMON_REQUIRED:
        if key not in payload:
            errors.append(f"missing required field: {key}")
    expected = ARTIFACT_KINDS.get(kind)
    if expected is None:
        errors.append(f"unknown artifact kind: {kind}")
    else:
        for field in sorted(expected):
            if field not in payload:
                errors.append(f"{kind} artifact missing field: {field}")
    generator = payload.get("generator")
    if generator is not None:
        if not isinstance(generator, dict):
            errors.append("generator must be an object when present")
        else:
            for key in ("skill", "script"):
                if not generator.get(key):
                    errors.append(f"generator.{key} is required when generator is present")
    return errors


def is_valid_artifact(payload: Any, kind: str = "generic") -> bool:
    return not validate_artifact(payload, kind)
