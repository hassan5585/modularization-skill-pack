# Android vs KMP Navigation 3 differences

## Project detection

| Signal | Platform classification |
|---|---|
| `kotlin { androidTarget / ios* / … }` multiplatform blocks | `kmp` |
| Android app/library plugins without KMP | `android` |
| `src/commonMain` present with Compose Multiplatform | `kmp` + multiplatform compose |

The audit records source sets and recommends coordinate families. Agents must
still confirm against the version catalog and official docs at migration time.

## Dependency coordinates

### Android-only (AndroidX)

Typical Navigation 2:

- `androidx.navigation:navigation-compose`

Typical Navigation 3 (names evolve — verify current artifacts):

- `androidx.navigation3:navigation3-runtime`
- `androidx.navigation3:navigation3-ui`
- lifecycle ViewModel Navigation 3 artifacts as needed

### Kotlin Multiplatform / Compose Multiplatform (JetBrains AndroidX)

Typical Navigation 2:

- `org.jetbrains.androidx.navigation:navigation-compose`

Typical Navigation 3:

- `org.jetbrains.androidx.navigation3:navigation3-ui`
- related lifecycle / adaptive artifacts from the JetBrains AndroidX line

**Rule:** Do not mix AndroidX-only Navigation 3 artifacts into `commonMain`.
Keep portable navigation code on multiplatform coordinates. Android-only apps
should stay on AndroidX.

## Version resolution

1. Prefer existing version catalog keys if the repo already depends on Navigation 3
   elsewhere (or related JetBrains AndroidX BOM).
2. Otherwise consult current official get-started / migration docs and the
   repository’s dependency update policy.
3. Record chosen versions in the migration receipt — not as permanent skill pins.

## Source set ownership

| Concern | KMP | Android-only |
|---|---|---|
| Route keys / Navigator interface | `commonMain` | `main` |
| NavDisplay host | `commonMain` when CMP hosts UI; else platform UI module | app `main` |
| Deep link activity wiring | `androidMain` / app module | app `main` |
| iOS URL openers | `iosMain` / app bridge | n/a |
| Serializer modules | `commonMain` + explicit registration | same if polymorphic |

## Serialization

KMP Navigation 3 saveable stacks commonly require:

- `@Serializable` route keys
- explicit polymorphic `SerializersModule` registration for sealed hierarchies
- no reliance on sealed-subclass discovery alone when shrinkers/obfuscation apply

Android-only projects should still prefer explicit registration for release
shrink safety.

## Expect/actual

Avoid expect/actual for the Navigator interface itself. Keep the contract
portable; put platform deep-link entry wiring in app modules.

## Process death

- Prefer official saveable back-stack APIs / entry decorators.
- Verify restoration for both single-stack and multi-stack hosts on Android.
- On iOS, document which state survives process death vs activity-equivalent
  recreation — do not claim Android parity without evidence.

## Verification differences

| Check | Android | KMP |
|---|---|---|
| Leftover `navigation-compose` Nav2 deps | yes | yes (JetBrains + any Android residual) |
| `NavController` imports in commonMain | n/a | fail if present after cutover |
| Polymorphic serializer registration | recommended | required when audit flagged it |
| Host registration completeness | app module | composeApp / shared host module |
