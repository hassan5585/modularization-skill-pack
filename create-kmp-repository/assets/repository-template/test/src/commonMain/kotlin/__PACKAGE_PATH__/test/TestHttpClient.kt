package @@PACKAGE@@.test

import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockRequestHandler
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.json.Json

fun testHttpClient(handler: MockRequestHandler): HttpClient = HttpClient(MockEngine(handler)) {
    install(ContentNegotiation) {
        json(Json { ignoreUnknownKeys = true })
    }
}
