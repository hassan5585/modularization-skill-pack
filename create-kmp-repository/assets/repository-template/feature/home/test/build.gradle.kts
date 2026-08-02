plugins {
    alias(libs.plugins.architecture.library)
}

dependencies {
    commonMainImplementation(project(":core:domain"))
    commonMainImplementation(project(":feature:home:domain"))
    commonMainApi(project(":test:core"))
}
