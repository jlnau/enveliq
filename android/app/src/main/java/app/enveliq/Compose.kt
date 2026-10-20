package app.enveliq

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.material3.IconButton
import androidx.compose.ui.layout.positionInParent
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.foundation.layout.widthIn
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Surface
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
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
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** What the writing screen is for. [kind] is new, reply, reply_all or forward; [mail] is the email being answered or forwarded; [draft] is a saved draft being continued. */
data class ComposeTarget(val kind: String, val mail: Mail? = null, val draft: Draft? = null, val presetSubject: String = "", val presetBody: String = "", val presetTo: String = "")

/** A file chosen to attach. Kept in memory only. */
class PickedFile(val name: String, val type: String, val bytes: ByteArray)

private fun sizeText(n: Int): String = if (n >= 1024 * 1024) String.format(java.util.Locale.US, "%.1f MB", n / 1048576.0) else maxOf(1, n / 1024).toString() + " KB"

private fun readPicked(context: android.content.Context, uri: android.net.Uri): PickedFile? = try {
    val resolver = context.contentResolver
    var name = "attachment"
    resolver.query(uri, arrayOf(android.provider.OpenableColumns.DISPLAY_NAME), null, null, null)?.use { if (it.moveToFirst()) name = it.getString(0) ?: name }
    val bytes = resolver.openInputStream(uri)?.use { it.readBytes() }
    if (bytes == null) null else PickedFile(name, resolver.getType(uri) ?: "application/octet-stream", bytes)
} catch (e: Exception) { null }

private val SEPARATORS = Regex("[,;\\s]+")

private fun addresses(text: String): List<String> = text.split(SEPARATORS).map { it.trim() }.filter { it.isNotEmpty() }

/** The people in a box plus whatever is still being typed, each once. */
private fun people(done: String, typing: String): List<String> = (addresses(done) + addresses(typing)).distinctBy { it.lowercase() }

private fun badAddress(list: List<String>): String? =
    list.firstOrNull { !it.contains("@") || it.startsWith("@") || it.endsWith("@") }

private fun kindName(kind: String) = when (kind) {
    "reply" -> "Reply"
    "reply_all" -> "Reply all"
    "forward" -> "Forward"
    else -> "New email"
}

