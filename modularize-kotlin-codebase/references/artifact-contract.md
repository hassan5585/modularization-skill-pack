# `.modularization` artifact contract

Use JSON with `schema_version: 1`. Treat paths as repository-relative POSIX paths. Do not store secrets, absolute developer paths, generated build output, or environment-specific credentials.

## Configuration

`config.json` records user-approved intent:

- project platform and root package;
- target module roots and layers;
- feature ownership overrides;
- convention plugin strategy;
- architecture rules and narrow exceptions;
- baseline verification commands.

## Audit

`audit.json` records observed facts and heuristic classifications:

- project/build detection;
- modules and project dependencies;
- source files, packages, imports, inferred feature/layer, and confidence;
- external library/import families;
- feature candidates and coupling.

Do not hand-edit generated audit fields. Put corrections in an overrides file.

## Plan

`plan.json` records proposed intent:

- features and target modules;
- file-to-layer assignments;
- unresolved files;
- proposed shared/core/utility candidates;
- dependency risks;
- pilot recommendation and migration sequence.

The plan becomes approved only after an agent or user reviews ambiguous assignments.

## Move manifests

Each move has:

```json
{
  "from": "old/path/File.kt",
  "to": "feature/example/domain/src/commonMain/kotlin/com/example/domain/File.kt",
  "package_from": "com.example.old",
  "package_to": "com.example.feature.domain"
}
```

Omit package fields for resources or files without a package declaration. Never use wildcards.

## Findings

Each finding should contain:

- stable rule ID;
- severity;
- source module/file;
- target module/import when applicable;
- concise evidence;
- whether an exception matched.

Artifacts may evolve, but scripts must reject unsupported schema versions rather than silently misreading them.
