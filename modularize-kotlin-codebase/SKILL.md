---
name: modularize-kotlin-codebase
description: Orchestrate an incremental modularization of an existing Kotlin/Gradle codebase into feature slices with domain, data, navigation, UI, and reusable test-support modules, plus core and cross-cutting utility modules. Use for monolith-to-modules migrations, architecture redesigns, dependency-boundary cleanup, KMP/Android/JVM module planning, convention-plugin extraction, or coordinating the sibling audit, Gradle-convention, feature-migration, and verification skills.
---

# Modularize Kotlin Codebase

Treat modularization as a behavior-preserving migration, not a directory reshuffle. Discover the target project’s actual frameworks and constraints, agree on boundaries, introduce reusable build conventions, migrate one vertical slice at a time, and keep the build green at every checkpoint.

## Required sibling skills

Use these sibling skills in order when they are installed:

1. `$audit-kotlin-architecture` — inventory sources, build configuration, dependencies, and candidate boundaries.
2. `$design-gradle-conventions` — extract repeated Gradle setup into project-specific convention plugins.
3. `$migrate-kotlin-feature` — scaffold and migrate one approved vertical slice.
4. `$verify-kotlin-modules` — enforce module shape, dependency direction, imports, and build checkpoints.

If a sibling is unavailable, follow the same phase in this skill and use its artifacts only when present. Do not invent findings that require repository inspection.

## Start by reading project rules

1. Find and read every applicable `AGENTS.md`, `CONTRIBUTING.md`, architecture document, and build guide before editing.
2. Inspect the working tree. Preserve unrelated changes.
3. Determine whether the project is Kotlin Multiplatform, Android-only, JVM, or mixed.
4. Identify the current UI, navigation, DI, networking, persistence, serialization, testing, code-generation, and resource systems from build files and imports.
5. Record constraints such as package naming, source sets, generated sources, app entry points, minimum SDKs, native targets, and CI tasks.

Do not replace working libraries merely to resemble a reference architecture. Map existing libraries to architectural capabilities.

## Migration contract

Preserve these invariants unless the user explicitly changes them:

- Runtime behavior, navigation routes, persistence schemas, serialization names, deep links, and public APIs remain stable.
- The app continues compiling after each migration batch.
- A domain layer contains policies, models, use cases, and ports; it does not know UI, database, HTTP, or framework implementation details.
- A data layer implements domain ports and owns DTOs, mappers, persistence, network, and cache implementations.
- A navigation layer owns route/destination contracts and graph wiring appropriate to the project’s navigation library.
- A UI layer owns presentation state, screens, controllers/ViewModels/presenters, resources, and UI-only formatters.
- A test-support module contains reusable fakes, fixtures, and test builders; it is never on a production runtime path.
- Cross-feature sharing moves only after a second real consumer appears or a stable product concept is clearly app-wide.

Read [references/architecture-blueprint.md](references/architecture-blueprint.md) before designing the target graph. Read [references/migration-playbook.md](references/migration-playbook.md) before making changes. Read [references/artifact-contract.md](references/artifact-contract.md) when creating or consuming `.modularization` artifacts.

## Phase 0: Establish a baseline

1. Capture the current build and test commands from CI and local documentation.
2. Run the smallest reliable baseline checks. Record pre-existing failures separately.
3. Create `.modularization/` only when the user has authorized repository changes; otherwise keep reports in a temporary directory.
4. Copy [assets/modularization.config.example.json](assets/modularization.config.example.json) to `.modularization/config.json` and adapt it after discovery. Never accept placeholders as real decisions.

Exit this phase with a known baseline and a list of commands that must remain green.

## Phase 1: Audit and propose boundaries

Invoke `$audit-kotlin-architecture`.

Require these outputs:

- source and build inventory;
- existing module graph;
- internal package/import coupling;
- library capability inventory;
- feature candidates with confidence and ambiguous files;
- proposed core, utility, and feature ownership;
- cycle and high-coupling hotspots;
- a migration plan ordered by dependency risk.

Review feature names against product language, not just package names. Prefer cohesive user capabilities such as `billing` or `profile` over technical buckets such as `screens` or `repositories`.

Do not proceed with ambiguous boundaries that would materially change the target design. Ask for user direction only after presenting the evidence and a recommended choice.

## Phase 2: Design convention plugins

Invoke `$design-gradle-conventions` after the audit is stable and before generating many modules.

Create a thin base plugin per platform family, then compose optional capabilities detected in the project:

- UI/resources;
- data/network/database;
- navigation;
- serialization;
- dependency injection/code generation;
- unit tests and reusable test fixtures;
- publishing/export/native frameworks when genuinely needed.

Keep app-only signing, secrets, distribution, environment files, and release automation separate from library conventions. Avoid a boolean-heavy universal plugin if independent capability plugins make module intent clearer. If the project already has a mature convention system, extend it rather than creating a parallel build.

Compile the build logic and migrate one existing low-risk module to prove it before scaffolding the full target graph.

## Phase 3: Prepare foundations

Introduce only foundations required by the first feature:

- `core:domain` for truly app-wide contracts and models;
- `core:data` for shared infrastructure rather than feature repositories;
- `core:navigation` for navigation abstractions and shared route contracts;
- `core:ui` for the design system and presentation foundations;
- `util:<capability>:domain` plus `real` and optional `ui` for independently reusable cross-cutting services.

Do not create empty speculative modules. Do not move feature-specific code into `core` as a shortcut.

## Phase 4: Migrate a pilot feature

Choose a feature that is real but bounded: enough data/UI/navigation behavior to exercise the pattern, without being the most coupled area.

Invoke `$migrate-kotlin-feature` and migrate dependency-first:

1. Domain contracts, models, and pure logic.
2. Test fakes/fixtures needed by domain consumers.
3. Data implementations and mappers.
4. Navigation contracts and adapters.
5. UI and presentation state.
6. DI registration, app aggregation, and entry-point wiring.
7. Old code deletion only after all references have moved and checks pass.

Use compatibility adapters when a single atomic move would be too risky. Make adapters temporary, named, and tracked in the plan.

## Phase 5: Repeat by vertical slice

After the pilot passes verification:

1. Update the plan with what was learned.
2. Migrate one feature at a time.
3. Run layer-local tests, dependent-module tests, and an app compile after each batch.
4. Re-run architecture checks after every feature.
5. Promote shared code only when evidence shows stable reuse.
6. Keep a remaining-files queue; every monolith file must be assigned, intentionally retained, or deleted.

Avoid horizontal big-bang moves such as extracting every model before any feature works end-to-end.

## Phase 6: Harden and finish

Invoke `$verify-kotlin-modules` for the full repository.

Completion requires:

- no forbidden module or source import edges;
- no dependency cycles;
- no production dependency on test-support modules;
- settings, app aggregation, DI, navigation, and generated-code registration are complete;
- feature-owned resources and platform source sets are in the correct module;
- all baseline checks pass or only documented pre-existing failures remain;
- no compatibility adapter, duplicate implementation, or stale monolith source remains untracked;
- architecture documentation and CI checks describe the new structure.

## Stop conditions

Stop and request direction when:

- product boundaries are genuinely ambiguous and choosing one changes public ownership;
- a move requires changing externally consumed APIs, database migrations, route identity, or serialization wire formats;
- build logic cannot be proven without adding or upgrading major dependencies;
- the only path forward requires destructive cleanup of unrelated user work.

Do not stop merely because the migration is large. Continue with the next safe vertical slice when scope authorizes the full migration.
