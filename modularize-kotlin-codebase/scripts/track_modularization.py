#!/usr/bin/env python3
"""Create and maintain a resumable, repository-local modularization work ledger.

The script never runs build commands or edits production code. It records reviewed
chunks, decisions, risks, adapters, and command outcomes in JSON and regenerates a
human-readable Markdown log after every mutation.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_VERSION = 1
DEFAULT_STATE = ".modularization/work-state.json"
DEFAULT_MARKDOWN = ".modularization/worklog.md"
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
TERMINAL_STATUSES = {"completed", "skipped"}
CHECK_CLASSIFICATIONS = {"pass", "pre-existing-failure", "introduced-failure", "not-run"}


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root")
    parser.add_argument("--state", default=DEFAULT_STATE, help="Repository-relative JSON state path")
    parser.add_argument("--markdown", default=DEFAULT_MARKDOWN, help="Repository-relative Markdown path")
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="Initialize a work ledger from an optional module plan")
    init.add_argument("--plan", type=Path)
    init.add_argument("--config", type=Path)

    add_chunk = commands.add_parser("add-chunk", help="Append one reviewed work chunk")
    add_chunk.add_argument("--id", required=True)
    add_chunk.add_argument("--phase", required=True)
    add_chunk.add_argument("--title", required=True)
    add_chunk.add_argument("--depends-on", action="append", default=[])
    add_chunk.add_argument("--scope", action="append", default=[])
    add_chunk.add_argument("--acceptance", action="append", default=[])
    add_chunk.add_argument("--skippable", action="store_true", help="Allow this manually-added optional chunk to be skipped")

    start = commands.add_parser("start", help="Start one planned or blocked chunk")
    start.add_argument("--chunk", required=True)

    check = commands.add_parser("record-check", help="Record one externally-run verification command")
    check.add_argument("--chunk", required=True)
    check.add_argument("--argv-json", required=True, help='JSON array, for example ["./gradlew",":app:check"]')
    check.add_argument("--exit-code", required=True, type=int)
    check.add_argument("--classification", choices=sorted(CHECK_CLASSIFICATIONS))
    check.add_argument("--summary", required=True)
    check.add_argument("--artifact", action="append", default=[])
    check.add_argument("--advisory", action="store_true", help="Do not require this check to pass before completion")

    complete = commands.add_parser("complete", help="Complete an in-progress chunk after evidence is recorded")
    complete.add_argument("--chunk", required=True)
    complete.add_argument("--note", required=True)
    complete.add_argument("--evidence", action="append", default=[])
    complete.add_argument("--no-check-reason")

    block = commands.add_parser("block", help="Record a concrete blocker for an in-progress chunk")
    block.add_argument("--chunk", required=True)
    block.add_argument("--reason", required=True)

    skip = commands.add_parser("skip", help="Skip a chunk only with an explicit architectural reason")
    skip.add_argument("--chunk", required=True)
    skip.add_argument("--reason", required=True)

    decision = commands.add_parser("add-decision", help="Record an approved architecture decision")
    decision.add_argument("--id", required=True)
    decision.add_argument("--summary", required=True)
    decision.add_argument("--rationale", required=True)

    risk = commands.add_parser("add-risk", help="Record a migration risk and mitigation")
    risk.add_argument("--id", required=True)
    risk.add_argument("--summary", required=True)
    risk.add_argument("--mitigation", required=True)

    adapter = commands.add_parser("add-adapter", help="Track temporary compatibility code")
    adapter.add_argument("--id", required=True)
    adapter.add_argument("--path", required=True)
    adapter.add_argument("--owner", required=True)
    adapter.add_argument("--remove-when", required=True)

    resolve = commands.add_parser("resolve-adapter", help="Mark a temporary adapter removed")
    resolve.add_argument("--id", required=True)
    resolve.add_argument("--note", required=True)

    commands.add_parser("status", help="Print a concise work-ledger status")
    commands.add_parser("validate", help="Validate state invariants and regenerate Markdown")
    return parser.parse_args()


def safe_path(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute():
        raise ValueError(f"ledger paths must be repository-relative: {relative}")
    resolved = (root / candidate).resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"ledger path escapes repository root: {relative}")
    return resolved


def load_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {label} {path}: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported or missing schema_version in {label} {path}")
    return value


def git(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def repository_snapshot(root: Path) -> dict:
    top = git(root, "rev-parse", "--show-toplevel")
    if top is None or Path(top).resolve() != root:
        raise ValueError(f"root is not the top level of a Git repository: {root}")
    status = (git(root, "status", "--short", "--untracked-files=all") or "").splitlines()
    return {
        "branch": git(root, "branch", "--show-current") or None,
        "head": git(root, "rev-parse", "HEAD"),
        "dirty_files": status,
    }


def feature_chunks(plan: dict) -> list[dict]:
    plan_acceptance = plan.get("plan_acceptance", {})
    if not isinstance(plan_acceptance, dict):
        raise ValueError("plan_acceptance must be an object")
    shared_ui_gate = plan_acceptance.get("shared_ui_graph")
    shared_ui_violations = plan.get("shared_ui_violations", [])
    if not isinstance(shared_ui_violations, list):
        raise ValueError("shared_ui_violations must be a list")
    shared_ui_dependencies = plan.get("shared_ui_dependencies", [])
    if not isinstance(shared_ui_dependencies, list):
        raise ValueError("shared_ui_dependencies must be a list")
    has_shared_ui_metadata = (
        "shared_ui_dependencies" in plan
        or "shared_ui_violations" in plan
        or "shared_ui_graph" in plan_acceptance
    )
    if (has_shared_ui_metadata and shared_ui_gate != "pass") or shared_ui_violations:
        raise ValueError(
            "plan cannot initialize while the shared-UI dependency graph gate "
            f"is {shared_ui_gate or 'unset'} with "
            f"{len(shared_ui_violations)} violation(s)"
        )
    chunks: list[dict] = [
        chunk("baseline", "baseline", "Capture repository baseline", [], ["Build and test baseline is recorded with pre-existing failures separated."]),
        chunk("conventions", "build-conventions", "Create and prove convention plugins", ["baseline"], ["Build logic compiles.", "At least one representative production module uses the conventions without task, target, source-set, dependency, resource, or test regressions."]),
    ]
    shared_test_modules = plan.get("testing", {}).get("shared_foundation_modules", [])
    if shared_test_modules:
        chunks.append(chunk("test-foundations", "testing", "Create or validate shared test foundations required by consumers", ["conventions"], ["Shared test modules are test-classpath only.", "Owning modules retain their actual test cases."]))
    foundation_targets = list(plan.get("foundation_modules", []))
    foundation_targets += [
        value.get("target")
        for value in plan.get("shared_assignments", [])
        if isinstance(value, dict) and isinstance(value.get("target"), str)
        and value["target"].startswith((":core", ":util", ":utility"))
    ]
    if foundation_targets:
        chunks.append(chunk("foundations", "foundations", "Create or validate pilot-required core and utility foundations", ["conventions"], ["Only reviewed foundation targets are introduced.", "No speculative empty modules are introduced."]))
    has_test_foundations = any(item["id"] == "test-foundations" for item in chunks)
    has_foundations = any(item["id"] == "foundations" for item in chunks)
    feature_done: list[str] = []
    used_feature_ids: set[str] = set()
    all_module_chunks: dict[str, str] = {}
    for feature in plan.get("features", []):
        name = feature.get("name")
        if not isinstance(name, str):
            continue
        feature_id = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        if not ID_RE.fullmatch(feature_id) or feature_id in used_feature_ids:
            raise ValueError(f"feature name cannot produce a unique chunk id: {name!r}")
        used_feature_ids.add(feature_id)
        target_modules = feature.get("target_modules", [])
        configured_layers = {value.split(":")[-1] for value in target_modules if isinstance(value, str)}
        existing_layers = {
            value.split(":")[-1]
            for value in feature.get("existing_modules", [])
            if isinstance(value, str)
        }
        if not target_modules:
            configured_layers = {"domain", "test", "data", "navigation", "ui"}
        previous = "foundations" if has_foundations else "conventions"
        for layer, title in (
            ("domain", "Migrate domain contracts and behavior"),
            ("test-support", "Create feature test support when reuse requires it"),
            ("data", "Migrate data implementations and persistence/network ownership"),
            ("navigation", "Migrate stable navigation contracts"),
            ("shared-ui", "Migrate feature-owned reusable UI"),
            ("ui", "Migrate presentation and resources"),
            ("wiring", "Register app, DI, navigation, serialization, and platform wiring"),
            ("cleanup", "Remove legacy paths and temporary bridges"),
            ("verify", "Verify the complete vertical slice"),
        ):
            module_layer = "test" if layer == "test-support" else layer
            if layer not in {"wiring", "cleanup", "verify"} and module_layer not in configured_layers:
                continue
            chunk_id = f"feature-{feature_id}-{layer}"
            dependencies = [previous]
            if has_test_foundations and layer in {"data", "navigation", "shared-ui", "ui"}:
                dependencies.append("test-foundations")
            reviewed_title = title
            if module_layer in existing_layers:
                reviewed_title = f"Validate the existing {module_layer} module and migrate assigned behavior"
            chunks.append(chunk(
                chunk_id,
                f"feature-{name}",
                f"{name}: {reviewed_title}",
                dependencies,
                [
                    f"The `{name}` {layer} batch satisfies its migration definition of done.",
                    "Pre-existing module structure is never treated as completed without current convention, boundary, source-placement, and test evidence."
                    if module_layer in existing_layers
                    else "New module structure is registered, convention-driven, and verified before dependent layers move.",
                ],
            ))
            for target_module in target_modules:
                if (
                    isinstance(target_module, str)
                    and target_module.split(":")[-1] == module_layer
                ):
                    all_module_chunks[target_module] = chunk_id
            previous = chunk_id
        feature_done.append(previous)
    chunks_by_id = {item["id"]: item for item in chunks}
    feature_root_parts = [
        part
        for part in str(plan.get("feature_root", "feature")).replace("/", ":").split(":")
        if part
    ]

    def feature_layer(path: object) -> str | None:
        if not isinstance(path, str):
            return None
        parts = [part for part in path.split(":") if part]
        if (
            len(parts) != len(feature_root_parts) + 2
            or parts[:len(feature_root_parts)] != feature_root_parts
        ):
            return None
        return parts[-1]

    for edge in shared_ui_dependencies:
        if not isinstance(edge, dict):
            raise ValueError("shared_ui_dependencies entries must be objects")
        consumer = edge.get("consumer")
        provider = edge.get("provider")

        if feature_layer(consumer) != "ui" or feature_layer(provider) != "shared-ui":
            raise ValueError(
                "shared_ui_dependencies require a consumer feature ui module "
                "and provider feature shared-ui module"
            )
        consumer_chunk = all_module_chunks.get(consumer)
        provider_chunk = all_module_chunks.get(provider)
        if not consumer_chunk or not provider_chunk:
            raise ValueError(
                "shared_ui_dependencies must reference planned consumer ui and provider shared-ui modules"
            )
        chunks_by_id[consumer_chunk]["depends_on"] = list(dict.fromkeys([
            *chunks_by_id[consumer_chunk]["depends_on"],
            provider_chunk,
        ]))
    final_dependencies = list(dict.fromkeys([
        *(["test-foundations"] if has_test_foundations else []),
        *(["foundations"] if has_foundations else []),
        *feature_done,
    ]))
    if not final_dependencies:
        final_dependencies = ["conventions"]
    chunks.append(chunk("final-verification", "completion", "Run repository-wide architecture and build verification", final_dependencies, ["No untracked adapters or remaining monolith files exist.", "Convention use and test-module boundaries are enforced.", "All required repository checks pass or only approved baseline failures remain."]))
    return chunks


def chunk(chunk_id: str, phase: str, title: str, dependencies: list[str], acceptance: list[str]) -> dict:
    return {
        "id": chunk_id,
        "phase": phase,
        "title": title,
        "status": "planned",
        "depends_on": list(dict.fromkeys(dependencies)),
        "scope": [],
        "acceptance": acceptance,
        "checks": [],
        "evidence": [],
        "notes": [],
        "history": [{"at": now(), "event": "planned"}],
        "skippable": False,
    }


def initial_state(root: Path, plan: dict | None, config: dict | None) -> dict:
    snapshot = repository_snapshot(root)
    chunks = feature_chunks(plan or {"features": []})
    verification = (config or {}).get("verification", {})
    if verification:
        by_id = {item["id"]: item for item in chunks}
        by_id["baseline"]["planned_checks"] = verification.get("baseline_commands", [])
        by_id["conventions"]["planned_checks"] = verification.get("build_logic_commands", [])
        by_id["final-verification"]["planned_checks"] = verification.get("app_compile_commands", []) + verification.get("architecture_commands", [])
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": now(),
        "updated_at": now(),
        "repository": {"root_name": root.name, "baseline": snapshot},
        "source_artifacts": {
            "plan": str(plan.get("audit_source")) if plan else None,
            "config_project": (config or {}).get("project", {}).get("name"),
        },
        "chunks": chunks,
        "decisions": [],
        "risks": [],
        "adapters": [],
    }


def chunk_by_id(state: dict, chunk_id: str) -> dict:
    for item in state.get("chunks", []):
        if item.get("id") == chunk_id:
            return item
    raise ValueError(f"unknown chunk: {chunk_id}")


def validate_id(value: str, label: str = "id") -> None:
    if not ID_RE.fullmatch(value):
        raise ValueError(f"{label} must use lowercase letters, numbers, and single hyphens: {value}")


def validate_state(state: dict) -> None:
    if state.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported work-state schema_version")
    chunks = state.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        raise ValueError("work state must contain at least one chunk")
    ids: list[str] = []
    in_progress = 0
    for item in chunks:
        chunk_id = item.get("id")
        validate_id(chunk_id, "chunk id")
        if chunk_id in ids:
            raise ValueError(f"duplicate chunk id: {chunk_id}")
        ids.append(chunk_id)
        if item.get("status") not in {"planned", "in_progress", "blocked", "completed", "skipped"}:
            raise ValueError(f"invalid status for {chunk_id}: {item.get('status')}")
        in_progress += item.get("status") == "in_progress"
    if in_progress > 1:
        raise ValueError("only one chunk may be in progress")
    known = set(ids)
    for item in chunks:
        missing = set(item.get("depends_on", [])) - known
        if missing:
            raise ValueError(f"chunk {item['id']} has unknown dependencies: {sorted(missing)}")
        if item["id"] in item.get("depends_on", []):
            raise ValueError(f"chunk {item['id']} depends on itself")
    visiting: set[str] = set()
    visited: set[str] = set()
    by_id = {item["id"]: item for item in chunks}

    def visit(chunk_id: str) -> None:
        if chunk_id in visiting:
            raise ValueError(f"chunk dependency cycle includes {chunk_id}")
        if chunk_id in visited:
            return
        visiting.add(chunk_id)
        for dependency in by_id[chunk_id].get("depends_on", []):
            visit(dependency)
        visiting.remove(chunk_id)
        visited.add(chunk_id)

    for chunk_id in ids:
        visit(chunk_id)
    for item in chunks:
        if item["status"] in TERMINAL_STATUSES:
            incomplete = [dependency for dependency in item.get("depends_on", []) if by_id[dependency]["status"] not in TERMINAL_STATUSES]
            if incomplete:
                raise ValueError(f"terminal chunk {item['id']} has non-terminal dependencies: {incomplete}")


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def markdown(state: dict) -> str:
    lines = [
        "# Modularization work log",
        "",
        f"Updated: `{state['updated_at']}`",
        "",
        "## Progress",
        "",
        "| Chunk | Phase | Status | Dependencies |",
        "|---|---|---|---|",
    ]
    for item in state["chunks"]:
        dependencies = ", ".join(f"`{value}`" for value in item.get("depends_on", [])) or "—"
        lines.append(f"| `{item['id']}` {item['title']} | `{item['phase']}` | **{item['status']}** | {dependencies} |")
    lines += ["", "## Chunk evidence", ""]
    for item in state["chunks"]:
        lines += [f"### {item['id']}: {item['title']}", "", f"Status: **{item['status']}**", ""]
        if item.get("acceptance"):
            lines.append("Acceptance:")
            lines.append("")
            lines += [f"- {value}" for value in item["acceptance"]]
            lines.append("")
        if item.get("checks"):
            lines.append("Checks:")
            lines.append("")
            for check in item["checks"]:
                argv = " ".join(check["argv"])
                lines.append(f"- `{argv}` — **{check['classification']}** (exit {check['exit_code']}): {check['summary']}")
            lines.append("")
        for note in item.get("notes", []):
            lines.append(f"- {note['at']}: {note['text']}")
        if item.get("notes"):
            lines.append("")
    for title, key in (("Decisions", "decisions"), ("Risks", "risks"), ("Temporary adapters", "adapters")):
        lines += [f"## {title}", ""]
        values = state.get(key, [])
        if not values:
            lines.append("None recorded.")
        else:
            for value in values:
                detail = value.get("rationale") or value.get("mitigation") or value.get("remove_when") or ""
                status = f" [{value.get('status')}]" if value.get("status") else ""
                lines.append(f"- `{value['id']}`{status}: {value.get('summary') or value.get('path')} — {detail}")
        lines.append("")
    return "\n".join(lines)


def persist(state: dict, state_path: Path, markdown_path: Path) -> None:
    state["updated_at"] = now()
    validate_state(state)
    atomic_write(state_path, json.dumps(state, indent=2, sort_keys=True) + "\n")
    atomic_write(markdown_path, markdown(state))


def unique_append(items: list[dict], value: dict) -> None:
    validate_id(value["id"])
    if any(item.get("id") == value["id"] for item in items):
        raise ValueError(f"duplicate id: {value['id']}")
    items.append(value)


def status_text(state: dict) -> str:
    counts = {status: sum(item["status"] == status for item in state["chunks"]) for status in ("planned", "in_progress", "blocked", "completed", "skipped")}
    active = next((item["id"] for item in state["chunks"] if item["status"] == "in_progress"), None)
    unresolved_adapters = sum(item.get("status") != "resolved" for item in state.get("adapters", []))
    return (
        f"Chunks: {counts['completed']} completed, {counts['in_progress']} in progress, "
        f"{counts['blocked']} blocked, {counts['planned']} planned, {counts['skipped']} skipped; "
        f"active={active or 'none'}; unresolved adapters={unresolved_adapters}"
    )


def main() -> int:
    options = parse_args()
    root = options.root.resolve()
    if not root.is_dir():
        print(f"error: root is not a directory: {root}", file=sys.stderr)
        return 2
    try:
        state_path = safe_path(root, options.state)
        markdown_path = safe_path(root, options.markdown)
        if state_path == markdown_path:
            raise ValueError("state and Markdown paths must differ")
        if options.command == "init":
            if state_path.exists() or markdown_path.exists():
                raise ValueError("work ledger already exists; use status/validate instead of reinitializing")
            plan = load_json(options.plan.resolve(), "plan") if options.plan else None
            config = load_json(options.config.resolve(), "config") if options.config else None
            state = initial_state(root, plan, config)
            persist(state, state_path, markdown_path)
            print(f"Initialized {state_path.relative_to(root)} with {len(state['chunks'])} chunk(s)")
            return 0

        state = load_json(state_path, "work state")
        validate_state(state)
        if options.command == "status":
            print(status_text(state))
            return 0
        if options.command == "validate":
            persist(state, state_path, markdown_path)
            print(f"Valid work state. {status_text(state)}")
            return 0
        if options.command == "add-chunk":
            validate_id(options.id, "chunk id")
            if any(item["id"] == options.id for item in state["chunks"]):
                raise ValueError(f"duplicate chunk id: {options.id}")
            state["chunks"].append(chunk(options.id, options.phase, options.title, options.depends_on, options.acceptance))
            state["chunks"][-1]["scope"] = options.scope
            state["chunks"][-1]["skippable"] = options.skippable
        elif options.command == "start":
            item = chunk_by_id(state, options.chunk)
            if any(other["status"] == "in_progress" and other["id"] != item["id"] for other in state["chunks"]):
                raise ValueError("another chunk is already in progress")
            if item["status"] not in {"planned", "blocked"}:
                raise ValueError(f"chunk {item['id']} cannot start from status {item['status']}")
            incomplete = [value for value in item.get("depends_on", []) if chunk_by_id(state, value)["status"] not in TERMINAL_STATUSES]
            if incomplete:
                raise ValueError(f"chunk {item['id']} has incomplete dependencies: {incomplete}")
            item["status"] = "in_progress"
            item["started_at"] = now()
            item["start_repository"] = repository_snapshot(root)
            item["history"].append({"at": now(), "event": "started"})
        elif options.command == "record-check":
            item = chunk_by_id(state, options.chunk)
            if item["status"] != "in_progress":
                raise ValueError("checks may only be recorded against the in-progress chunk")
            try:
                argv = json.loads(options.argv_json)
            except json.JSONDecodeError as exc:
                raise ValueError(f"argv-json is invalid JSON: {exc}") from exc
            if not isinstance(argv, list) or not argv or not all(isinstance(value, str) and value for value in argv):
                raise ValueError("argv-json must be a non-empty JSON array of non-empty strings")
            classification = options.classification or ("pass" if options.exit_code == 0 else "introduced-failure")
            if classification == "pass" and options.exit_code != 0:
                raise ValueError("a passing check must have exit code 0")
            if classification in {"pre-existing-failure", "introduced-failure"} and options.exit_code == 0:
                raise ValueError("a failed check must have a non-zero exit code")
            item["checks"].append({
                "at": now(), "argv": argv, "exit_code": options.exit_code,
                "classification": classification, "summary": options.summary,
                "artifacts": options.artifact, "required": not options.advisory,
            })
        elif options.command == "complete":
            item = chunk_by_id(state, options.chunk)
            if item["status"] != "in_progress":
                raise ValueError("only the in-progress chunk may be completed")
            required_checks = [value for value in item.get("checks", []) if value.get("required", True)]
            blocking = [value for value in required_checks if value["classification"] in {"introduced-failure", "not-run"}]
            if blocking:
                raise ValueError("required checks contain introduced failures or were not run")
            recorded_argv = [value["argv"] for value in required_checks]
            missing_planned = []
            for command in item.get("planned_checks", []):
                try:
                    expected_argv = shlex.split(command)
                except ValueError as exc:
                    raise ValueError(f"planned check is not valid shell-like argv: {command!r}: {exc}") from exc
                if expected_argv not in recorded_argv:
                    missing_planned.append(command)
            if missing_planned:
                raise ValueError(f"planned checks have no required recorded result: {missing_planned}")
            if not required_checks and not options.no_check_reason:
                raise ValueError("record a required check or provide --no-check-reason")
            if item["id"] == "final-verification":
                open_adapters = [value["id"] for value in state.get("adapters", []) if value.get("status") != "resolved"]
                if open_adapters:
                    raise ValueError(f"final verification cannot complete with open adapters: {open_adapters}")
            if options.no_check_reason:
                item["notes"].append({"at": now(), "text": f"No executable check: {options.no_check_reason}"})
            item["notes"].append({"at": now(), "text": options.note})
            item["evidence"].extend(options.evidence)
            item["status"] = "completed"
            item["completed_at"] = now()
            item["end_repository"] = repository_snapshot(root)
            item["history"].append({"at": now(), "event": "completed"})
        elif options.command == "block":
            item = chunk_by_id(state, options.chunk)
            if item["status"] != "in_progress":
                raise ValueError("only the in-progress chunk may be blocked")
            item["status"] = "blocked"
            item["notes"].append({"at": now(), "text": f"Blocked: {options.reason}"})
            item["history"].append({"at": now(), "event": "blocked", "reason": options.reason})
        elif options.command == "skip":
            item = chunk_by_id(state, options.chunk)
            if item["status"] not in {"planned", "blocked"}:
                raise ValueError("only a planned or blocked chunk may be skipped")
            if not item.get("skippable", False):
                raise ValueError(f"chunk {item['id']} is required; complete it with evidence instead of skipping it")
            item["status"] = "skipped"
            item["notes"].append({"at": now(), "text": f"Skipped: {options.reason}"})
            item["history"].append({"at": now(), "event": "skipped", "reason": options.reason})
        elif options.command == "add-decision":
            unique_append(state["decisions"], {"id": options.id, "summary": options.summary, "rationale": options.rationale, "recorded_at": now()})
        elif options.command == "add-risk":
            unique_append(state["risks"], {"id": options.id, "summary": options.summary, "mitigation": options.mitigation, "recorded_at": now()})
        elif options.command == "add-adapter":
            unique_append(state["adapters"], {"id": options.id, "path": options.path, "owner": options.owner, "remove_when": options.remove_when, "status": "open", "recorded_at": now()})
        elif options.command == "resolve-adapter":
            adapter = next((item for item in state["adapters"] if item["id"] == options.id), None)
            if not adapter:
                raise ValueError(f"unknown adapter: {options.id}")
            if adapter.get("status") == "resolved":
                raise ValueError(f"adapter already resolved: {options.id}")
            adapter.update({"status": "resolved", "resolved_at": now(), "resolution": options.note})
        persist(state, state_path, markdown_path)
        print(status_text(state))
        return 0
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
