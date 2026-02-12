package org.openclaw.canvas.mock

import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow

/**
 * Mock-Backend das Agent-Antworten mit Streaming-Delay simuliert.
 * Jedes Token wird einzeln emittiert um Streaming nachzuahmen.
 */
class MockAgentBackend {

    private val responses = listOf(
        "Ich bin dein Agent. Wie kann ich dir helfen?",
        "Das ist eine gute Frage! Lass mich kurz nachdenken…",
        "Ich habe die Informationen gefunden, die du brauchst.",
        "Klar, das kann ich für dich erledigen.",
        "Hier ist meine Antwort auf deine Anfrage.",
        "Interessant! Dazu habe ich folgende Gedanken…",
    )

    private var responseIndex = 0

    /**
     * Gibt eine Agent-Antwort als Token-Stream zurück.
     * Jedes Token ist ein einzelnes Wort mit simuliertem Delay.
     */
    fun getResponse(userMessage: String): Flow<String> = flow {
        val response = responses[responseIndex % responses.size]
        responseIndex++

        val words = response.split(" ")
        val accumulated = StringBuilder()

        for ((index, word) in words.withIndex()) {
            if (index > 0) accumulated.append(" ")
            accumulated.append(word)
            emit(accumulated.toString())
            delay(TOKEN_DELAY_MS)
        }
    }

    companion object {
        /** Delay zwischen Tokens in Millisekunden. */
        const val TOKEN_DELAY_MS = 80L
    }
}