/** The full-screen writing screen: Close at the top, Send and Save draft fixed at the bottom, only the middle scrolls. */
@Composable
fun ComposeScreen(target: ComposeTarget, api: EnveliqApi, onClose: () -> Unit, onSent: (Sent) -> Unit) {
    val kind = target.kind
    val mail = target.mail
    val draft = target.draft
    val isReply = kind == "reply" || kind == "reply_all"
    // A reply starts with the people the website would offer: the sender (and, for Reply all, the others and Cc). All of it can be changed.
    val startTo = if (isReply && mail != null) (listOf(mail.replyTo.ifBlank { mail.address }) + (if (kind == "reply_all") mail.replyAlsoTo else emptyList())).filter { it.isNotBlank() } else emptyList()
    val startCc = if (kind == "reply_all" && mail != null) mail.replyCc else emptyList()
    var to by remember { mutableStateOf(if (draft != null && draft.to.isNotEmpty()) draft.to.joinToString(", ") else startTo.joinToString(", ").ifBlank { target.presetTo }) }
    var cc by remember { mutableStateOf(if (draft != null && draft.to.isNotEmpty()) draft.cc.joinToString(", ") else startCc.joinToString(", ")) }
    var bcc by remember { mutableStateOf(draft?.bcc?.joinToString(", ") ?: "") }
    // What has been typed in a box but not yet turned into a person (Enter, a comma or a space does that). Send and Save draft take it too.
    var toTyping by remember { mutableStateOf("") }
    var ccTyping by remember { mutableStateOf("") }
    var bccTyping by remember { mutableStateOf("") }
    var showCc by remember { mutableStateOf(cc.isNotBlank() || bcc.isNotBlank()) }
    var subject by remember { mutableStateOf(if (kind == "new") draft?.subject ?: target.presetSubject else "") }
    var body by remember { mutableStateOf(draft?.body ?: target.presetBody) }
    var options by remember { mutableStateOf<List<FromOption>>(emptyList()) }
    var from by remember { mutableStateOf<FromOption?>(null) }
    val boxId = from?.accountId ?: ""
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }
    var askClose by remember { mutableStateOf(false) }
    var askLater by remember { mutableStateOf(false) }
    var laterLabel by remember { mutableStateOf("") }
    val scope = rememberCoroutineScope()
    val writeInfo = rememberWriteHelp(api)
    val wh = remember { WriteHelpState() }
    var askCheck by remember { mutableStateOf(false) }          // "Send what is in your box?" after using writing help
    var quickBusy by remember { mutableStateOf(false) }
    val context = androidx.compose.ui.platform.LocalContext.current
    // Files for a new email. They are held in memory only, sent, and never saved on this phone.
    val files = remember { androidx.compose.runtime.mutableStateListOf<PickedFile>() }
    val picker = androidx.activity.compose.rememberLauncherForActivityResult(androidx.activity.result.contract.ActivityResultContracts.GetMultipleContents()) { uris ->
        for (uri in uris) {
            val f = readPicked(context, uri)
            if (f == null) { error = "That file could not be read."; continue }
            if (files.size >= 10) { error = "You can attach up to 10 files."; break }
            if (files.sumOf { it.bytes.size } + f.bytes.size > 10 * 1024 * 1024) { error = "Files can add up to 10 MB at most."; break }
            files.add(f)
        }
    }
    // "Pick a person" from the phone's contacts. Android hands over only the one address chosen, so no contacts permission is needed.
    val contactPicker = androidx.activity.compose.rememberLauncherForActivityResult(androidx.activity.result.contract.ActivityResultContracts.StartActivityForResult()) { res ->
        val uri = res.data?.data ?: return@rememberLauncherForActivityResult
        val address = try {
            context.contentResolver.query(uri, arrayOf(android.provider.ContactsContract.CommonDataKinds.Email.ADDRESS), null, null, null)?.use { if (it.moveToFirst()) it.getString(0) else null }
        } catch (e: Exception) { null }
        if (address.isNullOrBlank()) error = "Could not read that contact's address." else to = if (to.isBlank()) address else to.trimEnd(',', ' ') + ", " + address
    }

    val original = mail?.subject.orEmpty().ifBlank { "(no subject)" }
    val shownSubject = when (kind) {
        "reply", "reply_all" -> "Re: $original"
        "forward" -> "Fwd: $original"
        else -> subject
    }
    val hasContent = body.isNotBlank() || to.isNotBlank() || toTyping.isNotBlank() || (kind == "new" && subject.isNotBlank())

    // Your signature (from Settings on the website) is put in the box when a new message starts, where you can change or remove it.
    LaunchedEffect(Unit) {
        if (draft == null && body.isBlank()) {
            try {
                val sig = withContext(Dispatchers.IO) { api.signature() }
                if (sig.isNotBlank() && body.isBlank()) body = "\n\n" + sig
            } catch (_: Exception) { }
        }
    }

    LaunchedEffect(Unit) {
        try {
            val all = withContext(Dispatchers.IO) { api.fromOptions() }
            // A reply or forward is sent from the mailbox the email arrived in; a new email can use any of them.
            val usable = if (kind == "new") all else all.filter { it.accountId == mail?.accountId }
            options = usable
            from = usable.firstOrNull { draft != null && draft.fromAddress.isNotBlank() && it.address.equals(draft.fromAddress, ignoreCase = true) }
                ?: usable.firstOrNull { draft != null && draft.accountId.isNotBlank() && it.accountId == draft.accountId && it.isDefault }
                ?: usable.firstOrNull { it.isDefault }
                ?: usable.firstOrNull()
        } catch (e: ApiException) {
            error = e.message ?: "Could not find your mailboxes."
        } catch (e: Exception) {
            error = "Could not find your mailboxes."
        }
    }

    fun requestClose() {
        if (hasContent && !busy) askClose = true else onClose()
    }
    BackHandler { requestClose() }

    fun saveDraftThenClose() {
        busy = true
        scope.launch {
            try {
                val toSave = Draft(
                    id = "", kind = kind, accountId = if (kind == "new") boxId else mail?.accountId ?: "",
                    messageId = mail?.id ?: "", to = people(to, toTyping), cc = people(cc, ccTyping), bcc = people(bcc, bccTyping),
                    subject = shownSubject, body = body, fromAddress = from?.address ?: "",
                )
                withContext(Dispatchers.IO) { api.saveDraft(draft?.id, toSave) }
                onClose()
            } catch (e: ApiException) {
                error = e.message ?: "Could not save the draft."
                askClose = false
            } catch (e: Exception) {
                error = "Could not save the draft."
                askClose = false
            } finally {
                busy = false
            }
        }
    }

    fun send(laterAtMs: Long? = null, bodyOverride: String? = null, subjectOverride: String? = null, checked: Boolean = false) {
        error = ""
        val text = bodyOverride ?: body
        val subj = subjectOverride ?: subject
        val toList = people(to, toTyping)
        val ccList = people(cc, ccTyping)
        val bccList = people(bcc, bccTyping)
        val bad = badAddress(toList + ccList + bccList)
        if (bad != null) {
            error = "\"$bad\" does not look like an email address."
            return
        }
        if (toList.isEmpty()) {
            error = "Add who it is going to."
            return
        }
        if ((kind == "reply" || kind == "reply_all") && text.isBlank()) {
            error = "Write your reply first."
            return
        }
        if (kind == "new" && boxId.isBlank()) {
            error = "There is no mailbox to send from."
            return
        }
        if (laterAtMs != null && files.isNotEmpty()) {
            error = "Files cannot wait for later. Send now, or take the files off."
            return
        }
        // Words the AI suggested are only sent after a clear "yes" (Quick AI Send asks for that in advance by pressing its own button).
        if (wh.used && !checked && bodyOverride == null && laterAtMs == null) { askCheck = true; return }
        busy = true
        val chosen = from?.takeIf { !it.isDefault }?.address        // the mailbox's own address is the default, so nothing is sent for it
        scope.launch {
            try {
                val result = withContext(Dispatchers.IO) {
                    if (laterAtMs != null) {
                        val id = api.scheduleSend(kind, if (kind == "new") boxId else mail!!.accountId, mail?.id, toList, ccList, bccList, subj, text, chosen, laterAtMs / 1000.0)
                        return@withContext Sent(false, "", 0, id, laterLabel)
                    }
                    when (kind) {
                        "reply" -> api.reply(mail!!, false, text, chosen, files.toList(), toList, ccList, bccList)
                        "reply_all" -> api.reply(mail!!, true, text, chosen, files.toList(), toList, ccList, bccList)
                        "forward" -> api.forward(mail!!, toList, ccList, bccList, text, chosen, files.toList())
                        else -> api.sendNew(boxId, toList, ccList, bccList, subj, text, chosen, files.toList())
                    }
                }
                if (draft != null) {
                    try {
                        withContext(Dispatchers.IO) { api.deleteDraft(draft.id) }
                    } catch (_: Exception) {
                    }
                }
                onSent(result)
            } catch (e: ApiException) {
                error = e.message ?: "That did not send."
            } catch (e: Exception) {
                error = "That did not send. Please try again."
            } finally {
                busy = false
            }
        }
    }

    // Quick AI Send: a strict proofread, then the normal send. The text box is never changed, so if anything fails the draft is exactly as it was.
    fun quickSend() {
        error = ""
        if (body.isBlank()) { error = if (kind == "forward") "Add a note first, or use Send." else "Write your message first."; return }
        quickBusy = true
        scope.launch {
            try {
                val fixed = withContext(Dispatchers.IO) { api.quickFix(if (kind == "new") subject else "", body) }
                quickBusy = false
                send(null, fixed.text, if (kind == "new") fixed.subject.ifBlank { subject } else null, true)
            } catch (e: ApiException) {
                error = e.message ?: "Quick AI Send did not work. Your message is still here."
            } catch (e: Exception) {
                error = "Quick AI Send did not work. Your message is still here."
            } finally {
                quickBusy = false
            }
        }
    }

    val scroll = rememberScrollState()
    var viewH by remember { mutableStateOf(0) }
    var bodyTop by remember { mutableStateOf(0) }
    var bodyFocused by remember { mutableStateOf(false) }
    LaunchedEffect(bodyFocused, viewH) { if (bodyFocused) scroll.animateScrollTo(bodyTop) }      // tapped the message: bring it up above the keyboard
    val askWrite = rememberWriteAsk(api, mail, subject, body, kind == "new", wh)
    Column(Modifier.fillMaxSize().background(Navy).systemBarsPadding().imePadding()) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = { requestClose() }) { Text("Close", color = Blue, fontSize = 16.sp) }
            Text(kindName(kind), color = Ink, fontSize = 20.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f).padding(start = 8.dp))
            IconButton(onClick = { askLater = true }, enabled = !busy, modifier = Modifier.semantics { contentDescription = "Send later" }) { ClockIcon(if (busy) Muted else Ink) }
            Button(
                onClick = { send() }, enabled = !busy, shape = RoundedCornerShape(10.dp),
                contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 16.dp), modifier = Modifier.height(38.dp).padding(end = 6.dp),
            ) {
                if (busy) CircularProgressIndicator(Modifier.size(18.dp), color = Ink, strokeWidth = 2.dp)
                else Text("Send", fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
            }
        }
        Column(
            Modifier.weight(1f).onSizeChanged { viewH = it.height }.verticalScroll(scroll).padding(horizontal = 20.dp),
        ) {
            if (options.size > 1) FromPicker(options, from) { from = it }
            AddressField("To", to, { to = it }, toTyping, { toTyping = it }, api)
            if (kind == "reply") Text("Starts with the sender. Add or take off anyone.", color = Muted, fontSize = 13.sp)
            if (kind == "reply_all") Text("Starts with the sender, the other people on the email and everyone on Cc. Take off anyone you like.", color = Muted, fontSize = 13.sp)
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                TextButton(onClick = {
                    try { contactPicker.launch(android.content.Intent(android.content.Intent.ACTION_PICK, android.provider.ContactsContract.CommonDataKinds.Email.CONTENT_URI)) }
                    catch (e: Exception) { error = "This phone has no contacts app to pick from." }
                }) { Text("Contacts", color = Blue, fontSize = 14.sp) }
                if (!showCc) TextButton(onClick = { showCc = true }) { Text("Cc or Bcc", color = Blue, fontSize = 14.sp) }
            }
            if (showCc) {
                AddressField("Cc", cc, { cc = it }, ccTyping, { ccTyping = it }, api)
                AddressField("Bcc", bcc, { bcc = it }, bccTyping, { bccTyping = it }, api)
            }
            if (kind == "new") {
                Text("Subject", color = Muted, fontSize = 14.sp, modifier = Modifier.padding(top = 12.dp, bottom = 6.dp))
                SpellField(subject, { subject = it }, singleLine = true, modifier = Modifier.fillMaxWidth())
            } else {
                Text(shownSubject, color = Ink, fontSize = 17.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 12.dp))
                if (kind == "forward") Text("The email you are forwarding goes underneath, with its files.", color = Muted, fontSize = 13.sp, modifier = Modifier.padding(top = 2.dp))
            }
            Text(if (kind == "forward") "Your note (optional)" else "Message", color = Muted, fontSize = 14.sp, modifier = Modifier.padding(top = 14.dp, bottom = 6.dp))
            // The box is as tall as the space above the keyboard, and when you tap it the page scrolls so it sits at the top of that space.
            val boxH = with(androidx.compose.ui.platform.LocalDensity.current) { (viewH.toDp() - 40.dp).coerceAtLeast(140.dp) }
            SpellField(
                body, { body = it }, singleLine = false, minLines = 3, onFocus = { bodyFocused = it },
                modifier = Modifier.fillMaxWidth().height(boxH).onGloballyPositioned { bodyTop = it.positionInParent().y.toInt() },
            )
            if (writeInfo != null && (kind == "new" || mail != null)) {
                WriteHelpBox(api, writeInfo, mail, subject, body, kind == "new", wh) { body = it }
            }
            run {
                files.forEachIndexed { i, f ->
                    Row(Modifier.fillMaxWidth().padding(top = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text(f.name + " (" + sizeText(f.bytes.size) + ")", color = Ink, fontSize = 15.sp, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                        TextButton(onClick = { files.removeAt(i) }) { Text("Remove", color = Red) }
                    }
                }
            }
            if (kind == "reply" || kind == "reply_all") {
                Text("The email you are answering is added underneath.", color = Muted, fontSize = 13.sp, modifier = Modifier.padding(top = 6.dp))
            }
            if (error.isNotEmpty()) Text(error, color = Red, fontSize = 15.sp, modifier = Modifier.padding(top = 12.dp, bottom = 8.dp))
            Spacer(Modifier.height(16.dp))
        }
        val helpOn = writeInfo != null && writeInfo.on && writeInfo.aiReady && (kind == "new" || mail != null)
        val quickOn = helpOn && writeInfo != null && writeInfo.quick
        val tight = androidx.compose.foundation.layout.PaddingValues(horizontal = 10.dp)
        Column(Modifier.fillMaxWidth().background(Panel).padding(horizontal = 12.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            if (helpOn) Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                OutlinedButton(
                    onClick = { askWrite() }, enabled = !busy && !wh.busy, contentPadding = tight,
                    modifier = Modifier.weight(1f).height(44.dp), shape = RoundedCornerShape(12.dp), border = BorderStroke(1.dp, Line),
                ) { Text(writeHelpLabel(wh, body, kind == "new"), color = Blue, fontSize = 14.sp, maxLines = 1) }
                if (quickOn) OutlinedButton(
                    onClick = { quickSend() }, enabled = !busy && !quickBusy, contentPadding = tight,
                    modifier = Modifier.weight(1f).height(44.dp), shape = RoundedCornerShape(12.dp), border = BorderStroke(1.dp, Blue),
                ) { Text(if (quickBusy) "Checking…" else "Quick AI send", color = Blue, fontSize = 14.sp, maxLines = 1) }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                OutlinedButton(
                    onClick = { picker.launch("*/*") }, contentPadding = tight,
                    modifier = Modifier.weight(1f).height(44.dp), shape = RoundedCornerShape(12.dp), border = BorderStroke(1.dp, Line),
                ) { Text(if (files.isEmpty()) "Attach files" else "Attach more", color = Ink, fontSize = 14.sp, maxLines = 1) }
                OutlinedButton(
                    onClick = { saveDraftThenClose() }, enabled = !busy && hasContent, contentPadding = tight,
                    modifier = Modifier.weight(1f).height(44.dp), shape = RoundedCornerShape(12.dp), border = BorderStroke(1.dp, Line),
                ) { Text("Save draft", color = Ink, fontSize = 14.sp, maxLines = 1) }
            }
        }
    }

    if (askCheck) {
        val gap = hasGap(body)
        AlertDialog(
            onDismissRequest = { askCheck = false },
            containerColor = Panel,
            title = { Text("Send what is in your box?", color = Ink) },
            text = {
                Column {
                    Text("You used writing help. Only what is in your box will be sent, not the AI box.", color = Muted)
                    if (wh.backup != null) Text("This includes wording suggested by AI.", color = Muted, modifier = Modifier.padding(top = 6.dp))
                    if (gap) Text("There are still [brackets] left to fill in.", color = Amber, modifier = Modifier.padding(top = 6.dp))
                    Text(body.take(600), color = Ink, fontSize = 14.sp, modifier = Modifier.padding(top = 10.dp))
                }
            },
            confirmButton = { TextButton(onClick = { askCheck = false; send(checked = true) }) { Text(if (gap) "Send anyway" else "Yes, send it", color = Blue) } },
            dismissButton = { TextButton(onClick = { askCheck = false }) { Text("Go back", color = Muted) } },
        )
    }

    if (askLater) {
        fun at(daysAhead: Int, hour: Int): Long {
            val c = java.util.Calendar.getInstance()
            c.add(java.util.Calendar.DAY_OF_YEAR, daysAhead)
            c.set(java.util.Calendar.HOUR_OF_DAY, hour); c.set(java.util.Calendar.MINUTE, 0); c.set(java.util.Calendar.SECOND, 0); c.set(java.util.Calendar.MILLISECOND, 0)
            return c.timeInMillis
        }
        fun pick(ms: Long, words: String) { askLater = false; laterLabel = words; send(ms) }
        AlertDialog(
            onDismissRequest = { askLater = false },
            containerColor = Panel,
            title = { Text("Send later", color = Ink) },
            text = {
                Column {
                    Text("Enveliq keeps it, and sends it from your mailbox at that time. Files cannot wait.", color = Muted, fontSize = 13.sp)
                    TextButton(onClick = { pick(System.currentTimeMillis() + 3 * 3600_000L, "in 3 hours") }) { Text("In 3 hours", color = Blue, fontSize = 16.sp) }
                    TextButton(onClick = {
                        val evening = at(0, 18)
                        if (evening > System.currentTimeMillis() + 60_000L) pick(evening, "this evening") else pick(at(1, 18), "tomorrow evening")
                    }) { Text("This evening", color = Blue, fontSize = 16.sp) }
                    TextButton(onClick = { pick(at(1, 8), "tomorrow morning") }) { Text("Tomorrow morning", color = Blue, fontSize = 16.sp) }
                    TextButton(onClick = {
                        val c = java.util.Calendar.getInstance()
                        val toMonday = ((java.util.Calendar.MONDAY - c.get(java.util.Calendar.DAY_OF_WEEK) + 7) % 7).let { if (it == 0) 7 else it }
                        pick(at(toMonday, 8), "on Monday morning")
                    }) { Text("Next Monday morning", color = Blue, fontSize = 16.sp) }
                }
            },
            confirmButton = {},
            dismissButton = { TextButton(onClick = { askLater = false }) { Text("Cancel", color = Muted) } },
        )
    }

    if (askClose) {
        AlertDialog(
            onDismissRequest = { askClose = false },
            containerColor = Panel,
            title = { Text("Keep this as a draft?", color = Ink) },
            text = { Text("Drafts are kept for 14 days. You can find them in the Drafts tab.", color = Muted) },
            confirmButton = { TextButton(onClick = { saveDraftThenClose() }) { Text("Save draft", color = Blue) } },
            dismissButton = {
                Row {
                    TextButton(onClick = { askClose = false }) { Text("Keep writing", color = Muted) }
                    TextButton(onClick = { onClose() }) { Text("Discard", color = Red) }
                }
            },
        )
    }
}

