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
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

// Pages that bring the website's Away reply, Saved replies, Subscriptions, Tags and Ask Enveliq to the phone. Each one uses the
// website's own route, so the server still decides what the signed-in person may see or change.

private fun pickDay(context: android.content.Context, current: String, onPicked: (String) -> Unit) {
    val now = java.util.Calendar.getInstance()
    val parts = current.split("-")
    if (parts.size == 3) {
        parts[0].toIntOrNull()?.let { y -> parts[1].toIntOrNull()?.let { m -> parts[2].toIntOrNull()?.let { d -> now.set(y, m - 1, d) } } }
    }
    val dialog = android.app.DatePickerDialog(context, { _, y, m, d -> onPicked(String.format(java.util.Locale.ROOT, "%04d-%02d-%02d", y, m + 1, d)) },
        now.get(java.util.Calendar.YEAR), now.get(java.util.Calendar.MONTH), now.get(java.util.Calendar.DAY_OF_MONTH))
    dialog.show()
}

/** Away reply: the same words and dates as the website. Saved on your own server. */
@Composable
internal fun AwayPage(api: EnveliqApi, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    var loaded by remember { mutableStateOf(false) }
    var enabled by remember { mutableStateOf(false) }
    var start by remember { mutableStateOf("") }
    var end by remember { mutableStateOf("") }
    var body by remember { mutableStateOf("") }
    var note by remember { mutableStateOf("") }
    var state by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) {
        try {
            val a = withContext(Dispatchers.IO) { api.away() }
            enabled = a.enabled; start = a.start; end = a.end; body = a.body; state = a.state
            if (start.isBlank()) start = a.today
            if (end.isBlank()) end = a.today
            loaded = true
        } catch (e: ApiException) { note = e.message ?: "Could not load this." }
        catch (e: Exception) { note = "Could not load this. Check your connection." }
    }
    SubPage("Away reply", "Answers new email for you while you are away", onBack = onBack) {
        if (!loaded) {
            if (note.isEmpty()) Box0 { CircularProgressIndicator(color = Blue) } else Text(note, color = Red, modifier = Modifier.padding(20.dp))
        } else Column(Modifier.fillMaxSize().imePadding()) {
            Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Card {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text("Send an away reply", color = Ink, fontSize = 16.sp)
                            Text("Between the two days below", color = Muted, fontSize = 13.sp)
                        }
                        Switch(checked = enabled, onCheckedChange = { enabled = it })
                    }
                }
                Card {
                    Row(Modifier.fillMaxWidth().clickable { pickDay(context, start) { start = it } }.padding(vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text("First day", color = Ink, fontSize = 16.sp, modifier = Modifier.weight(1f)); Text(start, color = Muted, fontSize = 15.sp)
                    }
                    Row(Modifier.fillMaxWidth().clickable { pickDay(context, end) { end = it } }.padding(vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text("Last day", color = Ink, fontSize = 16.sp, modifier = Modifier.weight(1f)); Text(end, color = Muted, fontSize = 15.sp)
                    }
                }
                Text("What it says", color = Muted, fontSize = 13.sp)
                OutlinedTextField(value = body, onValueChange = { body = it }, modifier = Modifier.fillMaxWidth().height(160.dp), placeholder = { Text("Thanks for your email. I am away until…") })
                if (state.isNotBlank()) Text("Right now: " + state, color = Muted, fontSize = 13.sp)
                if (note.isNotEmpty()) Text(note, color = Amber, fontSize = 14.sp)
                Text("The days use your own time zone. An away reply answers each person once and never answers mailing lists or automatic email.", color = Muted, fontSize = 12.sp)
            }
            Row(Modifier.fillMaxWidth().padding(16.dp)) {
                Button(onClick = {
                    scope.launch {
                        busy = true; note = ""
                        try {
                            val a = withContext(Dispatchers.IO) { api.saveAway(enabled, start, end, body) }
                            enabled = a.enabled; state = a.state; note = "Saved."
                        } catch (e: ApiException) { note = e.message ?: "That did not save." }
                        catch (e: Exception) { note = "That did not save. Check your connection." }
                        busy = false
                    }
                }, enabled = !busy, modifier = Modifier.fillMaxWidth().height(48.dp), shape = RoundedCornerShape(12.dp)) { Text("Save") }
            }
        }
    }
}

