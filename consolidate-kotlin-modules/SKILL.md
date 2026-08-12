---
name: consolidate-kotlin-modules
description: Audit, plan, and verify the evidence-backed consolidation of over-fragmented Kotlin, Android, JVM, or Kotlin Multiplatform Gradle modules while preserving source sets, resources, public APIs, DI/navigation registration, persistence contracts, and dependency direction. Use when build metrics show modularization overhead, tiny modules have inseparable ownership and release cadence, or redundant aggregation/leaf modules should be safely merged or retired.
---

# Consolidate Kotlin Modules

Provide a controlled reverse migration when module boundaries cost more than
they isolate. Require evidence; do not merge modules merely to reduce count.

## Workflow

1. Read [references/consolidation-criteria.md](references/consolidation-criteria.md).
2. Capture build/coupling evidence with `$measure-kotlin-modular-build-performance`
   and `$audit-kotlin-architecture` when not already available.
3. Copy [assets/module-consolidation-spec.example.json](assets/module-consolidation-spec.example.json)
   and record exact source modules, target module, reason, and evidence.
4. Audit and plan:

   ```bash
   python3 scripts/consolidate_modules.py audit --root /path/to/repo \
     --spec module-consolidation-spec.json \
     --json-out .modularization/module-consolidation-audit.json
   python3 scripts/consolidate_modules.py plan --root /path/to/repo \
     --audit .modularization/module-consolidation-audit.json \
     --spec module-consolidation-spec.json \
     --json-out .modularization/module-consolidation-plan.json
   ```

5. Review the simulated graph and every source/resource/schema/DI/navigation
   concern. Move with hash-guarded manifests, then update dependencies, settings,
   registrations, and build logic in small batches.
6. Verify retired modules no longer exist or receive dependencies:

   ```bash
   python3 scripts/consolidate_modules.py check --root /path/to/repo \
     --spec module-consolidation-spec.json
   ```

7. Run architecture checks and repeat the same build-metric scenarios.

## Guardrails

- Do not merge across unrelated product ownership or incompatible platforms.
- Do not hide a dependency cycle by collapsing an arbitrary strongly connected
  component; use `$break-kotlin-module-cycles` first.
- Preserve public contracts and native export boundaries.
- Keep test-support off production paths and retain one persistence schema owner.

## Completion

Complete when retired modules and edges are gone, the simulated/final graph is
acyclic, all contracts compile, and before/after metrics justify the outcome.
