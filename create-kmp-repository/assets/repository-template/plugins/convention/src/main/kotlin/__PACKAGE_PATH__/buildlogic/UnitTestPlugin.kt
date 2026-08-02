package @@PACKAGE@@.buildlogic

import org.gradle.api.Plugin
import org.gradle.api.Project
import org.gradle.kotlin.dsl.configure
import org.jetbrains.kotlin.gradle.dsl.KotlinMultiplatformExtension

internal class UnitTestPlugin : Plugin<Project> {
    override fun apply(target: Project) = with(target) {
        extensions.configure<KotlinMultiplatformExtension> {
            sourceSets.commonTest.dependencies {
                implementation(kotlin("test"))
                implementation(libs.library("kotlinx-coroutines-test"))
                implementation(libs.library("turbine"))
                if (path != ":test") implementation(project(":test"))
            }
        }
        tasks.matching { it.name == "check" }.configureEach {
            dependsOn("testAndroidHostTest")
        }
    }
}
