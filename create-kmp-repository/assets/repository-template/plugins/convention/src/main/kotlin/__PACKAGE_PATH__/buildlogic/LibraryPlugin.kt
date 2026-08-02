package @@PACKAGE@@.buildlogic

import org.gradle.api.Plugin
import org.gradle.api.Project

class LibraryPlugin : Plugin<Project> {
    override fun apply(target: Project) = with(target) {
        pluginManager.apply(libs.pluginId("kotlin-multiplatform"))
        pluginManager.apply(libs.pluginId("android-kmp-library"))
        configureCommonKmpTargets(namespaceForPath())
        pluginManager.apply(UnitTestPlugin::class.java)
        installBuildExtension()
    }
}
