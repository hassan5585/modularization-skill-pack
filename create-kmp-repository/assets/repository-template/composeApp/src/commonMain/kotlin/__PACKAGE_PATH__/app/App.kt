@file:OptIn(kotlin.experimental.ExperimentalObjCRefinement::class)

package @@PACKAGE@@.app

import androidx.compose.runtime.Composable
import @@PACKAGE@@.core.ui.AppTheme
import @@PACKAGE@@.home.ui.HomeScreen
import @@PACKAGE@@.util.platform.real.createPlatformInfo
import kotlin.native.HiddenFromObjC

@Composable
@HiddenFromObjC
fun App() {
    AppTheme {
        HomeScreen(platformName = createPlatformInfo().name)
    }
}
