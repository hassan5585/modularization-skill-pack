plugins {
    alias(libs.plugins.architecture.library)
}

configureBuild {
    setup {
        usesDI = true
    }
}

dependencies {
    commonMainApi(project(":feature:home:domain"))
    commonMainApi(project(":feature:home:data"))
    commonMainApi(project(":feature:home:navigation"))
    commonMainApi(project(":feature:home:ui"))
}
