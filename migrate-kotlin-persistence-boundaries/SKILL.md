---
name: migrate-kotlin-persistence-boundaries
description: Audit and migrate Room, SQLDelight, DataStore, and related Kotlin persistence code across modules while preserving database versions, schemas, table/column names, migration chains, preference keys, KMP drivers/builders, and runtime behavior. Use when extracting persistence into feature data or utility modules, moving KMP database construction, splitting a shared database owner, or when a modularization move risks schema or stored-key drift.
---

# Migrate Kotlin Persistence Boundaries

Separate ownership moves from schema migrations. Default to byte- and
identity-preserving relocation of stored contracts.

## Workflow

1. Read [references/persistence-contracts.md](references/persistence-contracts.md).
2. Copy [assets/persistence-boundary-rules.example.json](assets/persistence-boundary-rules.example.json)
   and record the target module plus expected database versions.
3. Audit and plan:

   ```bash
   python3 scripts/analyze_persistence.py audit --root /path/to/repo \
     --rules persistence-boundary-rules.json \
     --json-out .modularization/persistence-boundary-audit.json
   python3 scripts/analyze_persistence.py plan --root /path/to/repo \
     --audit .modularization/persistence-boundary-audit.json \
     --rules persistence-boundary-rules.json \
     --json-out .modularization/persistence-migration-plan.json
   ```

4. Review every database/entity/DAO/query/migration/driver/preference component
   and the recorded schema fingerprints.
5. Move common contracts and platform builders in separate compilable batches.
   Use hash-guarded manifests; preserve schema export files.
6. Run repository persistence tests and platform database construction checks.
   Compare schema and stored-key snapshots before and after.

## Guardrails

- Do not bump a database version or add/drop/rename stored fields during an
  ownership-only move.
- Do not split a database across modules without one explicit schema owner.
- Do not move platform drivers/builders into portable source sets.
- Stop and request a separately reviewed migration when snapshots differ.

## Completion

Complete when the schema owner is explicit, versions and stored identities are
unchanged, all migration/driver registrations remain reachable, and platform
construction plus persistence tests pass.
