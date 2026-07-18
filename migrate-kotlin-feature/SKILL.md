---
name: migrate-kotlin-feature
description: Incrementally extract one vertical product feature from a Kotlin/Gradle monolith into an aggregation module plus domain, data, navigation, UI, and reusable test-support modules while preserving the project’s existing UI, DI, networking, persistence, navigation, serialization, and testing libraries. Use for pilot feature extraction, repeated feature-by-feature migration, source moves, package rewrites, module registration, dependency rewiring, or compatibility-adapter removal.
---

# Migrate Kotlin Feature

Migrate exactly one approved feature slice at a time. Keep behavior stable and the build green after each dependency-first batch.

## Inputs

Require or derive:

- an approved feature name and product responsibility;
- owned source files and ambiguous-file decisions;
- current and target package prefixes;
- platform family and source sets;
- existing convention plugin IDs or explicit Gradle configuration;
- required core/utility dependencies;
- app, DI, navigation, resource, generated-code, and test registration points;
- baseline and layer-local verification commands.

Read [references/feature-migration-procedure.md](references/feature-migration-procedure.md) before moving code. Use [assets/feature-spec.example.json](assets/feature-spec.example.json) for feature scaffolding, [assets/test-foundations-spec.example.json](assets/test-foundations-spec.example.json) for repository-wide test foundations when required, and [assets/move-manifest.example.json](assets/move-manifest.example.json) for controlled moves.

If repository-independent helpers or core-contract fakes already have multiple consumers, scaffold their explicit modules before feature migration:

```bash
python3 scripts/scaffold_test_foundations.py --root /path/to/repo --spec /path/to/test-foundations.json
python3 scripts/scaffold_test_foundations.py --root /path/to/repo --spec /path/to/test-foundations.json --apply
```

Register these modules in settings and consume them only from test source sets/configurations. Do not add them to an app, feature aggregation root, DI graph, or production source set.

## Scaffold the target shape

Preview:

```bash
python3 scripts/scaffold_feature.py --root /path/to/repo --spec /path/to/feature-spec.json
```

Review every build file and dependency, then apply:

```bash
python3 scripts/scaffold_feature.py --root /path/to/repo --spec /path/to/feature-spec.json --apply
```

The script creates module build files and source roots but does not edit `settings.gradle*`, app aggregation, DI, or navigation. Apply those edits deliberately because their syntax is project-specific. Put feature test-support dependencies in each layer’s `test_dependencies`; the scaffold renders them into `commonTest` for KMP or expects explicit `testImplementation`-style expressions for Android/JVM.

## Migration order

### 1. Domain

Move pure models, repository/service interfaces, use cases, policies, events, and errors. Keep transport DTOs, database entities, UI state, framework controllers, and navigation runtime types out unless the project’s public contract truly requires them.

Compile and run domain tests before continuing.

### 2. Test support

Move reusable fakes, fixtures, recording navigators, test builders, and deterministic clocks/dispatchers used by multiple tests. Keep actual test cases in the module that owns the production behavior. Ensure the test-support dependency graph remains below all consumers.

### 3. Data

Move repository implementations, API clients, DTOs, mappers, database entities/DAOs, caches, preferences, and platform data adapters. Bind implementations to domain ports using the project’s existing DI mechanism.

Preserve wire names, table/schema identifiers, migration files, cache keys, and error semantics.

### 4. Navigation

Move route/destination contracts, argument types allowed by the existing navigation library, deep-link handlers, result contracts, and feature graph declarations as appropriate.

Preserve stable route IDs, deep-link URLs, argument serialization, back-stack behavior, and external entry points.

### 5. UI

Move screens, UI state, ViewModels/presenters/controllers, resources, UI models, formatters, and UI-only widgets. Keep business decisions in domain/presentation logic according to the target project’s existing architecture.

Move resources with their owning UI. Check generated resource packages and imports.

### 6. Aggregation and app wiring

Register modules in settings, app dependencies, DI graph, navigation graph, deep links, serialization registries, generated-code configuration, and platform entry points. Keep the root aggregation module thin.

### 7. Remove the old path

Delete old sources only after references resolve from new modules and verification passes. Remove temporary adapters when all consumers have migrated.

## Controlled source moves

Generate a reviewed manifest from the approved plan. Preview it:

```bash
python3 scripts/apply_move_manifest.py --root /path/to/repo --manifest /path/to/moves.json
```

Apply it only after all collisions and package changes are reviewed:

```bash
python3 scripts/apply_move_manifest.py --root /path/to/repo --manifest /path/to/moves.json --apply
```

For an approved move batch, calculate and add each source file’s lowercase SHA-256 as `expected_sha256`, then apply with `--require-hashes` and a repository-local receipt:

```bash
python3 scripts/apply_move_manifest.py \
  --root /path/to/repo \
  --manifest /path/to/moves.json \
  --require-hashes \
  --receipt-out .modularization/receipts/orders-domain-01.json \
  --apply
```

Record the receipt in the active work-ledger chunk. Hash preconditions prevent a reviewed manifest from moving a source that changed after review.

The script changes only explicit `package` declarations. Update imports and fully qualified references using repository-aware searches and compiler feedback. Never run broad global replacement across generated, vendored, migration, or serialized data.

## Dependency rules

Target the following default direction, adapting only with documented project evidence:

```text
feature root -> data + domain + navigation + ui
ui           -> domain + navigation + core/ui + approved utility contracts
data         -> domain + core/data + approved utility contracts/implementations
navigation   -> domain + core/navigation
domain       -> core/domain + pure utility contracts
tests        -> owning module + test-support
```

Production modules must not depend on test-support. Domain must not depend on data, navigation UI, UI, database, HTTP, or platform UI frameworks.

## Checkpoints

After each batch:

1. Check moved packages and imports with `rg`.
2. Compile the changed module.
3. Run its unit tests.
4. Compile direct dependents.
5. Run architecture verification.
6. Compile the app or relevant deliverable.
7. Record new failures separately from the baseline.

The feature is complete only when no source, resource, registration, fixture, or behavior belonging to it remains accidentally in the monolith and all temporary adapters are removed or explicitly tracked.
