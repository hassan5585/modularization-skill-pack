# Post-generation customization

## First product decisions

After the base repository verifies, decide these in product order:

1. Brand palette, typography, icons, launch assets, and accessible copy.
2. Dev/prod backend URLs and non-secret environment values.
3. Authentication and session ownership.
4. Persistence schemas and migration policy.
5. First real feature boundary and navigation entry point.
6. Android signing and Apple developer identities.
7. Analytics, crash reporting, notifications, deep links, and distribution services.

Keep secrets in ignored local files, environment variables, or CI secret stores. Do not commit credentials to build logic or generated sources.

## Add a feature

Prefer the installed `$migrate-kotlin-feature` skill and its deterministic scaffold. A feature normally owns:

```text
feature/{name}/
  build.gradle.kts
  Feature.MD
  domain/
  data/
  navigation/
  ui/
  test/        # only for reusable fakes/fixtures
  shared-ui/   # only for demonstrated provider-owned reuse
```

Register children in `settings.gradle.kts`, aggregate production children in the feature root, add the feature aggregation root to `composeApp`, and wire the graph from the feature UI module. Never put the feature test module on a production path.

## Add a utility

Use `util/{capability}/domain` for portable interfaces/models and `util/{capability}/real` for implementations. Add `ui` only when the utility owns UI. Depend on domain contracts from features; keep platform implementation details in the real module and platform source sets.

## Add an integration

Extend `gradle/libs.versions.toml`, then update or add one focused convention capability through `$design-gradle-conventions`. Avoid growing the base library plugin with dependencies that only some modules need.

Common integration placement:

- Firebase/auth/analytics/notifications: utility domain/real modules plus platform graph inputs.
- HTTP services: feature data modules using core Ktor infrastructure.
- Room databases: owning data module, checked-in schemas, explicit migrations.
- Maps/files/payments: utility contracts plus platform implementations; expose UI only when reusable.
- SwiftPM packages: `composeApp` only when used by the app framework; keep imported types behind internal Kotlin/platform adapters.

## Native framework checks

Swift should enter Kotlin through `IosAppBridge`. Keep app graphs, repositories, ViewModels, feature models, and imported SwiftPM types out of the generated header. Never add `framework.export`, `transitiveExport`, or disabled Devirtualization/DCE phases as a shortcut.

After public API, bridge, SwiftPM, or native dependency changes, use `$audit-kotlin-native-framework` against a freshly linked device framework.

## Release setup

The base project has release-capable build types but no credentials or store upload workflow. Add release automation only after application identifiers and signing ownership are final. Prefer:

- `BUILD_NUMBER` from CI with a repository default;
- release branches named `release/x.y.z` only if that workflow is desired;
- Android AAB plus native symbols;
- Xcode archives with explicit environment/release schemes;
- separate verification from upload, and dry-run before external publication.
