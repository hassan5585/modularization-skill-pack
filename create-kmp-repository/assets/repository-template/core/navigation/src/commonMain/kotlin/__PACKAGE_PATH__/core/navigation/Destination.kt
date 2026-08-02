package @@PACKAGE@@.core.navigation

import androidx.navigation3.runtime.NavKey

interface Destination : NavKey {
    val destinationId: String
}