@Composable
private fun Box0(content: @Composable () -> Unit) {
    androidx.compose.foundation.layout.Box(Modifier.fillMaxWidth().padding(40.dp), contentAlignment = Alignment.Center) { content() }
}

/** Saved replies: short answers you use often, kept on your server. Add, change or remove them here; pick one while writing. */
@Composable
internal fun SavedRepliesPage(api: EnveliqApi, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    var list by remember { mutableStateOf<List<SavedReply>?>(null) }
    var note by remember { mutableStateOf("") }
    var editing by remember { mutableStateOf<SavedReply?>(null) }
    var adding by remember { mutableStateOf(false) }
    fun run(block: () -> List<SavedReply>) {
        scope.launch {
            try { list = withContext(Dispatchers.IO) { block() }; note = "" }
            catch (e: ApiException) { note = e.message ?: "That did not work." }
            catch (e: Exception) { note = "That did not work. Check your connection." }
        }
    }
    LaunchedEffect(Unit) { run { api.savedReplies() } }
    SubPage("Saved replies", "Words you use again and again", onBack = onBack, trailing = {
        TextButton(onClick = { adding = true }) { Text("Add", color = Blue) }
    }) {
        val l = list
        LazyColumn(Modifier.fillMaxSize().padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            if (l == null && note.isEmpty()) item { Box0 { CircularProgressIndicator(color = Blue) } }
            if (note.isNotEmpty()) item { Text(note, color = Amber, fontSize = 14.sp) }
            if (l != null && l.isEmpty()) item { Empty("No saved replies yet. Press Add to keep a short answer you use often.") }
            if (l != null) items(l, key = { it.id }) { r ->
                Card(onClick = { editing = r }) {
                    Text(r.title, color = Ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                    Text(r.text, color = Muted, fontSize = 14.sp, maxLines = 2, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(top = 2.dp))
                }
            }
        }
    }
    if (adding) SavedReplyForm(null, { adding = false }, onSave = { t, x -> adding = false; run { api.addSavedReply(t, x) } }, onDelete = null)
    editing?.let { r -> SavedReplyForm(r, { editing = null }, onSave = { t, x -> editing = null; run { api.updateSavedReply(r.id, t, x) } }, onDelete = { editing = null; run { api.deleteSavedReply(r.id) } }) }
}

@Composable
private fun SavedReplyForm(reply: SavedReply?, onClose: () -> Unit, onSave: (String, String) -> Unit, onDelete: (() -> Unit)?) {
    var title by remember { mutableStateOf(reply?.title ?: "") }
    var text by remember { mutableStateOf(reply?.text ?: "") }
    androidx.compose.ui.window.Dialog(onDismissRequest = onClose, properties = androidx.compose.ui.window.DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        Column(Modifier.fillMaxSize().background(Navy).systemBarsPadding().imePadding()) {
            Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(if (reply == null) "New saved reply" else "Saved reply", color = Ink, fontSize = 18.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f).padding(start = 8.dp))
                TextButton(onClick = onClose) { Text("Close", color = Blue, fontSize = 16.sp) }
            }
            Column(Modifier.weight(1f).fillMaxWidth().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedTextField(value = title, onValueChange = { title = it }, label = { Text("Name") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = text, onValueChange = { text = it }, label = { Text("The words") }, modifier = Modifier.fillMaxWidth().height(200.dp))
            }
            Row(Modifier.fillMaxWidth().padding(16.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = { onSave(title.trim(), text.trim()) }, enabled = title.isNotBlank() && text.isNotBlank(), modifier = Modifier.weight(1f).height(48.dp), shape = RoundedCornerShape(12.dp)) { Text("Save") }
                if (onDelete != null) OutlinedButton(onClick = onDelete, modifier = Modifier.weight(1f).height(48.dp), shape = RoundedCornerShape(12.dp), border = BorderStroke(1.dp, Line)) { Text("Remove", color = Red) }
            }
        }
    }
}

