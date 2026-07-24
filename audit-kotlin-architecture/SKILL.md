---
name: audit-kotlin-architecture
description: Inspect an Android, Kotlin Multiplatform, JVM, or mixed Kotlin/Gradle repository and produce an evidence-backed inventory and modularization plan. Use before splitting a monolith, choosing feature boundaries, mapping files into domain/data/navigation/UI/optional shared-UI/test layers, identifying core or utility candidates, finding dependency cycles and hotspots, or determining which existing libraries and build capabilities must be preserved.
---

# Audit Kotlin Architecture

Build an evidence-backed model of the codebase before proposing moves. Treat script classifications as candidates requiring source review, not as architectural truth.

## Workflow

1. Read applicable repository instructions and architecture/build documentation.
2. Inspect `settings.gradle*`, root and module build files, version catalogs, build-logic/included builds, CI files, and source-set layout.
3. Run the inventory script without modifying production files:

   ```bash
   python3 scripts/audit_codebase.py \
     --root /path/to/repo \
     --json-out /path/to/repo/.modularization/audit.json \
     --markdown-out /path/to/repo/.modularization/audit.md
   ```

   Add `--root-package com.example` when automatic package inference is wrong. Add repeated `--exclude path` options for generated or vendored trees not covered by defaults.

4. Read [references/classification-heuristics.md](references/classification-heuristics.md), then inspect every low-confidence or unknown classification and every high-coupling candidate.
   Package-only candidates outside an existing `feature/*` graph remain unresolved until reviewed; this prevents app-shell helpers from silently becoming fake product features.
5. Copy [assets/audit-overrides.example.json](assets/audit-overrides.example.json), replace all placeholders, and provide it to the planner when package-derived feature names are insufficient. Leave `target_feature_layers` empty to derive only evidenced/existing layers; fill it only after approving a uniform feature shape. Use a feature’s `target_layers` for an optional `shared-ui`; do not add it to every feature. Record reviewed `shared_ui_dependencies` so provider shared UI migrates before consumer UI. Leave `shared_test_modules` and `foundation_modules` empty unless the audit proves those shared targets are required; existing top-level test-support modules are retained automatically when no override is supplied.
6. Generate a proposed module plan:

   ```bash
   python3 scripts/plan_modules.py \
     --audit .modularization/audit.json \
     --overrides .modularization/audit-overrides.json \
     --json-out .modularization/plan.json \
     --markdown-out .modularization/plan.md
   ```

7. Compare the proposed features with product vocabulary, navigation landmarks, API ownership, persistence ownership, and team ownership.
8. Report evidence, assumptions, confidence, unresolved decisions, cycles, and a recommended pilot feature.

## Required analysis

### Build and platform

Determine:

- Gradle DSL and wrapper version;
- Kotlin/AGP/KMP/Compose or other UI plugins;
- Android, JVM, native, and KMP targets;
- version catalogs and included build logic;
- source sets, generated sources, resources, manifests, schemas, and native interop;
- CI build, lint, test, code-generation, and packaging tasks.

### Library capabilities

Map concrete libraries to roles:

- UI toolkit and resources;
- navigation;
- DI/code generation;
- networking and serialization;
- persistence and preferences;
- async/reactive primitives;
- testing and fixtures;
- platform services.

Preserve the detected choices. Recommend replacement only when the user requests it or the current library prevents the target boundary.

### Feature boundaries

Use multiple signals:

- product nouns and navigation entry points;
- route or destination groups;
- API endpoints and repositories;
- database tables/DAOs and persistence ownership;
- package cohesion and import density;
- UI flows and state holders;
- DI scopes and registrations;
- tests and fixtures;
- team/domain ownership.

Reject boundaries based only on technical type (`screens`, `models`, `repositories`).

### Layer classification

Classify each owned production file as `domain`, `data`, `navigation`,
`shared-ui`, `ui`, `platform`, `di`, `test`, or `unknown`. Explain ambiguous
cases. Assign `shared-ui` only when a module already owns the file or reviewed
consumer evidence proves feature-owned UI reuse; UI-looking code alone remains
`ui`. `di` usually follows the implementation it wires or lives in the feature
aggregation module; do not create a separate DI layer by reflex.

### Shared-code decisions

Use:

- `core:*` for stable app-wide foundations used broadly;
- `util:<capability>:domain/real/ui` for an independently reusable cross-cutting service;
- feature modules for feature-specific code, even if another feature temporarily calls it;
- an optional provider-owned feature `shared-ui` when another feature UI needs a stable reusable surface;
- a shared feature contract module only when direct feature integration is intentional and stable.

Do not infer `core` merely from high fan-in; inspect semantics and volatility.
Do not plan `shared-ui -> shared-ui` edges. Compose multiple providers in the
consumer UI or promote a truly generic primitive to core UI.

## Quality gates

Before accepting the plan:

- Account for every source file or explicitly mark it excluded/generated/unknown.
- Account separately for every detected manifest, UI/resource file, database/network/serialization schema, shrinker rule, and native interop/platform source artifact.
- Confirm the plan’s source-accounting total equals the audit source count across feature, shared, retained, and unresolved assignments.
- List existing and proposed module cycles.
- List every shared-UI provider/consumer edge and order provider migration before consumer UI.
- Require `plan_acceptance.shared_ui_graph` to be `pass`; review every
  `shared_ui_violations` entry and reject shared-UI chains, unsupported
  consumers, foreign contracts, and lower-layer dependencies on shared UI.
- Identify files with multiple feature candidates.
- Separate observed facts from inferred ownership.
- Include a pilot feature, dependency-first migration order, and verification commands.
- Flag route identity, serialization, database, platform, and generated-code risks.
- Ensure the target plan uses libraries already present unless a gap is proven.

The audit is complete only when another agent can start one feature migration without rediscovering the repository.
