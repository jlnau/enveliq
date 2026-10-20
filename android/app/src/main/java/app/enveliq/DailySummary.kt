package app.enveliq

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.clickable
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.foundation.layout.Box
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

// The daily summary: one special item at the top of the inbox, once a day. It is not an email from a provider. It opens and reads like an
// email, with the AI's short summaries organised (what needs you today first, then by kind), and each line opens the original in Enveliq.
// Making it sends no alert. Nothing is hidden or marked reviewed by it.

private fun dayWords(createdAt: Double): String = try {
    java.time.Instant.ofEpochSecond(createdAt.toLong()).atZone(java.time.ZoneId.systemDefault())
        .format(java.time.format.DateTimeFormatter.ofPattern("EEEE d MMMM", java.util.Locale.getDefault()))
} catch (e: Exception) { "" }

/** The special row in the inbox list. */
@Composable
internal fun DigestCard(row: DigestRow, onClick: () -> Unit) {
    Surface(
        color = Panel, shape = RoundedCornerShape(14.dp), border = BorderStroke(1.dp, Blue),
        modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp).clickable(onClick = onClick),
    ) {
        Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.background(Blue, RoundedCornerShape(50)).padding(horizontal = 10.dp, vertical = 3.dp)) { Text("Summary", color = Navy, fontSize = 12.sp, fontWeight = FontWeight.Bold) }
            Column(Modifier.weight(1f).padding(horizontal = 12.dp)) {
                Text("Daily summary: " + dayWords(row.createdAt), color = Ink, fontSize = 16.sp, fontWeight = if (row.read) FontWeight.Normal else FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(
                    "${row.count} email${if (row.count == 1) "" else "s"}" + (if (row.urgent > 0) ", ${row.urgent} that need${if (row.urgent == 1) "s" else ""} you today" else ""),
                    color = Muted, fontSize = 13.sp,
                )
            }
            if (!row.read) Box(Modifier.size(9.dp).background(Blue, CircleShape))
        }
    }
}

