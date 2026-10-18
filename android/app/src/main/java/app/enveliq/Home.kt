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
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Email
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.OutlinedButton
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
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

private enum class Stage { Opening, Start, SignIn, Home }
private enum class Tab { Inbox, Tasks, Settings }

@Composable
fun EnveliqApp(activity: MainActivity) {
    val prefs = remember { activity.getSharedPreferences("enveliq", Context.MODE_PRIVATE) }
    val kept = remember { SessionVault.load(activity) }
    var stage by remember { mutableStateOf(if (kept != null) Stage.Opening else Stage.Start) }
    var api by remember { mutableStateOf<EnveliqApi?>(null) }
    var server by remember { mutableStateOf("") }
    var notice by remember { mutableStateOf("") }

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
            stage = Stage.Start
        } catch (e: Exception) {
            notice = "Could not reach your Enveliq. Try again."
            stage = Stage.Start
        }
    }

    when (stage) {
        Stage.Opening -> Box(Modifier.fillMaxSize().background(Navy), contentAlignment = Alignment.Center) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                CircularProgressIndicator(color = Blue)
                Text("Opening your inbox…", color = Muted, fontSize = 15.sp, modifier = Modifier.padding(top = 14.dp))
            }
        }
        Stage.Start -> StartScreen(
            notice = notice,
            onSample = { api = null; server = ""; notice = ""; stage = Stage.Home },
            onConnect = { notice = ""; stage = Stage.SignIn },
        )
        Stage.SignIn -> {
            BackHandler { stage = Stage.Start }
            SignInScreen(
                initialAddress = prefs.getString("server", "") ?: "",
                onBack = { stage = Stage.Start },
                onDone = { client, address, keep ->
                    prefs.edit().putString("server", address).apply()
                    if (keep) SessionVault.save(activity, address, client.sessionCookies()) else {
                        SessionVault.clear(activity)
                        AlertPrefs.reset(activity)          // alerts need a kept sign-in
                        MailWatcherService.stop(activity)
                    }
                    api = client
                    server = address
                    stage = Stage.Home
                },
            )
        }
        Stage.Home -> HomeScreen(
            activity = activity,
            prefs = prefs,
            api = api,
            server = server,
            onLeave = { signOut ->
                if (signOut) {
                    val client = api
                    if (client != null) Thread { client.signOut() }.start()
                    SessionVault.clear(activity)
                    AlertPrefs.reset(activity)
                    MailWatcherService.stop(activity)
                }
                EnveliqApi.forgetSession()
                api = null
                notice = ""
                stage = Stage.Start
            },
        )
    }
}

