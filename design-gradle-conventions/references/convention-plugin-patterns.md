# Convention plugin design patterns

## Contents

1. Included build layout
2. Plugin decomposition
3. Version catalogs and plugin classpaths
4. Platform base patterns
5. Capability patterns
6. Module application matrix
7. Migration and validation

## 1. Included build layout

A typical isolated build-logic project is:

```text
build-logic/
  settings.gradle.kts
  convention/
    build.gradle.kts
    src/main/kotlin/com/example/buildlogic/
      KotlinLibraryConventionPlugin.kt
      AndroidLibraryConventionPlugin.kt
      MultiplatformLibraryConventionPlugin.kt
      UiConventionPlugin.kt
      DataConventionPlugin.kt
      NavigationConventionPlugin.kt
      SerializationConventionPlugin.kt
      DiConventionPlugin.kt
      UnitTestConventionPlugin.kt
```

Register the included build in root `settings.gradle.kts`:

```kotlin
pluginManagement {
    includeBuild("build-logic")
}
```

If the repository already uses `plugins/`, `buildSrc`, or an included build, extend it unless isolation or migration constraints justify a replacement.

## 2. Plugin decomposition

Use a platform base for invariants:

- language/platform plugin;
- toolchain and compiler defaults;
- target/source-set creation;
- namespace convention;
- baseline unit-test source sets.

Use capability plugins for optional behavior:

- UI toolkit and resources;
- navigation;
- serialization;
- DI/code generation;
- network/database/data stores;
- reusable test fixtures;
- publishing or native export.

Keep app/release plugins separate because signing, credentials, environment files, distribution, and application IDs do not belong on libraries.

Avoid hidden dependency bloat. A base KMP library plugin should not make every domain module compile database, HTTP, UI, or code-generation plugins.

## 3. Version catalogs and plugin classpaths

The root version catalog is not automatically available to every included build. In build-logic settings, import it deliberately when desired:

```kotlin
dependencyResolutionManagement {
    versionCatalogs {
        create("libs") {
            from(files("../gradle/libs.versions.toml"))
        }
    }
}
```

Imperative plugin classes that configure typed AGP/Kotlin/Compose/KSP extensions need their Gradle plugin artifacts on the convention project compile classpath:

```kotlin
dependencies {
    compileOnly(libs.android.gradle.plugin)
    compileOnly(libs.kotlin.multiplatform.gradle.plugin)
}
```

The exact artifact aliases come from the target project. Do not guess coordinates when the catalog already provides them.

Applying a plugin by string ID is insufficient if the plugin implementation is absent from the target/plugin classpath. Compile the included build and apply each convention to a representative module to prove resolution.

## 4. Platform base patterns

### KMP library

Configure only detected targets and preserve the existing source-set hierarchy. Centralize toolchain, compiler options, Android target settings when present, and baseline tests. Do not create iOS/JVM/JS targets the project does not use.

### Android library

Centralize compile/min SDK, Java/Kotlin toolchains, namespace derivation, manifest defaults, packaging, and unit-test defaults. Leave resource/build-feature activation to capability plugins where possible.

### JVM library/application

Centralize Kotlin/JVM, Java toolchains, compiler options, test platform, and resource defaults. Keep application entry-point configuration separate from libraries.

## 5. Capability patterns

### UI

Apply only the UI/compiler/resource plugins actually used. Add dependencies to the correct source set. Configure resource visibility, compiler metrics, previews, or Android build features only where needed.

### Data

Data is often too broad for one plugin. If the project has data modules that do not all use both network and database stacks, split `network`, `database`, and `serialization` capabilities. Configure schemas and code generation in the owning module.

### Navigation

Add the detected navigation runtime and route serialization. Keep app graph wiring outside a library plugin.

### DI/code generation

Apply the detected compiler/plugin and runtime. Centralize stable compiler flags. Do not auto-register application graph modules from Gradle.

### Tests

Separate two concerns:

- an **owning-module unit-test convention** creates/configures the target project’s portable/JVM/Android/native test source sets and tasks, adds the approved base test libraries, and attaches required tests to `check`;
- a **test-support library convention** creates a normal library whose main/common source set contains reusable fakes/fixtures, but which is consumed only from test configurations.

Add shared test foundations only when the dependency graph does not cycle. Keep instrumentation/UI tests separate from portable/common tests. Do not add every feature’s support module globally from a base convention; add it only to the owning test source sets that need it.

## 6. Module application matrix

| Role | Base | Typical capabilities |
|---|---|---|
| feature domain | KMP/Android/JVM library | serialization only if contract needs it, DI annotations if required, unit tests |
| feature data | library | serialization, network, database, DI, unit tests as detected |
| feature navigation | library | navigation, route serialization, unit tests |
| feature UI | library | UI/resources, navigation UI, DI, UI/unit tests |
| feature test support | library | fixtures/test libraries; no app/release |
| feature aggregation | library | DI/aggregation only; child module dependencies |
| core domain/data/navigation/UI | matching library | only the corresponding capability |
| app/shared app | app base | feature roots, app DI, environment/release as needed |

The matrix must name both the owning-module test convention and the test-support library convention when reusable support modules are part of the approved architecture.

## 7. Migration and validation

For one representative module, compare before and after:

- applied plugins;
- target/variant/source-set list;
- compile/runtime/test dependency reports;
- compiler flags and toolchain;
- resource/generated-source directories;
- code-generation tasks;
- unit/instrumented/native test tasks;
- publishing/framework outputs.

Only then convert modules of the same role. A convention that compiles but changes target variants or test discovery is not equivalent.
