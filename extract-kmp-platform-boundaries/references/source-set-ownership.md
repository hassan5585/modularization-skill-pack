# Source-set ownership

| Source set | May contain |
|---|---|
| `commonMain` | Pure Kotlin, multiplatform libraries only |
| `androidMain` | Android SDK, AndroidX, JVM Android APIs |
| `iosMain` / apple targets | Kotlin/Native interop, platform.* |
| `jvmMain` | Java SE APIs when JVM is a real target |
| `main` (Android/JVM single-target) | That platform’s APIs |

Custom intermediate source sets inherit the strictest parent constraint that still
matches all of their compilations.