@Composable
private fun HomeScreen(activity: MainActivity, prefs: SharedPreferences, api: EnveliqApi?, server: String, onLeave: (Boolean) -> Unit) {
    val demo = api == null
    val mails = remember { mutableStateListOf<Mail>() }
    var loading by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }
    var tab by remember { mutableStateOf(Tab.Inbox) }
    var opened by remember { mutableStateOf<Mail?>(null) }
    val snack = remember { SnackbarHostState() }
    val scope = rememberCoroutineScope()

    fun load() {
        if (api == null) {
            mails.clear()
            mails.addAll(Demo.mails)
            return
        }
        loading = true
        error = ""
        scope.launch {
            try {
                val list = withContext(Dispatchers.IO) { api.inbox() }
                mails.clear()
                mails.addAll(list)
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
            }
        }
    }

    LaunchedEffect(Unit) { load() }
    BackHandler(enabled = opened != null) { opened = null }

    // The email leaves the list at once. It is only marked at your mailbox when the Undo time has passed.
    fun resolve(mail: Mail, outcome: Outcome) {
        val at = mails.indexOf(mail).coerceAtLeast(0)
        mails.remove(mail)
        opened = null
        scope.launch {
            val result = snack.showSnackbar(message = outcome.done, actionLabel = "Undo", duration = SnackbarDuration.Short)
            if (result == SnackbarResult.ActionPerformed) {
                mails.add(at.coerceAtMost(mails.size), mail)
            } else if (api != null) {
                try {
                    withContext(Dispatchers.IO) { api.resolve(mail, outcome) }
                } catch (e: Exception) {
                    mails.add(at.coerceAtMost(mails.size), mail)
                    snack.showSnackbar((e.message ?: "That did not work.") + " The email is back in your list.")
                }
            }
        }
    }

    val current = opened
    Scaffold(
        containerColor = Navy,
        snackbarHost = { SnackbarHost(snack) },
        bottomBar = {
            if (current != null) {
                ActionBar { outcome -> resolve(current, outcome) }
            } else {
                NavigationBar(containerColor = Panel) {
                    val colors = NavigationBarItemDefaults.colors(
                        indicatorColor = PanelHigh,
                        selectedIconColor = Blue,
                        selectedTextColor = Blue,
                        unselectedIconColor = Muted,
                        unselectedTextColor = Muted,
                    )
                    NavigationBarItem(
                        selected = tab == Tab.Inbox, onClick = { tab = Tab.Inbox }, colors = colors,
                        icon = { Icon(Icons.Filled.Email, contentDescription = null) }, label = { Text("Inbox") },
                    )
                    NavigationBarItem(
                        selected = tab == Tab.Tasks, onClick = { tab = Tab.Tasks }, colors = colors,
                        icon = { Icon(Icons.Filled.CheckCircle, contentDescription = null) }, label = { Text("Tasks") },
                    )
                    NavigationBarItem(
                        selected = tab == Tab.Settings, onClick = { tab = Tab.Settings }, colors = colors,
                        icon = { Icon(Icons.Filled.Settings, contentDescription = null) }, label = { Text("Settings") },
                    )
                }
            }
        },
    ) { inner ->
        Box(Modifier.padding(inner).fillMaxSize()) {
            if (current != null) {
                DetailBody(current, api, onBack = { opened = null })
            } else {
                when (tab) {
                    Tab.Inbox -> InboxTab(mails, loading, error, demo, onOpen = { opened = it }, onRefresh = { load() })
                    Tab.Tasks -> TasksTab(mails, onOpen = { opened = it })
                    Tab.Settings -> SettingsTab(activity, prefs, demo, server, api, onLeave)
                }
            }
        }
    }
}

@Composable
private fun Heading(title: String, subtitle: String, trailing: @Composable () -> Unit = {}) {
    Row(Modifier.fillMaxWidth().padding(start = 20.dp, end = 8.dp, top = 14.dp, bottom = 6.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(title, color = Ink, fontSize = 28.sp, fontWeight = FontWeight.Bold)
            if (subtitle.isNotEmpty()) Text(subtitle, color = Muted, fontSize = 14.sp, modifier = Modifier.padding(top = 2.dp))
        }
        trailing()
    }
}

@Composable
private fun InboxTab(mails: List<Mail>, loading: Boolean, error: String, demo: Boolean, onOpen: (Mail) -> Unit, onRefresh: () -> Unit) {
    var onlyAction by remember { mutableStateOf(false) }
    val shown = if (onlyAction) mails.filter { it.needsAction } else mails
    val needs = mails.count { it.needsAction }
    Column(Modifier.fillMaxSize()) {
        Heading(
            "My inbox",
            if (loading) "Looking for your email…" else "${mails.size} emails to look at, $needs need you" + if (demo) " · sample email" else "",
        ) {
            TextButton(onClick = onRefresh, enabled = !loading) { Text("Refresh", color = Blue, fontSize = 15.sp) }
        }
        Row(Modifier.padding(horizontal = 16.dp, vertical = 6.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip(selected = !onlyAction, onClick = { onlyAction = false }, label = { Text("All") })
            FilterChip(selected = onlyAction, onClick = { onlyAction = true }, label = { Text("Needs action") })
        }
        when {
            loading && mails.isEmpty() -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator(color = Blue) }
            error.isNotEmpty() -> Column(Modifier.padding(24.dp)) {
                Text(error, color = Red, fontSize = 16.sp)
                OutlinedButton(onClick = onRefresh, modifier = Modifier.padding(top = 14.dp)) { Text("Try again") }
            }
            shown.isEmpty() -> Text(
                if (onlyAction) "Nothing needs you right now." else "You're all caught up.",
                color = Muted, fontSize = 17.sp, modifier = Modifier.padding(24.dp),
            )
            else -> LazyColumn(Modifier.fillMaxSize()) {
                items(shown, key = { it.accountId + ":" + it.id }) { m -> MailRow(m) { onOpen(m) } }
            }
        }
    }
}

