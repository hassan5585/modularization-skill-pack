package @@PACKAGE@@.core.domain.model.util

sealed interface KtResult<out D, out E : Error> {
    data class Success<out D>(val data: D) : KtResult<D, Nothing>
    data class Failure<out E : Error>(val error: E) : KtResult<Nothing, E>
}

typealias EmptyResult<E> = KtResult<Unit, E>

suspend fun <T, E : Error, R> KtResult<T, E>.map(
    transform: suspend (T) -> R,
): KtResult<R, E> = when (this) {
    is KtResult.Success -> KtResult.Success(transform(data))
    is KtResult.Failure -> KtResult.Failure(error)
}

suspend fun <T, E : Error> KtResult<T, E>.onSuccess(
    action: suspend (T) -> Unit,
): KtResult<T, E> = apply {
    if (this is KtResult.Success) action(data)
}

suspend fun <T, E : Error> KtResult<T, E>.onError(
    action: suspend (E) -> Unit,
): KtResult<T, E> = apply {
    if (this is KtResult.Failure) action(error)
}

fun <T, E : Error> KtResult<T, E>.getOrNull(): T? = (this as? KtResult.Success)?.data

fun <T, E : Error, F : Error> KtResult<T, E>.mapError(
    transform: (E) -> F,
): KtResult<T, F> = when (this) {
    is KtResult.Success -> KtResult.Success(data)
    is KtResult.Failure -> KtResult.Failure(transform(error))
}
