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

    fun load(prefs: SharedPreferences) {
        theme = prefs.getString("theme", "system") ?: "system"
        textScale = scaleOf(prefs.getString("text_size", "normal") ?: "normal")
    }

    fun scaleOf(size: String): Float = when (size) { "large" -> 1.15f; "larger" -> 1.3f; else -> 1f }
}

/** Whether the colours below are the dark or the light set. Changing it redraws every screen that uses them. */
object Pal {
    var dark by mutableStateOf(true)
}

val Navy: Color get() = if (Pal.dark) Color(0xFF0B1220) else Color(0xFFF3F5F9)
val Panel: Color get() = if (Pal.dark) Color(0xFF111826) else Color(0xFFFFFFFF)
val PanelHigh: Color get() = if (Pal.dark) Color(0xFF172033) else Color(0xFFE8EDF5)
val Line: Color get() = if (Pal.dark) Color(0xFF232A36) else Color(0xFFD9E0EA)
val Blue: Color get() = if (Pal.dark) Color(0xFF2F7BFF) else Color(0xFF1F62E0)
val Ink: Color get() = if (Pal.dark) Color(0xFFE8EDF5) else Color(0xFF142033)
val Muted: Color get() = if (Pal.dark) Color(0xFF93A0B5) else Color(0xFF55657B)
val Green: Color get() = if (Pal.dark) Color(0xFF3DDC97) else Color(0xFF1B9A66)
val Red: Color get() = if (Pal.dark) Color(0xFFFF7B7B) else Color(0xFFD13B3B)
val Amber: Color get() = if (Pal.dark) Color(0xFFF2C46D) else Color(0xFFA9680B)

private val darkScheme = darkColorScheme(
    primary = Color(0xFF2F7BFF),
    onPrimary = Color.White,
    background = Color(0xFF0B1220),
    onBackground = Color(0xFFE8EDF5),
    surface = Color(0xFF111826),
    onSurface = Color(0xFFE8EDF5),
    surfaceVariant = Color(0xFF172033),
    onSurfaceVariant = Color(0xFF93A0B5),
    outline = Color(0xFF232A36),
    error = Color(0xFFFF7B7B),
)

private val lightScheme = lightColorScheme(
    primary = Color(0xFF1F62E0),
    onPrimary = Color.White,
    background = Color(0xFFF3F5F9),
    onBackground = Color(0xFF142033),
    surface = Color(0xFFFFFFFF),
    onSurface = Color(0xFF142033),
    surfaceVariant = Color(0xFFE8EDF5),
    onSurfaceVariant = Color(0xFF55657B),
    outline = Color(0xFFD9E0EA),
    error = Color(0xFFD13B3B),
)

/** Calm and dark by default, light if the phone (or the person) says so, with the text size the person chose. */
@Composable
fun EnveliqTheme(content: @Composable () -> Unit) {
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
        MaterialTheme(colorScheme = if (dark) darkScheme else lightScheme, content = content)
    }
}
