---
name: modularize-kotlin-codebase
description: Orchestrate an incremental modularization of an existing Kotlin/Gradle codebase into feature slices with domain, data, navigation, UI, optional provider-owned shared-UI, and reusable test-support modules, plus core and cross-cutting utility modules. Use for monolith-to-modules migrations, architecture redesigns, shared-UI dependency design, dependency/public-API cleanup, KMP native-framework boundary planning, convention-plugin extraction, or coordinating the sibling audit, Gradle-convention, feature-migration, native-framework, and verification skills.
---

# Modularize Kotlin Codebase

Treat modularization as a behavior-preserving migration, not a directory reshuffle. Discover the target project’s actual frameworks and constraints, agree on boundaries, introduce reusable build conventions, migrate one vertical slice at a time, and keep the build green at every checkpoint. Persist progress so another agent can resume without rediscovering completed work.

## Required sibling skills

Use these sibling skills in order when they are installed:

1. `$audit-kotlin-architecture` — inventory sources, build configuration, dependencies, and candidate boundaries.
2. `$design-gradle-conventions` — extract repeated Gradle setup into project-specific convention plugins.
3. `$migrate-kotlin-feature` — scaffold and migrate one approved vertical slice.
4. `$verify-kotlin-modules` — enforce module shape, dependency direction, imports, and build checkpoints.
5. `$audit-kotlin-native-framework` — for KMP Apple frameworks, enforce a narrow Swift-facing header and native build configuration.

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
- An optional feature `shared-ui` owns provider-specific UI reused by feature UI modules. It uses normal UI internals, sits below consumers, and never depends on another shared-UI module.
- A test-support module contains reusable fakes, fixtures, and test builders; it is never on a production runtime path.
- Cross-feature sharing moves only after a second real consumer appears or a stable product concept is clearly app-wide.
- Leaf dependencies default to `implementation`; every `api` edge represents a reviewed public Kotlin contract. An optional feature aggregation root may re-export its own production children only when it is the documented app-facing Kotlin facade.
- An application’s Kotlin/Native framework keeps one narrow app-owned Swift bridge and does not export implementation dependency modules.

Read [references/architecture-blueprint.md](references/architecture-blueprint.md) before designing the target graph. Read [references/migration-playbook.md](references/migration-playbook.md) before making changes. Read [references/chunk-tracking.md](references/chunk-tracking.md) before the first repository edit. Read [references/artifact-contract.md](references/artifact-contract.md) when creating or consuming `.modularization` artifacts.

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

Do not begin structural edits until every production/test source is assigned to a feature, core/utility/app-shell target, intentionally retained, generated/excluded, or listed in the unresolved queue with an owner.

After the plan is reviewed, require its shared-UI graph gate to pass, then
initialize `.modularization/work-state.json` and `.modularization/worklog.md`
with `scripts/track_modularization.py init --plan ... --config ...`. The tracker
refuses a failed gate or nonempty `shared_ui_violations`. Keep these files in
the target repository. Review the generated dependency graph and add/split
chunks before the first structural edit.

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

Compile the build logic and migrate one existing low-risk module to prove it before scaffolding the full target graph. Record the representative module, its before/after plugins, targets/source sets, dependencies, generated outputs, resources, and test tasks. Convention creation is not complete while new modules still copy raw platform configuration instead of applying the approved convention plugins.

For native framework output, keep export behavior out of ordinary KMP/feature conventions. Never make `api`, dependency export, transitive export, or `-Xdisable-phases` the default path to Swift visibility. Establish the intended bridge and generated-header baseline with `$audit-kotlin-native-framework`.

## Phase 3: Prepare foundations

Introduce only foundations required by the first feature:

- `core:domain` for truly app-wide contracts and models;
- `core:data` for shared infrastructure rather than feature repositories;
- `core:navigation` for navigation abstractions and shared route contracts;
- `core:ui` for the design system and presentation foundations;
- `feature:<name>:shared-ui` only for reviewed feature-owned reuse; keep generic design-system primitives in `core:ui`;
- `util:<capability>:domain` plus `real` and optional `ui` for independently reusable cross-cutting services.
- a repository-wide test-foundation module for production-independent helpers, plus a downstream-safe core-contract fake module when multiple features need it;
- feature/utility `test` support modules only when fakes or fixtures have multiple owning-test consumers and the dependency direction is acyclic.

