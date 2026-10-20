package app.enveliq

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.os.Build
import android.provider.Settings
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.clickable
import androidx.compose.ui.semantics.CustomAccessibilityAction
import androidx.compose.ui.semantics.customActions
import androidx.compose.ui.semantics.semantics
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.border
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Create
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.filled.Email
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.DrawerValue
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.IconButton
import androidx.compose.material3.ModalDrawerSheet
import androidx.compose.material3.ModalNavigationDrawer
import androidx.compose.material3.NavigationDrawerItem
import androidx.compose.material3.NavigationDrawerItemDefaults
import androidx.compose.material3.rememberDrawerState
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.ArrowDropDown
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Delete
import androidx.compose.ui.layout.layout
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.foundation.layout.RowScope
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SwipeToDismissBox
import androidx.compose.material3.SwipeToDismissBoxValue
import androidx.compose.material3.rememberSwipeToDismissBoxState
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarDuration
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.SnackbarResult
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.util.Calendar
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

private enum class Stage { Opening, SignIn, Welcome, Home }
@Composable
private fun RowScope.ReplyAction(label: String, onClick: () -> Unit, icon: @Composable () -> Unit) {
    OutlinedButton(
        onClick = onClick, modifier = Modifier.weight(1f).height(44.dp).semantics { contentDescription = label },
        shape = RoundedCornerShape(12.dp), border = BorderStroke(1.dp, Line), contentPadding = androidx.compose.foundation.layout.PaddingValues(0.dp),
    ) { icon() }
}

/** Quick ways to add a task for this email: the date is one tap. */
@Composable
private fun AddTaskPopup(mail: Mail, api: EnveliqApi, onClose: () -> Unit, onDone: (String) -> Unit) {
    var title by remember(mail.id) { mutableStateOf("") }
    var busy by remember(mail.id) { mutableStateOf(false) }
    var problem by remember(mail.id) { mutableStateOf("") }
    val scope = rememberCoroutineScope()
    fun day(add: Int): String {
        val c = Calendar.getInstance()
        c.add(Calendar.DAY_OF_YEAR, add)
        return String.format(java.util.Locale.US, "%04d-%02d-%02d", c.get(Calendar.YEAR), c.get(Calendar.MONTH) + 1, c.get(Calendar.DAY_OF_MONTH))
    }
    val toSaturday = (Calendar.SATURDAY - Calendar.getInstance().get(Calendar.DAY_OF_WEEK) + 7) % 7
    val toMonday = ((Calendar.MONDAY - Calendar.getInstance().get(Calendar.DAY_OF_WEEK) + 7) % 7).let { if (it == 0) 7 else it }
    fun add(on: String, label: String) {
        if (busy) return
        busy = true
        problem = ""
        val words = title.trim().ifBlank { "Follow up: " + mail.subject.take(80) }
        scope.launch {
            try {
                withContext(Dispatchers.IO) { api.addTask(mail, words, on) }
                onDone("Task added for " + label)
            } catch (e: ApiException) {
                problem = e.message ?: "That did not work. Try again."
            } catch (e: Exception) {
                problem = "That did not work. Try again."
            }
            busy = false
        }
    }
    AlertDialog(
        onDismissRequest = { if (!busy) onClose() },
        containerColor = Panel,
        title = { Text("Add a task", color = Ink) },
        text = {
            Column {
                OutlinedTextField(
                    value = title, onValueChange = { title = it.take(300) }, singleLine = true,
                    placeholder = { Text("What to do (optional)") }, modifier = Modifier.fillMaxWidth(),
                )
                Text("When?", color = Muted, fontSize = 13.sp, modifier = Modifier.padding(top = 10.dp))
                listOf(
                    Triple("Today", 0, "today"), Triple("Tomorrow", 1, "tomorrow"),
                    Triple("This weekend", toSaturday, "the weekend"), Triple("Next week", toMonday, "next week"),
                ).forEach { (label, ahead, said) ->
                    TextButton(onClick = { add(day(ahead), said) }, enabled = !busy) { Text(label, color = Blue, fontSize = 16.sp) }
                }
                if (problem.isNotEmpty()) Text(problem, color = Red, fontSize = 14.sp)
            }
        },
        confirmButton = {},
        dismissButton = { TextButton(onClick = onClose, enabled = !busy) { Text("Cancel", color = Muted) } },
    )
}

private enum class Tab { Inbox, Tasks, Drafts, More, Settings }

@Composable
fun EnveliqApp(activity: MainActivity) {
    val prefs = remember { activity.getSharedPreferences("enveliq", Context.MODE_PRIVATE) }
    val kept = remember { SessionVault.load(activity) }
    var stage by remember { mutableStateOf(if (kept != null) Stage.Opening else Stage.SignIn) }
    var api by remember { mutableStateOf<EnveliqApi?>(null) }
    var server by remember { mutableStateOf("") }
    var notice by remember { mutableStateOf("") }
    var startOnSettings by remember { mutableStateOf(false) }

    // A kept sign-in is tried first, so you land straight in your inbox.
    LaunchedEffect(Unit) {
        if (kept == null) return@LaunchedEffect
        try {
            val client = EnveliqApi(kept.first)
            withContext(Dispatchers.IO) { client.restore(kept.second) }
            api = client
            server = kept.first
            stage = Stage.Home
        } catch (e: ApiException) {
            if (e.code == 401) SessionVault.clear(activity)
            notice = if (e.code == 401) "You were signed out. Please sign in again." else (e.message ?: "Could not reach your Enveliq.")
            stage = Stage.SignIn
        } catch (e: Exception) {
            notice = "Could not reach your Enveliq. Try again."
            stage = Stage.SignIn
        }
    }

    // Shown once on this phone, once you are in: what Enveliq is and is not. "I understand" is remembered here.
    var termsSeen by remember { mutableStateOf(prefs.getBoolean("terms_ack", false)) }
    if (!termsSeen && (stage == Stage.Home || stage == Stage.Welcome) && server.isNotEmpty()) {
        TermsNotice(server) { prefs.edit().putBoolean("terms_ack", true).apply(); termsSeen = true }
    }

    when (stage) {
        Stage.Opening -> Box(Modifier.fillMaxSize().background(Navy), contentAlignment = Alignment.Center) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                CircularProgressIndicator(color = Blue)
                Text("Opening your inbox…", color = Muted, fontSize = 15.sp, modifier = Modifier.padding(top = 14.dp))
            }
        }
        Stage.SignIn -> {
            SignInScreen(
                initialAddress = prefs.getString("server", "") ?: "",
                notice = notice,
                linkCode = activity.linkCode,
                onLinkUsed = { activity.linkCode = null },
                onDone = { client, address, keep ->
                    prefs.edit().putString("server", address).apply()
                    if (keep) SessionVault.save(activity, address, client.sessionCookies()) else {
                        SessionVault.clear(activity)
                        AlertPrefs.reset(activity)          // alerts need a kept sign-in
                        MailWatcherService.stop(activity)
                    }
                    api = client
                    server = address
                    // A brand-new sign-in on this phone starts with a short, calm welcome; after that it never comes back.
                    stage = if (prefs.getBoolean("welcomed", false)) Stage.Home else Stage.Welcome
                },
            )
        }
        Stage.Welcome -> WelcomeScreen { openSettings ->
            prefs.edit().putBoolean("welcomed", true).apply()
            startOnSettings = openSettings
            stage = Stage.Home
        }
        Stage.Home -> {
            val client = api
            if (client != null) HomeScreen(
                activity = activity,
                prefs = prefs,
                api = client,
                server = server,
                startOnSettings = startOnSettings,
                onLeave = { signedOutByServer ->
                    val pushId = AlertPrefs.pushDevice(activity)
                    Thread {
                        if (pushId != null) try { client.unregisterPush(pushId) } catch (_: Exception) { }
                        client.signOut()
                    }.start()
                    if (pushId != null) Push.stop(activity)
                    SessionVault.clear(activity)
                    AlertPrefs.reset(activity)
                    MailWatcherService.stop(activity)
                    WaitingWidget.clear(activity)
                    EnveliqApi.forgetSession()
                    api = null
                    notice = if (signedOutByServer) "You were signed out. Please sign in again." else ""
                    stage = Stage.SignIn
                },
            )
        }
    }
}

