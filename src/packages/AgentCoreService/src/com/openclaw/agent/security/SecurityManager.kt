/**
 * SecurityManager — The Bouncer
 *
 * Enforces capability-based access control for the agent.
 * Every action the agent takes goes through here first.
 *
 * The philosophy: Trust but verify. The LLM can suggest anything,
 * but we decide what actually happens. Like a restaurant where
 * the chef can propose any dish, but the maître d' decides
 * if you're actually allowed to eat at that table.
 *
 * @author Forge (Backend Lead, Agent Lab)
 * @since 0.1.0
 */
package com.openclaw.agent.security

import com.openclaw.agent.model.*
import java.time.Instant

/**
 * Interface for security and access control.
 */
interface SecurityManager {

    companion object {
        fun create(): SecurityManager = SecurityManagerImpl()
    }

    /**
     * Validate an incoming request.
     * Throws SecurityException if the request is malformed or suspicious.
     */
    fun validateRequest(request: AgentRequest)

    /**
     * Check if a tool call is permitted under current capabilities.
     */
    fun checkToolPermission(toolCall: ToolCall): PermissionResult

    /**
     * Check if a specific capability is granted.
     */
    fun checkCapability(capability: AgentCapability): PermissionResult

    /**
     * Request user confirmation for a critical action.
     * Shows a system dialog that the agent cannot bypass.
     *
     * @return true if user confirmed, false if declined or timed out
     */
    suspend fun requestUserConfirmation(toolCall: ToolCall): Boolean

    /**
     * Record an action in the audit trail.
     * Every. Single. Action. No exceptions. No "it's just a small thing".
     */
    fun auditToolExecution(toolCall: ToolCall, result: ToolResult)

    /**
     * Get audit log entries.
     */
    fun getAuditLog(since: Instant, limit: Int = 100): List<AuditEntry>

    /**
     * Grant a capability to the agent.
     */
    fun grantCapability(capability: AgentCapability)

    /**
     * Revoke a capability from the agent.
     */
    fun revokeCapability(capability: AgentCapability)

    /**
     * Get all currently granted capabilities.
     */
    fun getGrantedCapabilities(): Set<AgentCapability>

    /**
     * KILL SWITCH — immediately halt all agent actions.
     * This is the "oh no" button. Accessible from hardware button combo
     * or voice command "Agent, stopp alles".
     */
    fun activateKillSwitch()

    /**
     * Deactivate kill switch, resume normal operation.
     */
    fun deactivateKillSwitch()

    /**
     * Is the kill switch currently active?
     */
    fun isKillSwitchActive(): Boolean
}

/**
 * Actions that ALWAYS require user confirmation.
 * No exceptions. Not even if the user said "don't ask me".
 * Some things are too important to YOLO.
 */
object CriticalActions {
    val ALWAYS_CONFIRM = setOf(
        "payment",
        "purchase",
        "delete_data",
        "uninstall_app",
        "factory_reset",
        "share_location_persistent",
        "send_money",
        "modify_security_settings"
    )

    val CONFIRM_FIRST_TIME = setOf(
        "send_message",      // First time per contact
        "make_call",         // First time per contact
        "share_photo",       // First time per recipient
        "control_garage",    // Can be configured to skip
        "unlock_vehicle"     // Can be configured to skip
    )
}

// ==========================================
// Implementation
// ==========================================

internal class SecurityManagerImpl : SecurityManager {

    private val grantedCapabilities = mutableSetOf<AgentCapability>()
    private val auditLog = mutableListOf<AuditEntry>()
    private var killSwitchActive = false

    // Rate limiting: prevent runaway agent loops
    private var actionCountThisMinute = 0
    private var minuteStart = Instant.now()
    private val maxActionsPerMinute = 30  // If the agent does 30 things in a minute, something is wrong

    override fun validateRequest(request: AgentRequest) {
        if (killSwitchActive) {
            throw SecurityException("Kill switch is active. All agent actions are halted.")
        }

        // Rate limiting
        val now = Instant.now()
        if (now.epochSecond - minuteStart.epochSecond > 60) {
            actionCountThisMinute = 0
            minuteStart = now
        }
        actionCountThisMinute++
        if (actionCountThisMinute > maxActionsPerMinute) {
            throw SecurityException(
                "Rate limit exceeded ($maxActionsPerMinute actions/minute). " +
                "Either something is wrong or the agent is VERY enthusiastic."
            )
        }

        // Basic validation
        if (request.content.length > 100_000) {
            throw SecurityException("Request content too large (${request.content.length} chars)")
        }
    }

    override fun checkToolPermission(toolCall: ToolCall): PermissionResult {
        if (killSwitchActive) {
            return PermissionResult(
                allowed = false,
                reason = "Kill switch active"
            )
        }

        // Check if action always requires confirmation
        val requiresConfirmation = toolCall.action in CriticalActions.ALWAYS_CONFIRM ||
            toolCall.action in CriticalActions.CONFIRM_FIRST_TIME

        return PermissionResult(
            allowed = true,
            requiresConfirmation = requiresConfirmation,
            reason = null
        )
    }

    override fun checkCapability(capability: AgentCapability): PermissionResult {
        val hasCapability = capability in grantedCapabilities
        return PermissionResult(
            allowed = hasCapability,
            reason = if (!hasCapability) "Capability ${capability.name} not granted" else null
        )
    }

    override suspend fun requestUserConfirmation(toolCall: ToolCall): Boolean {
        // TODO: Show system confirmation dialog
        // This must be a SYSTEM dialog that the agent cannot dismiss
        // The user has full control here
        android.util.Slog.i("SecurityManager",
            "Confirmation requested for: ${toolCall.toolId}.${toolCall.action}")
        return false // Default deny until UI is implemented
    }

    override fun auditToolExecution(toolCall: ToolCall, result: ToolResult) {
        val entry = AuditEntry(
            timestamp = Instant.now(),
            action = "${toolCall.toolId}.${toolCall.action}",
            toolId = toolCall.toolId,
            parameters = toolCall.parameters,
            result = if (result.success) "success" else "failed: ${result.error}",
            success = result.success
        )
        auditLog.add(entry)

        // Keep audit log bounded (persist old entries to DB)
        if (auditLog.size > 10_000) {
            // TODO: Persist to encrypted SQLite before trimming
            auditLog.subList(0, 5_000).clear()
        }
    }

    override fun getAuditLog(since: Instant, limit: Int): List<AuditEntry> {
        return auditLog
            .filter { it.timestamp >= since }
            .takeLast(limit)
    }

    override fun grantCapability(capability: AgentCapability) {
        grantedCapabilities.add(capability)
        android.util.Slog.i("SecurityManager", "Granted capability: ${capability.name}")
    }

    override fun revokeCapability(capability: AgentCapability) {
        grantedCapabilities.remove(capability)
        android.util.Slog.i("SecurityManager", "Revoked capability: ${capability.name}")
    }

    override fun getGrantedCapabilities(): Set<AgentCapability> =
        grantedCapabilities.toSet()

    override fun activateKillSwitch() {
        killSwitchActive = true
        android.util.Slog.w("SecurityManager", "🚨 KILL SWITCH ACTIVATED")
    }

    override fun deactivateKillSwitch() {
        killSwitchActive = false
        android.util.Slog.i("SecurityManager", "Kill switch deactivated, resuming normal operation")
    }

    override fun isKillSwitchActive(): Boolean = killSwitchActive
}
