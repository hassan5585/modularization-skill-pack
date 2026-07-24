# Portable layered feature architecture

## Contents

1. Target graph
2. Module responsibilities
3. Dependency rules
4. Feature, core, and utility decisions
5. Adapting to the target stack
6. Kotlin platform variants
7. Common failure modes

## 1. Target graph

Use this as a default, not a reason to ignore the target repository:

```text
application / shared application shell
  -> feature:<name> aggregation roots
       -> feature:<name>:ui
       -> feature:<name>:shared-ui (optional)
       -> feature:<name>:data
       -> feature:<name>:navigation
       -> feature:<name>:domain

feature:<name>:ui
  -> feature:<name>:domain
  -> feature:<name>:navigation
  -> core:ui
  -> utility contracts
  -> own or another feature's shared-ui

feature:<name>:shared-ui (optional)
  -> feature:<name>:domain
  -> feature:<name>:navigation
  -> core:ui
  -> utility contracts

feature:<name>:data
  -> feature:<name>:domain
  -> core:data
  -> core:domain
  -> utility contracts and selected implementations

feature:<name>:navigation
  -> feature:<name>:domain when route contracts require domain primitives/enums
  -> core:navigation

feature:<name>:domain
  -> core:domain
  -> pure utility contracts

tests in each layer
  -> feature:<name>:test support
  -> shared test foundations
```

The aggregation root exists to give the app one feature dependency and one place for feature-level registration. It must not become a miscellaneous implementation module.

## 2. Module responsibilities

### Domain

Own business vocabulary and decisions:

- domain models and value objects;
- repository/service ports;
- use cases and policies;
- domain events and errors;
- pure validation and formatting that is part of the business contract.

Avoid UI state, UI resources, transport DTOs, database entities, network clients, Android/iOS framework types, and implementation DI wiring.

Serialization may be acceptable when serialization is itself part of a stable contract. Do not add it to all domain modules by habit.

### Data

Own integration implementations:

- repository implementations;
- network clients and endpoint adapters;
- request/response DTOs and mappers;
- database entities, DAOs, migrations, and caches;
- preference/data-store implementations;
- platform-backed data providers.

Expose domain types, not DTOs or database entities, across the boundary.

### Navigation

Own stable feature entry contracts:

- route or destination declarations;
- supported primitive/serializable arguments;
- deep-link contracts and result contracts;
- feature navigation graph declarations when the navigation framework permits separation.

Graph-to-screen registration may remain in UI if it needs UI implementation types. Keep route identity stable during moves.

### UI

Own presentation:

- screens/views/composables/fragments;
- ViewModels, presenters, controllers, and UI state;
- feature UI models and UI-only formatters;
- feature resources and UI widgets;
- adapters between navigation entries and screens.

UI depends on domain ports. It should not instantiate or import data implementations directly.

### Shared UI

Own feature-specific presentation reused by one or more feature UI modules:

- reusable views/composables and their resources;
- UI models, display formatters, and presentation helpers;
- provider-owned interaction contracts that remain UI concerns.

Apply the same platform/UI conventions as regular UI, but keep the dependency
role distinct. A shared-UI module sits below every consuming UI. It must not
depend on a regular feature UI, a feature aggregation root, or any other
shared-UI module. Keep app-wide design-system primitives in core UI.

### Test support

Own reusable testing infrastructure, not test cases:

- handwritten fakes;
- recording adapters;
- fixtures, object mothers, and builders;
- deterministic clocks, dispatchers, and IDs scoped to the feature;
- shared assertions only when multiple owning tests use them.

Put it on test classpaths only. If domain tests need it, the test-support module must not depend back on that domain module; split downstream-safe contracts or fixtures when necessary.

## 3. Dependency rules

The most important property is direction, not the number of modules.

| From | Usually allowed | Usually forbidden |
|---|---|---|
| domain | core domain, pure utility contracts | data, UI, shared UI, navigation UI, HTTP, DB, platform UI |
| data | own domain, core data/domain, utility contracts/real | UI, shared UI, navigation UI, other feature implementation |
| navigation | own domain, core navigation, route serialization | data implementation, UI/shared-UI implementation |
| shared UI | owner domain/navigation, core UI, utility contracts | feature UI/root, data, every other shared UI |
| UI | own domain/navigation, core UI, utility contracts, approved feature shared UI | own data implementation, unrelated feature UI |
| aggregation | own production layers | test support, behavior implementation |
| test support | downstream-safe contracts and shared test foundations | production app/aggregation, same module when it creates a cycle |

