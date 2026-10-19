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