/** Subscriptions: what you pay for and what renews soon, from the same list as the website. Read only here. */
@Composable
internal fun SubscriptionsPage(api: EnveliqApi, onBack: () -> Unit) {
    SubPage("Subscriptions", "What you pay for, and what renews soon", onBack = onBack) {
        Loader(0, { api.subscriptions() }) { info ->
            LazyColumn(Modifier.fillMaxSize().padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                if (!info.enabled) item { Empty("Subscriptions is switched off. An administrator can switch it on.") }
                else if (info.items.isEmpty()) item { Empty("Nothing here yet. Enveliq lists subscriptions it finds in your email receipts.") }
                items(info.items, key = { it.id }) { s ->
                    Card {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f)) {
                                Text(s.service, color = Ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                                val line = when {
                                    s.nextOn.isNotBlank() -> (if (s.nextKind == "renews") "Renews " else "Next: ") + s.nextOn + if (s.nextDays in 0..30) " (in ${s.nextDays} days)" else ""
                                    s.status == "cancelled" -> "Cancelled"
                                    else -> s.status
                                }
                                Text(line, color = if (s.soon) Amber else Muted, fontSize = 13.sp, modifier = Modifier.padding(top = 2.dp))
                            }
                            if (s.amount.isNotBlank()) Text(s.amount + if (s.period.isNotBlank()) " / " + s.period else "", color = Ink, fontSize = 15.sp)
                        }
                    }
                }
                item { Text("Change or cancel a subscription on the website. This list is for reading.", color = Muted, fontSize = 12.sp, modifier = Modifier.padding(vertical = 8.dp)) }
            }
        }
    }
}

@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
/** Tags: the mailbox's tags, and the emails that carry the chosen one. Read live, never kept. */
@Composable
internal fun TagsPage(api: EnveliqApi, accountIds: List<String>, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    var acct by remember { mutableStateOf(accountIds.firstOrNull() ?: "") }
    var chosen by remember { mutableStateOf("") }
    val rows = remember { mutableStateListOf<FolderMail>() }
    var more by remember { mutableStateOf(false) }
    var note by remember { mutableStateOf("") }
    var reading by remember { mutableStateOf<FolderMail?>(null) }
    var text by remember { mutableStateOf("") }
    val row = reading
    if (row != null) {
        SubPage(row.subject, row.from, onBack = { reading = null }) {
            LaunchedEffect(row.token) {
                text = ""
                try { text = withContext(Dispatchers.IO) { api.folderOriginal(row.token) } }
                catch (e: ApiException) { text = e.message ?: "Could not open this email." }
                catch (e: Exception) { text = "Could not open this email. Check your connection." }
            }
            Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp)) {
                if (text.isEmpty()) CircularProgressIndicator(color = Blue) else Text(text, color = Ink, fontSize = 16.sp, lineHeight = 24.sp)
            }
        }
        return
    }
    fun open(name: String, offset: Int) {
        if (offset == 0) { rows.clear(); chosen = name }
        note = "Reading $name…"
        scope.launch {
            try {
                val p = withContext(Dispatchers.IO) { api.tagMail(acct, name, offset) }
                rows.addAll(p.rows); more = p.more
                note = if (p.total == 0) "No email has $name." else "$name: ${p.total} ${if (p.total == 1) "email" else "emails"}, newest first."
            } catch (e: ApiException) { note = e.message ?: "Could not open that tag." }
            catch (e: Exception) { note = "Could not open that tag. Check your connection." }
        }
    }
    SubPage("Tags", onBack = onBack) {
        Loader(0, { api.tagInfo(acct) ?: TagInfo(emptyList(), false) }) { info ->
            LazyColumn(Modifier.fillMaxSize().padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                if (info.names.isEmpty()) item { Empty("This mailbox has no tags, or its mail service does not keep tags. Open an email and press Tag to make one.") }
                item {
                    androidx.compose.foundation.layout.FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        for (n in info.names) {
                            val on = chosen == n
                            Surface(color = if (on) androidx.compose.ui.graphics.Color(0xFF173056) else PanelHigh, shape = RoundedCornerShape(20.dp), modifier = Modifier.clickable { open(n, 0) }) {
                                Text(n, color = if (on) androidx.compose.ui.graphics.Color(0xFF8DB8FF) else Ink, fontSize = 14.sp, modifier = Modifier.padding(horizontal = 14.dp, vertical = 8.dp))
                            }
                        }
                    }
                }
                if (note.isNotEmpty()) item { Text(note, color = Muted, fontSize = 13.sp) }
                items(rows.toList(), key = { it.token }) { r ->
                    Card(onClick = { reading = r }) {
                        Text(r.from, color = Ink, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        Text(r.subject, color = Muted, fontSize = 14.sp, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(top = 2.dp))
                    }
                }
                if (more) item { TextButton(onClick = { open(chosen, rows.size) }) { Text("Show more", color = Blue) } }
                item { Text("Read from your mailbox when you look. Nothing is saved in Enveliq.", color = Muted, fontSize = 12.sp, modifier = Modifier.padding(vertical = 8.dp)) }
            }
        }
    }
}

