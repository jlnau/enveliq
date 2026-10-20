package app.enveliq

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
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
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle
import java.time.format.TextStyle
import java.util.Locale

/** When a task is due, in the same words as the website: Today, Tomorrow, a weekday, a date, or "Waiting since". */
internal fun taskWhen(t: MyTask): String {
    val due = try { LocalDate.parse(t.due) } catch (_: Exception) { return t.due }
    val weekday = due.dayOfWeek.getDisplayName(TextStyle.SHORT, Locale.getDefault())
    val dayMonth = due.dayOfMonth.toString() + " " + due.month.getDisplayName(TextStyle.SHORT, Locale.getDefault())
    return when {
        t.days < 0 -> if (t.days > -7) "Waiting since $weekday" else "Waiting since $dayMonth"
        t.days == 0 -> if (t.remindAt > 0)
            "Today · " + DateTimeFormatter.ofLocalizedTime(FormatStyle.SHORT).format(Instant.ofEpochSecond(t.remindAt).atZone(ZoneId.systemDefault()))
        else "Today"
        t.days == 1 -> "Tomorrow"
        t.days < 7 -> weekday
        else -> "$weekday $dayMonth"
    }
}

/**
 * The tasks for the open email, like the website shows them: a label, the title, when it is due, and a three-dot menu
 * with Move and Remove. If the list of tasks cannot be loaded, the task the AI found is still shown, without the menu.
 */
@Composable
internal fun EmailTasks(mail: Mail, api: EnveliqApi) {
    var reload by remember(mail.id) { mutableStateOf(0) }
    var tasks by remember(mail.id) { mutableStateOf<List<MyTask>?>(null) }
    var moving by remember(mail.id) { mutableStateOf<MyTask?>(null) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    LaunchedEffect(mail.id, reload) {
        tasks = try {
            withContext(Dispatchers.IO) { api.myTasks() }.filter { it.accountId == mail.accountId && it.messageId == mail.id }
        } catch (_: Exception) { tasks }
    }

    fun act(t: MyTask, action: String, to: String? = null, on: String? = null) {
        scope.launch {
            try {
                withContext(Dispatchers.IO) { api.taskAct(t.id, action, to, on) }
            } catch (e: ApiException) {
                android.widget.Toast.makeText(context, e.message ?: "That did not work.", android.widget.Toast.LENGTH_LONG).show()
            } catch (e: Exception) {
                android.widget.Toast.makeText(context, "That did not work. Check your connection.", android.widget.Toast.LENGTH_LONG).show()
            }
            reload++
        }
    }

    val loaded = tasks
    if (loaded == null) {
        // Not loaded yet (or it failed): show what the AI found, with no menu.
        if (mail.taskTitle != null) TaskBox("Task", mail.taskTitle, "", mail.taskDue?.takeIf { it.isNotBlank() }?.let { "Due: $it" } ?: "", null)
        return
    }
    for (t in loaded) {
        val open = t.state == "open"
        TaskBox(
            label = if (!open) "Task done" else if (t.manual) "Your task" else "Task added",
            title = t.title, detail = t.detail, whenText = if (open) taskWhen(t) else "", overdue = open && t.days < 0,
            menu = { close ->
                if (open) {
                    DropdownMenuItem(text = { Text("Move", color = Ink) }, onClick = { close(); moving = t })
                    DropdownMenuItem(text = { Text("Remove", color = Ink) }, onClick = { close(); act(t, "remove") })
                } else {
                    DropdownMenuItem(text = { Text("Put back", color = Ink) }, onClick = { close(); act(t, "reopen") })
                }
            },
        )
    }

    moving?.let { t ->
        AlertDialog(
            onDismissRequest = { moving = null },
            containerColor = Panel,
            title = { Text("Move this task to", color = Ink) },
            text = {
                Column {
                    for ((id, label) in listOf("later_today" to "Later today", "tomorrow" to "Tomorrow morning", "weekend" to "This weekend", "next_week" to "Next week")) {
                        TextButton(onClick = { moving = null; act(t, "move", id) }, modifier = Modifier.fillMaxWidth()) { Text(label, color = Ink, fontSize = 17.sp) }
                    }
                    TextButton(onClick = {
                        moving = null
                        val now = java.util.Calendar.getInstance()
                        val picker = android.app.DatePickerDialog(context, { _, y, m, d ->
                            act(t, "move", "date", "%04d-%02d-%02d".format(y, m + 1, d))
                        }, now.get(java.util.Calendar.YEAR), now.get(java.util.Calendar.MONTH), now.get(java.util.Calendar.DAY_OF_MONTH))
                        picker.datePicker.minDate = System.currentTimeMillis() - 1000
                        picker.show()
                    }, modifier = Modifier.fillMaxWidth()) { Text("Pick a day…", color = Ink, fontSize = 17.sp) }
                }
            },
            confirmButton = {},
            dismissButton = { TextButton(onClick = { moving = null }) { Text("Cancel", color = Muted) } },
        )
    }
}

@Composable
private fun TaskBox(label: String, title: String, detail: String, whenText: String, menu: (@Composable (close: () -> Unit) -> Unit)?, overdue: Boolean = false) {
    var open by remember { mutableStateOf(false) }
    Surface(
        color = Panel, shape = RoundedCornerShape(16.dp), border = BorderStroke(1.dp, Line),
        modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
    ) {
        Row(Modifier.padding(start = 16.dp, top = 12.dp, bottom = 14.dp, end = if (menu != null) 4.dp else 16.dp), verticalAlignment = Alignment.Top) {
            Column(Modifier.weight(1f).padding(top = 4.dp)) {
                Text(label, color = Amber, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                Text(title, color = Ink, fontSize = 17.sp, modifier = Modifier.padding(top = 4.dp))
                if (whenText.isNotBlank()) Text(
                    whenText, color = if (overdue) Red else Amber, fontSize = 14.sp, fontWeight = FontWeight.Medium,
                    modifier = Modifier.padding(top = 4.dp),
                )
                if (detail.isNotBlank()) Text(detail, color = Muted, fontSize = 14.sp, modifier = Modifier.padding(top = 4.dp))
            }
            if (menu != null) Box {
                IconButton(onClick = { open = true }) { Icon(Icons.Filled.MoreVert, contentDescription = "Task options", tint = Muted) }
                DropdownMenu(expanded = open, onDismissRequest = { open = false }, containerColor = Panel) { menu { open = false } }
            }
        }
    }
}
