package app.enveliq

/** One email as the app shows it. The app keeps the summary only while the screen is open; nothing is written to the phone's storage. */
data class Mail(
    val id: String,
    val accountId: String,
    val sender: String,
    val address: String,
    val subject: String,
    val summary: String,
    val whenText: String,
    val needsAction: Boolean,
    val taskTitle: String? = null,
    val taskDue: String? = null,
    val received: Long = 0L,
)

enum class Outcome(val api: String, val done: String) {
    Reviewed("reviewed", "Marked reviewed"),
    Archived("archived", "Archived"),
    Binned("binned", "Moved to Bin"),
}

/** A mailbox the person can send from. */
data class Mailbox(val id: String, val label: String)

/** A person from the address list, for suggestions while typing. */
data class Contact(val name: String, val address: String)

/** A saved draft. [kind] is new, reply, reply_all or forward. For a reply or forward, [messageId] is the email being answered. */
data class Draft(
    val id: String,
    val kind: String,
    val accountId: String,
    val messageId: String,
    val to: List<String>,
    val cc: List<String>,
    val bcc: List<String>,
    val subject: String,
    val body: String,
)

/** What the server said after a send. When [queued], the email waits [secondsLeft] seconds (the "undo send" time) and can still be taken back. */
class Sent(val queued: Boolean, val outboxId: String, val secondsLeft: Int)