@Composable
private fun MailRow(mail: Mail, onClick: () -> Unit) {
    Column(Modifier.fillMaxWidth().clickable(onClick = onClick).padding(horizontal = 20.dp, vertical = 12.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            if (mail.needsAction) {
                Box(Modifier.size(8.dp).clip(CircleShape).background(Amber))
                Spacer(Modifier.size(8.dp))
            }
            Text(
                mail.sender, color = Ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold,
                maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f),
            )
            Text(mail.whenText, color = Muted, fontSize = 13.sp)
        }
        Text(mail.subject, color = Ink, fontSize = 15.sp, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(top = 2.dp))
        if (mail.summary.isNotBlank()) {
            Text("✦ " + mail.summary, color = Muted, fontSize = 14.sp, lineHeight = 20.sp, maxLines = 2, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(top = 3.dp))
        }
    }
    HorizontalDivider(color = Line)
}

@Composable
private fun DetailBody(mail: Mail, api: EnveliqApi?, onBack: () -> Unit) {
    var original by remember(mail.id) { mutableStateOf<String?>(null) }
    var loadingOriginal by remember(mail.id) { mutableStateOf(false) }
    var originalError by remember(mail.id) { mutableStateOf("") }
    val scope = rememberCoroutineScope()

    Column(Modifier.fillMaxSize()) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = onBack) { Text("‹ Back", color = Blue, fontSize = 16.sp) }
        }
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 20.dp)) {
            Text(mail.subject, color = Ink, fontSize = 24.sp, fontWeight = FontWeight.Bold, lineHeight = 30.sp)
            Text(mail.sender + if (mail.whenText.isNotEmpty()) " · " + mail.whenText else "", color = Muted, fontSize = 14.sp, modifier = Modifier.padding(top = 6.dp))
            if (mail.address.isNotEmpty()) Text(mail.address, color = Muted, fontSize = 13.sp)

            Surface(
                color = Panel, shape = RoundedCornerShape(16.dp), border = BorderStroke(1.dp, Line),
                modifier = Modifier.fillMaxWidth().padding(top = 18.dp),
            ) {
                Column(Modifier.padding(16.dp)) {
                    Text("✦ AI summary", color = Blue, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                    Text(
                        mail.summary.ifBlank { "No summary yet." },
                        color = Ink, fontSize = 17.sp, lineHeight = 26.sp, modifier = Modifier.padding(top = 6.dp),
                    )
                    Text("Written by the AI. It can be wrong. Check the original when it matters.", color = Muted, fontSize = 12.sp, modifier = Modifier.padding(top = 8.dp))
                }
            }

            if (mail.taskTitle != null) {
                Surface(
                    color = Panel, shape = RoundedCornerShape(16.dp), border = BorderStroke(1.dp, Line),
                    modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
                ) {
                    Column(Modifier.padding(16.dp)) {
                        Text("Task", color = Amber, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                        Text(mail.taskTitle, color = Ink, fontSize = 17.sp, modifier = Modifier.padding(top = 4.dp))
                        if (!mail.taskDue.isNullOrBlank()) Text("Due: " + mail.taskDue, color = Muted, fontSize = 14.sp, modifier = Modifier.padding(top = 2.dp))
                    }
                }
            }

            val text = original
            if (text == null) {
                OutlinedButton(
                    onClick = {
                        if (mail.demoBody != null) {
                            original = mail.demoBody
                        } else if (api != null && !loadingOriginal) {
                            loadingOriginal = true
                            originalError = ""
                            scope.launch {
                                try {
                                    original = withContext(Dispatchers.IO) { api.originalText(mail) }
                                } catch (e: ApiException) {
                                    originalError = e.message ?: "Could not open the original email."
                                } catch (e: Exception) {
                                    originalError = "Could not open the original email."
                                } finally {
                                    loadingOriginal = false
                                }
                            }
                        }
                    },
                    enabled = !loadingOriginal,
                    modifier = Modifier.fillMaxWidth().padding(top = 16.dp).height(50.dp),
                    shape = RoundedCornerShape(14.dp),
                    border = BorderStroke(1.dp, Line),
                ) {
                    if (loadingOriginal) CircularProgressIndicator(Modifier.size(20.dp), color = Blue, strokeWidth = 2.dp)
                    else Text("Show the original email", color = Ink, fontSize = 16.sp)
                }
                if (originalError.isNotEmpty()) Text(originalError, color = Red, fontSize = 14.sp, modifier = Modifier.padding(top = 8.dp))
            } else {
                Text("Original email · plain text, links and pictures switched off", color = Muted, fontSize = 12.sp, modifier = Modifier.padding(top = 18.dp, bottom = 6.dp))
                Surface(color = Color.White, shape = RoundedCornerShape(12.dp), modifier = Modifier.fillMaxWidth()) {
                    Text(text, color = Color(0xFF1B2430), fontSize = 15.sp, lineHeight = 23.sp, modifier = Modifier.padding(16.dp))
                }
            }
            Spacer(Modifier.height(24.dp))
        }
    }
}

