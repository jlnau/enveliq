package app.enveliq

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.OutlinedTextField
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

private val doNames = listOf(
    "archived" to "Archive it", "reviewed" to "Mark it as read", "junked" to "Send it to Junk", "starred" to "Star it",
    "snoozed" to "Snooze it", "safe" to "Never send it to Junk", "notasks" to "Never make tasks",
)
private val snoozeChoices = listOf(1 to "1 hour", 4 to "4 hours", 24 to "1 day", 72 to "3 days", 168 to "1 week")

private fun who(r: Rule) = if (r.sender.isBlank()) "anyone" else if (r.sender.startsWith("@")) "everyone at " + r.sender.drop(1) else r.sender

private fun doing(r: Rule): String = when (r.action) {
    "moved" -> "Move it to “" + r.folderLabel + "”"
    "tag" -> "Always apply tags"
    "snoozed" -> "Snooze it for " + (snoozeChoices.firstOrNull { it.first == r.hours }?.second ?: (r.hours.toString() + " hours"))
    else -> doNames.firstOrNull { it.first == r.action }?.second ?: r.action
}

private fun sentence(r: Rule): String {
    val bits = ArrayList<String>()
    if (r.sender.isNotBlank()) bits += "is from " + who(r)
    if (r.subject.isNotBlank()) bits += "has “" + r.subject + "” in the subject"
    if (r.notSubject.isNotBlank()) bits += "does not have “" + r.notSubject + "” in the subject"
    if (r.to.isNotBlank()) bits += "was sent to " + r.to
    if (r.list.isNotBlank()) bits += "comes from the list “" + r.list + "”"
    if (r.files) bits += "has a file"
    if (r.largerMb > 0) bits += "is bigger than " + r.largerMb + " MB"
    return (if (bits.isEmpty()) "All new mail" else "New mail that " + bits.joinToString(" and ")) + "."
}

