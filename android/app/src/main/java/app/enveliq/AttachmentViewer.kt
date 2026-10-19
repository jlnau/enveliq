package app.enveliq

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

private fun isPicture(f: Attachment): Boolean {
    val n = f.name.lowercase()
    return f.mime.startsWith("image/") || n.endsWith(".jpg") || n.endsWith(".jpeg") || n.endsWith(".png") || n.endsWith(".gif") || n.endsWith(".webp")
}

/** The files that came with an email, each with the AI's note on it (labelled), a way to look at it, and a way to save it. The app keeps nothing. */
@Composable
internal fun AttachmentsSection(mail: Mail, api: EnveliqApi) {
    if (mail.attachments.isEmpty()) return
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var pending by remember(mail.id) { mutableStateOf<Attachment?>(null) }
    var viewing by remember(mail.id) { mutableStateOf<Attachment?>(null) }
    var status by remember(mail.id) { mutableStateOf("") }
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/octet-stream")) { uri: Uri? ->
        val file = pending
        pending = null
        if (uri != null && file != null) {
            status = "Saving " + file.name + "…"
            scope.launch {
                try {
                    val bytes = withContext(Dispatchers.IO) { api.download(mail, file.index) }
                    withContext(Dispatchers.IO) { context.contentResolver.openOutputStream(uri)?.use { it.write(bytes) } }
                    status = "Saved " + file.name + "."
                } catch (e: ApiException) {
                    status = e.message ?: "Could not save the file."
                } catch (e: Exception) {
                    status = "Could not save the file."
                }
            }
        }
    }
    Column(Modifier.fillMaxWidth().padding(top = 18.dp)) {
        Text("Files with this email", color = Muted, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
        mail.attachments.forEach { file ->
            Surface(
                color = Panel, shape = RoundedCornerShape(14.dp), border = BorderStroke(1.dp, Line),
                modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
            ) {
                Column(Modifier.padding(14.dp)) {
                    Text(file.name, color = Ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                    val size = sizeText(file.size)
                    val kind = if (isPicture(file)) "Picture" else file.mime.substringAfter('/', "").uppercase().take(12)
                    val line = listOf(size, kind, if (file.pages > 0) file.pages.toString() + (if (file.pages == 1) " page" else " pages") else "").filter { it.isNotEmpty() }.joinToString(" · ")
                    if (line.isNotEmpty()) Text(line, color = Muted, fontSize = 13.sp)
                    when {
                        file.summary.isNotBlank() -> {
                            Text("✦ " + file.summary, color = Ink, fontSize = 14.sp, lineHeight = 21.sp, modifier = Modifier.padding(top = 6.dp))
                            file.parts.filter { it.second.isNotBlank() }.forEach { (title, text) ->
                                if (title.isNotBlank()) Text(title, color = Ink, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 8.dp))
                                Text(text, color = Ink, fontSize = 14.sp, lineHeight = 21.sp, modifier = Modifier.padding(top = 2.dp))
                            }
                            if (file.note.isNotBlank()) Text(file.note, color = Muted, fontSize = 12.sp, modifier = Modifier.padding(top = 4.dp))
                            Text("Written by the AI. It can be wrong.", color = Muted, fontSize = 12.sp, modifier = Modifier.padding(top = 4.dp))
                        }
                        file.state == "working" || file.state == "reading" -> Text("The AI is still reading this file…", color = Muted, fontSize = 14.sp, modifier = Modifier.padding(top = 6.dp))
                        file.reason.isNotBlank() -> Text(file.reason, color = Muted, fontSize = 13.sp, modifier = Modifier.padding(top = 6.dp))
                    }
                    Row(Modifier.padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(
                            onClick = { viewing = file },
                            shape = RoundedCornerShape(12.dp), border = BorderStroke(1.dp, Line),
                        ) { Text(if (isPicture(file)) "Preview" else "View", color = Ink) }
                        OutlinedButton(
                            onClick = { pending = file; picker.launch(file.name) },
                            shape = RoundedCornerShape(12.dp), border = BorderStroke(1.dp, Line),
                        ) { Text("Save to my phone", color = Ink) }
                    }
                }
            }
        }
        if (status.isNotEmpty()) Text(status, color = Muted, fontSize = 14.sp, modifier = Modifier.padding(top = 6.dp))
        Text("Fetched from your mailbox when you ask. Not saved in Enveliq or kept on this phone.", color = Muted, fontSize = 12.sp, modifier = Modifier.padding(top = 6.dp))
    }
    viewing?.let { AttachmentViewer(mail, it, api, onSave = { pending = it; picker.launch(it.name) }) { viewing = null } }
}

private sealed class Shown {
    object Loading : Shown()
    class Failed(val text: String) : Shown()
    class Picture(val bitmap: Bitmap) : Shown()
    class Pages(val pages: List<Bitmap>, val total: Int) : Shown()
    class Table(val rows: List<List<String>>, val cut: Boolean) : Shown()
    class Words(val text: String, val cut: Boolean) : Shown()
}

