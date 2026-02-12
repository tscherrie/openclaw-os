/**
 * ToolRegistry — The Agent's Toolbox
 *
 * Manages all tools the agent can use. Tools are the agent's
 * interface to the real world — phone calls, smart home,
 * app control, etc.
 *
 * Every tool is registered here. When the LLM says "call smart_home
 * with {device: heater, temp: 22}", the ToolRegistry routes that
 * to the right implementation. Like a switchboard operator, but
 * for an AI. And without the attitude.
 *
 * @author Forge (Backend Lead, Agent Lab)
 * @since 0.1.0
 */
package com.openclaw.agent.tools

import com.openclaw.agent.model.*
import com.openclaw.agent.security.SecurityManager

/**
 * Registry for agent tools.
 */
interface ToolRegistry {

    companion object {
        fun create(securityManager: SecurityManager): ToolRegistry =
            ToolRegistryImpl(securityManager)
    }

    /**
     * Register a tool.
     */
    fun register(tool: AgentTool)

    /**
     * Unregister a tool.
     */
    fun unregister(toolId: String)

    /**
     * Get all registered tool definitions (for LLM context).
     */
    fun getToolDefinitions(): List<ToolDefinition>

    /**
     * Execute a tool call.
     *
     * @param call The tool call from the LLM
     * @return Result of execution
     */
    suspend fun executeTool(call: ToolCall): ToolResult

    /**
     * Check if a tool is registered and available.
     */
    fun isAvailable(toolId: String): Boolean

    /**
     * Cancel all running tool executions.
     */
    fun cancelAll()

    /**
     * Get the number of registered tools.
     * Mainly for logging. And bragging.
     */
    fun toolCount(): Int
}

/**
 * Base interface for all agent tools.
 *
 * Implement this to create a new tool the agent can use.
 * Every tool is a bridge between LLM JSON and real-world actions.
 */
interface AgentTool {
    /** Unique identifier for this tool */
    val id: String

    /** Human-readable name */
    val name: String

    /** Description for the LLM (be specific — the LLM reads this!) */
    val description: String

    /** JSON Schema for the tool's input parameters */
    val inputSchema: Map<String, Any>

    /** Required capability (null = always available) */
    val requiredCapability: AgentCapability?

    /**
     * Execute the tool with the given parameters.
     *
     * @param action The specific action to perform
     * @param parameters The parameters from the LLM
     * @return Result of the execution
     */
    suspend fun execute(action: String, parameters: Map<String, Any?>): ToolResult
}

// ==========================================
// Built-in Tool Stubs
// ==========================================

/**
 * Smart Home control tool.
 * Controls IoT devices via their respective APIs.
 */
class SmartHomeTool : AgentTool {
    override val id = "smart_home"
    override val name = "Smart Home Control"
    override val description = """
        Control smart home devices. Supported actions:
        - set_temperature: Set thermostat temperature
        - toggle_light: Turn lights on/off
        - toggle_plug: Turn smart plugs on/off
        - get_status: Get device status
        - open_garage: Open/close garage door
    """.trimIndent()
    override val inputSchema = mapOf(
        "type" to "object",
        "properties" to mapOf(
            "device_id" to mapOf("type" to "string", "description" to "Device identifier"),
            "action" to mapOf("type" to "string", "description" to "Action to perform"),
            "parameters" to mapOf("type" to "object", "description" to "Action-specific parameters")
        ),
        "required" to listOf("device_id", "action")
    )
    override val requiredCapability = AgentCapability.CAN_CONTROL_HOME

    override suspend fun execute(action: String, parameters: Map<String, Any?>): ToolResult {
        // TODO: Route to SwitchBot/Tapo/Meross drivers
        return ToolResult(
            callId = "",
            success = false,
            error = "Smart home bridge not yet implemented"
        )
    }
}

/**
 * Phone call tool.
 */
class PhoneCallTool : AgentTool {
    override val id = "phone_call"
    override val name = "Phone Call"
    override val description = "Make or manage phone calls. Actions: dial, hangup, mute, speaker"
    override val inputSchema = mapOf(
        "type" to "object",
        "properties" to mapOf(
            "action" to mapOf("type" to "string"),
            "number" to mapOf("type" to "string"),
            "contact_name" to mapOf("type" to "string")
        ),
        "required" to listOf("action")
    )
    override val requiredCapability = AgentCapability.CAN_COMMUNICATE

