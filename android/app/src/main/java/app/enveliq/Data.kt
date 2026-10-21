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
    /** The email has files (known even before the AI has read them). */
    val hasFiles: Boolean = false,
    /** Who a reply goes to, and the other people on the email (for Reply all). */
    val replyTo: String = "",
    val replyCc: List<String> = emptyList(),
    val replyAlsoTo: List<String> = emptyList(),
    /** A quiet entry from "Include read mail": no summary until you ask for one. */
    val quiet: Boolean = false,
    val ungenerated: Boolean = false,
    /** Held for the daily summary: not in the inbox, listed under Held for summary. */
    val held: Boolean = false,
)

/** A file that came with an email. [summary] is written by the AI and is labelled that way where it is shown. */
/** A file that came with an email: its name, size, the AI's summary (when it was read) and, when it was not, why. */
data class Attachment(
    val index: Int, val name: String, val size: Long, val summary: String,
    val mime: String = "", val state: String = "", val note: String = "", val reason: String = "",
    val parts: List<Pair<String, String>> = emptyList(), val pages: Int = 0,
)

/** Who is signed in: for the round picture (or initials) at the top of the inbox. */
data class Me(val id: String, val name: String, val initials: String, val avatarVersion: String)

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

data class MyTask(val id: String, val accountId: String, val messageId: String, val title: String, val sender: String, val priority: String, val due: String, val days: Int, val state: String, val manual: Boolean, val detail: String = "", val remindAt: Long = 0L)
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

/** A conversation the person muted: later replies go to Archive without an alert. */
data class MutedConversation(val id: String, val subject: String, val count: Int)

/** Where the newest Android app is published. */
const val APP_DOWNLOAD_PAGE = "https://github.com/jlnau/enveliq/releases/latest"

/** One email found by "Find any email". [token] opens it; the email itself stays at the mailbox. */
data class FoundRow(val token: String, val from: String, val subject: String, val date: String, val mailbox: String, val folder: String)

/** How a search is going: [done] when every mailbox has answered. */
data class FindProgress(val id: String, val done: Boolean, val listed: Int, val notes: List<String>)

/** A mailing list in Clean up. [unsubUrl] or [unsubMailto] is null when the sender has none, or looks like a fake. [last] is seconds since 1970. */
data class Sender(
    val id: String, val name: String, val address: String, val count: Int, val opened: Int, val last: Long, val mailbox: String,
    val flagged: Boolean, val unsubUrl: String?, val unsubMailto: String?, val unsubSubject: String,
)

/** What Clean up knows right now. [undo] is the one-time Undo token after an archive (it lasts about ten minutes), [undoName] says whose email it was. */
data class CleanUp(val senders: List<Sender>, val kept: Int, val days: Int, val now: Long, val mailboxes: Int, val problems: List<String>, val undo: String = "", val undoCount: Int = 0, val undoName: String = "", val toast: String = "")

/** Writing help settings from the server (Settings, Writing help). */
data class WriteHelpInfo(val available: Boolean, val aiReady: Boolean, val on: Boolean, val quick: Boolean, val instructions: String, val isDefault: Boolean, val default: String, val max: Int)

/** Text the AI suggested. It is only ever shown in its own box; nothing is sent until the person accepts it and sends. */
data class WriteSuggestion(val text: String, val notes: List<String>, val gaps: Boolean)

/** The corrected subject and text from Quick AI Send. */
data class QuickFixed(val subject: String, val text: String, val changed: Boolean)

/** The personal writing-style guide (Settings, Writing style). */
data class StyleInfo(val available: Boolean, val aiReady: Boolean, val on: Boolean, val guide: String, val mode: String, val generatedAt: Double, val samples: Int, val error: String, val max: Int, val busy: Boolean)

/** One email held for the summary. The one-line summary was written by the AI. */
data class DigestItem(val accountId: String, val messageId: String, val sender: String, val subject: String, val summary: String, val category: String, val heldAt: Double)

/** The daily summary: the emails held for it (they are not in the inbox). [enabled] is false when the person has not switched it on. */
data class SummaryInfo(val enabled: Boolean, val count: Int, val unread: Int, val items: List<DigestItem>)
