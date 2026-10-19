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
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
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
    var to by remember { mutableStateOf(draft?.to?.joinToString(", ") ?: target.presetTo) }
    var cc by remember { mutableStateOf(draft?.cc?.joinToString(", ") ?: "") }
    var bcc by remember { mutableStateOf(draft?.bcc?.joinToString(", ") ?: "") }
    var showCc by remember { mutableStateOf(draft != null && (draft.cc.isNotEmpty() || draft.bcc.isNotEmpty())) }
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
    val hasContent = body.isNotBlank() || to.isNotBlank() || (kind == "new" && subject.isNotBlank())

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
                    messageId = mail?.id ?: "", to = addresses(to), cc = addresses(cc), bcc = addresses(bcc),
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

    fun send(laterAtMs: Long? = null) {
        error = ""
        val toList = addresses(to)
        val ccList = addresses(cc)
        val bccList = addresses(bcc)
        val bad = badAddress(toList + ccList + bccList)
        if (bad != null) {
            error = "\"$bad\" does not look like an email address."
            return
        }
        if ((kind == "forward" || kind == "new") && toList.isEmpty()) {
            error = "Add who it is going to."
            return
        }
        if ((kind == "reply" || kind == "reply_all") && body.isBlank()) {
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
        busy = true
        val chosen = from?.takeIf { !it.isDefault }?.address        // the mailbox's own address is the default, so nothing is sent for it
        scope.launch {
            try {
                val result = withContext(Dispatchers.IO) {
                    if (laterAtMs != null) {
                        val id = api.scheduleSend(kind, if (kind == "new") boxId else mail!!.accountId, mail?.id, toList, ccList, bccList, subject, body, chosen, laterAtMs / 1000.0)
                        return@withContext Sent(false, "", 0, id, laterLabel)
                    }
                    when (kind) {
                        "reply" -> api.reply(mail!!, false, body, chosen, files.toList())
                        "reply_all" -> api.reply(mail!!, true, body, chosen, files.toList())
                        "forward" -> api.forward(mail!!, toList, ccList, bccList, body, chosen, files.toList())
                        else -> api.sendNew(boxId, toList, ccList, bccList, subject, body, chosen, files.toList())
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

    Column(Modifier.fillMaxSize().background(Navy).systemBarsPadding().imePadding()) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = { requestClose() }) { Text("Close", color = Blue, fontSize = 16.sp) }
            Text(kindName(kind), color = Ink, fontSize = 20.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f).padding(start = 8.dp))
        }
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 20.dp)) {
            if (options.size > 1) FromPicker(options, from) { from = it }
            if (kind == "reply" || kind == "reply_all") {
                Text(
                    if (kind == "reply") "Going to the sender" + (mail?.address?.takeIf { it.isNotBlank() }?.let { ": $it" } ?: "")
                    else "Going to the sender and the other people on the email",
                    color = Muted, fontSize = 14.sp, modifier = Modifier.padding(top = 6.dp),
                )
                Text(shownSubject, color = Ink, fontSize = 17.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 6.dp))
            } else {
                AddressField("To", to, { to = it }, api)
                TextButton(onClick = {
                    try { contactPicker.launch(android.content.Intent(android.content.Intent.ACTION_PICK, android.provider.ContactsContract.CommonDataKinds.Email.CONTENT_URI)) }
                    catch (e: Exception) { error = "This phone has no contacts app to pick from." }
                }) { Text("Pick from phone contacts", color = Blue, fontSize = 15.sp) }
                if (showCc) {
                    AddressField("Cc", cc, { cc = it }, api)
                    AddressField("Bcc", bcc, { bcc = it }, api)
                } else {
                    TextButton(onClick = { showCc = true }) { Text("Add Cc or Bcc", color = Blue, fontSize = 15.sp) }
                }
                if (kind == "new") {
                    Text("Subject", color = Muted, fontSize = 14.sp, modifier = Modifier.padding(top = 12.dp, bottom = 6.dp))
                    OutlinedTextField(value = subject, onValueChange = { subject = it }, singleLine = true, modifier = Modifier.fillMaxWidth())
                } else {
                    Text(shownSubject, color = Ink, fontSize = 17.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 12.dp))
                    Text("The email you are forwarding goes underneath, with its files.", color = Muted, fontSize = 13.sp, modifier = Modifier.padding(top = 2.dp))
                }
            }
            Text(if (kind == "forward") "Your note (optional)" else "Message", color = Muted, fontSize = 14.sp, modifier = Modifier.padding(top = 14.dp, bottom = 6.dp))
            OutlinedTextField(value = body, onValueChange = { body = it }, minLines = 8, modifier = Modifier.fillMaxWidth())
            run {
                files.forEachIndexed { i, f ->
                    Row(Modifier.fillMaxWidth().padding(top = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text(f.name + " (" + sizeText(f.bytes.size) + ")", color = Ink, fontSize = 15.sp, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                        TextButton(onClick = { files.removeAt(i) }) { Text("Remove", color = Red) }
                    }
                }
                TextButton(onClick = { picker.launch("*/*") }) { Text(if (files.isEmpty()) "Attach files" else "Attach more files", color = Blue, fontSize = 15.sp) }
            }
            if (kind == "reply" || kind == "reply_all") {
                Text("The email you are answering is added underneath.", color = Muted, fontSize = 13.sp, modifier = Modifier.padding(top = 6.dp))
            }
            if (error.isNotEmpty()) Text(error, color = Red, fontSize = 15.sp, modifier = Modifier.padding(top = 12.dp, bottom = 8.dp))
            Spacer(Modifier.height(16.dp))
        }
        Row(
            Modifier.fillMaxWidth().background(Panel).padding(horizontal = 20.dp, vertical = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            if (hasContent) {
                OutlinedButton(
                    onClick = { saveDraftThenClose() }, enabled = !busy,
                    modifier = Modifier.height(52.dp), shape = RoundedCornerShape(14.dp), border = BorderStroke(1.dp, Line),
                ) { Text("Save draft", color = Ink) }
            }
            OutlinedButton(
                onClick = { askLater = true }, enabled = !busy,
                modifier = Modifier.height(52.dp), shape = RoundedCornerShape(14.dp), border = BorderStroke(1.dp, Line),
            ) { Text("Later", color = Ink) }
            Button(onClick = { send() }, enabled = !busy, modifier = Modifier.weight(1f).height(52.dp), shape = RoundedCornerShape(14.dp)) {
                if (busy) CircularProgressIndicator(Modifier.size(22.dp), color = Ink, strokeWidth = 2.dp)
                else Text("Send", fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
            }
        }
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

/** A box for one or more addresses, with suggestions from the address list as you type the last one. */
@Composable
private fun AddressField(label: String, value: String, onChange: (String) -> Unit, api: EnveliqApi) {
    var found by remember { mutableStateOf<List<Contact>>(emptyList()) }
    val token = value.split(SEPARATORS).lastOrNull().orEmpty()
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
    OutlinedTextField(
        value = value, onValueChange = onChange,
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
        modifier = Modifier.fillMaxWidth(),
    )
    found.take(5).forEach { c ->
        TextButton(onClick = {
            onChange(value.substring(0, value.length - token.length) + c.address + ", ")
            found = emptyList()
        }) {
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
