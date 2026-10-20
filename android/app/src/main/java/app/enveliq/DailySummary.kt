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
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.Icon
import androidx.compose.foundation.layout.RowScope
import androidx.compose.ui.graphics.Color
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

// The daily summary. Email that can wait is held for it: it is not in the inbox, it is listed under "Held for summary", and it is in the summary
// at the top of the inbox straight away. Each email has four icon buttons: reviewed, archive, bin, and take it out of the summary (back to the
// inbox). "Done with summary" sends anything still in it back to the inbox. After 7 days the server returns held email to the inbox by itself.

/** The special row at the top of the inbox. */
@Composable
internal fun DigestCard(info: SummaryInfo, onClick: () -> Unit) {
    Surface(
        color = Panel, shape = RoundedCornerShape(14.dp), border = BorderStroke(1.dp, Blue),
        modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp).clickable(onClick = onClick),
    ) {
        Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.background(Blue, RoundedCornerShape(50)).padding(horizontal = 10.dp, vertical = 3.dp)) { Text("Summary", color = Navy, fontSize = 12.sp, fontWeight = FontWeight.Bold) }
            Column(Modifier.weight(1f).padding(horizontal = 12.dp)) {
                Text("Your daily summary", color = Ink, fontSize = 16.sp, fontWeight = if (info.unread > 0) FontWeight.SemiBold else FontWeight.Normal, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text("${info.count} email${if (info.count == 1) "" else "s"} waiting", color = Muted, fontSize = 13.sp)
            }
            if (info.unread > 0) Box(Modifier.size(9.dp).background(Blue, CircleShape))
        }
    }
}

@Composable
private fun RowScope.SummaryIcon(label: String, tint: Color, container: Color, onClick: () -> Unit, icon: @Composable () -> Unit) =
    BarIcon(label, tint, container, onClick, icon)

