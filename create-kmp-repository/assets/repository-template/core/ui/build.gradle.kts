plugins {
    alias(libs.plugins.architecture.library)
}

configureBuild {
    setup {
        usesDI = true
        usesNavigation = true
        isUiLibrary = true
        exposeResources = true
    }
}

dependencies {
    commonMainApi(project(":core:domain"))
    commonMainApi(project(":core:navigation"))
}
