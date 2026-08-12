---
name: migrate-kotlin-tests
description: Audit and migrate Kotlin tests, fixtures, builders, and handwritten fakes alongside modularized production code across commonTest, Android host/unit/instrumented tests, JVM tests, iOS tests, and reusable test-support modules. Use during feature or foundation extraction, when package/module moves break tests, when deciding whether a fake deserves a test-support module, or when preventing production dependencies on test code and selecting affected Gradle test tasks.
---

# Migrate Kotlin Tests

Keep behavioral evidence attached to the production code it verifies. Preserve
the repository’s test stack and source-set conventions.

## Workflow

1. Read repository testing guidance and
   [references/test-ownership.md](references/test-ownership.md).
2. Copy [assets/test-migration-rules.example.json](assets/test-migration-rules.example.json)
   and configure source-set/task mappings only where discovery is ambiguous.
3. Audit and plan:

   ```bash
   python3 scripts/plan_test_migration.py audit --root /path/to/repo \
     --rules test-migration-rules.json \
     --json-out .modularization/test-boundary-audit.json
   python3 scripts/plan_test_migration.py plan --root /path/to/repo \
     --audit .modularization/test-boundary-audit.json \
     --rules test-migration-rules.json \
     --json-out .modularization/test-migration-plan.json
   ```

4. Review production matches and unresolved fixtures. Keep portable tests in
   common test source sets; use platform tests only for platform behavior.
5. Move tests in the same ledger batch as their production declaration. Create
   reviewed hash-guarded move manifests; create test-support modules only for
   reusable fakes/fixtures with real consumers.
6. Run narrow tests first, then affected module/consumer tasks from the plan.
7. Verify no production configuration depends on test-support.

## Guardrails

- Do not change test libraries as part of a source move.
- Do not weaken assertions merely to make migrated tests pass.
- Do not place common production tests only in Android/JVM source sets.
- Do not promote single-consumer fakes into global test foundations.

## Completion

Complete when tests follow production ownership, reusable support edges remain
test-only and acyclic, affected tasks pass, and unresolved matches are reviewed.
