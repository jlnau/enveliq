package app.enveliq

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

// Beyond email: the same lists the website has for tasks, the bell, shipping, trips, news and messages. Each one reads the
// website's own route, so the server still decides what the signed-in person may see.

/** Loads something from the server and shows it; a plain-words message when it fails. [reload] changes to load again. */
@Composable
internal fun <T : Any> Loader(reload: Int, load: () -> T, content: @Composable (T) -> Unit) {
    var data by remember { mutableStateOf<T?>(null) }
    var err by remember { mutableStateOf("") }
    LaunchedEffect(reload) {
        try {
            data = withContext(Dispatchers.IO) { load() }
            err = ""
        } catch (e: ApiException) {
            err = e.message ?: "Could not load this."
        } catch (e: Exception) {
            err = "Could not load this. Check your connection."
        }
    }
    val value = data
    when {
        value != null -> content(value)
        err.isNotEmpty() -> Text(err, color = Red, fontSize = 15.sp, modifier = Modifier.padding(20.dp))
        else -> Box(Modifier.fillMaxWidth().padding(40.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator(color = Blue) }
    }
}

@Composable
internal fun Empty(text: String) = Text(text, color = Muted, fontSize = 16.sp, lineHeight = 23.sp, modifier = Modifier.padding(20.dp))

@Composable
internal fun Card(modifier: Modifier = Modifier, onClick: (() -> Unit)? = null, content: @Composable () -> Unit) {
    val base = if (onClick != null) modifier.fillMaxWidth().clickable(onClick = onClick) else modifier.fillMaxWidth()
    Surface(color = Panel, shape = RoundedCornerShape(16.dp), border = BorderStroke(1.dp, Line), modifier = base) { Column(Modifier.padding(16.dp)) { content() } }
}

/** A sub-page with a Back button fixed at the top. */
@Composable
internal fun SubPage(title: String, subtitle: String = "", onBack: () -> Unit, trailing: @Composable () -> Unit = {}, content: @Composable () -> Unit) {
    BackHandler(onBack = onBack)
    Column(Modifier.fillMaxSize()) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = onBack) { Text("‹ Back", color = Blue, fontSize = 16.sp) }
            Column(Modifier.weight(1f)) {
                Text(title, color = Ink, fontSize = 20.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                if (subtitle.isNotEmpty()) Text(subtitle, color = Muted, fontSize = 13.sp)
            }
            trailing()
        }
        Box(Modifier.weight(1f).fillMaxWidth()) { content() }
    }
}

private fun dayWords(days: Int, due: String): String = when {
    days < 0 -> "Was due " + due
    days == 0 -> "Today"
    days == 1 -> "Tomorrow"
    else -> "In $days days"
}

// ---------- Tasks ----------

