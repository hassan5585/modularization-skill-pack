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
    commonMainApi(project(":core:domain"))
    commonMainApi(libs.androidx.navigation3.ui)
}
