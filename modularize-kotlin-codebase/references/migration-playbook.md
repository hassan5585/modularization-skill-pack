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
- for KMP Apple frameworks, the latest existing framework/header baseline and intentional Swift bridge.

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
  work-state.json
  worklog.md
```

JSON is the machine contract; Markdown is the review surface. Keep them generated from the same inputs.

Initialize the work state from the reviewed plan. Start, verify, and complete one chunk at a time. Record temporary bridges and removal conditions when they are introduced, not during final cleanup.

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
6. Move an approved provider `shared-ui`; compile/test it and every consumer UI.
7. Move UI/resources; compile UI and app.
8. Rewire DI and app aggregation.
9. Remove old code and compatibility adapters.
10. Run broad verification.

Map these batches into the repository ledger. A conversation checklist is not a durable checkpoint.

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
8. existing generated native framework/header audit where relevant;
9. platform packaging/native link when a fresh artifact is required;
10. lint/static analysis;
11. full repository checks when risk or milestone warrants them.

Generated code, resources, navigation registration, database schemas, and native framework output require actual Gradle tasks; static checks cannot prove them. Inspect an existing framework before triggering an expensive release link, and keep Devirtualization/DCE enabled in the final configuration.

## 7. Completion criteria

A feature migration is done when:

- all owned production and test code has intentional ownership;
- app, DI, navigation, serialization, resource, and platform registration is complete;
- old packages and duplicate implementations are gone;
- compatibility adapters are removed or explicitly scheduled;
- no forbidden dependency/import edges exist;
- no direct cross-feature regular-UI edge or shared-UI chain exists;
- changed-layer and app checks pass;
- documentation reflects the new owner and entry points.
- all `api` project dependencies are intentional and any Apple framework retains its approved narrow Swift surface.

The overall monolith split is done only when the remaining monolith is an intentional app shell or platform entry point, not a residual dumping ground.
