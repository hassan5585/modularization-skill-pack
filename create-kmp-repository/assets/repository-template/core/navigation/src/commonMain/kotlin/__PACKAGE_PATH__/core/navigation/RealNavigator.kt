package @@PACKAGE@@.core.navigation

import @@PACKAGE@@.core.domain.di.AppScope
import dev.zacsweers.metro.ContributesBinding
import dev.zacsweers.metro.Inject
import dev.zacsweers.metro.SingleIn
import dev.zacsweers.metro.binding
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

@Inject
@SingleIn(AppScope::class)
@ContributesBinding(AppScope::class, binding = binding<Navigator>())
class RealNavigator : Navigator {
    private val backStack = mutableListOf<Destination>()
    private val mutableCurrentDestination = MutableStateFlow<Destination?>(null)
    private val mutablePreviousDestination = MutableStateFlow<Destination?>(null)

    override val currentDestination: StateFlow<Destination?> = mutableCurrentDestination.asStateFlow()
    override val previousDestination: StateFlow<Destination?> = mutablePreviousDestination.asStateFlow()

    override fun navigate(destination: Destination, launchSingleTop: Boolean) {
        if (!launchSingleTop || backStack.lastOrNull() != destination) backStack += destination
        publish()
    }

    override fun popBackStack(): Boolean {
        if (backStack.size <= 1) return false
        backStack.removeAt(backStack.lastIndex)
        publish()
        return true
    }

    override fun resetTo(destination: Destination) {
        backStack.clear()
        backStack += destination
        publish()
    }

    private fun publish() {
        mutableCurrentDestination.value = backStack.lastOrNull()
        mutablePreviousDestination.value = backStack.dropLast(1).lastOrNull()
    }
}