/** A full-screen summary. [onOpenMail] opens the original email in Enveliq (the screen closes first). */
@Composable
internal fun DigestScreen(api: EnveliqApi, id: String, onBack: () -> Unit, onOpenMail: (String, String) -> Unit, onChanged: () -> Unit) {
    val scope = rememberCoroutineScope()
    var digest by remember { mutableStateOf<Digest?>(null) }
    var err by remember { mutableStateOf("") }
    var askDelete by remember { mutableStateOf(false) }
    LaunchedEffect(id) {
        try {
            digest = withContext(Dispatchers.IO) { api.digest(id) }
            withContext(Dispatchers.IO) { api.readDigest(id) }
            onChanged()
        } catch (e: ApiException) { err = e.message ?: "That summary is not there any more." }
        catch (e: Exception) { err = "Could not open the summary. Check your connection." }
    }
    BackHandler(onBack = onBack)
    Column(Modifier.fillMaxSize().background(Navy)) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = onBack) { Text("‹ Back", color = Blue, fontSize = 16.sp) }
            Column(Modifier.weight(1f)) {
                Text("Your daily summary", color = Ink, fontSize = 20.sp, fontWeight = FontWeight.SemiBold)
                digest?.let { Text(dayWords(it.createdAt), color = Muted, fontSize = 13.sp) }
            }
        }
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 16.dp)) {
            val d = digest
            if (d == null) {
                Text(err.ifEmpty { "Loading…" }, color = if (err.isEmpty()) Muted else Red, fontSize = 15.sp, modifier = Modifier.padding(top = 12.dp))
            } else {
                Text("Written by AI from your email summaries. Nothing was hidden or marked as reviewed: every email is still in your inbox.", color = Muted, fontSize = 13.sp, modifier = Modifier.padding(bottom = 8.dp))
                val groups = linkedMapOf<String, List<DigestItem>>()
                d.items.filter { it.urgent }.takeIf { it.isNotEmpty() }?.let { groups["Needs you today"] = it }
                d.items.filter { !it.urgent }.groupBy { it.category }.toSortedMap().forEach { (k, v) -> groups[k] = v }
                groups.forEach { (title, list) ->
                    Text(title, color = Ink, fontSize = 15.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 14.dp, bottom = 6.dp))
                    list.forEach { i ->
                        Card(Modifier.padding(bottom = 8.dp)) {
                            Text(i.sender.ifBlank { "Unknown sender" }, color = Muted, fontSize = 13.sp)
                            Text(i.subject.ifBlank { "(no subject)" }, color = Ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                            if (i.reason.isNotBlank()) Text("Why today: " + i.reason, color = Blue, fontSize = 13.sp, modifier = Modifier.padding(top = 2.dp))
                            Text(i.summary, color = Ink, fontSize = 15.sp, lineHeight = 21.sp, modifier = Modifier.padding(top = 4.dp))
                            TextButton(onClick = { onOpenMail(i.accountId, i.messageId) }) { Text("Open this email", color = Blue, fontSize = 15.sp) }
                        }
                    }
                }
                Box(Modifier.size(16.dp))
            }
        }
        Row(Modifier.fillMaxWidth().background(Panel).padding(horizontal = 16.dp, vertical = 12.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            OutlinedButton(onClick = { askDelete = true }, enabled = digest != null, modifier = Modifier.height(52.dp), shape = RoundedCornerShape(14.dp), border = BorderStroke(1.dp, Line)) { Text("Delete this summary", color = Red) }
            Button(onClick = onBack, modifier = Modifier.weight(1f).height(52.dp), shape = RoundedCornerShape(14.dp)) { Text("Close", fontSize = 17.sp, fontWeight = FontWeight.SemiBold) }
        }
    }
    if (askDelete) {
        androidx.compose.material3.AlertDialog(
            onDismissRequest = { askDelete = false }, containerColor = Panel,
            title = { Text("Delete this summary?", color = Ink) },
            text = { Text("Only the summary goes. Your email is not touched.", color = Muted) },
            confirmButton = {
                TextButton(onClick = {
                    askDelete = false
                    scope.launch {
                        try { withContext(Dispatchers.IO) { api.deleteDigest(id) } } catch (_: Exception) { }
                        onChanged(); onBack()
                    }
                }) { Text("Delete", color = Red) }
            },
            dismissButton = { TextButton(onClick = { askDelete = false }) { Text("Keep it", color = Muted) } },
        )
    }
}

/** Settings, Notifications: the switch for the daily summary in the inbox, and a button to see today's now. */
@Composable
internal fun DigestSetting(api: EnveliqApi) {
    val scope = rememberCoroutineScope()
    var on by remember { mutableStateOf<Boolean?>(null) }
    var msg by remember { mutableStateOf("") }
    LaunchedEffect(Unit) { on = try { withContext(Dispatchers.IO) { api.digestInboxOn() } } catch (e: Exception) { null } }
    val v = on ?: return
    Column(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp)) {
        SwitchLine(
            "Put a daily summary in my inbox",
            "The AI picks out email that needs you today, and that still alerts you at once. Everything else is gathered into one summary at your daily summary time, at the top of your inbox. The summary makes no sound or alert, and nothing is hidden.",
            v,
        ) { want ->
            msg = ""
            scope.launch {
                try { withContext(Dispatchers.IO) { api.setDigestInbox(want) }; on = want }
                catch (e: ApiException) { msg = e.message ?: "That did not save." }
                catch (e: Exception) { msg = "That did not save. Check your connection." }
            }
        }
        if (v) OutlinedButton(
            onClick = {
                msg = ""
                scope.launch {
                    try { msg = if (withContext(Dispatchers.IO) { api.makeDigestNow() }) "Done. It is at the top of your inbox." else "Nothing new to put in a summary yet." }
                    catch (e: ApiException) { msg = e.message ?: "That did not work." }
                    catch (e: Exception) { msg = "That did not work. Check your connection." }
                }
            },
            shape = RoundedCornerShape(12.dp), border = BorderStroke(1.dp, Line), modifier = Modifier.padding(top = 6.dp),
        ) { Text("Make today's summary now", color = Blue) }
        if (msg.isNotEmpty()) Text(msg, color = Muted, fontSize = 13.sp, modifier = Modifier.padding(top = 4.dp))
    }
}
