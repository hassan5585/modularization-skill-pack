# Navigation

Navigation contracts live in feature navigation modules and implement the app-owned `Destination` interface.

```kotlin
@Serializable
sealed interface OrdersDestination : Destination {
    override val destinationId: String

    @Serializable
    @SerialName("orders.landing")
    data object Landing : OrdersDestination {
        override val destinationId = "orders.landing"
    }

    @Serializable
    @SerialName("orders.detail")
    data class Detail(val orderId: String) : OrdersDestination {
        override val destinationId = "orders.detail"
    }
}
```

Every concrete destination has an explicit stable `@SerialName` and `destinationId`. Do not derive identity from class names. Route fields are primitives, nullable primitives, or serializable enums; pass IDs and load complex objects in ViewModels.

Keep navigation in `commonMain`. Inject `Navigator` into ViewModels and never expose platform controllers to feature code. When adding a Navigation 3 host, register destination serializers explicitly and keep app graph roots distinct from renderable destinations.
