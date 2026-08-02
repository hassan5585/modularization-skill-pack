package @@PACKAGE@@.home.data

import @@PACKAGE@@.core.domain.di.AppScope
import @@PACKAGE@@.home.domain.Greeting
import @@PACKAGE@@.home.domain.GreetingRepository
import dev.zacsweers.metro.ContributesBinding
import dev.zacsweers.metro.Inject
import dev.zacsweers.metro.binding

@ContributesBinding(AppScope::class, binding = binding<GreetingRepository>())
internal class RealGreetingRepository @Inject constructor() : GreetingRepository {
    override fun greeting(): Greeting = Greeting(
        title = "@@APP_NAME@@",
        message = "Your modular Kotlin Multiplatform foundation is ready.",
    )
}
