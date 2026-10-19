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
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

// Settings: one short list of topics. Tapping a topic opens its own page; anything that needs a longer explanation or a choice opens one more page.

private fun appVersion(context: Context): String = try {
    context.packageManager.getPackageInfo(context.packageName, 0).versionName ?: ""
} catch (e: Exception) {
    ""
}

private val swipeNames = listOf("archive" to "Archive", "bin" to "Bin", "reviewed" to "Reviewed", "none" to "Nothing")
private fun swipeName(id: String) = swipeNames.firstOrNull { it.first == id }?.second ?: "Nothing"

/** A rounded card that holds a few rows. */
@Composable
private fun Group(modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Surface(color = Panel, shape = RoundedCornerShape(18.dp), modifier = modifier.fillMaxWidth().padding(vertical = 6.dp)) {
        Column(content = content)
    }
}

@Composable
private fun RowLine() = HorizontalDivider(color = Line, modifier = Modifier.padding(start = 66.dp))

/** A small coloured square holding a symbol, the way phone settings screens mark each topic. */
@Composable
private fun Badge(symbol: String, tint: Color) {
    Box(Modifier.size(36.dp).clip(RoundedCornerShape(10.dp)).background(tint), contentAlignment = Alignment.Center) {
        Text(symbol, fontSize = 18.sp)
    }
}

/** A row that opens something. [value] is the current answer, shown on the right. */
@Composable
private fun NavRow(symbol: String, tint: Color, title: String, value: String = "", note: String = "", danger: Boolean = false, onClick: () -> Unit) {
    Row(Modifier.fillMaxWidth().clickable(onClick = onClick).padding(horizontal = 16.dp, vertical = 14.dp), verticalAlignment = Alignment.CenterVertically) {
        if (symbol.isNotEmpty()) {
            Badge(symbol, tint)
            Box(Modifier.size(14.dp))
        }
        Column(Modifier.weight(1f)) {
            Text(title, color = if (danger) Red else Ink, fontSize = 16.sp)
            if (note.isNotEmpty()) Text(note, color = Muted, fontSize = 13.sp, lineHeight = 18.sp)
        }
        if (value.isNotEmpty()) Text(value, color = Muted, fontSize = 15.sp, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(start = 10.dp, end = 4.dp))
        Text("›", color = Muted, fontSize = 22.sp, modifier = Modifier.padding(start = 6.dp))
    }
}

/** A row with an on and off switch. The whole row can be tapped. */
@Composable
private fun ToggleRow(title: String, note: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    Row(
        Modifier.fillMaxWidth().toggleable(value = checked, role = Role.Switch, onValueChange = onChange).padding(horizontal = 16.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f).padding(end = 12.dp)) {
            Text(title, color = Ink, fontSize = 16.sp)
            if (note.isNotEmpty()) Text(note, color = Muted, fontSize = 13.sp, lineHeight = 18.sp)
        }
        Switch(checked = checked, onCheckedChange = null)
    }
}

/** A row where exactly one choice in the group is picked. */
@Composable
private fun ChoiceRow(title: String, note: String = "", selected: Boolean, enabled: Boolean = true, onPick: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().clickable(enabled = enabled, onClick = onPick).padding(horizontal = 16.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        RadioButton(selected = selected, onClick = null, enabled = enabled)
        Column(Modifier.weight(1f).padding(start = 14.dp)) {
            Text(title, color = Ink, fontSize = 16.sp)
            if (note.isNotEmpty()) Text(note, color = Muted, fontSize = 13.sp, lineHeight = 18.sp)
        }
    }
}

@Composable
private fun Footnote(text: String, color: Color = Muted) {
    Text(text, color = color, fontSize = 13.sp, lineHeight = 18.sp, modifier = Modifier.padding(horizontal = 8.dp, vertical = 6.dp))
}

/** A settings page with its title and a Back button fixed at the top. Only the middle scrolls. */
@Composable
private fun Page(title: String, onBack: () -> Unit, content: @Composable ColumnScope.() -> Unit) {
    BackHandler(onBack = onBack)
    Column(Modifier.fillMaxSize()) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = onBack) { Text("‹ Back", color = Blue, fontSize = 16.sp) }
            Text(title, color = Ink, fontSize = 20.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(start = 4.dp))
        }
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 4.dp)) {
            content()
            Box(Modifier.size(24.dp))
        }
    }
}

