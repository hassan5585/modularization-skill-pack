plugins {
    alias(libs.plugins.architecture.library)
}

dependencies {
    commonMainApi(libs.kotlinx.coroutines.test)
    commonMainApi(libs.ktor.client.mock)
    commonMainImplementation(libs.ktor.client.content.negotiation)
    commonMainImplementation(libs.ktor.serialization.json)
}
