---
name: break-kotlin-module-cycles
description: Find and safely remediate Gradle build-graph and source-import dependency cycles between Kotlin modules. Use when features depend on each other, a project cycle blocks migration, UI and data form a cycle, or you need the best edge to cut before extracting a feature. Scripts report and plan only; they never invent abstractions autonomously.
---

# Break Kotlin Module Cycles

Detect strongly connected components in the build graph and source-import graph,
explain them with file evidence, and produce a **reviewed** cut plan.

## Non-goals

- Autonomously creating event buses, catch-all cores, or shared-UI chains.
- Applying multi-edge rewrites without compilation checkpoints.
- Treating test-only edges as production architecture failures without review.

## Workflow

1. Detect:

   ```bash
   python3 scripts/detect_module_cycles.py \
     --root /path/to/repo \
     --json-out .modularization/cycle-report.json
   ```

2. Read [references/cycle-breaking-patterns.md](references/cycle-breaking-patterns.md)
   and [references/edge-selection-heuristics.md](references/edge-selection-heuristics.md).
3. Plan cuts (optional rules from [assets/cycle-rules.example.json](assets/cycle-rules.example.json)):

   ```bash
   python3 scripts/plan_cycle_breaks.py \
     --report .modularization/cycle-report.json \
     --json-out .modularization/cycle-break-plan.json
   ```

4. Review candidate edges and choose a pattern: dependency inversion, domain
   contract, event contract, navigation contract, app-shell orchestration,
   feature-owned shared UI, or temporary adapter.
5. Apply **one** edge cut at a time; compile both sides and dependents.
6. Remove temporary adapters after consumers migrate.
7. Re-run detection and `$verify-kotlin-modules`.

## Completion

Done when production SCCs are empty (or only documented exceptions remain),
source cycles are resolved or explicitly deferred, and verification is green.
