# Feature module shapes

## Standard four-layer feature

- `feature/<name>/` aggregation root (optional but recommended)
- `domain`, `data`, `navigation`, `ui`
- Optional `shared-ui` only with reviewed cross-feature UI consumers
- Optional `test` for reusable fakes/fixtures consumed from test configurations

## Platform source sets

| Platform | Main | Test |
|---|---|---|
| KMP | `commonMain` | `commonTest` |
| Android | `main` | `test` |
| JVM | `main` | `test` |

Map Gradle directory `shared-ui` to package suffix `sharedui`.

## Forbidden shapes

- `shared-ui` → `shared-ui`
- Production `dependencies` on `:test` / test-support modules
- Domain depending on data, UI, or shared-ui
- Empty speculative layers with no planned sources
