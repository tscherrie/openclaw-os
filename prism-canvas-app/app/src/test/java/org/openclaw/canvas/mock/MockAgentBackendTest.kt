package org.openclaw.canvas.mock

import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertTrue
import org.junit.Test

class MockAgentBackendTest {

    @Test
    fun `getResponse emittiert wachsenden Text`() = runTest {
        val backend = MockAgentBackend()
        val tokens = backend.getResponse("Hallo").toList()

        assertTrue(tokens.isNotEmpty())
        // Jedes Token sollte länger als das vorherige sein
        for (i in 1 until tokens.size) {
            assertTrue(tokens[i].length > tokens[i - 1].length)
        }
    }

    @Test
    fun `getResponse rotiert durch Antworten`() = runTest {
        val backend = MockAgentBackend()

        val first = backend.getResponse("A").toList().last()
        val second = backend.getResponse("B").toList().last()

        // Verschiedene Antworten
        assertTrue(first != second)
    }

    @Test
    fun `letztes Token ist vollstaendige Antwort`() = runTest {
        val backend = MockAgentBackend()
        val tokens = backend.getResponse("Test").toList()
        val lastToken = tokens.last()

        // Sollte mindestens 2 Wörter enthalten
        assertTrue(lastToken.split(" ").size >= 2)
    }
}
