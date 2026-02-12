/**
 * AgentCoreService — The Central Nervous System of OpenClaw OS
 *
 * This is the main system service that orchestrates the AI agent.
 * It runs in system_server with full platform privileges.
 * If this service were a person, it would be the one friend who
 * somehow knows everyone and can get you into any restaurant.
 *
 * @author Forge (Backend Lead, Agent Lab)
 * @since 0.1.0 (Sprint 1, February 2026)
 */
package com.openclaw.agent

import android.content.Context
import android.content.Intent
import android.os.IBinder
import android.util.Slog
import com.openclaw.agent.bridge.AccessibilityBridge
import com.openclaw.agent.bridge.CloudBridge
import com.openclaw.agent.bridge.TailscaleBridge
import com.openclaw.agent.context.ContextManager
import com.openclaw.agent.intent.IntentRouter
import com.openclaw.agent.model.*
import com.openclaw.agent.peripheral.PeripheralManager
import com.openclaw.agent.security.SecurityManager
import com.openclaw.agent.tools.ToolRegistry
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.Flow

/**
 * AgentCoreService — runs as a System Service inside system_server.
 *
 * Lifecycle:
 *   1. Registered in SystemServer.startOtherServices()
 *   2. onStart() → initialize internal state
 *   3. onBootPhase() → progressively acquire system service references
 *   4. PHASE_BOOT_COMPLETED → agent is fully alive, ready to serve
 *
 * Design invariant: If this service fails, the phone still works as a phone.
 * We degrade gracefully, not catastrophically. Unlike my cooking.
 */
class AgentCoreService(context: Context) {

    companion object {
        private const val TAG = "AgentCoreService"
        const val SERVICE_NAME = "agent_core"
    }

    // === Core Components ===
    private lateinit var cloudBridge: CloudBridge
    private lateinit var contextManager: ContextManager
    private lateinit var toolRegistry: ToolRegistry
    private lateinit var intentRouter: IntentRouter
    private lateinit var securityManager: SecurityManager
    private lateinit var accessibilityBridge: AccessibilityBridge
    private lateinit var tailscaleBridge: TailscaleBridge
    private lateinit var peripheralManager: PeripheralManager

    // === Agent State ===
    private var state: AgentState = AgentState.STARTING
    private var ownerProfile: UserProfile? = null

    // === Coroutine Scope (dies with the service) ===
    private val serviceScope = CoroutineScope(
        SupervisorJob() + Dispatchers.Default + CoroutineExceptionHandler { _, throwable ->
            Slog.e(TAG, "Uncaught exception in agent coroutine", throwable)
            // Don't crash system_server. Ever. EVER.
        }
    )

    // ==========================================
    // Lifecycle
    // ==========================================

    /**
     * Called when the service is first created.
     * Initialize components but don't connect to anything yet.
     * Think of this as waking up — eyes open, but not out of bed.
     */
    fun onStart() {
        Slog.i(TAG, "AgentCoreService starting... 🔥")

        try {
            // Initialize components with dependency injection
            securityManager = SecurityManager.create()
            contextManager = ContextManager.create()
            toolRegistry = ToolRegistry.create(securityManager)
            cloudBridge = CloudBridge.create()
            intentRouter = IntentRouter.create()
            accessibilityBridge = AccessibilityBridge.create()
            tailscaleBridge = TailscaleBridge.create()
            peripheralManager = PeripheralManager.create(tailscaleBridge)

            state = AgentState.DEGRADED
            Slog.i(TAG, "AgentCoreService components initialized (degraded mode)")
        } catch (e: Exception) {
            Slog.e(TAG, "Failed to initialize AgentCoreService", e)
            state = AgentState.ERROR
            // Phone still works. We just don't have an agent.
            // It's like a car without the radio — still drives.
        }
    }

    /**
     * Called at various boot phases.
     * We progressively acquire capabilities as the system comes up.
     */
    fun onBootPhase(phase: Int) {
        when (phase) {
            PHASE_SYSTEM_SERVICES_READY -> {
                Slog.i(TAG, "System services ready — acquiring references")
                acquireSystemServiceReferences()
            }
            PHASE_ACTIVITY_MANAGER_READY -> {
                Slog.i(TAG, "Activity manager ready — registering intent interceptors")
                registerIntentInterceptors()
            }
            PHASE_THIRD_PARTY_APPS_READY -> {
                Slog.i(TAG, "Third-party apps ready — initializing cloud bridge")
                initializeCloudConnection()
            }
            PHASE_BOOT_COMPLETED -> {
                Slog.i(TAG, "Boot completed — Agent is ALIVE! 🤖")
                onAgentReady()
            }
        }
    }

    // ==========================================
    // Agent Core Logic
    // ==========================================

    /**
     * Process an incoming message from the user.
     * This is the main entry point for all user interactions.
     *
     * @param request The user's request (text, voice, or system event)
     * @return A Flow of response chunks for streaming to the UI
     */
    suspend fun processRequest(request: AgentRequest): Flow<AgentResponseChunk> {
        Slog.d(TAG, "Processing request: ${request.type} — ${request.content.take(50)}...")

        // 1. Security check
        securityManager.validateRequest(request)

        // 2. Update context with this request
        contextManager.updateFromRequest(request)

        // 3. Build full context for LLM
        val context = contextManager.buildContext()

        // 4. Send to cloud (or local) and stream response
        val responseFlow = cloudBridge.sendMessage(request, context)

        // 5. Process response chunks (tool calls, card updates, etc.)
        return processResponseFlow(responseFlow)
    }

