# Source repository audit

## Contents

1. [Audit scope](#audit-scope)
2. [Generalized foundation](#generalized-foundation)
3. [Architecture and module shape](#architecture-and-module-shape)
4. [Build and dependency management](#build-and-dependency-management)
5. [Android and iOS applications](#android-and-ios-applications)
6. [Runtime architecture](#runtime-architecture)
7. [Quality and developer tooling](#quality-and-developer-tooling)
8. [Documentation conventions](#documentation-conventions)
9. [Excluded product-specific material](#excluded-product-specific-material)

## Audit scope

The source audit covered the root and included Gradle builds, version catalog, convention plugin sources, 120 build files, 2,416 Kotlin/Java sources, 365 resource/native artifacts, Android and iOS application configuration, the 13 feature families, core and utility modules, shared test infrastructure, CI, release scripts, architecture checks, and normative documentation.

The audit used the pack’s architecture and Gradle analyzers, then manually inspected representative build files and platform entry points. No production source was copied wholesale. Patterns were classified as portable foundation, optional integration, or product-specific behavior.

## Generalized foundation

The generated blueprint brings forward:

- Android+iOS KMP with `commonMain` as the default implementation location;
- Compose Multiplatform Material 3, adaptive dependencies, lifecycle-aware state, and Compose resources;
- Android KMP library targets plus `iosArm64` and `iosSimulatorArm64`;
- JDK 21, Gradle build cache, Kotlin/Native incremental compilation, and build reports;
- a version catalog and included convention-plugin build;
- capability-driven module configuration rather than repeated raw Gradle blocks;
- four-layer feature slices, core foundations, cross-cutting util slices, and explicit test support;
- independent dev/prod environments and debug/release build types;
- a single static ComposeApp framework with a narrow Swift bridge;
- Metro compile-time dependency injection conventions;
- Navigation 3 destination contracts with stable IDs and primitive route fields;
- Ktor, kotlinx serialization, Room, SQLite, DataStore, and typed result/error foundations;
- design-system ownership in core UI and feature-owned resources;
- MVI ViewModels with immutable state, intent dispatch, lifecycle-aware collection, and controlled coroutines;
- kotlin.test, coroutines-test, Turbine, MockEngine, handwritten fakes, common tests, and Android host tests;
- architecture documentation, repository rules, structural verification, and CI checks.

## Architecture and module shape

### Application and core

- `androidApp` owns Android application packaging and platform startup.
- `composeApp` owns shared application composition and the only Swift-consumed framework.
- `iosApp` is a small native SwiftUI host.
- `core:domain` owns app-wide pure contracts, result/error primitives, and scopes.
- `core:data` owns shared data infrastructure, not arbitrary feature repositories.
- `core:navigation` owns destination and navigator abstractions.
- `core:ui` owns theme, shared widgets, responsive foundations, ViewModel base behavior, and resource access.

### Features

The portable feature contract is an aggregation root plus `domain`, `data`, `navigation`, and `ui`. Optional `shared-ui` is provider-owned, never chains to another shared UI, and appears only after demonstrated reuse. Optional `test` contains reusable fakes/fixtures and never enters production aggregation.

Dependency direction remains domain-first. UI does not depend on data implementations. Navigation owns route types. Data implements domain ports. Aggregation roots re-export only documented production children.

### Utilities

Cross-cutting capabilities use `util/{name}/domain` and `real`, with optional `ui`. Feature code prefers utility contracts. Platform-specific `actual` code lives in real/platform source sets.

### Public API policy

Leaf dependencies default to `implementation`. `api` is reserved for public Kotlin signatures and documented aggregation façades. ComposeApp implementation dependencies are not exported to Swift.

## Build and dependency management

### Included build

The source repository uses `plugins/` as an included build and `plugins/convention` for implementation classes. The generated form keeps public app, Android app, and KMP library plugins; internal capabilities configure UI, data, navigation, serialization, DI, and tests.

### Base KMP convention

The base convention generalizes:

- Android namespace derivation from package plus Gradle path;
- compile/min SDK values from the catalog;
- iOS device and Apple Silicon simulator targets;
- JDK toolchain and shared language opt-ins;
- baseline coroutines/date-time dependencies;
- Android host-test source-set setup;
- kotlin.test, coroutines-test, and Turbine;
- `check` depending on host tests;
- the `configureBuild` capability extension.

### Capability conventions

- UI: Compose/compiler, resources, Material 3, adaptive layout, lifecycle, Coil, optional public resources, compiler metrics/reports.
- Data: serialization, KSP, Room schemas/compiler targets, Ktor, bundled SQLite, and DataStore.
- Navigation: Navigation 3 runtime/UI and serialization.
- DI: Metro compiler and contribution providers.
- Serialization: JSON contracts without the full data stack.

### Build behavior

The portable Gradle properties retain build caching, native incremental compilation, file build reports, bounded workers, AndroidX, non-transitive R classes, and explicit JVM memory. Configuration cache is not enabled by default because native linking behavior should be proven per project.

## Android and iOS applications

### Android

The source repository crosses an `environment` flavor dimension with standard build types. The generalized plugin keeps `dev` and `prod`, application ID/display-name suffixes, `APP_ENVIRONMENT`, release minification/resource shrinking, optimized ProGuard defaults, packaging exclusions, and full native symbols. It removes mandatory signing and Firebase plugins so a new repository builds immediately.

### iOS

The source repository mirrors environments with four Xcode configurations and shared schemes. The generated project keeps `DevDebug`, `DevRelease`, `ProdDebug`, and `ProdRelease`, environment xcconfigs, framework build-type mapping, a Gradle embed/sign phase, iOS 17.2 minimum, and a SwiftUI host.

The generated static framework exposes `IosAppBridge`; app composition is hidden from Objective-C. It does not export dependency modules or disable native optimization phases.

## Runtime architecture

### Dependency injection

Metro remains constructor-injection first. Implementations can contribute bindings at app scope. Providers are reserved for runtime/platform/third-party factories. Platform graphs and session scopes are patterns to add when needed; the empty starter does not fabricate a session model.

### Navigation

Destinations are serializable, stable-ID contracts in feature navigation modules. Route parameters remain primitive, nullable primitive, or enum. The generated foundation includes a portable navigator; a real feature can add the full Navigation 3 host without changing ownership boundaries.

### State and UI

The blueprint carries forward `BaseViewModel`, immutable state expectations, nested State/Intent conventions, lifecycle-aware collection, `launch {}` over direct `viewModelScope.launch`, display-ready state, resource-backed UI strings, durable lazy keys, and app-window-based adaptive decisions.

### Data

Domain repositories return typed results or flows. Data implementations are internal `Real*Repository` classes. Shared Ktor clients and `safeCall` map representative network/serialization failures while preserving coroutine cancellation. Room schemas and migrations belong to the owning data module.

## Quality and developer tooling

The source repository contains more than 30 focused scripts covering module shape, layer boundaries, registration, platform imports, navigation contracts, repository results, serialization, ViewModel/MVI rules, coroutine use, Compose state collection, hardcoded strings, resources, accessibility, Room versions, native link surface, and releases.

The greenfield repository installs the portable skill pack and adds a fast structural verifier plus CI. This avoids copying product/path-specific scripts while keeping their capabilities available through the sibling audit, convention, migration, native-framework, and verification skills.

Testing conventions generalized into the starter:

- commonTest for commonMain behavior;
- Android host tests wired to `check`;
- iOS simulator tests where practical;
- kotlin.test, coroutines-test, Turbine, Ktor MockEngine;
- direct construction and handwritten fakes;
- shared production-independent helpers in `:test`;
- core-contract fakes in `:test:core` only for downstream consumers;
- feature fakes in feature test-support modules;
- no mocking framework or live external services.

## Documentation conventions

The generated repository includes:

- root `AGENTS.md` as the architecture hub;
- focused BUILD, DI, NAVIGATION, MVI, DATA, UI, and TESTING references;
- one `Feature.MD` per feature;
- an app-wide `assistant/Features.MD` hub;
- one help file for the sample destination;
- the rule that screen changes update help and feature documentation;
- a bootstrap manifest recording inputs, modules, variants, installed skills, and first checks.

## Excluded product-specific material

The audit intentionally excludes existing feature names/behavior, roles and permissions, healthcare/NDIS models, country policy, support prompts, product copy, branded resources, Firebase projects, backend routes, OAuth clients, maps/stream keys, database schemas, deep-link hosts, notification services, widgets, release credentials, store upload automation, and current build/version numbers.

These are useful patterns but not valid defaults for unrelated applications. Their architectural extension points remain available without copying their identities or secrets.
