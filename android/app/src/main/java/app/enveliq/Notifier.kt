package app.enveliq

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.drawable.Icon
import android.os.Build

/** The app's own notifications. Each kind has its own Android channel, so the phone's settings can mute each one. */
object Notifier {
    const val CHANNEL_MAIL = "mail"
    const val CHANNEL_REMINDERS = "reminders"
    const val CHANNEL_QUIET = "mail_quiet"
    const val CHANNEL_WATCH = "watching"
    const val WATCH_ID = 1002
    const val GROUP_ID = 2002

    /** The notification number for one email's alert, so it can be found again to clear it. */
    fun mailNoteId(mailId: String): Int = 3000 + (mailId.hashCode() and 0xffff)

    /** Takes down the alerts for emails that are no longer waiting, for example because they were reviewed on another device. */
    fun clearGone(context: Context, stillWaiting: Collection<String>, known: Collection<String>) {
        val manager = context.getSystemService(NotificationManager::class.java)
        val keep = stillWaiting.toSet()
        known.filter { it !in keep }.forEach { manager.cancel(mailNoteId(it)) }
        if (keep.isEmpty()) manager.cancel(GROUP_ID)
    }

    fun clearOne(context: Context, mailId: String) {
        context.getSystemService(NotificationManager::class.java).cancel(mailNoteId(mailId))
    }

    fun ensureChannels(context: Context) {
        val manager = context.getSystemService(NotificationManager::class.java)
        val mail = NotificationChannel(CHANNEL_MAIL, "New email", NotificationManager.IMPORTANCE_DEFAULT)
        mail.description = "A quiet note when email that needs you arrives."
        mail.lockscreenVisibility = Notification.VISIBILITY_PRIVATE
        val reminders = NotificationChannel(CHANNEL_REMINDERS, "Task reminders", NotificationManager.IMPORTANCE_DEFAULT)
        reminders.description = "Reminders for tasks that are due."
        reminders.lockscreenVisibility = Notification.VISIBILITY_PRIVATE
        val watch = NotificationChannel(CHANNEL_WATCH, "Watching for new email", NotificationManager.IMPORTANCE_MIN)
        watch.description = "The small note Android requires while Enveliq waits quietly for new email."
        watch.setShowBadge(false)
        val quiet = NotificationChannel(CHANNEL_QUIET, "New email (quiet hours)", NotificationManager.IMPORTANCE_LOW)
        quiet.description = "New email that arrives during your quiet hours: no sound and no buzz."
        quiet.lockscreenVisibility = Notification.VISIBILITY_PRIVATE
        manager.createNotificationChannel(quiet)
        manager.createNotificationChannel(watch)
        manager.createNotificationChannel(mail)
        manager.createNotificationChannel(reminders)
    }

    fun canNotify(context: Context): Boolean =
        Build.VERSION.SDK_INT < 33 ||
            context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED

    /**
     * Shows what a real alert will look like: on the lock screen it only says "New email"; the words show once the phone is unlocked.
     */
    fun sendTest(context: Context): Boolean {
        if (!canNotify(context)) return false
        val manager = context.getSystemService(NotificationManager::class.java)
        val open = PendingIntent.getActivity(
            context, 0, Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val generic = Notification.Builder(context, CHANNEL_MAIL)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle("New email")
            .build()
        val note = Notification.Builder(context, CHANNEL_MAIL)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle("Larch Street Primary")
            .setContentText("Excursion permission is needed by Friday.")
            .setVisibility(Notification.VISIBILITY_PRIVATE)
            .setPublicVersion(generic)
            .setContentIntent(open)
            .setAutoCancel(true)
            .build()
        manager.notify(1001, note)
        return true
    }

    private fun openApp(context: Context): PendingIntent = PendingIntent.getActivity(
        context, 0, Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
    )

    /** A plain note with the same words on and off the lock screen (nothing private in it). */
    fun simple(context: Context, id: Int, title: String, text: String) {
        if (!canNotify(context)) return
        val note = Notification.Builder(context, CHANNEL_MAIL)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(title).setContentText(text)
            .setContentIntent(openApp(context)).setAutoCancel(true).build()
        context.getSystemService(NotificationManager::class.java).notify(id, note)
    }

    /** A plain note for messages, notes, tasks or parcels. The words are the same on and off the lock screen: they say nothing private. */
    fun other(context: Context, kind: String, text: String, quiet: Boolean) {
        if (!canNotify(context)) return
        val title = when (kind) {
            "messages" -> "New message"
            "tasks" -> "A task is due"
            "shipping" -> "A parcel needs you"
            else -> "Something new in Enveliq"
        }
        val note = Notification.Builder(context, if (quiet) CHANNEL_QUIET else CHANNEL_REMINDERS)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(title).setContentText(text)
            .setContentIntent(openApp(context)).setAutoCancel(true).build()
        context.getSystemService(NotificationManager::class.java).notify(4000 + (kind.hashCode() and 0xff), note)
    }

    /**
     * New email whose AI summary is done. On the lock screen it only says "New email"; the sender and subject show once the phone
     * is unlocked. During quiet hours it still appears, but without sound or buzz.
     */
    fun newMail(context: Context, mails: List<Mail>, quiet: Boolean) {
        if (!canNotify(context) || mails.isEmpty()) return
        val manager = context.getSystemService(NotificationManager::class.java)
        val generic = Notification.Builder(context, CHANNEL_MAIL)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(if (mails.size == 1) "New email" else "${mails.size} new emails")
            .build()
        val builder = Notification.Builder(context, if (quiet) CHANNEL_QUIET else CHANNEL_MAIL).setSmallIcon(R.drawable.ic_notification)
        val id: Int
        if (mails.size == 1) {
            val m = mails[0]
            builder.setContentTitle(m.sender).setContentText(m.subject)
            id = mailNoteId(m.id)
            // Tapping the alert opens this email, and the two buttons act on it without opening the app.
            val open = PendingIntent.getActivity(
                context, id,
                Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP)
                    .putExtra(MainActivity.EXTRA_MAIL, m.id).putExtra(MainActivity.EXTRA_ACCOUNT, m.accountId),
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
            )
            builder.setContentIntent(open)
            builder.addAction(action(context, id, 1, "Reviewed", m, Outcome.Reviewed))
            builder.addAction(action(context, id, 2, "Archive", m, Outcome.Archived))
        } else {
            builder.setContentTitle("${mails.size} new emails")
            builder.setContentText(mails.take(3).joinToString(", ") { it.sender })
            val style = Notification.InboxStyle()
            mails.take(5).forEach { style.addLine(it.sender + ": " + it.subject) }
            builder.setStyle(style)
            id = GROUP_ID
        }
        builder.setVisibility(Notification.VISIBILITY_PRIVATE).setPublicVersion(generic).setAutoCancel(true)
        if (mails.size != 1) builder.setContentIntent(openApp(context))
        manager.notify(id, builder.build())
    }

    private fun action(context: Context, noteId: Int, n: Int, label: String, mail: Mail, outcome: Outcome): Notification.Action {
        val intent = Intent(context, MailActionReceiver::class.java)
            .putExtra("account", mail.accountId).putExtra("mail", mail.id).putExtra("outcome", outcome.api).putExtra("nid", noteId)
        val pending = PendingIntent.getBroadcast(context, noteId * 10 + n, intent, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        return Notification.Action.Builder(Icon.createWithResource(context, R.drawable.ic_notification), label, pending).build()
    }
}
