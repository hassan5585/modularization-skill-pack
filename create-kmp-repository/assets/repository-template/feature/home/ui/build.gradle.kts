plugins {
    alias(libs.plugins.architecture.library)
}

configureBuild {
    setup {
        usesDI = true
        usesNavigation = true
        isUiLibrary = true
    }
}

dependencies {
    commonMainImplementation(project(":core:ui"))
    commonMainImplementation(project(":feature:home:domain"))
    commonMainImplementation(project(":feature:home:navigation"))
    commonMainImplementation(project(":util:platform:domain"))
}

kotlin {
    sourceSets.commonTest.dependencies {
        implementation(project(":feature:home:test"))
    }
}
