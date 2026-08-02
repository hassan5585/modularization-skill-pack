package @@PACKAGE@@.buildlogic

import javax.inject.Inject

abstract class BuildExtension @Inject constructor() {
    companion object {
        const val NAME = "configureBuild"
    }

    private val configuration = Setup()
    internal var listener: ((Setup) -> Unit)? = null

    fun setup(action: Setup.() -> Unit) {
        configuration.apply(action)
        listener?.invoke(configuration)
    }

    data class Setup(
        var usesDI: Boolean = false,
        var usesNavigation: Boolean = false,
        var isUiLibrary: Boolean = false,
        var isDataLibrary: Boolean = false,
        var usesSerialization: Boolean = false,
        var exposeResources: Boolean = false,
    )
}
