# Kotlin/Native framework boundary rules

## Contents

1. Dependency visibility
2. Swift export boundary
3. Compiler and linker behavior
4. Verification workflow

## 1. Dependency visibility

Use `implementation` by default. An `api` dependency is justified when a declaration intentionally exposed to Kotlin consumers contains a type from that dependency, or when an optional aggregation root is explicitly designed as the app-facing Kotlin facade for its own production children. DI discovery and same-repository access alone are not sufficient reasons.

Review public declarations and dependency configurations together. A small header can still hide an unnecessarily broad Kotlin compile contract, while a narrow Gradle graph can still export too many public declarations from the framework-producing module. Kotlin `api` and Apple framework dependency export are distinct contracts; approve and verify them independently.

## 2. Swift export boundary

Application frameworks should normally expose a small app-owned facade. Keep these behind it:

- dependency graphs and factories;
- repositories and data implementations;
- ViewModels and feature presentation models;
- navigation and notification implementations;
- third-party CocoaPods or SwiftPM types;
- generated resource and DI APIs.

Prefer `internal` for same-module Kotlin declarations. Use `@HiddenFromObjC` for public cross-module Kotlin declarations that Swift must not call when the target Kotlin version supports it. Do not solve visibility by exporting dependency modules or enabling transitive export.

A reusable library may intentionally export a broader contract, but every dependency export and header symbol must be part of its documented consumer API. Record exact exceptions; do not use a blanket export convention.

## 3. Compiler and linker behavior

Kotlin/Native release optimization performs whole-program analysis. Broad public/reachable graphs can make Devirtualization and dead-code elimination expensive in time and memory. Disabling those phases can prove a diagnosis, but it is not a durable architecture fix and may increase binary size or reduce optimization.

Treat these as signals of a boundary problem:

- a generated Objective-C header grows sharply;
- repositories, ViewModels, graphs, or feature internals appear in it;
- `linkReleaseFramework*` memory grows for long periods;
- the same link succeeds only with Devirtualization/DCE disabled;
- dependency export or broad `api` edges were recently introduced.

## 4. Verification workflow

1. Audit the most recent existing framework without rebuilding.
2. Compare its header line/declaration counts and symbol set with the reviewed baseline.
3. Run static module verification for public dependency and native export rules.
4. For an intentional boundary change, link a device debug framework and audit it explicitly.
5. Run the release link only when release verification is required.
6. Inspect Kotlin build reports, binary size, and peak memory when diagnosing performance.

Keep thresholds repository-specific. Establish them from an approved narrow bridge and tighten them when the contract shrinks; never copy another application’s counts as universal limits.
