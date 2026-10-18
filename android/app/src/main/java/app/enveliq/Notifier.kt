package app.enveliq

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build

/** The app's own notifications. Each kind has its own Android channel, so the phone's settings can mute each one. */
object Notifier {
    const val CHANNEL_MAIL = "mail"
    const val CHANNEL_REMINDERS = "reminders"

    fun ensureChannels(context: Context) {
        val manager = context.getSystemService(NotificationManager::class.java)
        val mail = NotificationChannel(CHANNEL_MAIL, "New email", NotificationManager.IMPORTANCE_DEFAULT)
        mail.description = "A quiet note when email that needs you arrives."
        mail.lockscreenVisibility = Notification.VISIBILITY_PRIVATE
        val reminders = NotificationChannel(CHANNEL_REMINDERS, "Task reminders", NotificationManager.IMPORTANCE_DEFAULT)
        reminders.description = "Reminders for tasks that are due."
        reminders.lockscreenVisibility = Notification.VISIBILITY_PRIVATE
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
}
