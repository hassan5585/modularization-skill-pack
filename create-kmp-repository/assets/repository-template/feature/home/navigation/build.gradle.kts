plugins {
    alias(libs.plugins.architecture.library)
}

configureBuild {
    setup {
        usesDI = true
        usesNavigation = true
    }
}

dependencies {
    commonMainApi(project(":core:navigation"))
    commonMainImplementation(project(":feature:home:domain"))
}
