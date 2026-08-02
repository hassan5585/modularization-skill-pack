---
name: audit-kotlin-native-framework
description: Audit a built Kotlin/Native Apple framework and the Gradle configuration that feeds it, with configurable header-size, Objective-C declaration, required bridge, forbidden symbol, dependency export, and compiler-phase checks. Use when modularizing a KMP app that ships an iOS framework, changing public or iosMain declarations, dependency scopes, framework exports, Swift bridges, CocoaPods or SwiftPM interop, or diagnosing slow, stuck, memory-heavy, or out-of-memory native link tasks.
---

# Audit Kotlin Native Framework

Keep the Swift-facing framework contract deliberate and small. Inspect an existing framework before starting another expensive release link.

## Establish the boundary

1. Read the target repository’s native build and bridge documentation.
2. Identify the framework-producing module and the API Swift intentionally calls.
3. Treat public Kotlin declarations as implementation details unless they are part of that bridge or a real public library contract.
4. Copy [references/native-framework-rules.example.json](references/native-framework-rules.example.json), replace its example patterns and thresholds with an approved baseline, and store it with the target repository’s architecture rules.

For an application framework, prefer one narrow facade such as `IosAppBridge`. Keep repositories, ViewModels, dependency graphs, generated DI factories, feature models, and third-party native types behind it. Make Kotlin-only declarations `internal`; when a declaration must remain public for another Kotlin module, use `@HiddenFromObjC` where the project’s Kotlin version supports Objective-C refinement.

## Audit an existing artifact

Run the bundled standard-library script against a `.framework` directory or its generated Objective-C header:

```bash
python3 scripts/audit_native_framework.py \
  --path /path/to/Shared.framework \
  --rules /path/to/native-framework-rules.json \
  --check \
  --json-out /path/to/native-framework-audit.json
```

The check fails when the header exceeds its reviewed limits, a required bridge is absent, or a forbidden symbol pattern is exported. Read [references/native-framework-boundaries.md](references/native-framework-boundaries.md) before changing Gradle or source visibility.

If no current artifact exists and verification is authorized, link a device debug framework first. Use a release link only when release verification is explicitly in scope.

## Review Gradle inputs

Run `$verify-kotlin-modules` with its dependency-visibility and native-framework rules enabled. Require explicit review for every project `api` edge and dependency export.

- Default project and library dependencies to `implementation`.
- Use `api` only when a public Kotlin signature truly exposes the dependency type to Kotlin consumers.
- Do not use `api` merely so an app shell, DI graph, or Swift caller can see an implementation. An optional aggregation root may deliberately re-export its own children as a documented Kotlin facade; record those exact edges as reviewed allowances.
- Do not add `framework.export(...)`, `export(project(...))`, `export = true`, or `transitiveExport = true` merely to expose Kotlin internals to Swift.
- Do not make `-Xdisable-phases` a permanent linker workaround. Keep Devirtualization and DCE enabled and narrow the reachable/public graph instead.

Do not confuse a reviewed Kotlin `api` edge with a native framework dependency export. The former controls Kotlin consumer compilation; the latter explicitly adds dependency declarations to the generated Apple framework API and requires separate justification.

## Interpret regressions

A much larger header, unexpected feature or implementation symbols, or sustained linker memory growth is a boundary regression. Find the declaration or dependency that widened reachability, narrow it behind the bridge, and rerun the static and artifact checks. Do not raise thresholds until the larger Swift contract is explicitly approved and documented.

Report the artifact inspected, header lines, declaration count, required/forbidden symbol results, dependency/export findings, commands run, and any platform behavior that remains unverified.
