# `.modularization` artifact contract

Use JSON with `schema_version: 1`. Treat paths as repository-relative POSIX paths and represent the repository root as `.`. Do not store secrets, absolute developer paths, generated build output, or environment-specific credentials.

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
- manifests, resources, schemas, shrinker rules, and native artifacts with module/source-set ownership;
- external library/import families;
- feature candidates and coupling.

Do not hand-edit generated audit fields. Put corrections in an overrides file.

## Plan

`plan.json` records proposed intent:

- features and target modules;
- file-to-layer assignments;
- non-code artifact assignments and unresolved artifact ownership;
- unresolved files;
- proposed shared/core/utility candidates;
- explicitly approved `foundation_modules` and shared test-foundation modules (empty means no global foundation chunk);
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

Omit package fields for resources or files without a package declaration. Never use wildcards. Before applying, add `expected_sha256` for each source and require hashes so a stale manifest cannot move changed content. Store the generated receipt under `.modularization/receipts/` and link it from the active chunk.

## Findings

Each finding should contain:

- stable rule ID;
- severity;
- source module/file;
- target module/import when applicable;
- concise evidence;
- whether an exception matched.

Artifacts may evolve, but scripts must reject unsupported schema versions rather than silently misreading them.

## Work state

`work-state.json` is the resumable execution contract. It records:

- initial repository branch/head and dirty baseline;
- dependency-ordered chunks with one active chunk at most;
- start/end repository snapshots;
- exact check argv, exit code, classification, summary, and log artifacts;
- completion evidence and reasons for any non-executable batch;
- approved decisions, risks/mitigations, and temporary adapters/removal conditions.

Generate `worklog.md` from the JSON state. Do not maintain a second hand-written progress source. Final completion requires a valid state graph, no introduced required-check failure, and no unexplained open adapter.

All pack traversal scripts ignore `.modularization` by default so generated plans, dry-run fixtures, and reports cannot be rediscovered as production modules or sources.