/** Settings, Mail rules: the list in order, Edit, up and down arrows, Add a rule and Run on existing mail. */
@Composable
internal fun RulesPage(api: EnveliqApi, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    var rules by remember { mutableStateOf<List<Rule>?>(null) }
    var reload by remember { mutableStateOf(0) }
    var note by remember { mutableStateOf("") }
    var form by remember { mutableStateOf<Rule?>(null) }          // a rule being changed
    var adding by remember { mutableStateOf(false) }
    var plan by remember { mutableStateOf<RunPlan?>(null) }
    LaunchedEffect(reload) {
        try { rules = withContext(Dispatchers.IO) { api.rules() } }
        catch (e: Exception) { note = "Could not load your rules. Check your connection and try again." }
    }
    if (adding || form != null) {
        RuleForm(api, form, onClose = { adding = false; form = null }, onSaved = { adding = false; form = null; reload++ })
        return
    }
    BackHandler(onBack = onBack)
    Column(Modifier.fillMaxSize()) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = onBack) { Text("‹ Back", color = Blue, fontSize = 16.sp) }
            Text("Mail rules", color = Ink, fontSize = 20.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(start = 4.dp))
        }
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 4.dp)) {
            val list = rules
            if (list == null && note.isEmpty()) Text("Loading...", color = Muted, fontSize = 13.sp)
            if (list != null) {
                Text("Rules are tried from the top. The first one that fits and does something is used.", color = Muted, fontSize = 13.sp, lineHeight = 18.sp, modifier = Modifier.padding(horizontal = 8.dp, vertical = 6.dp))
                if (list.isEmpty()) Text("No rules yet. Add one, or open an email and use its menu.", color = Muted, fontSize = 14.sp, modifier = Modifier.padding(8.dp))
                else Surface(color = Panel, shape = RoundedCornerShape(18.dp), modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
                    Column {
                        list.forEachIndexed { i, r ->
                            if (i > 0) HorizontalDivider(color = Line, modifier = Modifier.padding(start = 16.dp))
                            Column(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp)) {
                                Text(doing(r), color = Ink, fontSize = 16.sp)
                                Text(sentence(r), color = Muted, fontSize = 13.sp, lineHeight = 18.sp)
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    if (r.action != "moved" && r.action != "tag") TextButton(onClick = { form = r }) { Text("Edit", color = Blue) }
                                    if (i > 0) TextButton(onClick = {
                                        scope.launch { try { withContext(Dispatchers.IO) { api.moveRule(r.id, true) }; note = "" } catch (e: Exception) { note = "Could not move that rule." }; reload++ }
                                    }) { Text("↑", color = Blue) }
                                    if (i < list.size - 1) TextButton(onClick = {
                                        scope.launch { try { withContext(Dispatchers.IO) { api.moveRule(r.id, false) }; note = "" } catch (e: Exception) { note = "Could not move that rule." }; reload++ }
                                    }) { Text("↓", color = Blue) }
                                    Box(Modifier.weight(1f))
                                    TextButton(onClick = {
                                        scope.launch { try { withContext(Dispatchers.IO) { api.deleteRule(r.id) }; note = "" } catch (e: Exception) { note = "Could not remove that rule." }; reload++ }
                                    }) { Text("Remove", color = Red) }
                                }
                            }
                        }
                    }
                }
                Surface(color = Panel, shape = RoundedCornerShape(18.dp), modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
                    Column {
                        TextButton(onClick = { adding = true }, modifier = Modifier.fillMaxWidth()) { Text("Add a rule", color = Blue, fontSize = 16.sp) }
                        HorizontalDivider(color = Line)
                        TextButton(onClick = {
                            scope.launch {
                                try { plan = withContext(Dispatchers.IO) { api.rulesPlan() }; note = "" }
                                catch (e: Exception) { note = (e as? ApiException)?.message ?: "Could not count that. Please try again." }
                            }
                        }, modifier = Modifier.fillMaxWidth()) { Text("Run on existing mail", color = Blue, fontSize = 16.sp) }
                    }
                }
                Text("Rules only touch new mail unless you press Run on existing mail. No rule can delete email.", color = Muted, fontSize = 13.sp, lineHeight = 18.sp, modifier = Modifier.padding(horizontal = 8.dp, vertical = 6.dp))
            }
            if (note.isNotEmpty()) Text(note, color = Amber, fontSize = 13.sp, modifier = Modifier.padding(8.dp))
        }
    }
    val p = plan
    if (p != null) {
        if (p.total == 0) AlertDialog(
            onDismissRequest = { plan = null },
            title = { Text("Nothing to tidy") },
            text = { Text("None of the email in your inbox fits a rule that does something.") },
            confirmButton = { TextButton(onClick = { plan = null }) { Text("OK", color = Blue) } },
        ) else AlertDialog(
            onDismissRequest = { plan = null },
            title = { Text("Run your rules on your inbox?") },
            text = {
                Text(
                    p.total.toString() + " email" + (if (p.total == 1) "" else "s") + " in your inbox fit a rule: " +
                        p.counts.entries.joinToString(", ") { it.value.toString() + " to " + (doNames.firstOrNull { n -> n.first == it.key }?.second ?: it.key).lowercase() } + "." +
                        (if (p.total > p.limit) " Only the first " + p.limit + " are done each time." else "") + " Nothing is deleted.",
                )
            },
            confirmButton = {
                TextButton(onClick = {
                    plan = null
                    scope.launch {
                        try { val n = withContext(Dispatchers.IO) { api.runRules() }; note = "Done. " + n + " email" + (if (n == 1) "" else "s") + " tidied." }
                        catch (e: Exception) { note = (e as? ApiException)?.message ?: "That did not work. Please try again." }
                    }
                }) { Text("Tidy " + minOf(p.total, p.limit) + " email" + (if (minOf(p.total, p.limit) == 1) "" else "s"), color = Blue) }
            },
            dismissButton = { TextButton(onClick = { plan = null }) { Text("Not now", color = Muted) } },
        )
    }
}

