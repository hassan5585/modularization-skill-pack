---
name: verify-kotlin-modules
description: Validate a modular Kotlin/Gradle architecture with feature aggregation modules and domain, data, navigation, UI, and test-support layers. Use after scaffolding or migrating modules, in architecture reviews, or in CI to check module shape, settings registration, project dependency direction, source-import boundaries, feature coupling, production-to-test leaks, dependency cycles, source-set placement, and appropriate Gradle verification tasks.
---

# Verify Kotlin Modules

Use static checks as fast architecture feedback, then confirm with the target project’s actual Gradle compilation and tests.

## Configure rules

Copy [assets/architecture-rules.example.json](assets/architecture-rules.example.json) to `.modularization/architecture-rules.json` and adapt package prefixes, roots, exceptions, and severities. Read [references/rules-and-exceptions.md](references/rules-and-exceptions.md) before adding exceptions.

Every exception must include a narrow source/target, reason, owner, and removal condition. Never add a wildcard exception to make a migration green.

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
- production dependencies on test-support modules;
- graph cycles;
- required feature layers when configured;
- explicit, narrow exceptions.

## Select build checks

Generate a reviewable command matrix:

```bash
python3 scripts/suggest_gradle_checks.py --root /path/to/repo --changed feature/orders
```

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