/** The full-screen summary. [onOpenMail] opens the original email in Enveliq (the screen closes first). [onChanged] tells the inbox to reload. */
@Composable
internal fun DigestScreen(api: EnveliqApi, onBack: () -> Unit, onOpenMail: (String, String) -> Unit, onChanged: () -> Unit) {
    val scope = rememberCoroutineScope()
    val items = remember { androidx.compose.runtime.mutableStateListOf<DigestItem>() }
    var loaded by remember { mutableStateOf(false) }
    var err by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) {
        try {
            val info = withContext(Dispatchers.IO) { api.summary() }
            items.clear(); items.addAll(info.items); loaded = true
            withContext(Dispatchers.IO) { api.summarySeen() }
            onChanged()
        } catch (e: ApiException) { err = e.message ?: "Could not open the summary." }
        catch (e: Exception) { err = "Could not open the summary. Check your connection." }
    }
    fun finish() {
        if (busy) return
        busy = true
        scope.launch {
            try { withContext(Dispatchers.IO) { api.summaryDone() } } catch (_: Exception) { }
            onChanged(); onBack()
        }
    }
    fun act(i: DigestItem, what: suspend () -> Unit) {
        if (busy) return
        busy = true
        scope.launch {
            try {
                withContext(Dispatchers.IO) { what() }
                items.remove(i)
                onChanged()
                if (items.isEmpty()) onBack()
            } catch (e: ApiException) { err = e.message ?: "That did not work." }
            catch (e: Exception) { err = "That did not work. Check your connection." }
            busy = false
        }
    }
    BackHandler(onBack = onBack)
    Column(Modifier.fillMaxSize().background(Navy)) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = onBack) { Text("‹ Close", color = Blue, fontSize = 16.sp) }
            Text("Your daily summary", color = Ink, fontSize = 20.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
            Button(onClick = { finish() }, enabled = !busy, shape = RoundedCornerShape(12.dp)) { Text("Done with summary", fontSize = 14.sp) }
        }
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 16.dp)) {
            if (!loaded) {
                Text(err.ifEmpty { "Loading…" }, color = if (err.isEmpty()) Muted else Red, fontSize = 15.sp, modifier = Modifier.padding(top = 12.dp))
            } else {
                Text("Written by AI from your email summaries. These emails are not in your inbox while they are here. Anything you leave in the summary goes back to your inbox when you press Done with summary, or after 7 days.", color = Muted, fontSize = 13.sp, modifier = Modifier.padding(bottom = 8.dp))
                if (err.isNotEmpty()) Text(err, color = Red, fontSize = 14.sp, modifier = Modifier.padding(bottom = 6.dp))
                val groups = items.groupBy { it.category }.toSortedMap()
                groups.forEach { (title, list) ->
                    Text(title, color = Ink, fontSize = 15.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 14.dp, bottom = 6.dp))
                    list.forEach { i ->
                        Card(Modifier.padding(bottom = 8.dp)) {
                            Text(i.sender.ifBlank { "Unknown sender" }, color = Muted, fontSize = 13.sp)
                            Text(i.subject.ifBlank { "(no subject)" }, color = Ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                            Text(i.summary, color = Ink, fontSize = 15.sp, lineHeight = 21.sp, modifier = Modifier.padding(top = 4.dp))
                            TextButton(onClick = { onOpenMail(i.accountId, i.messageId) }) { Text("Open this email", color = Blue, fontSize = 15.sp) }
                            Row(Modifier.fillMaxWidth().padding(top = 2.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                SummaryIcon("Reviewed", Green, Color(0xFF16382B), { act(i) { api.resolveIds(i.accountId, i.messageId, Outcome.Reviewed) } }) { Icon(Icons.Filled.Check, contentDescription = null, tint = Green) }
                                SummaryIcon("Archive", Color(0xFF8DB8FF), Color(0xFF173056), { act(i) { api.resolveIds(i.accountId, i.messageId, Outcome.Archived) } }) { ArchiveIcon(Color(0xFF8DB8FF)) }
                                SummaryIcon("Bin", Red, Color(0xFF3A1D22), { act(i) { api.resolveIds(i.accountId, i.messageId, Outcome.Binned) } }) { Icon(Icons.Filled.Delete, contentDescription = null, tint = Red) }
                                SummaryIcon("Take out of the summary and put back in my inbox", Ink, PanelHigh, { act(i) { api.summaryRemove(i.accountId, i.messageId) } }) { Icon(Icons.Filled.ArrowBack, contentDescription = null, tint = Ink) }
                            }
                        }
                    }
                }
                Box(Modifier.size(16.dp))
            }
        }
        Row(Modifier.fillMaxWidth().background(Panel).padding(horizontal = 16.dp, vertical = 12.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            OutlinedButton(onClick = onBack, modifier = Modifier.height(52.dp), shape = RoundedCornerShape(14.dp), border = BorderStroke(1.dp, Line)) { Text("Close", color = Ink) }
            Button(onClick = { finish() }, enabled = !busy, modifier = Modifier.weight(1f).height(52.dp), shape = RoundedCornerShape(14.dp)) { Text("Done with summary", fontSize = 17.sp, fontWeight = FontWeight.SemiBold) }
        }
    }
}

/** Settings, Notifications: the switch for holding email for the daily summary. */
@Composable
internal fun DigestSetting(api: EnveliqApi) {
    val scope = rememberCoroutineScope()
    var on by remember { mutableStateOf<Boolean?>(null) }
    var msg by remember { mutableStateOf("") }
    LaunchedEffect(Unit) { on = try { withContext(Dispatchers.IO) { api.digestInboxOn() } } catch (e: Exception) { null } }
    val v = on ?: return
    Column(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp)) {
        SwitchLine(
            "Hold email for the daily summary",
            "Email that can wait is held out of your inbox and gathered into one summary at the top of it, and under Held for summary in the menu. Email that needs you today, or is from someone important, stays in your inbox and alerts you at once. You get one alert a day to open the summary.",
            v,
        ) { want ->
            msg = ""
            scope.launch {
                try { withContext(Dispatchers.IO) { api.setDigestInbox(want) }; on = want }
                catch (e: ApiException) { msg = e.message ?: "That did not save." }
                catch (e: Exception) { msg = "That did not save. Check your connection." }
            }
        }
        if (msg.isNotEmpty()) Text(msg, color = Muted, fontSize = 13.sp, modifier = Modifier.padding(top = 4.dp))
    }
}