private val tintAlerts = Color(0xFFE5484D)
private val tintSwipe = Color(0xFF3E63DD)
private val tintSecurity = Color(0xFF30A46C)
private val tintAccount = Color(0xFF8E4EC6)
private val tintAbout = Color(0xFF6B7A90)
private val tintTool = Color(0xFF2B3A55)

@Composable
internal fun SettingsTab(activity: MainActivity, prefs: SharedPreferences, server: String, api: EnveliqApi, onLeave: (Boolean) -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var page by remember { mutableStateOf("home") }

    var mailAlerts by remember { mutableStateOf(AlertPrefs.on(context)) }
    var quietOn by remember { mutableStateOf(AlertPrefs.quietOn(context)) }
    var quietFrom by remember { mutableStateOf(AlertPrefs.quietFrom(context)) }
    var quietTo by remember { mutableStateOf(AlertPrefs.quietTo(context)) }
    var alertNote by remember { mutableStateOf("") }
    var mode by remember { mutableStateOf(AlertPrefs.mode(context)) }
    var googleOffered by remember { mutableStateOf(false) }
    var working by remember { mutableStateOf(false) }
    var swipeRight by remember { mutableStateOf(prefs.getString("swipe_right", "archive") ?: "archive") }
    var swipeLeft by remember { mutableStateOf(prefs.getString("swipe_left", "bin") ?: "bin") }
    val power = remember { context.getSystemService(android.os.PowerManager::class.java) }
    var unrestricted by remember { mutableStateOf(power.isIgnoringBatteryOptimizations(context.packageName)) }
    var hide by remember { mutableStateOf(prefs.getBoolean("hide_in_recents", false)) }
    var appLock by remember { mutableStateOf(prefs.getBoolean("app_lock", false)) }
    var lockNote by remember { mutableStateOf("") }
    var testNote by remember { mutableStateOf("") }

    LaunchedEffect(mailAlerts) {
        googleOffered = false
        if (mailAlerts && Push.installed(context)) googleOffered = try { withContext(Dispatchers.IO) { api.pushAvailable() } } catch (_: Exception) { false }
    }

    fun useGoogle() {
        if (working) return
        working = true
        alertNote = ""
        scope.launch {
            try {
                val token = Push.token(context) ?: throw ApiException("Google's push service did not answer. Check that this phone has Google Play services and a connection, then try again.")
                val id = withContext(Dispatchers.IO) { api.registerPush(token, Build.MODEL, AlertPrefs.pushDevice(context)) }
                AlertPrefs.setPushDevice(context, id)
                AlertPrefs.setMode(context, "google")
                mode = "google"
                MailWatcherService.stop(context)
                alertNote = "Done. New-email alerts now come through Google's push service, and the watching note is gone."
            } catch (e: ApiException) {
                alertNote = e.message ?: "Could not set up Google push."
            } catch (_: Exception) {
                alertNote = "Could not set up Google push. Try again."
            } finally {
                working = false
            }
        }
    }
    fun useDirect() {
        val id = AlertPrefs.pushDevice(context)
        AlertPrefs.setMode(context, "direct")
        AlertPrefs.setPushDevice(context, null)
        mode = "direct"
        Push.stop(context)
        if (id != null) scope.launch(Dispatchers.IO) { try { api.unregisterPush(id) } catch (_: Exception) { } }
        MailWatcherService.start(context)
        alertNote = ""
    }
    fun turnOnAlerts() {
        SessionVault.save(context, server, api.sessionCookies())     // alerts need a kept sign-in
        AlertPrefs.setSeeded(context, false)       // what is in the inbox now is not new
        AlertPrefs.setMode(context, "direct")
        mode = "direct"
        AlertPrefs.setOn(context, true)
        mailAlerts = true
        alertNote = ""
        MailWatcherService.start(context)
    }
    val askMailPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) turnOnAlerts() else alertNote = "Notifications are off for Enveliq. Turn them on in Android's settings, then try again."
    }
    val askPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        testNote = if (granted && Notifier.sendTest(context)) "Sent. Lock your phone to see how it looks on the lock screen."
        else "Notifications are off for Enveliq. Turn them on in Android's settings."
    }
    fun pickTime(from: Boolean) {
        val now = if (from) quietFrom else quietTo
        android.app.TimePickerDialog(context, { _, h, m ->
            if (from) quietFrom = h * 60 + m else quietTo = h * 60 + m
            AlertPrefs.setQuiet(context, quietFrom, quietTo)
        }, now / 60, now % 60, true).show()
    }
    val back: (String) -> () -> Unit = { target -> { page = target } }

    when (page) {
        "alerts" -> Page("Notifications", back("home")) {
            Group {
                ToggleRow("New email alerts", "A quiet note once the AI has finished reading an email. The lock screen only says \"New email\".", mailAlerts) { on ->
                    if (!on) {
                        if (AlertPrefs.mode(context) == "google") useDirect()
                        AlertPrefs.setOn(context, false)
                        mailAlerts = false
                        mode = "direct"
                        MailWatcherService.stop(context)
                    } else if (!Notifier.canNotify(context) && Build.VERSION.SDK_INT >= 33) {
                        askMailPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
                    } else turnOnAlerts()
                }
            }
            if (alertNote.isNotEmpty()) Footnote(alertNote)
            if (mailAlerts) {
                Group {
                    if (googleOffered || mode == "google") {
                        NavRow("", tintTool, "How alerts reach this phone", value = if (mode == "google") "Google" else "Direct") { page = "delivery" }
                        HorizontalDivider(color = Line, modifier = Modifier.padding(start = 16.dp))
                    }
                    ToggleRow("Quiet hours", "No sound or buzz. New email still waits in the notification list.", quietOn) {
                        quietOn = it
                        AlertPrefs.setQuietOn(context, it)
                    }
                    if (quietOn) {
                        HorizontalDivider(color = Line, modifier = Modifier.padding(start = 16.dp))
                        NavRow("", tintTool, "From", value = AlertPrefs.timeText(quietFrom)) { pickTime(true) }
                        HorizontalDivider(color = Line, modifier = Modifier.padding(start = 16.dp))
                        NavRow("", tintTool, "Until", value = AlertPrefs.timeText(quietTo)) { pickTime(false) }
                    }
                }
            }
            Group {
                NavRow("", tintTool, "Send a test notification", note = "See how an alert looks on this phone.") {
                    if (Notifier.canNotify(context)) {
                        Notifier.sendTest(context)
                        testNote = "Sent. Lock your phone to see how it looks on the lock screen."
                    } else if (Build.VERSION.SDK_INT >= 33) {
                        askPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
                    }
                }
                if (mailAlerts && !unrestricted && mode == "direct") {
                    HorizontalDivider(color = Line, modifier = Modifier.padding(start = 16.dp))
                    NavRow("", tintTool, "Keep alerts on time", note = "If alerts come late, let Enveliq run without Android's battery limit.") {
                        context.startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, android.net.Uri.parse("package:" + context.packageName)))
                        unrestricted = power.isIgnoringBatteryOptimizations(context.packageName)
                    }
                }
                HorizontalDivider(color = Line, modifier = Modifier.padding(start = 16.dp))
                NavRow("", tintTool, "Android's notification settings", note = "Sounds, lock screen and channels.") {
                    context.startActivity(Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, context.packageName))
                }
            }
            if (testNote.isNotEmpty()) Footnote(testNote)
            if (mailAlerts) Footnote("Enveliq stays signed in on this phone and keeps one quiet connection to your server. It uses almost no battery, and does nothing while the phone has no signal.")
        }
        "delivery" -> Page("How alerts reach this phone", back("alerts")) {
            Group {
                ChoiceRow("Direct from my server", "Nothing goes through any other company. Android shows a small \"watching\" note while it waits.", mode == "direct", !working) { if (mode != "direct") useDirect() }
                HorizontalDivider(color = Line, modifier = Modifier.padding(start = 16.dp))
                ChoiceRow("Google's push service", "Instant, with no \"watching\" note. Google is told that a notification was sent, never what it says.", mode == "google", !working && googleOffered) { if (mode != "google") useGoogle() }
            }
            if (alertNote.isNotEmpty()) Footnote(alertNote)
            if (mode == "google") Group {
                NavRow("", tintTool, "Send a test through Google") {
                    val id = AlertPrefs.pushDevice(context)
                    if (id != null && !working) {
                        working = true
                        scope.launch {
                            alertNote = try { withContext(Dispatchers.IO) { api.testPush(id) }; "Sent. A note should appear in a few seconds." }
                            catch (e: ApiException) { e.message ?: "The test did not go through." } catch (_: Exception) { "The test did not go through." }
                            working = false
                        }
                    }
                }
            }
        }
        "swipe" -> Page("Swipe on an email", back("home")) {
            Group {
                NavRow("", tintTool, "Swipe right to", value = swipeName(swipeRight)) { page = "swipe_right" }
                HorizontalDivider(color = Line, modifier = Modifier.padding(start = 16.dp))
                NavRow("", tintTool, "Swipe left to", value = swipeName(swipeLeft)) { page = "swipe_left" }
            }
            Footnote("Swiping can be undone for a few seconds. Press and hold an email to select several.")
        }
        "swipe_right", "swipe_left" -> {
            val right = page == "swipe_right"
            Page(if (right) "Swipe right to" else "Swipe left to", back("swipe")) {
                Group {
                    swipeNames.forEachIndexed { i, (id, label) ->
                        if (i > 0) HorizontalDivider(color = Line, modifier = Modifier.padding(start = 16.dp))
                        ChoiceRow(label, selected = (if (right) swipeRight else swipeLeft) == id) {
                            if (right) { swipeRight = id; prefs.edit().putString("swipe_right", id).apply() }
                            else { swipeLeft = id; prefs.edit().putString("swipe_left", id).apply() }
                        }
                    }
                }
            }
        }
        "security" -> Page("Security", back("home")) {
            Group {
                ToggleRow("Ask for my fingerprint, face or PIN", "To open Enveliq, and again after it has been out of sight for a minute.", appLock) {
                    if (it && !activity.canLock()) {
                        lockNote = "Set up a fingerprint, face or PIN in Android's settings first, then switch this on."
                    } else {
                        lockNote = ""
                        appLock = it
                        prefs.edit().putBoolean("app_lock", it).apply()
                    }
                }
                HorizontalDivider(color = Line, modifier = Modifier.padding(start = 16.dp))
                ToggleRow("Hide Enveliq in recent apps", "Also stops screenshots of the app.", hide) {
                    hide = it
                    prefs.edit().putBoolean("hide_in_recents", it).apply()
                    activity.setSecure(it)
                }
            }
            if (lockNote.isNotEmpty()) Footnote(lockNote, Amber)
        }
        "account" -> Page("Account", back("home")) {
            Group {
                NavRow("", tintTool, "Server", value = server.removePrefix("https://")) { }
            }
            Footnote("You stay signed in on this phone until you sign out.")
            Group { NavRow("", tintTool, "Sign out", danger = true) { onLeave(false) } }
        }
        "about" -> Page("About", back("home")) {
            Group { NavRow("", tintTool, "Version", value = appVersion(context)) { } }
            Footnote("Email is held in memory while it is on the screen and is never saved on this phone. Backups are switched off.")
            Footnote("The only thing kept is your sign-in, encrypted on this phone, if you chose to stay signed in. The app only talks to the server you typed, over HTTPS.")
        }
        else -> Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp)) {
            Heading("Settings", "")
            Group {
                Row(Modifier.fillMaxWidth().padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(48.dp).clip(RoundedCornerShape(14.dp)).background(Blue), contentAlignment = Alignment.Center) { Text("✉", fontSize = 24.sp, color = Color.White) }
                    Column(Modifier.padding(start = 14.dp)) {
                        Text("Enveliq", color = Ink, fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
                        Text(server.removePrefix("https://"), color = Muted, fontSize = 14.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                }
            }
            Group {
                NavRow("🔔", tintAlerts, "Notifications", value = if (mailAlerts) "On" else "Off") { page = "alerts" }
                RowLine()
                NavRow("↔", tintSwipe, "Swipe on an email", value = swipeName(swipeRight) + " · " + swipeName(swipeLeft)) { page = "swipe" }
                RowLine()
                NavRow("🔒", tintSecurity, "Security", value = if (appLock) "Lock on" else "") { page = "security" }
            }
            Group {
                NavRow("👤", tintAccount, "Account") { page = "account" }
                RowLine()
                NavRow("ℹ", tintAbout, "About", value = appVersion(context)) { page = "about" }
            }
            Box(Modifier.size(24.dp))
        }
    }
}
