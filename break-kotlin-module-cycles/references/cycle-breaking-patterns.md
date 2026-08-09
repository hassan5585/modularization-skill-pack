# Cycle-breaking patterns

| Pattern | When |
|---|---|
| Dependency inversion | Lower layer imported a higher layer; introduce a port |
| Domain contract extraction | Two features share a stable type that belongs in domain/core |
| Event contract | One-way notification without a hard dependency |
| Navigation contract | UI cycles through navigation runtime types |
| App-shell orchestration | Only the app should know both features |
| Feature-owned shared UI | UI reuse without feature→feature domain coupling |
| Temporary adapter | Bridge during migration; track removal condition |

Never “fix” a cycle by creating `core:common` or chaining `shared-ui` modules.
