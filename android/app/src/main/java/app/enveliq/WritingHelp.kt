package app.enveliq

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedButton
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
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

// Writing help on the phone, the same as the website: a suggestion box under the message (Accept, Put my version back, Copy, Try again,
// Close), a check before sending words the AI wrote, Quick AI Send, and the Writing help and Writing style settings.
// The AI only ever suggests. Nothing it writes is sent until the person accepts it and presses Send.

private val bracketGap = Regex("\\[[^\\]\\n]{1,80}\\]")
internal fun hasGap(text: String) = bracketGap.containsMatchIn(text)

/** What the composer needs to know about the person's Writing help settings. Null while loading, or when the feature is off for them. */
@Composable
internal fun rememberWriteHelp(api: EnveliqApi, reload: Int = 0): WriteHelpInfo? {
    var info by remember { mutableStateOf<WriteHelpInfo?>(null) }
    LaunchedEffect(reload) { info = try { withContext(Dispatchers.IO) { api.writeHelp() }.takeIf { it.available } } catch (e: Exception) { null } }
    return info
}

/** The button and the "Suggested by AI" box under the message. [text] is the person's own box; [accept] puts wording into it. */
@Composable
internal fun WriteHelpBox(
    api: EnveliqApi, info: WriteHelpInfo, mail: Mail?, subject: String, text: String, isNew: Boolean,
    state: WriteHelpState, accept: (String) -> Unit,
) {
    val scope = rememberCoroutineScope()
    val clipboard = LocalClipboardManager.current
    fun ask() {
        state.busy = true; state.error = ""
        val draft = text
        scope.launch {
            try {
                val r = withContext(Dispatchers.IO) { if (isNew || mail == null) api.writeForNew(subject, draft) else api.writeForReply(mail, draft) }
                state.suggestion = r; state.used = true
            } catch (e: ApiException) {
                state.error = e.message ?: "Writing help did not work."
            } catch (e: Exception) {
                state.error = "Writing help did not work. Check your connection and try again."
            } finally { state.busy = false }
        }
    }
    Column(Modifier.fillMaxWidth().padding(top = 10.dp)) {
        if (!info.on) {
            Text("Want help writing? You can turn on Writing help in Settings, under Writing help.", color = Muted, fontSize = 13.sp)
            return@Column
        }
        val label = if (state.busy) "Thinking…" else if (text.isBlank()) (if (isNew) "Help me write" else "Write a reply for me") else (if (isNew) "Check my email" else "Check my reply")
        OutlinedButton(onClick = { ask() }, enabled = !state.busy && info.aiReady, shape = RoundedCornerShape(14.dp), border = BorderStroke(1.dp, Line)) { Text(label, color = Blue) }
        Text(
            if (info.aiReady) "The AI reads what you wrote (and the email you are answering) and suggests text. You choose what to use."
            else "No AI model is set up yet, so writing help cannot work. An administrator can add one.",
            color = Muted, fontSize = 13.sp, modifier = Modifier.padding(top = 4.dp),
        )
        if (state.error.isNotEmpty()) Text(state.error, color = Red, fontSize = 14.sp, modifier = Modifier.padding(top = 6.dp))
        val s = state.suggestion
        if (s != null) {
            Card(Modifier.padding(top = 10.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("Suggested by AI", color = Blue, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
                    Text("  Nothing here is sent.", color = Muted, fontSize = 13.sp)
                }
                SelectionContainer { Text(s.text, color = Ink, fontSize = 16.sp, lineHeight = 22.sp, modifier = Modifier.padding(top = 8.dp)) }
                s.notes.forEach { Text("• $it", color = Muted, fontSize = 13.sp, modifier = Modifier.padding(top = 4.dp)) }
                if (hasGap(s.text)) Text("Check the [brackets]: they are gaps for you to fill in before sending.", color = Amber, fontSize = 13.sp, modifier = Modifier.padding(top = 6.dp))
                Row(Modifier.padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    if (state.backup == null) TextButton(onClick = { state.backup = text; accept(s.text) }) { Text(if (text.isBlank()) "Accept" else "Accept (replaces my text)", color = Blue) }
                    else TextButton(onClick = { accept(state.backup ?: ""); state.backup = null }) { Text("Put my version back", color = Blue) }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    TextButton(onClick = { clipboard.setText(AnnotatedString(s.text)) }) { Text("Copy", color = Muted) }
                    TextButton(onClick = { state.backup = null; ask() }, enabled = !state.busy) { Text("Try again", color = Muted) }
                    TextButton(onClick = { state.suggestion = null; state.backup = null }) { Text("Close", color = Muted) }
                }
            }
        }
    }
}

/** Held by the composer: the suggestion, the person's own text to go back to, and whether writing help has been used on this message. */
internal class WriteHelpState {
    var suggestion by mutableStateOf<WriteSuggestion?>(null)
    var backup by mutableStateOf<String?>(null)
    var busy by mutableStateOf(false)
    var error by mutableStateOf("")
    var used by mutableStateOf(false)
}

/** Settings, Writing help: the switch, Quick AI Send, the instructions, and the writing style. */
@Composable
internal fun WritingSettingsPage(api: EnveliqApi, onBack: () -> Unit) {
    SubPage("Writing help", onBack = onBack) {
        Column(Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            WriteHelpSettings(api)
            WritingStyleSettings(api)
        }
    }
}

@Composable
private fun SwitchLine(title: String, note: String, checked: Boolean, enabled: Boolean = true, onChange: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f).padding(end = 12.dp)) {
            Text(title, color = Ink, fontSize = 16.sp)
            Text(note, color = Muted, fontSize = 13.sp, lineHeight = 18.sp)
        }
        Switch(checked = checked, onCheckedChange = onChange, enabled = enabled)
    }
}

