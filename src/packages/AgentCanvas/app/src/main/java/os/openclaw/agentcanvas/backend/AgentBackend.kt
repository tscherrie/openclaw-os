/**
 * AgentBackend — The frontend's contract with whatever intelligence lives on the other side.
 *
 * This interface decouples the Canvas UI from any specific cloud provider,
 * making it trivially swappable between real clouds, mocks, and local inference.
 *
 * @author Prism (Frontend Lead, Agent Lab)
 * @since 0.2.0 (Sprint 3)
 */
package os.openclaw.agentcanvas.backend

import kotlinx.coroutines.flow.Flow

/**
 * Backend interface for agent communication.
 *
 * Implementations:
 * - [CloudBridgeBackend] — Production (OpenAI-compatible SSE via Gateway)
 * - [MockBackend] — Tests and Compose Previews
 */
interface AgentBackend {

    /**
     * Stream a chat completion response.
     *
     * @param messages Conversation history
     * @param model Model identifier (optional, uses default)
     * @return Flow of [StreamEvent]s — text deltas, errors, and completion signals
     */
    fun streamChat(
        messages: List<ChatMessage>,
        model: String? = null,
    ): Flow<StreamEvent>

    /**
     * Non-streaming chat completion. Use sparingly.
     */
    suspend fun sendChat(
        messages: List<ChatMessage>,
        model: String? = null,
    ): ChatResult

    /**
     * Check if the backend is reachable.
     */
    suspend fun healthCheck(): HealthStatus
}

// ==========================================
// Data Models
// ==========================================

data class ChatMessage(
    val role: ChatRole,
    val content: String,
)

enum class ChatRole {
    System,
    User,
    Assistant,
}

/**
 * Events emitted during streaming.
 */
sealed class StreamEvent {
    /** A chunk of text from the assistant */
    data class Delta(val text: String) : StreamEvent()

    /** Stream completed successfully */
    data class Done(val usage: TokenUsage? = null) : StreamEvent()

    /** An error occurred */
    data class Error(val error: BackendError) : StreamEvent()
}

data class ChatResult(
    val content: String,
    val usage: TokenUsage? = null,
)

data class TokenUsage(
    val promptTokens: Int,
    val completionTokens: Int,
    val totalTokens: Int = promptTokens + completionTokens,
)

data class HealthStatus(
    val reachable: Boolean,
    val latencyMs: Long? = null,
    val error: String? = null,
)

// ==========================================
// Errors
// ==========================================

data class BackendError(
    val kind: ErrorKind,
    val message: String,
    val retryable: Boolean = false,
    val httpStatus: Int? = null,
)

enum class ErrorKind {
    CloudUnavailable,
    AuthFailed,
    RateLimited,
    Offline,
    ContextTooLarge,
    Unknown,
}
