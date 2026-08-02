package @@PACKAGE@@.buildlogic

import com.android.build.api.dsl.ApplicationExtension
import org.gradle.api.Plugin
import org.gradle.api.Project
import org.gradle.kotlin.dsl.configure
import org.jetbrains.kotlin.gradle.dsl.kotlinExtension

class AndroidAppPlugin : Plugin<Project> {
    override fun apply(target: Project) = with(target) {
        pluginManager.apply(libs.pluginId("android-application"))
        pluginManager.apply(libs.pluginId("jetbrains-compose"))
        pluginManager.apply(libs.pluginId("compose-compiler"))
        kotlinExtension.jvmToolchain(libs.jdk)

        extensions.configure<ApplicationExtension> {
            namespace = "@@PACKAGE@@.android"
            compileSdk = libs.compileSdk
            defaultConfig {
                applicationId = "@@PACKAGE@@"
                minSdk = libs.minSdk
                targetSdk = libs.targetSdk
                versionCode = System.getenv("BUILD_NUMBER")?.toIntOrNull() ?: 1
                versionName = "0.1.0"
                testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
                vectorDrawables.useSupportLibrary = true
            }
            buildFeatures {
                buildConfig = true
                compose = true
            }
            flavorDimensions += "environment"
            productFlavors {
                create("dev") {
                    dimension = "environment"
                    applicationIdSuffix = ".dev"
                    manifestPlaceholders["appName"] = "@@DEV_APP_NAME@@"
                    buildConfigField("String", "APP_ENVIRONMENT", "\"dev\"")
                }
                create("prod") {
                    dimension = "environment"
                    manifestPlaceholders["appName"] = "@@APP_NAME@@"
                    buildConfigField("String", "APP_ENVIRONMENT", "\"prod\"")
                }
            }
            buildTypes {
                debug {
                    isMinifyEnabled = false
                    manifestPlaceholders["diagnosticsEnabled"] = true
                }
                release {
                    isDebuggable = false
                    isMinifyEnabled = true
                    isShrinkResources = true
                    proguardFiles(
                        getDefaultProguardFile("proguard-android-optimize.txt"),
                        "proguard-rules.pro",
                    )
                    manifestPlaceholders["diagnosticsEnabled"] = false
                    ndk.debugSymbolLevel = "FULL"
                }
            }
            packaging.resources.excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }
}