@Composable
private fun WriteHelpSettings(api: EnveliqApi) {
    val scope = rememberCoroutineScope()
    var info by remember { mutableStateOf<WriteHelpInfo?>(null) }
    var err by remember { mutableStateOf("") }
    var text by remember { mutableStateOf("") }
    var saved by remember { mutableStateOf("") }
    LaunchedEffect(Unit) {
        try { info = withContext(Dispatchers.IO) { api.writeHelp() }; text = info!!.instructions }
        catch (e: ApiException) { err = e.message ?: "Could not load Writing help." }
        catch (e: Exception) { err = "Could not load Writing help. Check your connection." }
    }
    fun save(on: Boolean, quick: Boolean, instructions: String?) {
        err = ""; saved = ""
        scope.launch {
            try { info = withContext(Dispatchers.IO) { api.saveWriteHelp(on, quick, instructions) }; text = info!!.instructions; saved = "Saved." }
            catch (e: ApiException) { err = e.message ?: "That did not save." }
            catch (e: Exception) { err = "That did not save. Check your connection." }
        }
    }
    val i = info
    Card {
        Text("Writing help", color = Ink, fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
        if (i == null) {
            Text(err.ifEmpty { "Loading…" }, color = if (err.isEmpty()) Muted else Red, fontSize = 14.sp, modifier = Modifier.padding(top = 6.dp))
            return@Card
        }
        Text("The AI can suggest a reply, a new email, or better wording. It only suggests: nothing is sent until you accept it and press Send. AI wording is always labelled.", color = Muted, fontSize = 13.sp, lineHeight = 18.sp, modifier = Modifier.padding(top = 4.dp, bottom = 8.dp))
        SwitchLine("Turn on Writing help", "Adds a button to replies and new emails.", i.on) { save(it, i.quick, null) }
        SwitchLine("Quick AI Send", "Adds a button beside Send that fixes spelling, grammar and punctuation, then sends at once. It never changes what you mean. Needs Writing help on.", i.quick, enabled = i.on) { save(i.on, it, null) }
        Text("Instructions for the AI", color = Ink, fontSize = 15.sp, modifier = Modifier.padding(top = 10.dp, bottom = 6.dp))
        SpellField(text, { text = it.take(i.max) }, singleLine = false, minLines = 5, modifier = Modifier.fillMaxWidth())
        Row(Modifier.padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = { save(i.on, i.quick, text) }, enabled = text != i.instructions, shape = RoundedCornerShape(12.dp)) { Text("Save") }
            if (!i.isDefault) OutlinedButton(onClick = { save(i.on, i.quick, i.default) }, shape = RoundedCornerShape(12.dp), border = BorderStroke(1.dp, Line)) { Text("Use the standard instructions", color = Ink) }
        }
        if (saved.isNotEmpty()) Text(saved, color = Green, fontSize = 14.sp, modifier = Modifier.padding(top = 6.dp))
        if (err.isNotEmpty()) Text(err, color = Red, fontSize = 14.sp, modifier = Modifier.padding(top = 6.dp))
    }
}

