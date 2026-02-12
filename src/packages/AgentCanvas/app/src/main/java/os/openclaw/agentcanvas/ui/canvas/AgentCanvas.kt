package os.openclaw.agentcanvas.ui.canvas

import androidx.compose.animation.*
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import os.openclaw.agentcanvas.data.*
import os.openclaw.agentcanvas.ui.cards.ConversationCard
import os.openclaw.agentcanvas.ui.cards.StatusCard
import os.openclaw.agentcanvas.ui.theme.OpenClawTheme

/**
 * AgentCanvas — The root composable that replaces the Android home screen.
 *
 * This is it. The face of the future. A LazyColumn of cards driven by an
 * AI agent, with a voice input bar nailed to the bottom. No app icons.
 * No widgets. No regrets.
 *
 * Layout:
 * ┌──────────────────┐
 * │  Context Header   │  ← Time, weather, next event
 * ├──────────────────┤
 * │                   │
 * │   Card Stream     │  ← Agent-driven cards
 * │                   │
 * ├──────────────────┤
 * │  Agent Input Bar  │  ← Voice + Text + State indicator
 * └──────────────────┘
 */
@Composable
fun AgentCanvas(
    state: CanvasState,
    onUserMessage: (String) -> Unit = {},
    modifier: Modifier = Modifier
) {
    Box(
        modifier = modifier
            .fillMaxSize()
            .background(OpenClawTheme.colors.surfaceBase)
    ) {
        Column(modifier = Modifier.fillMaxSize()) {
            // --- Context Header ---
            ContextHeader(
                time = state.contextHeader.time,
                weather = state.contextHeader.weather,
                nextEvent = state.contextHeader.nextEvent,
            )

            // --- Card Stream ---
            LazyColumn(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth(),
                contentPadding = PaddingValues(
                    horizontal = OpenClawTheme.spacing.base,
                    vertical = OpenClawTheme.spacing.sm
                ),
                verticalArrangement = Arrangement.spacedBy(OpenClawTheme.spacing.sm)
            ) {
                items(
                    items = state.cards,
                    key = { it.id }
                ) { card ->
                    AnimatedVisibility(
                        visible = true,
                        enter = fadeIn() + slideInVertically { it / 4 },
                    ) {
                        when (card) {
                            is CardState.Conversation -> ConversationCard(card)
                            is CardState.Status -> StatusCard(card)
                            // TODO: MediaCard, ControlCard, SuggestionCard, etc.
                            // They'll get their turn. Rome wasn't built in a sprint.
                        }
                    }
                }

                // Empty state — the void stares back
                if (state.cards.isEmpty()) {
                    item {
                        EmptyCanvasMessage()
                    }
                }
            }

            // --- Agent Input Bar ---
            AgentInputBar(
                agentState = state.agentState,
                onSendMessage = onUserMessage,
            )
        }
    }
}

/**
 * Context Header — the glanceable strip at the top.
 * Time, weather, next event. That's it. That's the tweet.
 */
