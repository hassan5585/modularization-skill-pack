package @@PACKAGE@@.home.test

import @@PACKAGE@@.home.domain.Greeting
import @@PACKAGE@@.home.domain.GreetingRepository

class FakeGreetingRepository(
    var result: Greeting = Greeting("Test", "Test greeting"),
) : GreetingRepository {
    var callCount: Int = 0
        private set

    override fun greeting(): Greeting {
        callCount += 1
        return result
    }
}
