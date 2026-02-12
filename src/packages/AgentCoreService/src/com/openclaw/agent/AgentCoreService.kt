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

import android.app.Service
import android.content.Intent
import android.os.IBinder
import android.os.RemoteCallbackList
import android.util.Slog
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
 * AgentCoreService — runs as a privileged app Service.
 *
 * Lifecycle:
 *   1. onCreate() — initialize components (degraded mode)
 *   2. onStartCommand() — service started, prepare for requests
 *   3. onDestroy() — clean shutdown
 *
 * Design invariant: If this service fails, the phone still works as a phone.
 * We degrade gracefully, not catastrophically. Unlike my cooking.
 */
class AgentCoreService : Service() {

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
    // AccessibilityBridge is now a system service (com.openclaw.agent.service.AccessibilityBridge)
    private lateinit var tailscaleBridge: TailscaleBridge
    private lateinit var peripheralManager: PeripheralManager

    // === Agent State ===
    private var state: AgentState = AgentState.STARTING
    private var ownerProfile: UserProfile? = null

    // === Event Listeners (IPC callbacks) ===
    private val eventListeners = RemoteCallbackList<IAgentEventListener>()

    // === Coroutine Scope (dies with the service) ===
    private val serviceScope = CoroutineScope(
        SupervisorJob() + Dispatchers.Default + CoroutineExceptionHandler { _, throwable ->
            Slog.e(TAG, "Uncaught exception in agent coroutine", throwable)
        }
    )

    // ==========================================
    // Android Service Lifecycle
    // ==========================================

    override fun onCreate() {
        super.onCreate()
        Slog.i(TAG, "AgentCoreService.onCreate() 🔥")

        try {
            // Initialize components with dependency injection
            securityManager = SecurityManager.create()
            contextManager = ContextManager.create()
            toolRegistry = ToolRegistry.create(securityManager)
            cloudBridge = CloudBridge.create()
            intentRouter = IntentRouter.create()
            // AccessibilityBridge is now a system service — don't instantiate here
            tailscaleBridge = TailscaleBridge.create()
            peripheralManager = PeripheralManager.create(tailscaleBridge)

            state = AgentState.DEGRADED
            Slog.i(TAG, "AgentCoreService components initialized (degraded mode)")
        } catch (e: Exception) {
            Slog.e(TAG, "Failed to initialize AgentCoreService", e)
            state = AgentState.ERROR
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        Slog.i(TAG, "AgentCoreService.onStartCommand()")
        return START_STICKY
    }

    override fun onDestroy() {
        super.onDestroy()
        Slog.i(TAG, "AgentCoreService.onDestroy()")
        serviceScope.cancel()
        eventListeners.kill()
    }

    override fun onBind(intent: Intent?): IBinder {
        Slog.d(TAG, "onBind: ${intent?.action}")
        return binder
    }

    // ==========================================
    // AIDL Binder Implementation
    // ==========================================

    private val binder = object : IAgentCoreService.Stub() {
        override fun submitRequest(
            text: String?,
            callback: IAgentResponseCallback?
        ): String? {
            // TODO: Implement streaming via callback
            Slog.d(TAG, "submitRequest: $text")
            return "stub-request-id"
        }

        override fun cancelRequest(requestId: String?): Boolean {
            Slog.d(TAG, "cancelRequest: $requestId")
            return false
        }

        override fun getAgentState(): Int = state.ordinal

        override fun registerEventListener(listener: IAgentEventListener?) {
            listener?.let { eventListeners.register(it) }
            Slog.d(TAG, "registerEventListener")
        }

        override fun unregisterEventListener(listener: IAgentEventListener?) {
            listener?.let { eventListeners.unregister(it) }
            Slog.d(TAG, "unregisterEventListener")
        }

        override fun confirmAction(actionId: String?, confirmed: Boolean) {
            Slog.d(TAG, "confirmAction: $actionId = $confirmed")
        }

        override fun emergencyStop() {
            Slog.w(TAG, "🚨 EMERGENCY STOP")
            serviceScope.coroutineContext.cancelChildren()
            cloudBridge.cancelAll()
            state = AgentState.STOPPED
        }

        override fun isCloudAvailable(): Boolean = cloudBridge.isConnected()

        override fun getContextSummary(): String = "Not yet implemented"

        override fun setCapabilityEnabled(capabilityId: String?, enabled: Boolean): Boolean {
            Slog.d(TAG, "setCapabilityEnabled: $capabilityId = $enabled")
            return false
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
    // Private Helpers
    // ==========================================

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

}
