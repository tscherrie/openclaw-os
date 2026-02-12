package os.openclaw.agentcanvas.ui.cards

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.*
import androidx.compose.animation.fadeIn
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CloudOff
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.WifiOff
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import os.openclaw.agentcanvas.data.*
import os.openclaw.agentcanvas.ui.theme.OpenClawTheme

/**
 * ConversationCard — The primary interaction card.
 *
 * Shows the dialogue between human and agent. Messages stream in,
 * actions appear when needed, and the whole thing collapses gracefully
 * when the conversation moves on. Like all good conversations should.
 *
 * Unlike your group chats, this one is actually productive.
 */
@Composable
fun ConversationCard(
    state: CardState.Conversation,
    onActionClick: (String) -> Unit = {},
    onRetry: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    val shape = RoundedCornerShape(OpenClawTheme.radii.lg)

    Surface(
        color = OpenClawTheme.colors.surfaceRaised,
        shape = shape,
        modifier = modifier
            .fillMaxWidth()
            .border(
                width = 1.dp,
                color = OpenClawTheme.colors.borderSubtle,
                shape = shape
            )
    ) {
        Column(
            modifier = Modifier.padding(OpenClawTheme.spacing.base)
        ) {
            // Card header
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = "🤖 Agent",
                    style = OpenClawTheme.typography.titleSmall,
                    color = OpenClawTheme.colors.textSecondary,
                )
                Text(
                    text = "jetzt",
                    style = OpenClawTheme.typography.bodySmall,
                    color = OpenClawTheme.colors.textTertiary,
                )
            }

            Spacer(modifier = Modifier.height(OpenClawTheme.spacing.md))

            // Messages
            state.messages.forEach { message ->
                if (message.error != null) {
                    ErrorBubble(message.error, onRetry = onRetry)
                } else {
                    MessageBubble(message)
                }
                Spacer(modifier = Modifier.height(OpenClawTheme.spacing.sm))
            }

            // Streaming indicator
            if (state.isStreaming) {
                TypingIndicator()
                Spacer(modifier = Modifier.height(OpenClawTheme.spacing.sm))
            }

            // Action buttons (when agent needs user input)
            if (state.actions.isNotEmpty()) {
                Spacer(modifier = Modifier.height(OpenClawTheme.spacing.sm))
                Row(
                    horizontalArrangement = Arrangement.spacedBy(OpenClawTheme.spacing.sm),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    state.actions.forEach { action ->
                        OutlinedButton(
                            onClick = { onActionClick(action) },
                            shape = RoundedCornerShape(OpenClawTheme.radii.md),
                            colors = ButtonDefaults.outlinedButtonColors(
                                contentColor = OpenClawTheme.colors.accentPrimary,
                            ),
                            border = ButtonDefaults.outlinedButtonBorder(enabled = true),
                            modifier = Modifier.weight(1f),
                        ) {
                            Text(
                                text = action,
                                style = OpenClawTheme.typography.labelLarge,
                                maxLines = 1,
                            )
                        }
                    }
                }
            }
        }
    }
}

/**
 * A single message bubble.
 * Agent messages are left-aligned, user messages right-aligned with accent color.
 * Because visual hierarchy isn't optional, it's oxygen.
 */
@Composable
private fun MessageBubble(message: Message) {
    val isAgent = message.sender == Sender.Agent

    Column(
        modifier = Modifier.fillMaxWidth(),
        horizontalAlignment = if (isAgent) Alignment.Start else Alignment.End,
    ) {
        Box(
            modifier = Modifier
                .widthIn(max = 300.dp)
                .background(
                    color = if (isAgent)
                        OpenClawTheme.colors.surfaceElevated
                    else
                        OpenClawTheme.colors.accentSubtle,
                    shape = RoundedCornerShape(
                        topStart = OpenClawTheme.radii.md,
                        topEnd = OpenClawTheme.radii.md,
                        bottomStart = if (isAgent) 4.dp else OpenClawTheme.radii.md,
                        bottomEnd = if (isAgent) OpenClawTheme.radii.md else 4.dp,
                    )
                )
                .padding(
                    horizontal = OpenClawTheme.spacing.md,
                    vertical = OpenClawTheme.spacing.sm,
                )
        ) {
            Text(
                text = message.text,
                style = OpenClawTheme.typography.bodyLarge,
                color = if (isAgent)
                    OpenClawTheme.colors.textPrimary
                else
                    OpenClawTheme.colors.accentPrimary,
            )
        }
    }
}

/**
 * Error bubble — red-tinted, with icon and optional retry button.
 * Errors deserve dignity too.
 */
