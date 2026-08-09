#!/usr/bin/env python3
"""Capture reproducible Gradle build metrics for modularization scenarios.

Accepts explicit commands. Does not require Gradle Enterprise or network services.
Warmups are excluded from metrics. Unit tests should pass fake commands.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path


SCHEMA_VERSION = 1
SCRIPT_VERSION = "1"
SKILL = "measure-kotlin-modular-build-performance"

TASK_STATE_RE = re.compile(
    r"(\d+)\s+actionable\s+tasks?:?\s*((?:\d+\s+executed(?:,\s*)?)?(?:\d+\s+from\s+cache(?:,\s*)?)?(?:\d+\s+up-to-date(?:,\s*)?)?(?:\d+\s+skipped(?:,\s*)?)?)",
    re.IGNORECASE,
)
ALT_TASK_RE = re.compile(
    r"(\d+)\s+actionable\s+tasks?:\s*(\d+)\s+executed(?:,\s*(\d+)\s+from\s+cache)?(?:,\s*(\d+)\s+up-to-date)?(?:,\s*(\d+)\s+skipped)?",
    re.IGNORECASE,
)
CONFIG_CACHE_RE = re.compile(
    r"Configuration cache (entry reused|entry stored|cannot be reused|problems found)",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path, required=True, help="build-metrics-config JSON")
    parser.add_argument("--output", type=Path, required=True, help="metrics JSON output path")
    parser.add_argument(
        "--label",
        default="current",
        help="baseline|current|or custom label stored in the artifact",
    )
    parser.add_argument(
        "--command-runner",
        default=None,
        help="Optional executable used instead of the shell for tests (receives argv after --)",
    )
    return parser.parse_args()


def load_config(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version: {data.get('schema_version')!r}")
    scenarios = data.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("config.scenarios must be a non-empty list")
    for scenario in scenarios:
        if not isinstance(scenario, dict) or not scenario.get("id"):
            raise ValueError("each scenario needs an id")
        if not scenario.get("command") or not isinstance(scenario["command"], list):
            raise ValueError(f"scenario {scenario.get('id')!r} needs command argv list")
    return data


def parse_task_states(output: str) -> dict[str, int]:
    states = {"executed": 0, "from_cache": 0, "up_to_date": 0, "skipped": 0, "actionable": 0}
    match = ALT_TASK_RE.search(output)
    if match:
        states["actionable"] = int(match.group(1))
        states["executed"] = int(match.group(2) or 0)
        states["from_cache"] = int(match.group(3) or 0)
        states["up_to_date"] = int(match.group(4) or 0)
        states["skipped"] = int(match.group(5) or 0)
        return states
    # Fallback token scan
    states["actionable"] = _first_int(r"(\d+)\s+actionable\s+tasks?", output)
    states["executed"] = _first_int(r"(\d+)\s+executed", output)
    states["from_cache"] = _first_int(r"(\d+)\s+from\s+cache", output)
    states["up_to_date"] = _first_int(r"(\d+)\s+up-to-date", output)
    states["skipped"] = _first_int(r"(\d+)\s+skipped", output)
    return states


def _first_int(pattern: str, text: str) -> int:
    match = re.search(pattern, text, re.IGNORECASE)
    return int(match.group(1)) if match else 0


def parse_configuration_cache(output: str) -> str | None:
    match = CONFIG_CACHE_RE.search(output)
    if not match:
        return None
    token = match.group(1).lower()
    if "reused" in token:
        return "reused"
    if "stored" in token:
        return "stored"
    if "cannot" in token:
        return "not-reused"
    return token


def median(values: list[float]) -> float | None:
    if not values:
        return None
    return float(statistics.median(values))


def run_command(
    root: Path,
    command: list[str],
    env: dict[str, str],
    timeout: int,
    command_runner: str | None,
) -> subprocess.CompletedProcess[str]:
    argv = list(command)
    if command_runner:
        argv = [command_runner, *argv]
    return subprocess.run(
        argv,
        cwd=root,
        text=True,
        capture_output=True,
        env=env,
        timeout=timeout,
    )


def capture(root: Path, config: dict, label: str, command_runner: str | None) -> dict:
    warmups = int(config.get("warmups", 1))
    runs = int(config.get("measured_runs", 3))
    timeout = int(config.get("timeout_seconds", 3600))
    env = os.environ.copy()
    env.update({str(k): str(v) for k, v in (config.get("environment") or {}).items()})
    scenario_results = []
    for scenario in config["scenarios"]:
        command = [str(part) for part in scenario["command"]]
        warmup_runs = []
        measured = []
        failed = False
        failure_message = None
        for index in range(warmups):
            try:
                result = run_command(root, command, env, timeout, command_runner)
            except (OSError, subprocess.TimeoutExpired) as exc:
                failed = True
                failure_message = str(exc)
                break
            warmup_runs.append(
                {
                    "index": index,
                    "exit_code": result.returncode,
                    "elapsed_seconds": None,
                    "excluded_from_metrics": True,
                }
            )
            if result.returncode != 0 and not scenario.get("allow_failure", False):
                failed = True
                failure_message = result.stderr[-500:] or result.stdout[-500:]
                break
        if failed:
            scenario_results.append(
                {
                    "id": scenario["id"],
                    "command": command,
                    "status": "failed",
                    "failure": failure_message,
                    "warmups": warmup_runs,
                    "runs": [],
                    "median_elapsed_seconds": None,
                }
            )
            continue
        for index in range(runs):
            started = time.perf_counter()
            try:
                result = run_command(root, command, env, timeout, command_runner)
            except (OSError, subprocess.TimeoutExpired) as exc:
                failed = True
                failure_message = str(exc)
                break
            elapsed = time.perf_counter() - started
            output = (result.stdout or "") + "\n" + (result.stderr or "")
            # Allow fake runners to embed METRICS_ELAPSED=...
            embedded = re.search(r"METRICS_ELAPSED=([0-9.]+)", output)
            if embedded:
                elapsed = float(embedded.group(1))
            states = parse_task_states(output)
            measured.append(
                {
                    "index": index,
                    "exit_code": result.returncode,
                    "elapsed_seconds": elapsed,
                    "task_states": states,
                    "configuration_cache": parse_configuration_cache(output),
                    "excluded_from_metrics": False,
                }
            )
            if result.returncode != 0 and not scenario.get("allow_failure", False):
                failed = True
                failure_message = result.stderr[-500:] or result.stdout[-500:]
                break
        elapsed_values = [run["elapsed_seconds"] for run in measured if run["elapsed_seconds"] is not None]
        scenario_results.append(
            {
                "id": scenario["id"],
                "command": command,
                "status": "failed" if failed else "ok",
                "failure": failure_message,
                "warmups": warmup_runs,
                "runs": measured,
                "median_elapsed_seconds": median(elapsed_values),
                "median_task_states": {
                    key: median(
                        [
                            float(run["task_states"].get(key, 0))
                            for run in measured
                            if run.get("task_states")
                        ]
                    )
                    for key in ("executed", "from_cache", "up_to_date", "skipped", "actionable")
                }
                if measured
                else None,
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "generator": {"skill": SKILL, "script": "capture_gradle_build_metrics.py", "version": SCRIPT_VERSION},
        "repository": {"root": ".", "revision": None},
        "label": label,
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "java_home": env.get("JAVA_HOME"),
            "config_environment": config.get("environment") or {},
        },
        "inputs": {
            "warmups": warmups,
            "measured_runs": runs,
            "scenario_ids": [s["id"] for s in config["scenarios"]],
        },
        "scenarios": scenario_results,
        "unresolved": [s["id"] for s in scenario_results if s["status"] != "ok"],
        "gates": {
            "all_scenarios_ok": "pass" if all(s["status"] == "ok" for s in scenario_results) else "fail"
        },
    }


def main() -> int:
    options = parse_args()
    root = options.root.resolve()
    if not root.is_dir():
        print(f"error: root is not a directory: {root}", file=sys.stderr)
        return 2
    try:
        config = load_config(options.config)
        result = capture(root, config, options.label, options.command_runner)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote build metrics to {options.output}")
    return 0 if result["gates"]["all_scenarios_ok"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
