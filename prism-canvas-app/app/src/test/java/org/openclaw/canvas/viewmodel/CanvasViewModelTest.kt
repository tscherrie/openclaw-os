package org.openclaw.canvas.viewmodel

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.openclaw.canvas.model.Sender

@OptIn(ExperimentalCoroutinesApi::class)
class CanvasViewModelTest {

    private val testDispatcher = StandardTestDispatcher()
    private lateinit var viewModel: CanvasViewModel

    @Before
    fun setup() {
        Dispatchers.setMain(testDispatcher)
        viewModel = CanvasViewModel()
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    @Test
    fun `initialer State ist leer`() {
        val state = viewModel.state.value
        assertEquals(0, state.messageCount)
        assertEquals("", state.inputText)
        assertFalse(state.isAgentTyping)
    }

    @Test
    fun `onInputChanged aktualisiert inputText`() {
        viewModel.onInputChanged("Hallo Welt")
        assertEquals("Hallo Welt", viewModel.state.value.inputText)
    }

    @Test
    fun `sendMessage bei leerem Input tut nichts`() {
        viewModel.onInputChanged("")
        viewModel.sendMessage()
        assertEquals(0, viewModel.state.value.messageCount)
    }

    @Test
    fun `sendMessage fuegt User-Nachricht hinzu und leert Input`() = runTest {
        viewModel.onInputChanged("Test Nachricht")
        viewModel.sendMessage()

        val state = viewModel.state.value
        assertEquals("", state.inputText)
        // Mindestens User-Nachricht + leere Agent-Nachricht
        assertTrue(state.messages.size >= 1)
        assertEquals(Sender.USER, state.messages.first().sender)
        assertEquals("Test Nachricht", state.messages.first().text)
    }

    @Test
    fun `sendMessage triggert Agent-Antwort mit Streaming`() = runTest {
        viewModel.onInputChanged("Hallo")
        viewModel.sendMessage()

        // Nach dem Senden sollte Agent tippen
        assertTrue(viewModel.state.value.isAgentTyping)

        // Warten bis Agent fertig
        advanceUntilIdle()

        val state = viewModel.state.value
        assertFalse(state.isAgentTyping)
        assertEquals(2, state.messageCount)
        assertEquals(Sender.AGENT, state.messages[1].sender)
        assertTrue(state.messages[1].text.isNotEmpty())
        assertFalse(state.messages[1].isStreaming)
    }

    @Test
    fun `sendMessage blockiert waehrend Agent tippt`() = runTest {
        viewModel.onInputChanged("Erste")
        viewModel.sendMessage()

        // Versuche zweite Nachricht zu senden während Agent tippt
        viewModel.onInputChanged("Zweite")
        assertFalse(viewModel.state.value.canSend)

        advanceUntilIdle()

        // Jetzt sollte senden wieder möglich sein
        viewModel.onInputChanged("Zweite")
        assertTrue(viewModel.state.value.canSend)
    }

    @Test
    fun `mehrere Nachrichten wachsen den Chat`() = runTest {
        viewModel.onInputChanged("Erste")
        viewModel.sendMessage()
        advanceUntilIdle()

        viewModel.onInputChanged("Zweite")
        viewModel.sendMessage()
        advanceUntilIdle()

        assertEquals(4, viewModel.state.value.messageCount)
    }
}
