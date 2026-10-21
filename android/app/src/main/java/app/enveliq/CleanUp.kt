package app.enveliq

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshots.SnapshotStateList
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.compose.foundation.BorderStroke
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

// Clean up: the mailing lists that fill the inbox. Same server route as the website. Enveliq only reads who each email is from, when, and
// whether it has an unsubscribe link. The Unsubscribe button opens the sender's own page in the browser after the usual link check (or a
// mail to the sender's address); Enveliq never opens it itself. Nothing is deleted: Archive moves email and marks it read, and Undo lasts ten minutes.

private fun agoWords(now: Long, then: Long): String {
    if (then <= 0) return ""
    val d = ((now - then) / 86400).toInt()
    return if (d <= 0) "today" else if (d == 1) "yesterday" else "$d days ago"
}

@Composable
internal fun CleanUpPage(api: EnveliqApi, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    var data by remember { mutableStateOf<CleanUp?>(null) }
    var err by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(true) }
    var note by remember { mutableStateOf("") }
    var stepping by remember { mutableStateOf(true) }                      // one at a time is the calm default on a phone
    val skipped: SnapshotStateList<String> = remember { mutableStateListOf() }
    val unsubbed: SnapshotStateList<String> = remember { mutableStateListOf() }
    val ruled: SnapshotStateList<String> = remember { mutableStateListOf() }
    var confirm by remember { mutableStateOf<Sender?>(null) }
    var link by remember { mutableStateOf<String?>(null) }
    var undo by remember { mutableStateOf("") }
    var undoText by remember { mutableStateOf("") }

    fun run(block: () -> CleanUp, after: (CleanUp) -> Unit = {}) {
        scope.launch {
            busy = true; err = ""
            try {
                val r = withContext(Dispatchers.IO) { block() }
                data = r
                undo = r.undo                                              // the server says whether an Undo is still on offer
                undoText = if (r.undoCount > 0) "Archived ${r.undoCount} from ${r.undoName.ifBlank { "that sender" }}." else "Archived."
                note = r.toast
                after(r)
            } catch (e: ApiException) {
                err = e.message ?: "That did not work. Please try again."
                if (err.contains("not on the list any more", ignoreCase = true)) run({ api.senders(true) })
            } catch (e: Exception) {
                err = "That did not work. Check your connection."
            }
            busy = false
        }
    }
    androidx.compose.runtime.LaunchedEffect(Unit) { run({ api.senders() }) }

    // Back closes the confirmation first, then the page.
    androidx.activity.compose.BackHandler(enabled = confirm != null) { confirm = null }

    SubPage("Clean up", "Quiet the mailing lists you do not need", onBack = onBack, trailing = {
        TextButton(onClick = { skipped.clear(); run({ api.senders(true) }) }, enabled = !busy) { Text("Look again", color = Blue) }
    }) {
        val d = data
        val left = d?.senders?.filter { it.id !in skipped } ?: emptyList()
        LazyColumn(Modifier.fillMaxSize().padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item { Text("These are the mailing lists that wrote to you in the last ${d?.days ?: 60} days. Nothing is deleted.", color = Muted, fontSize = 14.sp, lineHeight = 20.sp) }
            if (busy) item { Text(if (d == null) "Looking through the last 60 days of your mail…" else "One moment…", color = Muted, fontSize = 14.sp) }
            if (err.isNotEmpty()) item { Text(err, color = Red, fontSize = 15.sp) }
            d?.problems?.forEach { p -> item { Text(p, color = Amber, fontSize = 14.sp) } }
            if (note.isNotEmpty()) item { Text(note, color = Amber, fontSize = 14.sp) }
            if (undo.isNotEmpty()) item {
                Card {
                    Text(undoText, color = Ink, fontSize = 15.sp)
                    TextButton(onClick = {
                        val t = undo
                        scope.launch {
                            try { val n = withContext(Dispatchers.IO) { api.undoClean(t) }; note = "Put back $n."; undo = ""; run({ api.senders(true) }) }
                            catch (e: Exception) { note = "That could not be undone. It may be too late."; undo = "" }
                        }
                    }) { Text("Undo", color = Blue) }
                }
            }
            if (d != null && d.senders.isEmpty() && !busy) item { Empty("Nothing to clean up. No mailing lists are filling your inbox.") }
            if (d != null && d.senders.isNotEmpty()) item {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    OutlinedButton(onClick = { stepping = !stepping }, shape = RoundedCornerShape(12.dp), border = BorderStroke(1.dp, Line)) {
                        Text(if (stepping) "See the whole list" else "Step through them", color = Ink, fontSize = 14.sp)
                    }
                    if (stepping) Text(if (left.isEmpty()) "  That was all of them" else "  ${d.senders.size - left.size + 1} of ${d.senders.size}", color = Muted, fontSize = 13.sp)
                }
            }
            if (d != null) {
                val shown = if (stepping) left.take(1) else d.senders
                items(shown, key = { it.id }) { s ->
                    SenderCard(s, d, ruled.contains(s.id), unsubbed.contains(s.id), busy,
                        onUnsub = {
                            if (s.unsubUrl != null) link = s.unsubUrl
                            else try {
                                val uri = android.net.Uri.parse("mailto:" + (s.unsubMailto ?: "") + if (s.unsubSubject.isNotBlank()) "?subject=" + android.net.Uri.encode(s.unsubSubject) else "")
                                context.startActivity(android.content.Intent(android.content.Intent.ACTION_SENDTO, uri).addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK))
                            } catch (e: Exception) { }
                            unsubbed.add(s.id)
                        },
                        onNotYet = { unsubbed.remove(s.id) },
                        onArchive = { confirm = s },
                        onAlways = { run({ api.alwaysArchive(s.id) }) { ruled.add(s.id); note = "From now on, new email from them is archived. You can change this in Mail rules." } },
                        onKeep = { run({ api.keepSender(s.id) }) { note = "Kept. They will not be listed again." } },
                    )
                }
                if (stepping && left.isNotEmpty()) item { OutlinedButton(onClick = { skipped.add(left[0].id) }, modifier = Modifier.fillMaxWidth().height(48.dp), shape = RoundedCornerShape(12.dp), border = BorderStroke(1.dp, Line)) { Text("Skip for now", color = Ink) } }
                if (d.kept > 0) item { TextButton(onClick = { run({ api.showKeptSenders() }) }) { Text("Show the ${d.kept} you kept again", color = Blue) } }
                item { Text("Enveliq only reads who each email is from, when, and whether it has an unsubscribe link. It keeps nothing about the senders except the ones you chose to keep.", color = Muted, fontSize = 12.sp, lineHeight = 17.sp, modifier = Modifier.padding(bottom = 24.dp)) }
            }
        }
    }

    link?.let { LinkConfirm(it) { link = null } }

    confirm?.let { s ->
        // Full screen, with Close at the top and the buttons at the bottom, so they can always be reached.
        Dialog(onDismissRequest = { confirm = null }, properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
            Column(Modifier.fillMaxSize().background(Navy).systemBarsPadding().imePadding()) {
                Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text("Archive ${s.name}'s email?", color = Ink, fontSize = 18.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f).padding(start = 8.dp))
                    TextButton(onClick = { confirm = null }) { Text("Close", color = Blue, fontSize = 16.sp) }
                }
                Column(Modifier.weight(1f).fillMaxWidth().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text("All their email in your inbox moves to your Archive and is marked as read (${s.count} from the last ${data?.days ?: 60} days). Nothing is deleted.", color = Ink, fontSize = 16.sp, lineHeight = 23.sp)
                    Text("Email that has an open task stays in your inbox. You can undo this for 10 minutes.", color = Muted, fontSize = 15.sp, lineHeight = 22.sp)
                }
                Row(Modifier.fillMaxWidth().padding(16.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { val id = s.id; confirm = null; unsubbed.remove(id); run({ api.archiveSender(id) }) }, modifier = Modifier.weight(1f).height(48.dp), shape = RoundedCornerShape(12.dp)) {
                        Text("Archive ${s.count} ${if (s.count == 1) "email" else "emails"}")
                    }
                    OutlinedButton(onClick = { confirm = null }, modifier = Modifier.weight(1f).height(48.dp), shape = RoundedCornerShape(12.dp), border = BorderStroke(1.dp, Line)) { Text("Cancel", color = Ink) }
                }
            }
        }
    }
}

