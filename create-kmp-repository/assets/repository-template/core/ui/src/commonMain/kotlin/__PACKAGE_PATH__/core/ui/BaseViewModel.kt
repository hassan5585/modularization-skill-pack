package @@PACKAGE@@.core.ui

import androidx.lifecycle.DefaultLifecycleObserver
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.launch
import kotlin.coroutines.CoroutineContext
import kotlin.coroutines.EmptyCoroutineContext

abstract class BaseViewModel<STATE, EVENT, INTENT> : ViewModel(), DefaultLifecycleObserver {
    protected val mutableState = MutableStateFlow(initialState())
    val state = mutableState.asStateFlow()
    protected val currentState: STATE get() = state.value

    private val mutableEvents = Channel<EVENT>()
    val events = mutableEvents.receiveAsFlow()

    protected abstract fun initialState(): STATE
    abstract fun handleIntent(intent: INTENT)

    protected fun updateState(transform: STATE.() -> STATE) {
        mutableState.value = currentState.transform()
    }

    protected fun sendEvent(event: EVENT) {
        launch { mutableEvents.send(event) }
    }
}

fun ViewModel.launch(
    context: CoroutineContext = EmptyCoroutineContext,
    start: CoroutineStart = CoroutineStart.DEFAULT,
    block: suspend CoroutineScope.() -> Unit,
): Job = viewModelScope.launch(context, start, block)
