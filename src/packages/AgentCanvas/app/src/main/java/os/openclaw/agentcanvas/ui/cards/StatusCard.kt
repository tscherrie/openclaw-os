package os.openclaw.agentcanvas.ui.cards

import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import os.openclaw.agentcanvas.data.CardState
import os.openclaw.agentcanvas.data.StatusItem
import os.openclaw.agentcanvas.ui.theme.OpenClawTheme

/**
 * StatusCard — Passive contextual information at a glance.
 *
 * Calendar events, device status, weather. The stuff you check
 * your phone for 47 times a day but pretend you don't.
 * Now it's just... there. Staring at you. Helpfully.
 */
@Composable
fun StatusCard(
    state: CardState.Status,
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
            // Header
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = state.title,
                    style = OpenClawTheme.typography.titleMedium,
                    color = OpenClawTheme.colors.textPrimary,
                )
                if (state.subtitle.isNotEmpty()) {
                    Text(
                        text = state.subtitle,
                        style = OpenClawTheme.typography.bodySmall,
                        color = OpenClawTheme.colors.textTertiary,
                    )
                }
            }

            Spacer(modifier = Modifier.height(OpenClawTheme.spacing.md))

            // Status items
            state.items.forEach { item ->
                Row(
                    modifier = Modifier.padding(vertical = OpenClawTheme.spacing.xxs),
                    horizontalArrangement = Arrangement.spacedBy(OpenClawTheme.spacing.sm),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        text = item.icon,
                        style = OpenClawTheme.typography.bodyMedium,
                    )
                    Text(
                        text = item.label,
                        style = OpenClawTheme.typography.bodyMedium,
                        color = OpenClawTheme.colors.textSecondary,
                    )
                }
            }

            // Quick stats row (compact device/weather summary)
            if (state.quickStats.isNotEmpty()) {
                Spacer(modifier = Modifier.height(OpenClawTheme.spacing.md))
                Text(
                    text = state.quickStats,
                    style = OpenClawTheme.typography.bodySmall,
                    color = OpenClawTheme.colors.textTertiary,
                )
            }
        }
    }
}

@Preview(showBackground = true, backgroundColor = 0xFF0A0A0F)
@Composable
fun StatusCardPreview() {
    OpenClawTheme(darkTheme = true) {
        StatusCard(
            state = CardState.Status(
                id = "preview",
                title = "📅 Heute",
                subtitle = "Do 12. Feb",
                items = listOf(
                    StatusItem("📅", "10:00  Team Standup"),
                    StatusItem("📅", "14:00  Zahnarzt  ⚠️ in 2h"),
                ),
                quickStats = "🚗 92%  ·  🏠 19°C  ·  🌤️ 4°C"
            ),
            modifier = Modifier.padding(16.dp)
        )
    }
}
