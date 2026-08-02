plugins {
    alias(libs.plugins.architecture.library)
}

dependencies {
    commonMainImplementation(project(":core:domain"))
    commonMainImplementation(project(":core:navigation"))
    commonMainImplementation(project(":core:ui"))
}