/** The same viewer as the website: a picture, the pages of a PDF (with zoom), a table or plain text. The server makes it in memory; nothing is saved. */
@Composable
private fun AttachmentViewer(mail: Mail, file: Attachment, api: EnveliqApi, onSave: () -> Unit, onClose: () -> Unit) {
    var shown by remember(file.index) { mutableStateOf<Shown>(Shown.Loading) }
    var zoom by remember(file.index) { mutableStateOf(100) }
    LaunchedEffect(file.index) {
        shown = try {
            withContext(Dispatchers.IO) {
                if (isPicture(file)) {
                    val bytes = api.download(mail, file.index, preview = true)
                    val bmp = BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
                    if (bmp == null) Shown.Failed("This picture cannot be shown here. Use Save to my phone.") else Shown.Picture(bmp)
                } else {
                    val j = api.viewAttachment(mail, file.index)
                    when (j.optString("kind")) {
                        "pdf" -> {
                            val arr = j.optJSONArray("pages")
                            val list = ArrayList<Bitmap>()
                            if (arr != null) for (i in 0 until arr.length()) {
                                val raw = android.util.Base64.decode(arr.optString(i), android.util.Base64.DEFAULT)
                                BitmapFactory.decodeByteArray(raw, 0, raw.size)?.let { list.add(it) }
                            }
                            Shown.Pages(list, j.optInt("total", list.size))
                        }
                        "csv" -> {
                            val rows = ArrayList<List<String>>()
                            val arr = j.optJSONArray("rows")
                            if (arr != null) for (i in 0 until arr.length()) {
                                val r = arr.optJSONArray(i) ?: continue
                                rows.add((0 until r.length()).map { r.optString(it) })
                            }
                            Shown.Table(rows, j.optBoolean("truncated", false))
                        }
                        "text" -> Shown.Words(j.optString("text").ifBlank { "(empty)" }, j.optBoolean("truncated", false))
                        else -> Shown.Failed(j.optString("reason").ifBlank { "This file cannot be shown here. Use Save to my phone." })
                    }
                }
            }
        } catch (e: ApiException) {
            Shown.Failed(e.message ?: "Could not open that file.")
        } catch (e: Exception) {
            Shown.Failed("Could not open that file.")
        }
    }
    Dialog(onDismissRequest = onClose, properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        Surface(color = Navy, modifier = Modifier.fillMaxSize()) {
            Column(Modifier.fillMaxSize().systemBarsPadding()) {
                Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f).padding(start = 8.dp)) {
                        Text(file.name, color = Ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
                        val s = shown
                        val sub = when (s) {
                            is Shown.Pages -> sizeText(file.size) + " · " + s.total + (if (s.total == 1) " page" else " pages")
                            else -> sizeText(file.size)
                        }
                        if (sub.isNotBlank()) Text(sub, color = Muted, fontSize = 12.sp)
                    }
                    if (shown is Shown.Pages || shown is Shown.Picture) {
                        TextButton(onClick = { zoom = (zoom - 20).coerceAtLeast(40) }) { Text("−", color = Blue, fontSize = 20.sp) }
                        TextButton(onClick = { zoom = (zoom + 20).coerceAtMost(300) }) { Text("+", color = Blue, fontSize = 20.sp) }
                    }
                    TextButton(onClick = onSave) { Text("Save", color = Blue, fontSize = 15.sp) }
                    TextButton(onClick = onClose) { Text("Close", color = Blue, fontSize = 15.sp) }
                }
                val width = (LocalConfiguration.current.screenWidthDp - 24).dp
                Box(Modifier.weight(1f).fillMaxWidth()) {
                    when (val s = shown) {
                        is Shown.Loading -> Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.Center, horizontalAlignment = Alignment.CenterHorizontally) {
                            CircularProgressIndicator(color = Blue)
                            Text("Fetching from your mailbox…", color = Muted, fontSize = 14.sp, modifier = Modifier.padding(top = 12.dp))
                        }
                        is Shown.Failed -> Text(s.text, color = Muted, fontSize = 16.sp, modifier = Modifier.padding(24.dp))
                        is Shown.Picture -> Box(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).horizontalScroll(rememberScrollState())) {
                            Image(s.bitmap.asImageBitmap(), contentDescription = file.name, contentScale = ContentScale.FillWidth, modifier = Modifier.width(width * zoom / 100).padding(12.dp))
                        }
                        is Shown.Pages -> Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).horizontalScroll(rememberScrollState()).padding(12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            s.pages.forEachIndexed { i, bmp ->
                                Image(bmp.asImageBitmap(), contentDescription = "Page " + (i + 1) + " of " + s.total, contentScale = ContentScale.FillWidth, modifier = Modifier.width(width * zoom / 100).background(androidx.compose.ui.graphics.Color.White))
                            }
                            if (s.pages.size < s.total) Text("Showing the first " + s.pages.size + " of " + s.total + " pages. Save to my phone to read the rest.", color = Muted, fontSize = 13.sp)
                        }
                        is Shown.Table -> Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).horizontalScroll(rememberScrollState()).padding(12.dp)) {
                            s.rows.forEachIndexed { ri, row ->
                                Row {
                                    row.forEach { cell ->
                                        Text(
                                            cell, color = Ink, fontSize = 13.sp, fontWeight = if (ri == 0) FontWeight.Bold else FontWeight.Normal, maxLines = 3,
                                            modifier = Modifier.width(130.dp).padding(end = 8.dp, bottom = 6.dp),
                                        )
                                    }
                                }
                            }
                            if (s.cut) Text("Shortened for display. Save to my phone for the whole file.", color = Muted, fontSize = 13.sp, modifier = Modifier.padding(top = 8.dp))
                        }
                        is Shown.Words -> Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp)) {
                            Text(s.text, color = Ink, fontSize = 14.sp, lineHeight = 21.sp, fontFamily = FontFamily.Monospace)
                            if (s.cut) Text("Shortened for display. Save to my phone for the whole file.", color = Muted, fontSize = 13.sp, modifier = Modifier.padding(top = 8.dp))
                        }
                    }
                }
            }
        }
    }
}
