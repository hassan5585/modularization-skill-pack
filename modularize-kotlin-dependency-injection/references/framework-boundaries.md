# DI framework boundary patterns

| Concern | Metro | Dagger / Hilt | Koin | Manual DI |
|---|---|---|---|---|
| Binding discovery | Contributions and graph scope | Modules/components and generated factories | Loaded modules and definitions | Explicit constructors/factories |
| App aggregation | `@DependencyGraph` / contributed containers | Component or Hilt aggregation | `startKoin` module list | Composition root |
| Platform boundary | Platform dependency graph | Android component/entry point | Platform-loaded module | Platform factory |
| Multibinding | Into-set/map contributions | `@IntoSet` / `@IntoMap` | Qualified collections or module composition | Explicit collection assembly |

Preserve framework semantics rather than translating annotations mechanically.
Record graph owners, scopes, qualifiers, and runtime parameters before moving a
binding. Generated-code visibility must follow supported framework aggregation;
an `api(project(...))` edge is not a substitute for correct graph registration.

Use injected interfaces for replaceable platform services. Use platform graph
entry points for OS/runtime values. Keep session-scoped objects below the
session graph and never capture them in an application singleton.
