---
name: modularize-kotlin-dependency-injection
description: Audit and migrate dependency-injection boundaries across Kotlin, Android, JVM, and Kotlin Multiplatform modules while preserving the repository’s existing Metro, Dagger/Hilt, Koin, or manual-DI framework. Use when feature extraction breaks generated bindings, scopes or graph visibility; when app/platform graphs need aggregation; when providers, multibindings, assisted factories, or session scopes cross module boundaries; or before integrating a newly modularized feature.
---

# Modularize Kotlin Dependency Injection

Preserve the detected DI framework and runtime object graph while moving graph
ownership, bindings, and scopes to intentional module boundaries.

## Workflow

1. Read repository DI/build guidance and
   [references/framework-boundaries.md](references/framework-boundaries.md).
2. Copy [assets/di-boundary-rules.example.json](assets/di-boundary-rules.example.json),
   remove placeholders, and record the approved framework and graph entry points.
3. Audit and plan:

   ```bash
   python3 scripts/analyze_di.py audit --root /path/to/repo \
     --rules di-boundary-rules.json \
     --json-out .modularization/di-boundary-audit.json
   python3 scripts/analyze_di.py plan --root /path/to/repo \
     --audit .modularization/di-boundary-audit.json \
     --rules di-boundary-rules.json \
     --json-out .modularization/di-migration-plan.json
   ```

4. Review mixed-framework findings, platform graphs, runtime/session scopes,
   provider methods, multibindings, and generated-code visibility.
5. Move contracts before implementations. Move graph/container aggregation only
   after all contributed bindings remain reachable from the same runtime graph.
6. Preserve qualifiers, scopes, keys, assisted parameters, eager/lazy semantics,
   and platform-specific graph construction.
7. Compile graph-owning modules and platform entry points, then run
   `$integrate-kotlin-feature` and `$verify-kotlin-modules`.

## Guardrails

- Do not switch DI frameworks as part of modularization.
- Do not replace constructor injection with service location.
- Do not widen `api` dependencies solely for generated-code discovery.
- Treat providers as reviewed factory boundaries, not a default binding style.
- Stop when a scope lifetime or runtime graph owner cannot be proven.

## Completion

Complete the migration when one approved framework remains, all graph entry
points reach their bindings, platform graphs compile, scope lifetimes are
unchanged, and the DI plan has no unresolved blocking finding.
