package @@PACKAGE@@.app

import @@PACKAGE@@.core.ui.responsiveLayout
import kotlin.test.Test
import kotlin.test.assertNotNull

class AppSmokeTest {
    @Test
    fun `given compact dimensions when layout is resolved then a layout is returned`() {
        assertNotNull(responsiveLayout(widthDp = 360, heightDp = 640))
    }
}
