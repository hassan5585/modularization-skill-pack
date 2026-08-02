package @@PACKAGE@@.home.domain

import kotlin.test.Test
import kotlin.test.assertEquals

class GreetingTest {
    @Test
    fun `given values when greeting is created then values are retained`() {
        val greeting = Greeting(title = "Title", message = "Message")

        assertEquals("Title", greeting.title)
        assertEquals("Message", greeting.message)
    }
}
