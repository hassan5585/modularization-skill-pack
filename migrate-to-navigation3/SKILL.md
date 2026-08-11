---
name: migrate-to-navigation3
description: Migrate Android and Compose Multiplatform applications from Navigation Compose 2 to Navigation 3. Supports typed and string-based routes, preserves repository route conventions, and extracts an app-owned Navigator contract without depending on a fixed Destination type. Use when migrating to Navigation 3, cutting over NavHost to NavDisplay, removing NavController from ViewModels, or running /migrate-to-navigation3.
---

# Migrate to Navigation 3

Migrate Compose Navigation 2 applications to Navigation 3 with a **safe hybrid
workflow**: deterministic auditing, planning, contract scaffolding, and
verification in one Python script; project-specific Kotlin migration remains
**agent-driven and reviewable**.

## Scope

**In scope**

- Android-only and Kotlin Multiplatform Compose apps already on Navigation Compose 2
- Typed Navigation 2 routes and string-based routes
- App-owned Navigator extraction before Nav3 host cutover
- Single or multiple back stacks, deep links, dialogs/sheets, results, process death
- AndroidX versus JetBrains Navigation 3 coordinates chosen from the project shape

**Out of scope**

- Fragment / XML Navigation graphs and non-Compose navigation libraries
- Broad automatic source rewrites by the script
- Changing route identity or user-visible navigation unless the user requests it
- Generating Metro / Koin / Hilt DI bindings
- Requiring or inventing a class named `Destination` (YSN-specific)

## Non-goals

- Do not rewrite production navigation hosts wholesale without a reviewed plan.
- Do not pin this pack’s Navigation 3 versions permanently; resolve compatible
  versions from repository conventions and current official guidance.
- Do not remove Navigation 2 dependencies until verification passes.
- Do not create a new Gradle navigation module without coordinating with
  `$extract-kotlin-foundations` when foundations are missing.

## Preflight

1. Confirm the user **explicitly** wants Navigation 3 migration (not a greenfield
   Navigation 3 app — use `$create-kmp-repository` for that).
2. Read project `AGENTS.md`, navigation docs, and DI docs. Preserve DI system.
3. Ensure a clean baseline: app compiles on Navigation 2 with known green checks.
4. Run the audit (read-only):

   ```bash
   python3 scripts/migrate_navigation3.py audit \
     --root /path/to/repo \
     --json-out .modularization/navigation3-audit.json
   ```

5. Stop immediately if the audit reports **unsupported-scope** (Fragment/XML or
   non-Compose navigation). Present findings; do not invent a Compose migration path.

## References

Read before planning or scaffolding:

- [references/migration-procedure.md](references/migration-procedure.md)
- [references/navigator-inference.md](references/navigator-inference.md)
- [references/android-vs-kmp.md](references/android-vs-kmp.md)
- [assets/navigation3-spec.example.json](assets/navigation3-spec.example.json)

Align agent decisions with the official Android Navigation 2→3 migration guide
and Compose Multiplatform Navigation 3 guidance.

## Phases

### Phase A — Audit (script)

Capture Gradle/source sets, Navigation 2 dependencies, route styles, hosts,
graphs, controllers, back-stack behavior, results, deep links, ViewModel scopes,
dialogs/sheets, animations, and multiple stacks.

Artifact: `.modularization/navigation3-audit.json` (`navigation3-audit` kind).

### Phase B — Plan (script + human review)

```bash
python3 scripts/migrate_navigation3.py plan \
  --root /path/to/repo \
  --audit .modularization/navigation3-audit.json \
  --json-out .modularization/navigation3-spec.json
```

Review every **unresolved** decision and plan gate. Edit the spec only to record
approved choices (module path, package, route base type, API surface, stack
model). Do not treat heuristic API flags as requirements until behavior evidence
exists.

Artifact: `.modularization/navigation3-spec.json` (`navigation3-spec` kind).

### Phase C — String-route conversion (agent, if needed)

When the audit reports `route_style: string` (or mixed):

1. Introduce serializable **app-owned route keys** while Navigation 2 still runs.
2. Preserve old route names, arguments, deep links, and tests.
3. Prefer typed Navigation 2 (`toRoute` / type-safe APIs) as an intermediate step.
4. Re-audit after conversion so the cutover starts from typed keys.

Skip this phase when routes are already typed and serializable.

### Phase D — Extract Navigator boundary (script scaffold + agent wiring)

Preview by default; apply only after review:

