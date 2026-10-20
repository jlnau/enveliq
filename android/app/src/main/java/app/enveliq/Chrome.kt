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
    bellUnread: Boolean = false, onBell: () -> Unit = {},
) {
    var open by remember { mutableStateOf(false) }
    Row(Modifier.fillMaxWidth().height(52.dp).padding(horizontal = 4.dp), verticalAlignment = Alignment.CenterVertically) {
        IconButton(onClick = onMenu) { Icon(Icons.Filled.Menu, contentDescription = "Menu", tint = Ink) }
        Image(painterResource(R.drawable.wordmark), contentDescription = "Enveliq", contentScale = ContentScale.Fit, modifier = Modifier.height(30.dp).widthIn(max = 110.dp))
        Spacer(Modifier.weight(1f))
        IconButton(onClick = onBell) {
            Box(contentAlignment = Alignment.TopEnd) {
                BellIcon(Ink, Modifier.size(24.dp))
                if (bellUnread) Box(Modifier.size(9.dp).clip(CircleShape).background(Color(0xFFE5484D)))
            }
        }
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

private fun reply(scope: androidx.compose.ui.graphics.drawscope.DrawScope, tint: Color, flip: Boolean, double: Boolean) = with(scope) {
    val u = size.width / 24f
    fun x(v: Float) = (if (flip) 24f - v else v) * u
    val st = Stroke(width = 2f * u, cap = StrokeCap.Round, join = androidx.compose.ui.graphics.StrokeJoin.Round)
    fun head(dx: Float) {
        val p = androidx.compose.ui.graphics.Path()
        p.moveTo(x(9f + dx), 7f * u); p.lineTo(x(4f + dx), 12f * u); p.lineTo(x(9f + dx), 17f * u)
        drawPath(p, tint, style = st)
    }
    val body = androidx.compose.ui.graphics.Path()
    val from = if (double) 9f else 4f
    body.moveTo(x(from), 12f * u); body.lineTo(x(14f), 12f * u); body.quadraticBezierTo(x(21f), 12f * u, x(21f), 19f * u)
    drawPath(body, tint, style = st)
    head(if (double) 5f else 0f)
    if (double) head(0f)
}

@Composable
internal fun ReplyIcon(tint: Color, modifier: Modifier = Modifier.size(24.dp)) = Canvas(modifier) { reply(this, tint, flip = false, double = false) }

@Composable
internal fun ReplyAllIcon(tint: Color, modifier: Modifier = Modifier.size(24.dp)) = Canvas(modifier) { reply(this, tint, flip = false, double = true) }

@Composable
internal fun ForwardIcon(tint: Color, modifier: Modifier = Modifier.size(24.dp)) = Canvas(modifier) { reply(this, tint, flip = true, double = false) }

/** A tick box with a plus: add a task. */
@Composable
internal fun AddTaskIcon(tint: Color, modifier: Modifier = Modifier.size(24.dp)) = Canvas(modifier) {
    val u = size.width / 24f
    val st = Stroke(width = 2f * u, cap = StrokeCap.Round)
    drawRoundRect(tint, Offset(4f * u, 4f * u), Size(16f * u, 16f * u), androidx.compose.ui.geometry.CornerRadius(3f * u), style = st)
    drawLine(tint, Offset(12f * u, 8.5f * u), Offset(12f * u, 15.5f * u), strokeWidth = 2f * u, cap = StrokeCap.Round)
    drawLine(tint, Offset(8.5f * u, 12f * u), Offset(15.5f * u, 12f * u), strokeWidth = 2f * u, cap = StrokeCap.Round)
}

/** The notification bell: notes and alerts from your other services. */
@Composable
internal fun BellIcon(tint: Color, modifier: Modifier = Modifier.size(24.dp)) = Canvas(modifier) {
    val u = size.width / 24f
    val p = androidx.compose.ui.graphics.Path()
    p.moveTo(5.5f * u, 17f * u)
    p.cubicTo(7f * u, 15.5f * u, 7f * u, 13f * u, 7f * u, 10.5f * u)
    p.cubicTo(7f * u, 7.5f * u, 9.2f * u, 5.5f * u, 12f * u, 5.5f * u)
    p.cubicTo(14.8f * u, 5.5f * u, 17f * u, 7.5f * u, 17f * u, 10.5f * u)
    p.cubicTo(17f * u, 13f * u, 17f * u, 15.5f * u, 18.5f * u, 17f * u)
    p.close()
    val st = Stroke(width = 2f * u, cap = StrokeCap.Round, join = androidx.compose.ui.graphics.StrokeJoin.Round)
    drawPath(p, tint, style = st)
    drawLine(tint, Offset(12f * u, 3.5f * u), Offset(12f * u, 5.5f * u), strokeWidth = 2f * u, cap = StrokeCap.Round)
    val c = androidx.compose.ui.graphics.Path()
    c.moveTo(10f * u, 19.5f * u); c.quadraticBezierTo(12f * u, 21.8f * u, 14f * u, 19.5f * u)
    drawPath(c, tint, style = st)
}

/** An envelope with a tick: "Include read mail". */
@Composable
internal fun ReadMailIcon(tint: Color, modifier: Modifier = Modifier.size(24.dp)) = Canvas(modifier) {
    val u = size.width / 24f
    val st = Stroke(width = 2f * u, cap = StrokeCap.Round, join = androidx.compose.ui.graphics.StrokeJoin.Round)
    drawRoundRect(tint, topLeft = Offset(3f * u, 5f * u), size = Size(18f * u, 14f * u), cornerRadius = androidx.compose.ui.geometry.CornerRadius(2.5f * u), style = st)
    val p = androidx.compose.ui.graphics.Path()
    p.moveTo(3.5f * u, 7f * u); p.lineTo(12f * u, 13.5f * u); p.lineTo(20.5f * u, 7f * u)
    drawPath(p, tint, style = st)
}

/** A key: sign in with a passkey. */
@Composable
internal fun KeyIcon(tint: Color, modifier: Modifier = Modifier.size(22.dp)) = Canvas(modifier) {
    val u = size.width / 24f
    val st = Stroke(width = 2f * u, cap = StrokeCap.Round, join = androidx.compose.ui.graphics.StrokeJoin.Round)
    drawCircle(tint, radius = 4f * u, center = Offset(7.5f * u, 12f * u), style = st)
    drawLine(tint, Offset(11.5f * u, 12f * u), Offset(21f * u, 12f * u), strokeWidth = 2f * u, cap = StrokeCap.Round)
    drawLine(tint, Offset(17.5f * u, 12f * u), Offset(17.5f * u, 15.5f * u), strokeWidth = 2f * u, cap = StrokeCap.Round)
    drawLine(tint, Offset(21f * u, 12f * u), Offset(21f * u, 15.5f * u), strokeWidth = 2f * u, cap = StrokeCap.Round)
}
