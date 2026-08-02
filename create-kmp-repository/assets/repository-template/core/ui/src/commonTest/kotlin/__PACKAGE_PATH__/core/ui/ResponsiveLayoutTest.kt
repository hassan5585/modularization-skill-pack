package @@PACKAGE@@.core.ui

import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class ResponsiveLayoutTest {
    @Test
    fun `given expanded width and medium height then two panes are available`() {
        assertTrue(responsiveLayout(widthDp = 900, heightDp = 700).canUseTwoPane)
    }

    @Test
    fun `given expanded width and compact height then two panes are unavailable`() {
        assertFalse(responsiveLayout(widthDp = 900, heightDp = 400).canUseTwoPane)
    }
}
