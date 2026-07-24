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

Configure `conventions.included_builds`, `conventions.required_registered_plugin_ids`, and `conventions.required_plugins_by_role` after convention design is approved. With `validate_included_build_plugins` enabled, the checker confirms that included-build subprojects are registered, every static plugin registration has an implementation class whose source exists, ids are unique, and the required ids are registered. This turns “create convention plugins” into an enforceable build-logic and consumer-module rule. Use `forbidden_plugins_by_role` only for raw plugins fully owned by a convention.

For `alias(libs.plugins.example.feature.domain)`, configure the token `example.feature.domain`; for `id("com.example.feature.domain")`, configure the full plugin id. Use the exact token shown in the Gradle audit because static verification does not resolve version-catalog aliases to ids.

Configure `required_test_modules` for approved shared foundations. Feature-specific test support remains optional unless the target plan explicitly requires it.

Use `required_feature_layers_by_feature` for deliberately partial feature shapes. Exact feature entries override `required_feature_layers`; `"*"` is the mapping fallback. For example, `{"profile": ["domain", "ui"], "payments": ["domain", "data"]}` verifies the approved architecture without manufacturing empty layers.

`direct_project_imports` is optional. Enable it only when the repository forbids imports obtained through another module’s public `api` dependency; otherwise leave its severity null.

## 2. Default layer direction

Default hard constraints:

- `domain` must not depend on `data`, `navigation`, `shared-ui`, `ui`, app, or test-support modules.
- `data` must not depend on `navigation`, `shared-ui`, or `ui`.
- `navigation` must not depend on `data`, `shared-ui`, or `ui`.
- `ui` must not depend directly on `data` or test-support.
- `shared-ui` may use core UI, its owner’s domain/navigation contracts, and
  approved utility contracts. Among feature contracts, it may use only its
  owner’s; it must not depend on feature UI, a feature root, another
  `shared-ui`, foreign feature contracts, data, or test support.
- A feature `shared-ui` target may be consumed only by its owner aggregation
  root or a feature regular-UI module; app, core, util, and lower layers are not
  consumers.
- aggregation roots must not depend on test-support.
- any production role must not depend on test-support.
- project dependency cycles are errors.

`forbidden_target_roles` expresses role-only restrictions. It intentionally
does not put `ui` or `aggregation` in the `shared-ui` list because that would
also reject legal `core:ui`; the non-suppressible shared-UI checks apply the
feature-aware regular-UI and owner-root restrictions.

The checker reports cross-feature implementation coupling as a warning unless project rules make it an error.

## 3. Package mapping

For import checks, configure `package_roots` when module packages do not directly match paths. The checker also observes package declarations and assigns the most common package prefix to each module.

Generated packages may not have declarations in source. Add narrow ignored import prefixes for generated resources/code only after confirming build dependencies enforce the intended edge.

## 4. Cross-feature policy

Common policies, from least to most permissive:

1. Features communicate only through app/core contracts and navigation entries.
2. UI may depend on another feature’s navigation/domain contract but not its UI/data.
3. Explicit shared-feature contract modules are allowed.
4. Feature UI may consume a provider feature’s `shared-ui`, but only the
   source/target role pair `ui -> shared-ui`.
5. Direct feature UI dependencies are temporarily allowed during migration.

Choose and encode one. Warnings left indefinitely are not an architecture policy.

Encode source-sensitive edges without opening the target role globally:

```json
{
  "cross_feature": {
    "severity": "error",
    "allowed_target_roles": ["domain", "navigation"],
    "allowed_role_edges": {
      "ui": ["shared-ui"]
    }
  }
}
```

Never put `shared-ui` in `allowed_target_roles`; that would let data,
navigation, aggregation, and other shared-UI modules consume it. The checker
always treats `shared-ui -> shared-ui`,
`shared-ui -> foreign feature domain/navigation`, `shared-ui -> feature ui`,
`shared-ui -> feature root`, and unsupported consumers of `shared-ui` as errors
that cannot be suppressed by an exception.

The checker also applies the new lower-layer/shared-UI hard boundaries to older
schema-v1 rule files that do not yet contain `shared-ui` entries. When such a
file omits `cross_feature.allowed_role_edges.ui`, the compatible default permits
only `ui -> shared-ui`; an explicitly configured `ui` list remains authoritative.

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

Exceptions cannot suppress the shared-UI hard-boundary rule IDs. In particular,
`shared-ui -> shared-ui` is never an accepted migration state; compose providers
in consumer UI or move a genuinely generic primitive to core UI.

Exceptions should still appear in reports as suppressed debt. Expiry dates may be added if the team has a process that enforces them.

## 6. CI adoption

Adopt in stages:

1. Generate a baseline report.
2. Fix or encode narrow pre-existing exceptions.
3. Fail CI on new errors.
4. Decide whether warnings fail CI.
5. Run Gradle compile/tests after the static checker.

Do not hide all baseline violations with broad path or rule exclusions. The goal is to prevent regression while paying down known debt.
