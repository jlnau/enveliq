package app.enveliq

import android.text.format.DateFormat
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** A calendar invitation read from an email by the server. Nothing but the person's own answer is kept; times are Unix seconds. */
data class Invite(
    val summary: String, val location: String, val description: String,
    val start: Double?, val end: Double?, val allDay: Boolean, val startDay: String, val endDay: String,
    val repeats: Boolean, val cancelled: Boolean,
    val organizerName: String, val organizerEmail: String, val people: Int,
    val canAnswer: Boolean, val canAdd: Boolean, val organizerDiffers: Boolean,
    val mine: String, val calendar: String,
    val response: String, val calendarProblem: String, val proposed: Boolean,
)

private fun whenText(inv: Invite): String {
    val locale = Locale.getDefault()
    if (inv.allDay) {
        val day = try { SimpleDateFormat("yyyy-MM-dd", Locale.US).parse(inv.startDay) } catch (_: Exception) { null }
        return if (day != null) SimpleDateFormat("EEE d MMM yyyy", locale).format(day) + " (all day)" else inv.startDay
    }
    val start = inv.start ?: return ""
    val first = Date((start * 1000).toLong())
    val last = Date(((inv.end ?: start) * 1000).toLong())
    val dayPattern = DateFormat.getBestDateTimePattern(locale, "EEE d MMM jmm")
    val clockPattern = DateFormat.getBestDateTimePattern(locale, "jmm")
    val sameDay = SimpleDateFormat("yyyyMMdd", locale).format(first) == SimpleDateFormat("yyyyMMdd", locale).format(last)
    val end = SimpleDateFormat(if (sameDay) clockPattern else dayPattern, locale).format(last)
    return SimpleDateFormat(dayPattern, locale).format(first) + " to " + end
}

/**
 * The invitation card on an open email: Accept, Maybe, Decline and Propose a new time. The server sends the answer by email (with the
 * same Undo as other sent email) and puts an accepted meeting in the calendar connected on the website. Shown only for emails that
 * carry an invitation.
 */
