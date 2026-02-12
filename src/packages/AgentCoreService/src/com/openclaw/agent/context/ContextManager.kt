/**
 * ContextManager — The Agent's Memory
 *
 * Manages everything the agent knows: conversation history,
 * user preferences, device state, peripheral states, and more.
 *
 * This is the difference between an agent that says "Who are you?"
 * every time and one that says "Good morning Jeremias, your Tesla
 * is charged and Donika wants to know about dinner."
 *
 * Think of it as the agent's hippocampus. Except it never forgets
 * your birthday. Unlike some people's actual hippocampus.
 *
 * @author Forge (Backend Lead, Agent Lab)
 * @since 0.1.0
 */
package com.openclaw.agent.context

import com.openclaw.agent.model.*
import java.time.DayOfWeek
import java.time.Instant
import java.time.ZoneId
import java.time.ZonedDateTime

/**
 * Interface for managing the agent's context and memory.
 */
interface ContextManager {

    companion object {
        fun create(): ContextManager = ContextManagerImpl()
    }

    /**
     * Build the full conversation context for an LLM request.
     * This includes system prompt, history, device state, etc.
     */
    fun buildContext(): ConversationContext

    /**
     * Update context with a new user request.
     */
    fun updateFromRequest(request: AgentRequest)

    /**
     * Update context with an agent response.
     */
    fun updateFromResponse(response: AgentResponse)

    /**
     * Update context with a tool execution result.
     */
    fun updateFromToolResult(toolCall: ToolCall, result: ToolResult)

    /**
     * Update context from a device event (battery, connectivity, etc.)
     */
    fun updateFromDeviceEvent(event: DeviceEvent)

    /**
     * Get the user's profile.
     */
    fun getUserProfile(): UserProfile

    /**
     * Set/update user profile.
     */
    fun setUserProfile(profile: UserProfile)

    /**
     * Get current estimated token count for the context.
     * Used to decide when to compact/summarize history.
     */
    fun getEstimatedTokenCount(): Int

    /**
     * Compact conversation history to stay within token limits.
     * Summarizes older messages while keeping recent ones intact.
     */
    suspend fun compactHistory()

    /**
     * Persist context to encrypted local storage.
     */
    suspend fun persist()

    /**
     * Load context from storage.
     */
    suspend fun restore()
}

/**
 * Device events that update context.
 */
sealed class DeviceEvent {
    data class BatteryChanged(val percent: Int, val isCharging: Boolean) : DeviceEvent()
    data class ConnectivityChanged(val type: String, val connected: Boolean) : DeviceEvent()
    data class LocationChanged(val lat: Double, val lon: Double, val label: String?) : DeviceEvent()
    data class AppForeground(val packageName: String) : DeviceEvent()
    data class NotificationReceived(val packageName: String, val title: String, val text: String) : DeviceEvent()
    data class CallIncoming(val number: String, val contactName: String?) : DeviceEvent()
    data class PeripheralUpdate(val deviceId: String, val state: Map<String, Any?>) : DeviceEvent()
}

// ==========================================
// Implementation (Stub)
// ==========================================

internal class ContextManagerImpl : ContextManager {

    private var userProfile = UserProfile(
        name = "User",  // Set during onboarding
        language = "de",
        timezone = "Europe/Berlin"
    )

    private val conversationHistory = mutableListOf<Message>()
    private var deviceState = DeviceState(
        batteryPercent = 100,
        isCharging = false,
        connectivityType = "unknown",
        signalStrength = null,
        locationAvailable = false
    )
    private val peripheralStates = mutableMapOf<String, PeripheralState>()
    private val activeTasks = mutableListOf<TaskState>()

    // Maximum context window (in estimated tokens)
    // ~75% of Claude's window, leaving room for response
    private val maxContextTokens = 150_000

    override fun buildContext(): ConversationContext {
        val now = ZonedDateTime.now(ZoneId.of(userProfile.timezone))

        return ConversationContext(
            systemPrompt = buildSystemPrompt(),
            userProfile = userProfile,
            messages = conversationHistory.toList(),
            deviceState = deviceState,
            activeCards = emptyList(),  // TODO: Get from CardManager
            activeTasks = activeTasks.toList(),
            peripheralStates = peripheralStates.toMap(),
            timeContext = TimeContext(
                now = Instant.now(),
                timezone = userProfile.timezone,
                dayOfWeek = now.dayOfWeek.name,
                isWorkHours = now.hour in 9..17 && now.dayOfWeek !in listOf(
                    DayOfWeek.SATURDAY, DayOfWeek.SUNDAY
                ),
                upcomingEvents = emptyList()  // TODO: Query CalendarProvider
            ),
            availableTools = emptyList()  // TODO: Get from ToolRegistry
        )
    }