/** Fixed at the bottom, so the buttons can always be reached. */
@Composable
private fun ActionBar(onResolve: (Outcome) -> Unit) {
    Row(
        Modifier.fillMaxWidth().background(Panel).navigationBarsPadding().padding(horizontal = 16.dp, vertical = 12.dp),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Button(
            onClick = { onResolve(Outcome.Reviewed) }, modifier = Modifier.weight(1f).height(52.dp), shape = RoundedCornerShape(14.dp),
            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF16382B), contentColor = Green),
        ) { Text("Reviewed", fontWeight = FontWeight.SemiBold) }
        Button(
            onClick = { onResolve(Outcome.Archived) }, modifier = Modifier.weight(1f).height(52.dp), shape = RoundedCornerShape(14.dp),
            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF173056), contentColor = Color(0xFF8DB8FF)),
        ) { Text("Archive", fontWeight = FontWeight.SemiBold) }
        Button(
            onClick = { onResolve(Outcome.Binned) }, modifier = Modifier.weight(1f).height(52.dp), shape = RoundedCornerShape(14.dp),
            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF3A1D22), contentColor = Red),
        ) { Text("Bin", fontWeight = FontWeight.SemiBold) }
    }
}

@Composable
private fun TasksTab(mails: List<Mail>, onOpen: (Mail) -> Unit) {
    val tasks = mails.filter { it.taskTitle != null }
    Column(Modifier.fillMaxSize()) {
        Heading("Tasks", if (tasks.isEmpty()) "" else "${tasks.size} to do")
        if (tasks.isEmpty()) {
            Text("No tasks right now. Tasks appear here when an email needs something from you.", color = Muted, fontSize = 16.sp, modifier = Modifier.padding(20.dp))
        } else {
            LazyColumn(Modifier.fillMaxSize().padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                items(tasks, key = { "t" + it.accountId + ":" + it.id }) { m ->
                    Surface(
                        color = Panel, shape = RoundedCornerShape(16.dp), border = BorderStroke(1.dp, Line),
                        modifier = Modifier.fillMaxWidth().clickable { onOpen(m) },
                    ) {
                        Column(Modifier.padding(16.dp)) {
                            Text(m.taskTitle ?: "", color = Ink, fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
                            if (!m.taskDue.isNullOrBlank()) Text("Due: " + m.taskDue, color = Amber, fontSize = 14.sp, modifier = Modifier.padding(top = 3.dp))
                            Text("From " + m.sender, color = Muted, fontSize = 13.sp, modifier = Modifier.padding(top = 3.dp))
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun SectionTitle(text: String) {
    Text(text, color = Blue, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 22.dp, bottom = 8.dp))
}

@Composable
private fun SwitchRow(title: String, note: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f).padding(end = 12.dp)) {
            Text(title, color = Ink, fontSize = 16.sp)
            Text(note, color = Muted, fontSize = 13.sp, lineHeight = 18.sp)
        }
        Switch(checked = checked, onCheckedChange = onChange)
    }
}

@Composable
private fun SettingsTab(activity: MainActivity, prefs: SharedPreferences, demo: Boolean, server: String, api: EnveliqApi?, onLeave: (Boolean) -> Unit) {
    val context = LocalContext.current
    var mailAlerts by remember { mutableStateOf(AlertPrefs.on(context)) }
    var quietOn by remember { mutableStateOf(AlertPrefs.quietOn(context)) }
    var quietFrom by remember { mutableStateOf(AlertPrefs.quietFrom(context)) }
    var quietTo by remember { mutableStateOf(AlertPrefs.quietTo(context)) }
    var alertNote by remember { mutableStateOf("") }
    val power = remember { context.getSystemService(android.os.PowerManager::class.java) }
    var unrestricted by remember { mutableStateOf(power.isIgnoringBatteryOptimizations(context.packageName)) }
    var hide by remember { mutableStateOf(prefs.getBoolean("hide_in_recents", false)) }
    var message by remember { mutableStateOf("") }
    fun turnOnAlerts() {
        api?.let { SessionVault.save(context, server, it.sessionCookies()) }     // alerts need a kept sign-in
        AlertPrefs.setSeeded(context, false)       // what is in the inbox now is not new
        AlertPrefs.setOn(context, true)
        mailAlerts = true
        alertNote = ""
        MailWatcherService.start(context)
    }
    val askMailPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) turnOnAlerts() else alertNote = "Notifications are off for Enveliq. Turn them on in Android's settings, then try again."
    }
    val askPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        message = if (granted && Notifier.sendTest(context)) "Sent. Lock your phone to see how it looks on the lock screen."
        else "Notifications are off for Enveliq. Turn them on in Android's settings."
    }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 20.dp)) {
        Heading("Settings", "")
        SectionTitle("Notifications")
        SwitchRow(
            "Tell me when new email arrives",
            if (demo) "Sign in to your Enveliq to use this." else "A quiet note once the AI has finished reading it. The lock screen only says \"New email\".",
            mailAlerts,
        ) { on ->
            if (demo) {
                alertNote = "Sign in to your own Enveliq first. Sample email never changes."
            } else if (!on) {
                AlertPrefs.setOn(context, false)
                mailAlerts = false
                MailWatcherService.stop(context)
            } else if (!Notifier.canNotify(context) && Build.VERSION.SDK_INT >= 33) {
                askMailPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
            } else turnOnAlerts()
        }
        if (mailAlerts) Text(
            "Enveliq stays signed in on this phone and keeps one quiet connection to your server. It uses almost no battery, and does nothing at all while the phone has no signal.",
            color = Muted, fontSize = 13.sp, lineHeight = 18.sp, modifier = Modifier.padding(bottom = 6.dp),
        )
        if (alertNote.isNotEmpty()) Text(alertNote, color = Muted, fontSize = 13.sp, modifier = Modifier.padding(bottom = 6.dp))
        if (mailAlerts) {
            SwitchRow("Quiet hours", "No sound or buzz. New email still waits for you in the notification list.", quietOn) {
                quietOn = it
                AlertPrefs.setQuietOn(context, it)
            }
            if (quietOn) Row(Modifier.fillMaxWidth().padding(bottom = 6.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedButton(
                    onClick = {
                        android.app.TimePickerDialog(context, { _, h, m ->
                            quietFrom = h * 60 + m
                            AlertPrefs.setQuiet(context, quietFrom, quietTo)
                        }, quietFrom / 60, quietFrom % 60, true).show()
                    },
                    modifier = Modifier.weight(1f).height(48.dp), shape = RoundedCornerShape(14.dp), border = BorderStroke(1.dp, Line),
                ) { Text("From " + AlertPrefs.timeText(quietFrom), color = Ink) }
                OutlinedButton(
                    onClick = {
                        android.app.TimePickerDialog(context, { _, h, m ->
                            quietTo = h * 60 + m
                            AlertPrefs.setQuiet(context, quietFrom, quietTo)
                        }, quietTo / 60, quietTo % 60, true).show()
                    },
                    modifier = Modifier.weight(1f).height(48.dp), shape = RoundedCornerShape(14.dp), border = BorderStroke(1.dp, Line),
                ) { Text("Until " + AlertPrefs.timeText(quietTo), color = Ink) }
            }
            if (!unrestricted) {
                Text(
                    "If alerts sometimes arrive late when the phone has been still for a while, let Enveliq run without Android's battery limit. It still uses very little.",
                    color = Muted, fontSize = 13.sp, lineHeight = 18.sp,
                )
                OutlinedButton(
                    onClick = {
                        val intent = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, android.net.Uri.parse("package:" + context.packageName))
                        context.startActivity(intent)
                        unrestricted = power.isIgnoringBatteryOptimizations(context.packageName)
                    },
                    modifier = Modifier.fillMaxWidth().padding(top = 8.dp).height(48.dp), shape = RoundedCornerShape(14.dp), border = BorderStroke(1.dp, Line),
                ) { Text("Keep alerts on time", color = Ink) }
            }
        }
        Button(
            onClick = {
                if (Notifier.canNotify(context)) {
                    Notifier.sendTest(context)
                    message = "Sent. Lock your phone to see how it looks on the lock screen."
                } else if (Build.VERSION.SDK_INT >= 33) {
                    askPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
                }
            },
            modifier = Modifier.fillMaxWidth().padding(top = 8.dp).height(50.dp),
            shape = RoundedCornerShape(14.dp),
        ) { Text("Send a test notification to this phone") }
        if (message.isNotEmpty()) Text(message, color = Muted, fontSize = 13.sp, modifier = Modifier.padding(top = 6.dp))
        OutlinedButton(
            onClick = {
                val intent = Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, context.packageName)
                context.startActivity(intent)
            },
            modifier = Modifier.fillMaxWidth().padding(top = 10.dp).height(48.dp),
            shape = RoundedCornerShape(14.dp), border = BorderStroke(1.dp, Line),
        ) { Text("Android's notification settings", color = Ink) }

        SectionTitle("Security")
        SwitchRow("Hide Enveliq in recent apps", "Also stops screenshots of the app.", hide) {
            hide = it
            prefs.edit().putBoolean("hide_in_recents", it).apply()
            activity.setSecure(it)
        }
        Text("App lock with your fingerprint, face or PIN is planned.", color = Muted, fontSize = 13.sp, modifier = Modifier.padding(top = 2.dp))

        SectionTitle("Account")
        Text(
            if (demo) "You are looking at made-up sample email. Nothing here is real." else "Signed in to $server. You stay signed in on this phone until you sign out.",
            color = Ink, fontSize = 15.sp, lineHeight = 22.sp,
        )
        OutlinedButton(
            onClick = { onLeave(true) },
            modifier = Modifier.fillMaxWidth().padding(top = 10.dp).height(48.dp),
            shape = RoundedCornerShape(14.dp), border = BorderStroke(1.dp, Line),
        ) { Text(if (demo) "Leave sample email" else "Sign out", color = Ink) }

        SectionTitle("About")
        Text("Enveliq for Android · version " + appVersion(context), color = Ink, fontSize = 15.sp)
        Text(
            "Email is held in memory while it is on the screen and is never saved on this phone. Backups are switched off. The only thing kept is your sign-in, encrypted on this phone, if you chose to stay signed in. The app only talks to the server you typed, over HTTPS.",
            color = Muted, fontSize = 13.sp, lineHeight = 19.sp, modifier = Modifier.padding(top = 4.dp, bottom = 30.dp),
        )
    }
}

private fun appVersion(context: Context): String = try {
    context.packageManager.getPackageInfo(context.packageName, 0).versionName ?: ""
} catch (e: Exception) {
    ""
}