@Composable
internal fun InviteCard(mail: Mail, api: EnveliqApi) {
    if (!mail.hasFiles) return
    val scope = rememberCoroutineScope()
    var invite by remember(mail.id) { mutableStateOf<Invite?>(null) }
    var refresh by remember(mail.id) { mutableStateOf(0) }
    var busy by remember(mail.id) { mutableStateOf(false) }
    var confirmed by remember(mail.id) { mutableStateOf(false) }
    var proposing by remember(mail.id) { mutableStateOf(false) }
    var note by remember(mail.id) { mutableStateOf("") }
    var undoId by remember(mail.id) { mutableStateOf("") }
    var undoLeft by remember(mail.id) { mutableStateOf(0) }

    LaunchedEffect(mail.id, refresh) {
        invite = try { withContext(Dispatchers.IO) { api.invite(mail) } } catch (_: Exception) { invite }
    }
    val inv = invite ?: return

    fun finished(sent: Sent) {
        busy = false
        if (sent.queued && sent.secondsLeft > 0) {
            undoId = sent.outboxId
            undoLeft = sent.secondsLeft
            note = ""
            scope.launch {
                while (undoLeft > 0) { delay(1000); undoLeft -= 1 }
                val waited = undoId.isNotEmpty()
                undoId = ""
                if (waited) { delay(2500); refresh += 1 }
            }
        } else {
            note = "Sent."
            scope.launch { delay(1500); refresh += 1 }
        }
    }

    fun problem(e: Exception) {
        busy = false
        note = (e as? ApiException)?.message ?: "That did not work. Please try again."
    }

    fun answer(response: String) {
        busy = true
        scope.launch {
            try { finished(withContext(Dispatchers.IO) { api.answerInvite(mail, response, confirmed) }) } catch (e: Exception) { problem(e) }
        }
    }

    fun calendar(action: String) {
        busy = true
        scope.launch {
            try {
                withContext(Dispatchers.IO) { api.inviteCalendar(mail, action) }
                busy = false
                note = if (action == "add") "Added to your calendar." else "Removed from your calendar."
                refresh += 1
            } catch (e: Exception) { problem(e) }
        }
    }

    val organiser = if (inv.organizerName.isNotBlank()) inv.organizerName + " (" + inv.organizerEmail + ")" else inv.organizerEmail
    val status = when {
        inv.cancelled -> "Cancelled"
        inv.response == "accepted" -> "You accepted"
        inv.response == "tentative" -> "You said maybe"
        inv.response == "declined" -> "You declined"
        inv.response == "added" -> "Added to your calendar"
        inv.proposed -> "New time suggested"
        else -> "Not answered"
    }
    val blocked = busy || undoId.isNotEmpty() || (inv.organizerDiffers && !confirmed)

    Surface(color = Panel, shape = RoundedCornerShape(16.dp), border = BorderStroke(1.dp, Line), modifier = Modifier.fillMaxWidth().padding(top = 14.dp)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(if (inv.cancelled) "Cancelled meeting" else if (inv.canAnswer) "Meeting invitation" else "Calendar event", color = Muted, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
            Text(inv.summary, color = Ink, fontSize = 18.sp, fontWeight = FontWeight.Bold)
            Text(status, color = if (inv.response == "accepted" || inv.response == "added") Green else Blue, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
            Text(whenText(inv) + if (inv.allDay) "" else " (your time)", color = Ink, fontSize = 15.sp)
            if (inv.location.isNotBlank()) Text("Where: " + inv.location, color = Ink, fontSize = 15.sp)
            if (inv.organizerEmail.isNotBlank()) Text("From: " + organiser, color = Ink, fontSize = 15.sp)
            if (inv.repeats) Text("Repeats. Your answer covers the whole series.", color = Muted, fontSize = 13.sp)
            if (inv.description.isNotBlank()) Text(inv.description, color = Muted, fontSize = 13.sp, maxLines = 6)

            if (inv.cancelled) {
                Text("This meeting was cancelled.", color = Muted, fontSize = 13.sp)
                if (inv.calendar.isNotBlank() && (inv.response == "accepted" || inv.response == "tentative" || inv.response == "added")) {
                    OutlinedButton(onClick = { calendar("remove") }, enabled = !busy, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp), shape = RoundedCornerShape(12.dp), border = BorderStroke(1.dp, Line)) {
                        Text("Remove from my calendar", color = Ink)
                    }
                }
            } else if (inv.canAnswer) {
                if (inv.organizerDiffers) {
                    Surface(color = PanelHigh, shape = RoundedCornerShape(12.dp), border = BorderStroke(1.dp, Amber), modifier = Modifier.fillMaxWidth().padding(top = 4.dp)) {
                        Column(Modifier.padding(12.dp)) {
                            Text("Be careful: this invitation names " + inv.organizerEmail + " as the organiser, but the email is from someone else. Your answer would go to the organiser.", color = Ink, fontSize = 13.sp)
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Checkbox(checked = confirmed, onCheckedChange = { confirmed = it })
                                Text("Send my answer to " + inv.organizerEmail + " anyway", color = Ink, fontSize = 13.sp)
                            }
                        }
                    }
                }
                Button(onClick = { answer("accepted") }, enabled = !blocked, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp).padding(top = 4.dp), shape = RoundedCornerShape(12.dp)) { Text("Accept") }
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = { answer("tentative") }, enabled = !blocked, modifier = Modifier.weight(1f).heightIn(min = 48.dp), shape = RoundedCornerShape(12.dp), border = BorderStroke(1.dp, Line)) { Text("Maybe", color = Ink) }
                    OutlinedButton(onClick = { answer("declined") }, enabled = !blocked, modifier = Modifier.weight(1f).heightIn(min = 48.dp), shape = RoundedCornerShape(12.dp), border = BorderStroke(1.dp, Line)) { Text("Decline", color = Ink) }
                }
                OutlinedButton(onClick = { proposing = true }, enabled = !blocked, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp), shape = RoundedCornerShape(12.dp), border = BorderStroke(1.dp, Line)) { Text("Propose new time", color = Ink) }
                Text(
                    "Your answer is sent to " + (inv.organizerName.ifBlank { inv.organizerEmail }) + " by email from " + inv.mine + "." +
                        if (inv.calendar.isNotBlank()) " Accepting adds the meeting to " + inv.calendar + "." else " No calendar is connected, so nothing will be added to one (set it up on the website, Settings, Calendar and to-do).",
                    color = Muted, fontSize = 12.sp,
                )
            } else if (inv.canAdd) {
                if (inv.calendar.isNotBlank()) {
                    Button(onClick = { calendar("add") }, enabled = !busy, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp), shape = RoundedCornerShape(12.dp)) { Text("Add to my calendar") }
                } else {
                    Text("This is a calendar event. Connect a calendar on the website (Settings, Calendar and to-do) to add it.", color = Muted, fontSize = 12.sp)
                }
            }

            if (undoId.isNotEmpty()) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("Sending in " + undoLeft + " seconds", color = Ink, fontSize = 13.sp, modifier = Modifier.weight(1f))
                    TextButton(onClick = {
                        val id = undoId
                        scope.launch {
                            try {
                                withContext(Dispatchers.IO) { api.cancelSend(id) }
                                undoLeft = 0
                                undoId = ""
                                note = "Not sent. Your answer was taken back."
                            } catch (_: Exception) { note = "It may already have been sent." }
                        }
                    }) { Text("Undo", color = Blue) }
                }
            }
            if (note.isNotBlank()) Text(note, color = Muted, fontSize = 13.sp)
            if (inv.calendarProblem.isNotBlank()) Text("The meeting could not be put in your calendar: " + inv.calendarProblem, color = Amber, fontSize = 13.sp)
            else if (inv.calendar.isNotBlank() && (inv.response == "accepted" || inv.response == "tentative" || inv.response == "added")) Text("It is in " + inv.calendar + ".", color = Muted, fontSize = 13.sp)
        }
    }

    if (proposing) ProposeScreen(
        inv = inv, busy = busy,
        onClose = { proposing = false },
        onSend = { startSeconds, endSeconds, text ->
            busy = true
            scope.launch {
                try {
                    val sent = withContext(Dispatchers.IO) { api.proposeInvite(mail, startSeconds, endSeconds, TimeZone.getDefault().id, text, confirmed) }
                    proposing = false
                    finished(sent)
                } catch (e: Exception) { problem(e); proposing = false }
            }
        },
    )
}