@Composable
private fun HomeScreen(activity: MainActivity, prefs: SharedPreferences, api: EnveliqApi, server: String, startOnSettings: Boolean = false, onLeave: (Boolean) -> Unit) {
    val mails = remember { mutableStateListOf<Mail>() }
    var loading by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }
    var tab by remember { mutableStateOf(if (startOnSettings) Tab.Settings else Tab.Inbox) }
    var opened by remember { mutableStateOf<Mail?>(null) }
    var loaded by remember { mutableStateOf(false) }
    var view by remember { mutableStateOf("inbox") }
    val inboxList = rememberLazyListState()
    val drawer = rememberDrawerState(DrawerValue.Closed)
    var searching by remember { mutableStateOf(false) }
    var query by remember { mutableStateOf("") }
    var me by remember { mutableStateOf<Me?>(null) }
    var picture by remember { mutableStateOf<android.graphics.Bitmap?>(null) }
    LaunchedEffect(Unit) {
        try {
            val who = withContext(Dispatchers.IO) { api.me() }
            me = who
            val bytes = withContext(Dispatchers.IO) { api.avatar(who) }
            if (bytes != null) picture = android.graphics.BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
        } catch (_: Exception) {
        }
    }
    val snack = remember { SnackbarHostState() }
    val scope = rememberCoroutineScope()

    // "Include read mail": a setting that stays on until you switch it off, even after the app is closed.
    var includeRead by remember { mutableStateOf(prefs.getBoolean("include_read", false)) }
    var includeReadOk by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { includeReadOk = withContext(Dispatchers.IO) { api.includeReadAvailable() } }

    // Which emails you have opened in Enveliq. The ones you have not opened glow softly in the list.
    val openedKeys = remember { androidx.compose.runtime.mutableStateMapOf<String, Boolean>() }
    var openedLoaded by remember { mutableStateOf(false) }
    suspend fun loadOpened() {
        try {
            val keys = withContext(Dispatchers.IO) { api.openedKeys() }
            keys.forEach { openedKeys[it] = true }
            openedLoaded = true
        } catch (_: Exception) { }
    }

    fun load() {
        loading = true
        error = ""
        scope.launch {
            loadOpened()
            if (!includeReadOk) includeReadOk = withContext(Dispatchers.IO) { api.includeReadAvailable() }
            try {
                val list = withContext(Dispatchers.IO) { api.inbox(view, includeRead) }
                mails.clear()
                mails.addAll(list)
                if (view == "inbox") WaitingWidget.update(activity, list.count { !it.quiet })
                if (view == "inbox") Notifier.clearGone(activity, list.map { it.id }, AlertPrefs.alerted(activity))     // reviewed elsewhere: take its alert down
            } catch (e: ApiException) {
                if (e.code == 401) {
                    onLeave(true)
                } else {
                    error = e.message ?: "Could not load your email."
                }
            } catch (e: Exception) {
                error = "Could not load your email."
            } finally {
                loading = false
                loaded = true
            }
        }
    }

    LaunchedEffect(view) { load() }

    // After "Generate summary": look again every few seconds (for about two minutes) and show the summary when it is ready.
    fun watchSummary(m: Mail) {
        scope.launch {
            repeat(24) {
                delay(5000)
                try {
                    val list = withContext(Dispatchers.IO) { api.inbox(view, includeRead) }
                    val found = list.firstOrNull { it.id == m.id && it.accountId == m.accountId }
                    mails.clear(); mails.addAll(list)
                    if (found != null && opened?.id == m.id) opened = found
                    if (found == null || !found.ungenerated) return@launch
                } catch (_: Exception) { }
            }
        }
    }

    // Tapping a new-email alert opens that email. If the list is already showing, it is refreshed first.
    val request = activity.openRequest
    LaunchedEffect(request) { if (request != null && loaded) load() }
    LaunchedEffect(request, loaded, loading, mails.size) {
        val r = activity.openRequest ?: return@LaunchedEffect
        if (!loaded || loading) return@LaunchedEffect
        val found = mails.firstOrNull { it.id == r.second && it.accountId == r.first }
        if (found != null) {
            tab = Tab.Inbox
            opened = found
        }
        activity.openRequest = null
    }
    BackHandler(enabled = opened != null) { opened = null }
    BackHandler(enabled = drawer.isOpen) { scope.launch { drawer.close() } }

    val selected = remember { mutableStateListOf<String>() }
    var askSnooze by remember { mutableStateOf(false) }
    var askTask by remember { mutableStateOf(false) }
    var taskVersion by remember { mutableStateOf(0) }          // goes up when a task is added, so the open email shows it at once
    var tagPicker by remember { mutableStateOf<Pair<Mail, TagInfo>?>(null) }
    val tagMap = remember { mutableStateMapOf<String, List<String>>() }
    var composing by remember { mutableStateOf<ComposeTarget?>(null) }
    // Back from Tasks, Drafts, More or Settings goes to the inbox first; Back from the inbox leaves the app.
    BackHandler(enabled = tab != Tab.Inbox && opened == null && composing == null) { tab = Tab.Inbox }
    // Back from a filtered inbox (Reviewed, Archived, needs action, a mailbox or a tag) clears the filters and shows the whole inbox.
    // Only then does Back leave the app.
    val filters = remember { InboxFilters() }
    BackHandler(enabled = tab == Tab.Inbox && opened == null && composing == null && !drawer.isOpen && selected.isEmpty() &&
        (view != "inbox" || filters.active)) {
        view = "inbox"; filters.clear()
    }
    // With emails ticked, Back unticks them first instead of leaving the app.
    BackHandler(enabled = tab == Tab.Inbox && opened == null && composing == null && !drawer.isOpen && selected.isNotEmpty()) {
        selected.clear()
    }
    // "Share" from another app: the text arrives in a new email, ready to address.
    val shared = activity.shareRequest
    LaunchedEffect(shared) {
        val sh = activity.shareRequest ?: return@LaunchedEffect
        composing = ComposeTarget("new", presetSubject = sh.first, presetBody = sh.second)
        activity.shareRequest = null
    }
    // A "mailto:" link from another app: a new email with the address filled in, ready to check and send.
    val mailto = activity.mailtoRequest
    LaunchedEffect(mailto) {
        val mt = activity.mailtoRequest ?: return@LaunchedEffect
        composing = ComposeTarget("new", presetSubject = mt.second, presetBody = mt.third, presetTo = mt.first)
        activity.mailtoRequest = null
    }
    fun keyOf(m: Mail) = m.accountId + ":" + m.id
    // Opening an email (from the list, an alert or anywhere else) records it as opened.
    val openedNow = opened
    LaunchedEffect(openedNow?.id) {
        val m = openedNow ?: return@LaunchedEffect
        if (openedKeys[keyOf(m)] != true) {
            openedKeys[keyOf(m)] = true
            try { withContext(Dispatchers.IO) { api.markOpened(m) } } catch (_: Exception) { }
        }
    }

    // The Tag button: finds out which tags this mailbox offers, then opens the picker.
    fun openTags(m: Mail) {
        scope.launch {
            var problem = ""
            val info = try {
                withContext(Dispatchers.IO) { api.tagInfo(m.accountId) }
            } catch (e: ApiException) {
                if (e.code == 401) { onLeave(true); return@launch }
                problem = e.message ?: "Could not load the tags."
                null
            } catch (e: Exception) {
                problem = "Could not load the tags. Please try again."
                null
            }
            if (info != null) tagPicker = m to info else snack.showSnackbar(problem.ifBlank { "Your mail service does not keep tags." })
        }
    }

    // Puts the unread mark back on an email you had marked Reviewed. It goes back to the inbox.
    fun markUnread(m: Mail) {
        val at = mails.indexOf(m).coerceAtLeast(0)
        mails.remove(m)
        opened = null
        scope.launch {
            try {
                withContext(Dispatchers.IO) { api.markUnread(m) }
                snack.showSnackbar("Marked unread. It is back in your inbox.")
            } catch (e: ApiException) {
                mails.add(at.coerceAtMost(mails.size), m)
                snack.showSnackbar(e.message ?: "That did not work.")
            } catch (e: Exception) {
                mails.add(at.coerceAtMost(mails.size), m)
                snack.showSnackbar("That did not work. Please try again.")
            }
        }
    }

    // The emails leave the list at once. They are only marked at your mailbox when the Undo time has passed.
    fun resolveAll(items: List<Mail>, outcome: Outcome, onCommitted: (() -> Unit)? = null) {
        if (items.isEmpty()) return
        val placed = items.map { it to mails.indexOf(it).coerceAtLeast(0) }
        // "Open the next email" (a Settings choice): after archiving or reviewing the one you were reading, the next one in the list opens.
        val next = if (items.size == 1 && opened == items[0] && prefs.getBoolean("open_next", false) && (outcome == Outcome.Archived || outcome == Outcome.Reviewed))
            mails.getOrNull(mails.indexOf(items[0]) + 1) else null
        items.forEach { mails.remove(it); Notifier.clearOne(activity, it.id) }
        selected.clear()
        opened = next
        scope.launch {
            val label = if (items.size == 1) outcome.done else outcome.done + " (" + items.size + ")"
            val result = snack.showSnackbar(message = label, actionLabel = "Undo", duration = SnackbarDuration.Short)
            fun putBack(list: List<Pair<Mail, Int>>) {
                list.sortedBy { it.second }.forEach { (m, at) -> mails.add(at.coerceAtMost(mails.size), m) }
            }
            if (result == SnackbarResult.ActionPerformed) {
                putBack(placed)
            } else {
                val failed = ArrayList<Pair<Mail, Int>>()
                for (p in placed) {
                    try {
                        withContext(Dispatchers.IO) { api.resolve(p.first, outcome) }
                    } catch (e: Exception) {
                        failed.add(p)
                    }
                }
                if (failed.isNotEmpty()) {
                    putBack(failed)
                    snack.showSnackbar("That did not work for " + failed.size + ". They are back in your list.")
                } else {
                    onCommitted?.invoke()
                }
            }
        }
    }

    fun resolve(mail: Mail, outcome: Outcome) = resolveAll(listOf(mail), outcome)

    // Junk: the email goes to the mailbox's Junk folder. "Block" also sends everything from that sender there from now on.
    // The block is only made once the Undo time has passed, so Undo takes back both.
    fun junk(mail: Mail, block: Boolean) = resolveAll(listOf(mail), Outcome.Junked) {
        if (block && mail.address.isNotBlank()) {
            scope.launch {
                try {
                    withContext(Dispatchers.IO) { api.blockSender(mail.address) }
                    snack.showSnackbar("Blocked. New email from " + mail.address + " goes to Junk.")
                } catch (e: Exception) {
                    snack.showSnackbar((e as? ApiException)?.message ?: "The email is in Junk, but blocking the sender did not work.")
                }
            }
        }
    }

    // Snooze: the email leaves the list until the time you pick, then comes back. Undo brings it back at once.
    fun snooze(mail: Mail, until: Long, label: String) {
        val at = mails.indexOf(mail).coerceAtLeast(0)
        mails.remove(mail)
        Notifier.clearOne(activity, mail.id)
        opened = null
        scope.launch {
            val result = snack.showSnackbar(message = "Back $label", actionLabel = "Undo", duration = SnackbarDuration.Short)
            if (result == SnackbarResult.ActionPerformed) {
                mails.add(at.coerceAtMost(mails.size), mail)
            } else {
                try {
                    withContext(Dispatchers.IO) { api.snooze(mail, until / 1000.0) }
                } catch (e: Exception) {
                    mails.add(at.coerceAtMost(mails.size), mail)
                    snack.showSnackbar((e.message ?: "That did not work.") + " The email is back in your list.")
                }
            }
        }
    }

    // After a send: say so, and while the "undo send" time lasts, let the person take it back.
    fun afterSend(result: Sent) {
        composing = null
        scope.launch {
            if (result.scheduledId.isNotEmpty()) {
                val answer = snack.showSnackbar(message = "It will be sent " + result.scheduledText, actionLabel = "Undo", duration = SnackbarDuration.Long)
                if (answer == SnackbarResult.ActionPerformed) {
                    try {
                        withContext(Dispatchers.IO) { api.cancelWaiting(result.scheduledId) }
                        snack.showSnackbar("Taken back. It will not be sent.")
                    } catch (e: Exception) {
                        snack.showSnackbar("Could not take it back. Look under More, Waiting to send.")
                    }
                }
            } else if (result.queued && result.secondsLeft > 0) {
                val timer = launch {
                    delay(result.secondsLeft * 1000L)
                    snack.currentSnackbarData?.dismiss()
                }
                val answer = snack.showSnackbar(
                    message = "Sending in " + result.secondsLeft + " seconds", actionLabel = "Undo", duration = SnackbarDuration.Indefinite,
                )
                timer.cancel()
                if (answer == SnackbarResult.ActionPerformed) {
                    try {
                        withContext(Dispatchers.IO) { api.cancelSend(result.outboxId) }
                        snack.showSnackbar("Not sent. The email was taken back.")
                    } catch (e: Exception) {
                        snack.showSnackbar("It may already have been sent.")
                    }
                }
            } else {
                snack.showSnackbar("Sent")
            }
        }
    }

    fun mailForDraft(d: Draft): Mail? {
        if (d.kind == "new") return null
        return mails.firstOrNull { it.id == d.messageId && it.accountId == d.accountId }
            ?: Mail(
                id = d.messageId, accountId = d.accountId, sender = "", address = "",
                subject = d.subject.removePrefix("Re: ").removePrefix("Fwd: "), summary = "", whenText = "", needsAction = false,
            )
    }

    val writing = composing
    if (writing != null) {
        ComposeScreen(writing, api, onClose = { composing = null }, onSent = { afterSend(it) })
        return
    }

    val current = opened
    var moreStart by remember { mutableStateOf("home") }
    var moreKey by remember { mutableStateOf(0) }
    var bellUnread by remember { mutableStateOf(false) }
    LaunchedEffect(tab, moreKey) {
        bellUnread = try { withContext(Dispatchers.IO) { api.bell() }.any { it.unread } } catch (_: Exception) { false }
    }
    fun goTo(t: Tab) { moreStart = "home"; moreKey++; tab = t; opened = null; scope.launch { drawer.close() } }
    ModalNavigationDrawer(
        drawerState = drawer,
        gesturesEnabled = drawer.isOpen,      // opened with the menu button; swiping the list is for archiving, so the edge swipe is left off
        drawerContent = {
            ModalDrawerSheet(drawerContainerColor = Panel) {
                androidx.compose.foundation.Image(
                    androidx.compose.ui.res.painterResource(R.drawable.wordmark), contentDescription = "Enveliq",
                    modifier = Modifier.padding(start = 24.dp, top = 24.dp, bottom = 16.dp).height(40.dp),
                )
                val colors = NavigationDrawerItemDefaults.colors(
                    selectedContainerColor = PanelHigh, unselectedContainerColor = Panel,
                    selectedTextColor = Blue, unselectedTextColor = Ink, selectedIconColor = Blue, unselectedIconColor = Muted,
                )
                listOf(
                    Triple(Tab.Inbox, "Inbox", Icons.Filled.Email), Triple(Tab.Tasks, "Tasks", Icons.Filled.CheckCircle),
                    Triple(Tab.Drafts, "Drafts", Icons.Filled.Edit), Triple(Tab.More, "More", Icons.Filled.Menu),
                    Triple(Tab.Settings, "Settings", Icons.Filled.Settings),
                ).forEach { (t, label, icon) ->
                    NavigationDrawerItem(
                        label = { Text(label, fontSize = 16.sp) }, selected = tab == t, onClick = { goTo(t) },
                        icon = { Icon(icon, contentDescription = null) }, colors = colors,
                        modifier = Modifier.padding(NavigationDrawerItemDefaults.ItemPadding),
                    )
                }
            }
        },
    ) {
    Scaffold(
        containerColor = Navy,
        snackbarHost = { SnackbarHost(snack) },
        floatingActionButton = {
            if (current == null && tab == Tab.Inbox && selected.isEmpty()) {
                FloatingActionButton(onClick = { composing = ComposeTarget("new") }, containerColor = Blue, contentColor = Navy) {
                    Icon(Icons.Filled.Create, contentDescription = "New email")
                }
            }
        },
        bottomBar = {
            if (current != null) {
                ActionBar(
                    onResolve = { outcome -> resolve(current, outcome) }, onSnooze = { askSnooze = true },
                    onTag = { openTags(current) }, onTask = { askTask = true },
                    onUnread = if (current.state == "reviewed") ({ markUnread(current) }) else null,
                )
            } else if (selected.isNotEmpty() && tab == Tab.Inbox) {
                val chosen = mails.filter { selected.contains(keyOf(it)) }
                SelectionBar(chosen.size, onResolve = { outcome -> resolveAll(chosen, outcome) }, onCancel = { selected.clear() })
            }
        },
    ) { inner ->
        tagPicker?.let { (m, info) ->
            TagPickerScreen(m, api, info, tagMap[keyOf(m)] ?: m.tags, onClose = { tagPicker = null }, onSaved = { tagMap[keyOf(m)] = it; tagPicker = null })
        }
        if (askTask && current != null) {
            AddTaskPopup(current, api, onClose = { askTask = false }, onDone = { msg -> askTask = false; taskVersion++; scope.launch { snack.showSnackbar(msg) } })
        }
        if (askSnooze && current != null) {
            SnoozeChoices(onPick = { until, label -> askSnooze = false; snooze(current, until, label) }, onCancel = { askSnooze = false })
        }
        // A wide screen (a tablet, or a phone on its side) shows the list and the open email side by side.
        val wide = androidx.compose.ui.platform.LocalConfiguration.current.screenWidthDp >= 720
        val inboxPane: @Composable () -> Unit = {
            InboxTab(
                        mails, loading, error, inboxList, selected, view, filters, onView = { view = it; selected.clear() },
                        searching = searching, query = query, onQuery = { query = it },
                        swipeRight = prefs.getString("swipe_right", "archive") ?: "archive",
                        swipeLeft = prefs.getString("swipe_left", "bin") ?: "bin",
                        tagsOf = { m -> tagMap[keyOf(m)] ?: m.tags },
                        fresh = { m -> openedLoaded && view == "inbox" && !m.quiet && openedKeys[keyOf(m)] != true },
                        includeRead = includeRead, includeReadOk = includeReadOk,
                        onIncludeRead = { on -> includeRead = on; prefs.edit().putBoolean("include_read", on).apply(); load() },
                        onOpen = { opened = it },
                        onSwipe = { m, outcome -> resolve(m, outcome) },
                        onRefresh = { load() },
                    )
        }
        val topBar: @Composable () -> Unit = {
            AppTopBar(
                me, picture, showSearch = tab == Tab.Inbox, searching = searching,
                onMenu = { scope.launch { drawer.open() } },
                onSearch = { searching = !searching; if (!searching) query = "" },
                onAccount = { try { activity.startActivity(Intent(Intent.ACTION_VIEW, android.net.Uri.parse(EnveliqApi.normalise(server) + "/account"))) } catch (_: Exception) { } },
                onSettings = { goTo(Tab.Settings) },
                bellUnread = bellUnread,
                onBell = { tab = Tab.More; opened = null; moreStart = "bell"; moreKey++ },
            )
        }
        Column(Modifier.padding(inner).fillMaxSize()) {
          if (current == null || wide) topBar()
          Box(Modifier.weight(1f).fillMaxWidth()) {
            if (wide && tab == Tab.Inbox) {
                Row(Modifier.fillMaxSize()) {
                    Box(Modifier.weight(0.42f).fillMaxHeight()) { inboxPane() }
                    Box(Modifier.weight(0.58f).fillMaxHeight()) {
                        if (current != null) DetailBody(current, tagMap[keyOf(current)] ?: current.tags, api, onBack = { opened = null }, onCompose = { kind -> composing = ComposeTarget(kind, current) }, onJunk = { block -> junk(current, block) }, onAskedSummary = { watchSummary(current) }, taskVersion = taskVersion)
                        else Text("Choose an email to read it here.", color = Muted, fontSize = 16.sp, modifier = Modifier.padding(32.dp))
                    }
                }
            } else if (current != null) {
                DetailBody(current, tagMap[keyOf(current)] ?: current.tags, api, onBack = { opened = null }, onCompose = { kind -> composing = ComposeTarget(kind, current) }, onJunk = { block -> junk(current, block) }, onAskedSummary = { watchSummary(current) }, taskVersion = taskVersion)
            } else {
                when (tab) {
                    Tab.Inbox -> inboxPane()
                    Tab.Tasks -> TasksScreen(api, mails, onOpen = { opened = it })
                    Tab.More -> androidx.compose.runtime.key(moreKey) { MoreTab(api, moreStart) }
                    Tab.Drafts -> DraftsTab(api, onOpen = { d -> composing = ComposeTarget(d.kind, mailForDraft(d), d) })
                    Tab.Settings -> SettingsTab(activity, prefs, server, api, onLeave)
                }
            }
          }
        }
    }
    }
}

