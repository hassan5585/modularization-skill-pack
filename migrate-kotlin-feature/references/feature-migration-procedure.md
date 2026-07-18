# Feature migration procedure

## Contents

1. Preflight
2. Target module contract
3. Dependency-first batches
4. Registration checklist
5. Source and package moves
6. High-risk identities
7. Definition of done

## 1. Preflight

Before editing:

- read repository instructions and feature documentation;
- confirm the approved feature boundary and file inventory;
- inspect the working tree;
- run or record baseline checks;
- identify generated sources/resources and never move generated output;
- list consumers outside the feature;
- list DI, navigation, serialization, database, manifest, native, and app registrations;
- create a feature spec using existing plugin IDs and dependency aliases.

## 2. Target module contract

Default shape:

```text
feature/<name>/
  build.gradle.kts
  src/.../aggregation or DI registration
  domain/
  data/
  navigation/
  ui/
  test/
```

The `test` child is reusable test support. Actual tests stay under each owning layer’s test source set.

Create repository-level `:test`-style foundations only when production-independent helpers have multiple module consumers. Create a core-contract fake module only for downstream feature/utility tests; core modules must not consume a fake module that depends back on core. Use the test-foundation scaffold spec as a reviewed starting point.

The feature root may be omitted when the app deliberately depends on layers directly. If present, it aggregates production layers and may own feature-level DI/registration. It never depends on test support.

## 3. Dependency-first batches

### Batch A: contracts

Move domain value types and ports needed by the rest of the feature. Preserve public signatures where possible. If old packages have many consumers, add narrow type aliases or forwarding contracts and schedule their removal.

### Batch B: pure behavior and tests

Move use cases, policies, validators, and their tests. This proves the domain module without framework dependencies.

### Batch C: test support

Move fakes/fixtures after checking consumers and cycles. If domain tests need a fake of a domain interface, either keep a local fake or place downstream-safe contracts in shared test foundations; do not make `domain -> test -> domain`.

### Batch D: data

Move DTOs, entities, mappers, repositories, clients, DAOs, and caches. Keep API/database identity stable. Move schema files and code-generation configuration with the owning module.

### Batch E: navigation

Move stable route/destination types and deep-link contracts. Keep screen construction in UI if it requires UI implementations.

### Batch F: UI

Move presentation state, controllers/ViewModels, screens, resources, and UI helpers. Update generated resource imports and preview/test source sets.

### Batch G: wiring and cleanup

Register settings, app dependencies, DI, navigation, serializers, manifests, and native exports. Compile app/platform deliverables. Remove legacy sources and adapters.

## 4. Registration checklist

Inspect the target project for:

- `include(...)`/project discovery in settings;
- application/shared-app project dependencies;
- DI graph modules, scopes, bindings, factories, and generated contributions;
- navigation graphs, route serializers, deep links, and destination preferences;
- JSON polymorphic serializers or service-loader entries;
- Android manifests, resources, consumer ProGuard rules, and build features;
- database schemas/migrations and KSP/KAPT outputs;
- KMP target/source-set dependencies and native framework exports;
- CI task lists, lint baselines, and test aggregation.

Search by the old package and key class names after each registration step.

## 5. Source and package moves

Use explicit manifests. For each file:

1. Confirm semantic owner and target layer.
2. Preserve source-set platform (`commonMain`, `androidMain`, `iosMain`, `main`, `test`, etc.).
3. Derive target package from repository rules.
4. Move the file.
5. Change only its package declaration first.
6. Update imports and fully qualified references using repository search.
7. Compile the narrowest target.

Avoid global replacement when package text may occur in serialized names, database schemas, manifests, ProGuard rules, reflection, or documentation examples.

## 6. High-risk identities

Preserve unless explicitly migrating:

- serialized field/class names and discriminators;
- route IDs, deep-link URLs, argument keys, and back-stack semantics;
- database table/column names, schema locations, migrations, and preference keys;
- resource names referenced from native or external code;
- application IDs, namespaces, manifest authorities, and service names;
- reflection/service-loader names and shrinker rules;
- iOS framework/module names and exported symbols.

Package moves can change generated or reflection identity even when Kotlin compilation succeeds. Run the relevant packaging/linking tests.

## 7. Definition of done

- Target layers compile with intended conventions.
- Layer-local changed behavior has tests.
- Direct dependents and app compile.
- DI, navigation, resources, generated code, persistence, and platform wiring work.
- Architecture checks show no new forbidden edges or cycles.
- Test support is absent from production dependency graphs.
- Old sources, duplicate resources, and obsolete registrations are removed.
- Temporary compatibility code has been removed or has a named owner and deletion condition.
- Feature and architecture documentation identify the new modules and entry points.