Cross-feature dependencies require a design decision. Prefer:

1. a destination/entry contract;
2. an app-wide domain contract in core;
3. a reusable utility contract;
4. an explicitly named shared feature contract;
5. provider-owned `shared-ui` when the dependency is specifically UI reuse.

Allow `feature:B:ui -> feature:A:shared-ui` directly. Do not allow
`feature:B:ui -> feature:A:ui` or any `shared-ui -> shared-ui` chain.

## 4. Feature, core, and utility decisions

Ask these questions in order:

1. Does the code express one product capability and change with it? Keep it in that feature.
2. Is it a stable foundation used by many unrelated features? Consider `core`.
3. Is it an independently replaceable cross-cutting capability with a contract and implementation, such as authentication, analytics, permissions, or platform services? Consider `util:<name>:domain/real[/ui]`.
4. Is it shared by exactly two features because one calls the other? Prefer a narrow contract owned by the providing feature or app shell before promoting to core.
5. Is the shared surface UI owned by the provider? Consider the provider’s optional `shared-ui`.
6. Is the abstraction speculative? Leave it with the first owner.

High fan-in alone does not make a concept core. Volatility and semantic ownership matter.

## 5. Adapting to the target stack

Map libraries to capabilities:

| Capability | Examples of evidence | Architectural effect |
|---|---|---|
| UI | Compose, XML views, SwiftUI bridge, JavaFX | UI plugin and resource/source-set setup |
| Navigation | Navigation 2/3, Decompose, Voyager, custom router | destination contracts and graph wiring |
| DI | Metro, Dagger/Hilt, Koin, manual factories | aggregation and generated-code registration |
| Network | Ktor, Retrofit, OkHttp, GraphQL client | data capability only |
| Persistence | Room, SQLDelight, Realm, JDBC | data capability, schemas/migrations |
| Serialization | kotlinx.serialization, Moshi, Gson | DTOs; domain only when contract requires it |
| Async | coroutines/Flow, RxJava | domain contracts may expose stable abstractions |
| Tests | kotlin.test, JUnit, Turbine, MockEngine, fakes | base and test-support conventions |

Do not copy plugin IDs or dependency aliases from another repository. Detect them in the target build.

## 6. Kotlin platform variants

### Kotlin Multiplatform

- Default shared behavior to `commonMain` and tests to `commonTest`.
- Preserve existing target hierarchy and intermediate source sets.
- Put platform implementations in matching platform source sets.
- Verify native frameworks/exports, CocoaPods/SwiftPM interop, resource generation, and host tests.

### Android-only

- Use Android library modules and existing `src/main`, unit-test, and instrumented-test source sets.
- Preserve namespaces, manifests, consumer rules, build features, flavors, and resource IDs.
- Avoid moving app-only plugins or signing into feature libraries.

### JVM/server/desktop

- Use Kotlin/JVM or Java-library conventions.
- Preserve application/plugin entry points, service loaders, resources, and integration-test source sets.
- Navigation may mean command routing, HTTP routing, or desktop navigation; retain the layer only when it represents a stable entry contract.

### Mixed repositories

Create platform-specific base conventions and share capability plugins only where APIs are compatible. Do not force Android and KMP modules through one typed extension if it obscures different source sets or variants.

## 7. Common failure modes

- Moving files before defining dependency direction.
- Treating technical packages as features.
- Creating a `common` dumping ground.
- Making domain serializable/UI-aware because it is convenient.
- Letting UI depend on data implementations.
- Letting regular feature UIs depend directly on each other.
- Chaining feature shared-UI modules instead of composing at the consumer.
- Adding every library through the base plugin.
- Putting test fakes in production modules.
- Creating test-support cycles.
- Breaking route, wire, schema, or resource identity during package moves.
- Migrating all layers horizontally instead of completing one vertical slice.
- Deleting old code before app registration and dependent modules compile.
