# Portable Kotlin modularization skill pack

Five coordinated Codex skills audit, design, migrate, track, and verify an
incremental layered modularization of Android, Kotlin Multiplatform, JVM, or
mixed Kotlin/Gradle repositories. The pack supports optional feature-owned
`shared-ui` modules without permitting shared-UI dependency chains. It preserves
the target project’s libraries and generates project-specific convention
plugins instead of copying a reference stack.

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

Start with `$modularize-kotlin-codebase`. It coordinates architecture discovery,
convention-plugin creation and representative-module proof, dependency-first
feature and shared-UI chunks, explicit shared/feature test-support modules,
repository-local progress tracking, and static plus Gradle verification.
