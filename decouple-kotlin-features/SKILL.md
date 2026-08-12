---
name: decouple-kotlin-features
description: Audit and remediate undesirable feature-to-feature Kotlin module dependencies, including acyclic coupling that cycle detection does not report. Use when one feature imports another feature’s UI or data implementation, when cross-feature domain/navigation edges proliferate, when provider-owned shared UI should be extracted, or when choosing between a port, event, navigation contract, stable foundation, approved dependency, or shared-ui boundary.
---

# Decouple Kotlin Features

Reduce semantic feature coupling without dumping types into `core` or inventing
an event bus. Analyze every production cross-feature edge, not only cycles.

## Workflow

1. Read [references/edge-remediation.md](references/edge-remediation.md).
2. Copy [assets/feature-coupling-rules.example.json](assets/feature-coupling-rules.example.json)
   and add only reviewed allowed edges.
3. Audit and plan:

   ```bash
   python3 scripts/analyze_feature_coupling.py audit --root /path/to/repo \
     --rules feature-coupling-rules.json \
     --json-out .modularization/feature-coupling-report.json
   python3 scripts/analyze_feature_coupling.py plan --root /path/to/repo \
     --report .modularization/feature-coupling-report.json \
     --json-out .modularization/feature-decoupling-plan.json
   ```

4. Review the semantic owner and consumer of each edge. Fan-in alone is not
   evidence that a contract belongs in core.
5. Apply one reviewed edge cut at a time. Use hash-guarded move manifests from
   `$migrate-kotlin-feature` for source/resource moves.
6. Compile both features and their app consumer, then run
   `$break-kotlin-module-cycles` and `$verify-kotlin-modules`.

## Guardrails

- Keep navigation contracts in navigation modules and implementation data in
  the owning data module.
- Extract provider-owned shared UI only for a demonstrated consumer; never
  create shared-ui chains.
- Use events for facts that already happened, not synchronous queries.
- Preserve a direct dependency when it is the clearest stable product contract;
  record the exact edge and reason.

## Completion

Complete when forbidden feature edges are removed, approved edges have reasons,
the shared-UI graph is valid, and the affected build graph remains acyclic.
