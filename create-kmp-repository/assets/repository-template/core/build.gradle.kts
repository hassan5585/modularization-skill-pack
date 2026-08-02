plugins {
    alias(libs.plugins.architecture.library)
}

dependencies {
    commonMainApi(project(":core:domain"))
    commonMainApi(project(":core:data"))
    commonMainApi(project(":core:navigation"))
    commonMainApi(project(":core:ui"))
}
