# Build and modules

## Foundations

The root includes `plugins/` as a Gradle build and uses `gradle/libs.versions.toml` for versions, dependencies, and plugin aliases.

| Alias | Use |
|---|---|
| `libs.plugins.architecture.library` | Feature, core, util, and test KMP libraries |
| `libs.plugins.architecture.app` | Shared `composeApp` KMP framework |
| `libs.plugins.architecture.android.app` | Native Android application |

The library convention owns the Android KMP library target, `iosArm64`, `iosSimulatorArm64`, JDK 21, namespaces, coroutines/date-time, common tests, Android host tests, and the `configureBuild` extension.

## Capabilities

```kotlin
configureBuild {
    setup {
        usesDI = true
        usesNavigation = false
        isUiLibrary = false
        isDataLibrary = false
        usesSerialization = false
        exposeResources = false
    }
}
```

- `usesDI` enables Metro.
- `usesNavigation` enables Navigation 3 and route serialization.
- `isUiLibrary` enables Compose, resources, lifecycle, adaptive UI, and Coil.
- `isDataLibrary` enables Ktor, serialization, Room/KSP, SQLite, and DataStore.
- `usesSerialization` enables JSON contracts without the full data stack.
- `exposeResources` makes the Compose resource class public and must be deliberate.

Do not repeat platform/toolchain/source-set setup in leaf modules. Add a new focused capability when a dependency has independent consumers or expensive build effects.

## Variants

Android crosses environment and build type:

| Environment | Debug | Release |
|---|---|---|
| Dev | `devDebug` | `devRelease` |
| Prod | `prodDebug` | `prodRelease` |

Use `:androidApp:assembleDevDebug` for development and `:androidApp:bundleProdRelease` for store artifacts. iOS mirrors `DevDebug`, `DevRelease`, `ProdDebug`, and `ProdRelease`.

Environment selects app identity and future service configuration. Build type selects debuggability, diagnostics, shrinking, and optimization.

## Native boundary

`composeApp` produces the static `ComposeApp` framework. Swift accesses only `IosAppBridge`. Never export dependency modules, enable transitive export, or disable native optimization phases. Use implementation dependencies in ComposeApp and hide Kotlin-only public declarations from Objective-C.

## Module templates

Feature production roots re-export only their own domain/data/navigation/UI children. Domain stays pure; data depends downward; navigation owns routes; UI owns presentation. Optional shared UI and test support are not speculative.

Use `$migrate-kotlin-feature` for additional slices and `$design-gradle-conventions` for build capabilities.
