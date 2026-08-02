---
name: design-gradle-conventions
description: Analyze repeated Gradle configuration and create or refine project-specific convention plugins for Kotlin Multiplatform, Android, JVM, feature-layer, core, utility, and test-support modules. Use when extracting build logic from duplicated build.gradle(.kts) files, defining plugins applied to domain/data/navigation/UI/optional shared-UI/test modules, adopting an included build or build-logic project, preserving narrow dependency visibility/native framework exports, or making new modularized modules reuse the target codebase’s existing libraries and versions.
---

# Design Gradle Conventions

Extract conventions from the target repository’s real build behavior. Keep module build files declarative and readable while avoiding a universal plugin that silently applies every library everywhere.

## Discover repetition

1. Read repository build rules and inspect existing `buildSrc`, `build-logic`, included builds, root plugin declarations, version catalogs, and representative modules.
2. Run:

   ```bash
   python3 scripts/analyze_gradle_conventions.py \
     --root /path/to/repo \
     --json-out /path/to/repo/.modularization/gradle-audit.json \
     --markdown-out /path/to/repo/.modularization/gradle-audit.md
   ```

3. Review clusters by platform and role. Ignore generated, sample, benchmark, and vendored builds unless they are in scope.
4. Read [references/convention-plugin-patterns.md](references/convention-plugin-patterns.md) before choosing plugin boundaries.

## Design plugin layers

Prefer three strata:

1. **Platform base** — Kotlin/JVM, Android library/application, or KMP targets; toolchains; source sets; compiler options; namespaces; baseline tests.
2. **Capabilities** — UI/resources, data, navigation, serialization, DI/code generation, test fixtures, publishing/export.
3. **App/release** — application ID, signing, environments, distribution, crash reporting, packaging. Keep this separate from reusable libraries.

A module should advertise what it is and which exceptional capabilities it needs. Use either:

- composable plugin IDs such as `example.kotlin.multiplatform`, `example.ui`, and `example.serialization`; or
- one base plugin plus a small typed extension whose flags map one-to-one to independent capabilities.

Prefer separate plugins when capabilities have independent consumers or expensive side effects. Prefer a typed extension when nearly every module uses the same base and combinations are stable.

Default dependencies added by conventions and leaf-module scaffolds to `implementation`. Permit `api` only for a reviewed public Kotlin signature that exposes the dependency type. An optional aggregation root may explicitly re-export its own production children when its documented purpose is an app-facing Kotlin facade; keep that policy out of the base convention and record the exact allowed edges.

For KMP Apple frameworks, keep framework creation separate from ordinary KMP library setup. Do not make dependency export, transitive export, or disabled compiler phases a base-plugin default. Application frameworks should expose an app-owned Swift bridge; use `$audit-kotlin-native-framework` to establish and verify its generated-header baseline.

## Preserve the target stack

Derive plugin artifacts and dependency aliases from the target’s version catalog and root plugin declarations. Do not hardcode the reference project’s Compose, Metro, Ktor, Room, Navigation, or test stack.

For each capability, document:

- plugin IDs it applies;
- extensions/tasks it configures;
- dependencies it adds and to which source set/configuration;
- generated code or resources it enables;
- platform-specific behavior;
- whether it is safe for domain modules;
- verification task.

## Scaffold an included build

Copy [assets/build-logic-spec.example.json](assets/build-logic-spec.example.json), replace all placeholders, and list only plugins justified by the audit. Preview first:

```bash
python3 scripts/scaffold_build_logic.py --root /path/to/repo --spec /path/to/spec.json
```

Apply only after reviewing paths and plugin IDs:

```bash
python3 scripts/scaffold_build_logic.py --root /path/to/repo --spec /path/to/spec.json --apply
```

The scaffold is intentionally thin. Complete typed Gradle configuration by adapting verified snippets from the target build. Supply compile-time plugin artifacts and Kotlin imports in the spec when implementation classes reference AGP, Kotlin, Compose, KSP, Room, or other plugin types. List at least one representative module and its exact proof commands in the spec.

## Integrate safely

1. Add `includeBuild(...)` under `pluginManagement` without disturbing repository declarations.
2. Add convention plugin aliases to the existing version catalog when that is the project norm.
3. Compile the included build alone.
4. Convert one low-risk module.
5. Compare its task graph, variants/targets, dependencies, compiler flags, resources, generated sources, and tests before and after.
6. Convert the pilot feature modules.
7. Remove duplicated configuration only after the convention proves equivalent.

Do not call convention design complete after merely generating plugin classes. The included build must be registered, compile, and be applied by the representative module. Encode approved per-role plugin IDs in the architecture rules so later raw-module configuration or missing convention use fails verification.

## Rules by layer

- **Domain:** apply only language, serialization if domain contracts require it, DI annotations/compiler only if unavoidable, and unit-test foundations. Never add UI, database, network client, Android framework, or app plugins by default.
- **Data:** add the project’s network/persistence/serialization/code-generation capabilities, but not UI or navigation UI.
- **Navigation:** add only route serialization and the detected navigation contracts/runtime required for declarations.
- **UI:** add the detected UI toolkit, resource pipeline, lifecycle/presentation, navigation UI, previews, and UI tests when used.
- **Shared UI:** reuse the regular UI convention and capabilities. Treat `shared-ui` as a dependency role, not a reason to create a second UI convention plugin.
- **Test support:** add test libraries and downstream-safe contracts; never make production aggregators depend on it.
- **Owning-module tests:** configure the project’s real unit-test source sets/tasks and portable base libraries, then attach required tests to the normal verification lifecycle. Keep this distinct from the test-support library convention.
- **Aggregation root:** expose or implement child modules and register DI/entry points; avoid owning feature behavior.

## Validation

Require:

- included-build compilation;
- plugin application to representative KMP/Android/JVM modules in scope;
- no version duplication outside the catalog unless documented;
- no test-support leak into production runtime;
- no domain pollution from UI/data capabilities;
- no unreviewed `api` project edges, dependency exports, transitive native export, or permanent `-Xdisable-phases` flags;
- a generated-header audit for every framework-producing representative module in scope;
- stable source sets, targets, resource visibility, code generation, and test tasks;
- clear failures when a required alias or plugin artifact is missing.

Do not mass-convert modules until the representative module and pilot feature pass.
