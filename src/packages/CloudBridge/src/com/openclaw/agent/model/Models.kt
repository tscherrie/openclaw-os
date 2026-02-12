/**
 * Core data models for AgentCoreService.
 *
 * These are the nouns of our system. The verbs live in the interfaces.
 * Together they form sentences like "Agent sends message to cloud"
 * and "User taps card action". Poetry, really.
 *
 * @author Forge (Backend Lead, Agent Lab)
 * @since 0.1.0
 */
package com.openclaw.agent.model

import java.time.Instant
import java.util.UUID

// ==========================================
// Agent State
// ==========================================

/**
 * The agent's current operational state.
 * Like a traffic light, but with more existential implications.
 */
enum class AgentState {
    STARTING,    // Booting up, components initializing
    DEGRADED,    // Running but no cloud connection (local inference only)
    ACTIVE,      // Fully operational, cloud connected
    STOPPED,     // Emergency stop activated
    ERROR        // Something went wrong during initialization
}

// ==========================================
// Requests & Responses
// ==========================================

/**
 * A request from the user or system to the agent.
 */
data class AgentRequest(
    val id: String = UUID.randomUUID().toString(),
    val type: RequestType,
    val content: String,
    val attachments: List<Attachment> = emptyList(),
    val metadata: RequestMetadata = RequestMetadata()
)

enum class RequestType {
    TEXT,           // User typed something
    VOICE,          // User spoke (already transcribed)
    INTENT,         // Android intent was intercepted
    SYSTEM_EVENT,   // System event (battery low, call incoming, etc.)
    CARD_ACTION     // User tapped a card button
}

data class Attachment(
    val type: AttachmentType,
    val uri: String,
    val mimeType: String? = null,
    val data: ByteArray? = null
)

enum class AttachmentType {
    IMAGE, AUDIO, VIDEO, FILE
}

data class RequestMetadata(
    val timestamp: Instant = Instant.now(),
    val source: String = "user",
    val priority: Priority = Priority.NORMAL
)

enum class Priority {
    LOW, NORMAL, HIGH, CRITICAL
}

/**
 * A chunk of the agent's streaming response.
 * Like opening a present slowly — the excitement is in the unwrapping.
 */
sealed class AgentResponseChunk {
    /** Text content being streamed */
    data class Text(val content: String) : AgentResponseChunk()

    /** Agent wants to call a tool */
    data class ToolUse(val toolCall: ToolCall) : AgentResponseChunk()

    /** Agent wants to show/update a card on the Canvas */
    data class CardUpdate(val card: CardDefinition) : AgentResponseChunk()

    /** Response is complete */
    data class Done(val usage: TokenUsage) : AgentResponseChunk()

    /** Something went wrong */
    data class Error(val error: AgentError) : AgentResponseChunk()
}

/**
 * Complete (non-streaming) agent response.
 */
data class AgentResponse(
    val id: String,
    val text: String? = null,
    val toolCalls: List<ToolCall> = emptyList(),
    val cardUpdates: List<CardDefinition> = emptyList(),
    val usage: TokenUsage
)

// ==========================================
// Tool Calls
// ==========================================

/**
 * A tool call requested by the LLM.
 * This is the agent saying "I know what to do, let me do it."
 */
data class ToolCall(
    val id: String = UUID.randomUUID().toString(),
    val toolId: String,
    val action: String,
    val parameters: Map<String, Any?> = emptyMap()
)

/**
 * Result of executing a tool call.
 * The moment of truth — did it work?
 */
data class ToolResult(
    val callId: String,
    val success: Boolean,
    val result: Map<String, Any?>? = null,
    val error: String? = null,
    val durationMs: Long = 0
)

/**
 * Definition of a tool that the agent can use.
 * Sent to the LLM as part of the system prompt.
 */
data class ToolDefinition(
    val id: String,
    val name: String,
    val description: String,
    val inputSchema: Map<String, Any>,
    val requiredCapability: AgentCapability? = null
)

// ==========================================
// Cards (Agent ↔ UI Contract)
// ==========================================

/**
 * A card to display on the Agent Canvas.
 * Cards are the agent's way of showing you things without
 * making you read through a wall of text. UI candy. 🍬
 */
data class CardDefinition(
    val id: String = UUID.randomUUID().toString(),
    val type: CardType,
    val priority: Int = 0,
    val title: String? = null,
    val subtitle: String? = null,
    val body: String? = null,
    val iconUrl: String? = null,
    val actions: List<CardAction> = emptyList(),
    val data: Map<String, Any?> = emptyMap(),
    val expiresAt: Instant? = null,
    val persistent: Boolean = false
)

enum class CardType {
    INFO,           // Passive information (weather, time)
    ACTION,         // Suggested action ("Donika wrote — reply?")
    MEDIA,          // Music, video, photos
    MAP,            // Navigation, location
    APP,            // Embedded app view
    INPUT,          // Agent needs input from user
    DEVICE,         // Peripheral device status
    NOTIFICATION    // Batched notifications
}

