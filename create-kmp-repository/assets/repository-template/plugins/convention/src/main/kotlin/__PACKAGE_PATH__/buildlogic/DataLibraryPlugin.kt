package @@PACKAGE@@.buildlogic

import androidx.room.gradle.RoomExtension
import org.gradle.api.Plugin
import org.gradle.api.Project
import org.gradle.kotlin.dsl.configure
import org.gradle.kotlin.dsl.dependencies
import org.jetbrains.kotlin.gradle.dsl.KotlinMultiplatformExtension

internal class DataLibraryPlugin : Plugin<Project> {
    override fun apply(target: Project) = with(target) {
        pluginManager.apply(libs.pluginId("ksp"))
        pluginManager.apply(libs.pluginId("kotlin-serialization"))
        pluginManager.apply(libs.pluginId("room"))
        extensions.configure<RoomExtension> {
            schemaDirectory("$projectDir/schemas")
            generateKotlin = true
        }
        extensions.configure<KotlinMultiplatformExtension> {
            sourceSets.commonMain.dependencies {
                implementation(libs.bundle("ktor"))
                implementation(libs.library("kotlinx-serialization-json"))
                implementation(libs.library("room-runtime"))
                implementation(libs.library("sqlite-bundled"))
                implementation(libs.library("datastore"))
                implementation(libs.library("datastore-preferences"))
            }
            sourceSets.androidMain.dependencies {
                implementation(libs.library("ktor-client-okhttp"))
            }
            sourceSets.iosMain.dependencies {
                implementation(libs.library("ktor-client-darwin"))
            }
        }
        dependencies {
            add("kspAndroid", libs.library("room-compiler"))
            add("kspIosArm64", libs.library("room-compiler"))
            add("kspIosSimulatorArm64", libs.library("room-compiler"))
        }
    }
}
