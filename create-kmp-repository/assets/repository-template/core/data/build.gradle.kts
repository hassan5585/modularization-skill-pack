plugins {
    alias(libs.plugins.architecture.library)
}

configureBuild {
    setup {
        usesDI = true
        isDataLibrary = true
    }
}

dependencies {
    commonMainImplementation(project(":core:domain"))
}

kotlin {
    sourceSets.commonTest.dependencies {
        implementation(project(":test:core"))
        implementation(libs.ktor.client.mock)
    }
}
