package org.openclaw.canvas.model

/**
 * Einzelne Chat-Nachricht im Canvas.
 *
 * @property id Eindeutige ID
 * @property text Nachrichteninhalt (wächst bei Streaming)
 * @property sender Absender der Nachricht
 * @property isStreaming Ob die Nachricht gerade gestreamt wird
 */
data class ChatMessage(
    val id: String,
    val text: String,
    val sender: Sender,
    val isStreaming: Boolean = false,
)

/** Absender einer Nachricht. */
enum class Sender {
    USER,
    AGENT,
}
