plugins {
    alias(libs.plugins.architecture.library)
}

dependencies {
    commonMainApi(project(":util:platform:domain"))
    commonMainApi(project(":util:platform:real"))
}
