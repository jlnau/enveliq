package app.enveliq

import android.content.Intent
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.FilterChip
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
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
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.net.URI

/** The tags on an email. Tap Choose tags to open a full screen list where several can be ticked at once. Hidden when the mail service does not keep tags. */
/** Full screen: search at the top, a scrolling list of tags with tick boxes, Save fixed at the bottom. The email's current tags start ticked. */
@Composable
internal fun TagPickerScreen(mail: Mail, api: EnveliqApi, info: TagInfo, start: List<String>, onClose: () -> Unit, onSaved: (List<String>) -> Unit) {
    var query by remember { mutableStateOf("") }
    val chosen = remember { mutableStateListOf<String>().also { it.addAll(start) } }
    var made by remember { mutableStateOf(listOf<String>()) }
    var busy by remember { mutableStateOf(false) }
    var problem by remember { mutableStateOf("") }
    val scope = rememberCoroutineScope()
    fun isOn(name: String) = chosen.any { it.equals(name, ignoreCase = true) }
    val names = (info.names + start + made).distinctBy { it.lowercase() }.sortedBy { it.lowercase() }
    val q = query.trim()
    val shown = if (q.isEmpty()) names else names.filter { it.contains(q, ignoreCase = true) }
    val canMake = info.canCreate && q.isNotEmpty() && names.none { it.equals(q, ignoreCase = true) }
    val changed = start.size != chosen.size || start.any { s -> !isOn(s) }

    fun save() {
        busy = true
        problem = ""
        scope.launch {
            try {
                var now = start
                val toAdd = chosen.filter { c -> start.none { it.equals(c, ignoreCase = true) } }
                val toRemove = start.filter { s -> !isOn(s) }
                withContext(Dispatchers.IO) {
                    for (name in toAdd) {
                        if (info.names.none { it.equals(name, ignoreCase = true) }) {
                            try { api.createTag(mail.accountId, name) } catch (e: ApiException) { if (e.code == 401) throw e }
                        }
                        now = api.setTag(mail, name, true)
                    }
                    for (name in toRemove) now = api.setTag(mail, name, false)
                }
                onSaved(now)
            } catch (e: ApiException) {
                problem = e.message ?: "The tags did not save. Please try again."
            } catch (e: Exception) {
                problem = "The tags did not save. Please try again."
            } finally {
                busy = false
            }
        }
    }

    Dialog(onDismissRequest = { if (!busy) onClose() }, properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        Column(Modifier.fillMaxSize().background(Navy).systemBarsPadding().imePadding()) {
            Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                TextButton(onClick = onClose, enabled = !busy) { Text("Close", color = Blue, fontSize = 16.sp) }
                Text("Tags", color = Ink, fontSize = 20.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(start = 8.dp))
            }
            OutlinedTextField(
                value = query, onValueChange = { query = it }, singleLine = true, placeholder = { Text("Search tags") },
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp),
            )
            LazyColumn(Modifier.weight(1f).fillMaxWidth()) {
                if (canMake) item {
                    Row(
                        Modifier.fillMaxWidth().clickable { made = made + q; chosen.add(q); query = "" }.padding(horizontal = 20.dp, vertical = 14.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) { Text("Make the tag \"" + q + "\"", color = Blue, fontSize = 16.sp) }
                    HorizontalDivider(color = Line)
                }
                items(shown, key = { it.lowercase() }) { name ->
                    Row(
                        Modifier.fillMaxWidth().clickable {
                            val at = chosen.indexOfFirst { it.equals(name, ignoreCase = true) }
                            if (at >= 0) chosen.removeAt(at) else chosen.add(name)
                        }.padding(horizontal = 20.dp, vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Checkbox(checked = isOn(name), onCheckedChange = null)
                        Text(name, color = Ink, fontSize = 16.sp, modifier = Modifier.padding(start = 14.dp))
                    }
                    HorizontalDivider(color = Line)
                }
                if (shown.isEmpty() && !canMake) item {
                    Text(if (q.isEmpty()) "There are no tags yet." else "No tags match that.", color = Muted, fontSize = 16.sp, modifier = Modifier.padding(24.dp))
                }
            }
            if (problem.isNotEmpty()) Text(problem, color = Red, fontSize = 14.sp, modifier = Modifier.padding(horizontal = 20.dp, vertical = 6.dp))
            Row(Modifier.fillMaxWidth().background(Panel).padding(horizontal = 20.dp, vertical = 12.dp)) {
                Button(onClick = { save() }, enabled = !busy && changed, modifier = Modifier.fillMaxWidth().height(52.dp), shape = RoundedCornerShape(14.dp)) {
                    if (busy) CircularProgressIndicator(Modifier.size(22.dp), color = Ink, strokeWidth = 2.dp)
                    else Text(if (changed) "Save tags" else "Nothing changed", fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
                }
            }
        }
    }
}

/** Full screen: search, then tap a tag to show only the emails that have it. [counts] pairs each tag with how many emails carry it. */
@Composable
internal fun TagFilterScreen(counts: List<Pair<String, Int>>, current: String?, onPick: (String?) -> Unit, onClose: () -> Unit) {
    var query by remember { mutableStateOf("") }
    val q = query.trim()
    val shown = if (q.isEmpty()) counts else counts.filter { it.first.contains(q, ignoreCase = true) }
    Dialog(onDismissRequest = onClose, properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        Column(Modifier.fillMaxSize().background(Navy).systemBarsPadding().imePadding()) {
            Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                TextButton(onClick = onClose) { Text("Close", color = Blue, fontSize = 16.sp) }
                Text("Tags", color = Ink, fontSize = 20.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f).padding(start = 8.dp))
                if (current != null) TextButton(onClick = { onPick(null) }) { Text("Clear filter", color = Blue, fontSize = 16.sp) }
            }
            OutlinedTextField(
                value = query, onValueChange = { query = it }, singleLine = true, placeholder = { Text("Search tags") },
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp),
            )
            LazyColumn(Modifier.weight(1f).fillMaxWidth()) {
                items(shown, key = { it.first.lowercase() }) { (name, count) ->
                    val on = current != null && current.equals(name, ignoreCase = true)
                    Row(
                        Modifier.fillMaxWidth().clickable { onPick(name) }.padding(horizontal = 20.dp, vertical = 16.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text("# " + name, color = if (on) Blue else Ink, fontSize = 16.sp, fontWeight = if (on) FontWeight.SemiBold else FontWeight.Normal, modifier = Modifier.weight(1f))
                        Text(if (count == 1) "1 email" else "$count emails", color = Muted, fontSize = 14.sp)
                        if (on) Text("  ✓", color = Blue, fontSize = 16.sp)
                    }
                    HorizontalDivider(color = Line)
                }
                if (shown.isEmpty()) item {
                    Text(if (counts.isEmpty()) "No emails here have tags." else "No tags match that.", color = Muted, fontSize = 16.sp, modifier = Modifier.padding(24.dp))
                }
            }
        }
    }
}

