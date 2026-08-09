---
name: extract-kmp-platform-boundaries
description: Separate portable common Kotlin code from Android, iOS, JVM, and native implementation details using injected interfaces, expect/actual, or platform entry points. Use when Android APIs appear in commonMain, choosing expect/actual versus DI interfaces, extracting platform services into util modules, cleaning iOS interop before modularizing, or fixing platform source-set ownership.
---

# Extract KMP Platform Boundaries

Keep portable layers free of platform imports; place implementations in matching
source sets or utility modules.

## Non-goals

- Rewriting business architecture unrelated to platform leakage.
- Preferring expect/actual for every service (interfaces are often better).
- Leaving expect declarations without actuals.

## Workflow

1. Audit:

   ```bash
   python3 scripts/audit_source_set_boundaries.py \
     --root /path/to/repo \
     --json-out .modularization/platform-boundary-audit.json
   ```

2. Read [references/source-set-ownership.md](references/source-set-ownership.md),
   [references/expect-actual-vs-interface.md](references/expect-actual-vs-interface.md),
   and [references/native-interop-boundaries.md](references/native-interop-boundaries.md).
3. Plan:

   ```bash
   python3 scripts/plan_platform_extraction.py \
     --audit .modularization/platform-boundary-audit.json \
     --json-out .modularization/platform-boundary-plan.json
   ```

4. Create common contracts before moving implementations.
5. Move Android and iOS code in matching batches; wire with existing DI.
6. Compile common metadata and each affected platform.
7. When public/native declarations change, run `$audit-kotlin-native-framework`.

## Boundary choices

| Kind | Prefer |
|---|---|
| Replaceable / business-facing service | Injected interface |
| Narrow primitive, identical semantics | expect/actual |
| Lifecycle / OS integration | Platform entry-point module |

## Completion

Portable source sets have no platform imports, expect/actual pairs match,
Android and iOS verification commands appear in the matrix, and native audits
pass when applicable.
