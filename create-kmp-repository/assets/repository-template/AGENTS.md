# AGENTS.md — @@APP_NAME@@

This repository is an Android+iOS Kotlin Multiplatform app. Read the focused documents in `docs/` before changing their concern.

## Stack

| Concern | Choice |
|---|---|
| UI | Compose Multiplatform + Material 3 |
| DI | Metro compile-time DI |
| Navigation | AndroidX Navigation 3 with app-owned contracts |
| Networking | Ktor + kotlinx serialization |
| Persistence | Room KMP + SQLite + DataStore |
| Async | Coroutines + Flow |
| Images | Coil 3 |
| Tests | kotlin.test, coroutines-test, Turbine, Ktor MockEngine, handwritten fakes |
| Package | `@@PACKAGE@@` |
| Targets | Android 26+ / iOS 17.2+ |
| JDK | 21 |

## Modules

```text
androidApp/            Android entry and packaging
composeApp/            Shared app and only Swift-consumed framework
iosApp/                Native SwiftUI host
core/{domain,data,navigation,ui}/
feature/{name}/{domain,data,navigation,ui,test?}/
util/{name}/{domain,real,ui?}/
test/                  Production-independent test helpers
test/core/             Downstream-safe core-contract fakes
plugins/convention/    Included build conventions
```

Every feature has an aggregation root and four production layers. Add `shared-ui` only for demonstrated provider-owned reuse; it must not depend on another shared UI. Add `test` only for reusable fakes/fixtures and never aggregate it into production.

## Dependency direction

- Domain is pure policy and contracts. It must not know UI, HTTP, databases, or implementations.
- Data implements domain ports and owns DTOs, mappers, network, persistence, and caches.
- Navigation owns serializable destination contracts and stable destination IDs.
- UI owns screens, ViewModels, state, UI models, resources, and display formatting.
- Features depend on utility contracts, not platform implementations, unless the composition root intentionally wires them.
- Default to `implementation`. Use `api` only for a public signature or documented aggregation façade.
- Never put a test-support module on a production dependency path.

## Build

Use convention plugins from `plugins/`; do not repeat platform setup in leaf modules. `configureBuild.setup` enables `usesDI`, `usesNavigation`, `isUiLibrary`, `isDataLibrary`, `usesSerialization`, and intentional `exposeResources`.

Android environments (`dev`, `prod`) are independent of build types (`debug`, `release`). iOS mirrors the same four combinations. Secrets and signing credentials are never committed.

`ComposeApp` is the only framework Swift consumes. Keep dependency modules implementation-only, expose only `IosAppBridge` intentionally, and never add framework exports, transitive exports, or disabled native optimization phases.

## Code rules

- Default to `commonMain`; use platform source sets only for real platform boundaries.
- Prefer constructor injection. Use providers only for runtime/platform/third-party factories.
- Repository implementations are internal `Real*Repository` classes behind domain interfaces.
- Fallible repository APIs return typed results or Flow-style contracts.
- Destinations use `@Serializable`, explicit `@SerialName`, stable IDs, and primitive/enum parameters only.
- ViewModels are internal, extend `BaseViewModel`, expose immutable state, and dispatch every intent branch to a private function.
- Use the `launch {}` ViewModel extension; do not call `viewModelScope.launch` directly.
- Collect screen state with `collectAsStateWithLifecycle()`.
- Keep business and display formatting out of composables.
- Put user-facing strings in the owning module’s Compose resources.
- Prefer core UI primitives over raw Material components when an equivalent exists.
- Provide accessibility labels for actionable/non-decorative visual content.

## Tests

New or changed testable behavior ships with unit tests. Prefer `commonTest` for `commonMain`; construct subjects directly with handwritten fakes. Do not add mocking frameworks or live service/device dependencies.

Run touched modules with `testAndroidHostTest` and portable iOS tests when practical. The convention attaches Android host tests to `check`.

## Documentation

- Update `feature/{name}/Feature.MD` whenever feature behavior changes.
- Every renderable destination has `assistant/screens/{Destination}_help.MD`; update it with screen changes.
- Update `assistant/Features.MD` only for app-wide feature/navigation landmarks.
- Structural graph roots do not need help files.

## Verification

```bash
python3 scripts/verify_repository.py
./gradlew :plugins:convention:build
./gradlew testAndroidHostTest
./gradlew :androidApp:assembleDevDebug
```

Use repository-local skills in `.agents/skills` for architecture audits, convention changes, feature work, native framework audits, and verification.
