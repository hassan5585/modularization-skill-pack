---
name: create-kmp-repository
description: Create a new production-ready Android and iOS Kotlin Multiplatform repository from the owner’s modular architecture and build conventions. Use when starting a greenfield KMP mobile app, generating a fresh modular Compose Multiplatform codebase, bootstrapping dev/prod variants and convention plugins, or asking for a new repository similar to the owner’s established feature/domain/data/navigation/UI architecture. Collect only the app name, full repository destination, and Kotlin package/application ID before previewing and creating the repository.
---

# Create KMP Repository

Generate a runnable, batteries-included KMP mobile repository without copying product-specific code or secrets.

## Required inputs

Collect exactly these three values if the user has not already supplied them:

1. App display name, for example `Focus Garden`.
2. Full destination directory for the new repository, for example `/Users/me/dev/focus-garden`. The directory must not already exist.
3. Reverse-DNS Kotlin package and application ID, for example `com.example.focusgarden`.

Do not ask about frameworks, module shapes, variants, test libraries, or tooling. This skill owns those defaults. Explain any invalid input and ask only for its replacement.

## Read before generating

- Read [references/generated-repository-contract.md](references/generated-repository-contract.md) to understand the generated files, boundaries, and non-goals.
- Read [references/source-repository-audit.md](references/source-repository-audit.md) when the user asks what was generalized, wants a design rationale, or requests changes to the blueprint.
- Read [references/post-generation-customization.md](references/post-generation-customization.md) before adding integrations, more modules, or release infrastructure after generation.

## Workflow

1. Inspect the destination parent and confirm the exact destination does not exist. Never overwrite or merge into an existing directory.
2. Preview with the bundled generator; do not hand-create the repository:

   ```bash
   python3 scripts/create_kmp_repository.py \
     --app-name "Focus Garden" \
     --output /absolute/path/focus-garden \
     --package-name com.example.focusgarden
   ```

3. Review the normalized inputs, module list, variant matrix, and planned files printed by the preview.
4. Apply with the same arguments plus `--apply`:

   ```bash
   python3 scripts/create_kmp_repository.py \
     --app-name "Focus Garden" \
     --output /absolute/path/focus-garden \
     --package-name com.example.focusgarden \
     --apply
   ```

   The generator writes through a sibling staging directory, verifies token replacement and required files, initializes a `main` Git branch, and then atomically moves the repository into place. When this skill is run from the transport pack, it also installs the complete sibling skill pack into `.agents/skills` in the new repository.

5. Inspect `bootstrap-manifest.json`, `git status --short`, and the generated `AGENTS.md`.
6. Run verification in increasing cost order:

   ```bash
   python3 scripts/verify_repository.py
   ./gradlew projects
   ./gradlew :plugins:convention:build
   ./gradlew testAndroidHostTest
   ./gradlew :androidApp:assembleDevDebug
   ```

   On macOS with Xcode installed, also run:

   ```bash
   xcodebuild -list -project iosApp/iosApp.xcodeproj
   ./gradlew :composeApp:linkDebugFrameworkIosSimulatorArm64
   ```

7. Report the created path, package, included variants/modules/tooling, skill-pack installation status, and exact verification results. Distinguish unavailable toolchains or network failures from source failures.

## Generation guarantees

- Preserve the requested app name and package; never substitute a sample identity.
- Use the destination folder name as `rootProject.name`.
- Generate Android and iOS shells, `composeApp`, core layers, a working Home feature, a platform utility slice, test foundations, docs, CI, and an included `plugins` build.
- Generate `dev` and `prod` environments independently from `debug` and `release` build types.
- Keep `ComposeApp` as the only Swift-consumed static framework and expose only `IosAppBridge` intentionally.
- Keep secrets, signing material, Firebase configuration, backend URLs, Apple team IDs, branded assets, and store credentials out of the repository.
- Default to `implementation`; use `api` only for documented aggregation/public-contract edges.
- Keep product behavior out of core and do not create speculative features or utilities.
- Keep the repository immediately buildable without optional service credentials.

## Safe variants

- Use `--without-skills` only when the user explicitly does not want repository-local skills.
- Use `--no-git` only when Git initialization is explicitly unwanted or Git is unavailable.
- Never use these optional switches as additional user questions by default.

## Extending the result

Use the installed sibling skills rather than improvising structure:

- `$scaffold-kotlin-feature` to add new product capabilities (domain/data/navigation/UI and optional shared-ui/test).
- `$standardize-kotlin-destinations` to introduce or check the Destination contract in an existing (non-generated) repository. The template already includes Destination.
- `$migrate-kotlin-feature` only when extracting behavior from an existing monolith path.
- `$design-gradle-conventions` to add new build capabilities.
- `$extract-kmp-platform-boundaries` and `$harden-kotlin-module-apis` when validating or extending the template boundaries.
- `$verify-kotlin-modules` for architecture enforcement.
- `$audit-kotlin-native-framework` after public KMP API, framework, SwiftPM, or native dependency changes.
- `$measure-kotlin-modular-build-performance` when comparing build isolation after structural changes.

The generator installs the full skill pack (all manifest skills plus shared
`common/` helpers). After generation, run architecture, platform-boundary, and
API checks against the template when changing module shape.

Apply integrations such as Firebase, analytics, maps, payments, notifications, widgets, deep links, or release uploads only when the user requests them and provides the required product decisions or credentials.
