---
name: migrate-kotlin-data-boundaries
description: Audit and migrate Kotlin repository contracts, implementations, request/response DTOs, serializers, mappers, HTTP clients, caches, and shared wire models between feature and core data modules without changing runtime or wire behavior. Use when extracting a feature data layer, removing DTO leakage from domain APIs, deciding whether a data model is feature-owned or genuinely shared, or moving networking/caching code while preserving serialization names and endpoints.
---

# Migrate Kotlin Data Boundaries

Move data ownership without changing HTTP, serialization, mapping, caching, or
repository behavior. Delegate persistence schemas to the persistence skill.

## Workflow

1. Read repository data conventions and
   [references/data-ownership.md](references/data-ownership.md).
2. Copy [assets/data-boundary-rules.example.json](assets/data-boundary-rules.example.json)
   and record the target feature and reviewed shared-model exceptions.
3. Audit and plan:

   ```bash
   python3 scripts/analyze_data_boundaries.py audit --root /path/to/repo \
     --rules data-boundary-rules.json \
     --json-out .modularization/data-boundary-audit.json
   python3 scripts/analyze_data_boundaries.py plan --root /path/to/repo \
     --audit .modularization/data-boundary-audit.json \
     --rules data-boundary-rules.json \
     --json-out .modularization/data-boundary-plan.json
   ```

4. Review ownership and wire-contract snapshots. Keep repository interfaces in
   domain and implementations, DTOs, mappers, HTTP, and caches in data.
5. Move contracts before implementations with reviewed hash-guarded manifests.
6. Preserve endpoint construction, serial names, defaults, nullability,
   polymorphic registrations, error mapping, cache keys, and invalidation.
7. Run serialization/mapper/repository tests, compile consumers, then run
   `$harden-kotlin-module-apis` and `$verify-kotlin-modules`.

## Guardrails

- Do not expose response/request/entity classes through domain contracts.
- Do not promote a wire model to core from fan-in alone.
- Do not combine a database schema change with an ownership-only move.
- Stop if a move requires a wire-format or public contract change.

## Completion

Complete when every component has reviewed ownership, preserved wire snapshots
match, repository consumers compile, and no data implementation leaks upward.