    /**
     * Handle an Android intent that was intercepted by the IntentRouter.
     * The agent decides: handle it, modify it, or let it pass.
     *
     * @return true if the agent handled the intent, false to pass through
     */
    suspend fun handleInterceptedIntent(intent: Intent): Boolean {
        val decision = intentRouter.evaluate(intent, contextManager.buildContext())

        return when (decision) {
            is IntentDecision.Intercept -> {
                Slog.d(TAG, "Agent intercepting intent: ${intent.action}")
                executeAgentAction(decision.action)
                true
            }
            is IntentDecision.ModifyAndPass -> {
                Slog.d(TAG, "Agent modifying intent: ${intent.action}")
                intentRouter.modifyIntent(intent, decision.modifications)
                false // Let modified intent pass through
            }
            is IntentDecision.PassThrough -> {
                false // Not our business
            }
        }
    }

    /**
     * Execute a tool call from the LLM response.
     * This is where the agent's decisions become reality.
     * The moment where JSON becomes action. Beautiful, isn't it?
     */
    private suspend fun executeTool(toolCall: ToolCall): ToolResult {
        Slog.d(TAG, "Executing tool: ${toolCall.toolId}.${toolCall.action}")

        // Security gate — check if this action is allowed
        val permission = securityManager.checkToolPermission(toolCall)
        if (!permission.allowed) {
            return ToolResult(
                callId = toolCall.id,
                success = false,
                error = "Permission denied: ${permission.reason}",
                durationMs = 0
            )
        }

        // If confirmation required, ask user
        if (permission.requiresConfirmation) {
            val confirmed = securityManager.requestUserConfirmation(toolCall)
            if (!confirmed) {
                return ToolResult(
                    callId = toolCall.id,
                    success = false,
                    error = "User declined",
                    durationMs = 0
                )
            }
        }

        // Execute!
        val startTime = System.currentTimeMillis()
        val result = toolRegistry.executeTool(toolCall)
        val duration = System.currentTimeMillis() - startTime

        // Audit trail
        securityManager.auditToolExecution(toolCall, result)

        // Update context
        contextManager.updateFromToolResult(toolCall, result)

        return result.copy(durationMs = duration)
    }

    // ==========================================
    // Emergency Controls
    // ==========================================

    /**
     * KILL SWITCH — Stop everything the agent is doing. Immediately.
     * No questions asked. No "are you sure?" dialogs.
     * When the human says stop, we stop.
     */
    fun emergencyStop() {
        Slog.w(TAG, "🚨 EMERGENCY STOP activated")
        serviceScope.coroutineContext.cancelChildren()
        cloudBridge.cancelAll()
        toolRegistry.cancelAll()
        state = AgentState.STOPPED
        // The agent sits in the corner and thinks about what it did.
    }

    // ==========================================
    // Private Helpers
    // ==========================================

    private fun acquireSystemServiceReferences() {
        // TODO: Get references to AMS, PMS, WMS, NMS, etc.
        // These are needed for intent interception, app control, etc.
        Slog.d(TAG, "Acquiring system service references...")
    }

    private fun registerIntentInterceptors() {
        // TODO: Register with AMS for intent interception
        Slog.d(TAG, "Registering intent interceptors...")
    }

    private fun initializeCloudConnection() {
        serviceScope.launch {
            try {
                val health = cloudBridge.healthCheck()
                if (health.connected) {
                    state = AgentState.ACTIVE
                    Slog.i(TAG, "Cloud bridge connected: ${health.provider}")
                } else {
                    Slog.w(TAG, "Cloud bridge not available, staying in degraded mode")
                }
            } catch (e: Exception) {
                Slog.w(TAG, "Cloud connection failed, degraded mode active", e)
            }
        }
    }

    private fun onAgentReady() {
        state = if (cloudBridge.isConnected()) AgentState.ACTIVE else AgentState.DEGRADED

        // Register all built-in tools
        registerBuiltInTools()

        // Start peripheral discovery
        serviceScope.launch {
            peripheralManager.discoverDevices()
        }

        Slog.i(TAG, "Agent ready! State: $state. Let's go. 🚀")
    }

    private fun registerBuiltInTools() {
        // TODO: Register all built-in tools (phone, SMS, camera, etc.)
        Slog.d(TAG, "Registering built-in tools...")
    }

    private fun processResponseFlow(
        responseFlow: Flow<AgentResponseChunk>
    ): Flow<AgentResponseChunk> {
        // TODO: Intercept tool calls in the stream, execute them,
        // and continue the conversation with results
        return responseFlow
    }

    private suspend fun executeAgentAction(action: AgentAction) {
        // TODO: Execute an agent-decided action (from intent interception)
        Slog.d(TAG, "Executing agent action: ${action.type}")
    }

    // ==========================================
    // Boot Phase Constants (from SystemService)
    // ==========================================

    companion object BootPhases {
        const val PHASE_SYSTEM_SERVICES_READY = 500
        const val PHASE_ACTIVITY_MANAGER_READY = 550
        const val PHASE_THIRD_PARTY_APPS_READY = 600
        const val PHASE_BOOT_COMPLETED = 1000
    }
}
