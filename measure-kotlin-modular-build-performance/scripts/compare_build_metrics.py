#!/usr/bin/env python3
"""Compare baseline and current modular build-metric captures."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


SCHEMA_VERSION = 1
SCRIPT_VERSION = "1"
SKILL = "measure-kotlin-modular-build-performance"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--thresholds", type=Path, help="Optional thresholds JSON")
    parser.add_argument("--json-out", type=Path)
    return parser.parse_args()


def load(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version in {path}")
    return data


def env_warnings(baseline: dict, current: dict) -> list[str]:
    warnings = []
    b_env = baseline.get("environment") or {}
    c_env = current.get("environment") or {}
    for key in ("platform", "java_home"):
        if b_env.get(key) != c_env.get(key):
            warnings.append(f"environment mismatch for {key}: {b_env.get(key)!r} vs {c_env.get(key)!r}")
    return warnings


def compare(baseline: dict, current: dict, thresholds: dict) -> dict:
    b_scenarios = {item["id"]: item for item in baseline.get("scenarios") or []}
    c_scenarios = {item["id"]: item for item in current.get("scenarios") or []}
    ids = sorted(set(b_scenarios) | set(c_scenarios))
    max_regression = float(thresholds.get("max_median_regression_ratio", 1.25))
    comparisons = []
    failures = []
    for scenario_id in ids:
        left = b_scenarios.get(scenario_id)
        right = c_scenarios.get(scenario_id)
        if left is None or right is None:
            comparisons.append(
                {
                    "id": scenario_id,
                    "status": "missing",
                    "baseline_median": None if left is None else left.get("median_elapsed_seconds"),
                    "current_median": None if right is None else right.get("median_elapsed_seconds"),
                }
            )
            failures.append(f"missing scenario: {scenario_id}")
            continue
        if left.get("status") != "ok" or right.get("status") != "ok":
            comparisons.append(
                {
                    "id": scenario_id,
                    "status": "failed-input",
                    "baseline_status": left.get("status"),
                    "current_status": right.get("status"),
                }
            )
            failures.append(f"failed scenario input: {scenario_id}")
            continue
        b_med = left.get("median_elapsed_seconds")
        c_med = right.get("median_elapsed_seconds")
        ratio = None
        if b_med and c_med and b_med > 0:
            ratio = c_med / b_med
        status = "ok"
        if ratio is not None and ratio > max_regression:
            status = "regression"
            failures.append(
                f"{scenario_id} median regression ratio {ratio:.3f} exceeds {max_regression}"
            )
        comparisons.append(
            {
                "id": scenario_id,
                "status": status,
                "baseline_median": b_med,
                "current_median": c_med,
                "ratio": ratio,
                "baseline_task_states": left.get("median_task_states"),
                "current_task_states": right.get("median_task_states"),
                "interpretation": interpret(scenario_id, ratio, left, right),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "generator": {"skill": SKILL, "script": "compare_build_metrics.py", "version": SCRIPT_VERSION},
        "repository": current.get("repository") or {"root": ".", "revision": None},
        "baseline": {"label": baseline.get("label"), "path": "baseline"},
        "current": {"label": current.get("label"), "path": "current"},
        "environment_warnings": env_warnings(baseline, current),
        "comparisons": comparisons,
        "thresholds": {"max_median_regression_ratio": max_regression},
        "gates": {
            "thresholds": "fail" if any(c.get("status") == "regression" for c in comparisons) else "pass",
            "complete_scenarios": "fail" if any(c.get("status") in {"missing", "failed-input"} for c in comparisons) else "pass",
        },
        "failures": failures,
        "recommendations": [
            "Do not claim statistical significance from a single run.",
            "Investigate module granularity, dependency visibility, build logic, code generation, and platform coupling when regressions appear.",
        ],
    }


def interpret(scenario_id: str, ratio: float | None, left: dict, right: dict) -> str:
    if ratio is None:
        return "Insufficient medians to interpret."
    if ratio <= 1.05:
        return "No meaningful slowdown versus baseline median."
    if ratio <= 1.25:
        return "Mild slowdown; confirm with additional runs before changing module shape."
    return (
        f"Regression on `{scenario_id}`. Check whether invalidation widened "
        "(executed tasks), configuration-cache reuse dropped, or platform coupling increased."
    )


def main() -> int:
    options = parse_args()
    try:
        baseline = load(options.baseline)
        current = load(options.current)
        thresholds = load(options.thresholds) if options.thresholds else {"schema_version": SCHEMA_VERSION}
        result = compare(baseline, current, thresholds)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if options.json_out:
        options.json_out.parent.mkdir(parents=True, exist_ok=True)
        options.json_out.write_text(text, encoding="utf-8")
        print(f"Wrote comparison to {options.json_out}")
    else:
        sys.stdout.write(text)
    if result["gates"]["thresholds"] == "fail" or result["gates"]["complete_scenarios"] == "fail":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
