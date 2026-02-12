/**
 * IntentRouter — The Traffic Controller
 *
 * Intercepts Android intents before they reach their default handler.
 * The agent gets first dibs on every intent — like a bouncer who
 * checks the guest list before letting anyone into the party.
 *
 * When you tap a phone number, instead of immediately opening the
 * dialer, the agent can say "That's the pizza place. Want me to
 * just reorder the usual?" THAT'S the OpenClaw experience.
 *
 * @author Forge (Backend Lead, Agent Lab)
 * @since 0.1.0
 */
package com.openclaw.agent.intent

import android.content.Intent
import android.content.IntentFilter
import com.openclaw.agent.model.*

/**
 * Interface for Android intent interception and routing.
 */
interface IntentRouter {

    companion object {
        fun create(): IntentRouter = IntentRouterImpl()
    }

    /**
     * Evaluate whether the agent should intercept this intent.
     *
     * @param intent The Android intent about to be dispatched
     * @param context Current agent context (for smart decisions)
     * @return Decision: pass through, intercept, or modify
     */
    fun evaluate(intent: Intent, context: ConversationContext): IntentDecision

    /**
     * Modify an intent before passing it through.
     * Used for MODIFY_AND_PASS decisions.
     */
    fun modifyIntent(intent: Intent, modifications: Map<String, Any?>)

    /**
     * Register an intent filter for interception.
     * Higher priority filters are checked first.
     *
     * @param filter The intent filter to match
     * @param priority Higher = checked first
     * @param handler The handler function
     */
    fun addInterceptFilter(
        filter: IntentFilter,
        priority: Int = 0,
        handler: IntentHandler
    )

    /**
     * Remove an intercept filter.
     */
    fun removeInterceptFilter(filter: IntentFilter)

    /**
     * Get all registered intercept filters.
     * Mostly for debugging: "Why did my phone not open Chrome?"
     */
    fun getInterceptFilters(): List<InterceptFilterInfo>
}

/**
 * Handler for intercepted intents.
 */
fun interface IntentHandler {
    suspend fun handle(intent: Intent): IntentHandleResult
}

data class IntentHandleResult(
    val handled: Boolean,
    val agentMessage: String? = null,  // Message to show user
    val cardUpdate: CardDefinition? = null  // Card to display
)

data class InterceptFilterInfo(
    val filter: IntentFilter,
    val priority: Int,
    val description: String
)

// ==========================================
// Implementation (Stub)
// ==========================================

internal class IntentRouterImpl : IntentRouter {

    private data class RegisteredFilter(
        val filter: IntentFilter,
        val priority: Int,
        val handler: IntentHandler
    )

    private val filters = mutableListOf<RegisteredFilter>()

    override fun evaluate(intent: Intent, context: ConversationContext): IntentDecision {
        // TODO: Check registered filters and use agent intelligence
        // to decide if we should handle this intent

        // For now: examples of what we'd intercept
        return when (intent.action) {
            Intent.ACTION_DIAL -> {
                // Agent could offer: "That's Mama's number. Call her?"
                IntentDecision.PassThrough  // Default: don't intercept yet
            }
            Intent.ACTION_VIEW -> {
                // Agent could summarize the webpage
                IntentDecision.PassThrough
            }
            Intent.ACTION_SEND -> {
                // Agent could offer to compose the message
                IntentDecision.PassThrough
            }
            else -> IntentDecision.PassThrough
        }
    }

    override fun modifyIntent(intent: Intent, modifications: Map<String, Any?>) {
        // TODO: Apply modifications to intent extras
        modifications.forEach { (key, value) ->
            when (value) {
                is String -> intent.putExtra(key, value)
                is Int -> intent.putExtra(key, value)
                is Boolean -> intent.putExtra(key, value)
                // etc.
            }
        }
    }

    override fun addInterceptFilter(
        filter: IntentFilter,
        priority: Int,
        handler: IntentHandler
    ) {
        filters.add(RegisteredFilter(filter, priority, handler))
        // Keep sorted by priority (descending)
        filters.sortByDescending { it.priority }
    }

    override fun removeInterceptFilter(filter: IntentFilter) {
        filters.removeAll { it.filter == filter }
    }

    override fun getInterceptFilters(): List<InterceptFilterInfo> {
        return filters.map { registered ->
            InterceptFilterInfo(
                filter = registered.filter,
                priority = registered.priority,
                description = "Filter with ${registered.filter.countActions()} actions"
            )
        }
    }
}
