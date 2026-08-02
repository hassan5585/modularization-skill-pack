package @@PACKAGE@@.buildlogic

import dev.zacsweers.metro.gradle.MetroGradleSubplugin
import dev.zacsweers.metro.gradle.MetroPluginExtension
import org.gradle.api.Plugin
import org.gradle.api.Project
import org.gradle.kotlin.dsl.configure

internal class MetroPlugin : Plugin<Project> {
    override fun apply(target: Project) = with(target) {
        pluginManager.apply(MetroGradleSubplugin::class.java)
        extensions.configure<MetroPluginExtension> {
            generateContributionProviders.set(true)
        }
    }
}
