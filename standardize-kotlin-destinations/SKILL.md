---
name: standardize-kotlin-destinations
description: Adopt the portable Destination NavKey convention used by create-kmp-repository: an app-owned Destination interface with stable destinationId and SerialName values, primitive-only route parameters, feature navigation ownership, and explicit serializer registration. Use when introducing Destination into an existing Android or Kotlin Multiplatform app, converting AppRoute, Screen, or NavKey types to Destination, adding a new destination, checking destinationId, SerialName, or serializer compliance, making a repo match the pack navigation house style, or running /standardize-kotlin-destinations. Complements migrate-to-navigation3, which never invents Destination.
---

# Standardize Kotlin Destinations

Give an existing Android or Kotlin Multiplatform app the same **Destination**
route contract that `$create-kmp-repository` generates. Deterministic audit,
plan, contract scaffolding, and checks stay in one Python script. Converting
existing `AppRoute` / `Screen` types and authoring feature destinations remain
**agent-driven and reviewable**.

This skill owns Destination. `$migrate-to-navigation3` owns Nav2 → Nav3 and
must not invent Destination.

## Scope

**In scope**

- Introducing `interface Destination : NavKey { val destinationId: String }`
- Converting existing typed route bases onto Destination
- Authoring feature sealed destinations (`OrdersDestination`, …)
- Primitive-only parameters, matching `@SerialName` / `destinationId`
- Explicit `subclass(Foo.serializer())` registration
- Checking an already-Destination repo (including greenfield templates)

**Out of scope**

- Navigation 2 → 3 host cutover (use `$migrate-to-navigation3`)
- Generating `Navigator`, NavDisplay hosts, deep-link handlers, or DI bindings
- Creating a missing `:core:navigation` module (use `$extract-kotlin-foundations`)
- Changing user-visible route identity or deep-link URLs unless requested
- Product-specific core destinations (login root, invite, external URL, …)

## Preflight

1. Confirm the user wants the Destination convention (not only a Nav3 cutover).
2. Read project `AGENTS.md` and navigation docs. Preserve DI and host APIs.
3. If the app is still on Navigation Compose 2, run `$migrate-to-navigation3`
   first (or stop — Destination extends `NavKey`).
4. If no navigation foundation module exists, stop and use
   `$extract-kotlin-foundations`.

## References

Read before planning, scaffolding, or authoring:

- [references/destination-convention.md](references/destination-convention.md)
- [references/authoring-and-conversion.md](references/authoring-and-conversion.md)
- [assets/destination-spec.example.json](assets/destination-spec.example.json)

## Phases

### Phase A — Audit (script)

```bash
python3 scripts/standardize_destinations.py audit \
  --root /path/to/repo \
  --json-out .modularization/destination-audit.json
```

Capture Destination presence, other route bases, leaf destinations,
`@SerialName` / `destinationId`, parameter types, ownership, serializer
registration, string routes, and Nav3 availability.

Artifact: `.modularization/destination-audit.json` (`destination-audit` kind).

### Phase B — Plan (script + human review)

```bash
python3 scripts/standardize_destinations.py plan \
  --root /path/to/repo \
  --audit .modularization/destination-audit.json \
  --json-out .modularization/destination-spec.json
```

Review unresolved items (module, package, conversion strategy). Edit the spec
only to record approved choices. Do not treat heuristic conversions as
requirements until identity is reviewed.

Artifact: `.modularization/destination-spec.json` (`destination-spec` kind).

### Phase C — Scaffold Destination (script)

Preview by default; apply only after review:

```bash
python3 scripts/standardize_destinations.py scaffold \
  --root /path/to/repo \
  --spec .modularization/destination-spec.json

python3 scripts/standardize_destinations.py scaffold \
  --root /path/to/repo \
  --spec .modularization/destination-spec.json \
  --apply
```

Creates only missing files (never overwrites):

- `Destination.kt` — `Destination : NavKey` with `destinationId`
- `DestinationSerializers.kt` — empty `registerCoreDestinationSerializers()`

Skip scaffold when Destination already exists. Do not generate feature
destinations or rewrite `AppRoute`.

### Phase D — Convert and author (agent)

Follow [references/authoring-and-conversion.md](references/authoring-and-conversion.md):

1. Make each remaining route base implement `Destination`, or replace it with
   feature sealed destinations.
2. Add `@Serializable`, destination-level `@SerialName("feature.screen")`, and
   a matching `destinationId` on every concrete destination.
3. Keep parameters primitive, nullable primitive, or `@Serializable` enum.
4. Keep feature destinations in feature `navigation` modules.
5. Register every concrete type with `subclass(Type.serializer())`.
6. Point an existing `Navigator` at `Destination` if it is still typed to
   `AppRoute` / `NavKey`.

Preserve serialized names and deep-link URLs unless the user approves a change.

### Phase E — Verify (script + build)

```bash
python3 scripts/standardize_destinations.py check \
  --root /path/to/repo \
  --spec .modularization/destination-spec.json \
  --json-out .modularization/destination-check.json
```

Compile affected navigation modules and run repository navigation tests.

Artifact: `.modularization/destination-check.json` (`destination-check` kind).

## Stop conditions

Stop and request direction when:

- Navigation 2 is still the production host and Nav3 was not requested;
- the navigation module target is missing;
- converting a route would change `@SerialName`, deep-link URLs, or saved state;
- a screen needs a complex object in the route instead of a stable ID;
- Destination already exists under a different name the team wants to keep.

If the team keeps `AppRoute` as the public name, do not rename it to
`Destination`. Record that as an explicit exception and still require
`destinationId`, `@SerialName`, primitive params, and serializer registration.

## Verification checklist

- [ ] `destination-audit` / `destination-spec` / `destination-check` artifacts valid
- [ ] `Destination` (or approved existing base) implements `NavKey` and exposes `destinationId`
- [ ] Every concrete destination is `@Serializable` with a stable `@SerialName`
- [ ] `destinationId` matches `@SerialName` unless a reviewed compatibility exception exists
- [ ] Route parameters are primitives, nullable primitives, or serializable enums
- [ ] Feature destinations live in feature navigation modules, not UI or a core dump
- [ ] Every concrete destination has an explicit `subclass(….serializer())` entry
- [ ] Identity is not derived from `qualifiedName`, `simpleName`, or `.route()`
- [ ] Navigator, if present, accepts Destination (or the approved existing base)

## Script contract summary

| Subcommand | Writes files? | Primary output |
|---|---|---|
| `audit` | optional JSON | inventory + findings |
| `plan` | optional JSON | reviewed-ready destination-spec |
| `scaffold` | only with `--apply` | Destination + serializer stub |
| `check` | optional JSON | convention completeness report |

Preview is the default for `scaffold`. Conflicts refuse overwrite (exit 3).
Invalid paths/packages or a missing Nav3/`NavKey` runtime fail closed (exit 2).
