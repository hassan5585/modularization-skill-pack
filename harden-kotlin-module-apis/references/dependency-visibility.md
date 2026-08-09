# Dependency visibility

- Default new project edges to `implementation`.
- Use `api` only when a public signature exposes the dependency’s type, or when
  an aggregation root is the documented Kotlin facade for its own children.
- Test configurations never justify production `api` edges.
- Native `export(project(...))` is not an API-hardening tool; keep Swift surface
  on the bridge and audit the framework header separately.
