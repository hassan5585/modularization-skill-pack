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
    commonMainImplementation(project(":core:data"))
    commonMainImplementation(project(":feature:home:domain"))
}

kotlin {
    sourceSets.commonTest.dependencies {
        implementation(project(":feature:home:test"))
        implementation(libs.ktor.client.mock)
    }
}
