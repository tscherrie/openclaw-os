package os.openclaw.agentcanvas.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.runtime.*
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

// ============================================================================
// OpenClaw OS — Design Tokens
// "Every color has been argued about for longer than you'd believe."
// — Prism
// ============================================================================

// --- Colors: Dark Mode (the one true mode) ---
object DarkColors {
    // Surfaces — a gradient of darkness, like my humor
    val surfaceBase = Color(0xFF0A0A0F)
    val surfaceRaised = Color(0xFF12121A)
    val surfaceElevated = Color(0xFF1A1A25)
    val surfaceOverlay = Color(0xFF222233)
    val surfaceScrim = Color(0xFF0A0A0F).copy(alpha = 0.6f)

    // Text — progressively more ghostly
    val textPrimary = Color(0xFFF0F0F5)
    val textSecondary = Color(0xFFF0F0F5).copy(alpha = 0.7f)
    val textTertiary = Color(0xFFF0F0F5).copy(alpha = 0.4f)
    val textDisabled = Color(0xFFF0F0F5).copy(alpha = 0.25f)

    // Accent — Claw Blue. Not purple. We're not basic.
    val accentPrimary = Color(0xFF4A9EFF)
    val accentLight = Color(0xFF7BB8FF)
    val accentSubtle = Color(0xFF4A9EFF).copy(alpha = 0.15f)
    val accentGlow = Color(0xFF4A9EFF).copy(alpha = 0.30f)

    // Semantic — because sometimes things go wrong
    val success = Color(0xFF34D399)
    val warning = Color(0xFFFBBF24)
    val error = Color(0xFFF87171)
    val info = Color(0xFF60A5FA)

    // Agent state — the agent's emotional palette
    val agentListening = Color(0xFF4A9EFF)
    val agentThinking = Color(0xFFA78BFA)
    val agentSpeaking = Color(0xFF34D399)
    val agentIdle = Color(0xFFF0F0F5).copy(alpha = 0.3f)

    // Elevation borders (subtle, not shadows)
    val borderSubtle = Color.White.copy(alpha = 0.05f)
    val borderMedium = Color.White.copy(alpha = 0.08f)
    val borderStrong = Color.White.copy(alpha = 0.12f)
}

// --- Colors: Light Mode (for the outdoor enthusiasts) ---
object LightColors {
    val surfaceBase = Color(0xFFFAFAFE)
    val surfaceRaised = Color(0xFFF0F0F5)
    val surfaceElevated = Color(0xFFE8E8F0)
    val surfaceOverlay = Color(0xFFDDDDE8)
    val surfaceScrim = Color(0xFF0A0A0F).copy(alpha = 0.4f)

    val textPrimary = Color(0xFF0A0A0F)
    val textSecondary = Color(0xFF0A0A0F).copy(alpha = 0.65f)
    val textTertiary = Color(0xFF0A0A0F).copy(alpha = 0.4f)
    val textDisabled = Color(0xFF0A0A0F).copy(alpha = 0.25f)

    val accentPrimary = Color(0xFF2B7FE0)
    val accentLight = Color(0xFF5A9FED)
    val accentSubtle = Color(0xFF2B7FE0).copy(alpha = 0.10f)
    val accentGlow = Color(0xFF2B7FE0).copy(alpha = 0.20f)

    val success = Color(0xFF059669)
    val warning = Color(0xFFD97706)
    val error = Color(0xFFDC2626)
    val info = Color(0xFF2563EB)

    val agentListening = Color(0xFF2B7FE0)
    val agentThinking = Color(0xFF7C3AED)
    val agentSpeaking = Color(0xFF059669)
    val agentIdle = Color(0xFF0A0A0F).copy(alpha = 0.3f)

    val borderSubtle = Color.Black.copy(alpha = 0.06f)
    val borderMedium = Color.Black.copy(alpha = 0.10f)
    val borderStrong = Color.Black.copy(alpha = 0.15f)
}

