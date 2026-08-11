# Navigator inference rules

The scaffold generates an **app-owned** navigation boundary. Inference is
conservative: only APIs justified by audit evidence are enabled.

## Route contract type

| Situation | Contract type |
|---|---|
| Existing sealed/interface route base found (e.g. `AppRoute`, `Screen`, `Route`) | Use that type; ensure it implements `NavKey` before Nav3 cutover |
| Only concrete typed routes, no shared base | Type against `NavKey` |
| String routes only | Plan a string→typed phase first; contract type becomes the new base or `NavKey` |

**Never** introduce or require a class named `Destination`. That name is not
part of this skill’s contract (even if some repositories use it).

## Always generated

| API | Reason |
|---|---|
| `navigate(route, …)` | Universal forward navigation |
| `popBackStack()` / `goBack()` equivalent | Universal back |

Default names prefer `navigate` + `popBackStack` when the repository already
uses those terms; otherwise use clear synonyms documented in the generated file.

## Conditionally generated

Enable only when the audit records matching behavior:

| Spec flag | Evidence examples |
|---|---|
| `launch_single_top` | `launchSingleTop = true`, `NavOptions` single-top builders |
| `pop_up_to` | `popUpTo`, `popUpToRoute`, inclusive pop patterns |
| `navigate_up` | `navigateUp()` call sites distinct from `popBackStack` |
| `current_route_flow` | observers of current destination / back-stack entry route |
| `previous_route_flow` | previous destination comparisons or flows |
| `transient_results` | `savedStateHandle` result set/get, `setResult` / `consumeResult` |
| `readiness` | gates waiting for nav host readiness before navigate |
| `deep_link_routing` | `navDeepLink`, deep link handlers, external URI → route |
| `graph_view_model_scope` | nav-graph scoped ViewModels / `getBackStackEntry(graph)` |
| `entry_view_model_scope` | destination/entry scoped ViewModels beyond activity scope |
| `reset_session` | logout / full-stack reset to a root route |

## Module placement

1. Prefer an existing navigation module (`:core:navigation`, `:shared:navigation`,
   or equivalent) discovered by the audit.
2. Prefer an existing `Navigator` interface: **reuse-and-extend** rather than
   duplicate.
3. If no module exists, set `navigator.module_path` only when an existing target
   module can host the files; otherwise mark unresolved and use
   `$extract-kotlin-foundations`.
4. Source set: `commonMain` for KMP portable contracts; `main` for Android-only.

## Generated files

With `--apply`, create only missing files (refuse overwrite):

1. **Navigator interface** — package and name from the spec.
2. **NavOptions / PopUpTo types** — only if `launch_single_top` or `pop_up_to`.
3. **Recording fake** — implements the same interface; records calls for tests.
   Prefer an existing test-support module path from the spec; otherwise place
   beside the interface under a clear `testing` / test source note.

## DI

Do **not** generate Metro, Koin, or Hilt modules. After scaffolding, the agent
binds the interface using the repository’s existing DI patterns.

## Temporary vs final implementation

| Phase | Implementation |
|---|---|
| Boundary extraction | Interface + recording fake only (script) |
| Pre-cutover | Agent writes Nav2-backed real class using `NavController` |
| Post-cutover | Agent rewrites real class against Nav3 state / display APIs |

The script never generates a full `NavController` or `NavDisplay` host.

## Validation

Scaffold fails closed when:

- package or module path is invalid;
- contract type would force a new `Destination` type name;
- target files already exist (exit 3);
- required route conversion phase is still open and `force` is not set.
