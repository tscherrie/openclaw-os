/**
 * MockBackend — Fake backend for tests and Compose Previews.
 *
 * Simulates streaming with configurable delay, and can trigger
 * any error scenario on demand. The Swiss Army knife of testing.
 *
 * @author Prism (Frontend Lead, Agent Lab)
 * @since 0.2.0 (Sprint 3)
 */
package os.openclaw.agentcanvas.backend

import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow

class MockBackend(
    private val responseText: String = "Ich bin der Agent. Wie kann ich helfen?",
    private val delayPerChunkMs: Long = 30L,
    private val chunkSize: Int = 3,
    private val simulateError: ErrorKind? = null,
) : AgentBackend {

    override fun streamChat(
        messages: List<ChatMessage>,
        model: String?,
    ): Flow<StreamEvent> = flow {
        // Simulate error if configured
        if (simulateError != null) {
            delay(200) // Brief delay to feel real
            emit(StreamEvent.Error(BackendError(
                kind = simulateError,
                message = when (simulateError) {
                    ErrorKind.CloudUnavailable -> "Cloud nicht erreichbar"
                    ErrorKind.AuthFailed -> "API Key ungültig"
                    ErrorKind.RateLimited -> "Zu viele Anfragen — bitte warten"
                    ErrorKind.Offline -> "Keine Internetverbindung"
                    ErrorKind.ContextTooLarge -> "Konversation zu lang"
                    ErrorKind.Unknown -> "Unbekannter Fehler"
                },
                retryable = simulateError != ErrorKind.AuthFailed,
            )))
            return@flow
        }

        // Stream text in chunks
        var i = 0
        while (i < responseText.length) {
            val end = minOf(i + chunkSize, responseText.length)
            emit(StreamEvent.Delta(responseText.substring(i, end)))
            delay(delayPerChunkMs)
            i = end
        }

        emit(StreamEvent.Done(TokenUsage(
            promptTokens = messages.sumOf { it.content.length / 4 },
            completionTokens = responseText.length / 4,
        )))
    }

    override suspend fun sendChat(
        messages: List<ChatMessage>,
        model: String?,
    ): ChatResult {
        delay(300) // Simulate network latency

        if (simulateError != null) {
            throw BackendException(BackendError(
                kind = simulateError,
                message = "Mock error: $simulateError",
                retryable = simulateError != ErrorKind.AuthFailed,
            ))
        }

        return ChatResult(
            content = responseText,
            usage = TokenUsage(
                promptTokens = messages.sumOf { it.content.length / 4 },
                completionTokens = responseText.length / 4,
            ),
        )
    }

    override suspend fun healthCheck(): HealthStatus {
        delay(50)
        return if (simulateError == null) {
            HealthStatus(reachable = true, latencyMs = 42)
        } else {
            HealthStatus(reachable = false, error = "Mock: simulated failure")
        }
    }
}