@Composable
private fun SenderCard(s: Sender, d: CleanUp, ruled: Boolean, asked: Boolean, busy: Boolean, onUnsub: () -> Unit, onNotYet: () -> Unit, onArchive: () -> Unit, onAlways: () -> Unit, onKeep: () -> Unit) {
    Card {
        Text(s.name, color = Ink, fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
        Text(s.address, color = Muted, fontSize = 13.sp)
        Text("${s.count} ${if (s.count == 1) "email" else "emails"} · you opened ${s.opened} · last ${agoWords(d.now, s.last)}" + if (d.mailboxes > 1) " · " + s.mailbox else "", color = Muted, fontSize = 14.sp, modifier = Modifier.padding(top = 4.dp))
        if (s.flagged) Text("Something about this sender looks odd, so there is no Unsubscribe button. Unsubscribing from a fake tells them your address is real.", color = Amber, fontSize = 13.sp, lineHeight = 18.sp, modifier = Modifier.padding(top = 6.dp))
        if (ruled) Text("New email from them is now archived for you. You can change this in Mail rules.", color = Muted, fontSize = 13.sp, modifier = Modifier.padding(top = 6.dp))
        if (asked) Column(Modifier.padding(top = 8.dp)) {
            Text("Did that work? If it did, you can clear out what is already in your inbox.", color = Ink, fontSize = 14.sp)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                TextButton(onClick = onArchive) { Text("Yes, clear them out", color = Blue) }
                TextButton(onClick = onNotYet) { Text("Not yet", color = Muted) }
            }
        }
        Column(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            if (!s.flagged && (s.unsubUrl != null || s.unsubMailto != null)) OutlinedButton(onClick = onUnsub, modifier = Modifier.fillMaxWidth().height(48.dp), shape = RoundedCornerShape(12.dp), border = BorderStroke(1.dp, Line)) { Text("Unsubscribe", color = Ink) }
            Button(onClick = onArchive, enabled = !busy, modifier = Modifier.fillMaxWidth().height(48.dp), shape = RoundedCornerShape(12.dp)) { Text("Archive what's here") }
            if (!ruled) OutlinedButton(onClick = onAlways, enabled = !busy, modifier = Modifier.fillMaxWidth().height(48.dp), shape = RoundedCornerShape(12.dp), border = BorderStroke(1.dp, Line)) { Text("Always archive new ones", color = Ink) }
            OutlinedButton(onClick = onKeep, enabled = !busy, modifier = Modifier.fillMaxWidth().height(48.dp), shape = RoundedCornerShape(12.dp), border = BorderStroke(1.dp, Line)) { Text("Keep", color = Ink) }
        }
    }
}
