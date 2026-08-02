package @@PACKAGE@@.util.platform.real

import android.os.Build
import @@PACKAGE@@.util.platform.domain.PlatformInfo

actual fun createPlatformInfo(): PlatformInfo = object : PlatformInfo {
    override val name: String = "Android ${Build.VERSION.SDK_INT}"
}
