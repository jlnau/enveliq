package app.enveliq

import android.graphics.Bitmap
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.layout.RowScope
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics

// Small line icons drawn by hand, so the app does not need the big icon library.

@Composable
internal fun ArchiveIcon(tint: Color, modifier: Modifier = Modifier.size(24.dp)) = Canvas(modifier) {
    val u = size.width / 24f
    val st = Stroke(width = 2f * u, cap = StrokeCap.Round)
    drawRect(tint, Offset(3f * u, 4f * u), Size(18f * u, 5f * u), style = st)
    drawRect(tint, Offset(5f * u, 9f * u), Size(14f * u, 11f * u), style = st)
    drawLine(tint, Offset(10f * u, 13f * u), Offset(14f * u, 13f * u), strokeWidth = 2f * u, cap = StrokeCap.Round)
}

/** Three lines getting shorter: "filter". */
@Composable
internal fun FilterIcon(tint: Color, modifier: Modifier = Modifier.size(24.dp)) = Canvas(modifier) {
    val u = size.width / 24f
    fun line(y: Float, a: Float, b: Float) = drawLine(tint, Offset(a * u, y * u), Offset(b * u, y * u), strokeWidth = 2f * u, cap = StrokeCap.Round)
    line(7f, 4f, 20f); line(12f, 7f, 17f); line(17f, 10f, 14f)
}

/** A "#": tags and other ways to narrow the list. */
@Composable
internal fun TagIcon(tint: Color, modifier: Modifier = Modifier.size(24.dp)) = Canvas(modifier) {
    val u = size.width / 24f
    fun line(x1: Float, y1: Float, x2: Float, y2: Float) = drawLine(tint, Offset(x1 * u, y1 * u), Offset(x2 * u, y2 * u), strokeWidth = 2f * u, cap = StrokeCap.Round)
    line(9f, 4f, 7f, 20f); line(17f, 4f, 15f, 20f); line(4f, 9f, 20f, 9f); line(4f, 15f, 20f, 15f)
}

@Composable
internal fun ClockIcon(tint: Color, modifier: Modifier = Modifier.size(24.dp)) = Canvas(modifier) {
    val u = size.width / 24f
    drawCircle(tint, radius = 9f * u, center = Offset(12f * u, 12f * u), style = Stroke(width = 2f * u))
    drawLine(tint, Offset(12f * u, 7f * u), Offset(12f * u, 12f * u), strokeWidth = 2f * u, cap = StrokeCap.Round)
    drawLine(tint, Offset(12f * u, 12f * u), Offset(15.5f * u, 14f * u), strokeWidth = 2f * u, cap = StrokeCap.Round)
}

/** The person's picture, or their initials when there is none. No words. */
@Composable
internal fun AvatarCircle(me: Me?, picture: Bitmap?, size: Int = 34) {
    Box(Modifier.size(size.dp).clip(CircleShape).background(PanelHigh), contentAlignment = Alignment.Center) {
        if (picture != null) Image(picture.asImageBitmap(), contentDescription = null, contentScale = ContentScale.Crop, modifier = Modifier.size(size.dp))
        else Text(me?.initials ?: "", color = Ink, fontSize = (size * 0.38f).sp, fontWeight = FontWeight.Bold)
    }
}

/** The top row of the list screens: menu, the Enveliq logo, search, and the person's picture with its small menu. */
@Composable
internal fun AppTopBar(
    me: Me?, picture: Bitmap?, showSearch: Boolean, searching: Boolean,
    onMenu: () -> Unit, onSearch: () -> Unit, onAccount: () -> Unit, onSettings: () -> Unit,
) {
    var open by remember { mutableStateOf(false) }
    Row(Modifier.fillMaxWidth().height(52.dp).padding(horizontal = 4.dp), verticalAlignment = Alignment.CenterVertically) {
        IconButton(onClick = onMenu) { Icon(Icons.Filled.Menu, contentDescription = "Menu", tint = Ink) }
        Image(painterResource(R.drawable.wordmark), contentDescription = "Enveliq", contentScale = ContentScale.Fit, modifier = Modifier.height(30.dp).widthIn(max = 110.dp))
        Spacer(Modifier.weight(1f))
        if (showSearch) IconButton(onClick = onSearch) { Icon(Icons.Filled.Search, contentDescription = if (searching) "Close search" else "Search", tint = if (searching) Blue else Ink) }
        Box(Modifier.padding(start = 2.dp, end = 10.dp)) {
            Box(Modifier.clip(CircleShape).clickable { open = true }.padding(2.dp)) { AvatarCircle(me, picture) }
            DropdownMenu(expanded = open, onDismissRequest = { open = false }, containerColor = Panel) {
                DropdownMenuItem(text = { Text("Your account", color = Ink) }, onClick = { open = false; onAccount() })
                DropdownMenuItem(text = { Text("Settings", color = Ink) }, onClick = { open = false; onSettings() })
            }
        }
    }
}

/** A round icon button for the bar at the bottom of an open email. */
@Composable
internal fun RowScope.BarIcon(label: String, tint: Color, container: Color, onClick: () -> Unit, icon: @Composable () -> Unit) {
    Box(
        Modifier.weight(1f).height(52.dp).clip(androidx.compose.foundation.shape.RoundedCornerShape(14.dp)).background(container)
            .clickable(onClickLabel = label, onClick = onClick)
            .androidx_semantics(label),
        contentAlignment = Alignment.Center,
    ) { icon() }
}

private fun Modifier.androidx_semantics(label: String): Modifier =
    this.then(Modifier.semantics { contentDescription = label })

/** A small paperclip: this email has files. */
@Composable
internal fun PaperclipIcon(tint: Color, modifier: Modifier = Modifier.size(16.dp)) = Canvas(modifier) {
    val u = size.width / 24f
    val p = androidx.compose.ui.graphics.Path()
    p.moveTo(9f * u, 7f * u)
    p.lineTo(9f * u, 16f * u)
    p.arcTo(androidx.compose.ui.geometry.Rect(9f * u, 12.5f * u, 16f * u, 19.5f * u), 180f, -180f, false)
    p.lineTo(16f * u, 6f * u)
    p.arcTo(androidx.compose.ui.geometry.Rect(11f * u, 3.5f * u, 16f * u, 8.5f * u), 0f, -180f, false)
    p.lineTo(11f * u, 15f * u)
    drawPath(p, tint, style = Stroke(width = 2f * u, cap = StrokeCap.Round))
}
