# Generated repository contract

## Contents

The generator creates a greenfield Android+iOS KMP repository with:

- shared `composeApp`, native `androidApp`, and SwiftUI `iosApp` shells;
- an included `plugins` build and a version catalog;
- `core:domain`, `core:data`, `core:navigation`, and `core:ui` foundations;
- a runnable `feature:home` vertical slice with domain, data, navigation, UI, and test-support modules;
- a `util:platform` domain/real split demonstrating portable `expect`/`actual` boundaries;
- repository-wide `:test` helpers and downstream-safe `:test:core` fakes;
- dev/prod environments crossed with debug/release build types;
- static Compose iOS framework output with one deliberate Swift bridge;
- common test, Android host-test, and portable iOS test support;
- Compose compiler stability/report configuration;
- architecture, build, DI, navigation, state, data, UI, and testing documentation;
- a structural repository verifier and GitHub Actions workflow;
- the complete modularization skill pack under `.agents/skills` when the source pack is available.

## Module dependency contract

```text
androidApp -> composeApp
iosApp     -> ComposeApp.framework

composeApp -> core + feature/home + util/platform

feature/home
  -> domain
  -> data       -> domain + core/data + core/domain
  -> navigation -> domain + core/navigation
  -> ui         -> domain + navigation + core/ui + util/platform/domain

core
  -> domain
  -> data       -> domain
  -> navigation -> domain
  -> ui         -> domain + navigation

util/platform
  -> domain
  -> real -> domain

test/core -> core production contracts
feature/home/test -> home domain + test/core
```

Aggregation roots re-export only their own production children. Test-support modules never enter a production aggregation root.

## Convention plugins

The included build exposes three public plugins:

| Alias | Role |
|---|---|
| `architecture.library` | KMP library baseline for feature, core, util, and test modules |
| `architecture.app` | Shared KMP application framework |
| `architecture.android.app` | Native Android application and variants |

`configureBuild.setup` composes these capabilities:

- `usesDI`: Metro compiler/contribution support.
- `usesNavigation`: Navigation 3 runtime/UI and route serialization.
- `isUiLibrary`: Compose Multiplatform, lifecycle, resources, adaptive UI, and Coil.
- `isDataLibrary`: Ktor, serialization, Room/KSP, SQLite, and DataStore.
- `usesSerialization`: kotlinx serialization without the full data stack.
- `exposeResources`: intentional public Compose resource access.

The base KMP convention owns Android KMP target configuration, iOS device/simulator targets, JDK 21, namespace derivation, coroutines/date-time, common tests, Android host tests, and `check` integration.

## Variant matrix

Environment and build type stay independent:

| Environment | Debug | Release | Identity |
|---|---|---|---|
| Dev | `devDebug` | `devRelease` | package suffix `.dev`, display suffix ` Dev` |
| Prod | `prodDebug` | `prodRelease` | requested package/display name |

iOS mirrors this as `DevDebug`, `DevRelease`, `ProdDebug`, and `ProdRelease`. Environment selects identity and future service configuration; build type selects diagnostics and optimization.

## Deliberate non-goals

The template never invents or copies:

- API endpoints, OAuth clients, Firebase projects, maps keys, notification credentials, or other service secrets;
- Android signing keys, Apple developer team IDs, provisioning profiles, store credentials, or upload automation;
- product roles, backend DTOs, database schemas, permissions, analytics taxonomies, deep-link hosts, widgets, or business features;
- fonts, icons, logos, color branding, legal copy, or accessibility claims specific to another product;
- exported dependency frameworks or broad Swift-visible Kotlin APIs.

Add those only as explicit post-generation work.

## Generated source guarantees

- Package paths and declarations derive from the requested package.
- `rootProject.name` derives from the destination folder.
- Human-facing starter text derives from the requested app name.
- No unresolved template token may remain.
- The destination must not exist; generation never merges or overwrites.
- The write occurs in a sibling staging directory and moves into place only after structural validation.
