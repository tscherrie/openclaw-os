package org.openclaw.canvas.model

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CanvasStateTest {

    @Test
    fun `leerer State hat keine Nachrichten`() {
        val state = CanvasState()
        assertEquals(0, state.messageCount)
        assertTrue(state.messages.isEmpty())
    }

    @Test
    fun `canSend ist false bei leerem Input`() {
        val state = CanvasState(inputText = "")
        assertFalse(state.canSend)
    }

    @Test
    fun `canSend ist false bei nur Whitespace`() {
        val state = CanvasState(inputText = "   ")
        assertFalse(state.canSend)
    }

    @Test
    fun `canSend ist true bei Text und Agent nicht am Tippen`() {
        val state = CanvasState(inputText = "Hallo", isAgentTyping = false)
        assertTrue(state.canSend)
    }

    @Test
    fun `canSend ist false wenn Agent tippt`() {
        val state = CanvasState(inputText = "Hallo", isAgentTyping = true)
        assertFalse(state.canSend)
    }

    @Test
    fun `messageCount zaehlt korrekt`() {
        val messages = listOf(
            ChatMessage(id = "1", text = "Hi", sender = Sender.USER),
            ChatMessage(id = "2", text = "Hallo", sender = Sender.AGENT),
        )
        val state = CanvasState(messages = messages)
        assertEquals(2, state.messageCount)
    }

    @Test
    fun `ChatMessage Default isStreaming ist false`() {
        val msg = ChatMessage(id = "1", text = "Test", sender = Sender.USER)
        assertFalse(msg.isStreaming)
    }

    @Test
    fun `ChatMessage copy aendert nur gewuenschte Felder`() {
        val msg = ChatMessage(id = "1", text = "Alt", sender = Sender.AGENT, isStreaming = true)
        val updated = msg.copy(text = "Neu", isStreaming = false)
        assertEquals("1", updated.id)
        assertEquals("Neu", updated.text)
        assertEquals(Sender.AGENT, updated.sender)
        assertFalse(updated.isStreaming)
    }
}
