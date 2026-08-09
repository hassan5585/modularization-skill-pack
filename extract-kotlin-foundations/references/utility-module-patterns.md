# Utility module patterns

Independently reusable cross-cutting capabilities use:

```text
util/<capability>/domain   # pure contracts and models
util/<capability>/real     # implementations (may have platform source sets)
util/<capability>/ui       # optional UI helpers for that capability only
```

## Dependency direction

```text
real -> domain
ui   -> domain (+ core:ui when needed)
features -> domain (prefer) or real only when the project’s DI style requires it
```

Never let `domain` depend on `real`. Never put feature product logic in util.
