# Foundation ownership

## Core

Use `core:domain`, `core:data`, `core:navigation`, and `core:ui` only for
**stable, app-wide** contracts and infrastructure. High fan-in is a signal to
investigate, never sufficient evidence by itself.

`core:navigation` may own the app-wide `Destination : NavKey` interface.
Feature destinations stay in feature navigation modules. Introduce or check
that contract with `$standardize-kotlin-destinations`.

## Reject

- Feature screens, ViewModels, destinations, and repositories in core
- Catch-all `common`, `shared`, `misc`, or `base` modules as cycle fixes
- Empty modules created “for later”
- Platform Android/iOS types in portable core common sources

## Evidence checklist

1. At least two real consumers outside one feature, **and**
2. Stable product language (not a temporary call site), **and**
3. Low volatility relative to features, **and**
4. No feature-specific nouns in the type’s responsibility