```bash
python3 scripts/migrate_navigation3.py scaffold \
  --root /path/to/repo \
  --spec .modularization/navigation3-spec.json

python3 scripts/migrate_navigation3.py scaffold \
  --root /path/to/repo \
  --spec .modularization/navigation3-spec.json \
  --apply
```

Scaffold creates only reviewed files (never overwrites):

- `Navigator.kt` — app-owned contract typed to existing route base or `NavKey`
- optional `NavOptions` / `PopUpTo` types when the spec enables them
- `RecordingNavigator` (or equivalent) fake for unit tests

Rules:

- Reuse an existing app route base type when available and make it a `NavKey`.
- Otherwise type the contract against `NavKey`; **never** introduce `Destination`.
- Place files in the approved core/shared navigation module from the spec.
- If a new module is required, stop and invoke `$extract-kotlin-foundations`.
- Preserve the repository DI system; wire bindings manually in the project style.
- Always include `navigate` and back. Add popUpTo/single-top, current/previous
  flows, results, readiness, deep-link routing, or graph/entry ViewModel scope
  **only** when the audit found matching behavior (see navigator-inference).

### Phase E — Temporary Navigation 2-backed implementation (agent)

1. Implement `Navigator` with the existing `NavController` (or wrappers).
2. Migrate ViewModels off `NavController` onto the injected `Navigator`.
3. Keep hosts on Navigation 2 until ViewModels and call sites no longer leak
   controller types.
4. Keep tests green against the recording fake + temporary real implementation.

### Phase F — Atomic host cutover (agent)

In one reviewed batch per navigation host (or coordinated multi-host cutover):

1. Add Navigation 3 dependencies (AndroidX or JetBrains per
   [references/android-vs-kmp.md](references/android-vs-kmp.md)).
2. Ensure route keys implement `NavKey` and are `@Serializable` as required.
3. Replace `NavHost` with Navigation 3 state + `NavDisplay` / entry providers.
4. Prefer official entry decorators for saveable state and entry-scoped ViewModels.
5. Add project-owned graph scoping or nested-flow normalization only where the
   audit requires existing behavior.
6. Switch the real `Navigator` implementation to Navigation 3 state APIs.
7. Preserve single vs multiple back stacks, top-level selection, dialog/sheet
   metadata, result delivery, deep links, process-death restoration, and
   full-session reset semantics.

### Phase G — Remove Navigation 2 (agent, after verification)

Only after Phase H passes:

- Remove Navigation 2 dependencies and compatibility adapters.
- Delete temporary NavController bridges.
- Re-run check and app verification.

### Phase H — Verify (script + build)

```bash
python3 scripts/migrate_navigation3.py check \
  --root /path/to/repo \
  --spec .modularization/navigation3-spec.json \
  --json-out .modularization/navigation3-check.json
```

The check reports leftover Navigation 2 usage, controller leaks, incomplete route
conversion/serialization, missing host registration, and unverified behavior
gates. Compile and run repository navigation/unit tests. For KMP, confirm
platform-appropriate coordinates and polymorphic serializer registration.

Artifact: `.modularization/navigation3-check.json` (`navigation3-check` kind).

## Stop conditions

Stop and request direction when:

- Fragment/XML or non-Compose navigation is required for production screens;
- route identity or deep-link URLs would change without product approval;
- the navigation module target is missing and foundation extraction is needed;
- multiple back-stack ownership or top-level selection rules are ambiguous;
- process-death or result contracts cannot be reconstructed from evidence;
- DI wiring would force a framework change the repository does not use.

## Verification checklist

- [ ] `navigation3-audit` / `navigation3-spec` / `navigation3-check` artifacts valid
- [ ] No unsupported-scope findings left unaddressed
- [ ] Navigator uses existing route base or `NavKey` — no required `Destination`
- [ ] ViewModels do not import or hold `NavController`
- [ ] Hosts use Navigation 3 display/entry APIs
- [ ] Route keys serializable where saveable back stack is required
- [ ] KMP serializers registered when polymorphic navigation is used
- [ ] Navigation 2 dependencies removed only after check + build pass
- [ ] Dialogs, deep links, results, multi-stack, and restore behavior preserved
- [ ] Recording fake covers the generated API surface

## Script contract summary

| Subcommand | Writes files? | Primary output |
|---|---|---|
| `audit` | optional JSON | inventory + findings |
| `plan` | optional JSON | reviewed-ready navigation3-spec |
| `scaffold` | only with `--apply` | Navigator + options + recording fake |
| `check` | optional JSON | leftover Nav2 / leak / completeness report |

Preview is the default for `scaffold`. Conflicts refuse overwrite (exit 3).
Invalid paths/packages fail closed (exit 2).