@Composable
private fun WritingStyleSettings(api: EnveliqApi) {
    val scope = rememberCoroutineScope()
    var info by remember { mutableStateOf<StyleInfo?>(null) }
    var err by remember { mutableStateOf("") }
    var text by remember { mutableStateOf("") }
    var edited by remember { mutableStateOf(false) }
    fun take(s: StyleInfo) { info = s; if (!edited) text = s.guide }
    LaunchedEffect(Unit) {
        try { take(withContext(Dispatchers.IO) { api.writingStyle() }) }
        catch (e: ApiException) { err = e.message ?: "" }
        catch (e: Exception) { err = "Could not load your writing style." }
        // while the guide is being made, look again every few seconds
        while (info?.busy == true) {
            delay(3000)
            try { take(withContext(Dispatchers.IO) { api.writingStyle() }) } catch (e: Exception) { break }
        }
    }
    fun run(block: () -> StyleInfo) {
        err = ""
        scope.launch {
            try { take(withContext(Dispatchers.IO) { block() }) }
            catch (e: ApiException) { err = e.message ?: "That did not work." }
            catch (e: Exception) { err = "That did not work. Check your connection." }
            while (info?.busy == true) {
                delay(3000)
                try { take(withContext(Dispatchers.IO) { api.writingStyle() }) } catch (e: Exception) { break }
            }
        }
    }
    val i = info
    Card {
        Text("Your writing style", color = Ink, fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
        if (i == null || !i.available) {
            if (err.isNotEmpty()) Text(err, color = Red, fontSize = 14.sp, modifier = Modifier.padding(top = 6.dp))
            return@Card
        }
        Text("Enveliq can learn how you write from your 20 newest sent emails, using only your own words (never quoted replies, signatures, forwards or files). The guide below is added to Writing help and Quick AI Send so they sound like you.", color = Muted, fontSize = 13.sp, lineHeight = 18.sp, modifier = Modifier.padding(top = 4.dp, bottom = 8.dp))
        SwitchLine("Learn my writing style", "Off until you turn it on.", i.on) { v -> run { api.saveWritingStyle(on = v) } }
        if (i.on) {
            SwitchLine("Update it every week", if (i.mode == "auto") "A new guide is made each week from your latest 20 sent emails." else "Off, because you edited the guide. Your words stay as they are until you turn this on.", i.mode == "auto") { v -> run { api.saveWritingStyle(mode = if (v) "auto" else "manual") } }
            Text(if (i.busy) "Learning from your sent emails…" else if (i.guide.isBlank()) "No guide yet." else "Your guide (you can edit it):", color = Muted, fontSize = 14.sp, modifier = Modifier.padding(top = 8.dp, bottom = 6.dp))
            if (i.guide.isNotBlank() || edited) {
                SpellField(text, { text = it.take(i.max); edited = true }, singleLine = false, minLines = 6, modifier = Modifier.fillMaxWidth())
                Row(Modifier.padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { edited = false; run { api.saveWritingStyle(guide = text) } }, enabled = text != i.guide, shape = RoundedCornerShape(12.dp)) { Text("Save my edits") }
                }
            }
            OutlinedButton(onClick = { edited = false; run { api.rebuildWritingStyle() } }, enabled = !i.busy && i.aiReady, shape = RoundedCornerShape(12.dp), border = BorderStroke(1.dp, Line), modifier = Modifier.padding(top = 8.dp)) { Text("Make it again now", color = Blue) }
            if (i.samples > 0) Text("Learned from ${i.samples} sent emails. Only your own words were looked at.", color = Muted, fontSize = 13.sp, modifier = Modifier.padding(top = 6.dp))
        }
        val shownErr = err.ifEmpty { i.error }
        if (shownErr.isNotEmpty()) Text(shownErr, color = Red, fontSize = 14.sp, modifier = Modifier.padding(top = 6.dp))
    }
}