@Composable
internal fun Heading(title: String, subtitle: String, trailing: @Composable () -> Unit = {}) {
    Row(Modifier.fillMaxWidth().padding(start = 20.dp, end = 8.dp, top = 14.dp, bottom = 6.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(title, color = Ink, fontSize = 28.sp, fontWeight = FontWeight.Bold)
            if (subtitle.isNotEmpty()) Text(subtitle, color = Muted, fontSize = 14.sp, modifier = Modifier.padding(top = 2.dp))
        }
        trailing()
    }
}

/** The inbox filters that are not the Inbox/Reviewed/Archived choice. Kept here so Back can clear them. */
internal class InboxFilters {
    var onlyAction by mutableStateOf(false)
    var tag by mutableStateOf<String?>(null)
    var box by mutableStateOf<String?>(null)
    val active: Boolean get() = onlyAction || tag != null || box != null
    fun clear() { onlyAction = false; tag = null; box = null }
}

@OptIn(ExperimentalMaterial3Api::class, ExperimentalFoundationApi::class)
@Composable
private fun InboxTab(
    mails: List<Mail>, loading: Boolean, error: String, listState: LazyListState, selected: MutableList<String>,
    view: String, filters: InboxFilters, onView: (String) -> Unit,
    searching: Boolean, query: String, onQuery: (String) -> Unit,
    swipeRight: String, swipeLeft: String,
    fresh: (Mail) -> Boolean, tagsOf: (Mail) -> List<String>,
    includeRead: Boolean, includeReadOk: Boolean, onIncludeRead: (Boolean) -> Unit,
    onOpen: (Mail) -> Unit, onSwipe: (Mail, Outcome) -> Unit, onRefresh: () -> Unit,
) {
    var onlyAction by filters::onlyAction
    var tag by filters::tag
    var box by filters::box
    val q = query.trim()
    var pickingTag by remember { mutableStateOf(false) }
    var viewMenu by remember { mutableStateOf(false) }
    var otherMenu by remember { mutableStateOf(false) }
    val tagCounts = mails.flatMap { it.tags }.groupBy { it.lowercase() }.values.map { it.first() to it.size }.sortedBy { it.first.lowercase() }
    val boxes = mails.map { it.mailbox }.filter { it.isNotBlank() }.distinct()
    val base = mails.filter {
        (!onlyAction || it.needsAction) &&
            (tag == null || it.tags.any { t -> t.equals(tag, ignoreCase = true) }) &&
            (box == null || it.mailbox == box)
    }
    val shown = if (q.length < 2) base else base.filter {
        it.sender.contains(q, ignoreCase = true) || it.subject.contains(q, ignoreCase = true) ||
            it.summary.contains(q, ignoreCase = true) || it.address.contains(q, ignoreCase = true)
    }
    val needs = mails.count { it.needsAction }
    val selecting = selected.isNotEmpty()
    fun keyOf(m: Mail) = m.accountId + ":" + m.id
    Column(Modifier.fillMaxSize()) {
        // One thin row: where you are, the list filter (Inbox, Reviewed, Archived) and the other filters (needs action, mailbox, tags).
        Row(Modifier.fillMaxWidth().height(40.dp).padding(horizontal = 16.dp), verticalAlignment = Alignment.CenterVertically) {
            if (selecting) {
                Text(selected.size.toString() + " selected", color = Ink, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                TextButton(onClick = { shown.forEach { if (!selected.contains(keyOf(it))) selected.add(keyOf(it)) } }) { Text("Select all", color = Blue, fontSize = 14.sp) }
                TextButton(onClick = { selected.clear() }) { Text("Cancel", color = Blue, fontSize = 14.sp) }
            } else {
                Text(
                    when (view) { "reviewed" -> "Reviewed"; "archived" -> "Archived"; else -> "Inbox" },
                    color = Ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold,
                )
                Box {
                    IconButton(onClick = { viewMenu = true }) { FilterIcon(if (view != "inbox") Blue else Muted) }
                    DropdownMenu(expanded = viewMenu, onDismissRequest = { viewMenu = false }, containerColor = Panel) {
                        listOf("inbox" to "Inbox", "reviewed" to "Reviewed", "archived" to "Archived").forEach { (id, label) ->
                            DropdownMenuItem(text = { Text((if (view == id) "✓  " else "") + label, color = Ink) }, onClick = { viewMenu = false; onView(id) })
                        }
                    }
                }
                val narrowed = onlyAction || tag != null || box != null
                Box {
                    IconButton(onClick = { otherMenu = true }) { TagIcon(if (narrowed) Blue else Muted) }
                    DropdownMenu(expanded = otherMenu, onDismissRequest = { otherMenu = false }, containerColor = Panel) {
                        DropdownMenuItem(text = { Text((if (!narrowed) "✓  " else "") + "All", color = Ink) }, onClick = { otherMenu = false; onlyAction = false; tag = null; box = null })
                        DropdownMenuItem(text = { Text((if (onlyAction) "✓  " else "") + "Needs action", color = Ink) }, onClick = { otherMenu = false; onlyAction = !onlyAction })
                        if (boxes.size > 1) boxes.forEach { b ->
                            DropdownMenuItem(text = { Text((if (box == b) "✓  " else "") + b, color = Ink) }, onClick = { otherMenu = false; box = if (box == b) null else b })
                        }
                        if (tagCounts.isNotEmpty() || tag != null) DropdownMenuItem(text = { Text((if (tag != null) "✓  # " + tag else "Tags…"), color = Ink) }, onClick = { otherMenu = false; pickingTag = true })
                    }
                }
                if (includeReadOk) {
                    var readMenu by remember { mutableStateOf(false) }
                    Box {
                        IconButton(onClick = { readMenu = true }) { ReadMailIcon(if (includeRead) Blue else Muted) }
                        DropdownMenu(expanded = readMenu, onDismissRequest = { readMenu = false }, containerColor = Panel) {
                            Column(Modifier.widthIn(max = 280.dp).padding(horizontal = 16.dp, vertical = 8.dp)) {
                                Text("Include read mail", color = Ink, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
                                Text(
                                    "Adds mail you\u2019ve already read from the last 60 days. Summaries only when you ask.",
                                    color = Muted, fontSize = 13.sp, lineHeight = 19.sp, modifier = Modifier.padding(top = 4.dp, bottom = 8.dp),
                                )
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Text(if (includeRead) "On" else "Off", color = Ink, fontSize = 14.sp, modifier = Modifier.weight(1f))
                                    androidx.compose.material3.Switch(checked = includeRead, onCheckedChange = { onIncludeRead(it) })
                                }
                            }
                        }
                    }
                }
                Spacer(Modifier.weight(1f))
                Text(
                    if (loading && mails.isEmpty()) "" else if (view == "inbox") "${mails.count { !it.quiet }}" + (if (needs > 0) " · $needs need you" else "") else "${mails.size} kept for a few days",
                    color = Muted, fontSize = 12.sp,
                )
            }
        }
        if (searching) {
            OutlinedTextField(
                value = query, onValueChange = onQuery, singleLine = true,
                placeholder = { Text("Search your inbox") },
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp),
            )
        }
        if (pickingTag) TagFilterScreen(tagCounts, tag, onPick = { tag = it; pickingTag = false }, onClose = { pickingTag = false })
        PullToRefreshBox(isRefreshing = loading && mails.isNotEmpty(), onRefresh = onRefresh, modifier = Modifier.fillMaxSize()) {
        when {
            loading && mails.isEmpty() -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator(color = Blue) }
            error.isNotEmpty() -> Column(Modifier.padding(24.dp)) {
                Text(error, color = Red, fontSize = 16.sp)
                OutlinedButton(onClick = onRefresh, modifier = Modifier.padding(top = 14.dp)) { Text("Try again") }
            }
            shown.isEmpty() -> Text(
                if (q.length >= 2) "Nothing here matches that." else if (view != "inbox") "Nothing here at the moment." else if (tag != null || box != null) "Nothing matches that." else if (onlyAction) "Nothing needs you right now." else "You're all caught up.",
                color = Muted, fontSize = 17.sp, modifier = Modifier.padding(24.dp),
            )
            else -> LazyColumn(Modifier.fillMaxSize(), state = listState) {
                items(shown, key = { it.accountId + ":" + it.id }) { m ->
                    SwipeRow(
                        mail = m, right = swipeRight, left = swipeLeft, selecting = selecting, picked = selected.contains(keyOf(m)), fresh = fresh(m), tags = tagsOf(m),
                        onSwipe = { outcome -> onSwipe(m, outcome) },
                        onClick = { if (selecting) toggle(selected, keyOf(m)) else onOpen(m) },
                        onLongClick = { toggle(selected, keyOf(m)) },
                    )
                }
            }
        }
        }
    }
}