Do not create empty speculative modules. Do not move feature-specific code into `core` as a shortcut.

## Phase 4: Migrate a pilot feature

Choose a feature that is real but bounded: enough data/UI/navigation behavior to exercise the pattern, without being the most coupled area.

Invoke `$migrate-kotlin-feature` and migrate dependency-first:

1. Domain contracts, models, and pure logic.
2. Test fakes/fixtures needed by domain consumers.
3. Data implementations and mappers.
4. Navigation contracts and adapters.
5. Optional provider-owned shared UI, verified before every consuming feature UI.
6. UI and presentation state.
7. DI registration, app aggregation, and entry-point wiring.
8. Old code deletion only after all references have moved and checks pass.

For KMP Apple-framework projects, audit an existing framework after any batch that changes public declarations, dependency visibility, native interop, or app-shell wiring. Generate a debug device framework only when the current artifact is stale.

Before each numbered batch, start its ledger chunk. After the batch, record exact command results, changed paths, decisions, risks, and adapters, then complete the chunk. Keep only one chunk `in_progress`.

Use compatibility adapters when a single atomic move would be too risky. Make adapters temporary, named, and tracked in the plan.

## Phase 5: Repeat by vertical slice

After the pilot passes verification:

1. Update the plan with what was learned.
2. Migrate one feature at a time.
3. Run layer-local tests, dependent-module tests, and an app compile after each batch.
4. Re-run architecture checks after every feature.
5. Promote shared code only when evidence shows stable reuse.
6. Keep shared-UI provider chunks before consumer UI chunks; never create shared-UI chains.
7. Keep a remaining-files queue; every monolith file must be assigned, intentionally retained, or deleted.
8. Resume from the ledger rather than repeating completed discovery or moves. Revalidate the repository head and dirty baseline before resuming a blocked or interrupted chunk.

Avoid horizontal big-bang moves such as extracting every model before any feature works end-to-end.

## Phase 6: Harden and finish

Invoke `$verify-kotlin-modules` for the full repository.

Completion requires:

- no forbidden module or source import edges;
- no shared-UI-to-shared-UI or shared-UI-to-feature-UI edges;
- no dependency cycles;
- no production dependency on test-support modules;
- settings, app aggregation, DI, navigation, and generated-code registration are complete;
- feature-owned resources and platform source sets are in the correct module;
- all baseline checks pass or only documented pre-existing failures remain;
- no compatibility adapter, duplicate implementation, or stale monolith source remains untracked;
- architecture documentation and CI checks describe the new structure.
- all `api` project edges are explicitly justified and the configured dependency-visibility check is clean;
- KMP Apple-framework projects pass the configured native build/static rules and generated-header audit without disabled optimization phases;
- every completed work chunk has verification evidence or a specific reason no executable check exists;
- no required convention-plugin or testing-foundation chunk was skipped merely because hand-written Gradle configuration compiled;
- `.modularization/work-state.json` validates and has no open temporary adapter at final completion.

## Mandatory chunk protocol

Use `scripts/track_modularization.py`; do not maintain progress only in conversation or an ad hoc checklist.

```bash
python3 scripts/track_modularization.py --root /path/to/repo init \
  --plan /path/to/repo/.modularization/plan.json \
  --config /path/to/repo/.modularization/config.json

python3 scripts/track_modularization.py --root /path/to/repo start --chunk conventions

# Run the reviewed build command separately, then record its exact result.
python3 scripts/track_modularization.py --root /path/to/repo record-check \
  --chunk conventions \
  --argv-json '["./gradlew","-p","build-logic","build"]' \
  --exit-code 0 \
  --summary "Included build compiled successfully."

python3 scripts/track_modularization.py --root /path/to/repo complete \
  --chunk conventions \
  --note "Created the approved base/capability plugins and converted the representative module."
```

The tracker records results; it intentionally does not execute shell commands or commit changes. Stage or commit chunks only when the user authorizes Git writes. Never mark a chunk complete with an introduced required-check failure.

## Stop conditions

Stop and request direction when:

- product boundaries are genuinely ambiguous and choosing one changes public ownership;
- a move requires changing externally consumed APIs, database migrations, route identity, or serialization wire formats;
- build logic cannot be proven without adding or upgrading major dependencies;
- the only path forward requires destructive cleanup of unrelated user work.

Do not stop merely because the migration is large. Continue with the next safe vertical slice when scope authorizes the full migration.