/** Ask Enveliq: a chat about your own Enveliq. Every answer is labelled as written by AI. */
@Composable
internal fun AskPage(api: EnveliqApi, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    var info by remember { mutableStateOf<AgentInfo?>(null) }
    var text by remember { mutableStateOf("") }
    var err by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    val pending = remember { mutableStateOf("") }
    val listState = rememberLazyListState()
    LaunchedEffect(Unit) {
        try { info = withContext(Dispatchers.IO) { api.agent() } }
        catch (e: ApiException) { err = e.message ?: "Could not open the chat." }
        catch (e: Exception) { err = "Could not open the chat. Check your connection." }
    }
    // While the AI is still working on its answer, look again every few seconds.
    LaunchedEffect(info?.pending, busy) {
        var tries = 0
        while (info?.pending == true && tries < 60) {
            kotlinx.coroutines.delay(3000)
            tries++
            try { info = withContext(Dispatchers.IO) { api.agent(info?.chatId) } } catch (e: Exception) { }
        }
    }
    val shown = (info?.messages ?: emptyList()) + (if (pending.value.isNotEmpty()) listOf(AgentMessage("user", pending.value)) else emptyList())
    LaunchedEffect(shown.size) { if (shown.isNotEmpty()) listState.animateScrollToItem(shown.size - 1) }
    SubPage("Ask Enveliq", "Questions about your own Enveliq", onBack = onBack) {
        Column(Modifier.fillMaxSize().imePadding()) {
            LazyColumn(Modifier.weight(1f).fillMaxWidth().padding(horizontal = 16.dp), state = listState, verticalArrangement = Arrangement.spacedBy(10.dp)) {
                if (info == null && err.isEmpty()) item { Box0 { CircularProgressIndicator(color = Blue) } }
                if (info != null && info?.ready == false) item { Text("No AI is set up yet. An administrator can add one.", color = Amber, fontSize = 14.sp) }
                if (info != null && shown.isEmpty()) item { Empty("Ask about your tasks, parcels or settings. For example: How many parcels are on their way?") }
                items(shown.size) { i ->
                    val m = shown[i]
                    val mine = m.role == "user"
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = if (mine) Arrangement.End else Arrangement.Start) {
                        Surface(color = if (mine) androidx.compose.ui.graphics.Color(0xFF14316B) else PanelHigh, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth(0.86f)) {
                            Column(Modifier.padding(12.dp)) {
                                if (!mine) Text("✦ Written by AI", color = Amber, fontSize = 11.sp)
                                Text(m.text, color = Ink, fontSize = 15.sp, lineHeight = 21.sp)
                            }
                        }
                    }
                }
                if (info?.pending == true) item { Text("Thinking…", color = Muted, fontSize = 13.sp) }
                if (info?.error?.isNotBlank() == true) item { Text(info?.error ?: "", color = Red, fontSize = 14.sp) }
                if (err.isNotEmpty()) item { Text(err, color = Red, fontSize = 14.sp) }
            }
            Row(Modifier.fillMaxWidth().padding(12.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(value = text, onValueChange = { text = it }, placeholder = { Text("Ask a question…") }, modifier = Modifier.weight(1f), maxLines = 4)
                Button(onClick = {
                    val q = text.trim()
                    if (q.isEmpty() || busy) return@Button
                    text = ""; err = ""; busy = true; pending.value = q
                    scope.launch {
                        try { info = withContext(Dispatchers.IO) { api.agentSend(q, info?.chatId) } }
                        catch (e: ApiException) { err = e.message ?: "That did not send."; text = q }
                        catch (e: Exception) { err = "That did not send. Check your connection."; text = q }
                        pending.value = ""; busy = false
                    }
                }, enabled = !busy && text.isNotBlank(), shape = RoundedCornerShape(12.dp), modifier = Modifier.height(52.dp)) { Text("Send") }
            }
            Text("Written by AI from your Enveliq's own information. It can be wrong, and it never changes anything by itself.", color = Muted, fontSize = 11.sp, modifier = Modifier.padding(start = 16.dp, end = 16.dp, bottom = 8.dp))
        }
    }
}

