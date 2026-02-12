package org.openclaw.canvas.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import org.openclaw.canvas.mock.MockAgentBackend
import org.openclaw.canvas.model.CanvasState
import org.openclaw.canvas.model.ChatMessage
import org.openclaw.canvas.model.Sender
import java.util.UUID

/**
 * ViewModel für den Agent Canvas Chat.
 * Verwaltet Chat-State und koordiniert Mock-Agent-Antworten.
 */
class CanvasViewModel(
    private val backend: MockAgentBackend = MockAgentBackend(),
) : ViewModel() {

    private val _state = MutableStateFlow(CanvasState())
    val state: StateFlow<CanvasState> = _state.asStateFlow()

    /** Aktualisiert den Eingabetext. */
    fun onInputChanged(text: String) {
        _state.value = _state.value.copy(inputText = text)
    }

    /** Sendet die aktuelle Nachricht und triggert Agent-Antwort. */
    fun sendMessage() {
        val currentState = _state.value
        if (!currentState.canSend) return

        val userMessage = ChatMessage(
            id = UUID.randomUUID().toString(),
            text = currentState.inputText.trim(),
            sender = Sender.USER,
        )

        _state.value = currentState.copy(
            messages = currentState.messages + userMessage,
            inputText = "",
            isAgentTyping = true,
        )

        requestAgentResponse(userMessage.text)
    }

    private fun requestAgentResponse(userMessage: String) {
        val agentMessageId = UUID.randomUUID().toString()

        // WHY: Agent-Nachricht sofort als leer hinzufügen, dann per Streaming füllen
        _state.value = _state.value.copy(
            messages = _state.value.messages + ChatMessage(
                id = agentMessageId,
                text = "",
                sender = Sender.AGENT,
                isStreaming = true,
            ),
        )

        viewModelScope.launch {
            backend.getResponse(userMessage).collect { partialText ->
                _state.value = _state.value.copy(
                    messages = _state.value.messages.map { msg ->
                        if (msg.id == agentMessageId) {
                            msg.copy(text = partialText)
                        } else {
                            msg
                        }
                    },
                )
            }

            // Streaming fertig
            _state.value = _state.value.copy(
                isAgentTyping = false,
                messages = _state.value.messages.map { msg ->
                    if (msg.id == agentMessageId) {
                        msg.copy(isStreaming = false)
                    } else {
                        msg
                    }
                },
            )
        }
    }
}
