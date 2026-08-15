# Authoring and conversion

Scripts invent only the missing `Destination` interface and an empty core
serializer helper. Agents convert existing routes and add new destinations.

## Convert an existing route base

Typical starting points: `AppRoute`, `Screen`, `Route`, a `NavKey` sealed type,
or string `composable("home")` routes.

1. Finish `$migrate-to-navigation3` if Navigation 2 is still the host.
2. Scaffold `Destination` when it is missing. Skip this when the existing base
   will keep its name and already can become the contract.
3. Choose one conversion shape and record it in the spec:

   | Existing shape | Preferred conversion |
   |---|---|
   | One app-wide sealed route type | Make it implement `Destination`, add `destinationId` + `@SerialName` on each leaf |
   | Routes already split by feature | Rename/retarget each feature type to `{Name}Destination : Destination` |
   | String routes | Introduce typed destinations first; do not keep string keys as identity |

4. Preserve `@SerialName` values and deep-link URI patterns. If a leaf has no
   serial name, add `feature.screen_name` that matches the current route string
   when one exists.
5. Replace complex route fields with primitive IDs. Load objects in ViewModels.
6. Move types out of UI modules into feature `navigation` modules.
7. Add `subclass(Leaf.serializer())` for every concrete leaf.
8. Retype `Navigator` from `AppRoute` / `NavKey` to `Destination` only after
   leaves compile. Do not regenerate Navigator here.

Convert one feature (or one sealed type) per reviewable batch. Keep the app
compiling after each batch.

## Add a new destination

1. Add a `@Serializable` leaf to the feature navigation module.
2. Add `@SerialName("feature.screen_name")` and a matching `destinationId`.
3. Use `data object` with no parameters, or `data class` with primitive/enum
   fields only.
4. Register `subclass(NewDestination.serializer())` in the feature helper.
5. Wire the screen setup and graph in the feature UI module using the
   repository’s existing host APIs.
6. Add root normalization only when the new type is a graph root that can be
   navigated to directly.
7. Run `standardize_destinations.py check`.

Do not put the new type in a UI module, in `:core:navigation` (unless it is
truly app-wide), or in a shared catch-all `AppDestination` dump.

## Naming

- Feature sealed type: `{Name}Destination`
- Graph function (repository-owned): `{name}NavGraph()`
- Identity: lowercase `feature.screen_name` with dots and optional underscores
- `destinationId` equals `@SerialName`

## Compatibility

Do not change an existing `@SerialName` to “look nicer” if saved back-stack
state or deep links depend on it. Record a deliberate mismatch only when
`destinationId` must stay stable while a serial name is already shipped.
