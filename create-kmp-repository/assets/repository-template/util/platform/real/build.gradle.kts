plugins {
    alias(libs.plugins.architecture.library)
}

configureBuild {
    setup {
        usesDI = true
    }
}

dependencies {
    commonMainImplementation(project(":core:domain"))
    commonMainImplementation(project(":util:platform:domain"))
}
