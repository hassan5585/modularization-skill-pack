---
name: audit-kotlin-architecture
description: Inspect an Android, Kotlin Multiplatform, JVM, or mixed Kotlin/Gradle repository and produce an evidence-backed inventory and modularization plan. Use before splitting a monolith, choosing feature boundaries, mapping files into domain/data/navigation/UI/test layers, identifying core or utility candidates, finding dependency cycles and hotspots, or determining which existing libraries and build capabilities must be preserved.
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
5. Copy [assets/audit-overrides.example.json](assets/audit-overrides.example.json), replace all placeholders, and provide it to the planner when package-derived feature names are insufficient.
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

Classify each owned production file as `domain`, `data`, `navigation`, `ui`, `platform`, `di`, `test`, or `unknown`. Explain ambiguous cases. `di` usually follows the implementation it wires or lives in the feature aggregation module; do not create a separate DI layer by reflex.

### Shared-code decisions

Use:

- `core:*` for stable app-wide foundations used broadly;
- `util:<capability>:domain/real/ui` for an independently reusable cross-cutting service;
- feature modules for feature-specific code, even if another feature temporarily calls it;
- a shared feature contract module only when direct feature integration is intentional and stable.

Do not infer `core` merely from high fan-in; inspect semantics and volatility.

## Quality gates

Before accepting the plan:

- Account for every source file or explicitly mark it excluded/generated/unknown.
- List existing and proposed module cycles.
- Identify files with multiple feature candidates.
- Separate observed facts from inferred ownership.
- Include a pilot feature, dependency-first migration order, and verification commands.
- Flag route identity, serialization, database, platform, and generated-code risks.
- Ensure the target plan uses libraries already present unless a gap is proven.

The audit is complete only when another agent can start one feature migration without rediscovering the repository.
