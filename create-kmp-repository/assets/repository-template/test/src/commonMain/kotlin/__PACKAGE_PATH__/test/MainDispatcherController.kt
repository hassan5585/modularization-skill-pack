package @@PACKAGE@@.test

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain

@OptIn(ExperimentalCoroutinesApi::class)
class MainDispatcherController(
    val dispatcher: TestDispatcher = StandardTestDispatcher(),
) {
    fun install() {
        Dispatchers.setMain(dispatcher)
    }

    fun reset() {
        Dispatchers.resetMain()
    }
}
