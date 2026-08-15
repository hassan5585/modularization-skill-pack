# Destination convention

This is the portable route-key contract. Greenfield apps from
`$create-kmp-repository` already follow it. Existing apps adopt it with this
skill. `$migrate-to-navigation3` reuses an existing route base or `NavKey`
and must not invent `Destination`.

## Contract

```kotlin
package com.example.core.navigation

import androidx.navigation3.runtime.NavKey

interface Destination : NavKey {
    val destinationId: String
}
```

Rules:

- There is one app-owned `Destination` type in the navigation foundation module
  (`:core:navigation` or the project’s equivalent).
- `Destination` extends Navigation 3 `NavKey`.
- Every destination exposes a stable app-owned `destinationId`.
- Do not derive navigation behavior from `qualifiedName`, `simpleName`,
  substring matches, or a `.route()` helper. R8 may obfuscate class names.
- Keep the contract in `commonMain` for KMP and `main` for Android-only.

App-wide destinations that are not a feature (session root, external URL)
may live next to the interface. Feature screens must not accumulate there.

## Feature destinations

```kotlin
@Serializable
sealed interface OrdersDestination : Destination {
    override val destinationId: String
        get() = when (this) {
            Root -> "orders.root"
            Landing -> "orders.landing"
            is Detail -> "orders.detail"
        }

    @Serializable
    @SerialName("orders.root")
    data object Root : OrdersDestination

    @Serializable
    @SerialName("orders.landing")
    data object Landing : OrdersDestination

    @Serializable
    @SerialName("orders.detail")
    data class Detail(val orderId: String) : OrdersDestination
}
```

A per-leaf `override val destinationId = "orders.landing"` is equally valid.
Feature sealed interfaces usually implement it once with an exhaustive `when`.

| Element | Convention | Example |
|---|---|---|
| App contract | `Destination` | `interface Destination : NavKey` |
| Feature sealed type | `{Name}Destination` | `OrdersDestination` |
| Graph root | `Root` or `{Flow}Root` | `OrdersDestination.Root` |
| Screen with no args | `data object` | `Landing` |
| Screen with args | `data class` | `Detail(val orderId: String)` |
| Identity | `feature.screen_name` | `orders.detail` |

Rules:

- Every destination is `@Serializable`.
- Every concrete destination has a destination-level
  `@SerialName("feature.screen_name")`.
- `destinationId` and `@SerialName` match unless a reviewed compatibility
  exception is recorded.
- Implement `Destination` directly or through the feature sealed interface.
- Keep destination types in feature `navigation` modules, not UI modules.
- Root destinations are graph entry points; they are not renderable screens.
- Register every concrete type with an explicit `subclass(Type.serializer())`.

## Parameters

Allowed: `String`, `Int`, `Long`, `Float`, `Double`, `Boolean` (and nullables),
plus `@Serializable` enums.

Never: data classes, domain models, DTOs, sealed types, lists, maps, sets,
arrays, or JSON strings used to smuggle objects.

Pass a stable primitive ID and load the object in the ViewModel.

## Serializer registration

```kotlin
fun PolymorphicModuleBuilder<Destination>.registerOrdersDestinationSerializers() {
    subclass(OrdersDestination.Root.serializer())
    subclass(OrdersDestination.Landing.serializer())
    subclass(OrdersDestination.Detail.serializer())
}
```

Register the feature helper on the app-level `SavedStateConfiguration` (or the
project’s equivalent polymorphic module) used to save the Nav3 back stack.

Do not rely on sealed-subclass reflection. Registration must be explicit.

## Identity

Use `destinationId` for preferences, graph keys, analytics, and comparisons.

Forbidden identity sources:

```kotlin
destination::class.qualifiedName
destination::class.simpleName
Destination.route()
subclassesOfSealed<SomeDestination>()
```

## Keeping another type name

If the repository already has a public `AppRoute` (or similar) and the team
refuses to rename it, keep that name. Still require `NavKey`, `destinationId`,
`@SerialName`, primitive parameters, feature ownership, and explicit
serializers. Record the exception in the destination-spec; do not generate a
second unused `Destination` type beside a healthy existing contract.
