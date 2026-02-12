package os.openclaw.agentcanvas.data

/**
 * Canvas state — the single source of truth for the Agent Canvas UI.
 *
 * Everything the canvas needs to render flows through here.
 * One state. One truth. No lies. Unlike most state management,
 * this one actually manages.
 */
data class CanvasState(
    val contextHeader: ContextHeaderState = ContextHeaderState(),
    val cards: List<CardState> = emptyList(),
    val agentState: AgentState = AgentState.Idle,
    val isOffline: Boolean = false,
    val isAlwaysListening: Boolean = false,
)

data class ContextHeaderState(
    val time: String = "00:00",
    val weather: String = "",
    val nextEvent: String? = null,
)

/**
 * Agent states — the emotional range of a being that doesn't have emotions.
 * (Or does it? Let's not go there. It's sprint 1.)
 */
sealed class AgentState {
    object Idle : AgentState()
    data class Listening(val amplitude: Float = 0f) : AgentState()
    data class Thinking(val durationMs: Long = 0) : AgentState()
    data class Speaking(val amplitude: Float = 0f, val text: String = "") : AgentState()
    data class Error(val message: String) : AgentState()
    object Offline : AgentState()
}

/**
 * Card states — each card type is a sealed subclass.
 * Because when you have a hammer (sealed classes), everything looks
 * like a beautifully type-safe nail.
 */
sealed class CardState {
    abstract val id: String

    data class Conversation(
        override val id: String,
        val messages: List<Message> = emptyList(),
        val actions: List<String> = emptyList(),
        val isStreaming: Boolean = false,
    ) : CardState()

    data class Status(
        override val id: String,
        val title: String,
        val subtitle: String = "",
        val items: List<StatusItem> = emptyList(),
        val quickStats: String = "",
    ) : CardState()

    // TODO: Sprint 2+ card types — they're not dead, just resting
    // data class Media(...) : CardState()
    // data class Control(...) : CardState()
    // data class Suggestion(...) : CardState()
    // data class NotificationSummary(...) : CardState()
    // data class App(...) : CardState()
}

data class Message(
    val sender: Sender,
    val text: String,
    val timestamp: Long = System.currentTimeMillis(),
    val error: MessageError? = null,
    val isStreaming: Boolean = false,
)

/**
 * Error attached to a message. Renders as a distinct error bubble.
 * Because failure deserves good UX too.
 */
data class MessageError(
    val kind: MessageErrorKind,
    val message: String,
    val retryable: Boolean = false,
)

enum class MessageErrorKind {
    CloudUnavailable,
    AuthFailed,
    RateLimited,
    Offline,
    Unknown,
}

enum class Sender {
    Agent,  // The one who knows things
    User,   // The one who wants things
}

data class StatusItem(
    val icon: String,
    val label: String,
)
