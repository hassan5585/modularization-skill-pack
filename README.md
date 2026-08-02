# Portable Kotlin modularization skill pack

Seven coordinated Codex skills generate production-ready Kotlin Multiplatform
repositories or orchestrate, audit, design, migrate, and verify an incremental
layered modularization of Android, Kotlin Multiplatform, JVM, or mixed
Kotlin/Gradle repositories. The pack supports optional feature-owned `shared-ui`
modules without permitting shared-UI dependency chains. For KMP projects it
also guards the Kotlin/Native dependency and Swift export surface, including
generated framework headers. Existing-project workflows preserve the target
project’s libraries and generate project-specific convention plugins instead
of copying a reference stack.

Validate without third-party Python packages:

```bash
python3 validate_skill_pack.py
python3 -m unittest discover -s tests -v
```

Preview or install into a repository:

```bash
python3 install_skill_pack.py --target /path/to/repository
python3 install_skill_pack.py --target /path/to/repository --apply
```

For a greenfield Android+iOS app, start with `$create-kmp-repository`. It asks
for the app name, absolute destination, and reverse-DNS package name, then
previews and creates a working modular KMP repository with convention plugins,
dev/prod variants, a narrow iOS bridge, a representative feature, tests, CI,
documentation, repository-local skills, and verification tooling.

For an existing codebase, start with `$modularize-kotlin-codebase`. It
coordinates architecture discovery, convention-plugin creation and
representative-module proof, dependency-first feature and shared-UI chunks,
explicit shared/feature test-support modules, repository-local progress
tracking, and static plus Gradle verification.
KMP projects that produce Apple frameworks also use
`$audit-kotlin-native-framework` before release verification and after changes
to public declarations, dependency visibility, or native interop.
