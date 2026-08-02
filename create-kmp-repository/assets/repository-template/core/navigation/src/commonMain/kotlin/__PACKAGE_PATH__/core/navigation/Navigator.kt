package @@PACKAGE@@.core.navigation

import kotlinx.coroutines.flow.StateFlow

interface Navigator {
    val currentDestination: StateFlow<Destination?>
    val previousDestination: StateFlow<Destination?>

    fun navigate(destination: Destination, launchSingleTop: Boolean = false)
    fun popBackStack(): Boolean
    fun resetTo(destination: Destination)
}
