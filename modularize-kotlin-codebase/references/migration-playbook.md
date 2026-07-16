# Incremental migration playbook

## Contents

1. Baseline
2. Discovery artifacts
3. Pilot selection
4. Change batches
5. Compatibility techniques
6. Verification ladder
7. Completion criteria

## 1. Baseline

Before structural edits, capture:

- current branch and dirty files;
- CI-required tasks;
- fastest app/module compile;
- unit, lint, static-analysis, and code-generation checks;
- known failures with exact output;
- generated directories that must not be moved manually.

Never attribute a baseline failure to the migration without evidence.

## 2. Discovery artifacts

Store durable migration artifacts under `.modularization/` when repository writes are authorized:

```text
.modularization/
  config.json
  audit.json
  audit.md
  plan.json
  plan.md
  gradle-audit.json
  architecture-rules.json
  feature-<name>.json
  moves-<name>-<batch>.json
  findings.json
```

JSON is the machine contract; Markdown is the review surface. Keep them generated from the same inputs.

## 3. Pilot selection

Choose a feature with:

- a clear product name and entry point;
- owned UI, domain decisions, and at least one integration;
- representative tests or behavior that can be characterized;
- limited cross-feature UI coupling;
- no urgent database/serialization migration unless those risks are the explicit objective.

Avoid both trivial settings-only slices and the most entangled feature. The pilot must validate the architecture and convention plugins.

## 4. Change batches

Keep commits or logical batches compilable:

1. Add build conventions without converting all modules.
2. Add empty target modules and registration.
3. Move domain types and tests; compile.
4. Move data ports/implementations and tests; compile.
5. Move navigation contracts; compile navigation and dependents.
6. Move UI/resources; compile UI and app.
7. Rewire DI and app aggregation.
8. Remove old code and compatibility adapters.
9. Run broad verification.

If an intermediate build cannot compile, make the batch smaller or use a temporary adapter.

## 5. Compatibility techniques

Use deliberately and remove promptly:

- type aliases for package migrations that preserve source compatibility;
- forwarding factories/providers while DI registration moves;
- route adapters that preserve serialized route identity;
- repository facade implementations delegating to the new module;
- resource aliases when resource IDs are externally referenced.

Do not duplicate mutable state or business implementations. Name adapters with `Legacy`, `Compatibility`, or `Bridge`, record their removal condition, and prevent new call sites.

## 6. Verification ladder

Run from fastest/local to broadest:

1. static package/import checks;
2. build-logic compile;
3. changed module compile;
4. changed module unit tests;
5. direct dependent compile/tests;
6. feature aggregation check;
7. app/shared-app compile;
8. platform packaging/native link where relevant;
9. lint/static analysis;
10. full repository checks when risk or milestone warrants them.

Generated code, resources, navigation registration, database schemas, and native exports require actual Gradle tasks; static checks cannot prove them.

## 7. Completion criteria

A feature migration is done when:

- all owned production and test code has intentional ownership;
- app, DI, navigation, serialization, resource, and platform registration is complete;
- old packages and duplicate implementations are gone;
- compatibility adapters are removed or explicitly scheduled;
- no forbidden dependency/import edges exist;
- changed-layer and app checks pass;
- documentation reflects the new owner and entry points.

The overall monolith split is done only when the remaining monolith is an intentional app shell or platform entry point, not a residual dumping ground.
