/**
 * AccessibilityBridge — The Puppet Master
 *
 * Controls third-party apps via Android's Accessibility framework.
 * Can read screens, click buttons, type text — basically plays
 * every app like a very fast, very precise human.
 *
 * Ethical note: We use this power for good. The user asked us to
 * order pizza, not to read their ex's messages. Boundaries matter.
 *
 * @author Forge (Backend Lead, Agent Lab)
 * @since 0.1.0
 */
package com.openclaw.agent.bridge

import android.graphics.Bitmap

/**
 * Interface for controlling apps via Accessibility services.
 */
interface AccessibilityBridge {

    companion object {
        fun create(): AccessibilityBridge = AccessibilityBridgeImpl()
    }

    /**
     * Get the current screen content as structured data.
     * Returns all visible UI elements, text, and their hierarchy.
     */
    fun getScreenContent(): ScreenContent

    /**
     * Perform a UI action on the current screen.
     *
     * @param action The action to perform (click, type, scroll, etc.)
     * @return Result of the action
     */
    suspend fun performAction(action: UiAction): UiActionResult

    /**
     * Capture a screenshot of the current screen.
     * Used for visual analysis when accessibility tree isn't enough.
     * (Some apps are... creative... with their UI implementations.)
     */
    suspend fun captureScreen(): Bitmap?

    /**
     * Wait for a specific UI state to appear.
     * Like waiting for your food delivery, but with a timeout.
     *
     * @param predicate Condition to wait for
     * @param timeoutMs Maximum time to wait
     * @return true if condition was met, false if timed out
     */
    suspend fun waitForState(
        predicate: (ScreenContent) -> Boolean,
        timeoutMs: Long = 5000
    ): Boolean

    /**
     * Get the package name of the currently foreground app.
     */
    fun getForegroundApp(): String

    /**
     * Check if accessibility service is enabled and functional.
     */
    fun isServiceEnabled(): Boolean
}

/**
 * Structured representation of screen content.
 */
data class ScreenContent(
    val packageName: String,
    val activityName: String,
    val nodes: List<UiNode>,
    val textContent: List<String>  // All visible text, flattened
)

/**
 * A node in the UI accessibility tree.
 */
data class UiNode(
    val id: String?,
    val className: String,
    val text: String?,
    val contentDescription: String?,
    val isClickable: Boolean,
    val isEditable: Boolean,
    val isScrollable: Boolean,
    val bounds: UiRect,
    val children: List<UiNode>
)

data class UiRect(
    val left: Int,
    val top: Int,
    val right: Int,
    val bottom: Int
)

/**
 * An action to perform on the UI.
 */
sealed class UiAction {
    /** Click on a node matching the selector */
    data class Click(val selector: UiSelector) : UiAction()

    /** Long click on a node */
    data class LongClick(val selector: UiSelector) : UiAction()

    /** Type text into an editable field */
    data class TypeText(val selector: UiSelector, val text: String) : UiAction()

    /** Scroll in a direction */
    data class Scroll(val direction: ScrollDirection) : UiAction()

    /** Press back button */
    object Back : UiAction()

    /** Press home button */
    object Home : UiAction()

    /** Open recent apps */
    object Recents : UiAction()
}

enum class ScrollDirection { UP, DOWN, LEFT, RIGHT }

/**
 * How to find a UI element. Multiple strategies because
 * Android UI is a beautiful, chaotic mess.
 */
data class UiSelector(
    val text: String? = null,
    val contentDescription: String? = null,
    val resourceId: String? = null,
    val className: String? = null,
    val index: Int? = null
)

data class UiActionResult(
    val success: Boolean,
    val error: String? = null,
    val resultingScreen: ScreenContent? = null
)

// ==========================================
// Stub Implementation
// ==========================================

internal class AccessibilityBridgeImpl : AccessibilityBridge {

    override fun getScreenContent(): ScreenContent {
        // TODO: Implement via AccessibilityService
        return ScreenContent(
            packageName = "com.android.launcher",
            activityName = "LauncherActivity",
            nodes = emptyList(),
            textContent = listOf("🚧 Accessibility bridge not yet connected")
        )
    }

    override suspend fun performAction(action: UiAction): UiActionResult {
        // TODO: Implement via AccessibilityService node actions
        return UiActionResult(
            success = false,
            error = "Accessibility bridge not yet implemented"
        )
    }

    override suspend fun captureScreen(): Bitmap? {
        // TODO: Implement via MediaProjection or system-level screenshot
        return null
    }

    override suspend fun waitForState(
        predicate: (ScreenContent) -> Boolean,
        timeoutMs: Long
    ): Boolean {
        // TODO: Poll getScreenContent() until predicate matches or timeout
        return false
    }

    override fun getForegroundApp(): String {
        // TODO: Query ActivityManager for top activity
        return "unknown"
    }

    override fun isServiceEnabled(): Boolean {
        // TODO: Check if our AccessibilityService is registered
        return false
    }
}
