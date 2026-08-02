package @@PACKAGE@@.core.navigation

import kotlinx.serialization.Serializable
import kotlin.test.Test
import kotlin.test.assertEquals

class RealNavigatorTest {
    @Serializable
    private data object First : Destination {
        override val destinationId = "test.first"
    }

    @Serializable
    private data object Second : Destination {
        override val destinationId = "test.second"
    }

    @Test
    fun `given two destinations when back is popped then first is current`() {
        val navigator = RealNavigator()
        navigator.navigate(First)
        navigator.navigate(Second)

        navigator.popBackStack()

        assertEquals(First, navigator.currentDestination.value)
    }
}