data class CardAction(
    val id: String,
    val label: String,
    val icon: String? = null,
    val style: CardActionStyle = CardActionStyle.DEFAULT,
    val agentMessage: String  // What to send to agent when tapped
)

enum class CardActionStyle {
    DEFAULT, PRIMARY, DESTRUCTIVE, SECONDARY
}

// ==========================================
// Context
// ==========================================

/**
 * The full conversation context sent to the LLM.
 * This is the agent's working memory — everything it knows
 * about you, your devices, and the current situation.
 */
data class ConversationContext(
    val systemPrompt: String,
    val userProfile: UserProfile,
    val messages: List<Message>,
    val deviceState: DeviceState,
    val activeCards: List<CardDefinition>,
    val activeTasks: List<TaskState>,
    val peripheralStates: Map<String, PeripheralState>,
    val timeContext: TimeContext,
    val availableTools: List<ToolDefinition>
)

data class Message(
    val role: MessageRole,
    val content: String,
    val timestamp: Instant = Instant.now(),
    val toolCalls: List<ToolCall>? = null,
    val toolResults: List<ToolResult>? = null
)

enum class MessageRole {
    SYSTEM, USER, ASSISTANT, TOOL
}

data class UserProfile(
    val name: String,
    val language: String = "de",
    val timezone: String = "Europe/Berlin",
    val preferences: Map<String, Any?> = emptyMap()
)

data class DeviceState(
    val batteryPercent: Int,
    val isCharging: Boolean,
    val connectivityType: String, // "wifi", "cellular", "none"
    val signalStrength: Int?,
    val locationAvailable: Boolean,
    val latitude: Double? = null,
    val longitude: Double? = null,
    val locationLabel: String? = null  // "home", "work", "unterwegs"
)

data class TimeContext(
    val now: Instant,
    val timezone: String,
    val dayOfWeek: String,
    val isWorkHours: Boolean,
    val upcomingEvents: List<CalendarEvent>
)

data class CalendarEvent(
    val title: String,
    val startTime: Instant,
    val endTime: Instant?,
    val location: String? = null
)

data class TaskState(
    val id: String,
    val description: String,
    val status: TaskStatus,
    val createdAt: Instant,
    val completedAt: Instant? = null
)

enum class TaskStatus {
    PENDING, IN_PROGRESS, COMPLETED, FAILED, CANCELLED
}

data class PeripheralState(
    val deviceId: String,
    val deviceName: String,
    val deviceType: String,
    val connected: Boolean,
    val state: Map<String, Any?> = emptyMap(),
    val lastUpdated: Instant = Instant.now()
)

// ==========================================
// Security & Capabilities
// ==========================================

/**
 * Agent capabilities — what the agent is allowed to do.
 * Like permissions, but for a sentient (well, kinda) service.
 */
enum class AgentCapability {
    CAN_COMMUNICATE,      // Calls, messages, email
    CAN_NAVIGATE,         // Location, maps
    CAN_CAPTURE,          // Camera, microphone, screenshots
    CAN_PURCHASE,         // Payments, orders
    CAN_CONTROL_HOME,     // Smart home devices
    CAN_CONTROL_VEHICLE,  // Tesla, etc.
    CAN_ACCESS_HEALTH,    // Fitness, health data
    CAN_MANAGE_FILES      // Documents, photos, downloads
}

data class PermissionResult(
    val allowed: Boolean,
    val requiresConfirmation: Boolean = false,
    val reason: String? = null
)

data class AuditEntry(
    val id: String = UUID.randomUUID().toString(),
    val timestamp: Instant = Instant.now(),
    val action: String,
    val toolId: String?,
    val parameters: Map<String, Any?>?,
    val result: String,
    val success: Boolean
)

// ==========================================
// Token Usage & Cost
// ==========================================

data class TokenUsage(
    val inputTokens: Int,
    val outputTokens: Int,
    val model: String,
    val provider: String,
    val estimatedCostUsd: Double? = null
)

// ==========================================
// Errors
// ==========================================

data class AgentError(
    val code: ErrorCode,
    val message: String,
    val retryable: Boolean = false,
    val details: Map<String, Any?> = emptyMap()
)

enum class ErrorCode {
    CLOUD_UNAVAILABLE,
    CLOUD_RATE_LIMITED,
    CLOUD_AUTH_FAILED,
    TOOL_EXECUTION_FAILED,
    PERMISSION_DENIED,
    USER_CANCELLED,
    CONTEXT_TOO_LARGE,
    INTERNAL_ERROR,
    OFFLINE
}

// ==========================================
// Intent Routing
// ==========================================

/**
 * Agent's decision about an intercepted Android intent.
 */
sealed class IntentDecision {
    /** Let it through — not our business */
    object PassThrough : IntentDecision()

    /** We'll handle this */
    data class Intercept(val action: AgentAction) : IntentDecision()

    /** Modify and let it pass */
    data class ModifyAndPass(val modifications: Map<String, Any?>) : IntentDecision()
}

data class AgentAction(
    val type: String,
    val parameters: Map<String, Any?> = emptyMap()
)
