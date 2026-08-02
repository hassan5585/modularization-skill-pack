package @@PACKAGE@@.buildlogic

import org.gradle.api.Project
import org.gradle.kotlin.dsl.apply
import org.gradle.kotlin.dsl.configure
import org.jetbrains.kotlin.gradle.dsl.KotlinMultiplatformExtension

internal fun Project.configureCapabilities(setup: BuildExtension.Setup) {
    if (setup.usesNavigation) plugins.apply(NavigationPlugin::class)
    if (setup.usesDI) plugins.apply(MetroPlugin::class)
    if (setup.isUiLibrary) {
        extensions.extraProperties.set("exposeResources", setup.exposeResources)
        plugins.apply(UiLibraryPlugin::class)
    }
    if (setup.isDataLibrary) plugins.apply(DataLibraryPlugin::class)
    if (setup.usesSerialization && !setup.isDataLibrary) plugins.apply(SerializationPlugin::class)
}

internal fun Project.installBuildExtension() {
    val extension = extensions.create(BuildExtension.NAME, BuildExtension::class.java)
    extension.listener = ::configureCapabilities
}

internal fun Project.namespaceForPath(): String {
    val suffix = path.trim(':')
        .split(':')
        .filter(String::isNotBlank)
        .joinToString(".") { segment -> segment.replace('-', '_') }
    return listOf("@@PACKAGE@@", suffix).filter(String::isNotBlank).joinToString(".")
}

internal fun Project.configureCommonKmpTargets(namespace: String) {
    extensions.configure<KotlinMultiplatformExtension> {
        extensions.configure<com.android.build.api.dsl.KotlinMultiplatformAndroidLibraryExtension> {
            minSdk = libs.minSdk
            compileSdk = libs.compileSdk
            this.namespace = namespace
            experimentalProperties["android.experimental.kmp.enableAndroidResources"] = true
            withHostTestBuilder {
                sourceSetTreeName = "test"
            }.configure { }
        }
        jvmToolchain(libs.jdk)
        iosArm64()
        iosSimulatorArm64()
        sourceSets.all {
            languageSettings.optIn("kotlin.time.ExperimentalTime")
            languageSettings.optIn("kotlinx.coroutines.ExperimentalCoroutinesApi")
        }
        sourceSets.commonMain.dependencies {
            implementation(libs.library("kotlinx-coroutines-core"))
            implementation(libs.library("kotlinx-datetime"))
        }
        sourceSets.androidMain.dependencies {
            implementation(libs.library("kotlinx-coroutines-android"))
        }
    }
}