internal fun sizeText(bytes: Long): String = when {
    bytes <= 0L -> ""
    bytes < 1024L * 1024L -> ((bytes + 1023L) / 1024L).toString() + " KB"
    else -> String.format("%.1f MB", bytes / 1048576.0)
}

private val linkPattern = Regex("""https?://[^\s<>"')\]]+""")

internal fun hostOf(link: String): String? = try { URI(link.trimEnd('.', ',', ';', ':', '!', '?')).host?.lowercase() } catch (e: Exception) { null }

internal fun looksOdd(link: String, host: String): Boolean =
    link.startsWith("http://", ignoreCase = true) || host.startsWith("xn--") || host.split('.').all { p -> p.isNotEmpty() && p.all { it.isDigit() } }

/** The links in the email's text, each shown with where it really goes. Nothing opens until the person says so. */
@Composable
internal fun LinksSection(text: String) {
    val context = LocalContext.current
    val links = remember(text) {
        linkPattern.findAll(text).map { it.value.trimEnd('.', ',', ';', ':', '!', '?') }.distinct().filter { hostOf(it) != null }.take(12).toList()
    }
    var asking by remember(text) { mutableStateOf<String?>(null) }
    if (links.isEmpty()) return
    Column(Modifier.fillMaxWidth().padding(top = 18.dp)) {
        Text("Links in this email", color = Muted, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
        links.forEach { link ->
            val host = hostOf(link) ?: return@forEach
            TextButton(onClick = { asking = link }, modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.fillMaxWidth()) {
                    Text("Goes to " + host, color = Blue, fontSize = 16.sp)
                    Text(link, color = Muted, fontSize = 12.sp, maxLines = 1, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
                }
            }
        }
    }
    val target = asking
    if (target != null) LinkConfirm(target) { asking = null }
}

/** Asks before a link opens, naming the site it really goes to. */
@Composable
internal fun LinkConfirm(target: String, onDone: () -> Unit) {
    val context = LocalContext.current
    val host = hostOf(target) ?: ""
    AlertDialog(
        onDismissRequest = onDone,
        title = { Text("Open this link?") },
        text = {
            Column {
                if (host.isNotEmpty()) Text("It goes to " + host + ".", fontWeight = FontWeight.SemiBold)
                // The whole address, exactly as it is in the email, so you know what you are opening. It wraps and scrolls if it is very long.
                androidx.compose.foundation.text.selection.SelectionContainer {
                    Text(
                        target, fontSize = 13.sp, fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace,
                        modifier = Modifier.padding(top = if (host.isNotEmpty()) 8.dp else 0.dp).heightIn(max = 220.dp).verticalScroll(rememberScrollState()),
                    )
                }
                if (host.isNotEmpty() && looksOdd(target, host)) Text("This one looks unusual. Only open it if you are expecting it.", modifier = Modifier.padding(top = 8.dp))
                Text("Check that the address is the one you expect before you carry on.", modifier = Modifier.padding(top = 8.dp))
            }
        },
        confirmButton = {
            TextButton(onClick = {
                onDone()
                try { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(target)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) } catch (e: Exception) { }
            }) { Text("Open", color = Blue) }
        },
        dismissButton = { TextButton(onClick = onDone) { Text("Cancel", color = Blue) } },
    )
}

