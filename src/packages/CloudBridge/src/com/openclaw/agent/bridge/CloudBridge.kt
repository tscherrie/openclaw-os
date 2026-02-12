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

import com.openclaw.agent.model.AgentError
import com.openclaw.agent.model.AgentRequest
import com.openclaw.agent.model.AgentResponse
import com.openclaw.agent.model.AgentResponseChunk
import com.openclaw.agent.model.ConversationContext
import com.openclaw.agent.model.ErrorCode
import com.openclaw.agent.model.Message
import com.openclaw.agent.model.MessageRole
import com.openclaw.agent.model.TokenUsage
import java.io.IOException
import java.util.Collections
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import okhttp3.Call
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject

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
// OkHttp SSE Implementation (OpenAI-style)
// ==========================================

internal class CloudBridgeImpl : CloudBridge {

    private val client = OkHttpClient.Builder()
        .connectTimeout(20, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.SECONDS)
        .build()

    private val activeCalls = Collections.synchronizedSet(mutableSetOf<Call>())
    private var apiKey: String = ""
    private var connected = false

    private var currentProvider = CloudProvider(
        id = "openai",
        name = "OpenAI",
        baseUrl = "https://api.openai.com",
        defaultModel = "gpt-4o-mini"
    )

    override suspend fun sendMessage(
        request: AgentRequest,
        context: ConversationContext
    ): Flow<AgentResponseChunk> = flow {
        if (apiKey.isBlank()) {
            emit(errorChunk(ErrorCode.CLOUD_AUTH_FAILED, "Missing API key", retryable = false))
            return@flow
        }

        val httpRequest = buildHttpRequest(request, context, stream = true)
        val call = client.newCall(httpRequest)
        activeCalls.add(call)

        try {
            call.execute().use { response ->
                if (!response.isSuccessful) {
                    connected = false
                    emit(errorChunk(
                        ErrorCode.CLOUD_UNAVAILABLE,
                        "HTTP ${response.code}: ${response.message}",
                        retryable = response.code >= 500
                    ))
                    return@flow
                }

                connected = true
                val source = response.body?.source()
                if (source == null) {
                    emit(errorChunk(ErrorCode.CLOUD_UNAVAILABLE, "Empty response body", true))
                    return@flow
                }

                var lastUsage: TokenUsage? = null
                while (true) {
                    val line = source.readUtf8Line() ?: break
                    if (line.isBlank() || !line.startsWith("data:")) {
                        continue
                    }

                    val data = line.removePrefix("data:").trim()
                    if (data == "[DONE]") {
                        val usage = lastUsage ?: TokenUsage(
                            inputTokens = 0,
                            outputTokens = 0,
                            model = currentProvider.defaultModel,
                            provider = currentProvider.id
                        )
                        emit(AgentResponseChunk.Done(usage))
                        break
                    }

                    val eventJson = JSONObject(data)
                    val model = eventJson.optString("model", currentProvider.defaultModel)
                    val usage = parseUsage(eventJson, model)
                    if (usage != null) {
                        lastUsage = usage
                    }

                    val chunks = parseStreamDeltas(eventJson)
                    for (chunk in chunks) {
                        emit(chunk)
                    }
                }
            }
        } catch (e: IOException) {
            connected = false
            emit(errorChunk(ErrorCode.CLOUD_UNAVAILABLE, e.message ?: "Network error", true))
        } finally {
            activeCalls.remove(call)
        }
    }.flowOn(Dispatchers.IO)

    override suspend fun sendMessageSync(
        request: AgentRequest,
        context: ConversationContext
    ): AgentResponse {
        if (apiKey.isBlank()) {
            return AgentResponse(
                id = request.id,
                text = null,
                usage = TokenUsage(0, 0, currentProvider.defaultModel, currentProvider.id)
            )
        }

        val httpRequest = buildHttpRequest(request, context, stream = false)
        val call = client.newCall(httpRequest)
        activeCalls.add(call)

        return try {
            call.execute().use { response ->
                if (!response.isSuccessful) {
                    connected = false
                    return AgentResponse(
                        id = request.id,
                        text = null,
                        usage = TokenUsage(0, 0, currentProvider.defaultModel, currentProvider.id)
                    )
                }

                connected = true
                val body = response.body?.string().orEmpty()
                val json = JSONObject(body)
                val text = extractMessageText(json)
                val model = json.optString("model", currentProvider.defaultModel)
                val usage = parseUsage(json, model) ?: TokenUsage(0, 0, model, currentProvider.id)

                AgentResponse(
                    id = request.id,
                    text = text,
                    usage = usage
                )
            }
        } catch (e: IOException) {
            connected = false
            AgentResponse(
                id = request.id,
                text = null,
                usage = TokenUsage(0, 0, currentProvider.defaultModel, currentProvider.id)
            )
        } finally {
            activeCalls.remove(call)
        }
    }