/** Who the email goes out as. Tap to choose another of your addresses or aliases. */
@Composable
private fun FromPicker(options: List<FromOption>, selected: FromOption?, onPick: (FromOption) -> Unit) {
    var open by remember { mutableStateOf(false) }
    Box(Modifier.fillMaxWidth().padding(top = 8.dp)) {
        Surface(color = Panel, shape = RoundedCornerShape(14.dp), border = BorderStroke(1.dp, Line), modifier = Modifier.fillMaxWidth().clickable { open = true }) {
            Row(Modifier.padding(horizontal = 16.dp, vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                Text("From", color = Muted, fontSize = 14.sp)
                Column(Modifier.weight(1f).padding(horizontal = 14.dp)) {
                    Text(selected?.address ?: "", color = Ink, fontSize = 16.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    if (selected != null && selected.label != selected.address) Text(selected.label, color = Muted, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
                Text("▾", color = Muted, fontSize = 16.sp)
            }
        }
        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            options.forEach { o ->
                DropdownMenuItem(
                    text = {
                        Column {
                            Text(o.address, fontSize = 16.sp)
                            Text(if (o.isDefault) o.label + " · main address" else o.label + " · alias", fontSize = 12.sp)
                        }
                    },
                    onClick = { open = false; onPick(o) },
                )
            }
        }
    }
}

/**
 * One or more people. Each address becomes a small chip with a cross to take it off; type the next one and press Enter, a comma or a space.
 * Suggestions from your address list appear as you type a name.
 */
@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
private fun AddressField(label: String, value: String, onChange: (String) -> Unit, typing: String, onTyping: (String) -> Unit, api: EnveliqApi) {
    var found by remember { mutableStateOf<List<Contact>>(emptyList()) }
    val items = addresses(value)
    fun add(text: String) {
        val more = addresses(text)
        if (more.isNotEmpty()) onChange((items + more).distinctBy { it.lowercase() }.joinToString(", "))
        onTyping("")
        found = emptyList()
    }
    val token = typing.trim()
    LaunchedEffect(token) {
        found = emptyList()
        if (token.length < 2 || token.contains("@")) return@LaunchedEffect
        delay(250)
        try {
            found = withContext(Dispatchers.IO) { api.contacts(token) }
        } catch (_: Exception) {
            // The address list may be switched off; typing an address still works.
        }
    }
    Text(label, color = Muted, fontSize = 14.sp, modifier = Modifier.padding(top = 12.dp, bottom = 6.dp))
    if (items.isNotEmpty()) {
        androidx.compose.foundation.layout.FlowRow(
            horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp),
            modifier = Modifier.fillMaxWidth().padding(bottom = 6.dp),
        ) {
            items.forEach { who ->
                val odd = !who.contains("@") || who.startsWith("@") || who.endsWith("@")
                Surface(color = PanelHigh, shape = RoundedCornerShape(50), border = BorderStroke(1.dp, if (odd) Red else Line)) {
                    Row(
                        Modifier.clickable { onChange(items.filter { it != who }.joinToString(", ")) }.padding(start = 12.dp, end = 8.dp, top = 6.dp, bottom = 6.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(who, color = Ink, fontSize = 14.sp, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.widthIn(max = 240.dp))
                        Text("  ✕", color = Muted, fontSize = 14.sp, modifier = Modifier.semantics { contentDescription = "Take off $who" })
                    }
                }
            }
        }
    }
    OutlinedTextField(
        value = typing,
        onValueChange = { v -> if (v.endsWith(",") || v.endsWith(";") || v.endsWith(" ") || v.endsWith("\n")) add(v) else onTyping(v) },
        singleLine = true,
        placeholder = { Text(if (items.isEmpty()) "Type a name or an address" else "Add another person") },
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email, imeAction = androidx.compose.ui.text.input.ImeAction.Next),
        keyboardActions = androidx.compose.foundation.text.KeyboardActions(onNext = { add(typing) }),
        modifier = Modifier.fillMaxWidth().onFocusChanged { if (!it.isFocused && typing.isNotBlank()) add(typing) },
    )
    found.take(5).forEach { c ->
        TextButton(onClick = { add(c.address) }) {
            Text((if (c.name.isNotBlank()) c.name + "  " else "") + c.address, color = Blue, fontSize = 15.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
    }
}

/** The Drafts tab: emails you started and have not sent. Tap one to carry on. */
@Composable
fun DraftsTab(api: EnveliqApi, onOpen: (Draft) -> Unit) {
    var items by remember { mutableStateOf<List<Draft>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf("") }
    val scope = rememberCoroutineScope()

    fun load() {
        loading = true
        error = ""
        scope.launch {
            try {
                items = withContext(Dispatchers.IO) { api.drafts() }
            } catch (e: ApiException) {
                error = e.message ?: "Could not load your drafts."
            } catch (e: Exception) {
                error = "Could not load your drafts."
            } finally {
                loading = false
            }
        }
    }
    LaunchedEffect(Unit) { load() }

    Column(Modifier.fillMaxSize()) {
        Heading("Drafts", if (items.isEmpty()) "" else "${items.size} saved for 14 days")
        when {
            loading && items.isEmpty() -> Column(Modifier.fillMaxSize(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) { CircularProgressIndicator(color = Blue) }
            error.isNotEmpty() -> Column(Modifier.padding(24.dp)) {
                Text(error, color = Red, fontSize = 16.sp)
                OutlinedButton(onClick = { load() }, modifier = Modifier.padding(top = 14.dp)) { Text("Try again") }
            }
            items.isEmpty() -> Text("No drafts. Emails you start but do not send are kept here for 14 days.", color = Muted, fontSize = 16.sp, modifier = Modifier.padding(20.dp))
            else -> LazyColumn(Modifier.fillMaxSize()) {
                items(items, key = { it.id }) { d ->
                    Column(Modifier.fillMaxWidth().clickable { onOpen(d) }.padding(horizontal = 20.dp, vertical = 12.dp)) {
                        Text(kindName(d.kind), color = Blue, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                        Text(d.subject.ifBlank { "(no subject)" }, color = Ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        if (d.to.isNotEmpty()) Text("To: " + d.to.joinToString(", "), color = Muted, fontSize = 14.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        if (d.body.isNotBlank()) Text(d.body.take(120), color = Muted, fontSize = 14.sp, maxLines = 2, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(top = 2.dp))
                        TextButton(onClick = {
                            scope.launch {
                                try {
                                    withContext(Dispatchers.IO) { api.deleteDraft(d.id) }
                                    items = items.filter { it.id != d.id }
                                } catch (e: Exception) {
                                    error = "Could not delete that draft."
                                }
                            }
                        }) { Text("Delete", color = Red, fontSize = 14.sp) }
                    }
                    HorizontalDivider(color = Line)
                }
            }
        }
    }
}
