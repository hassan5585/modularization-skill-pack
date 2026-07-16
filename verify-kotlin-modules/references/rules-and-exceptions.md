# Architecture rules and exceptions

## Contents

1. Rule model
2. Default layer direction
3. Package mapping
4. Cross-feature policy
5. Exceptions
6. CI adoption

## 1. Rule model

The checker derives modules from directories containing `build.gradle` or `build.gradle.kts`. A module role is inferred from the last path segment or configured `module_roles` glob rules.

Rules operate on:

- Gradle project dependencies;
- Kotlin/Java imports mapped to owning modules by declared package prefixes;
- feature shape and required child layers;
- cycles in the project dependency graph.

Static parsing is intentionally conservative. It cannot fully interpret arbitrary Gradle Kotlin code, generated source dependencies, reflection, or runtime registration.

## 2. Default layer direction

Default hard constraints:

- `domain` must not depend on `data`, `navigation`, `ui`, app, or test-support modules.
- `data` must not depend on `navigation` or `ui`.
- `navigation` must not depend on `data` or `ui`.
- `ui` must not depend directly on `data` or test-support.
- aggregation roots must not depend on test-support.
- any production role must not depend on test-support.
- project dependency cycles are errors.

The checker reports cross-feature implementation coupling as a warning unless project rules make it an error.

## 3. Package mapping

For import checks, configure `package_roots` when module packages do not directly match paths. The checker also observes package declarations and assigns the most common package prefix to each module.

Generated packages may not have declarations in source. Add narrow ignored import prefixes for generated resources/code only after confirming build dependencies enforce the intended edge.

## 4. Cross-feature policy

Common policies, from least to most permissive:

1. Features communicate only through app/core contracts and navigation entries.
2. UI may depend on another feature’s navigation/domain contract but not its UI/data.
3. Explicit shared-feature contract modules are allowed.
4. Direct feature UI dependencies are temporarily allowed during migration.

Choose and encode one. Warnings left indefinitely are not an architecture policy.

## 5. Exceptions

An exception should look like:

```json
{
  "rule": "forbidden-layer-dependency",
  "source": ":feature:legacy:ui",
  "target": ":feature:legacy:data",
  "reason": "Temporary facade while repository port is extracted.",
  "owner": "mobile-platform",
  "remove_when": "LegacyRepositoryFacade is deleted"
}
```

Requirements:

- exact rule ID;
- exact source and target, not `*`;
- reason describing why the edge exists;
- accountable owner;
- objective removal condition.

Exceptions should still appear in reports as suppressed debt. Expiry dates may be added if the team has a process that enforces them.

## 6. CI adoption

Adopt in stages:

1. Generate a baseline report.
2. Fix or encode narrow pre-existing exceptions.
3. Fail CI on new errors.
4. Decide whether warnings fail CI.
5. Run Gradle compile/tests after the static checker.

Do not hide all baseline violations with broad path or rule exclusions. The goal is to prevent regression while paying down known debt.
