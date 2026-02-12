package org.openclaw.canvas.model

/**
 * Gesamtzustand des Canvas-Chats.
 */
data class CanvasState(
    val messages: List<ChatMessage> = emptyList(),
    val inputText: String = "",
    val isAgentTyping: Boolean = false,
) {
    /** Anzahl der Nachrichten. */
    val messageCount: Int get() = messages.size

    /** Prüft ob Senden möglich ist (nicht leer, Agent nicht am Tippen). */
    val canSend: Boolean get() = inputText.isNotBlank() && !isAgentTyping
}
