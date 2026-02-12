/**
 * CloudBridgeBackend — Production implementation of [AgentBackend].
 *
 * Talks to the OpenClaw Gateway (or any OpenAI-compatible endpoint)
 * via SSE streaming. The gateway handles provider routing, so we just
 * speak one protocol: OpenAI chat completions.
 *
 * @author Prism (Frontend Lead, Agent Lab)
 * @since 0.2.0 (Sprint 3)
 */
package os.openclaw.agentcanvas.backend

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.withContext
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.IOException
import java.io.InputStreamReader
import java.util.concurrent.TimeUnit

/**
 * Production backend hitting an OpenAI-compatible `/v1/chat/completions` endpoint.
 *
 * @param baseUrl Gateway base URL (e.g., "https://gw.openclaw.os")
 * @param apiKey API key for authentication
 * @param defaultModel Default model to use when none specified
 */
class CloudBridgeBackend(
    private val baseUrl: String,
    private val apiKey: String,
    private val defaultModel: String = "claude-sonnet-4-20250514",
) : AgentBackend {

    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(120, TimeUnit.SECONDS) // SSE streams can be long
        .writeTimeout(10, TimeUnit.SECONDS)
        .build()

    private val jsonMediaType = "application/json; charset=utf-8".toMediaType()

    override fun streamChat(
        messages: List<ChatMessage>,
        model: String?,
    ): Flow<StreamEvent> = callbackFlow {
        val body = buildRequestBody(messages, model, stream = true)
        val request = buildRequest(body)

        val call = client.newCall(request)
        call.enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                val error = when {
                    e.message?.contains("Unable to resolve host") == true ||
                    e.message?.contains("Network is unreachable") == true ->
                        BackendError(ErrorKind.Offline, "Network unavailable", retryable = true)
                    e.message?.contains("timeout") == true ->
                        BackendError(ErrorKind.CloudUnavailable, "Request timed out", retryable = true)
                    else ->
                        BackendError(ErrorKind.CloudUnavailable, e.message ?: "Connection failed", retryable = true)
                }
                trySend(StreamEvent.Error(error))
                close()
            }

            override fun onResponse(call: Call, response: Response) {
                if (!response.isSuccessful) {
                    val error = parseHttpError(response)
                    trySend(StreamEvent.Error(error))
                    close()
                    return
                }

                try {
                    val reader = BufferedReader(InputStreamReader(response.body!!.byteStream()))
                    var line: String?
                    while (reader.readLine().also { line = it } != null) {
                        val data = line ?: continue
                        if (!data.startsWith("data: ")) continue
                        val payload = data.removePrefix("data: ").trim()
                        if (payload == "[DONE]") {
                            trySend(StreamEvent.Done())
                            break
                        }
                        try {
                            val json = JSONObject(payload)
                            val choices = json.optJSONArray("choices") ?: continue
                            val delta = choices.getJSONObject(0)
                                .optJSONObject("delta") ?: continue
                            val content = delta.optString("content", "")
                            if (content.isNotEmpty()) {
                                trySend(StreamEvent.Delta(content))
                            }
                        } catch (_: Exception) {
                            // Skip malformed SSE lines
                        }
                    }
                    reader.close()
                } catch (e: Exception) {
                    trySend(StreamEvent.Error(
                        BackendError(ErrorKind.Unknown, "Stream read error: ${e.message}")
                    ))
                }
                close()
            }
        })

        awaitClose { call.cancel() }
    }

    override suspend fun sendChat(
        messages: List<ChatMessage>,
        model: String?,
    ): ChatResult = withContext(Dispatchers.IO) {
        val body = buildRequestBody(messages, model, stream = false)
        val request = buildRequest(body)

        try {
            val response = client.newCall(request).execute()
            if (!response.isSuccessful) {
                val error = parseHttpError(response)
                throw BackendException(error)
            }

            val json = JSONObject(response.body!!.string())
            val content = json.getJSONArray("choices")
                .getJSONObject(0)
                .getJSONObject("message")
                .getString("content")

            val usage = json.optJSONObject("usage")?.let {
                TokenUsage(
                    promptTokens = it.optInt("prompt_tokens", 0),
                    completionTokens = it.optInt("completion_tokens", 0),
                )
            }

            ChatResult(content = content, usage = usage)
        } catch (e: BackendException) {
            throw e
        } catch (e: IOException) {
            throw BackendException(
                BackendError(ErrorKind.CloudUnavailable, e.message ?: "Connection failed", retryable = true)
            )
        }
    }

    override suspend fun healthCheck(): HealthStatus = withContext(Dispatchers.IO) {
        val start = System.currentTimeMillis()
        try {
            // Minimal request to check connectivity
            val request = Request.Builder()
                .url("$baseUrl/v1/models")
                .addHeader("Authorization", "Bearer $apiKey")
                .get()
                .build()

            val response = client.newCall(request).execute()
            val latency = System.currentTimeMillis() - start

            HealthStatus(
                reachable = response.isSuccessful,
                latencyMs = latency,
                error = if (!response.isSuccessful) "HTTP ${response.code}" else null,
            )
        } catch (e: Exception) {
            HealthStatus(
                reachable = false,
                latencyMs = System.currentTimeMillis() - start,
                error = e.message,
            )
        }
    }

    // ==========================================
    // Helpers
    // ==========================================

    private fun buildRequestBody(
        messages: List<ChatMessage>,
        model: String?,
        stream: Boolean,
    ): RequestBody {
        val json = JSONObject().apply {
            put("model", model ?: defaultModel)
            put("stream", stream)
            put("messages", JSONArray().apply {
                messages.forEach { msg ->
                    put(JSONObject().apply {
                        put("role", msg.role.name.lowercase())
                        put("content", msg.content)
                    })
                }
            })
        }
        return json.toString().toRequestBody(jsonMediaType)
    }

    private fun buildRequest(body: RequestBody): Request =
        Request.Builder()
            .url("$baseUrl/v1/chat/completions")
            .addHeader("Authorization", "Bearer $apiKey")
            .addHeader("Accept", "text/event-stream")
            .post(body)
            .build()

    private fun parseHttpError(response: Response): BackendError {
        val status = response.code
        val body = try { response.body?.string() } catch (_: Exception) { null }

        return when (status) {
            401, 403 -> BackendError(
                ErrorKind.AuthFailed,
                "Authentication failed (HTTP $status)",
                retryable = false,
                httpStatus = status,
            )
            429 -> BackendError(
                ErrorKind.RateLimited,
                "Rate limited — slow down",
                retryable = true,
                httpStatus = status,
            )
            in 500..599 -> BackendError(
                ErrorKind.CloudUnavailable,
                "Server error (HTTP $status)",
                retryable = true,
                httpStatus = status,
            )
            else -> BackendError(
                ErrorKind.Unknown,
                body ?: "HTTP $status",
                retryable = false,
                httpStatus = status,
            )
        }
    }
}

/**
 * Exception wrapper for [BackendError]. Used in non-streaming calls.
 */
class BackendException(val error: BackendError) : Exception(error.message)
