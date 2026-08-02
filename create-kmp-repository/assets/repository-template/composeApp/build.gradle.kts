plugins {
    alias(libs.plugins.architecture.app)
}

configureBuild {
    setup {
        isUiLibrary = true
        usesDI = true
        usesNavigation = true
    }
}

dependencies {
    commonMainImplementation(project(":core"))
    commonMainImplementation(project(":feature:home"))
    commonMainImplementation(project(":util:platform"))
}

kotlin {
    sourceSets.commonTest.dependencies {
        implementation(project(":test:core"))
    }
}