@Composable
internal fun TasksScreen(api: EnveliqApi, mails: List<Mail>, onOpen: (Mail) -> Unit) {
    var reload by remember { mutableStateOf(0) }
    var note by remember { mutableStateOf("") }
    var moving by remember { mutableStateOf<MyTask?>(null) }
    var showDone by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    fun act(t: MyTask, action: String, to: String? = null) {
        scope.launch {
            try {
                withContext(Dispatchers.IO) { api.taskAct(t.id, action, to) }
                note = ""
            } catch (e: ApiException) {
                note = e.message ?: "That did not work."
            } catch (e: Exception) {
                note = "That did not work. Check your connection."
            }
            reload++
        }
    }
    Column(Modifier.fillMaxSize()) {
        Loader(reload, { api.myTasks() }) { all ->
            val open = all.filter { it.state == "open" }
            val done = all.filter { it.state != "open" }
            Heading("Tasks", if (open.isEmpty()) "" else "${open.size} to do")
            if (note.isNotEmpty()) Text(note, color = Amber, fontSize = 14.sp, modifier = Modifier.padding(horizontal = 20.dp))
            LazyColumn(Modifier.fillMaxSize().padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                if (open.isEmpty()) item { Empty("Nothing to do right now. Tasks appear here when an email needs something from you.") }
                items(open, key = { "t" + it.id }) { t ->
                    Card(onClick = { mails.firstOrNull { it.accountId == t.accountId && it.id == t.messageId }?.let(onOpen) }) {
                        Text(t.title, color = Ink, fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
                        Text(dayWords(t.days, t.due), color = if (t.days < 0) Red else if (t.days == 0) Amber else Muted, fontSize = 14.sp, modifier = Modifier.padding(top = 3.dp))
                        if (t.sender.isNotBlank()) Text("From " + t.sender, color = Muted, fontSize = 13.sp, modifier = Modifier.padding(top = 2.dp))
                        Row(Modifier.padding(top = 6.dp), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                            TextButton(onClick = { act(t, "done") }) { Text("Done", color = Green) }
                            TextButton(onClick = { moving = t }) { Text("Move", color = Blue) }
                            if (t.days <= 0) TextButton(onClick = { act(t, "not_today") }) { Text("Not today", color = Muted) }
                            TextButton(onClick = { act(t, "remove") }) { Text("Remove", color = Muted) }
                        }
                    }
                }
                if (done.isNotEmpty()) {
                    item { TextButton(onClick = { showDone = !showDone }) { Text(if (showDone) "Hide finished tasks" else "Show ${done.size} finished", color = Blue) } }
                    if (showDone) items(done, key = { "d" + it.id }) { t ->
                        Card {
                            Text(t.title, color = Muted, fontSize = 16.sp)
                            TextButton(onClick = { act(t, "reopen") }) { Text("Put back", color = Blue) }
                        }
                    }
                }
            }
        }
    }
    moving?.let { t ->
        androidx.compose.material3.AlertDialog(
            onDismissRequest = { moving = null },
            title = { Text("Move this task to") },
            text = {
                Column {
                    for ((id, label) in listOf("later_today" to "Later today", "tomorrow" to "Tomorrow", "weekend" to "The weekend", "next_week" to "Next week")) {
                        TextButton(onClick = { moving = null; act(t, "move", id) }, modifier = Modifier.fillMaxWidth()) { Text(label, color = Ink, fontSize = 17.sp) }
                    }
                }
            },
            confirmButton = {},
            dismissButton = { TextButton(onClick = { moving = null }) { Text("Cancel", color = Muted) } },
        )
    }
}

// ---------- The More tab ----------

@Composable
internal fun MoreTab(api: EnveliqApi, start: String = "home") {
    var page by remember { mutableStateOf(start) }
    val back = { page = "home" }
    var cleanOn by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { cleanOn = withContext(Dispatchers.IO) { api.cleanUpAvailable() } }
    when {
        page == "bell" -> BellPage(api, back)
        page == "shipping" -> ShippingPage(api, back)
        page == "trips" -> TripsPage(api, back)
        page == "news" -> NewsPage(api, back)
        page == "chat" -> ChatsPage(api, back)
        page == "find" -> FindPage(api, back)
        page == "later" -> WaitingPage(api, back)
        page == "cleanup" -> CleanUpPage(api, back)
        else -> Column(Modifier.fillMaxSize()) {
            Heading("More", "")
            LazyColumn(Modifier.fillMaxSize().padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                items(listOf(
                    Triple("cleanup", "Clean up", "Quiet the mailing lists you do not need."),
                    Triple("find", "Find any email", "Search everything in your mailboxes, old email too."),
                    Triple("later", "Waiting to send", "Emails you set to go later, and any that could not go."),
                    Triple("bell", "Notes and alerts", "Things your other services told Enveliq."),
                    Triple("chat", "Messages", "Chat with the people in your household."),
                    Triple("shipping", "Shipping", "Parcels on their way and when they arrive."),
                    Triple("trips", "Trips and calendar", "Flights, stays and bookings from your email."),
                    Triple("news", "News feeds", "The sites you follow."),
                ).filter { it.first != "cleanup" || cleanOn }) { (id, title, note) ->
                    Card(onClick = { page = id }) {
                        Text(title, color = Ink, fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
                        Text(note, color = Muted, fontSize = 14.sp, modifier = Modifier.padding(top = 2.dp))
                    }
                }
            }
        }
    }
}

@Composable
private fun BellPage(api: EnveliqApi, onBack: () -> Unit) {
    var reload by remember { mutableStateOf(0) }
    val scope = rememberCoroutineScope()
    fun run(block: () -> Unit) { scope.launch { try { withContext(Dispatchers.IO) { block() } } catch (e: Exception) { /* the list reloads either way */ }; reload++ } }
    SubPage("Notes and alerts", onBack = onBack) {
        Loader(reload, { api.bell().also { if (it.any { n -> n.unread }) try { api.bellRead() } catch (e: Exception) { } } }) { notes ->
            LazyColumn(Modifier.fillMaxSize().padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                if (notes.isEmpty()) item { Empty("Nothing here. When another service of yours sends Enveliq a note, it shows up here.") }
                items(notes, key = { it.id }) { n ->
                    Card {
                        Text(n.title.ifBlank { n.source.ifBlank { "Note" } }, color = Ink, fontSize = 16.sp, fontWeight = if (n.unread) FontWeight.Bold else FontWeight.SemiBold)
                        if (n.message.isNotBlank()) Text(n.message, color = Muted, fontSize = 14.sp, lineHeight = 20.sp, modifier = Modifier.padding(top = 3.dp))
                        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(top = 4.dp)) {
                            Text(whenText(n.at), color = Muted, fontSize = 12.sp, modifier = Modifier.weight(1f))
                            TextButton(onClick = { run { api.bellDismiss(n.id) } }) { Text("Dismiss", color = Muted) }
                        }
                    }
                }
                if (notes.isNotEmpty()) item { TextButton(onClick = { run { api.bellClear() } }) { Text("Clear all", color = Red) } }
            }
        }
    }
}

@Composable
private fun ShippingPage(api: EnveliqApi, onBack: () -> Unit) {
    var link by remember { mutableStateOf<String?>(null) }
    SubPage("Shipping", onBack = onBack) {
        Loader(0, { api.shipping() }) { sec ->
            if (!sec.enabled) Empty("Shipping is switched off. You can turn it on in Settings on the website.")
            else LazyColumn(Modifier.fillMaxSize().padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                if (sec.items.isEmpty()) item { Empty("No parcels yet. Order confirmations and shipping emails are picked up here.") }
                items(sec.items, key = { it.id }) { o ->
                    Card {
                        Text(o.shop.ifBlank { "Order" }, color = Ink, fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
                        if (o.items.isNotBlank()) Text(o.items, color = Muted, fontSize = 14.sp, modifier = Modifier.padding(top = 2.dp))
                        val status = when {
                            o.needsConfirm -> "Delivered. Did it arrive?"
                            o.delivered -> "Delivered"
                            o.delayed -> "Delayed" + if (o.expected.isNotBlank()) ", now " + o.expected else ""
                            else -> o.status.replaceFirstChar { it.uppercase() } + if (o.expected.isNotBlank()) ", expected " + o.expected else ""
                        }
                        Text(status, color = if (o.delayed) Amber else if (o.delivered) Green else Ink, fontSize = 14.sp, modifier = Modifier.padding(top = 4.dp))
                        if (o.trackUrl.startsWith("https://")) TextButton(onClick = { link = o.trackUrl }) { Text("Track it", color = Blue) }
                    }
                }
            }
        }
    }
    link?.let { LinkConfirm(it) { link = null } }
}

@Composable
private fun TripsPage(api: EnveliqApi, onBack: () -> Unit) {
    SubPage("Trips and calendar", onBack = onBack) {
        Loader(0, { api.trips() }) { sec ->
            if (!sec.enabled) Empty("Trips are switched off. You can turn them on in Settings on the website.")
            else {
                val trips = sec.items.filter { it.state != "past" }
                LazyColumn(Modifier.fillMaxSize().padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    if (trips.isEmpty()) item { Empty("No trips coming up. Flight, hotel and booking emails are picked up here.") }
                    items(trips, key = { it.start + it.title }) { t ->
                        Card {
                            Text(t.title, color = Ink, fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
                            Text(t.start + if (t.end.isNotBlank() && t.end != t.start) " to " + t.end else "", color = if (t.state == "now") Green else Muted, fontSize = 14.sp, modifier = Modifier.padding(top = 2.dp))
                            for (b in t.bookings) {
                                Text(
                                    listOf(b.kind.replaceFirstChar { it.uppercase() }, b.provider, b.detail, if (b.from.isNotBlank() || b.to.isNotBlank()) b.from + " to " + b.to else "", b.start + (if (b.startTime.isNotBlank()) " " + b.startTime else ""))
                                        .filter { it.isNotBlank() }.joinToString(", ") + if (b.cancelled) " (cancelled)" else "",
                                    color = if (b.cancelled) Muted else Ink, fontSize = 14.sp, lineHeight = 20.sp, modifier = Modifier.padding(top = 6.dp),
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun NewsPage(api: EnveliqApi, onBack: () -> Unit) {
    var reload by remember { mutableStateOf(0) }
    var open by remember { mutableStateOf<String?>(null) }
    var link by remember { mutableStateOf<String?>(null) }
    var refreshing by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    SubPage(
        "News feeds", onBack = { if (open != null) open = null else onBack() },
        trailing = {
            TextButton(enabled = !refreshing, onClick = {
                refreshing = true
                scope.launch { try { withContext(Dispatchers.IO) { api.newsRefresh() } } catch (e: Exception) { }; refreshing = false; reload++ }
            }) { Text(if (refreshing) "Checking..." else "Refresh", color = Blue) }
        },
    ) {
        Loader(reload, { api.news() }) { sec ->
            val feed = sec.items.firstOrNull { it.id == open }
            if (!sec.enabled) Empty("News feeds are switched off. You can turn them on in Settings on the website.")
            else if (feed == null) LazyColumn(Modifier.fillMaxSize().padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                if (sec.items.isEmpty()) item { Empty("No feeds yet. Add the sites you follow on the website.") }
                items(sec.items, key = { it.id }) { f ->
                    Card(onClick = { open = f.id }) {
                        Text(f.title, color = Ink, fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
                        Text(if (f.error.isNotBlank()) f.error else if (f.newCount > 0) "${f.newCount} new" else "Nothing new", color = if (f.error.isNotBlank()) Amber else Muted, fontSize = 14.sp, modifier = Modifier.padding(top = 2.dp))
                    }
                }
            } else LazyColumn(Modifier.fillMaxSize().padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                items(feed.items, key = { it.link + it.title }) { i ->
                    Card(onClick = if (i.link.startsWith("https://")) ({ link = i.link }) else null) {
                        Text(i.title, color = Ink, fontSize = 16.sp, fontWeight = if (i.isNew) FontWeight.Bold else FontWeight.Normal)
                        if (i.text.isNotBlank()) Text(i.text, color = Muted, fontSize = 14.sp, maxLines = 3, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(top = 3.dp))
                    }
                }
            }
        }
    }
    LaunchedEffect(open) { if (open != null) try { withContext(Dispatchers.IO) { api.newsSeen() } } catch (e: Exception) { } }
    link?.let { LinkConfirm(it) { link = null } }
}

@Composable
private fun ChatsPage(api: EnveliqApi, onBack: () -> Unit) {
    var open by remember { mutableStateOf<Chat?>(null) }
    val chat = open
    if (chat != null) { ChatThread(api, chat) { open = null }; return }
    SubPage("Messages", onBack = onBack) {
        Loader(0, { api.threads() }) { threads ->
            LazyColumn(Modifier.fillMaxSize().padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                if (threads.isEmpty()) item { Empty("No conversations yet. Start one on the website.") }
                items(threads, key = { it.id }) { t ->
                    Card(onClick = { open = t }) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(t.title, color = Ink, fontSize = 17.sp, fontWeight = if (t.unread > 0) FontWeight.Bold else FontWeight.SemiBold, modifier = Modifier.weight(1f))
                            if (t.unread > 0) Text("${t.unread}", color = Blue, fontSize = 14.sp, fontWeight = FontWeight.Bold)
                        }
                        if (t.last.isNotBlank()) Text(t.last, color = Muted, fontSize = 14.sp, maxLines = 2, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(top = 2.dp))
                    }
                }
            }
        }
    }
}

@Composable
private fun ChatThread(api: EnveliqApi, chat: Chat, onBack: () -> Unit) {
    var reload by remember { mutableStateOf(0) }
    var text by remember { mutableStateOf("") }
    var note by remember { mutableStateOf("") }
    val scope = rememberCoroutineScope()
    SubPage(chat.title, onBack = onBack) {
        Column(Modifier.fillMaxSize().imePadding()) {
            Box(Modifier.weight(1f)) {
                Loader(reload, { api.thread(chat.id) }) { msgs ->
                    LazyColumn(Modifier.fillMaxSize().padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(8.dp), reverseLayout = true) {
                        items(msgs.reversed(), key = { it.id }) { m ->
                            Column(Modifier.fillMaxWidth(), horizontalAlignment = if (m.mine) Alignment.End else Alignment.Start) {
                                Surface(color = if (m.mine) Blue else PanelHigh, shape = RoundedCornerShape(16.dp)) {
                                    Column(Modifier.padding(horizontal = 14.dp, vertical = 8.dp)) {
                                        if (!m.mine) Text(m.name, color = Muted, fontSize = 12.sp)
                                        Text(if (m.deleted) "Message removed" else m.text, color = if (m.mine) androidx.compose.ui.graphics.Color.White else Ink, fontSize = 16.sp)
                                    }
                                }
                                Text(whenText(m.at), color = Muted, fontSize = 11.sp, modifier = Modifier.padding(horizontal = 6.dp))
                            }
                        }
                    }
                }
            }
            if (note.isNotEmpty()) Text(note, color = Red, fontSize = 13.sp, modifier = Modifier.padding(horizontal = 16.dp))
            Row(Modifier.fillMaxWidth().background(Panel).padding(horizontal = 12.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                OutlinedTextField(value = text, onValueChange = { text = it }, modifier = Modifier.weight(1f), placeholder = { Text("Write a message") }, maxLines = 4)
                Box(Modifier.size(8.dp))
                Button(enabled = text.isNotBlank(), onClick = {
                    val sending = text
                    scope.launch {
                        try {
                            withContext(Dispatchers.IO) { api.sendChat(chat.id, sending) }
                            text = ""
                            note = ""
                            reload++
                        } catch (e: ApiException) {
                            note = e.message ?: "Could not send that."
                        } catch (e: Exception) {
                            note = "Could not send that. Check your connection."
                        }
                    }
                }) { Text("Send") }
            }
        }
    }
}

@Composable
private fun FindPage(api: EnveliqApi, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    var query by remember { mutableStateOf("") }
    var junk by remember { mutableStateOf(false) }
    var jobId by remember { mutableStateOf("") }
    var running by remember { mutableStateOf(false) }
    var note by remember { mutableStateOf("") }
    val rows = remember { androidx.compose.runtime.mutableStateListOf<FoundRow>() }
    var more by remember { mutableStateOf(false) }
    var reading by remember { mutableStateOf<FoundRow?>(null) }
    var text by remember { mutableStateOf("") }

    val row = reading
    if (row != null) {
        SubPage(row.subject, row.from, onBack = { reading = null }) {
            LaunchedEffect(row.token) {
                text = ""
                try { text = withContext(Dispatchers.IO) { api.findOriginal(row.token) } }
                catch (e: ApiException) { text = e.message ?: "Could not open this email." }
                catch (e: Exception) { text = "Could not open this email. Check your connection." }
            }
            Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp)) {
                if (text.isEmpty()) CircularProgressIndicator(color = Blue) else Text(text, color = Ink, fontSize = 16.sp, lineHeight = 24.sp)
            }
        }
        return
    }

    fun search() {
        if (query.isBlank() || running) return
        rows.clear(); more = false; note = ""; running = true
        scope.launch {
            try {
                var p = withContext(Dispatchers.IO) { api.findStart(query.trim(), junk) }
                jobId = p.id
                var shown = 0
                var tries = 0
                while (true) {
                    if (p.listed > shown || p.done) {
                        var offset = shown
                        while (offset < p.listed && offset < 100) {
                            val (got, hasMore) = withContext(Dispatchers.IO) { api.findPage(p.id, offset) }
                            if (got.isEmpty()) break
                            rows.addAll(got); offset += 25; more = hasMore
                        }
                        shown = p.listed
                    }
                    if (p.done || ++tries > 90) break
                    kotlinx.coroutines.delay(1500)
                    p = withContext(Dispatchers.IO) { api.findProgress(p.id) }
                }
                note = if (rows.isEmpty()) "Nothing found. Try fewer or different words." else p.notes.joinToString(" ")
            } catch (e: ApiException) {
                note = e.message ?: "The search did not work."
            } catch (e: Exception) {
                note = "The search did not work. Check your connection."
            }
            running = false
        }
    }

    SubPage("Find any email", onBack = onBack) {
        LazyColumn(Modifier.fillMaxSize().padding(horizontal = 16.dp).imePadding(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item {
                OutlinedTextField(
                    value = query, onValueChange = { query = it.take(300) }, singleLine = true, label = { Text("Words to look for") },
                    modifier = Modifier.fillMaxWidth(),
                )
                Row(Modifier.fillMaxWidth().padding(top = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                    androidx.compose.material3.Switch(checked = junk, onCheckedChange = { junk = it })
                    Text("Look in Junk too", color = Ink, fontSize = 15.sp, modifier = Modifier.padding(start = 10.dp))
                }
                Button(onClick = { search() }, enabled = !running && query.isNotBlank(), modifier = Modifier.fillMaxWidth().padding(top = 6.dp)) {
                    Text(if (running) "Searching..." else "Search")
                }
                if (running) TextButton(onClick = { scope.launch { withContext(Dispatchers.IO) { api.findCancel(jobId) } } }) { Text("Stop searching", color = Blue) }
                if (note.isNotEmpty()) Text(note, color = Muted, fontSize = 14.sp, modifier = Modifier.padding(top = 4.dp))
            }
            items(rows, key = { it.token }) { r ->
                Card(onClick = { reading = r }) {
                    Text(r.subject, color = Ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    Text(r.from, color = Muted, fontSize = 14.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(listOf(r.date.take(10), r.mailbox, r.folder).filter { it.isNotBlank() }.joinToString(" · "), color = Muted, fontSize = 12.sp)
                }
            }
            item { if (more && !running) Text("Only the first results are shown. Add more words to narrow it down.", color = Muted, fontSize = 13.sp) }
        }
    }
}

@Composable
private fun WaitingPage(api: EnveliqApi, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    var reload by remember { mutableStateOf(0) }
    var note by remember { mutableStateOf("") }
    SubPage("Waiting to send", onBack = onBack) {
        Loader(reload, { api.waiting() }) { items ->
            LazyColumn(Modifier.fillMaxSize().padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                if (items.isEmpty()) item { Empty("Nothing is waiting. Press Later when you write an email to send it at a time you choose.") }
                if (note.isNotEmpty()) item { Text(note, color = Amber, fontSize = 14.sp) }
                items(items, key = { it.id }) { w ->
                    Card {
                        Text(w.subject, color = Ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, maxLines = 2, overflow = TextOverflow.Ellipsis)
                        Text("To " + w.to + if (w.people > 1) " and " + (w.people - 1) + " more" else "", color = Muted, fontSize = 14.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        if (w.state == "failed") Text("Could not be sent: " + w.error.ifBlank { "Please try again." }, color = Red, fontSize = 14.sp, modifier = Modifier.padding(top = 4.dp))
                        else Text("Goes " + whenText(w.at), color = Muted, fontSize = 14.sp)
                        TextButton(onClick = {
                            scope.launch {
                                try { withContext(Dispatchers.IO) { api.cancelWaiting(w.id) }; note = if (w.state == "failed") "" else "Taken back. It will not be sent." }
                                catch (e: Exception) { note = "Could not do that. Please try again." }
                                reload++
                            }
                        }) { Text(if (w.state == "failed") "Remove" else "Take it back", color = Blue) }
                    }
                }
            }
        }
    }
}
