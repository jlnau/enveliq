package app.enveliq

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

val Navy = Color(0xFF0B1220)
val Panel = Color(0xFF111826)
val PanelHigh = Color(0xFF172033)
val Line = Color(0xFF232A36)
val Blue = Color(0xFF2F7BFF)
val Ink = Color(0xFFE8EDF5)
val Muted = Color(0xFF93A0B5)
val Green = Color(0xFF3DDC97)
val Red = Color(0xFFFF7B7B)
val Amber = Color(0xFFF2C46D)

private val scheme = darkColorScheme(
    primary = Blue,
    onPrimary = Color.White,
    background = Navy,
    onBackground = Ink,
    surface = Panel,
    onSurface = Ink,
    surfaceVariant = PanelHigh,
    onSurfaceVariant = Muted,
    outline = Line,
    error = Red,
)

/** One calm, dark look, like the website's default. */
@Composable
fun EnveliqTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = scheme, content = content)
}