    override fun updateFromRequest(request: AgentRequest) {
        conversationHistory.add(
            Message(
                role = MessageRole.USER,
                content = request.content,
                timestamp = request.metadata.timestamp
            )
        )
        trimHistoryIfNeeded()
    }

    override fun updateFromResponse(response: AgentResponse) {
        conversationHistory.add(
            Message(
                role = MessageRole.ASSISTANT,
                content = response.text ?: "",
                toolCalls = response.toolCalls.takeIf { it.isNotEmpty() }
            )
        )
    }

    override fun updateFromToolResult(toolCall: ToolCall, result: ToolResult) {
        conversationHistory.add(
            Message(
                role = MessageRole.TOOL,
                content = "Tool ${toolCall.toolId}: ${if (result.success) "success" else "failed: ${result.error}"}",
                toolResults = listOf(result)
            )
        )
    }

    override fun updateFromDeviceEvent(event: DeviceEvent) {
        when (event) {
            is DeviceEvent.BatteryChanged -> {
                deviceState = deviceState.copy(
                    batteryPercent = event.percent,
                    isCharging = event.isCharging
                )
            }
            is DeviceEvent.ConnectivityChanged -> {
                deviceState = deviceState.copy(
                    connectivityType = if (event.connected) event.type else "none"
                )
            }
            is DeviceEvent.LocationChanged -> {
                deviceState = deviceState.copy(
                    locationAvailable = true,
                    latitude = event.lat,
                    longitude = event.lon,
                    locationLabel = event.label
                )
            }
            is DeviceEvent.PeripheralUpdate -> {
                peripheralStates[event.deviceId] = PeripheralState(
                    deviceId = event.deviceId,
                    deviceName = event.deviceId,  // TODO: Resolve name
                    deviceType = "unknown",
                    connected = true,
                    state = event.state
                )
            }
            else -> {
                // TODO: Handle other events
            }
        }
    }

    override fun getUserProfile(): UserProfile = userProfile

    override fun setUserProfile(profile: UserProfile) {
        userProfile = profile
    }

    override fun getEstimatedTokenCount(): Int {
        // Rough estimation: ~4 chars per token for German/English mix
        val totalChars = conversationHistory.sumOf { it.content.length }
        return totalChars / 4
    }

    override suspend fun compactHistory() {
        // TODO: Summarize older messages using the LLM
        // Keep last N messages intact, summarize the rest
        if (conversationHistory.size > 50) {
            val toSummarize = conversationHistory.take(conversationHistory.size - 20)
            val toKeep = conversationHistory.takeLast(20)

            // TODO: Call LLM to summarize toSummarize
            val summary = Message(
                role = MessageRole.SYSTEM,
                content = "[Summary of ${toSummarize.size} earlier messages]"
            )

            conversationHistory.clear()
            conversationHistory.add(summary)
            conversationHistory.addAll(toKeep)
        }
    }

    override suspend fun persist() {
        // TODO: Encrypt and save to local database
    }

    override suspend fun restore() {
        // TODO: Load from encrypted local database
    }

    // ==========================================
    // Private Helpers
    // ==========================================

    private fun buildSystemPrompt(): String {
        return """
            You are the personal AI agent for ${userProfile.name}. 
            You run on their phone as part of OpenClaw OS.
            
            You are helpful, proactive, and respect ${userProfile.name}'s preferences.
            You speak ${userProfile.language} by default.
            
            You have access to tools for controlling the phone, smart home devices,
            communication, and more. Use them when appropriate.
            
            Current time: ${Instant.now()} (${userProfile.timezone})
            Device: Battery ${deviceState.batteryPercent}%, ${deviceState.connectivityType}
            ${if (deviceState.locationLabel != null) "Location: ${deviceState.locationLabel}" else ""}
            
            Be concise. Be useful. Be ${userProfile.name}'s favorite AI.
        """.trimIndent()
    }

    private fun trimHistoryIfNeeded() {
        while (getEstimatedTokenCount() > maxContextTokens && conversationHistory.size > 5) {
            conversationHistory.removeAt(0)
        }
    }
}
