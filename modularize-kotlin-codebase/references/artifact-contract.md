# `.modularization` artifact contract

Use JSON with `schema_version: 1`. Treat paths as repository-relative POSIX paths and represent the repository root as `.`. Do not store secrets, absolute developer paths, generated build output, or environment-specific credentials.

## Layout

```text
.modularization/
├── config.json
├── audit.json
├── plan.json                 # module plan (alias: module-plan.json)
├── foundation-plan.json
├── cycle-report.json
├── api-surface-report.json
├── platform-boundary-plan.json
├── feature-integration-audit.json
├── feature-integration-plan.json
├── di-boundary-audit.json
├── di-migration-plan.json
├── feature-coupling-report.json
├── feature-decoupling-plan.json
├── data-boundary-audit.json
├── data-boundary-plan.json
├── test-boundary-audit.json
├── test-migration-plan.json
├── resource-audit.json
├── resource-migration-plan.json
├── persistence-boundary-audit.json
├── persistence-migration-plan.json
├── module-consolidation-audit.json
├── module-consolidation-plan.json
├── module-consolidation-check.json
├── navigation3-audit.json    # optional; migrate-to-navigation3
├── navigation3-spec.json
├── navigation3-check.json
├── work-state.json
├── worklog.md
├── receipts/
└── build-metrics/
    ├── baseline.json
    ├── current.json
    └── comparison.json
```

## Common envelope

Every skill-written artifact should record when applicable:

- `schema_version` (required, `1`);
- `repository.root` / `repository.revision`;
- `generator.skill` / `generator.script` / `generator.version`;
- `inputs`;
- observed facts vs inferred `recommendations`;
- `unresolved` decisions;
- `gates` (pass/fail/review);
- `verification` command lists and results when known.

Cross-skill validation helpers live in the pack’s `common/artifact_schema.py`.

## Configuration

`config.json` records user-approved intent:

- project platform and root package;
- target module roots and layers;
- feature ownership overrides;
- convention plugin strategy;
- architecture rules and narrow exceptions;
- baseline verification commands.
- public project dependency allowances and native framework audit commands/rules when applicable.

## Audit

`audit.json` records observed facts and heuristic classifications:

- project/build detection;
- modules and project dependencies, including observed Gradle configurations such as `implementation`, `api`, test-only, and native export;
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
- explicit shared-UI consumer/provider module edges used for migration ordering;
- shared-UI graph violations and the non-waivable plan-acceptance gate;
- dependency risks;
- public API/native framework risks and the approved Swift bridge when applicable;
- pilot recommendation and migration sequence.

The plan becomes approved only after an agent or user reviews ambiguous assignments.

Shared-UI planning fields have this concrete shape:

```json
{
  "shared_ui_dependencies": [
    {
      "consumer": ":feature:checkout:ui",
      "provider": ":feature:orders:shared-ui",
      "source": "approved override"
    }
  ],
  "shared_ui_violations": [
    {
      "source": ":feature:orders:shared-ui",
      "target": ":feature:profile:shared-ui",
      "rule": "shared-ui-to-shared-ui",
      "evidence": "Shared UI must not depend on shared UI."
    }
  ],
  "plan_acceptance": {
    "shared_ui_graph": "fail"
  }
}
```

Every override edge uses exactly `consumer` and `provider`; generated plan
edges add `source` to distinguish observed Gradle dependencies from approved
overrides. The consumer must be
an absolute feature `:ui` path and the provider an absolute feature
`:shared-ui` path; both endpoints must be present in the plan. The planner
combines reviewed overrides with observed Gradle edges. It emits
`shared_ui_violations` for illegal direction, unsupported consumers, missing
endpoints, or forbidden provider dependencies, and sets
`plan_acceptance.shared_ui_graph` to `pass` only when that list is empty. The
work tracker refuses to initialize unless this gate passes.

## Focused boundary artifacts

Focused skills preserve evidence that must survive ownership changes:

- feature integration records physical modules, app owners, project edges, and
  DI/navigation/serializer/app-entry evidence;
- DI artifacts record detected frameworks, graph/container/binding/provider/
  scope/multibinding/assisted declarations, graph owners, and preserved keys;
- coupling artifacts record every production cross-feature edge, import
  evidence, classification, exact allowance reason, and reviewed cut strategy;
- data artifacts record component ownership plus wire `@SerialName` and source
  fingerprints; persistence artifacts separately record versions, schema files,
  table/column/preference identities, and platform construction concerns;
- test artifacts record production matches, source-set targets, expected source
  hashes, support candidates, production-to-test edges, and affected tasks;
- resource artifacts record type/key, owner, locale/qualifier variant, content
  hash, generated-accessor consumers, and reviewed moves;
- consolidation artifacts record evidence, before/simulated graphs, exact module
  inventories and hashes, incoming edges, concerns, ordered actions, and final
  retirement checks.

Never treat heuristic ownership as approval. Plan artifacts retain unresolved
decisions and use `review` gates until a user/agent has checked semantic
ownership. Wire/resource/schema/stored-key snapshots are invariants unless the
user explicitly scopes a separate compatibility migration.

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
