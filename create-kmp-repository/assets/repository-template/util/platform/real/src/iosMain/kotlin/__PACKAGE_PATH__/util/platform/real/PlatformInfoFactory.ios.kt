package @@PACKAGE@@.util.platform.real

import @@PACKAGE@@.util.platform.domain.PlatformInfo
import platform.UIKit.UIDevice

actual fun createPlatformInfo(): PlatformInfo = object : PlatformInfo {
    override val name: String = "${UIDevice.currentDevice.systemName} ${UIDevice.currentDevice.systemVersion}"
}