/** Full-screen form: Close and the title are fixed at the top, Check and Save are fixed at the bottom; only the middle scrolls. */
@Composable
private fun RuleForm(api: EnveliqApi, editing: Rule?, onClose: () -> Unit, onSaved: () -> Unit) {
    val scope = rememberCoroutineScope()
    BackHandler(onBack = onClose)
    var sender by remember { mutableStateOf(editing?.sender ?: "") }
    var subject by remember { mutableStateOf(editing?.subject ?: "") }
    var notSubject by remember { mutableStateOf(editing?.notSubject ?: "") }
    var to by remember { mutableStateOf(editing?.to ?: "") }
    var list by remember { mutableStateOf(editing?.list ?: "") }
    var files by remember { mutableStateOf(editing?.files ?: false) }
    var size by remember { mutableStateOf(if ((editing?.largerMb ?: 0) > 0) editing!!.largerMb.toString() else "") }
    var action by remember { mutableStateOf(editing?.action ?: "archived") }
    var hours by remember { mutableStateOf(editing?.hours?.takeIf { it > 0 } ?: 24) }
    var result by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    fun spec() = RuleSpec(sender.trim(), subject.trim(), notSubject.trim(), to.trim(), list.trim(), files, size.toIntOrNull() ?: 0, action, hours)

    Column(Modifier.fillMaxSize()) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(if (editing == null) "Add a rule" else "Change this rule", color = Ink, fontSize = 20.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f).padding(start = 8.dp))
            TextButton(onClick = onClose) { Text("Close", color = Blue, fontSize = 16.sp) }
        }
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 4.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("When new mail…", color = Muted, fontSize = 13.sp)
            OutlinedTextField(sender, { sender = it.take(320) }, label = { Text("From") }, placeholder = { Text("name@example.com or @example.com") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(subject, { subject = it.take(80) }, label = { Text("Subject has") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(notSubject, { notSubject = it.take(80) }, label = { Text("Subject does not have") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(to, { to = it.take(200) }, label = { Text("Sent to (To or Cc)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(list, { list = it.take(200) }, label = { Text("Mailing list") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("Has a file", color = Ink, fontSize = 16.sp)
                    Text("A guess from the email’s headers", color = Muted, fontSize = 13.sp)
                }
                Switch(checked = files, onCheckedChange = { files = it })
            }
            OutlinedTextField(size, { size = it.filter(Char::isDigit).take(4) }, label = { Text("Bigger than (MB)") }, singleLine = true, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), modifier = Modifier.fillMaxWidth())
            Text("Then…", color = Muted, fontSize = 13.sp, modifier = Modifier.padding(top = 6.dp))
            doNames.filter { it.first != "notasks" || editing?.action == "notasks" }.forEach { (key, label) ->
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    androidx.compose.material3.RadioButton(selected = action == key, onClick = { action = key })
                    Text(label, color = Ink, fontSize = 16.sp, modifier = Modifier.padding(start = 6.dp))
                }
            }
            if (action == "snoozed") {
                Text("Snooze for", color = Muted, fontSize = 13.sp)
                Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    snoozeChoices.forEach { (h, t) ->
                        Surface(onClick = { hours = h }, shape = RoundedCornerShape(20.dp), color = if (hours == h) androidx.compose.ui.graphics.Color(0xFF173056) else PanelHigh) {
                            Text(t, color = if (hours == h) androidx.compose.ui.graphics.Color(0xFF8DB8FF) else Ink, fontSize = 14.sp, modifier = Modifier.padding(horizontal = 14.dp, vertical = 8.dp), maxLines = 1)
                        }
                    }
                }
            }
            if (result.isNotEmpty()) Text(result, color = Amber, fontSize = 14.sp, lineHeight = 20.sp)
            Box(Modifier.size(8.dp))
        }
        HorizontalDivider(color = Line)
        Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            androidx.compose.material3.OutlinedButton(enabled = !busy, onClick = {
                busy = true
                scope.launch {
                    result = try { val (m, c) = withContext(Dispatchers.IO) { api.previewRule(spec()) }; "This would have matched $m of your $c recent emails. Nothing was changed." }
                    catch (e: Exception) { (e as? ApiException)?.message ?: "Could not check that. Please try again." }
                    busy = false
                }
            }, modifier = Modifier.weight(1f)) { Text("Check") }
            androidx.compose.material3.Button(enabled = !busy, onClick = {
                busy = true
                scope.launch {
                    try { withContext(Dispatchers.IO) { api.saveRule(editing?.id ?: "", spec()) }; onSaved() }
                    catch (e: Exception) { result = (e as? ApiException)?.message ?: "Could not save that. Please try again."; busy = false }
                }
            }, modifier = Modifier.weight(1f)) { Text("Save") }
        }
    }
}