    override suspend fun healthCheck(): CloudHealthStatus {
        if (apiKey.isBlank()) {
            return CloudHealthStatus(
                connected = false,
                provider = currentProvider.id,
                error = "Missing API key"
            )
        }

        val start = System.currentTimeMillis()
        val request = Request.Builder()
            .url("${currentProvider.baseUrl.trimEnd('/')}/v1/models")
            .addHeader("Authorization", "Bearer $apiKey")
            .get()
            .build()

        return try {
            client.newCall(request).execute().use { response ->
                connected = response.isSuccessful
                CloudHealthStatus(
                    connected = response.isSuccessful,
                    provider = currentProvider.id,
                    latencyMs = System.currentTimeMillis() - start,
                    error = if (response.isSuccessful) null else "HTTP ${response.code}"
                )
            }
        } catch (e: IOException) {
            connected = false
            CloudHealthStatus(
                connected = false,
                provider = currentProvider.id,
                latencyMs = System.currentTimeMillis() - start,
                error = e.message ?: "Network error"
            )
        }
    }

    override fun isConnected(): Boolean = connected

    override fun cancelAll() {
        val calls = activeCalls.toList()
        for (call in calls) {
            call.cancel()
        }
        activeCalls.clear()
    }

    override fun getProvider(): CloudProvider = currentProvider

    override fun setProvider(provider: CloudProvider, apiKey: String) {
        currentProvider = provider
        this.apiKey = apiKey
    }

    private fun buildHttpRequest(
        request: AgentRequest,
        context: ConversationContext,
        stream: Boolean
    ): Request {
        val url = "${currentProvider.baseUrl.trimEnd('/')}/v1/chat/completions"
        val payload = buildChatCompletionPayload(request, context, stream)
        val mediaType = "application/json; charset=utf-8".toMediaType()
        val body = payload.toString().toRequestBody(mediaType)

        return Request.Builder()
            .url(url)
            .addHeader("Authorization", "Bearer $apiKey")
            .addHeader("Content-Type", "application/json")
            .post(body)
            .build()
    }

    private fun buildChatCompletionPayload(
        request: AgentRequest,
        context: ConversationContext,
        stream: Boolean
    ): JSONObject {
        val payload = JSONObject()
        payload.put("model", currentProvider.defaultModel)
        payload.put("stream", stream)
        if (stream) {
            payload.put("stream_options", JSONObject().put("include_usage", true))
        }

        payload.put("messages", buildMessages(request, context))
        return payload
    }

    private fun buildMessages(
        request: AgentRequest,
        context: ConversationContext
    ): JSONArray {
        val messages = JSONArray()
        if (context.systemPrompt.isNotBlank()) {
            messages.put(
                JSONObject()
                    .put("role", "system")
                    .put("content", context.systemPrompt)
            )
        }

        for (message in context.messages) {
            messages.put(toJsonMessage(message))
        }

        val alreadyIncluded = context.messages.lastOrNull()?.let { last ->
            last.role == MessageRole.USER && last.content == request.content
        } ?: false

        if (!alreadyIncluded) {
            messages.put(
                JSONObject()
                    .put("role", "user")
                    .put("content", request.content)
            )
        }

        return messages
    }

    private fun toJsonMessage(message: Message): JSONObject {
        return JSONObject()
            .put("role", mapRole(message.role))
            .put("content", message.content)
    }

    private fun mapRole(role: MessageRole): String = when (role) {
        MessageRole.SYSTEM -> "system"
        MessageRole.USER -> "user"
        MessageRole.ASSISTANT -> "assistant"
        MessageRole.TOOL -> "tool"
    }

    private fun parseStreamDeltas(eventJson: JSONObject): List<AgentResponseChunk> {
        val chunks = mutableListOf<AgentResponseChunk>()
        val choices = eventJson.optJSONArray("choices") ?: return chunks

        for (i in 0 until choices.length()) {
            val choice = choices.optJSONObject(i) ?: continue
            val delta = choice.optJSONObject("delta") ?: continue
            val content = delta.optString("content", "")
            if (content.isNotEmpty()) {
                chunks.add(AgentResponseChunk.Text(content))
            }
        }

        return chunks
    }

    private fun extractMessageText(json: JSONObject): String? {
        val choices = json.optJSONArray("choices") ?: return null
        if (choices.length() == 0) {
            return null
        }
        val firstChoice = choices.optJSONObject(0) ?: return null
        val message = firstChoice.optJSONObject("message") ?: return null
        return message.optString("content", null)
    }

    private fun parseUsage(json: JSONObject, model: String): TokenUsage? {
        val usage = json.optJSONObject("usage") ?: return null
        return TokenUsage(
            inputTokens = usage.optInt("prompt_tokens", 0),
            outputTokens = usage.optInt("completion_tokens", 0),
            model = model,
            provider = currentProvider.id,
            estimatedCostUsd = usage.optDouble("estimated_cost", Double.NaN)
                .takeIf { !it.isNaN() }
        )
    }

    private fun errorChunk(
        code: ErrorCode,
        message: String,
        retryable: Boolean
    ): AgentResponseChunk.Error {
        return AgentResponseChunk.Error(
            AgentError(
                code = code,
                message = message,
                retryable = retryable
            )
        )
    }
}
