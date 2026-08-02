package @@PACKAGE@@.home.data

import kotlin.test.Test
import kotlin.test.assertTrue

class RealGreetingRepositoryTest {
    @Test
    fun `given the default repository when greeting is requested then starter text is returned`() {
        val result = RealGreetingRepository().greeting()

        assertTrue(result.title.isNotBlank())
        assertTrue(result.message.contains("Kotlin Multiplatform"))
    }
}
