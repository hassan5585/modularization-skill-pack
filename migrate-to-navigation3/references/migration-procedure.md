# Navigation 2 → Navigation 3 migration procedure

This procedure aligns with the official Android Navigation 2-to-3 migration
guide and Compose Multiplatform Navigation 3 guidance. Use it with the audit
and plan artifacts; do not skip evidence-based gates.

## Official cutover steps (host)

1. **Add Navigation 3 dependencies** using the coordinate family that matches
   the project (AndroidX for Android-only, JetBrains AndroidX multiplatform for
   KMP). Resolve versions from the repository version catalog or current
   official guidance — do not hard-pin pack-local versions.
2. **Update routes to implement `NavKey`.** Routes do not strictly require
   `NavKey` for all Nav3 APIs, but implementing it enables saveable back stacks
   via `rememberNavBackStack` (or project equivalents).
3. **Hold navigation state in app-owned classes** (single stack or multiple
   stacks). This is where back stacks live instead of `NavController`.
4. **Create a `Navigator` (or equivalent) that mutates that state** —
   `navigate`, `goBack` / `popBackStack`, and any options the app already uses.
5. **Move destinations from `NavHost` graphs into an `entryProvider`.**
6. **Replace `NavHost` with `NavDisplay`** (or the multiplatform equivalent),
   connecting `onBack` to the navigator’s back operation and feeding entries
   from navigation state + entry provider.

## Safe hybrid order (this skill)

The official steps assume a direct host rewrite. This skill inserts boundary
extraction so ViewModels stop depending on `NavController` before the host
cutover:

```text
audit → plan → [string→typed routes] → scaffold Navigator
  → temporary Nav2-backed Navigator
  → migrate call sites off NavController
  → atomic Nav3 host + real Navigator
  → verify → remove Nav2
```

## Typed routes

When Navigation 2 already uses `@Serializable` route types / type-safe APIs:

- Implement `NavKey` on the existing base type or on each route key.
- Keep argument fields primitive / serializable.
- Register polymorphic serializers when the back stack stores a sealed hierarchy.

## String routes

When hosts use string routes (`"home"`, `"detail/{id}"`):

1. **While still on Navigation 2**, introduce serializable app-owned route key
   classes that preserve the same path templates, argument names, deep links,
   and tests.
2. Migrate `composable("…")` registrations to typed routes incrementally.
3. Only then treat routes as typed for Nav3 `NavKey` cutover.

Never rename user-visible deep-link paths during conversion unless product
explicitly requests it.

## Nested graphs and dialogs

- Map Navigation 2 nested `navigation(route) { … }` graphs to nested state or
  entry metadata as required by existing back behavior.
- Map `dialog { }` / bottom-sheet destinations to Navigation 3 metadata or
  scene strategies so presentation (dialog vs full screen) is preserved.
- Preserve animation / transition policies when the app customized them.

## ViewModel scopes

- Prefer **official Navigation 3 entry decorators** for saveable state and
  entry-scoped ViewModels.
- Recreate **graph-scoped** ViewModels only when the audit found
  `navigation`-route scoped owners or equivalent shared scopes.
- Do not invent graph scoping for simple linear stacks.

## Results and deep links

- Transient results (`SavedStateHandle` / previous-entry patterns) become
  explicit navigator result APIs only when used today.
- Deep links keep the same URI patterns; route them through the navigator or
  host entry point without changing external URLs.

## Multiple back stacks

If the app uses bottom navigation (or similar) with separate stacks:

- Model one back stack per top-level root.
- Preserve top-level selection and per-tab history.
- Document reset-on-reselect vs restore-stack behavior from observed code.

## Removal of Navigation 2

Delete Navigation 2 dependencies, `NavHost` imports, and temporary adapters
only after:

- `migrate_navigation3.py check` is clean (or only accepted pre-existing noise);
- app hosts compile on Navigation 3;
- navigation unit tests and critical manual flows pass.

## Unsupported

- Fragment destinations, XML nav graphs, Navigation UI with Fragments
- Non-Compose navigation libraries (Conductor, custom Activity-only routers)

Report these as `unsupported-scope` findings and stop.
