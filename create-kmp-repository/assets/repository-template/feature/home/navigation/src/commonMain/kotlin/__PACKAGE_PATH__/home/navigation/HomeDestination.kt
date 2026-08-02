package @@PACKAGE@@.home.navigation

import @@PACKAGE@@.core.navigation.Destination
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
sealed interface HomeDestination : Destination {
    @Serializable
    @SerialName("home.root")
    data object Root : HomeDestination {
        override val destinationId = "home.root"
    }

    @Serializable
    @SerialName("home.landing")
    data object Landing : HomeDestination {
        override val destinationId = "home.landing"
    }
}