@Composable
private fun ContextHeader(
    time: String,
    weather: String,
    nextEvent: String?,
) {
    Surface(
        color = OpenClawTheme.colors.surfaceBase,
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(
            modifier = Modifier.padding(
                horizontal = OpenClawTheme.spacing.base,
                vertical = OpenClawTheme.spacing.md
            )
        ) {
            Text(
                text = time,
                style = OpenClawTheme.typography.displaySmall,
                color = OpenClawTheme.colors.textPrimary,
            )
            Row(
                horizontalArrangement = Arrangement.spacedBy(OpenClawTheme.spacing.sm),
                modifier = Modifier.padding(top = OpenClawTheme.spacing.xs)
            ) {
                Text(
                    text = weather,
                    style = OpenClawTheme.typography.bodyMedium,
                    color = OpenClawTheme.colors.textSecondary,
                )
                if (nextEvent != null) {
                    Text(
                        text = "·",
                        style = OpenClawTheme.typography.bodyMedium,
                        color = OpenClawTheme.colors.textTertiary,
                    )
                    Text(
                        text = nextEvent,
                        style = OpenClawTheme.typography.bodyMedium,
                        color = OpenClawTheme.colors.textSecondary,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }
        }
    }
}

/**
 * Agent Input Bar — the command center.
 * A state indicator, text field, mic button, camera button.
 * Fixed at the bottom. Always. Because if you can't talk to the agent,
 * you might as well use a calculator.
 */
@Composable
private fun AgentInputBar(
    agentState: AgentState,
    onSendMessage: (String) -> Unit,
) {
    val stateColor = when (agentState) {
        AgentState.Idle -> OpenClawTheme.colors.agentIdle
        is AgentState.Listening -> OpenClawTheme.colors.agentListening
        is AgentState.Thinking -> OpenClawTheme.colors.agentThinking
        is AgentState.Speaking -> OpenClawTheme.colors.agentSpeaking
        is AgentState.Error -> OpenClawTheme.colors.error
        AgentState.Offline -> OpenClawTheme.colors.textDisabled
    }

    Surface(
        color = OpenClawTheme.colors.surfaceRaised,
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            modifier = Modifier.padding(OpenClawTheme.spacing.md)
        ) {
            // Agent state indicator dot
            Box(
                modifier = Modifier
                    .size(12.dp)
                    .clip(CircleShape)
                    .background(stateColor)
            )

            Spacer(modifier = Modifier.height(OpenClawTheme.spacing.sm))

            // Input row
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(OpenClawTheme.spacing.sm),
                modifier = Modifier.fillMaxWidth()
            ) {
                // Text input
                var text by remember { mutableStateOf("") }
                OutlinedTextField(
                    value = text,
                    onValueChange = { text = it },
                    placeholder = {
                        Text(
                            "Type or speak...",
                            color = OpenClawTheme.colors.textTertiary,
                            style = OpenClawTheme.typography.bodyMedium
                        )
                    },
                    modifier = Modifier.weight(1f),
                    shape = RoundedCornerShape(OpenClawTheme.radii.md),
                    singleLine = true,
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = OpenClawTheme.colors.accentPrimary,
                        unfocusedBorderColor = OpenClawTheme.colors.borderSubtle,
                        cursorColor = OpenClawTheme.colors.accentPrimary,
                        focusedTextColor = OpenClawTheme.colors.textPrimary,
                        unfocusedTextColor = OpenClawTheme.colors.textPrimary,
                    ),
                )

                // Mic button
                IconButton(onClick = { /* TODO: Voice input */ }) {
                    Icon(
                        Icons.Default.Mic,
                        contentDescription = "Voice input",
                        tint = OpenClawTheme.colors.accentPrimary,
                    )
                }

                // Camera button
                IconButton(onClick = { /* TODO: Camera */ }) {
                    Icon(
                        Icons.Default.CameraAlt,
                        contentDescription = "Camera",
                        tint = OpenClawTheme.colors.textSecondary,
                    )
                }
            }
        }
    }
}

/**
 * The empty canvas message. Shown when the agent has nothing to show.
 * Which, honestly, should be never. But we plan for entropy.
 */
@Composable
private fun EmptyCanvasMessage() {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = OpenClawTheme.spacing.xxl),
        contentAlignment = Alignment.Center
    ) {
        Text(
            text = "Alles erledigt. Die Stille ist verdient.",
            style = OpenClawTheme.typography.bodyMedium,
            color = OpenClawTheme.colors.textTertiary,
        )
    }
}

// ============================================================================
// Preview — because seeing is believing, and believing is committing
// ============================================================================

@Preview(
    showBackground = true,
    backgroundColor = 0xFF0A0A0F,
    widthDp = 390,
    heightDp = 844,
    name = "Agent Canvas — Morning"
)
@Composable
fun AgentCanvasPreview() {
    OpenClawTheme(darkTheme = true) {
        AgentCanvas(
            state = CanvasState(
                contextHeader = ContextHeaderState(
                    time = "6:45",
                    weather = "4°C ☁️",
                    nextEvent = "10:00 Team Standup"
                ),
                cards = listOf(
                    CardState.Conversation(
                        id = "conv-1",
                        messages = listOf(
                            Message(
                                sender = Sender.Agent,
                                text = "Guten Morgen, Jeremias. Du hast um 10 Standup und um 14 Uhr Zahnarzt. Donika fragt ob du Brötchen willst. Soll ich antworten?"
                            )
                        ),
                        actions = listOf("Ja, mit Käse", "Nein danke")
                    ),
                    CardState.Status(
                        id = "status-1",
                        title = "Heute",
                        subtitle = "Do 12. Feb",
                        items = listOf(
                            StatusItem(icon = "📅", label = "10:00 Team Standup"),
                            StatusItem(icon = "📅", label = "14:00 Zahnarzt"),
                        ),
                        quickStats = "🚗 92%  ·  🏠 19°C"
                    ),
                ),
                agentState = AgentState.Idle,
            )
        )
    }
}
