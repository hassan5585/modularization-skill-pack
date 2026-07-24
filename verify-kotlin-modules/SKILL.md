---
name: verify-kotlin-modules
description: Validate a modular Kotlin/Gradle architecture with feature aggregation modules and domain, data, navigation, UI, optional feature shared-UI, and test-support layers. Use after scaffolding or migrating modules, in architecture reviews, or in CI to check module shape, settings registration, project dependency direction, shared-UI provider/consumer rules, source-import boundaries, feature coupling, production-to-test leaks, dependency cycles, source-set placement, and appropriate Gradle verification tasks.
---

# Verify Kotlin Modules

Use static checks as fast architecture feedback, then confirm with the target project’s actual Gradle compilation and tests.

## Configure rules

Copy [assets/architecture-rules.example.json](assets/architecture-rules.example.json) to `.modularization/architecture-rules.json` and adapt package prefixes, roots, exceptions, and severities. Read [references/rules-and-exceptions.md](references/rules-and-exceptions.md) before adding exceptions.

Every exception must include a narrow source/target, reason, owner, and removal condition. Never add a wildcard exception to make a migration green.

Configure `cross_feature.allowed_role_edges` when only specific role pairs may
cross a feature boundary. For the provider-owned shared-UI pattern, allow
`ui -> shared-ui`; do not add `shared-ui` to global `allowed_target_roles`,
because that would permit lower layers and aggregation roots to consume it.
The checker separately keeps provider `shared-ui` dependencies within the
provider’s own feature contracts and rejects consumers other than feature UI
modules or the provider’s aggregation root.
These shared-UI boundaries are enforced for existing schema-v1 rules files as
well; a rules file created before the pattern does not silently bypass them.

Configure the approved convention included build, every required registered plugin id, and role-to-plugin requirements. Replace every `example.*` value in the asset; never run CI with placeholders. With `validate_included_build_plugins` enabled, the checker also verifies the included build's settings registration, static plugin registrations, implementation-class source files, and duplicate ids. Configure shared test modules only when the plan requires them.

Use `required_feature_layers_by_feature` when features intentionally have different shapes. An exact feature key overrides `required_feature_layers`; `"*"` supplies a default. An explicit empty list documents that a feature has no mandatory child layers. Do not create empty data, navigation, UI, or test modules merely to satisfy a global template.

Leave `direct_project_imports.severity` null unless the target architecture requires every imported module to be a direct Gradle dependency. Enabling it in projects that intentionally expose transitive `api` contracts creates noise rather than a valid boundary rule.

## Run static verification

```bash
python3 scripts/check_architecture.py \
  --root /path/to/repo \
  --rules /path/to/repo/.modularization/architecture-rules.json \
  --json-out /path/to/repo/.modularization/architecture-findings.json
```

Without `--rules`, the script applies conservative defaults based on module path suffixes. Treat default warnings as review items until project-specific rules exist.

The checker validates:

- layer/module shape inferred from build-file paths;
- Gradle `project(...)` dependency edges;
- forbidden layer dependencies;
- source imports that bypass the Gradle graph or point inward incorrectly;
- cross-feature UI/data coupling;
- legal UI-to-shared-UI consumption and hard failures for shared-UI chains or shared-UI-to-feature-UI edges;
- production dependencies on test-support modules;
- graph cycles;
- global or per-feature required layers when configured;
- required shared test-support modules;
- required convention included builds, their registered subprojects/plugin implementations, and per-role convention plugin use;
- optional direct-project dependency coverage for production imports;
- explicit, narrow exceptions.

## Select build checks

Generate a reviewable command matrix:

```bash
python3 scripts/suggest_gradle_checks.py --root /path/to/repo --changed feature/orders
```

The suggester ignores `.modularization` outputs. When convention plugin names and source sets do not expose a module's platform, add narrow overrides such as `--platform-rule ':feature:legacy:*'=android` or `--platform-rule ':shared'=kmp`. This affects task suggestions only; it does not change architecture findings.

The output is advisory. Prefer tasks proven by CI or `./gradlew tasks` in the target repository. Run checks from narrow to broad:

1. included build/build-logic compilation;
2. changed layer compile;
3. changed layer unit tests;
4. direct dependent compile/tests;
5. feature aggregation checks;
6. app compile or platform deliverable;
7. repository lint/static analysis;
8. broader platform tests when risk warrants them.

## Review generated and platform behavior

Static imports are insufficient for:

- DI/KSP/KAPT/code-generation registration;
- Compose or Android resources;
- Room schemas and migrations;
- navigation serializer registries and deep links;
- iOS/native framework exports and source sets;
- manifests, service loaders, reflection, and shrinker behavior.

Inspect generated outputs/tasks and run the corresponding compile or packaging checks.

## Severity policy

- **Error:** forbidden direction, cycle, production-to-test dependency, missing required module, or source import that violates a hard rule.
- **Error:** a shared-UI module depending on another shared-UI module, a regular feature UI, or a feature aggregation root.
- **Warning:** cross-feature coupling, ambiguous ownership, unusual platform dependency, or an unconfigured module role.
- **Info:** migration debt or suggested cleanup that does not break the architecture contract.

Do not downgrade errors solely because they predate the migration. Record baseline debt separately and prevent new violations.

## Completion report

Report:

- commands run and their exact outcomes;
- static findings grouped by error/warning/info;
- pre-existing versus introduced failures;
- unverified platform/generated-code risks;
- exceptions used and why;
- remaining adapters or monolith files;
- whether the migrated feature and full modularization phase satisfy their definition of done.

Verification is complete only when the actual build graph and source graph agree with the intended architecture.
