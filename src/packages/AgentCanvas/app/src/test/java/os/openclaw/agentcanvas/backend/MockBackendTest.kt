package os.openclaw.agentcanvas.backend

import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.test.runTest
import org.junit.Assert.*
import org.junit.Test

class MockBackendTest {

    @Test
    fun `streamChat emits deltas and done`() = runTest {
        val backend = MockBackend(responseText = "Hello!", delayPerChunkMs = 0, chunkSize = 3)
        val events = backend.streamChat(
            listOf(ChatMessage(ChatRole.User, "Hi"))
        ).toList()

        // Should have text deltas + Done
        val deltas = events.filterIsInstance<StreamEvent.Delta>()
        val done = events.filterIsInstance<StreamEvent.Done>()

        assertEquals("Hel", deltas[0].text)
        assertEquals("lo!", deltas[1].text)
        assertEquals(1, done.size)
    }

    @Test
    fun `streamChat emits error when configured`() = runTest {
        val backend = MockBackend(simulateError = ErrorKind.AuthFailed, delayPerChunkMs = 0)
        val events = backend.streamChat(
            listOf(ChatMessage(ChatRole.User, "Hi"))
        ).toList()

        assertEquals(1, events.size)
        val error = events[0] as StreamEvent.Error
        assertEquals(ErrorKind.AuthFailed, error.error.kind)
        assertFalse(error.error.retryable)
    }

    @Test
    fun `streamChat emits retryable error for cloud unavailable`() = runTest {
        val backend = MockBackend(simulateError = ErrorKind.CloudUnavailable, delayPerChunkMs = 0)
        val events = backend.streamChat(
            listOf(ChatMessage(ChatRole.User, "Hi"))
        ).toList()

        val error = (events[0] as StreamEvent.Error).error
        assertEquals(ErrorKind.CloudUnavailable, error.kind)
        assertTrue(error.retryable)
    }

    @Test
    fun `sendChat returns content`() = runTest {
        val backend = MockBackend(responseText = "Test response", delayPerChunkMs = 0)
        val result = backend.sendChat(listOf(ChatMessage(ChatRole.User, "Hi")))
        assertEquals("Test response", result.content)
        assertNotNull(result.usage)
    }

    @Test
    fun `sendChat throws on error`() = runTest {
        val backend = MockBackend(simulateError = ErrorKind.RateLimited, delayPerChunkMs = 0)
        try {
            backend.sendChat(listOf(ChatMessage(ChatRole.User, "Hi")))
            fail("Should have thrown")
        } catch (e: BackendException) {
            assertEquals(ErrorKind.RateLimited, e.error.kind)
        }
    }

    @Test
    fun `healthCheck returns reachable when no error`() = runTest {
        val backend = MockBackend(delayPerChunkMs = 0)
        val status = backend.healthCheck()
        assertTrue(status.reachable)
        assertNull(status.error)
    }

    @Test
    fun `healthCheck returns unreachable when error configured`() = runTest {
        val backend = MockBackend(simulateError = ErrorKind.Offline, delayPerChunkMs = 0)
        val status = backend.healthCheck()
        assertFalse(status.reachable)
        assertNotNull(status.error)
    }
}
