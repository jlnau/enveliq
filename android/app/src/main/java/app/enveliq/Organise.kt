package app.enveliq

import android.content.Intent
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.FilterChip
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
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.net.URI

/** The tags on an email, with a tap to put one on or take it off. Hidden when the mail service does not keep tags. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
internal fun TagsSection(mail: Mail, api: EnveliqApi) {
    var tags by remember(mail.id) { mutableStateOf(mail.tags) }
    var info by remember(mail.id) { mutableStateOf<TagInfo?>(null) }
    var making by remember(mail.id) { mutableStateOf(false) }
    var newName by remember(mail.id) { mutableStateOf("") }
    var problem by remember(mail.id) { mutableStateOf("") }
    val scope = rememberCoroutineScope()

    LaunchedEffect(mail.id) {
        info = try { withContext(Dispatchers.IO) { api.tagInfo(mail.accountId) } } catch (e: Exception) { null }
    }
    val current = info
    if (current == null && tags.isEmpty()) return

    fun has(name: String) = tags.any { it.equals(name, ignoreCase = true) }

    fun change(name: String, on: Boolean, create: Boolean = false) {
        problem = ""
        scope.launch {
            try {
                if (create) {
                    try { withContext(Dispatchers.IO) { api.createTag(mail.accountId, name) } } catch (e: ApiException) { if (e.code == 401) throw e }
                }
                tags = withContext(Dispatchers.IO) { api.setTag(mail, name, on) }
                if (create) {
                    making = false
                    newName = ""
                    info = withContext(Dispatchers.IO) { api.tagInfo(mail.accountId) } ?: info
                }
            } catch (e: ApiException) {
                problem = e.message ?: "That tag did not change. Please try again."
            } catch (e: Exception) {
                problem = "That tag did not change. Please try again."
            }
        }
    }

    val all = ((current?.names ?: emptyList()) + tags).distinctBy { it.lowercase() }
    Column(Modifier.fillMaxWidth().padding(top = 18.dp)) {
        Text("Tags", color = Muted, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
        if (all.isEmpty()) Text("No tags yet.", color = Muted, fontSize = 14.sp, modifier = Modifier.padding(top = 4.dp))
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 6.dp)) {
            all.forEach { name ->
                FilterChip(
                    selected = has(name), enabled = current != null,
                    onClick = { change(name, !has(name)) },
                    label = { Text(name) },
                )
            }
            if (current?.canCreate == true) {
                FilterChip(selected = false, onClick = { making = !making }, label = { Text(if (making) "Cancel" else "+ New tag") })
            }
        }
        if (making) {
            Row(Modifier.fillMaxWidth().padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = newName, onValueChange = { newName = it }, singleLine = true,
                    placeholder = { Text("Name for the tag") }, modifier = Modifier.weight(1f),
                )
                TextButton(onClick = { if (newName.isNotBlank()) change(newName.trim(), true, create = true) }) { Text("Add", color = Blue) }
            }
        }
        if (problem.isNotEmpty()) Text(problem, color = Red, fontSize = 14.sp, modifier = Modifier.padding(top = 6.dp))
    }
}

private fun sizeText(bytes: Long): String = when {
    bytes <= 0L -> ""
    bytes < 1024L * 1024L -> ((bytes + 1023L) / 1024L).toString() + " KB"
    else -> String.format("%.1f MB", bytes / 1048576.0)
}

/** The files that came with an email. The AI's note on each is labelled. Save puts the file where the person chooses; the app keeps nothing. */
@Composable
internal fun AttachmentsSection(mail: Mail, api: EnveliqApi) {
    if (mail.attachments.isEmpty()) return
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var pending by remember(mail.id) { mutableStateOf<Attachment?>(null) }
    var status by remember(mail.id) { mutableStateOf("") }
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/octet-stream")) { uri: Uri? ->
        val file = pending
        pending = null
        if (uri != null && file != null) {
            status = "Saving " + file.name + "…"
            scope.launch {
                try {
                    val bytes = withContext(Dispatchers.IO) { api.download(mail, file.index) }
                    withContext(Dispatchers.IO) { context.contentResolver.openOutputStream(uri)?.use { it.write(bytes) } }
                    status = "Saved " + file.name + "."
                } catch (e: ApiException) {
                    status = e.message ?: "Could not save the file."
                } catch (e: Exception) {
                    status = "Could not save the file."
                }
            }
        }
    }
    Column(Modifier.fillMaxWidth().padding(top = 18.dp)) {
        Text("Files with this email", color = Muted, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
        mail.attachments.forEach { file ->
            Surface(
                color = Panel, shape = RoundedCornerShape(14.dp), border = BorderStroke(1.dp, Line),
                modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
            ) {
                Column(Modifier.padding(14.dp)) {
                    Text(file.name, color = Ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                    val size = sizeText(file.size)
                    if (size.isNotEmpty()) Text(size, color = Muted, fontSize = 13.sp)
                    if (file.summary.isNotBlank()) {
                        Text("✦ " + file.summary, color = Ink, fontSize = 14.sp, lineHeight = 21.sp, modifier = Modifier.padding(top = 6.dp))
                        Text("Written by the AI. It can be wrong.", color = Muted, fontSize = 12.sp, modifier = Modifier.padding(top = 4.dp))
                    }
                    OutlinedButton(
                        onClick = { pending = file; picker.launch(file.name) },
                        modifier = Modifier.padding(top = 8.dp), shape = RoundedCornerShape(12.dp), border = BorderStroke(1.dp, Line),
                    ) { Text("Save to my phone", color = Ink) }
                }
            }
        }
        if (status.isNotEmpty()) Text(status, color = Muted, fontSize = 14.sp, modifier = Modifier.padding(top = 6.dp))
    }
}

private val linkPattern = Regex("""https?://[^\s<>"')\]]+""")

private fun hostOf(link: String): String? = try { URI(link.trimEnd('.', ',', ';', ':', '!', '?')).host?.lowercase() } catch (e: Exception) { null }

private fun looksOdd(link: String, host: String): Boolean =
    link.startsWith("http://", ignoreCase = true) || host.startsWith("xn--") || host.split('.').all { p -> p.isNotEmpty() && p.all { it.isDigit() } }

/** The links in the email's text, each shown with where it really goes. Nothing opens until the person says so. */
@Composable
internal fun LinksSection(text: String) {
    val context = LocalContext.current
    val links = remember(text) {
        linkPattern.findAll(text).map { it.value.trimEnd('.', ',', ';', ':', '!', '?') }.distinct().filter { hostOf(it) != null }.take(12).toList()
    }
    var asking by remember(text) { mutableStateOf<String?>(null) }
    if (links.isEmpty()) return
    Column(Modifier.fillMaxWidth().padding(top = 18.dp)) {
        Text("Links in this email", color = Muted, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
        links.forEach { link ->
            val host = hostOf(link) ?: return@forEach
            TextButton(onClick = { asking = link }, modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.fillMaxWidth()) {
                    Text("Goes to " + host, color = Blue, fontSize = 16.sp)
                    Text(link, color = Muted, fontSize = 12.sp, maxLines = 1, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
                }
            }
        }
    }
    val target = asking
    if (target != null) {
        val host = hostOf(target) ?: ""
        AlertDialog(
            onDismissRequest = { asking = null },
            title = { Text("Open this link?") },
            text = {
                Column {
                    Text("It goes to " + host + ".")
                    if (looksOdd(target, host)) Text("This one looks unusual. Only open it if you are expecting it.", modifier = Modifier.padding(top = 8.dp))
                    Text("Check that the address is the one you expect before you carry on.", modifier = Modifier.padding(top = 8.dp))
                }
            },
            confirmButton = {
                TextButton(onClick = {
                    asking = null
                    try { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(target)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) } catch (e: Exception) { }
                }) { Text("Open", color = Blue) }
            },
            dismissButton = { TextButton(onClick = { asking = null }) { Text("Cancel", color = Blue) } },
        )
    }
}
