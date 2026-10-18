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
    /** Only the demo carries its own original text; a real email's original is fetched from the server when asked for. */
    val demoBody: String? = null,
)

enum class Outcome(val api: String, val done: String) {
    Reviewed("reviewed", "Marked reviewed"),
    Archived("archived", "Archived"),
    Binned("binned", "Moved to Bin"),
}

/** Made-up mail for the demo. Every name and address here is invented (example.invalid). */
object Demo {
    val mails: List<Mail> = listOf(
        Mail(
            id = "d1", accountId = "demo", sender = "Larch Street Primary", address = "office@school.example.invalid",
            subject = "Excursion permission needed by Friday",
            summary = "The Year 4 zoo excursion is next Thursday. Permission and \$18 are due by Friday. A hat and water bottle are needed.",
            whenText = "Today 9:12", needsAction = true,
            taskTitle = "Return the excursion permission form", taskDue = "Friday",
            demoBody = "Dear families,\n\nOur Year 4 excursion to the zoo is on Thursday 22 October. Please return the signed permission form and \$18 by this Friday.\n\nStudents should wear a hat, bring a water bottle and pack a light lunch.\n\nThank you,\nThe office",
        ),
        Mail(
            id = "d2", accountId = "demo", sender = "Harbourview Dental", address = "reminders@dental.example.invalid",
            subject = "Appointment reminder: Tuesday 10:40",
            summary = "A check-up is booked for Tuesday at 10:40. Arrive ten minutes early. Reply to change it.",
            whenText = "Today 8:02", needsAction = true,
            taskTitle = "Go to the dental check-up", taskDue = "Tuesday 10:40",
            demoBody = "Hello,\n\nThis is a reminder of your appointment on Tuesday at 10:40 AM with Dr Lee.\n\nPlease arrive ten minutes early. If you can't make it, reply to this email or call us.\n\nHarbourview Dental",
        ),
        Mail(
            id = "d3", accountId = "demo", sender = "Skyline Air", address = "no-reply@airline.example.invalid",
            subject = "Your trip to Melbourne leaves in 3 days",
            summary = "Flight SK281 leaves Saturday at 7:15 from Canberra. Online check-in is open. No action is needed.",
            whenText = "Yesterday", needsAction = false,
            demoBody = "Your flight SK281 to Melbourne departs Saturday at 7:15 AM.\n\nOnline check-in is now open. Bags can be dropped off from 5:45 AM.\n\nHave a good trip.",
        ),
        Mail(
            id = "d4", accountId = "demo", sender = "Power & Water", address = "billing@energy.example.invalid",
            subject = "Your bill is ready",
            summary = "Your bill for \$142.60 is due in 14 days. It is lower than last quarter.",
            whenText = "Yesterday", needsAction = true,
            taskTitle = "Pay the power bill (\$142.60)", taskDue = "In 14 days",
            demoBody = "Your latest bill is ready.\n\nAmount due: \$142.60\nDue date: in 14 days\n\nYou used less than last quarter. Thank you.",
        ),
        Mail(
            id = "d5", accountId = "demo", sender = "Book Club", address = "hello@bookclub.example.invalid",
            subject = "This month's pick and who is bringing snacks",
            summary = "The book is chosen and the meeting is on the 28th. Snacks are still needed.",
            whenText = "Mon", needsAction = false,
            demoBody = "Hi everyone,\n\nThis month we are reading a short mystery. We meet on the 28th at 7 PM.\n\nWe still need someone to bring snacks. Reply if you can.\n\nSee you there!",
        ),
        Mail(
            id = "d6", accountId = "demo", sender = "Garden Shed Co.", address = "orders@shop.example.invalid",
            subject = "Your order has shipped",
            summary = "Your order is on its way and should arrive in 3 to 5 days. No action is needed.",
            whenText = "Mon", needsAction = false,
            demoBody = "Good news! Your order has shipped.\n\nIt should arrive in 3 to 5 business days.\n\nThanks for shopping with us.",
        ),
    )
}
