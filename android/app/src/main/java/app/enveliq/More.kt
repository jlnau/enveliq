package app.enveliq

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Spacer
import androidx.compose.material3.OutlinedButton
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
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
internal fun MoreTab(api: EnveliqApi, start: String = "home", findStart: FindSpec? = null) {
    var page by remember { mutableStateOf(start) }
    val back = { page = "home" }
    var cleanOn by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { cleanOn = withContext(Dispatchers.IO) { api.cleanUpAvailable() } }
    var mailboxIds by remember { mutableStateOf(emptyList<String>()) }
    LaunchedEffect(Unit) { try { mailboxIds = withContext(Dispatchers.IO) { api.mailboxes().map { it.id } } } catch (e: Exception) { } }
    when {
        page == "bell" -> BellPage(api, back)
        page == "trips" -> TripsPage(api, back)
        page == "news" -> NewsPage(api, back)
        page == "find" -> FindPage(api, findStart, back)
        page == "later" -> WaitingPage(api, back)
        page == "cleanup" -> CleanUpPage(api, back)
        page == "subscriptions" -> SubscriptionsPage(api, back)
        page == "tags" -> TagsPage(api, mailboxIds, back)
        page == "ask" -> AskPage(api, back)
        else -> Column(Modifier.fillMaxSize()) {
            Heading("More", "")
            LazyColumn(Modifier.fillMaxSize().padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                items(listOf(
                    Triple("cleanup", "Clean up", "Quiet the mailing lists you do not need."),
                    Triple("find", "Find any email", "Search everything in your mailboxes, old email too."),
                    Triple("ask", "Ask Enveliq", "Questions about your own Enveliq. Answers are written by AI."),
                    Triple("tags", "Tags", "Your tags, and the emails that carry each one."),
                    Triple("subscriptions", "Subscriptions", "What you pay for, and what renews soon."),
                    Triple("later", "Waiting to send", "Emails you set to go later, and any that could not go."),
                    Triple("bell", "Notes and alerts", "Things your other services told Enveliq."),
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
internal fun ShippingPage(api: EnveliqApi, onBack: () -> Unit) {
    var link by remember { mutableStateOf<String?>(null) }
    var reload by remember { mutableStateOf(0) }
    var recvOpen by remember { mutableStateOf(false) }
    var noting by remember { mutableStateOf<Order?>(null) }
    var askNot by remember { mutableStateOf<Order?>(null) }
    val scope = rememberCoroutineScope()
    val snack = androidx.compose.runtime.remember { androidx.compose.material3.SnackbarHostState() }
    val clipboard = androidx.compose.ui.platform.LocalClipboardManager.current
    fun act(id: String, action: String) {
        scope.launch {
            try { withContext(Dispatchers.IO) { api.shippingAct(id, action) } } catch (e: Exception) { snack.showSnackbar((e as? ApiException)?.message ?: "That did not work. Please try again.") }
            reload++
        }
    }
    SubPage("Shipping", onBack = onBack) {
        Loader(reload, { api.shipping() }) { sec ->
            if (!sec.enabled) Empty("Shipping is switched off. You can turn it on in Settings on the website.")
            else {
                val got = sec.items.filter { it.delivered && it.acked }
                val active = sec.items.filter { !(it.delivered && it.acked) }
                LazyColumn(Modifier.fillMaxSize().padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    if (sec.items.isEmpty()) item { Empty("No parcels yet. Order confirmations and shipping emails are picked up here.") }
                    else if (active.isEmpty()) item { Empty("Nothing on its way. Parcels you have not marked as received show here.") }
                    items(active, key = { it.id }) { o ->
                        var menu by remember { mutableStateOf(false) }
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
                            if (o.note.isNotBlank()) Text(o.note, color = Muted, fontSize = 13.sp, modifier = Modifier.padding(top = 4.dp))
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                if (o.needsConfirm) {
                                    TextButton(onClick = { act(o.id, "confirm") }) { Text("Yes, I've got it", color = Green) }
                                    TextButton(onClick = { act(o.id, "not_yet") }) { Text("Not yet", color = Muted) }
                                } else if (o.trackUrl.startsWith("https://")) TextButton(onClick = { link = o.trackUrl }) { Text("Track it", color = Blue) }
                                Box(Modifier.weight(1f), contentAlignment = Alignment.CenterEnd) {
                                  // The menu hangs from the three dots themselves, so it opens right under them and raised above the cards.
                                  Box {
                                    TextButton(onClick = { menu = true }) { Text("⋮", color = Muted, fontSize = 20.sp) }
                                    androidx.compose.material3.DropdownMenu(expanded = menu, onDismissRequest = { menu = false }, containerColor = PanelHigh, shape = RoundedCornerShape(14.dp), shadowElevation = 8.dp) {
                                        if (o.needsConfirm && o.trackUrl.startsWith("https://")) androidx.compose.material3.DropdownMenuItem(text = { Text("Track it", color = Ink) }, onClick = { menu = false; link = o.trackUrl })
                                        if (o.tracking.isNotBlank()) androidx.compose.material3.DropdownMenuItem(text = { Text("Copy tracking number", color = Ink) }, onClick = { menu = false; clipboard.setText(androidx.compose.ui.text.AnnotatedString(o.tracking)) })
                                        androidx.compose.material3.DropdownMenuItem(text = { Text((if (o.note.isBlank()) "\u270E  Add a note" else "\u270E  Edit note"), color = Ink) }, onClick = { menu = false; noting = o })
                                        if (o.manual) androidx.compose.material3.DropdownMenuItem(text = { Text("\u2298  Remove", color = Red) }, onClick = { menu = false; act(o.id, "remove") })
                                        else androidx.compose.material3.DropdownMenuItem(text = { Text("\u2298  Not an order", color = Red) }, onClick = { menu = false; askNot = o })
                                    }
                                  }
                                }
                            }
                        }
                    }
                    if (got.isNotEmpty()) {
                        item {
                            Row(Modifier.fillMaxWidth().clickable { recvOpen = !recvOpen }.padding(vertical = 12.dp, horizontal = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                                Text("Received · " + got.size, color = Muted, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                                Text(if (recvOpen) "⌃" else "⌄", color = Muted, fontSize = 18.sp)
                            }
                        }
                        if (recvOpen) {
                            items(got, key = { "r" + it.id }) { o ->
                                Surface(color = Panel, shape = RoundedCornerShape(14.dp), border = BorderStroke(1.dp, Line), modifier = Modifier.fillMaxWidth()) {
                                    Row(Modifier.padding(start = 14.dp, top = 6.dp, bottom = 6.dp, end = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                                        Column(Modifier.weight(1f)) {
                                            Text(o.shop.ifBlank { "Order" }, color = Ink, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
                                            if (o.items.isNotBlank()) Text(o.items, color = Muted, fontSize = 13.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                        }
                                        TextButton(onClick = { act(o.id, "undo") }) { Text("Undo", color = Blue) }
                                    }
                                }
                            }
                            item { Text("Received orders stay here for 14 days, then are forgotten.", color = Muted, fontSize = 12.sp, modifier = Modifier.padding(4.dp)) }
                        }
                    }
                }
            }
        }
        androidx.compose.material3.SnackbarHost(snack)
    }
    link?.let { LinkConfirm(it) { link = null } }
    askNot?.let { o ->
        androidx.compose.material3.AlertDialog(
            onDismissRequest = { askNot = null }, title = { Text("This is not an order?") },
            text = { Text("It is taken off your list and Enveliq will not pick it up again.") },
            confirmButton = { TextButton(onClick = { askNot = null; act(o.id, "not_order") }) { Text("Not an order", color = Red) } },
            dismissButton = { TextButton(onClick = { askNot = null }) { Text("Cancel", color = Muted) } },
        )
    }
    noting?.let { o ->
        var text by remember(o.id) { mutableStateOf(o.note) }
        androidx.compose.material3.AlertDialog(
            onDismissRequest = { noting = null }, title = { Text("Note") },
            text = { OutlinedTextField(value = text, onValueChange = { text = it.take(500) }, modifier = Modifier.fillMaxWidth(), maxLines = 5) },
            confirmButton = { TextButton(onClick = { noting = null; scope.launch { try { withContext(Dispatchers.IO) { api.shippingNote(o.id, text) } } catch (e: Exception) { snack.showSnackbar("That did not work. Please try again.") }; reload++ } }) { Text("Save", color = Blue) } },
            dismissButton = { TextButton(onClick = { noting = null }) { Text("Cancel", color = Muted) } },
        )
    }
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

@OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class, androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
private fun DateField(label: String, value: String, onChange: (String) -> Unit, modifier: Modifier = Modifier) {
    var show by remember { mutableStateOf(false) }
    OutlinedTextField(
        value = value, onValueChange = {}, readOnly = true, singleLine = true, label = { Text(label) }, placeholder = { Text("any date") },
        modifier = modifier.clickable { show = true },
        enabled = false,
        colors = androidx.compose.material3.OutlinedTextFieldDefaults.colors(
            disabledTextColor = Ink, disabledBorderColor = Line, disabledLabelColor = Muted, disabledPlaceholderColor = Muted,
        ),
        trailingIcon = { if (value.isNotBlank()) TextButton(onClick = { onChange("") }) { Text("Clear", color = Blue, fontSize = 13.sp) } },
    )
    if (show) {
        val state = androidx.compose.material3.rememberDatePickerState(
            initialSelectedDateMillis = runCatching { java.time.LocalDate.parse(value).atStartOfDay(java.time.ZoneOffset.UTC).toInstant().toEpochMilli() }.getOrNull(),
        )
        androidx.compose.material3.DatePickerDialog(
            onDismissRequest = { show = false },
            confirmButton = {
                TextButton(onClick = {
                    state.selectedDateMillis?.let { onChange(java.time.Instant.ofEpochMilli(it).atZone(java.time.ZoneOffset.UTC).toLocalDate().toString()) }
                    show = false
                }) { Text("OK", color = Blue) }
            },
            dismissButton = { TextButton(onClick = { show = false }) { Text("Cancel", color = Muted) } },
        ) { androidx.compose.material3.DatePicker(state = state) }
    }
}

@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
private fun FindPage(api: EnveliqApi, start: FindSpec? = null, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    var spec by remember { mutableStateOf(start ?: FindSpec()) }
    var filtersOpen by remember { mutableStateOf(false) }
    var jobId by remember { mutableStateOf("") }
    var running by remember { mutableStateOf(false) }
    var searched by remember { mutableStateOf<FindSpec?>(null) }
    var note by remember { mutableStateOf("") }
    val rows = remember { androidx.compose.runtime.mutableStateListOf<FoundRow>() }
    var more by remember { mutableStateOf(false) }
    var reading by remember { mutableStateOf<FoundRow?>(null) }
    var text by remember { mutableStateOf("") }
    var boxes by remember { mutableStateOf<List<Mailbox>>(emptyList()) }
    var folders by remember { mutableStateOf<List<FolderInfo>>(emptyList()) }
    var history by remember { mutableStateOf(FindHistory(emptyList(), emptyList())) }
    var naming by remember { mutableStateOf(false) }
    var saveName by remember { mutableStateOf("") }
    var reload by remember { mutableStateOf(0) }

    LaunchedEffect(Unit) { boxes = try { withContext(Dispatchers.IO) { api.mailboxes() } } catch (_: Exception) { emptyList() } }
    LaunchedEffect(reload) { history = try { withContext(Dispatchers.IO) { api.findHistory() } } catch (_: Exception) { history } }
    LaunchedEffect(spec.accountId) {
        folders = if (spec.accountId.isBlank()) emptyList() else try { withContext(Dispatchers.IO) { api.folders(spec.accountId) } } catch (_: Exception) { emptyList() }
    }

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

    fun search(s: FindSpec = spec) {
        if (!s.canSearch || running) return
        spec = s; searched = s
        rows.clear(); more = false; note = ""; running = true; filtersOpen = false
        scope.launch {
            try {
                var p = withContext(Dispatchers.IO) { api.findStart(s) }
                jobId = p.id
                reload++
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
                note = if (rows.isEmpty()) "Nothing found. Try fewer or different words or filters." else p.notes.joinToString(" ")
            } catch (e: ApiException) {
                note = e.message ?: "The search did not work."
            } catch (e: Exception) {
                note = "The search did not work. Check your connection."
            }
            running = false
        }
    }
    // Opened from a saved search in the main menu: run it straight away.
    LaunchedEffect(start) { if (start != null && start.canSearch) search(start) }

    if (naming) {
        androidx.compose.material3.AlertDialog(
            onDismissRequest = { naming = false },
            title = { Text("Save this search") },
            text = { OutlinedTextField(value = saveName, onValueChange = { saveName = it.take(60) }, singleLine = true, label = { Text("Name") }) },
            confirmButton = {
                TextButton(enabled = saveName.isNotBlank(), onClick = {
                    naming = false
                    val s = searched ?: spec
                    scope.launch {
                        note = try { withContext(Dispatchers.IO) { api.findSave(saveName, s) }; "Saved. It is in the main menu." }
                        catch (e: ApiException) { e.message ?: "That did not save." }
                        catch (e: Exception) { "That did not save. Check your connection." }
                        saveName = ""; reload++
                    }
                }) { Text("Save", color = Blue) }
            },
            dismissButton = { TextButton(onClick = { naming = false }) { Text("Cancel", color = Muted) } },
        )
    }

    SubPage("Find any email", onBack = onBack) {
        LazyColumn(Modifier.fillMaxSize().padding(horizontal = 16.dp).imePadding(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item {
                OutlinedTextField(
                    value = spec.query, onValueChange = { spec = spec.copy(query = it.take(200)) }, singleLine = true, label = { Text("Words to look for") },
                    modifier = Modifier.fillMaxWidth(),
                )
                Row(Modifier.fillMaxWidth().clickable { filtersOpen = !filtersOpen }.padding(vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(if (filtersOpen) "Filters \u25B4" else "Filters \u25BE", color = Blue, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
                    Spacer(Modifier.weight(1f))
                    Text(if (spec.filterCount == 0) "none set" else spec.filterCount.toString() + " set", color = Muted, fontSize = 13.sp)
                }
                if (filtersOpen) {
                    OutlinedTextField(value = spec.sender, onValueChange = { spec = spec.copy(sender = it.take(100)) }, singleLine = true, label = { Text("From") }, placeholder = { Text("a name or address") }, modifier = Modifier.fillMaxWidth())
                    OutlinedTextField(value = spec.to, onValueChange = { spec = spec.copy(to = it.take(100)) }, singleLine = true, label = { Text("To") }, placeholder = { Text("a name or address") }, modifier = Modifier.fillMaxWidth().padding(top = 8.dp))
                    Row(Modifier.fillMaxWidth().padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        DateField("Since", spec.since, { spec = spec.copy(since = it) }, Modifier.weight(1f))
                        DateField("Until", spec.until, { spec = spec.copy(until = it) }, Modifier.weight(1f))
                    }
                    for ((label, on, set) in listOf<Triple<String, Boolean, (Boolean) -> Unit>>(
                        Triple("Has files", spec.files) { spec = spec.copy(files = it) },
                        Triple("Unread only", spec.unread) { spec = spec.copy(unread = it) },
                        Triple("Starred only", spec.starred) { spec = spec.copy(starred = it) },
                        Triple("Look in Junk too", spec.junk) { spec = spec.copy(junk = it) },
                    )) {
                        Row(Modifier.fillMaxWidth().padding(top = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                            Text(label, color = Ink, fontSize = 15.sp, modifier = Modifier.weight(1f))
                            androidx.compose.material3.Switch(checked = on, onCheckedChange = set)
                        }
                    }
                    if (boxes.size > 1) {
                        Text("Where", color = Muted, fontSize = 12.sp, modifier = Modifier.padding(top = 10.dp, bottom = 4.dp))
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            FindChip("All mailboxes", spec.accountId.isBlank()) { spec = spec.copy(accountId = "", folder = "") }
                            boxes.forEach { b -> FindChip(b.label, spec.accountId == b.id) { spec = spec.copy(accountId = b.id, folder = "") } }
                        }
                    }
                    if (spec.accountId.isNotBlank() && folders.isNotEmpty()) {
                        Text("Folder", color = Muted, fontSize = 12.sp, modifier = Modifier.padding(top = 10.dp, bottom = 4.dp))
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            FindChip("Every folder", spec.folder.isBlank()) { spec = spec.copy(folder = "") }
                            folders.forEach { f -> FindChip(f.label, spec.folder == f.name) { spec = spec.copy(folder = f.name) } }
                        }
                    }
                    TextButton(onClick = { spec = FindSpec(query = spec.query) }) { Text("Clear filters", color = Blue) }
                }
                Button(onClick = { search() }, enabled = !running && spec.canSearch, modifier = Modifier.fillMaxWidth().padding(top = 6.dp)) {
                    Text(if (running) "Searching..." else "Search")
                }
                if (running) TextButton(onClick = { scope.launch { withContext(Dispatchers.IO) { api.findCancel(jobId) } } }) { Text("Stop searching", color = Blue) }
                if (note.isNotEmpty()) Text(note, color = Muted, fontSize = 14.sp, modifier = Modifier.padding(top = 4.dp))
                val shownSpec = searched
                if (shownSpec != null) {
                    FlowRow(Modifier.padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        shownSpec.chips(boxes).forEach { c -> FindChip(c, true) {} }
                    }
                    if (!running) OutlinedButton(onClick = { saveName = ""; naming = true }, modifier = Modifier.fillMaxWidth().padding(top = 8.dp)) { Text("Save this search", color = Blue) }
                }
            }
            if (searched == null) {
                if (history.recent.isNotEmpty()) item {
                    Text("Recent", color = Muted, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                    FlowRow(Modifier.padding(top = 6.dp), horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        history.recent.forEach { r -> FindChip(r.describe(boxes), false) { search(r) } }
                        TextButton(onClick = { scope.launch { try { withContext(Dispatchers.IO) { api.findClearRecent() } } catch (_: Exception) { }; reload++ } }) { Text("Clear", color = Muted, fontSize = 13.sp) }
                    }
                }
                if (history.saved.isNotEmpty()) {
                    item { Text("Saved searches", color = Muted, fontSize = 13.sp, fontWeight = FontWeight.SemiBold) }
                    items(history.saved, key = { it.id }) { s ->
                        Card(onClick = { search(s.spec) }) {
                            Text(s.name, color = Ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                            Text(s.spec.describe(boxes), color = Muted, fontSize = 13.sp)
                            TextButton(onClick = { scope.launch { try { withContext(Dispatchers.IO) { api.findForget(s.id) } } catch (_: Exception) { }; reload++ } }) { Text("Remove", color = Muted, fontSize = 13.sp) }
                        }
                    }
                }
            }
            items(rows, key = { it.token }) { r ->
                Card(onClick = { reading = r }) {
                    Text(r.subject, color = Ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    Text(r.from, color = Muted, fontSize = 14.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(listOf(r.date.take(10), r.mailbox, r.folder).filter { it.isNotBlank() }.joinToString(" \u00B7 "), color = Muted, fontSize = 12.sp)
                }
            }
            item { if (more && !running) Text("Only the first results are shown. Add more words or a filter to narrow it down.", color = Muted, fontSize = 13.sp) }
        }
    }
}

@Composable
private fun FindChip(label: String, on: Boolean, onClick: () -> Unit) {
    Surface(onClick = onClick, shape = RoundedCornerShape(20.dp), color = if (on) androidx.compose.ui.graphics.Color(0xFF173056) else PanelHigh) {
        Text(label, color = if (on) androidx.compose.ui.graphics.Color(0xFF8DB8FF) else Ink, fontSize = 14.sp, modifier = Modifier.padding(horizontal = 14.dp, vertical = 8.dp), maxLines = 1, overflow = TextOverflow.Ellipsis)
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

// ---------- Folders ----------

/** Full-screen box to pick a folder to move [count] emails into, or to make a new one. */
@Composable
internal fun FolderPicker(api: EnveliqApi, accountId: String, count: Int, prefs: android.content.SharedPreferences, senderName: String? = null, startAlways: Boolean = false, onPick: (FolderInfo, Boolean) -> Unit, onClose: () -> Unit) {
    val scope = rememberCoroutineScope()
    var rows by remember { mutableStateOf<List<FolderInfo>?>(null) }
    var err by remember { mutableStateOf("") }
    var find by remember { mutableStateOf("") }
    var fresh by remember { mutableStateOf("") }
    var making by remember { mutableStateOf(false) }
    var always by remember { mutableStateOf(startAlways) }
    val key = "recent_folders_" + accountId
    val recent = (prefs.getString(key, "") ?: "").split("\n").filter { it.isNotBlank() }
    LaunchedEffect(accountId) {
        try { rows = withContext(Dispatchers.IO) { api.folders(accountId) } }
        catch (e: ApiException) { err = e.message ?: "Could not read your folders." }
        catch (e: Exception) { err = "Could not read your folders. Check your connection." }
    }
    fun choose(f: FolderInfo) {
        prefs.edit().putString(key, (listOf(f.name) + recent.filter { it != f.name }).take(6).joinToString("\n")).apply()
        onPick(f, always && senderName != null)
    }
    androidx.compose.ui.window.Dialog(onDismissRequest = onClose, properties = androidx.compose.ui.window.DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(color = androidx.compose.ui.graphics.Color.Unspecified.let { Navy }, modifier = Modifier.fillMaxSize()) {
            Column(Modifier.fillMaxSize().imePadding()) {
                Row(Modifier.fillMaxWidth().background(Panel).padding(horizontal = 16.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(if (count == 1) "Move this email to…" else "Move $count emails to…", color = Ink, fontSize = 18.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                    TextButton(onClick = onClose) { Text("Close", color = Blue, fontSize = 16.sp) }
                }
                OutlinedTextField(value = find, onValueChange = { find = it }, singleLine = true, placeholder = { Text("Find a folder") }, modifier = Modifier.fillMaxWidth().padding(16.dp, 12.dp, 16.dp, 4.dp))
                val shown = (rows ?: emptyList()).filter { it.target && (find.isBlank() || it.label.contains(find.trim(), ignoreCase = true)) }
                    .sortedWith(compareBy({ val i = recent.indexOf(it.name); if (i < 0) 99 else i }, { it.label.lowercase() }))
                LazyColumn(Modifier.weight(1f).padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (err.isNotEmpty()) item { Text(err, color = Red, fontSize = 15.sp, modifier = Modifier.padding(8.dp)) }
                    else if (rows == null) item { Box(Modifier.fillMaxWidth().padding(24.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator(color = Blue) } }
                    else if (shown.isEmpty()) item { Text(if (rows!!.any { it.target }) "No folder matches that." else "You have no folders of your own yet. Make one below.", color = Muted, fontSize = 15.sp, modifier = Modifier.padding(8.dp)) }
                    items(shown, key = { it.name }) { f -> Card(onClick = { choose(f) }) { Text(f.label, color = Ink, fontSize = 17.sp) } }
                }
                if (senderName != null) Row(Modifier.fillMaxWidth().background(Panel).padding(horizontal = 16.dp, vertical = 8.dp), verticalAlignment = Alignment.Top) {
                    androidx.compose.material3.Checkbox(checked = always, onCheckedChange = { always = it })
                    Column(Modifier.padding(start = 6.dp, top = 12.dp)) {
                        Text("Always move new email from " + senderName + " into the folder I pick", color = Ink, fontSize = 15.sp)
                        Text("It leaves the Inbox. To keep it in the Inbox too, use Tags.", color = Muted, fontSize = 12.sp, modifier = Modifier.padding(top = 2.dp))
                    }
                }
                Row(Modifier.fillMaxWidth().background(Panel).navigationBarsPadding().padding(12.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(value = fresh, onValueChange = { fresh = it.take(80) }, singleLine = true, placeholder = { Text("Or make a new folder") }, modifier = Modifier.weight(1f))
                    Button(enabled = fresh.isNotBlank() && !making, onClick = {
                        making = true
                        scope.launch {
                            try { choose(withContext(Dispatchers.IO) { api.makeFolder(accountId, fresh.trim()) }) }
                            catch (e: ApiException) { err = e.message ?: "That folder could not be made." }
                            catch (e: Exception) { err = "That folder could not be made. Check your connection." }
                            making = false
                        }
                    }) { Text("Make it") }
                }
            }
        }
    }
}

/** Folders: the mailbox's folders as chips, and the newest emails in the chosen one. Read live, never kept. */
@Composable
internal fun FoldersPage(api: EnveliqApi, accountIds: List<String>, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    var acct by remember { mutableStateOf(accountIds.firstOrNull() ?: "") }
    var chosen by remember { mutableStateOf<FolderInfo?>(null) }
    val rows = remember { androidx.compose.runtime.mutableStateListOf<FolderMail>() }
    var total by remember { mutableStateOf(0) }
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
    fun open(f: FolderInfo, offset: Int) {
        if (offset == 0) { rows.clear(); chosen = f }
        note = "Reading " + f.label + "…"
        scope.launch {
            try {
                val p = withContext(Dispatchers.IO) { api.folderMail(acct, f.name, offset) }
                rows.addAll(p.rows); total = p.total; more = p.more
                note = if (p.total == 0) f.label + " is empty." else f.label + ": " + p.total + (if (p.total == 1) " email" else " emails") + ", newest first."
            } catch (e: ApiException) { note = e.message ?: "Could not open that folder." }
            catch (e: Exception) { note = "Could not open that folder. Check your connection." }
        }
    }
    SubPage("Folders", onBack = onBack) {
        Loader(0, { api.folders(acct) }) { folders ->
            LazyColumn(Modifier.fillMaxSize().padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                if (folders.isEmpty()) item { Empty("This mailbox has no other folders.") }
                item {
                    androidx.compose.foundation.layout.FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        for (f in folders) {
                            val on = chosen?.name == f.name
                            Surface(color = if (on) androidx.compose.ui.graphics.Color(0xFF173056) else PanelHigh, shape = RoundedCornerShape(20.dp), modifier = Modifier.clickable { open(f, 0) }) {
                                Text(f.label, color = if (on) androidx.compose.ui.graphics.Color(0xFF8DB8FF) else Ink, fontSize = 14.sp, modifier = Modifier.padding(horizontal = 14.dp, vertical = 8.dp))
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
                if (more) item { TextButton(onClick = { chosen?.let { open(it, rows.size) } }) { Text("Show more", color = Blue) } }
                item { Text("Read from your mailbox when you look. Nothing is saved in Enveliq.", color = Muted, fontSize = 12.sp, modifier = Modifier.padding(vertical = 8.dp)) }
            }
        }
    }
}
