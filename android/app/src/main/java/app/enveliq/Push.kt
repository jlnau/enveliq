package app.enveliq

import android.content.Context
import com.google.firebase.FirebaseApp
import com.google.firebase.messaging.FirebaseMessaging
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume

/**
 * Google's push service, only used when the person chooses it in Settings. Until then the app never contacts Google:
 * Firebase's automatic start-up is switched off in the manifest, so no token is made and nothing is sent.
 */
object Push {
    /** True when this build includes the Firebase project's file (the GOOGLE_SERVICES_JSON secret) and the phone has Google Play services. */
    fun installed(context: Context): Boolean = try {
        FirebaseApp.getApps(context).isNotEmpty()
    } catch (_: Throwable) {
        false
    }

    /** Asks Google for this phone's push address. Null when Google does not answer. */
    suspend fun token(context: Context): String? {
        if (!installed(context)) return null
        FirebaseMessaging.getInstance().isAutoInitEnabled = true
        return suspendCancellableCoroutine { cont ->
            FirebaseMessaging.getInstance().token.addOnCompleteListener { cont.resume(if (it.isSuccessful) it.result else null) }
        }
    }

    /** Stops using Google: the phone's address is deleted and nothing starts by itself again. Best effort. */
    fun stop(context: Context) {
        try {
            if (!installed(context)) return
            FirebaseMessaging.getInstance().isAutoInitEnabled = false
            FirebaseMessaging.getInstance().deleteToken()
        } catch (_: Throwable) {
        }
    }
}

/** Receives Google's tiny wake-up message (it only says "mail" or "test", never any words) and then asks Enveliq itself what is new. */
class PushService : FirebaseMessagingService() {
    override fun onMessageReceived(message: RemoteMessage) {
        if (!AlertPrefs.on(this) || AlertPrefs.mode(this) != "google") return
        when (message.data["kind"]) {
            "mail" -> Alerts.checkNow(this)
            "test" -> Notifier.sendTest(this)
        }
    }

    /** Google changed this phone's address: tell Enveliq the new one. */
    override fun onNewToken(token: String) {
        if (!AlertPrefs.on(this) || AlertPrefs.mode(this) != "google") return
        val kept = SessionVault.load(this) ?: return
        try {
            val api = EnveliqApi(kept.first)
            api.restore(kept.second)
            AlertPrefs.setPushDevice(this, api.registerPush(token, android.os.Build.MODEL, AlertPrefs.pushDevice(this)))
        } catch (_: Exception) {
        }
    }
}
