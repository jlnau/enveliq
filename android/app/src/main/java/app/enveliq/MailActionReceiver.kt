package app.enveliq

import android.app.NotificationManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** The "Archive" and "Delete" (move to Bin) buttons on a new-email alert. Uses the kept sign-in; the email is marked at your mailbox like in the app. */
class MailActionReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val account = intent.getStringExtra("account") ?: return
        val mailId = intent.getStringExtra("mail") ?: return
        val outcome = Outcome.values().firstOrNull { it.api == intent.getStringExtra("outcome") } ?: return
        val noteId = intent.getIntExtra("nid", 0)
        val pending = goAsync()
        val app = context.applicationContext
        Thread {
            try {
                val kept = SessionVault.load(app)
                if (kept == null) {
                    Notifier.simple(app, 2004, "Please open Enveliq", "You are signed out, so that could not be done from the alert.")
                } else {
                    val api = EnveliqApi(kept.first)
                    api.restore(kept.second)
                    api.resolve(Mail(id = mailId, accountId = account, sender = "", address = "", subject = "", summary = "", whenText = "", needsAction = false), outcome)
                    app.getSystemService(NotificationManager::class.java).cancel(noteId)
                }
            } catch (e: Exception) {
                Notifier.simple(app, 2004, "That did not work", "Open Enveliq to look at the email.")
            } finally {
                pending.finish()
            }
        }.start()
    }
}
