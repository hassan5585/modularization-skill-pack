---
name: scaffold-kotlin-feature
description: Create a new feature in an already modular Kotlin/Gradle repository with domain, data, navigation, UI, optional provider-owned shared-UI, and optional reusable test-support modules. Use when adding a product capability to a modular app, generating feature module skeletons, registering feature modules in settings, or when migrate-kotlin-feature needs target modules created without moving monolith code.
---

# Scaffold Kotlin Feature

Create **new** feature modules in a repository that is already modular. This is not
monolith extraction — use `$migrate-kotlin-feature` when existing behavior must move.

## Non-goals

- Moving monolith sources (owned by `$migrate-kotlin-feature`).
- Inventing DI, navigation graph, or app aggregation wiring when project-specific.
- Creating shared-UI chains or production dependencies on test-support.
- Overwriting existing module build files.

## Workflow

1. Read repository `AGENTS.md`, build docs, and an existing feature’s Gradle/package shape.
2. Discover conventions:

   ```bash
   python3 scripts/discover_feature_conventions.py \
     --root /path/to/repo \
     --json-out .modularization/feature-conventions.json
   ```

3. Build a reviewable feature specification from
   [assets/feature-spec.example.json](assets/feature-spec.example.json) or
   [assets/feature-spec-with-shared-ui.example.json](assets/feature-spec-with-shared-ui.example.json).
   Enable only justified layers: aggregation root, domain, data, navigation, UI,
   optional shared UI, optional test support.
4. Validate the dependency graph mentally against
   [references/feature-shapes.md](references/feature-shapes.md).
5. Preview every generated path:

   ```bash
   python3 scripts/scaffold_feature.py --root /path/to/repo --spec feature-spec.json
   ```

6. Apply after review (optional settings registration is idempotent):

   ```bash
   python3 scripts/scaffold_feature.py \
     --root /path/to/repo \
     --spec feature-spec.json \
     --register-settings \
     --apply
   ```

7. Leave app, DI, and navigation wiring as explicit reviewed steps when they cannot
   be safely inferred. See [references/registration-strategies.md](references/registration-strategies.md).
8. Compile the new modules and run `$verify-kotlin-modules`.

## Layer rules

```text
feature root -> data + domain + navigation + optional shared-ui + ui
ui           -> domain + navigation + core/ui + approved shared-ui
shared-ui    -> owner domain/navigation + core/ui only
data         -> domain + core/data
navigation   -> domain + core/navigation
domain       -> core/domain
tests        -> owning module + test-support (test configurations only)
```

## Completion

The feature scaffold is complete when modules exist, settings includes are present,
placeholders compile under project conventions, architecture verification is clean
for the new graph, and no existing files were overwritten.
