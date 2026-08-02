package @@PACKAGE@@.test.core

import @@PACKAGE@@.core.navigation.Destination
import @@PACKAGE@@.core.navigation.Navigator
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

class FakeNavigator : Navigator {
    private val mutableCurrent = MutableStateFlow<Destination?>(null)
    private val mutablePrevious = MutableStateFlow<Destination?>(null)
    override val currentDestination: StateFlow<Destination?> = mutableCurrent
    override val previousDestination: StateFlow<Destination?> = mutablePrevious
    val visited = mutableListOf<Destination>()

    override fun navigate(destination: Destination, launchSingleTop: Boolean) {
        if (!launchSingleTop || visited.lastOrNull() != destination) visited += destination
        publish()
    }

    override fun popBackStack(): Boolean {
        if (visited.size <= 1) return false
        visited.removeAt(visited.lastIndex)
        publish()
        return true
    }

    override fun resetTo(destination: Destination) {
        visited.clear()
        visited += destination
        publish()
    }

    private fun publish() {
        mutableCurrent.value = visited.lastOrNull()
        mutablePrevious.value = visited.dropLast(1).lastOrNull()
    }
}
