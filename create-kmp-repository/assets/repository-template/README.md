# @@APP_NAME@@

Android and iOS Kotlin Multiplatform app using Compose Multiplatform and a layered feature architecture.

## Start here

Requirements: JDK 21, Android SDK 37, and Xcode 16+ for iOS work.

```bash
python3 scripts/verify_repository.py
./gradlew projects
./gradlew :plugins:convention:build
./gradlew testAndroidHostTest
./gradlew :androidApp:assembleDevDebug
```

Open `iosApp/iosApp.xcodeproj` and use the Dev scheme for iOS development.

Read `AGENTS.md` before changing architecture, build logic, navigation, data, UI, or tests. Repository-local Codex skills live under `.agents/skills` when installed by the bootstrap generator.