    override suspend fun execute(action: String, parameters: Map<String, Any?>): ToolResult {
        // TODO: Use TelecomManager to initiate/manage calls
        return ToolResult(callId = "", success = false, error = "Phone call tool not yet implemented")
    }
}

/**
 * SMS/Messaging tool.
 */
class SmsTool : AgentTool {
    override val id = "sms"
    override val name = "SMS / Messaging"
    override val description = "Send SMS messages. Actions: send, read_recent"
    override val inputSchema = mapOf(
        "type" to "object",
        "properties" to mapOf(
            "action" to mapOf("type" to "string"),
            "recipient" to mapOf("type" to "string"),
            "message" to mapOf("type" to "string")
        ),
        "required" to listOf("action")
    )
    override val requiredCapability = AgentCapability.CAN_COMMUNICATE

    override suspend fun execute(action: String, parameters: Map<String, Any?>): ToolResult {
        // TODO: Use SmsManager to send SMS
        return ToolResult(callId = "", success = false, error = "SMS tool not yet implemented")
    }
}

/**
 * Camera tool.
 */
class CameraTool : AgentTool {
    override val id = "camera"
    override val name = "Camera"
    override val description = "Capture photos or videos. Actions: photo, video, screenshot"
    override val inputSchema = mapOf(
        "type" to "object",
        "properties" to mapOf(
            "action" to mapOf("type" to "string"),
            "mode" to mapOf("type" to "string", "description" to "front, back, or auto")
        ),
        "required" to listOf("action")
    )
    override val requiredCapability = AgentCapability.CAN_CAPTURE

    override suspend fun execute(action: String, parameters: Map<String, Any?>): ToolResult {
        // TODO: Use Camera2 API
        return ToolResult(callId = "", success = false, error = "Camera tool not yet implemented")
    }
}

/**
 * Vehicle control tool (Tesla).
 */
class VehicleControlTool : AgentTool {
    override val id = "vehicle"
    override val name = "Vehicle Control"
    override val description = """
        Control Tesla vehicle. Actions: 
        lock, unlock, climate_on, climate_off, honk, flash_lights, 
        charge_limit, open_trunk, get_status
    """.trimIndent()
    override val inputSchema = mapOf(
        "type" to "object",
        "properties" to mapOf(
            "action" to mapOf("type" to "string"),
            "parameters" to mapOf("type" to "object")
        ),
        "required" to listOf("action")
    )
    override val requiredCapability = AgentCapability.CAN_CONTROL_VEHICLE

    override suspend fun execute(action: String, parameters: Map<String, Any?>): ToolResult {
        // TODO: Use Tesla Fleet API
        return ToolResult(callId = "", success = false, error = "Vehicle control not yet implemented")
    }
}

// ==========================================
// Registry Implementation
// ==========================================

internal class ToolRegistryImpl(
    private val securityManager: SecurityManager
) : ToolRegistry {

    private val tools = mutableMapOf<String, AgentTool>()

    override fun register(tool: AgentTool) {
        tools[tool.id] = tool
        android.util.Slog.i("ToolRegistry", "Registered tool: ${tool.id} (${tool.name})")
    }

    override fun unregister(toolId: String) {
        tools.remove(toolId)
    }

    override fun getToolDefinitions(): List<ToolDefinition> {
        return tools.values.map { tool ->
            ToolDefinition(
                id = tool.id,
                name = tool.name,
                description = tool.description,
                inputSchema = tool.inputSchema,
                requiredCapability = tool.requiredCapability
            )
        }
    }

    override suspend fun executeTool(call: ToolCall): ToolResult {
        val tool = tools[call.toolId]
            ?: return ToolResult(
                callId = call.id,
                success = false,
                error = "Unknown tool: ${call.toolId}. " +
                    "Available tools: ${tools.keys.joinToString()}"
            )

        // Check capability
        tool.requiredCapability?.let { cap ->
            val permission = securityManager.checkCapability(cap)
            if (!permission.allowed) {
                return ToolResult(
                    callId = call.id,
                    success = false,
                    error = "Capability ${cap.name} not granted: ${permission.reason}"
                )
            }
        }

        return try {
            tool.execute(call.action, call.parameters)
                .copy(callId = call.id)
        } catch (e: Exception) {
            ToolResult(
                callId = call.id,
                success = false,
                error = "Tool execution failed: ${e.message}"
            )
        }
    }

    override fun isAvailable(toolId: String): Boolean = toolId in tools

    override fun cancelAll() {
        // TODO: Cancel all in-flight tool executions
    }

    override fun toolCount(): Int = tools.size
}
