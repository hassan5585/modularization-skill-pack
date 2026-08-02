package @@PACKAGE@@.core.data

import @@PACKAGE@@.core.domain.model.util.DataError
import @@PACKAGE@@.core.domain.model.util.KtResult
import io.ktor.client.call.body
import io.ktor.client.network.sockets.SocketTimeoutException
import io.ktor.client.statement.HttpResponse
import io.ktor.http.isSuccess
import io.ktor.util.network.UnresolvedAddressException
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive

suspend inline fun <reified T> safeCall(
    execute: () -> HttpResponse,
): KtResult<T, DataError.Remote> {
    val response = try {
        execute()
    } catch (_: SocketTimeoutException) {
        return KtResult.Failure(DataError.Remote.REQUEST_TIMEOUT)
    } catch (_: UnresolvedAddressException) {
        return KtResult.Failure(DataError.Remote.NO_INTERNET)
    } catch (_: Exception) {
        currentCoroutineContext().ensureActive()
        return KtResult.Failure(DataError.Remote.UNKNOWN)
    }

    if (!response.status.isSuccess()) {
        val error = when (response.status.value) {
            408 -> DataError.Remote.REQUEST_TIMEOUT
            429 -> DataError.Remote.TOO_MANY_REQUESTS
            in 500..599 -> DataError.Remote.SERVER
            else -> DataError.Remote.UNKNOWN
        }
        return KtResult.Failure(error)
    }

    return try {
        KtResult.Success(response.body())
    } catch (_: Throwable) {
        KtResult.Failure(DataError.Remote.SERIALIZATION)
    }
}

suspend inline fun safeCallRaw(
    execute: () -> HttpResponse,
): KtResult<HttpResponse, DataError.Remote> = safeCall(execute)