private fun toggle(list: MutableList<String>, key: String) {
    if (!list.remove(key)) list.add(key)
}

/** What a swipe does: "archive", "bin" or "reviewed". Anything else means the swipe is switched off. */
private fun swipeOutcome(name: String): Outcome? = when (name) {
    "archive" -> Outcome.Archived
    "bin" -> Outcome.Binned
    "reviewed" -> Outcome.Reviewed
    else -> null
}

@OptIn(ExperimentalMaterial3Api::class, ExperimentalFoundationApi::class)
@Composable
private fun SwipeRow(
    mail: Mail, right: String, left: String, selecting: Boolean, picked: Boolean, fresh: Boolean, tags: List<String>,
    onSwipe: (Outcome) -> Unit, onClick: () -> Unit, onLongClick: () -> Unit,
) {
    val rightOutcome = swipeOutcome(right)
    val leftOutcome = swipeOutcome(left)
    var chosen by remember { mutableStateOf<Outcome?>(null) }
    var collapsed by remember { mutableStateOf(false) }
    val state = rememberSwipeToDismissBoxState(
        confirmValueChange = { value ->
            val outcome = when (value) {
                SwipeToDismissBoxValue.StartToEnd -> rightOutcome
                SwipeToDismissBoxValue.EndToStart -> leftOutcome
                else -> null
            }
            if (outcome != null) {
                chosen = outcome          // the row finishes its slide and folds away first; only then is it really actioned
                true
            } else {
                false
            }
        },
    )
    // A slower, visible finish: the row slides off, the coloured bar holds for a moment, then the gap folds closed. Then the email is actioned and Undo appears.
    val outcomeNow = chosen
    LaunchedEffect(outcomeNow) {
        if (outcomeNow == null) return@LaunchedEffect
        kotlinx.coroutines.delay(350)
        collapsed = true
        kotlinx.coroutines.delay(450)
        onSwipe(outcomeNow)
    }
    val fold by androidx.compose.animation.core.animateFloatAsState(
        if (collapsed) 0f else 1f, androidx.compose.animation.core.tween(450, easing = androidx.compose.animation.core.FastOutSlowInEasing), label = "fold",
    )
    Box(
        Modifier.layout { measurable, constraints ->
            val p = measurable.measure(constraints)
            val h = (p.height * fold).toInt()
            layout(p.width, h) { p.placeRelative(0, 0) }
        }.graphicsLayer { alpha = fold }.clipToBounds(),
    ) {
    SwipeToDismissBox(
        modifier = Modifier.semantics {
            // Swiping is hard or impossible with a screen reader, so the same actions are offered in TalkBack's actions menu.
            customActions = listOf(
                CustomAccessibilityAction("Mark reviewed") { onSwipe(Outcome.Reviewed); true },
                CustomAccessibilityAction("Archive") { onSwipe(Outcome.Archived); true },
                CustomAccessibilityAction("Move to Bin") { onSwipe(Outcome.Binned); true },
            )
        },
        state = state,
        enableDismissFromStartToEnd = rightOutcome != null && !selecting,
        enableDismissFromEndToStart = leftOutcome != null && !selecting,
        backgroundContent = {
            val toRight = state.dismissDirection == SwipeToDismissBoxValue.StartToEnd
            val outcome = if (toRight) rightOutcome else leftOutcome
            val color = when (outcome) {
                Outcome.Reviewed -> Color(0xFF16382B)
                Outcome.Archived -> Color(0xFF173056)
                Outcome.Binned -> Color(0xFF3A1D22)
                else -> Navy
            }
            val settled = chosen != null || state.targetValue != SwipeToDismissBoxValue.Settled
            val grow by androidx.compose.animation.core.animateFloatAsState(
                if (settled) 1.25f else 0.85f, androidx.compose.animation.core.spring(dampingRatio = 0.4f, stiffness = 300f), label = "grow",
            )
            Box(
                Modifier.fillMaxSize().background(color).padding(horizontal = 24.dp),
                contentAlignment = if (toRight) Alignment.CenterStart else Alignment.CenterEnd,
            ) {
                Row(Modifier.graphicsLayer { scaleX = grow; scaleY = grow }, verticalAlignment = Alignment.CenterVertically) {
                    when (outcome) {
                        Outcome.Reviewed -> Icon(Icons.Filled.Check, contentDescription = null, tint = Green)
                        Outcome.Archived -> ArchiveIcon(Color(0xFF8DB8FF))
                        Outcome.Binned -> Icon(Icons.Filled.Delete, contentDescription = null, tint = Red)
                        else -> {}
                    }
                    Text(
                        when (outcome) { Outcome.Reviewed -> "  Reviewed"; Outcome.Archived -> "  Archive"; Outcome.Binned -> "  Bin"; else -> "" },
                        color = Ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold,
                    )
                }
            }
        },
    ) {
        MailRow(mail, picked, fresh, tags, onClick, onLongClick)
    }
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun MailRow(mail: Mail, picked: Boolean, fresh: Boolean, tags: List<String>, onClick: () -> Unit, onLongClick: () -> Unit) {
    // Three looks: an email you have not opened yet glows softly (a thin blue edge and a faint blue wash);
    // read mail that has no summary yet is plain and quiet; everything else is as before.
    val plain = mail.quiet && mail.ungenerated
    val shape = RoundedCornerShape(12.dp)
    val glow = if (fresh && !picked) Modifier
        .background(androidx.compose.ui.graphics.Brush.horizontalGradient(listOf(Blue.copy(alpha = 0.13f), Color.Transparent)), shape)
        .border(1.dp, Blue.copy(alpha = 0.42f), shape) else Modifier
    Column(
        Modifier.fillMaxWidth().background(if (picked) PanelHigh else Navy).padding(horizontal = 8.dp, vertical = 2.dp)
            .clip(shape).then(glow)
            .combinedClickable(onClick = onClick, onLongClick = onLongClick)
            .padding(horizontal = 12.dp, vertical = 10.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            if (picked) {
                Text("\u2713", color = Blue, fontSize = 16.sp, fontWeight = FontWeight.Bold)
                Spacer(Modifier.size(8.dp))
            } else if (mail.needsAction) {
                Box(Modifier.size(8.dp).clip(CircleShape).background(Amber))
                Spacer(Modifier.size(8.dp))
            }
            Text(
                mail.sender, color = if (plain) Muted else Ink, fontSize = 16.sp, fontWeight = if (plain) FontWeight.Normal else FontWeight.SemiBold,
                maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f),
            )
            if (mail.hasFiles) {
                PaperclipIcon(Muted)
                Spacer(Modifier.size(4.dp))
            }
            Text(mail.whenText, color = Muted, fontSize = 13.sp)
        }
        Text(
            mail.subject, color = if (plain) Muted else Ink, fontSize = 15.sp, fontWeight = if (fresh) FontWeight.Bold else FontWeight.Normal,
            maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(top = 2.dp),
        )
        if (plain) {
            Text("No summary yet", color = Muted, fontSize = 13.sp, fontStyle = androidx.compose.ui.text.font.FontStyle.Italic, modifier = Modifier.padding(top = 3.dp))
        } else if (mail.summary.isNotBlank()) {
            Text("\u2726 " + mail.summary, color = Muted, fontSize = 14.sp, lineHeight = 20.sp, maxLines = 2, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(top = 3.dp))
        }
        // The tags on this email: small, neat chips on one line. Nothing is shown when there are none.
        if (tags.isNotEmpty()) Row(Modifier.padding(top = 6.dp), horizontalArrangement = Arrangement.spacedBy(4.dp), verticalAlignment = Alignment.CenterVertically) {
            tags.take(3).forEach { t ->
                Text(
                    t, color = Blue, fontSize = 11.sp, lineHeight = 14.sp, maxLines = 1, overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.widthIn(max = 110.dp).clip(RoundedCornerShape(6.dp)).background(Blue.copy(alpha = 0.14f)).padding(horizontal = 6.dp, vertical = 1.dp),
                )
            }
            if (tags.size > 3) Text("+" + (tags.size - 3), color = Muted, fontSize = 11.sp)
        }
    }
    HorizontalDivider(color = Line)
}

@Composable
private fun DetailBody(mail: Mail, tags: List<String>, api: EnveliqApi, onBack: () -> Unit, onCompose: (String) -> Unit, onJunk: (Boolean) -> Unit, onAskedSummary: () -> Unit = {}, taskVersion: Int = 0) {
    var summaryAsked by remember(mail.id) { mutableStateOf(false) }
    var showOriginal by remember(mail.id) { mutableStateOf(false) }
    var unsubLink by remember(mail.id) { mutableStateOf<String?>(null) }
    var askBlock by remember(mail.id) { mutableStateOf(false) }
    var moreMenu by remember(mail.id) { mutableStateOf(false) }
    var addressMenu by remember(mail.id) { mutableStateOf(false) }
    val context = androidx.compose.ui.platform.LocalContext.current
    val scope = rememberCoroutineScope()
    var important by remember(mail.id) { mutableStateOf<Boolean?>(null) }
    LaunchedEffect(mail.id) {
        important = try { withContext(Dispatchers.IO) { api.importantAddresses() }.contains(mail.address.lowercase()) } catch (_: Exception) { null }
    }
    fun tell(words: String) = android.widget.Toast.makeText(context, words, android.widget.Toast.LENGTH_LONG).show()

    Column(Modifier.fillMaxSize()) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) { Icon(Icons.Filled.ArrowBack, contentDescription = "Back", tint = Ink) }
        }
        // Everything in the email can be selected and copied: press and hold, then drag.
        androidx.compose.foundation.text.selection.SelectionContainer(Modifier.weight(1f)) {
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 20.dp)) {
            Text(mail.subject, color = Ink, fontSize = 24.sp, fontWeight = FontWeight.Bold, lineHeight = 30.sp)
            Text(mail.sender + if (mail.whenText.isNotEmpty()) " · " + mail.whenText else "", color = Muted, fontSize = 14.sp, modifier = Modifier.padding(top = 6.dp))
            if (mail.address.isNotEmpty()) Box {
                // Tapping the address offers Copy. (Press and hold still selects it like any other text.)
                Text(mail.address, color = Blue, fontSize = 13.sp, modifier = Modifier.clickable { addressMenu = true })
                DropdownMenu(expanded = addressMenu, onDismissRequest = { addressMenu = false }, containerColor = Panel) {
                    DropdownMenuItem(text = { Text("Copy " + mail.address, color = Ink) }, onClick = {
                        addressMenu = false
                        val clip = context.getSystemService(android.content.ClipboardManager::class.java)
                        clip.setPrimaryClip(android.content.ClipData.newPlainText("Email address", mail.address))
                        android.widget.Toast.makeText(context, "Address copied", android.widget.Toast.LENGTH_SHORT).show()
                    })
                }
            }
            // Tags: one slim line, only when there are some, with no heading.
            if (tags.isNotEmpty()) Row(Modifier.fillMaxWidth().padding(top = 4.dp).horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                tags.forEach { name ->
                    Surface(color = PanelHigh, shape = RoundedCornerShape(50), border = BorderStroke(1.dp, Line)) {
                        Text("# " + name, color = Ink, fontSize = 12.sp, maxLines = 1, modifier = Modifier.padding(horizontal = 8.dp, vertical = 1.dp))
                    }
                }
            }

            if (mail.scamReasons.isNotEmpty()) {
                Surface(
                    color = Panel, shape = RoundedCornerShape(16.dp), border = BorderStroke(2.dp, Amber),
                    modifier = Modifier.fillMaxWidth().padding(top = 18.dp),
                ) {
                    Column(Modifier.padding(16.dp)) {
                        Text("Take care with this one", color = Amber, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
                        mail.scamReasons.forEach { Text("• " + it, color = Ink, fontSize = 15.sp, modifier = Modifier.padding(top = 4.dp)) }
                        Text("Do not open links or send money or details unless you are sure it is real.", color = Muted, fontSize = 13.sp, modifier = Modifier.padding(top = 8.dp))
                    }
                }
            }

            Surface(
                color = Panel, shape = RoundedCornerShape(16.dp), border = BorderStroke(1.dp, Line),
                modifier = Modifier.fillMaxWidth().padding(top = 14.dp),
            ) {
                Column(Modifier.padding(16.dp)) {
                    Text("✦ AI summary", color = Blue, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                    if (mail.ungenerated) {
                        Text(if (summaryAsked) "Writing the summary\u2026 it will appear here when it is ready." else "Summary not generated", color = Ink, fontSize = 17.sp, lineHeight = 26.sp, modifier = Modifier.padding(top = 6.dp))
                        if (!summaryAsked) {
                            OutlinedButton(
                                onClick = {
                                    scope.launch {
                                        try {
                                            withContext(Dispatchers.IO) { api.askSummary(mail) }
                                            summaryAsked = true
                                            onAskedSummary()
                                        } catch (e: ApiException) { tell(e.message ?: "Could not ask for the summary.") }
                                        catch (_: Exception) { tell("Could not ask for the summary. Check your connection.") }
                                    }
                                },
                                modifier = Modifier.padding(top = 10.dp).height(38.dp), shape = RoundedCornerShape(12.dp), border = BorderStroke(1.dp, Line),
                            ) { Text("Generate summary", color = Ink, fontSize = 13.sp) }
                            Text("Pressing the button sends this email\u2019s text to your AI model.", color = Muted, fontSize = 12.sp, modifier = Modifier.padding(top = 8.dp))
                        }
                    } else Text(
                        mail.summary.ifBlank { "No summary yet." },
                        color = Ink, fontSize = 17.sp, lineHeight = 26.sp, modifier = Modifier.padding(top = 6.dp),
                    )
                }
            }

            // Reply, Reply all, Forward, and the less used actions behind the three dots, all on one line under the summary.
            Row(Modifier.fillMaxWidth().padding(top = 10.dp), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                val shape = RoundedCornerShape(12.dp)
                ReplyAction("Reply", { onCompose("reply") }) { ReplyIcon(Ink) }
                if (mail.replyCc.isNotEmpty()) ReplyAction("Reply all", { onCompose("reply_all") }) { ReplyAllIcon(Ink) }
                ReplyAction("Forward", { onCompose("forward") }) { ForwardIcon(Ink) }
                Box {
                    OutlinedButton(
                        onClick = { moreMenu = true }, modifier = Modifier.size(44.dp).semantics { contentDescription = "More actions" },
                        shape = shape, border = BorderStroke(1.dp, Line), contentPadding = androidx.compose.foundation.layout.PaddingValues(0.dp),
                    ) { Icon(Icons.Filled.MoreVert, contentDescription = null, tint = Ink) }
                    DropdownMenu(expanded = moreMenu, onDismissRequest = { moreMenu = false }, containerColor = Panel) {
                        if (mail.address.isNotBlank() && important != null) DropdownMenuItem(
                            text = { Text(if (important == true) "Not an important person" else "Important person", color = Ink) },
                            onClick = {
                                moreMenu = false
                                val on = important != true
                                scope.launch {
                                    try {
                                        withContext(Dispatchers.IO) { api.setImportant(mail.address.lowercase(), mail.sender, on) }
                                        important = on
                                        tell(if (on) (mail.sender.ifBlank { mail.address }) + " is now an important person." else (mail.sender.ifBlank { mail.address }) + " is no longer marked important.")
                                    } catch (e: ApiException) {
                                        tell(e.message ?: "That did not work.")
                                    } catch (e: Exception) {
                                        tell("That did not work. Please try again.")
                                    }
                                }
                            },
                        )
                        if (mail.address.isNotBlank() && important == false) DropdownMenuItem(
                            text = { Text("Always archive these", color = Ink) },
                            onClick = {
                                moreMenu = false
                                scope.launch {
                                    try {
                                        withContext(Dispatchers.IO) { api.archiveFrom(mail.address) }
                                        tell("From now on, new email from " + (mail.sender.ifBlank { mail.address }) + " is archived for you. You can change this in Mail rules on the website.")
                                    } catch (e: ApiException) {
                                        tell(e.message ?: "That did not work.")
                                    } catch (e: Exception) {
                                        tell("That did not work. Please try again.")
                                    }
                                }
                            },
                        )
                        DropdownMenuItem(text = { Text("Send to Junk", color = Ink) }, onClick = { moreMenu = false; onJunk(false) })
                        if (mail.address.isNotBlank()) DropdownMenuItem(text = { Text("Block sender", color = Ink) }, onClick = { moreMenu = false; askBlock = true })
                        if (mail.unsubUrl != null || mail.unsubMailto != null) DropdownMenuItem(text = { Text("Unsubscribe from this sender", color = Ink) }, onClick = {
                            moreMenu = false
                            if (mail.unsubUrl != null) unsubLink = mail.unsubUrl
                            else try {
                                val to = mail.unsubMailto ?: ""
                                val uri = android.net.Uri.parse("mailto:" + to + if (mail.unsubSubject.isNotBlank()) "?subject=" + android.net.Uri.encode(mail.unsubSubject) else "")
                                context.startActivity(android.content.Intent(android.content.Intent.ACTION_SENDTO, uri).addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK))
                            } catch (e: Exception) { }
                        })
                    }
                }
            }

            // The original email: a smaller button with its words, just under the reply row.
            OutlinedButton(
                onClick = { showOriginal = true },
                modifier = Modifier.fillMaxWidth().padding(top = 10.dp).height(38.dp),
                shape = RoundedCornerShape(12.dp), border = BorderStroke(1.dp, Line),
            ) { Text("Show original email", color = Ink, fontSize = 13.sp) }

            EmailTasks(mail, api, taskVersion)

            AttachmentsSection(mail, api)
            Spacer(Modifier.height(24.dp))
        }
        }
    }
    if (showOriginal) OriginalScreen(mail, api) { showOriginal = false }
    unsubLink?.let { LinkConfirm(it) { unsubLink = null } }
    if (askBlock) AlertDialog(
        onDismissRequest = { askBlock = false },
        containerColor = Panel,
        title = { Text("Block this sender?", color = Ink) },
        text = { Text("This email goes to Junk, and so will new email from " + mail.address + ". People you marked as important are never blocked. You can undo it any time in Settings, Blocked senders.", color = Ink) },
        confirmButton = { TextButton(onClick = { askBlock = false; onJunk(true) }) { Text("Block", color = Blue) } },
        dismissButton = { TextButton(onClick = { askBlock = false }) { Text("Cancel", color = Muted) } },
    )
}

