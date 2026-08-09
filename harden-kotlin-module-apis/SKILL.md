---
name: harden-kotlin-module-apis
description: Reduce accidental public Kotlin surface and align source visibility with Gradle dependency visibility. Use when replacing unjustified api(project) edges, making implementation classes internal, preventing DTO leakage through domain APIs, narrowing surface before framework extraction, or reviewing what downstream modules actually consume. Static analysis produces review candidates only.
---

# Harden Kotlin Module APIs

Align `api` vs `implementation` and `public` vs `internal` with real contracts.

## Non-goals

- Automatically rewriting visibility without review.
- Removing justified aggregation facades that re-export owned children.
- Broad ProGuard keep rules as a substitute for narrow APIs.

## Workflow

1. Audit:

   ```bash
   python3 scripts/audit_module_apis.py \
     --root /path/to/repo \
     --json-out .modularization/api-surface-report.json
   ```

2. Read [references/kotlin-api-boundaries.md](references/kotlin-api-boundaries.md)
   and [references/dependency-visibility.md](references/dependency-visibility.md).
3. Plan with optional rules from
   [assets/api-surface-rules.example.json](assets/api-surface-rules.example.json):

   ```bash
   python3 scripts/plan_dependency_visibility.py \
     --audit .modularization/api-surface-report.json \
     --json-out .modularization/api-hardening-plan.json
   ```

4. Change **one module at a time**:
   - `api` → `implementation` when no public signature needs the type
   - `public` → `internal` for implementation details
   - move interfaces into domain contracts
   - introduce mappers around wire/persistence DTOs
   - hide non-Swift APIs from the native export surface
5. Compile all known consumers; run `$verify-kotlin-modules`.
6. For KMP Apple frameworks, run `$audit-kotlin-native-framework`.

## Completion

Unjustified `api` edges are gone or allow-listed with reasons, public
implementations are internal, DTO leakage is addressed, and verification agrees
with the hardening plan.
