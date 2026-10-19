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
    val tags: List<String> = emptyList(),
    val attachments: List<Attachment> = emptyList(),
    val mailbox: String = "",
    val state: String = "unread",
    /** Plain reasons the server gives for a warning about this email, empty when there is none. */
    val scamReasons: List<String> = emptyList(),
    /** Where "unsubscribe" goes: a web address, or a mailto address to write to. Null when the email has none. */
    val unsubUrl: String? = null,
    val unsubMailto: String? = null,
    val unsubSubject: String = "",
)

/** A file that came with an email. [summary] is written by the AI and is labelled that way where it is shown. */
data class Attachment(val index: Int, val name: String, val size: Long, val summary: String)

/** The tags the mail service keeps for a mailbox, and whether a new one can be made. */
data class TagInfo(val names: List<String>, val canCreate: Boolean)

enum class Outcome(val api: String, val done: String) {
    Reviewed("reviewed", "Marked reviewed"),
    Archived("archived", "Archived"),
    Binned("binned", "Moved to Bin"),
    Junked("junked", "Sent to Junk"),
}

/** A mailbox the person can send from. */
data class Mailbox(val id: String, val label: String)

/** An address a mailbox may send from: its own, or one of its aliases. [isDefault] marks the mailbox's own address. */
data class FromOption(val accountId: String, val address: String, val label: String, val isDefault: Boolean)

/** What the server says about an original email: its plain text, and whether a formatted (HTML) version exists. */
data class OriginalInfo(val text: String, val hasHtml: Boolean, val remoteImages: Int)

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
    val fromAddress: String = "",
)

/** What the server said after a send. When [queued], the email waits [secondsLeft] seconds (the "undo send" time) and can still be taken back. */
class Sent(val queued: Boolean, val outboxId: String, val secondsLeft: Int, val scheduledId: String = "", val scheduledText: String = "")

/** An email waiting for the time it was set to go. [state] is pending or failed (with [error] saying why). [at] is in seconds since 1970. */
data class Waiting(val id: String, val subject: String, val to: String, val people: Int, val at: Long, val state: String, val error: String)

/** One place the person is signed in. [signedIn] is in seconds since 1970. */
data class DeviceInfo(val id: String, val name: String, val signedIn: Long, val current: Boolean)

data class MyTask(val id: String, val accountId: String, val messageId: String, val title: String, val sender: String, val priority: String, val due: String, val days: Int, val state: String, val manual: Boolean)
data class BellNote(val id: String, val title: String, val message: String, val source: String, val at: Long, val unread: Boolean)
data class Order(val id: String, val shop: String, val items: String, val status: String, val expected: String, val delayed: Boolean, val delivered: Boolean, val needsConfirm: Boolean, val trackUrl: String)
data class Booking(val kind: String, val provider: String, val detail: String, val from: String, val to: String, val start: String, val startTime: String, val reference: String, val cancelled: Boolean)
data class Trip(val title: String, val start: String, val end: String, val state: String, val cancelled: Boolean, val bookings: List<Booking>)
data class FeedItem(val title: String, val text: String, val link: String, val at: Long, val isNew: Boolean)
data class Feed(val id: String, val title: String, val error: String, val newCount: Int, val items: List<FeedItem>)
data class Chat(val id: String, val title: String, val unread: Int, val last: String, val updated: Long, val muted: Boolean)
data class ChatMessage(val id: String, val name: String, val mine: Boolean, val at: Long, val text: String, val deleted: Boolean)

/** A list from a feature that an administrator or the person may have switched off. */
data class Section<T>(val enabled: Boolean, val items: List<T>)

/** A rule: email from [sender] (and, when set, with [subject] words) gets [action] ("archived", "reviewed" or "junked"). */
data class Rule(val id: String, val sender: String, val subject: String, val action: String)

/** Where the newest Android app is published. */
const val APP_DOWNLOAD_PAGE = "https://github.com/jlnau/enveliq/releases/latest"

/** One email found by "Find any email". [token] opens it; the email itself stays at the mailbox. */
data class FoundRow(val token: String, val from: String, val subject: String, val date: String, val mailbox: String, val folder: String)

/** How a search is going: [done] when every mailbox has answered. */
data class FindProgress(val id: String, val done: Boolean, val listed: Int, val notes: List<String>)
