package @@PACKAGE@@.core.domain.model

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

class EnvironmentTest {
    @Test
    fun `given an unknown environment when configured then input is rejected`() {
        assertFailsWith<IllegalArgumentException> {
            Environment.configure("preview", isDebuggable = true)
        }
    }

    @Test
    fun `given dev when configured then profile is non production`() {
        Environment.configure("dev", isDebuggable = true)

        assertEquals(false, Environment.current.isProduction)
        assertEquals(true, Environment.current.isDebuggable)
    }
}
