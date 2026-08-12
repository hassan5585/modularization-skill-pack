---
name: integrate-kotlin-feature
description: Complete and verify the project-specific integration of a scaffolded or migrated Kotlin feature across settings, app dependencies, dependency injection, navigation, serializer registration, and app-shell aggregation. Use after scaffold-kotlin-feature or migrate-kotlin-feature, when a feature compiles in isolation but is absent at runtime, or when modularization leaves manual DI/navigation/app wiring unresolved.
---

# Integrate Kotlin Feature

Close the intentional gap between module creation and a reachable runtime
feature. Discover and preserve the repository’s existing integration style.

## Workflow

1. Read repository build, DI, navigation, and app-shell guidance plus
   [references/integration-strategies.md](references/integration-strategies.md).
2. Copy [assets/feature-integration-rules.example.json](assets/feature-integration-rules.example.json)
   and record only requirements proven for the target feature.
3. Audit and plan:

   ```bash
   python3 scripts/integrate_feature.py audit --root /path/to/repo \
     --feature orders --rules feature-integration-rules.json \
     --json-out .modularization/feature-integration-audit.json
   python3 scripts/integrate_feature.py plan --root /path/to/repo \
     --audit .modularization/feature-integration-audit.json \
     --rules feature-integration-rules.json \
     --json-out .modularization/feature-integration-plan.json
   ```

4. Review every proposed edit. Keep route IDs, serializer names, deep links,
   DI keys/scopes, and app-shell behavior unchanged.
5. Apply one integration surface at a time: settings, app dependency, DI,
   navigation/serializer registration, then app entry point.
6. Verify after edits:

   ```bash
   python3 scripts/integrate_feature.py check --root /path/to/repo \
     --feature orders --rules feature-integration-rules.json
   ```

7. Compile the feature and app entry points; run `$verify-kotlin-modules`.
   Invoke `$modularize-kotlin-dependency-injection` when graph ownership or
   scopes change rather than merely adding a known registration.

## Guardrails

- Do not invent a new registry, DI framework, navigator, or service locator.
- Do not add `api` merely to make app wiring compile.
- Do not register test-support modules on production paths.
- Stop when integration would change route/wire identity or runtime scope.

## Completion

Complete integration when all required gates pass, the feature is reachable
from the intended app entry point, and app/platform verification succeeds.
