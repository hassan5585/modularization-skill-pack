# Portable Kotlin modularization skill pack

Thirteen coordinated skills generate production-ready Kotlin Multiplatform
repositories or orchestrate, audit, design, extract foundations, scaffold and
migrate features, break module cycles, separate platform boundaries, harden
APIs, measure build performance, and verify an incremental layered modularization
of Android, Kotlin Multiplatform, JVM, or mixed Kotlin/Gradle repositories. The
pack supports optional feature-owned `shared-ui` modules without permitting
shared-UI dependency chains. For KMP projects it also guards the Kotlin/Native
dependency and Swift export surface, including generated framework headers.
Existing-project workflows preserve the target project’s libraries and generate
project-specific convention plugins instead of copying a reference stack.

Skills exchange versioned JSON artifacts under `.modularization/`
(`schema_version: 1`). Shared Python helpers live in `common/` and are installed
beside the skills.

## Skill map

```text
Existing repository
  -> audit-kotlin-architecture
  -> design-gradle-conventions
  -> extract-kotlin-foundations
  -> migrate-kotlin-feature  (scaffolds via scaffold-kotlin-feature)
  -> break-kotlin-module-cycles
  -> extract-kmp-platform-boundaries
  -> harden-kotlin-module-apis
  -> verify-kotlin-modules
  -> measure-kotlin-modular-build-performance

New KMP repository
  -> create-kmp-repository
  -> scaffold-kotlin-feature
  -> extract-kmp-platform-boundaries / verify-kotlin-modules / …
```

Orchestration entry point for brownfield work: `$modularize-kotlin-codebase`.

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
documentation, repository-local skills, and verification tooling. Add further
product capabilities with `$scaffold-kotlin-feature`.

For an existing codebase, start with `$modularize-kotlin-codebase`. It
coordinates architecture discovery, convention-plugin creation, foundation
extraction, dependency-first feature and shared-UI chunks, cycle remediation,
platform-boundary cleanup, API hardening, optional build-performance baselines,
repository-local progress tracking, and static plus Gradle verification.
KMP projects that produce Apple frameworks also use
`$audit-kotlin-native-framework` before release verification and after changes
to public declarations, dependency visibility, or native interop.