/** Always visible at the bottom of an open email. Symbols only: bin, archive, reviewed (or mark unread), tag, remind me later, add a task. */
@Composable
private fun ActionBar(onResolve: (Outcome) -> Unit, onSnooze: () -> Unit, onTag: () -> Unit, onTask: () -> Unit, onUnread: (() -> Unit)? = null) {
    Row(Modifier.fillMaxWidth().background(Panel).navigationBarsPadding().padding(horizontal = 10.dp, vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        BarIcon("Bin", Red, Color(0xFF3A1D22), { onResolve(Outcome.Binned) }) { Icon(Icons.Filled.Delete, contentDescription = null, tint = Red) }
        BarIcon("Archive", Color(0xFF8DB8FF), Color(0xFF173056), { onResolve(Outcome.Archived) }) { ArchiveIcon(Color(0xFF8DB8FF)) }
        if (onUnread != null) BarIcon("Mark unread", Color(0xFF8DB8FF), Color(0xFF173056), onUnread) { Icon(Icons.Filled.Email, contentDescription = null, tint = Color(0xFF8DB8FF)) }
        else BarIcon("Reviewed", Green, Color(0xFF16382B), { onResolve(Outcome.Reviewed) }) { Icon(Icons.Filled.Check, contentDescription = null, tint = Green) }
        BarIcon("Tags", Ink, PanelHigh, onTag) { TagIcon(Ink) }
        BarIcon("Remind me later", Ink, PanelHigh, onSnooze) { ClockIcon(Ink) }
        BarIcon("Add a task", Ink, PanelHigh, onTask) { AddTaskIcon(Ink) }
    }
}

/** The bar shown while several emails are ticked. */
@Composable
private fun SelectionBar(count: Int, onResolve: (Outcome) -> Unit, onCancel: () -> Unit) {
    Column(Modifier.fillMaxWidth().background(Panel).navigationBarsPadding().padding(horizontal = 16.dp, vertical = 12.dp)) {
        Text(if (count == 1) "1 email selected" else "$count emails selected", color = Ink, fontSize = 15.sp, modifier = Modifier.padding(bottom = 8.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            BarIcon("Reviewed", Green, Color(0xFF16382B), { onResolve(Outcome.Reviewed) }) { Icon(Icons.Filled.Check, contentDescription = null, tint = Green) }
            BarIcon("Archive", Color(0xFF8DB8FF), Color(0xFF173056), { onResolve(Outcome.Archived) }) { ArchiveIcon(Color(0xFF8DB8FF)) }
            BarIcon("Bin", Red, Color(0xFF3A1D22), { onResolve(Outcome.Binned) }) { Icon(Icons.Filled.Delete, contentDescription = null, tint = Red) }
        }
        TextButton(onClick = onCancel, modifier = Modifier.fillMaxWidth()) { Text("Cancel", color = Blue) }
    }
}

/** Where to put an email until later: three plain choices. [onPick] gets the time in milliseconds and words for "Back ...". */
@Composable
private fun SnoozeChoices(onPick: (Long, String) -> Unit, onCancel: () -> Unit) {
    fun at(daysAhead: Int, hour: Int): Long {
        val c = Calendar.getInstance()
        c.add(Calendar.DAY_OF_YEAR, daysAhead)
        c.set(Calendar.HOUR_OF_DAY, hour)
        c.set(Calendar.MINUTE, 0)
        c.set(Calendar.SECOND, 0)
        c.set(Calendar.MILLISECOND, 0)
        return c.timeInMillis
    }
    AlertDialog(
        onDismissRequest = onCancel,
        containerColor = Panel,
        title = { Text("Remind me later", color = Ink) },
        text = {
            Column {
                TextButton(onClick = { onPick(System.currentTimeMillis() + 3 * 3600_000L, "in 3 hours") }) { Text("In 3 hours", color = Blue, fontSize = 16.sp) }
                TextButton(onClick = { onPick(at(1, 8), "tomorrow morning") }) { Text("Tomorrow morning", color = Blue, fontSize = 16.sp) }
                TextButton(onClick = {
                    val c = Calendar.getInstance()
                    val toMonday = ((Calendar.MONDAY - c.get(Calendar.DAY_OF_WEEK) + 7) % 7).let { if (it == 0) 7 else it }
                    onPick(at(toMonday, 8), "on Monday morning")
                }) { Text("Next Monday morning", color = Blue, fontSize = 16.sp) }
            }
        },
        confirmButton = {},
        dismissButton = { TextButton(onClick = onCancel) { Text("Cancel", color = Muted) } },
    )
}

