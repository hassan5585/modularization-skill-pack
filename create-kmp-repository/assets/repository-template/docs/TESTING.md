# Unit testing

New or changed testable behavior ships with unit tests.

Use `src/commonTest/kotlin` for `commonMain` production behavior. Use platform test source sets only for matching platform production boundaries.

The standard stack is kotlin.test, coroutines-test, Turbine, Ktor MockEngine, and handwritten fakes. Construct subjects directly; do not test Metro, Room, or Compose generated code and do not add mocking frameworks.

- `:test` contains production-independent helpers such as main-dispatcher control and Ktor client builders.
- `:test:core` contains core-contract fakes for downstream features/utilities; core itself does not depend on it.
- `feature/{name}:test` contains reusable feature-owned fakes/fixtures and is visible only to test configurations.
- Keep one-off fakes beside their tests.

ViewModel tests install/reset a test main dispatcher, collect state with Turbine, and verify recorded navigation/effects. Repository tests cover request shape, mapping, representative failures, and feature-specific guards/caches.

```bash
./gradlew :feature:home:data:testAndroidHostTest
./gradlew :feature:home:domain:iosSimulatorArm64Test
./gradlew testAndroidHostTest
```

Compose rendering, live services, real devices, and Room SQL integration are not portable unit tests. Keep decisions pure and classify platform/integration coverage explicitly.
