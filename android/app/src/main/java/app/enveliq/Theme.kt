package app.enveliq

import android.app.Activity
import android.content.SharedPreferences
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.unit.Density
import androidx.core.view.WindowCompat

/** What the person chose for how the app looks: "system" (follow the phone), "light" or "dark", and how big the text is. */
object Look {
    var theme by mutableStateOf("system")
    var textScale by mutableStateOf(1f)
    /** The highlight colour: blue (the app's own), green, purple, orange, pink or teal. It is the colour of buttons, links and chosen items. */
    var highlight by mutableStateOf("blue")

    val highlights = listOf("blue" to "Blue", "green" to "Green", "purple" to "Purple", "orange" to "Orange", "pink" to "Pink", "teal" to "Teal")

    // The same six highlight colours as the Casier web app (theme/theme.css): the accent for buttons and links, the soft tint behind a chosen item and
    // the ink on that tint, each in a light and a dark version.
    private class Hue(val light: Long, val dark: Long, val tintLight: Long, val tintDark: Long, val inkLight: Long, val inkDark: Long)

    private fun hue(): Hue = when (highlight) {
        "green" -> Hue(0xFF148A50, 0xFF2FBF71, 0xFFE3F1EA, 0xFF224233, 0xFF0C5330, 0xFFA1E2BF)
        "purple" -> Hue(0xFF6A3FD0, 0xFF9A7BFF, 0xFFEDE8F9, 0xFF393353, 0xFF40267D, 0xFFD2C4FF)
        "orange" -> Hue(0xFFC2570A, 0xFFFF9A3C, 0xFFF8EBE2, 0xFF503A28, 0xFF743406, 0xFFFFD2A7)
        "pink" -> Hue(0xFFC2255F, 0xFFFF6FA8, 0xFFF8E5EC, 0xFF50313F, 0xFF741639, 0xFFFFBED8)
        "teal" -> Hue(0xFF0F7F8B, 0xFF2FC4D3, 0xFFE2F0F1, 0xFF224349, 0xFF094C53, 0xFFA1E4EB)
        else -> Hue(0xFF2F62D6, 0xFF7AA7FF, 0xFFE3EBFC, 0xFF22304D, 0xFF1F3F8F, 0xFFCFE0FF)
    }

    fun accent(dark: Boolean): Color = hue().let { Color(if (dark) it.dark else it.light) }
    fun tint(dark: Boolean): Color = hue().let { Color(if (dark) it.tintDark else it.tintLight) }
    fun tintInk(dark: Boolean): Color = hue().let { Color(if (dark) it.inkDark else it.inkLight) }

    fun load(prefs: SharedPreferences) {
        theme = prefs.getString("theme", "system") ?: "system"
        textScale = scaleOf(prefs.getString("text_size", "normal") ?: "normal")
        highlight = (prefs.getString("highlight", "blue") ?: "blue").let { h -> if (highlights.any { it.first == h }) h else "blue" }
    }

    fun scaleOf(size: String): Float = when (size) { "large" -> 1.15f; "larger" -> 1.3f; else -> 1f }
}

/** Whether the colours below are the dark or the light set. Changing it redraws every screen that uses them. */
object Pal {
    var dark by mutableStateOf(true)
}

// The colours are the Casier web app's: a neutral grey (no tint) for dark, soft grey and white for light, and only the highlight is coloured.
val Navy: Color get() = if (Pal.dark) Color(0xFF151618) else Color(0xFFF4F5F7)
val Panel: Color get() = if (Pal.dark) Color(0xFF1E1F22) else Color(0xFFFFFFFF)
val PanelHigh: Color get() = if (Pal.dark) Color(0xFF27282C) else Color(0xFFEEF0F3)
val Line: Color get() = if (Pal.dark) Color(0xFF34363B) else Color(0xFFDDE0E5)
val Blue: Color get() = Look.accent(Pal.dark)
/** The text and icons that sit on the highlight colour (a button). */
val OnBlue: Color get() = if (Pal.dark) Color(0xFF0B1020) else Color.White
/** The soft tint behind a chosen item (a selected filter, a chosen row) and the ink on it. They follow the highlight colour. */
val Highlight: Color get() = Look.tint(Pal.dark)
val HighlightInk: Color get() = Look.tintInk(Pal.dark)
val Ink: Color get() = if (Pal.dark) Color(0xFFE6E7EA) else Color(0xFF1B1E23)
val Muted: Color get() = if (Pal.dark) Color(0xFF9B9EA6) else Color(0xFF5D636E)
val Green: Color get() = if (Pal.dark) Color(0xFF5FD392) else Color(0xFF15803D)
val Red: Color get() = if (Pal.dark) Color(0xFFF08A8D) else Color(0xFFB3261E)
val Amber: Color get() = if (Pal.dark) Color(0xFFF2BD62) else Color(0xFFB45309)
/** Soft backgrounds behind the green and red swipe and action icons. */
val GoodTint: Color get() = if (Pal.dark) Color(0xFF203A2B) else Color(0xFFE2F1E8)
val BadTint: Color get() = if (Pal.dark) Color(0xFF402528) else Color(0xFFF8E3E2)

private val darkScheme = darkColorScheme(
    primary = Color(0xFF7AA7FF),
    onPrimary = Color(0xFF0B1020),
    background = Color(0xFF151618),
    onBackground = Color(0xFFE6E7EA),
    surface = Color(0xFF1E1F22),
    onSurface = Color(0xFFE6E7EA),
    surfaceVariant = Color(0xFF27282C),
    onSurfaceVariant = Color(0xFF9B9EA6),
    outline = Color(0xFF34363B),
    error = Color(0xFFF08A8D),
)

private val lightScheme = lightColorScheme(
    primary = Color(0xFF2F62D6),
    onPrimary = Color.White,
    background = Color(0xFFF4F5F7),
    onBackground = Color(0xFF1B1E23),
    surface = Color(0xFFFFFFFF),
    onSurface = Color(0xFF1B1E23),
    surfaceVariant = Color(0xFFEEF0F3),
    onSurfaceVariant = Color(0xFF5D636E),
    outline = Color(0xFFDDE0E5),
    error = Color(0xFFB3261E),
)

/** Calm and dark by default, light if the phone (or the person) says so, with the text size the person chose. */
@Composable
fun CasierMailTheme(content: @Composable () -> Unit) {
    val system = isSystemInDarkTheme()
    val dark = when (Look.theme) { "light" -> false; "dark" -> true; else -> system }
    SideEffect { if (Pal.dark != dark) Pal.dark = dark }
    val view = LocalView.current
    SideEffect {
        val window = (view.context as? Activity)?.window
        if (window != null) {
            val controller = WindowCompat.getInsetsController(window, view)
            controller.isAppearanceLightStatusBars = !dark
            controller.isAppearanceLightNavigationBars = !dark
        }
    }
    val density = LocalDensity.current
    CompositionLocalProvider(LocalDensity provides Density(density.density, density.fontScale * Look.textScale)) {
        MaterialTheme(colorScheme = (if (dark) darkScheme else lightScheme).copy(primary = Look.accent(dark), onPrimary = if (dark) Color(0xFF0B1020) else Color.White), content = content)
    }
}
