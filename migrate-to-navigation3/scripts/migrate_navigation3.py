#!/usr/bin/env python3
"""Audit, plan, scaffold, and check Compose Navigation 2 → Navigation 3 migrations.

Deterministic inventory and contract scaffolding only. Project-specific Kotlin
host rewrites remain agent-driven. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
SCRIPT_VERSION = "1"
SKILL = "migrate-to-navigation3"
SCRIPT_NAME = "migrate_navigation3.py"

_PACK_ROOT = Path(__file__).resolve().parents[2]
if str(_PACK_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACK_ROOT))

from common.artifact_schema import envelope_fields, validate_artifact  # type: ignore
from common.gradle_graph import (  # type: ignore
    IMPORT_RE,
    PACKAGE_RE,
    discover_modules,
    source_set_for_path,
    walk_files,
)

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

NAV2_COORD_RE = re.compile(
    r"(?:androidx\.navigation|org\.jetbrains\.androidx\.navigation)"
    r"[\"']?\s*[:.]?\s*navigation[\"']?",
    re.IGNORECASE,
)
NAV2_ARTIFACT_MARKERS = (
    "androidx.navigation:navigation-compose",
    "androidx.navigation:navigation-runtime",
    "androidx.navigation:navigation-fragment",
    "androidx.navigation:navigation-ui",
    "org.jetbrains.androidx.navigation:navigation-compose",
    "org.jetbrains.androidx.navigation:navigation-runtime",
    "androidx.navigation.compose",
    "libs.androidx.navigation",
    "libs.navigation.compose",
    "navigation-compose",
)
NAV3_ARTIFACT_MARKERS = (
    "androidx.navigation3",
    "org.jetbrains.androidx.navigation3",
    "navigation3-ui",
    "navigation3-runtime",
    "libs.androidx.navigation3",
    "navigation3",
)
FRAGMENT_XML_MARKERS = (
    "navigation-fragment",
    "NavHostFragment",
    "androidx.navigation.fragment",
    "androidx.navigation.ui",
    "app:navGraph",
    "NavigationUI.",
)
NON_COMPOSE_NAV_MARKERS = (
    "com.bluelinelabs.conductor",
    "com.github.terrakok:cicerone",
    "ru.terrakok.cicerone",
    "com.github.arkivanov.decompose",
)

NAV2_IMPORT_MARKERS = (
    "androidx.navigation.compose.NavHost",
    "androidx.navigation.compose.composable",
    "androidx.navigation.compose.rememberNavController",
    "androidx.navigation.compose.dialog",
    "androidx.navigation.compose.navigation",
    "androidx.navigation.NavController",
    "androidx.navigation.NavHostController",
    "androidx.navigation.compose.NavBackStackEntry",
    "androidx.navigation.navDeepLink",
    "androidx.navigation.NavType",
    "androidx.navigation.toRoute",
    "androidx.navigation.navOptions",
    "androidx.navigation.compose.currentBackStackEntryAsState",
)
NAV3_IMPORT_MARKERS = (
    "androidx.navigation3",
    "androidx.navigation3.runtime.NavKey",
    "androidx.navigation3.ui.NavDisplay",
    "androidx.navigation3.runtime.entryProvider",
    "androidx.navigation3.runtime.rememberNavBackStack",
    "org.jetbrains.androidx.navigation3",
)

REMEMBER_NAV_CONTROLLER_RE = re.compile(r"\brememberNavController\s*\(")
NAV_HOST_RE = re.compile(r"\bNavHost\s*\(")
NAV_DISPLAY_RE = re.compile(r"\bNavDisplay\s*\(")
COMPOSABLE_STRING_RE = re.compile(
    r"""\bcomposable\s*\(\s*["']([^"']+)["']"""
)
COMPOSABLE_TYPED_RE = re.compile(
    r"\bcomposable\s*<\s*([A-Za-z_][\w.]*)\s*>"
)
NAVIGATION_NESTED_RE = re.compile(r"\bnavigation\s*(?:<|\()")
DIALOG_RE = re.compile(r"\bdialog\s*(?:<|\()")
BOTTOM_SHEET_RE = re.compile(r"\bbottomSheet\s*(?:<|\(|\s*\{)", re.IGNORECASE)
DEEP_LINK_RE = re.compile(r"\b(?:navDeepLink|deepLinks|navDeepLinks)\b")
POP_UP_TO_RE = re.compile(r"\bpopUpTo\b")
SINGLE_TOP_RE = re.compile(r"\blaunchSingleTop\b")
NAVIGATE_UP_RE = re.compile(r"\bnavigateUp\s*\(")
SAVED_STATE_RESULT_RE = re.compile(
    r"savedStateHandle|setResultForPrevious|consumeResult|setResult\s*\("
)
VIEW_MODEL_GRAPH_RE = re.compile(
    r"navGraphViewModels|getBackStackEntry\s*\(|hiltViewModel\s*\(|"
    r"viewModel\s*\(\s*(?:nav|parent|backStack)",
    re.IGNORECASE,
)
CURRENT_DEST_RE = re.compile(
    r"currentBackStackEntry|currentDestination|currentBackStackEntryAsState"
)
PREVIOUS_DEST_RE = re.compile(r"previousBackStackEntry|previousDestination")
RESET_SESSION_RE = re.compile(
    r"popUpTo\s*\(\s*0\b|clearBackStack|resetTo\b|logout.*navigat",
    re.IGNORECASE,
)
MULTIPLE_STACK_RE = re.compile(
    r"NavHost\s*\(|rememberNavController\s*\(",
)
BOTTOM_NAV_RE = re.compile(
    r"BottomNavigation|NavigationBar|bottomBar|selectedTab|topLevel",
    re.IGNORECASE,
)
ANIMATION_RE = re.compile(
    r"enterTransition|exitTransition|AnimatedNavHost|composable.*enterTransition",
    re.IGNORECASE,
)
SERIALIZABLE_RE = re.compile(r"@Serializable\b")
NAV_KEY_RE = re.compile(r"\bNavKey\b")
INTERFACE_ROUTE_RE = re.compile(
    r"(?m)^\s*(?:(?:public|internal|sealed|fun)\s+)*"
    r"(?:sealed\s+)?(?:interface|class)\s+"
    r"(AppRoute|Route|Screen|NavRoute|AppScreen|RootRoute|NavigationRoute)\b"
)
GENERIC_ROUTE_BASE_RE = re.compile(
    r"(?m)^\s*(?:(?:public|internal)\s+)*(?:sealed\s+)?(?:interface|class)\s+"
    r"([A-Za-z_][\w]*)\b[^{]*\bNavKey\b"
)
NAVIGATOR_INTERFACE_RE = re.compile(
    r"(?m)^\s*(?:(?:public|internal)\s+)*interface\s+(Navigator|AppNavigator|Navigation|NavNavigator)\b"
)
NAV_CONTROLLER_TYPE_RE = re.compile(r"\bNav(?:Host)?Controller\b")
PACKAGE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
MODULE_PATH_RE = re.compile(r"^:[A-Za-z0-9_-]+(?::[A-Za-z0-9_-]+)*$")
FORBIDDEN_DESTINATION_NAME = "Destination"

KOTLIN_SUFFIXES = {".kt", ".kts"}
GRADLE_NAMES = {"build.gradle", "build.gradle.kts", "libs.versions.toml", "libs.versions.toml.kts"}
XML_SUFFIXES = {".xml"}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    audit = sub.add_parser("audit", help="Inspect Navigation 2 usage and related behavior")
    audit.add_argument("--root", type=Path, default=Path.cwd())
    audit.add_argument("--json-out", type=Path)

    plan = sub.add_parser("plan", help="Turn an audit into navigation3-spec.json")
    plan.add_argument("--root", type=Path, default=Path.cwd())
    plan.add_argument("--audit", type=Path, help="Path to navigation3-audit.json (optional)")
    plan.add_argument("--json-out", type=Path)

    scaffold = sub.add_parser("scaffold", help="Preview/apply Navigator contract files")
    scaffold.add_argument("--root", type=Path, default=Path.cwd())
    scaffold.add_argument("--spec", type=Path, required=True)
    scaffold.add_argument("--apply", action="store_true")
    scaffold.add_argument(
        "--force-unresolved",
        action="store_true",
        help="Allow scaffold when plan gates still list unresolved items (not recommended)",
    )

    check = sub.add_parser("check", help="Report leftover Nav2 usage and incomplete migration")
    check.add_argument("--root", type=Path, default=Path.cwd())
    check.add_argument("--spec", type=Path)
    check.add_argument("--json-out", type=Path)

    return parser.parse_args(argv)


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected JSON object")
    return data


def write_json(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=False))


def relative_posix(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def safe_under_root(root: Path, relative: Path) -> Path:
    target = (root / relative).resolve()
    if target != root.resolve() and root.resolve() not in target.parents:
        raise ValueError(f"path escapes repository root: {relative}")
    return target


# ---------------------------------------------------------------------------
# Project detection
# ---------------------------------------------------------------------------


def detect_platform(root: Path, modules: list[dict[str, Any]], texts: list[str]) -> dict[str, Any]:
    joined = "\n".join(texts)
    has_kmp = bool(
        re.search(r"\bkotlin\s*\{", joined)
        and re.search(r"\b(androidTarget|iosArm64|iosSimulatorArm64|jvm\s*\()\b", joined)
    )
    has_common = any((root / m["directory"] / "src" / "commonMain").is_dir() for m in modules if m["directory"] != ".")
    if not has_common:
        has_common = any(p.is_dir() for p in root.glob("**/src/commonMain") if ".modularization" not in p.parts)
    has_android = "com.android" in joined or "android.library" in joined or "android.application" in joined
    if has_kmp or has_common:
        platform = "kmp"
    elif has_android:
        platform = "android"
    else:
        platform = "unknown"
    source_sets: set[str] = set()
    for path in walk_files(root):
        if path.suffix != ".kt":
            continue
        ss = source_set_for_path(path.relative_to(root))
        if ss:
            source_sets.add(ss)
    coordinates = "jetbrains" if platform == "kmp" else "androidx"
    return {
        "platform": platform,
        "compose_variant": "multiplatform" if platform == "kmp" else "android",
        "source_sets": sorted(source_sets),
        "navigation_coordinates": coordinates,
    }


def scan_dependency_mentions(root: Path) -> dict[str, list[dict[str, str]]]:
    nav2: list[dict[str, str]] = []
    nav3: list[dict[str, str]] = []
    fragment: list[dict[str, str]] = []
    non_compose: list[dict[str, str]] = []
    for path in walk_files(root):
        if path.name not in GRADLE_NAMES and path.suffix not in {".kts", ".toml", ".gradle"}:
            if path.suffix not in KOTLIN_SUFFIXES and path.suffix not in XML_SUFFIXES:
                continue
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = relative_posix(path, root)
        lower = text
        for marker in NAV2_ARTIFACT_MARKERS:
            if marker in lower:
                nav2.append({"path": rel, "marker": marker})
                break
        for marker in NAV3_ARTIFACT_MARKERS:
            if marker in lower and "navigation-compose" not in marker:
                # avoid counting navigation-compose as nav3
                if "navigation3" in marker or "navigation3" in lower.lower():
                    nav3.append({"path": rel, "marker": marker})
                    break
        for marker in FRAGMENT_XML_MARKERS:
            if marker in text:
                fragment.append({"path": rel, "marker": marker})
                break
        for marker in NON_COMPOSE_NAV_MARKERS:
            if marker in text:
                non_compose.append({"path": rel, "marker": marker})
                break
        # XML nav graphs
        if path.suffix == ".xml" and ("</navigation>" in text or "<navigation" in text):
            fragment.append({"path": rel, "marker": "xml-navigation-graph"})
    return {
        "navigation2": _dedupe_mentions(nav2),
        "navigation3": _dedupe_mentions(nav3),
        "fragment_xml": _dedupe_mentions(fragment),
        "non_compose": _dedupe_mentions(non_compose),
    }


def _dedupe_mentions(items: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, str]] = []
    for item in items:
        key = (item["path"], item["marker"])
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


# ---------------------------------------------------------------------------
# Source analysis
# ---------------------------------------------------------------------------


def analyze_kotlin_file(root: Path, path: Path) -> dict[str, Any] | None:
    if path.suffix != ".kt":
        return None
    rel = path.relative_to(root)
    if any(part in rel.parts for part in ("generated", "build")):
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    rel_s = rel.as_posix()
    package_match = PACKAGE_RE.search(text)
    imports = IMPORT_RE.findall(text)
    nav2_imports = [i for i in imports if any(m in i for m in (
        "androidx.navigation",
    )) and "navigation3" not in i]
    nav3_imports = [i for i in imports if "navigation3" in i]
    string_routes = COMPOSABLE_STRING_RE.findall(text)
    typed_routes = COMPOSABLE_TYPED_RE.findall(text)
    # also detect route("...") patterns and navigate("...")
    string_navigate = re.findall(r"""\bnavigate\s*\(\s*["']([^"']+)["']""", text)
    has_nav_host = bool(NAV_HOST_RE.search(text))
    has_nav_display = bool(NAV_DISPLAY_RE.search(text))
    remember_count = len(REMEMBER_NAV_CONTROLLER_RE.findall(text))
    nav_host_count = len(NAV_HOST_RE.findall(text))
    features = {
        "nav_host": has_nav_host,
        "nav_display": has_nav_display,
        "remember_nav_controller": remember_count > 0,
        "nav_controller_type": bool(NAV_CONTROLLER_TYPE_RE.search(text)),
        "nested_navigation": bool(NAVIGATION_NESTED_RE.search(text)),
        "dialog": bool(DIALOG_RE.search(text)),
        "bottom_sheet": bool(BOTTOM_SHEET_RE.search(text)),
        "deep_links": bool(DEEP_LINK_RE.search(text)),
        "pop_up_to": bool(POP_UP_TO_RE.search(text)),
        "launch_single_top": bool(SINGLE_TOP_RE.search(text)),
        "navigate_up": bool(NAVIGATE_UP_RE.search(text)),
        "transient_results": bool(SAVED_STATE_RESULT_RE.search(text)),
        "view_model_scope": bool(VIEW_MODEL_GRAPH_RE.search(text)),
        "current_route": bool(CURRENT_DEST_RE.search(text)),
        "previous_route": bool(PREVIOUS_DEST_RE.search(text)),
        "reset_session": bool(RESET_SESSION_RE.search(text)),
        "bottom_nav": bool(BOTTOM_NAV_RE.search(text)),
        "animations": bool(ANIMATION_RE.search(text)),
        "serializable": bool(SERIALIZABLE_RE.search(text)),
        "nav_key": bool(NAV_KEY_RE.search(text)),
        "to_route": "toRoute" in text,
    }
    occurrence_counts = {
        "remember_nav_controller": remember_count,
        "nav_host": nav_host_count,
    }
    route_bases = INTERFACE_ROUTE_RE.findall(text)
    nav_key_bases = GENERIC_ROUTE_BASE_RE.findall(text)
    navigators = NAVIGATOR_INTERFACE_RE.findall(text)
    # Avoid treating YSN Destination specially — still record if present as a base name
    if re.search(r"(?m)^\s*(?:sealed\s+)?(?:interface|class)\s+Destination\b", text):
        route_bases = list(route_bases) + ["Destination"]
    return {
        "path": rel_s,
        "package": package_match.group(1) if package_match else None,
        "source_set": source_set_for_path(rel),
        "nav2_imports": nav2_imports,
        "nav3_imports": nav3_imports,
        "string_routes": string_routes,
        "typed_routes": typed_routes,
        "string_navigate": string_navigate,
        "features": features,
        "occurrence_counts": occurrence_counts,
        "route_bases": route_bases,
        "nav_key_bases": nav_key_bases,
        "navigators": navigators,
        "controller_leaks": _controller_leaks(text, rel_s),
    }


def _controller_leaks(text: str, path: str) -> list[dict[str, str]]:
    leaks: list[dict[str, str]] = []
    if "ViewModel" not in path and "viewmodel" not in path.lower() and "ViewModel" not in text:
        # still flag constructor params of NavController anywhere in feature code
        pass
    for match in re.finditer(
        r"(?m)^\s*(?:private\s+|internal\s+|protected\s+|public\s+)?(?:val|var)\s+\w+\s*:\s*Nav(?:Host)?Controller\b",
        text,
    ):
        leaks.append({"path": path, "kind": "property", "evidence": match.group(0).strip()})
    for match in re.finditer(
        r"\b(?:Nav(?:Host)?Controller)\b",
        text,
    ):
        # parameter style in primary constructor
        line_start = text.rfind("\n", 0, match.start()) + 1
        line_end = text.find("\n", match.end())
        line = text[line_start:line_end if line_end != -1 else None]
        if "class " in line or "(" in line or "fun " in line:
            if "import " in line:
                continue
            if any(k in line for k in ("NavController", "NavHostController")):
                if "property" in str(leaks) and line.strip() in {x["evidence"] for x in leaks}:
                    continue
                if re.search(r"\b(class|fun|constructor)\b", text[max(0, match.start() - 200):match.start() + 50]):
                    if "ViewModel" in text[max(0, match.start() - 400):match.start()] or "ViewModel" in path:
                        leaks.append(
                            {
                                "path": path,
                                "kind": "viewmodel_or_nearby",
                                "evidence": line.strip()[:200],
                            }
                        )
    # de-dupe
    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for item in leaks:
        key = item["kind"] + item["evidence"]
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def collect_sources(root: Path) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for path in walk_files(root):
        analyzed = analyze_kotlin_file(root, path)
        if analyzed and (
            analyzed["nav2_imports"]
            or analyzed["nav3_imports"]
            or analyzed["features"]["nav_host"]
            or analyzed["features"]["nav_display"]
            or analyzed["features"]["remember_nav_controller"]
            or analyzed["route_bases"]
            or analyzed["navigators"]
            or analyzed["string_routes"]
            or analyzed["typed_routes"]
            or analyzed["features"]["nav_key"]
        ):
            sources.append(analyzed)
    return sources


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def build_audit(root: Path) -> dict[str, Any]:
    modules = discover_modules(root)
    build_texts: list[str] = []
    for module in modules:
        build = root / module["build_file"]
        if build.is_file():
            build_texts.append(build.read_text(encoding="utf-8", errors="replace"))
    catalog = root / "gradle" / "libs.versions.toml"
    if catalog.is_file():
        build_texts.append(catalog.read_text(encoding="utf-8", errors="replace"))

    project = detect_platform(root, modules, build_texts)
    deps = scan_dependency_mentions(root)
    sources = collect_sources(root)

    string_routes: list[dict[str, str]] = []
    typed_routes: list[dict[str, str]] = []
    hosts: list[dict[str, Any]] = []
    route_bases: list[dict[str, Any]] = []
    navigators: list[dict[str, Any]] = []
    controller_leaks: list[dict[str, str]] = []
    feature_counter: Counter[str] = Counter()
    occurrence_counter: Counter[str] = Counter()

    for src in sources:
        for route in src["string_routes"]:
            string_routes.append({"path": src["path"], "route": route})
        for route in src.get("string_navigate", []):
            string_routes.append({"path": src["path"], "route": route, "kind": "navigate"})
        for route in src["typed_routes"]:
            typed_routes.append({"path": src["path"], "route": route})
        feats = src["features"]
        for key, enabled in feats.items():
            if enabled:
                feature_counter[key] += 1
        for key, count in (src.get("occurrence_counts") or {}).items():
            occurrence_counter[key] += int(count)
        if feats["nav_host"] or feats["nav_display"] or feats["remember_nav_controller"]:
            hosts.append(
                {
                    "path": src["path"],
                    "style": "nav_display" if feats["nav_display"] and not feats["nav_host"] else (
                        "nav_host" if feats["nav_host"] else "controller_only"
                    ),
                    "nested_graphs": feats["nested_navigation"],
                    "dialogs": feats["dialog"],
                    "bottom_sheets": feats["bottom_sheet"],
                    "animations": feats["animations"],
                    "deep_links": feats["deep_links"],
                }
            )
        for name in src["route_bases"]:
            route_bases.append(
                {
                    "name": name,
                    "package": src["package"],
                    "path": src["path"],
                    "implements_nav_key": feats["nav_key"] or name in src["nav_key_bases"],
                }
            )
        for name in src["nav_key_bases"]:
            if not any(r["name"] == name and r["path"] == src["path"] for r in route_bases):
                route_bases.append(
                    {
                        "name": name,
                        "package": src["package"],
                        "path": src["path"],
                        "implements_nav_key": True,
                    }
                )
        for name in src["navigators"]:
            navigators.append({"name": name, "package": src["package"], "path": src["path"]})
        controller_leaks.extend(src.get("controller_leaks") or [])

    # Route style
    has_string = bool(string_routes)
    has_typed = bool(typed_routes) or any(s["features"].get("to_route") for s in sources)
    if has_string and has_typed:
        route_style = "mixed"
    elif has_string:
        route_style = "string"
    elif has_typed or route_bases:
        route_style = "typed"
    else:
        route_style = "unknown"

    multiple_stacks = feature_counter["bottom_nav"] > 0 and (
        occurrence_counter["remember_nav_controller"] > 1 or occurrence_counter["nav_host"] > 1
    )
    if not multiple_stacks:
        # heuristic: multiple NavHost across files, or bottom nav with multiple hosts
        multiple_stacks = occurrence_counter["nav_host"] > 1 and (
            feature_counter["bottom_nav"] > 0 or occurrence_counter["remember_nav_controller"] > 1
        )

    findings: list[dict[str, Any]] = []
    if deps["fragment_xml"]:
        findings.append(
            {
                "rule": "unsupported-scope",
                "severity": "error",
                "category": "fragment_xml",
                "evidence": deps["fragment_xml"][:10],
                "message": "Fragment/XML navigation is out of scope for this skill",
            }
        )
    if deps["non_compose"]:
        findings.append(
            {
                "rule": "unsupported-scope",
                "severity": "error",
                "category": "non_compose_navigation",
                "evidence": deps["non_compose"][:10],
                "message": "Non-Compose navigation libraries are out of scope",
            }
        )
    if not deps["navigation2"] and not any(s["nav2_imports"] for s in sources) and not any(
        s["features"]["nav_host"] for s in sources
    ):
        if deps["navigation3"] or any(s["nav3_imports"] for s in sources):
            findings.append(
                {
                    "rule": "already-on-navigation3",
                    "severity": "info",
                    "message": "No Navigation 2 usage detected; project may already use Navigation 3",
                }
            )
        else:
            findings.append(
                {
                    "rule": "no-compose-navigation-detected",
                    "severity": "warning",
                    "message": "No Compose Navigation 2 or 3 markers found",
                }
            )
    if route_style in {"string", "mixed"}:
        findings.append(
            {
                "rule": "string-routes-require-typed-phase",
                "severity": "warning",
                "message": "String routes should be converted to serializable keys before Nav3 cutover",
                "route_style": route_style,
            }
        )
    if route_style == "mixed":
        findings.append(
            {
                "rule": "ambiguous-route-style",
                "severity": "warning",
                "message": "Mixed string and typed routes; resolve before cutover",
            }
        )
    if multiple_stacks:
        findings.append(
            {
                "rule": "multiple-back-stacks",
                "severity": "info",
                "message": "Multiple back stacks / bottom navigation patterns detected",
            }
        )
    for leak in controller_leaks:
        findings.append(
            {
                "rule": "nav-controller-leak",
                "severity": "warning",
                "path": leak["path"],
                "evidence": leak["evidence"],
                "message": "NavController appears retained outside host wiring",
            }
        )

    # Prefer non-Destination bases for recommendations
    preferred_bases = [b for b in route_bases if b["name"] != FORBIDDEN_DESTINATION_NAME]
    if not preferred_bases:
        preferred_bases = route_bases

    navigation_modules = [
        m
        for m in modules
        if "navigation" in m["path"].lower() or "navigation" in m["directory"].lower()
    ]

    payload = envelope_fields(
        skill=SKILL,
        script=SCRIPT_NAME,
        script_version=SCRIPT_VERSION,
        repository_root=".",
    )
    payload.update(
        {
            "project": project,
            "modules": [m["path"] for m in modules],
            "dependencies": deps,
            "sources": sources,
            "hosts": hosts,
            "routes": {
                "style": route_style,
                "string_routes": string_routes[:200],
                "typed_routes": typed_routes[:200],
                "bases": preferred_bases,
                "all_bases_including_destination": route_bases,
            },
            "navigators": navigators,
            "controller_leaks": controller_leaks,
            "behavior": {
                "launch_single_top": feature_counter["launch_single_top"] > 0,
                "pop_up_to": feature_counter["pop_up_to"] > 0,
                "navigate_up": feature_counter["navigate_up"] > 0,
                "current_route_flow": feature_counter["current_route"] > 0,
                "previous_route_flow": feature_counter["previous_route"] > 0,
                "transient_results": feature_counter["transient_results"] > 0,
                "deep_link_routing": feature_counter["deep_links"] > 0,
                "graph_view_model_scope": feature_counter["view_model_scope"] > 0,
                "entry_view_model_scope": feature_counter["view_model_scope"] > 0,
                "reset_session": feature_counter["reset_session"] > 0,
                "dialogs": feature_counter["dialog"] > 0,
                "bottom_sheets": feature_counter["bottom_sheet"] > 0,
                "animations": feature_counter["animations"] > 0,
                "nested_graphs": feature_counter["nested_navigation"] > 0,
                "multiple_stacks": multiple_stacks,
                "bottom_nav": feature_counter["bottom_nav"] > 0,
                "serializable_routes": feature_counter["serializable"] > 0,
                "uses_nav_key": feature_counter["nav_key"] > 0,
            },
            "candidate_modules": {
                "navigation": navigation_modules,
            },
            "findings": findings,
            "gates": {
                "unsupported_scope": "fail"
                if any(f["rule"] == "unsupported-scope" for f in findings)
                else "pass",
                "compose_navigation_present": "pass"
                if deps["navigation2"] or any(s["nav2_imports"] or s["features"]["nav_host"] for s in sources)
                else ("pass" if deps["navigation3"] else "review"),
                "route_style": "review" if route_style in {"string", "mixed", "unknown"} else "pass",
            },
            "observed": {
                "host_count": len(hosts),
                "string_route_count": len(string_routes),
                "typed_route_count": len(typed_routes),
                "navigator_count": len(navigators),
                "feature_counts": dict(feature_counter),
                "occurrence_counts": dict(occurrence_counter),
            },
            "recommendations": _audit_recommendations(
                project, route_style, preferred_bases, navigators, navigation_modules, findings
            ),
        }
    )
    return payload


def _audit_recommendations(
    project: dict[str, Any],
    route_style: str,
    bases: list[dict[str, Any]],
    navigators: list[dict[str, Any]],
    navigation_modules: list[dict[str, Any]],
    findings: list[dict[str, Any]],
) -> list[str]:
    recs: list[str] = []
    if any(f["rule"] == "unsupported-scope" for f in findings):
        recs.append("Stop: unsupported Fragment/XML or non-Compose navigation detected.")
        return recs
    if route_style in {"string", "mixed"}:
        recs.append("Create serializable app-owned route keys while Navigation 2 still runs.")
    if bases:
        base = bases[0]
        if base["name"] == FORBIDDEN_DESTINATION_NAME:
            recs.append(
                "Existing type named Destination found; you may reuse it as NavKey, but this skill will not generate Destination."
            )
        else:
            recs.append(f"Reuse existing route base `{base['name']}` and implement NavKey before cutover.")
    else:
        recs.append("Type Navigator against NavKey (no app route base detected).")
    if navigators:
        recs.append(f"Reuse existing `{navigators[0]['name']}` interface rather than creating a parallel contract.")
    else:
        recs.append("Scaffold an app-owned Navigator in the approved navigation module.")
    if navigation_modules:
        recs.append(f"Preferred module: {navigation_modules[0]['path']}")
    else:
        recs.append("No navigation module found; coordinate with extract-kotlin-foundations if a new module is needed.")
    if project["navigation_coordinates"] == "jetbrains":
        recs.append("Use JetBrains AndroidX Navigation 3 coordinates for commonMain.")
    else:
        recs.append("Use AndroidX Navigation 3 coordinates for the Android app.")
    recs.append("Extract Navigator and migrate ViewModels before atomic NavDisplay cutover.")
    recs.append("Remove Navigation 2 only after check and verification pass.")
    return recs


def cmd_audit(options: argparse.Namespace) -> int:
    root = options.root.resolve()
    if not root.is_dir():
        print(f"error: root is not a directory: {root}", file=sys.stderr)
        return 2
    payload = build_audit(root)
    errors = validate_artifact(payload, "navigation3-audit")
    if errors:
        print("error: produced invalid navigation3-audit artifact:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 2
    write_json(options.json_out, payload)
    _print_audit_summary(payload)
    if options.json_out is None:
        print_json(payload)
    return 0


def _print_audit_summary(payload: dict[str, Any]) -> None:
    print("Navigation 3 migration audit")
    print(f"  platform: {payload['project']['platform']} ({payload['project']['navigation_coordinates']})")
    print(f"  route style: {payload['routes']['style']}")
    print(f"  hosts: {payload['observed']['host_count']}")
    print(f"  findings: {len(payload['findings'])}")
    for finding in payload["findings"][:12]:
        print(f"    - [{finding.get('severity')}] {finding.get('rule')}: {finding.get('message')}")
    print(f"  gates: {payload['gates']}")


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------


def build_plan(root: Path, audit: dict[str, Any] | None) -> dict[str, Any]:
    if audit is None:
        audit = build_audit(root)
    project = audit.get("project") or detect_platform(root, discover_modules(root), [])
    behavior = audit.get("behavior") or {}
    routes = audit.get("routes") or {}
    bases = routes.get("bases") or []
    navigators = audit.get("navigators") or []
    hosts = audit.get("hosts") or []
    findings = audit.get("findings") or []
    deps = audit.get("dependencies") or {}
    modules = audit.get("candidate_modules", {}).get("navigation") or []

    unresolved: list[dict[str, Any]] = []
    if any(f.get("rule") == "unsupported-scope" for f in findings):
        unresolved.append(
            {
                "id": "unsupported-scope",
                "message": "Fragment/XML or non-Compose navigation blocks this skill",
            }
        )

    existing_base = None
    for base in bases:
        if base.get("name") and base["name"] != FORBIDDEN_DESTINATION_NAME:
            existing_base = base
            break
    # Allow Destination only as reuse of existing type, never as generated name
    if existing_base is None and bases:
        # fall back to first base including Destination for reuse only
        existing_base = bases[0]

    if existing_base:
        contract_type = existing_base["name"]
        contract_import = (
            f"{existing_base['package']}.{existing_base['name']}"
            if existing_base.get("package")
            else existing_base["name"]
        )
    else:
        contract_type = "NavKey"
        contract_import = "androidx.navigation3.runtime.NavKey"
        unresolved.append(
            {
                "id": "route-base-missing",
                "message": "No app route base type found; Navigator will type against NavKey",
            }
        )

    nav_mod = modules[0] if modules else None
    if nav_mod:
        module_path = nav_mod["path"]
        module_directory = nav_mod["directory"]
    else:
        module_path = None
        module_directory = None
        unresolved.append(
            {
                "id": "navigation-module-missing",
                "message": "No navigation module detected; set navigator.module_path after review or extract foundations",
            }
        )

    package = None
    if existing_base and existing_base.get("package"):
        package = existing_base["package"]
    elif navigators and navigators[0].get("package"):
        package = navigators[0]["package"]
    elif module_directory:
        # weak inference from directory
        package = "com.example." + ".".join(p for p in module_directory.split("/") if p)
        unresolved.append(
            {
                "id": "package-inferred",
                "message": f"Package inferred as {package}; confirm before scaffold --apply",
            }
        )
    else:
        unresolved.append(
            {
                "id": "package-unknown",
                "message": "Set navigator.package before scaffold",
            }
        )

    existing_navigator = navigators[0] if navigators else None
    route_style = routes.get("style") or "unknown"
    requires_string_phase = route_style in {"string", "mixed"}

    if requires_string_phase:
        unresolved.append(
            {
                "id": "string-to-typed",
                "message": "Complete string→typed route conversion before host cutover",
            }
        )

    if behavior.get("multiple_stacks") and not behavior.get("bottom_nav"):
        unresolved.append(
            {
                "id": "multi-stack-ownership",
                "message": "Multiple stacks suspected without clear bottom-nav ownership",
            }
        )

    apis = {
        "navigate": True,
        "back": True,
        "navigate_up": bool(behavior.get("navigate_up")),
        "launch_single_top": bool(behavior.get("launch_single_top")),
        "pop_up_to": bool(behavior.get("pop_up_to")),
        "current_route_flow": bool(behavior.get("current_route_flow")),
        "previous_route_flow": bool(behavior.get("previous_route_flow")),
        "transient_results": bool(behavior.get("transient_results")),
        "readiness": False,
        "deep_link_routing": bool(behavior.get("deep_link_routing")),
        "graph_view_model_scope": bool(behavior.get("graph_view_model_scope")),
        "entry_view_model_scope": bool(behavior.get("entry_view_model_scope")),
        "reset_session": bool(behavior.get("reset_session")),
    }

    source_set = "commonMain" if project.get("platform") == "kmp" else "main"
    coordinates = project.get("navigation_coordinates") or "androidx"
    if coordinates == "jetbrains":
        nav2_coords = ["org.jetbrains.androidx.navigation:navigation-compose"]
        nav3_coords = ["org.jetbrains.androidx.navigation3:navigation3-ui"]
    else:
        nav2_coords = ["androidx.navigation:navigation-compose"]
        nav3_coords = [
            "androidx.navigation3:navigation3-runtime",
            "androidx.navigation3:navigation3-ui",
        ]

    # Collect observed nav2 markers
    observed_nav2 = sorted({m["marker"] for m in deps.get("navigation2") or []})
    if observed_nav2:
        nav2_coords = observed_nav2

    polymorphic = bool(behavior.get("serializable_routes")) and (
        route_style in {"typed", "mixed"} or bool(bases)
    )

    payload = envelope_fields(
        skill=SKILL,
        script=SCRIPT_NAME,
        script_version=SCRIPT_VERSION,
        repository_root=".",
        inputs={"audit": "inline-or-file"},
        unresolved=unresolved,
    )
    payload.update(
        {
            "project": project,
            "route_model": {
                "style": route_style,
                "existing_base_type": existing_base,
                "contract_type": contract_type,
                "contract_import": contract_import,
                "requires_string_to_typed_phase": requires_string_phase,
                "serialization": {
                    "uses_kotlinx_serialization": bool(behavior.get("serializable_routes")),
                    "polymorphic_registration_required": polymorphic,
                },
            },
            "navigator": {
                "module_path": module_path,
                "module_directory": module_directory,
                "package": package,
                "source_set": source_set,
                "interface_name": (existing_navigator or {}).get("name") or "Navigator",
                "existing_navigator": (
                    {
                        "name": existing_navigator["name"],
                        "path": existing_navigator["path"],
                        "action": "reuse-and-extend",
                    }
                    if existing_navigator
                    else None
                ),
                "apis": apis,
                "files": {
                    "navigator": "Navigator.kt",
                    "nav_options": "NavOptions.kt" if apis["launch_single_top"] or apis["pop_up_to"] else None,
                    "recording_fake": "RecordingNavigator.kt",
                    "recording_fake_module": None,
                },
            },
            "hosts": hosts,
            "back_stack": {
                "model": "multiple" if behavior.get("multiple_stacks") else "single",
                "multiple_stacks": bool(behavior.get("multiple_stacks")),
                "top_level_selection": bool(behavior.get("bottom_nav")),
                "nested_flow_normalization": bool(behavior.get("nested_graphs")),
                "process_death_restoration": True,
            },
            "dependencies": {
                "navigation2": nav2_coords,
                "navigation3_recommended": nav3_coords,
                "resolve_versions_from": "repository_catalog_or_official_guidance",
            },
            "migration_phases": [
                "audit",
                "plan",
                "string_to_typed_if_needed",
                "extract_navigator",
                "nav2_backed_implementation",
                "atomic_host_cutover",
                "remove_nav2",
                "verify",
            ],
            "gates": {
                "unsupported_scope": "fail"
                if any(u["id"] == "unsupported-scope" for u in unresolved)
                else "pass",
                "route_identity_stable": "review",
                "navigator_module_exists": "pass" if module_path else "fail",
                "plan_reviewed": "review",
                "string_to_typed": "fail" if requires_string_phase else "pass",
            },
            "findings": findings,
            "observed": audit.get("observed") or {},
            "recommendations": audit.get("recommendations") or [],
            "verification": [
                f"python3 scripts/{SCRIPT_NAME} check --root . --spec .modularization/navigation3-spec.json",
                "Compile navigation module and app hosts",
                "Run navigation unit tests with RecordingNavigator",
            ],
        }
    )
    return payload


def cmd_plan(options: argparse.Namespace) -> int:
    root = options.root.resolve()
    if not root.is_dir():
        print(f"error: root is not a directory: {root}", file=sys.stderr)
        return 2
    audit = None
    if options.audit:
        try:
            audit = load_json(options.audit)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    payload = build_plan(root, audit)
    errors = validate_artifact(payload, "navigation3-spec")
    if errors:
        print("error: produced invalid navigation3-spec artifact:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 2
    write_json(options.json_out, payload)
    print("Navigation 3 migration plan (spec)")
    print(f"  contract: {payload['route_model']['contract_type']}")
    print(f"  module: {payload['navigator'].get('module_path')}")
    print(f"  package: {payload['navigator'].get('package')}")
    print(f"  apis: {[k for k, v in payload['navigator']['apis'].items() if v]}")
    print(f"  unresolved: {len(payload['unresolved'])}")
    for item in payload["unresolved"]:
        print(f"    - {item['id']}: {item['message']}")
    print(f"  gates: {payload['gates']}")
    if options.json_out is None:
        print_json(payload)
    return 0


# ---------------------------------------------------------------------------
# Scaffold
# ---------------------------------------------------------------------------


def load_spec(path: Path) -> dict[str, Any]:
    data = load_json(path)
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version: {data.get('schema_version')!r}")
    navigator = data.get("navigator")
    if not isinstance(navigator, dict):
        raise ValueError("spec.navigator is required")
    package = navigator.get("package")
    if not package or not PACKAGE_NAME_RE.fullmatch(str(package)):
        raise ValueError(f"invalid navigator.package: {package!r}")
    module_directory = navigator.get("module_directory")
    if not module_directory or not isinstance(module_directory, str):
        raise ValueError("navigator.module_directory is required for scaffold")
    if module_directory.startswith("/") or ".." in Path(module_directory).parts:
        raise ValueError(f"invalid navigator.module_directory: {module_directory!r}")
    module_path = navigator.get("module_path")
    if module_path is not None and not MODULE_PATH_RE.fullmatch(str(module_path)):
        raise ValueError(f"invalid navigator.module_path: {module_path!r}")
    route_model = data.get("route_model") or {}
    contract_type = route_model.get("contract_type") or "NavKey"
    if contract_type == FORBIDDEN_DESTINATION_NAME and not route_model.get("existing_base_type"):
        raise ValueError(
            "refusing to generate a new type named Destination; use an existing base or NavKey"
        )
    # Never invent Destination when no existing base
    if not route_model.get("existing_base_type") and contract_type == FORBIDDEN_DESTINATION_NAME:
        raise ValueError("contract_type Destination is only valid when reusing an existing type")
    apis = navigator.get("apis") or {}
    if not apis.get("navigate") or not apis.get("back"):
        raise ValueError("navigator.apis.navigate and navigator.apis.back are required")
    interface_name = navigator.get("interface_name") or "Navigator"
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", interface_name):
        raise ValueError(f"invalid interface_name: {interface_name!r}")
    if interface_name == FORBIDDEN_DESTINATION_NAME:
        raise ValueError("interface_name must not be Destination")
    return data


def kotlin_type_import(contract_type: str, contract_import: str) -> str:
    if contract_type == "NavKey":
        return "androidx.navigation3.runtime.NavKey"
    return contract_import


def generate_navigator_kt(spec: dict[str, Any]) -> str:
    nav = spec["navigator"]
    route_model = spec["route_model"]
    package = nav["package"]
    name = nav.get("interface_name") or "Navigator"
    contract = route_model["contract_type"]
    contract_import = kotlin_type_import(contract, route_model.get("contract_import") or contract)
    apis = nav["apis"]
    lines = [
        f"package {package}",
        "",
    ]
    imports: list[str] = []
    if contract == "NavKey" or contract_import.endswith(".NavKey"):
        imports.append("androidx.navigation3.runtime.NavKey")
    elif contract_import and not contract_import.startswith(package + ".") and "." in contract_import:
        imports.append(contract_import)
    if apis.get("current_route_flow") or apis.get("previous_route_flow"):
        imports.append("kotlinx.coroutines.flow.StateFlow")
    for item in sorted(set(imports)):
        lines.append(f"import {item}")
    if imports:
        lines.append("")
    lines.append("/**")
    lines.append(" * App-owned navigation boundary.")
    lines.append(" *")
    lines.append(" * Generated by migrate-to-navigation3 scaffold. Wire DI with the")
    lines.append(" * repository's existing system; do not depend on NavController in ViewModels.")
    lines.append(" */")
    lines.append(f"interface {name} {{")
    route_param = "route"
    # navigate
    if apis.get("launch_single_top") or apis.get("pop_up_to"):
        lines.append(f"    fun navigate({route_param}: {contract}, navOptions: NavOptions? = null)")
    else:
        lines.append(f"    fun navigate({route_param}: {contract})")
    # back
    lines.append("    fun popBackStack(): Boolean")
    if apis.get("navigate_up"):
        lines.append("    fun navigateUp(): Boolean")
    if apis.get("pop_up_to"):
        lines.append(
            f"    fun popBackStack({route_param}: {contract}, inclusive: Boolean = false): Boolean"
        )
    if apis.get("current_route_flow"):
        lines.append(f"    val currentRoute: StateFlow<{contract}?>")
    if apis.get("previous_route_flow"):
        lines.append(f"    val previousRoute: StateFlow<{contract}?>")
    if apis.get("transient_results"):
        lines.append("    fun setResultForPrevious(key: String, value: Any?)")
        lines.append("    fun <T> consumeResult(key: String): T?")
    if apis.get("readiness"):
        lines.append("    val isReady: Boolean")
    if apis.get("deep_link_routing"):
        lines.append(f"    fun openDeepLink(uri: String): Boolean")
    if apis.get("reset_session"):
        lines.append(f"    fun resetTo({route_param}: {contract})")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def generate_nav_options_kt(spec: dict[str, Any]) -> str:
    nav = spec["navigator"]
    route_model = spec["route_model"]
    package = nav["package"]
    contract = route_model["contract_type"]
    contract_import = kotlin_type_import(contract, route_model.get("contract_import") or contract)
    lines = [f"package {package}", ""]
    if contract == "NavKey":
        lines.append("import androidx.navigation3.runtime.NavKey")
        lines.append("")
    elif contract_import and "." in contract_import and not contract_import.startswith(package + "."):
        lines.append(f"import {contract_import}")
        lines.append("")
    lines.extend(
        [
            "data class NavOptions(",
            "    val launchSingleTop: Boolean = false,",
            "    val popUpTo: PopUpToSpec? = null,",
            ")",
            "",
            "data class PopUpToSpec(",
            f"    val target: {contract},",
            "    val inclusive: Boolean = false,",
            ")",
            "",
        ]
    )
    return "\n".join(lines)


def generate_recording_navigator_kt(spec: dict[str, Any]) -> str:
    nav = spec["navigator"]
    route_model = spec["route_model"]
    package = nav["package"]
    name = nav.get("interface_name") or "Navigator"
    contract = route_model["contract_type"]
    contract_import = kotlin_type_import(contract, route_model.get("contract_import") or contract)
    apis = nav["apis"]
    lines = [f"package {package}", ""]
    imports: list[str] = []
    if contract == "NavKey":
        imports.append("androidx.navigation3.runtime.NavKey")
    elif contract_import and "." in contract_import and not contract_import.startswith(package + "."):
        imports.append(contract_import)
    if apis.get("current_route_flow") or apis.get("previous_route_flow"):
        imports.append("kotlinx.coroutines.flow.MutableStateFlow")
        imports.append("kotlinx.coroutines.flow.StateFlow")
        imports.append("kotlinx.coroutines.flow.asStateFlow")
    for item in sorted(set(imports)):
        lines.append(f"import {item}")
    if imports:
        lines.append("")
    lines.append(f"/** Recording fake for unit tests. Implements [{name}]. */")
    lines.append(f"class Recording{name} : {name} {{")
    lines.append("    data class NavigateCall(val route: Any, val navOptions: Any? = null)")
    lines.append("    val navigateCalls = mutableListOf<NavigateCall>()")
    lines.append("    val popBackStackCalls = mutableListOf<Unit>()")
    if apis.get("current_route_flow"):
        lines.append(f"    private val _currentRoute = MutableStateFlow<{contract}?>(null)")
        lines.append(f"    override val currentRoute: StateFlow<{contract}?> = _currentRoute.asStateFlow()")
    if apis.get("previous_route_flow"):
        lines.append(f"    private val _previousRoute = MutableStateFlow<{contract}?>(null)")
        lines.append(f"    override val previousRoute: StateFlow<{contract}?> = _previousRoute.asStateFlow()")
    if apis.get("readiness"):
        lines.append("    override var isReady: Boolean = true")
    # navigate
    if apis.get("launch_single_top") or apis.get("pop_up_to"):
        lines.append(f"    override fun navigate(route: {contract}, navOptions: NavOptions?) {{")
        lines.append("        navigateCalls += NavigateCall(route, navOptions)")
        if apis.get("current_route_flow"):
            lines.append("        _currentRoute.value = route")
        lines.append("    }")
    else:
        lines.append(f"    override fun navigate(route: {contract}) {{")
        lines.append("        navigateCalls += NavigateCall(route)")
        if apis.get("current_route_flow"):
            lines.append("        _currentRoute.value = route")
        lines.append("    }")
    lines.append("    override fun popBackStack(): Boolean {")
    lines.append("        popBackStackCalls += Unit")
    lines.append("        return true")
    lines.append("    }")
    if apis.get("navigate_up"):
        lines.append("    override fun navigateUp(): Boolean = popBackStack()")
    if apis.get("pop_up_to"):
        lines.append(
            f"    override fun popBackStack(route: {contract}, inclusive: Boolean): Boolean {{"
        )
        lines.append("        popBackStackCalls += Unit")
        lines.append("        return true")
        lines.append("    }")
    if apis.get("transient_results"):
        lines.append("    private val results = mutableMapOf<String, Any?>()")
        lines.append("    override fun setResultForPrevious(key: String, value: Any?) { results[key] = value }")
        lines.append("    @Suppress(\"UNCHECKED_CAST\")")
        lines.append("    override fun <T> consumeResult(key: String): T? = results.remove(key) as T?")
    if apis.get("deep_link_routing"):
        lines.append("    val deepLinkCalls = mutableListOf<String>()")
        lines.append("    override fun openDeepLink(uri: String): Boolean {")
        lines.append("        deepLinkCalls += uri")
        lines.append("        return true")
        lines.append("    }")
    if apis.get("reset_session"):
        lines.append(f"    override fun resetTo(route: {contract}) {{ navigate(route) }}")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def scaffold_plan(root: Path, spec: dict[str, Any]) -> list[tuple[Path, str]]:
    nav = spec["navigator"]
    module_directory = Path(nav["module_directory"])
    package_path = Path(*nav["package"].split("."))
    source_set = nav.get("source_set") or "commonMain"
    base = module_directory / "src" / source_set / "kotlin" / package_path
    files: list[tuple[Path, str]] = []
    existing = nav.get("existing_navigator")
    # If reusing existing navigator file, skip generating interface when file exists;
    # still plan it so dry-run shows skip-on-conflict.
    files.append((base / (nav.get("files") or {}).get("navigator") or "Navigator.kt", generate_navigator_kt(spec)))
    nav_options_name = (nav.get("files") or {}).get("nav_options")
    apis = nav["apis"]
    if nav_options_name and (apis.get("launch_single_top") or apis.get("pop_up_to")):
        files.append((base / nav_options_name, generate_nav_options_kt(spec)))
    fake_name = (nav.get("files") or {}).get("recording_fake") or "RecordingNavigator.kt"
    fake_module = (nav.get("files") or {}).get("recording_fake_module")
    if fake_module and isinstance(fake_module, str) and fake_module.startswith(":"):
        fake_dir = Path(*[p for p in fake_module.split(":") if p])
        fake_base = fake_dir / "src" / source_set / "kotlin" / package_path
        files.append((fake_base / fake_name, generate_recording_navigator_kt(spec)))
    else:
        files.append((base / fake_name, generate_recording_navigator_kt(spec)))
    # Resolve under root
    resolved: list[tuple[Path, str]] = []
    for rel, content in files:
        resolved.append((safe_under_root(root, rel), content))
    # Ensure generated sources never mention a required new Destination type
    for _, content in resolved:
        if "class Destination" in content or "interface Destination" in content:
            if not (spec.get("route_model") or {}).get("existing_base_type"):
                raise ValueError("scaffold refused: generated Destination type without existing base")
    return resolved


def cmd_scaffold(options: argparse.Namespace) -> int:
    root = options.root.resolve()
    if not root.is_dir():
        print(f"error: root is not a directory: {root}", file=sys.stderr)
        return 2
    try:
        # Load raw JSON first so unsupported-scope can fail before package validation.
        raw = load_json(options.spec)
        if (raw.get("gates") or {}).get("unsupported_scope") == "fail":
            print("error: unsupported_scope gate is fail; refuse scaffold", file=sys.stderr)
            return 2
        if any(u.get("id") == "unsupported-scope" for u in (raw.get("unresolved") or [])):
            print("error: unsupported-scope remains unresolved; refuse scaffold", file=sys.stderr)
            return 2
        spec = load_spec(options.spec)
        unresolved = spec.get("unresolved") or []
        blocking = [u for u in unresolved if u.get("id") in {"unsupported-scope", "package-unknown", "navigation-module-missing"}]
        if blocking and not options.force_unresolved:
            print("error: unresolved blocking decisions remain (use --force-unresolved after review):", file=sys.stderr)
            for item in blocking:
                print(f"  - {item.get('id')}: {item.get('message')}", file=sys.stderr)
            return 2
        if not spec["navigator"].get("module_directory") or not spec["navigator"].get("package"):
            raise ValueError("navigator.module_directory and package are required")
        files = scaffold_plan(root, spec)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    conflicts = [path for path, _ in files if path.exists()]
    mode = "Applying" if options.apply else "Dry run"
    print(f"{mode}: {len(files)} navigation contract file(s)")
    for path, _ in files:
        rel = relative_posix(path, root)
        suffix = " [exists]" if path.exists() else ""
        print(f"  - {rel}{suffix}")
    print(f"  contract_type: {spec['route_model']['contract_type']}")
    print(f"  package: {spec['navigator']['package']}")
    if not options.apply:
        return 0
    if conflicts:
        print("error: refusing to overwrite existing files", file=sys.stderr)
        for path in conflicts:
            print(f"  - {relative_posix(path, root)}", file=sys.stderr)
        return 3
    for path, content in files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    print("Scaffold complete. Wire DI manually; implement Nav2-backed Navigator next.")
    return 0


# ---------------------------------------------------------------------------
# Check
# ---------------------------------------------------------------------------


def build_check(root: Path, spec: dict[str, Any] | None) -> dict[str, Any]:
    audit = build_audit(root)
    findings: list[dict[str, Any]] = []

    deps = audit["dependencies"]
    # Leftover Nav2 after intended migration: always report as findings for check
    for item in deps.get("navigation2") or []:
        findings.append(
            {
                "rule": "leftover-navigation2-dependency",
                "severity": "error",
                "path": item["path"],
                "marker": item["marker"],
                "message": "Navigation 2 dependency/marker still present",
            }
        )
    for src in audit.get("sources") or []:
        if src.get("nav2_imports"):
            findings.append(
                {
                    "rule": "leftover-navigation2-import",
                    "severity": "error",
                    "path": src["path"],
                    "imports": src["nav2_imports"][:20],
                    "message": "Navigation 2 imports still present",
                }
            )
        if src["features"].get("nav_host"):
            findings.append(
                {
                    "rule": "leftover-navhost",
                    "severity": "error",
                    "path": src["path"],
                    "message": "NavHost still present; cutover incomplete",
                }
            )
        if src["features"].get("remember_nav_controller"):
            findings.append(
                {
                    "rule": "leftover-remember-nav-controller",
                    "severity": "error",
                    "path": src["path"],
                    "message": "rememberNavController still present",
                }
            )
        for leak in src.get("controller_leaks") or []:
            findings.append(
                {
                    "rule": "nav-controller-leak",
                    "severity": "error",
                    "path": leak["path"],
                    "evidence": leak["evidence"],
                    "message": "NavController leak remains",
                }
            )
        for route in src.get("string_routes") or []:
            findings.append(
                {
                    "rule": "incomplete-route-conversion",
                    "severity": "error",
                    "path": src["path"],
                    "route": route,
                    "message": "String composable route still present",
                }
            )

    # Host registration: if no NavDisplay and no NavHost, warn
    hosts = audit.get("hosts") or []
    has_display = any(h.get("style") == "nav_display" for h in hosts)
    has_host = any(h.get("style") == "nav_host" for h in hosts)
    if not has_display and not has_host:
        findings.append(
            {
                "rule": "missing-host-registration",
                "severity": "warning",
                "message": "No NavHost or NavDisplay host detected",
            }
        )
    elif has_host and not has_display:
        findings.append(
            {
                "rule": "host-not-cut-over",
                "severity": "error",
                "message": "NavHost present without NavDisplay cutover",
            }
        )

    # Serialization / NavKey completeness when spec asks for it
    if spec:
        route_model = spec.get("route_model") or {}
        ser = route_model.get("serialization") or {}
        if ser.get("polymorphic_registration_required"):
            # look for SerializersModule / subclass registration near navigation
            found_reg = False
            for path in walk_files(root):
                if path.suffix != ".kt":
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
                if "SerializersModule" in text and ("subclass(" in text or "polymorphic(" in text):
                    found_reg = True
                    break
            if not found_reg:
                findings.append(
                    {
                        "rule": "missing-polymorphic-serializer-registration",
                        "severity": "error",
                        "message": "Polymorphic serializer registration not found but required by spec",
                    }
                )
        contract = route_model.get("contract_type")
        if contract and contract != "NavKey":
            # ensure NavKey appears on route base files when bases claimed
            bases = []
            if route_model.get("existing_base_type"):
                bases.append(route_model["existing_base_type"])
            for base in bases:
                bpath = base.get("path")
                if not bpath:
                    continue
                full = root / bpath
                if full.is_file():
                    text = full.read_text(encoding="utf-8", errors="replace")
                    if "NavKey" not in text and "@Serializable" not in text:
                        findings.append(
                            {
                                "rule": "missing-navkey-or-serializable",
                                "severity": "error",
                                "path": bpath,
                                "message": f"Route base {base.get('name')} lacks NavKey/@Serializable markers",
                            }
                        )

        # Fail if scaffold would have introduced Destination dependency incorrectly
        for path in walk_files(root):
            if path.suffix != ".kt":
                continue
            # only check generated recording / navigator mentions of ysn Destination package if any
            text = path.read_text(encoding="utf-8", errors="replace")
            if "com.ysn.core.navigation.Destination" in text and "migrate-to-navigation3" in text:
                findings.append(
                    {
                        "rule": "ysn-destination-dependency",
                        "severity": "error",
                        "path": relative_posix(path, root),
                        "message": "Generated navigation contract must not depend on YSN Destination",
                    }
                )

    unverified = []
    behavior = audit.get("behavior") or {}
    for key in (
        "deep_link_routing",
        "transient_results",
        "multiple_stacks",
        "dialogs",
        "process_death_restoration",
    ):
        # process_death always true in audit defaults — treat multi-stack/dialogs/results as needing manual verify
        if key == "process_death_restoration":
            unverified.append(
                {
                    "behavior": key,
                    "message": "Process-death restoration must be manually verified after cutover",
                }
            )
        elif behavior.get(key) or (spec and (spec.get("back_stack") or {}).get(key)):
            unverified.append(
                {
                    "behavior": key,
                    "message": f"Behavior '{key}' was observed or planned; confirm after cutover",
                }
            )

    gates = {
        "leftover_navigation2": "fail"
        if any(f["rule"].startswith("leftover-") for f in findings)
        else "pass",
        "controller_leaks": "fail"
        if any(f["rule"] == "nav-controller-leak" for f in findings)
        else "pass",
        "route_conversion": "fail"
        if any(f["rule"] == "incomplete-route-conversion" for f in findings)
        else "pass",
        "host_cutover": "fail"
        if any(f["rule"] in {"host-not-cut-over", "missing-host-registration"} for f in findings)
        else "pass",
        "serialization": "fail"
        if any(
            f["rule"] in {"missing-polymorphic-serializer-registration", "missing-navkey-or-serializable"}
            for f in findings
        )
        else "pass",
    }

    payload = envelope_fields(
        skill=SKILL,
        script=SCRIPT_NAME,
        script_version=SCRIPT_VERSION,
        repository_root=".",
        inputs={"spec": str(spec.get("generator")) if spec else None},
    )
    payload.update(
        {
            "findings": findings,
            "unverified_behavior": unverified,
            "gates": gates,
            "summary": {
                "error_count": sum(1 for f in findings if f.get("severity") == "error"),
                "warning_count": sum(1 for f in findings if f.get("severity") == "warning"),
                "passed": all(v == "pass" for v in gates.values()),
            },
            "observed": audit.get("observed") or {},
            "recommendations": [
                "Fix leftover Navigation 2 dependencies and imports.",
                "Remove NavController from ViewModels; use Navigator.",
                "Finish NavDisplay host cutover and route serialization.",
                "Manually verify deep links, results, dialogs, and multi-stack behavior.",
            ]
            if not all(v == "pass" for v in gates.values())
            else ["Navigation 3 check gates passed; still run app compile and UI verification."],
        }
    )
    return payload


def cmd_check(options: argparse.Namespace) -> int:
    root = options.root.resolve()
    if not root.is_dir():
        print(f"error: root is not a directory: {root}", file=sys.stderr)
        return 2
    spec = None
    if options.spec:
        try:
            spec = load_json(options.spec)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    payload = build_check(root, spec)
    errors = validate_artifact(payload, "navigation3-check")
    if errors:
        print("error: produced invalid navigation3-check artifact:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 2
    write_json(options.json_out, payload)
    summary = payload["summary"]
    print("Navigation 3 migration check")
    print(f"  errors: {summary['error_count']}  warnings: {summary['warning_count']}")
    print(f"  gates: {payload['gates']}")
    for finding in payload["findings"][:20]:
        print(f"    - [{finding.get('severity')}] {finding.get('rule')}: {finding.get('message')}")
    if options.json_out is None and not options.spec:
        pass
    passed = summary["passed"]
    if not passed:
        print("CHECK FAILED")
        return 1
    print("CHECK PASSED")
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    options = parse_args(argv)
    if options.command == "audit":
        return cmd_audit(options)
    if options.command == "plan":
        return cmd_plan(options)
    if options.command == "scaffold":
        return cmd_scaffold(options)
    if options.command == "check":
        return cmd_check(options)
    print(f"error: unknown command {options.command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