/** Forward, Tag and Rules for several emails at once: the three things the website's several-selected bar has beside Move. */
@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
internal fun BulkDialog(api: EnveliqApi, kind: String, mails: List<Mail>, onClose: () -> Unit, onDone: (String) -> Unit) {
    val scope = rememberCoroutineScope()
    var busy by remember { mutableStateOf(false) }
    var note by remember { mutableStateOf("") }
    var to by remember { mutableStateOf("") }
    var words by remember { mutableStateOf("") }
    var rule by remember { mutableStateOf("archived") }
    val ticked = remember { mutableStateListOf<String>() }
    var tagNames by remember { mutableStateOf<List<String>?>(null) }
    val oneBox = mails.map { it.accountId }.distinct().size == 1
    val senders = mails.map { it.address.lowercase() }.filter { it.isNotBlank() }.distinct()
    LaunchedEffect(kind) {
        if (kind == "tag" && oneBox) {
            try { tagNames = withContext(Dispatchers.IO) { api.tagInfo(mails[0].accountId)?.names ?: emptyList() } }
            catch (e: Exception) { note = "Could not load your tags. Check your connection."; tagNames = emptyList() }
        }
    }
    val title = when (kind) { "forward" -> "Forward ${mails.size} emails"; "tag" -> "Tag ${mails.size} emails"; else -> "Rules for ${senders.size} ${if (senders.size == 1) "sender" else "senders"}" }
    androidx.compose.ui.window.Dialog(onDismissRequest = onClose, properties = androidx.compose.ui.window.DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        Column(Modifier.fillMaxSize().background(Navy).systemBarsPadding().imePadding()) {
            Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(title, color = Ink, fontSize = 18.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f).padding(start = 8.dp))
                TextButton(onClick = onClose) { Text("Close", color = Blue, fontSize = 16.sp) }
            }
            Column(Modifier.weight(1f).fillMaxWidth().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                when (kind) {
                    "forward" -> {
                        Text("Each email is sent on its own, with its files, to this address.", color = Muted, fontSize = 14.sp)
                        OutlinedTextField(value = to, onValueChange = { to = it }, label = { Text("To") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                        OutlinedTextField(value = words, onValueChange = { words = it }, label = { Text("A note (optional)") }, modifier = Modifier.fillMaxWidth().height(140.dp))
                    }
                    "tag" -> {
                        if (!oneBox) Text("Pick emails from one mailbox at a time to tag them.", color = Amber, fontSize = 14.sp)
                        else if (tagNames == null) CircularProgressIndicator(color = Blue)
                        else if (tagNames?.isEmpty() == true) Text("This mailbox has no tags, or its mail service does not keep tags.", color = Muted, fontSize = 14.sp)
                        else androidx.compose.foundation.layout.FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            for (n in tagNames ?: emptyList()) {
                                val on = ticked.contains(n)
                                Surface(color = if (on) androidx.compose.ui.graphics.Color(0xFF173056) else PanelHigh, shape = RoundedCornerShape(20.dp), modifier = Modifier.clickable { if (on) ticked.remove(n) else ticked.add(n) }) {
                                    Text((if (on) "✓ " else "") + n, color = if (on) androidx.compose.ui.graphics.Color(0xFF8DB8FF) else Ink, fontSize = 14.sp, modifier = Modifier.padding(horizontal = 14.dp, vertical = 8.dp))
                                }
                            }
                        }
                    }
                    else -> {
                        Text("From now on, new email from these senders:", color = Muted, fontSize = 14.sp)
                        senders.take(6).forEach { Text(it, color = Ink, fontSize = 14.sp) }
                        if (senders.size > 6) Text("and ${senders.size - 6} more", color = Muted, fontSize = 13.sp)
                        for ((id, label) in listOf("archived" to "Is archived", "reviewed" to "Is marked as read", "starred" to "Is starred")) {
                            Surface(color = if (rule == id) androidx.compose.ui.graphics.Color(0xFF173056) else PanelHigh, shape = RoundedCornerShape(12.dp), modifier = Modifier.fillMaxWidth().clickable { rule = id }) {
                                Text((if (rule == id) "✓  " else "") + label, color = Ink, fontSize = 16.sp, modifier = Modifier.padding(14.dp))
                            }
                        }
                    }
                }
                if (note.isNotEmpty()) Text(note, color = Amber, fontSize = 14.sp)
            }
            Row(Modifier.fillMaxWidth().padding(16.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                val ready = !busy && when (kind) { "forward" -> to.contains("@"); "tag" -> oneBox && ticked.isNotEmpty(); else -> senders.isNotEmpty() }
                Button(onClick = {
                    scope.launch {
                        busy = true; note = ""
                        var done = 0
                        try {
                            withContext(Dispatchers.IO) {
                                when (kind) {
                                    "forward" -> for (m in mails) { api.forward(m, listOf(to.trim()), emptyList(), emptyList(), words.trim()); done++ }
                                    "tag" -> for (m in mails) { for (t in ticked) api.setTag(m, t, true); done++ }
                                    else -> for (a in senders) { api.saveRule("", RuleSpec(sender = a, action = rule)); done++ }
                                }
                                Unit
                            }
                            onDone(when (kind) { "forward" -> "Forwarded $done."; "tag" -> "Tagged $done."; else -> "Made $done ${if (done == 1) "rule" else "rules"}. Change them in Settings, Mail rules." })
                        } catch (e: ApiException) { note = (e.message ?: "That did not work.") + if (done > 0) " $done were done first." else "" }
                        catch (e: Exception) { note = "That did not work. Check your connection." + if (done > 0) " $done were done first." else "" }
                        busy = false
                    }
                }, enabled = ready, modifier = Modifier.weight(1f).height(48.dp), shape = RoundedCornerShape(12.dp)) {
                    Text(if (busy) "One moment…" else when (kind) { "forward" -> "Forward"; "tag" -> "Add the tags"; else -> "Make the rules" })
                }
                OutlinedButton(onClick = onClose, modifier = Modifier.weight(1f).height(48.dp), shape = RoundedCornerShape(12.dp), border = BorderStroke(1.dp, Line)) { Text("Cancel") }
            }
        }
    }
}
