/**
 * CloudBridge — The agent's telephone line to the big brains in the sky.
 *
 * Handles all communication with LLM providers (Anthropic, OpenAI, local).
 * Supports streaming, offline queuing, and provider failover.
 *
 * @author Forge (Backend Lead, Agent Lab)
 * @since 0.1.0
 */
package com.openclaw.agent.bridge

import com.openclaw.agent.model.*
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow

/**
 * Interface for cloud LLM communication.
 *
 * Implementations: AnthropicCloudBridge, OpenAICloudBridge, LocalCloudBridge
 */
interface CloudBridge {

    companion object {
        fun create(): CloudBridge = CloudBridgeImpl()
    }

    /**
     * Send a message to the LLM and stream the response.
     *
     * @param request The user's request
     * @param context Full conversation context
     * @return Flow of response chunks (text, tool calls, etc.)
     */
    suspend fun sendMessage(
        request: AgentRequest,
        context: ConversationContext
    ): Flow<AgentResponseChunk>

    /**
     * Send a message and wait for the complete response.
     * Use sparingly — streaming is almost always better for UX.
     */
    suspend fun sendMessageSync(
        request: AgentRequest,
        context: ConversationContext
    ): AgentResponse

    /**
     * Health check — is the current provider reachable?
     */
    suspend fun healthCheck(): CloudHealthStatus

    /**
     * Is the bridge currently connected?
     */
    fun isConnected(): Boolean

    /**
     * Cancel all in-flight requests.
     * Used by emergency stop.
     */
    fun cancelAll()

    /**
     * Get current provider configuration.
     */
    fun getProvider(): CloudProvider

    /**
     * Switch provider at runtime.
     */
    fun setProvider(provider: CloudProvider, apiKey: String)
}

/**
 * Cloud provider configuration.
 */
data class CloudProvider(
    val id: String,            // "anthropic", "openai", "local"
    val name: String,          // "Anthropic Claude"
    val baseUrl: String,       // "https://api.anthropic.com"
    val defaultModel: String,  // "claude-sonnet-4-20250514"
    val supportsStreaming: Boolean = true,
    val supportsToolUse: Boolean = true,
    val supportsMultimodal: Boolean = true
)

/**
 * Health check result.
 */
data class CloudHealthStatus(
    val connected: Boolean,
    val provider: String,
    val latencyMs: Long? = null,
    val error: String? = null
)

// ==========================================
// Default Implementation (Stub)
// ==========================================

/**
 * Stub implementation of CloudBridge.
 * TODO: Replace with real HTTP/SSE implementation in Sprint 2.
 *
 * Currently returns "I'm not connected to any cloud yet" which is
 * technically accurate and also a valid response for many philosophical questions.
 */
internal class CloudBridgeImpl : CloudBridge {

    private var connected = false
    private var currentProvider = CloudProvider(
        id = "anthropic",
        name = "Anthropic Claude",
        baseUrl = "https://api.anthropic.com",
        defaultModel = "claude-sonnet-4-20250514"
    )

    override suspend fun sendMessage(
        request: AgentRequest,
        context: ConversationContext
    ): Flow<AgentResponseChunk> = flow {
        // TODO: Real implementation with OkHttp/Ktor + SSE parsing
        // For now, emit a placeholder response
        emit(AgentResponseChunk.Text("🚧 CloudBridge not yet implemented. "))
        emit(AgentResponseChunk.Text("I received: \"${request.content}\""))
        emit(AgentResponseChunk.Done(TokenUsage(
            inputTokens = 0,
            outputTokens = 0,
            model = currentProvider.defaultModel,
            provider = currentProvider.id
        )))
    }

    override suspend fun sendMessageSync(
        request: AgentRequest,
        context: ConversationContext
    ): AgentResponse {
        return AgentResponse(
            id = request.id,
            text = "🚧 CloudBridge not yet implemented. Received: \"${request.content}\"",
            usage = TokenUsage(0, 0, currentProvider.defaultModel, currentProvider.id)
        )
    }

    override suspend fun healthCheck(): CloudHealthStatus {
        // TODO: Actually ping the provider
        return CloudHealthStatus(
            connected = false,
            provider = currentProvider.id,
            error = "Not implemented yet — patience, young padawan"
        )
    }

    override fun isConnected(): Boolean = connected

    override fun cancelAll() {
        // TODO: Cancel all OkHttp/Ktor calls
    }

    override fun getProvider(): CloudProvider = currentProvider

    override fun setProvider(provider: CloudProvider, apiKey: String) {
        currentProvider = provider
        // TODO: Store API key in secure keystore
    }
}
