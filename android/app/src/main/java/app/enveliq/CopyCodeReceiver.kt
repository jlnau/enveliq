package app.enveliq

import android.app.NotificationManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.widget.Toast

/** The "Copy code" button on a new-email alert for a verification code. Copies the code and closes the alert. */
class CopyCodeReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val code = intent.getStringExtra("code") ?: return
        CodeFinder.copy(context, code)
        context.getSystemService(NotificationManager::class.java).cancel(intent.getIntExtra("nid", 0))
        Toast.makeText(context, "Copied the code.", Toast.LENGTH_SHORT).show()
    }
}