/** Propose a new time: a full-screen form with Close at the top and the buttons at the bottom, so they can always be reached. */
@Composable
private fun ProposeScreen(inv: Invite, busy: Boolean, onClose: () -> Unit, onSend: (Double, Double, String) -> Unit) {
    val context = LocalContext.current
    val originalMinutes = if (inv.start != null && inv.end != null && inv.end > inv.start) ((inv.end - inv.start) / 60).toInt().coerceIn(15, 24 * 60) else 60
    var startMs by remember { mutableStateOf<Long?>(null) }
    var minutes by remember { mutableStateOf(originalMinutes) }
    var text by remember { mutableStateOf("") }
    val options = listOf(15, 30, 45, 60, 90, 120).let { if (it.contains(originalMinutes)) it else (it + originalMinutes).sorted() }
    fun label(ms: Long): String = SimpleDateFormat(DateFormat.getBestDateTimePattern(Locale.getDefault(), "EEE d MMM jmm"), Locale.getDefault()).format(Date(ms))

    Dialog(onDismissRequest = onClose, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(color = Navy, modifier = Modifier.fillMaxSize().imePadding()) {
            Column(Modifier.fillMaxSize()) {
                Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text("Propose a new time", color = Ink, fontSize = 18.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                    TextButton(onClick = onClose) { Text("Close", color = Blue) }
                }
                Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                    Text((inv.organizerName.ifBlank { inv.organizerEmail }) + " asked for " + whenText(inv) + ".", color = Muted, fontSize = 14.sp)
                    Text("New time", color = Ink, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
                    OutlinedButton(
                        onClick = { pickDateAndTime(context) { ms, _ -> startMs = ms } },
                        modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp), shape = RoundedCornerShape(12.dp), border = BorderStroke(1.dp, Line),
                    ) { Text(startMs?.let { label(it) } ?: "Pick a day and time", color = Ink) }
                    Text("How long", color = Ink, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        options.chunked(3).forEach { rowOptions ->
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                rowOptions.forEach { m ->
                                    OutlinedButton(
                                        onClick = { minutes = m },
                                        modifier = Modifier.weight(1f).heightIn(min = 48.dp), shape = RoundedCornerShape(12.dp),
                                        border = BorderStroke(if (minutes == m) 2.dp else 1.dp, if (minutes == m) Blue else Line),
                                    ) { Text(if (m < 60) "$m min" else if (m % 60 == 0) (m / 60).toString() + (if (m == 60) " hour" else " hours") else "$m min", color = Ink, fontSize = 13.sp) }
                                }
                            }
                        }
                    }
                    OutlinedTextField(value = text, onValueChange = { if (it.length <= 500) text = it }, label = { Text("Note (optional)") }, modifier = Modifier.fillMaxWidth(), minLines = 3)
                    Text("This sends a normal email with your suggestion. Calendar apps do not all understand proposals, so it is written in plain words. Your calendar is not changed.", color = Muted, fontSize = 13.sp)
                }
                Row(Modifier.fillMaxWidth().padding(16.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    OutlinedButton(onClick = onClose, modifier = Modifier.weight(1f).heightIn(min = 52.dp), shape = RoundedCornerShape(12.dp), border = BorderStroke(1.dp, Line)) { Text("Cancel", color = Ink) }
                    Button(
                        onClick = { startMs?.let { onSend(it / 1000.0, (it + minutes * 60_000L) / 1000.0, text) } },
                        enabled = startMs != null && !busy,
                        modifier = Modifier.weight(1f).heightIn(min = 52.dp), shape = RoundedCornerShape(12.dp),
                    ) { Text("Send suggestion") }
                }
            }
        }
    }
}
