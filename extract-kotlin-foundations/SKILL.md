---
name: extract-kotlin-foundations
description: Extract shared foundations required by modular features — core domain/data/navigation/UI, util capability modules, app-shell contracts, and test foundations — from an architecture audit before the first feature migration. Use when preparing core modules, moving authentication into a utility, stopping feature code from accumulating in core, or extracting common test fixtures without dependency cycles.
---

# Extract Kotlin Foundations

Fill the gap between convention-plugin creation and the first feature migration.
Scaffold only foundations required by the pilot feature.

## Non-goals

- Migrating full product features (use `$migrate-kotlin-feature`).
- Creating empty or speculative core/util modules.
- Promoting code to core because of high fan-in alone.
- Solving cycles with catch-all `common` / `shared` / `core` dumping grounds.
- Putting test-support on production dependency paths.

## Workflow

1. Consume `.modularization/audit.json` and the accepted module plan.
2. Read [references/foundation-ownership.md](references/foundation-ownership.md),
   [references/utility-module-patterns.md](references/utility-module-patterns.md), and
   [references/test-foundation-patterns.md](references/test-foundation-patterns.md).
3. Plan:

   ```bash
   python3 scripts/plan_foundations.py \
     --root /path/to/repo \
     --audit .modularization/audit.json \
     --plan .modularization/plan.json \
     --pilot-feature orders \
     --json-out .modularization/foundation-plan.json
   ```

4. Review every candidate ownership label. Static classifications are **candidates**.
5. Adapt [assets/foundation-spec.example.json](assets/foundation-spec.example.json)
   for modules you will actually scaffold (non-empty only).
6. Preview and apply:

   ```bash
   python3 scripts/scaffold_foundations.py --root /path/to/repo --spec foundation-spec.json
   python3 scripts/scaffold_foundations.py --root /path/to/repo --spec foundation-spec.json --apply
   ```

7. Apply reviewed, hash-guarded moves with `$migrate-kotlin-feature` move manifests.
8. Compile each foundation and its direct consumers; run `$verify-kotlin-modules`.
9. Record receipts under `.modularization/receipts/` and ledger chunks.

## Ownership classes

| Class | Meaning |
|---|---|
| stable-app-wide-foundation | True `core:*` contracts used broadly and stable |
| independently-reusable-utility | `util:<capability>:domain/real/ui` |
| app-shell | Entry/wiring that stays in app modules |
| feature-owned | Stays in a feature even with temporary callers |
| feature-owned-shared-ui | Provider UI reused by other feature UIs |
| test-foundation | Reusable fakes/fixtures for test configurations |
| unresolved | Needs human source review |

## Completion

Foundations are ready when the pilot feature’s required modules exist, plan gates
pass, no empty modules were created, production→test edges are absent, and
verification compiles the new graph.
