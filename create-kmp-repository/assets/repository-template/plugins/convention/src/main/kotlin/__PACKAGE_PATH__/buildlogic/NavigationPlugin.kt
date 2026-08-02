package @@PACKAGE@@.buildlogic

import org.gradle.api.Plugin
import org.gradle.api.Project
import org.gradle.kotlin.dsl.configure
import org.jetbrains.kotlin.gradle.dsl.KotlinMultiplatformExtension

internal class NavigationPlugin : Plugin<Project> {
    override fun apply(target: Project) = with(target) {
        pluginManager.apply(libs.pluginId("kotlin-serialization"))
        extensions.configure<KotlinMultiplatformExtension> {
            sourceSets.commonMain.dependencies {
                implementation(libs.library("androidx-navigation3-ui"))
                implementation(libs.library("compose-material3-adaptive-navigation3"))
                implementation(libs.library("kotlinx-serialization-json"))
            }
        }
    }
}