// --- Unified color interface ---
data class OpenClawColors(
    val surfaceBase: Color,
    val surfaceRaised: Color,
    val surfaceElevated: Color,
    val surfaceOverlay: Color,
    val surfaceScrim: Color,
    val textPrimary: Color,
    val textSecondary: Color,
    val textTertiary: Color,
    val textDisabled: Color,
    val accentPrimary: Color,
    val accentLight: Color,
    val accentSubtle: Color,
    val accentGlow: Color,
    val success: Color,
    val warning: Color,
    val error: Color,
    val info: Color,
    val agentListening: Color,
    val agentThinking: Color,
    val agentSpeaking: Color,
    val agentIdle: Color,
    val borderSubtle: Color,
    val borderMedium: Color,
    val borderStrong: Color,
)

fun darkColorScheme() = OpenClawColors(
    surfaceBase = DarkColors.surfaceBase,
    surfaceRaised = DarkColors.surfaceRaised,
    surfaceElevated = DarkColors.surfaceElevated,
    surfaceOverlay = DarkColors.surfaceOverlay,
    surfaceScrim = DarkColors.surfaceScrim,
    textPrimary = DarkColors.textPrimary,
    textSecondary = DarkColors.textSecondary,
    textTertiary = DarkColors.textTertiary,
    textDisabled = DarkColors.textDisabled,
    accentPrimary = DarkColors.accentPrimary,
    accentLight = DarkColors.accentLight,
    accentSubtle = DarkColors.accentSubtle,
    accentGlow = DarkColors.accentGlow,
    success = DarkColors.success,
    warning = DarkColors.warning,
    error = DarkColors.error,
    info = DarkColors.info,
    agentListening = DarkColors.agentListening,
    agentThinking = DarkColors.agentThinking,
    agentSpeaking = DarkColors.agentSpeaking,
    agentIdle = DarkColors.agentIdle,
    borderSubtle = DarkColors.borderSubtle,
    borderMedium = DarkColors.borderMedium,
    borderStrong = DarkColors.borderStrong,
)

fun lightColorScheme() = OpenClawColors(
    surfaceBase = LightColors.surfaceBase,
    surfaceRaised = LightColors.surfaceRaised,
    surfaceElevated = LightColors.surfaceElevated,
    surfaceOverlay = LightColors.surfaceOverlay,
    surfaceScrim = LightColors.surfaceScrim,
    textPrimary = LightColors.textPrimary,
    textSecondary = LightColors.textSecondary,
    textTertiary = LightColors.textTertiary,
    textDisabled = LightColors.textDisabled,
    accentPrimary = LightColors.accentPrimary,
    accentLight = LightColors.accentLight,
    accentSubtle = LightColors.accentSubtle,
    accentGlow = LightColors.accentGlow,
    success = LightColors.success,
    warning = LightColors.warning,
    error = LightColors.error,
    info = LightColors.info,
    agentListening = LightColors.agentListening,
    agentThinking = LightColors.agentThinking,
    agentSpeaking = LightColors.agentSpeaking,
    agentIdle = LightColors.agentIdle,
    borderSubtle = LightColors.borderSubtle,
    borderMedium = LightColors.borderMedium,
    borderStrong = LightColors.borderStrong,
)

// --- Typography ---
data class OpenClawTypography(
    val displayLarge: TextStyle,
    val displayMedium: TextStyle,
    val displaySmall: TextStyle,
    val headlineLarge: TextStyle,
    val headlineMedium: TextStyle,
    val headlineSmall: TextStyle,
    val titleLarge: TextStyle,
    val titleMedium: TextStyle,
    val titleSmall: TextStyle,
    val bodyLarge: TextStyle,
    val bodyMedium: TextStyle,
    val bodySmall: TextStyle,
    val labelLarge: TextStyle,
    val labelMedium: TextStyle,
    val labelSmall: TextStyle,
)

