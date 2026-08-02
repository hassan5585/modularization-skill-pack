package @@PACKAGE@@.buildlogic

import org.gradle.api.Plugin
import org.gradle.api.Project
import org.gradle.kotlin.dsl.configure
import org.jetbrains.kotlin.compose.compiler.gradle.ComposeCompilerGradlePluginExtension
import org.jetbrains.kotlin.gradle.dsl.KotlinMultiplatformExtension

internal class UiLibraryPlugin : Plugin<Project> {
    override fun apply(target: Project) = with(target) {
        pluginManager.apply(libs.pluginId("jetbrains-compose"))
        pluginManager.apply(libs.pluginId("compose-compiler"))
        extensions.configure<ComposeCompilerGradlePluginExtension> {
            stabilityConfigurationFiles.add(rootProject.layout.projectDirectory.file("compose_stability.conf"))
            if (findProperty("composeCompilerReports") == "true") {
                metricsDestination.set(layout.buildDirectory.dir("compose_compiler"))
                reportsDestination.set(layout.buildDirectory.dir("compose_compiler"))
            }
        }
        extensions.configure<KotlinMultiplatformExtension> {
            sourceSets.commonMain.dependencies {
                implementation(libs.bundle("compose"))
                implementation(libs.library("androidx-lifecycle-runtime-compose"))
                implementation(libs.library("androidx-lifecycle-viewmodel-compose"))
                implementation(libs.library("androidx-lifecycle-viewmodel-navigation3"))
                implementation(libs.library("metrox-viewmodel-compose"))
            }
            sourceSets.androidMain.dependencies {
                implementation(libs.library("androidx-activity-compose"))
                implementation(libs.library("compose-ui-tooling-preview"))
            }
        }
        val exposeResources = extensions.extraProperties.get("exposeResources") as Boolean
        extensions.configure<org.jetbrains.compose.ComposeExtension> {
            extensions.configure<org.jetbrains.compose.resources.ResourcesExtension> {
                packageOfResClass = "${namespaceForPath()}.generated.resources"
                publicResClass = exposeResources
            }
        }
    }
}
