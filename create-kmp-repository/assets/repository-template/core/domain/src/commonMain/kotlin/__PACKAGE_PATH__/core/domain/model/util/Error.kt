package @@PACKAGE@@.core.domain.model.util

interface Error

sealed interface DataError : Error {
    enum class Remote : DataError {
        REQUEST_TIMEOUT,
        TOO_MANY_REQUESTS,
        NO_INTERNET,
        SERVER,
        SERIALIZATION,
        UNKNOWN,
    }

    enum class Local : DataError {
        DISK_FULL,
        DOES_NOT_EXIST,
        UNKNOWN,
    }
}

data class ErrorWithMessage(val message: String) : Error
data class ThrowableError(val throwable: Throwable) : Error