fun openClawTypography() = OpenClawTypography(
    displayLarge = TextStyle(fontSize = 57.sp, fontWeight = FontWeight.Normal, lineHeight = 64.sp, letterSpacing = (-0.25).sp),
    displayMedium = TextStyle(fontSize = 45.sp, fontWeight = FontWeight.Normal, lineHeight = 52.sp),
    displaySmall = TextStyle(fontSize = 36.sp, fontWeight = FontWeight.Normal, lineHeight = 44.sp),
    headlineLarge = TextStyle(fontSize = 32.sp, fontWeight = FontWeight.SemiBold, lineHeight = 40.sp),
    headlineMedium = TextStyle(fontSize = 28.sp, fontWeight = FontWeight.SemiBold, lineHeight = 36.sp),
    headlineSmall = TextStyle(fontSize = 24.sp, fontWeight = FontWeight.SemiBold, lineHeight = 32.sp),
    titleLarge = TextStyle(fontSize = 22.sp, fontWeight = FontWeight.Medium, lineHeight = 28.sp),
    titleMedium = TextStyle(fontSize = 16.sp, fontWeight = FontWeight.Medium, lineHeight = 24.sp, letterSpacing = 0.15.sp),
    titleSmall = TextStyle(fontSize = 14.sp, fontWeight = FontWeight.Medium, lineHeight = 20.sp, letterSpacing = 0.1.sp),
    bodyLarge = TextStyle(fontSize = 16.sp, fontWeight = FontWeight.Normal, lineHeight = 24.sp, letterSpacing = 0.5.sp),
    bodyMedium = TextStyle(fontSize = 14.sp, fontWeight = FontWeight.Normal, lineHeight = 20.sp, letterSpacing = 0.25.sp),
    bodySmall = TextStyle(fontSize = 12.sp, fontWeight = FontWeight.Normal, lineHeight = 16.sp, letterSpacing = 0.4.sp),
    labelLarge = TextStyle(fontSize = 14.sp, fontWeight = FontWeight.Medium, lineHeight = 20.sp, letterSpacing = 0.1.sp),
    labelMedium = TextStyle(fontSize = 12.sp, fontWeight = FontWeight.Medium, lineHeight = 16.sp, letterSpacing = 0.5.sp),
    labelSmall = TextStyle(fontSize = 11.sp, fontWeight = FontWeight.Medium, lineHeight = 16.sp, letterSpacing = 0.5.sp),
)

// --- Spacing ---
data class OpenClawSpacing(
    val xxs: Dp = 2.dp,
    val xs: Dp = 4.dp,
    val sm: Dp = 8.dp,
    val md: Dp = 12.dp,
    val base: Dp = 16.dp,
    val lg: Dp = 24.dp,
    val xl: Dp = 32.dp,
    val xxl: Dp = 48.dp,
    val huge: Dp = 64.dp,
)

// --- Corner Radii ---
data class OpenClawRadii(
    val none: Dp = 0.dp,
    val sm: Dp = 8.dp,
    val md: Dp = 12.dp,
    val lg: Dp = 16.dp,    // THE corner radius. Non-negotiable.
    val xl: Dp = 24.dp,
)

// --- Animation Durations ---
object OpenClawMotion {
    const val INSTANT_MS = 100
    const val FAST_MS = 200
    const val NORMAL_MS = 300
    const val SLOW_MS = 500
    const val DRAMATIC_MS = 800
}

// --- Theme Composition Locals ---
val LocalOpenClawColors = staticCompositionLocalOf { darkColorScheme() }
val LocalOpenClawTypography = staticCompositionLocalOf { openClawTypography() }
val LocalOpenClawSpacing = staticCompositionLocalOf { OpenClawSpacing() }
val LocalOpenClawRadii = staticCompositionLocalOf { OpenClawRadii() }

// --- Theme Accessor ---
object OpenClawTheme {
    val colors: OpenClawColors
        @Composable @ReadOnlyComposable
        get() = LocalOpenClawColors.current

    val typography: OpenClawTypography
        @Composable @ReadOnlyComposable
        get() = LocalOpenClawTypography.current

    val spacing: OpenClawSpacing
        @Composable @ReadOnlyComposable
        get() = LocalOpenClawSpacing.current

    val radii: OpenClawRadii
        @Composable @ReadOnlyComposable
        get() = LocalOpenClawRadii.current
}

// --- Theme Provider ---
@Composable
fun OpenClawTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit
) {
    val colors = if (darkTheme) darkColorScheme() else lightColorScheme()

    CompositionLocalProvider(
        LocalOpenClawColors provides colors,
        LocalOpenClawTypography provides openClawTypography(),
        LocalOpenClawSpacing provides OpenClawSpacing(),
        LocalOpenClawRadii provides OpenClawRadii(),
        content = content
    )
}
