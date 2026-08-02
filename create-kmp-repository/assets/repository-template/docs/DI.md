# Metro dependency injection

Prefer constructor injection for app-owned repositories, use cases, formatters, managers, navigators, and ViewModels.

```kotlin
@ContributesBinding(AppScope::class, binding = binding<ThingRepository>())
internal class RealThingRepository @Inject constructor(
    private val client: HttpClient,
) : ThingRepository
```

Use `@SingleIn(AppScope::class)` only for shared app-lifetime state/resources. Add a separate session scope only when the product has a real authenticated session lifecycle.

Use `@Provides` for values Metro cannot construct: platform inputs, third-party factories, Ktor engines, Room builders/DAOs, DataStore, dispatchers/scopes, qualified values, and runtime selections. Do not write forwarding providers for app-owned classes that can use `@Inject`.

Keep common graph contracts narrow. Put platform `@DependencyGraph` declarations and runtime inputs in platform source sets. Swift must not see graphs, repositories, ViewModels, or feature implementation types; it enters through `IosAppBridge`.

Feature UI should obtain injected ViewModels through MetroX when a graph is introduced. Do not use graph access as a service locator from composables.