@Composable
private fun ErrorBubble(
    error: MessageError,
    onRetry: () -> Unit = {},
) {
    val errorColor = Color(0xFFFF4444)
    val errorBg = Color(0x33FF4444)

    Column(
        modifier = Modifier.fillMaxWidth(),
        horizontalAlignment = Alignment.Start,
    ) {
        Box(
            modifier = Modifier
                .widthIn(max = 300.dp)
                .background(
                    color = errorBg,
                    shape = RoundedCornerShape(OpenClawTheme.radii.md),
                )
                .padding(
                    horizontal = OpenClawTheme.spacing.md,
                    vertical = OpenClawTheme.spacing.sm,
                )
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(OpenClawTheme.spacing.sm),
            ) {
                Icon(
                    imageVector = when (error.kind) {
                        MessageErrorKind.Offline -> Icons.Default.WifiOff
                        else -> Icons.Default.CloudOff
                    },
                    contentDescription = null,
                    tint = errorColor,
                    modifier = Modifier.size(16.dp),
                )
                Text(
                    text = error.message,
                    style = OpenClawTheme.typography.bodySmall,
                    color = errorColor,
                    modifier = Modifier.weight(1f),
                )
                if (error.retryable) {
                    IconButton(
                        onClick = onRetry,
                        modifier = Modifier.size(24.dp),
                    ) {
                        Icon(
                            imageVector = Icons.Default.Refresh,
                            contentDescription = "Retry",
                            tint = errorColor,
                            modifier = Modifier.size(16.dp),
                        )
                    }
                }
            }
        }
    }
}

/**
 * Three-dot typing indicator with pulsing animation.
 * The universal "I'm thinking" signal. Works for agents and humans alike.
 */
@Composable
private fun TypingIndicator() {
    val infiniteTransition = rememberInfiniteTransition(label = "typing")

    Row(
        horizontalArrangement = Arrangement.spacedBy(4.dp),
        modifier = Modifier.padding(horizontal = OpenClawTheme.spacing.md),
    ) {
        repeat(3) { index ->
            val alpha by infiniteTransition.animateFloat(
                initialValue = 0.3f,
                targetValue = 1f,
                animationSpec = infiniteRepeatable(
                    animation = tween(600, easing = EaseInOut),
                    repeatMode = RepeatMode.Reverse,
                    initialStartOffset = StartOffset(index * 200),
                ),
                label = "dot_$index",
            )

            Box(
                modifier = Modifier
                    .size(8.dp)
                    .alpha(alpha)
                    .background(
                        color = OpenClawTheme.colors.accentPrimary,
                        shape = CircleShape,
                    )
            )
        }
    }
}

@Preview(showBackground = true, backgroundColor = 0xFF0A0A0F)
@Composable
fun ConversationCardPreview() {
    OpenClawTheme(darkTheme = true) {
        ConversationCard(
            state = CardState.Conversation(
                id = "preview",
                messages = listOf(
                    Message(Sender.Agent, "Guten Morgen, Jeremias. Donika fragt ob du Brötchen willst."),
                    Message(Sender.User, "Ja, mit Käse bitte."),
                    Message(Sender.Agent, "Geschickt. Heizung hoch?"),
                ),
                actions = listOf("Ja, auf 22°", "Nein"),
            ),
            modifier = Modifier.padding(16.dp)
        )
    }
}

@Preview(showBackground = true, backgroundColor = 0xFF0A0A0F)
@Composable
fun ConversationCardErrorPreview() {
    OpenClawTheme(darkTheme = true) {
        ConversationCard(
            state = CardState.Conversation(
                id = "error-preview",
                messages = listOf(
                    Message(Sender.User, "Was ist das Wetter?"),
                    Message(
                        sender = Sender.Agent,
                        text = "",
                        error = MessageError(
                            kind = MessageErrorKind.CloudUnavailable,
                            message = "Cloud nicht erreichbar",
                            retryable = true,
                        ),
                    ),
                ),
            ),
            modifier = Modifier.padding(16.dp)
        )
    }
}

@Preview(showBackground = true, backgroundColor = 0xFF0A0A0F)
@Composable
fun ConversationCardStreamingPreview() {
    OpenClawTheme(darkTheme = true) {
        ConversationCard(
            state = CardState.Conversation(
                id = "streaming-preview",
                messages = listOf(
                    Message(Sender.User, "Erzähl mir was"),
                    Message(Sender.Agent, "Ich denke gerade nach...", isStreaming = true),
                ),
                isStreaming = true,
            ),
            modifier = Modifier.padding(16.dp)
        )
    }
}
