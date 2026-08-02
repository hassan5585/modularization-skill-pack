plugins {
    `kotlin-dsl`
}

kotlin {
    jvmToolchain(libs.versions.jdk.get().toInt())
}

dependencies {
    compileOnly(libs.android.gradle.plugin)
    compileOnly(libs.android.kmp.gradle.plugin)
    compileOnly(libs.kotlin.multiplatform.plugin)
    compileOnly(libs.compose.plugin)
    compileOnly(libs.compose.compiler.plugin)
    compileOnly(libs.ksp.plugin)
    compileOnly(libs.room.plugin)
    implementation(libs.metro.gradle.plugin)
}

gradlePlugin {
    plugins {
        register("sharedApp") {
            id = "@@PACKAGE@@.plugin.app"
            implementationClass = "@@PACKAGE@@.buildlogic.AppPlugin"
        }
        register("androidApp") {
            id = "@@PACKAGE@@.plugin.android.app"
            implementationClass = "@@PACKAGE@@.buildlogic.AndroidAppPlugin"
        }
        register("library") {
            id = "@@PACKAGE@@.plugin.library"
            implementationClass = "@@PACKAGE@@.buildlogic.LibraryPlugin"
        }
    }
}
