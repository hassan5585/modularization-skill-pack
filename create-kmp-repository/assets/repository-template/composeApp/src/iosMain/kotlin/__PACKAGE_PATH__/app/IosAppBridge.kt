package @@PACKAGE@@.app

import androidx.compose.ui.window.ComposeUIViewController
import @@PACKAGE@@.core.domain.model.Environment
import platform.Foundation.NSBundle
import platform.UIKit.UIViewController

/** The complete Kotlin API intentionally consumed by the native iOS app. */
object IosAppBridge {
    fun makeMainViewController(): UIViewController {
        configureEnvironment()
        return ComposeUIViewController { App() }
    }

    private fun configureEnvironment() {
        val environmentId = NSBundle.mainBundle.objectForInfoDictionaryKey("AppEnvironment") as? String
            ?: error("Missing AppEnvironment in Info.plist")
        val isDebuggable = when (
            (NSBundle.mainBundle.objectForInfoDictionaryKey("AppDebuggable") as? String)?.uppercase()
        ) {
            "YES", "TRUE", "1" -> true
            "NO", "FALSE", "0" -> false
            else -> error("Missing or invalid AppDebuggable in Info.plist")
        }
        Environment.configure(environmentId, isDebuggable)
    }
}
