package app.enveliq

import android.content.Intent
import android.os.Bundle
import android.os.SystemClock
import android.view.WindowManager
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity

class MainActivity : FragmentActivity() {
    /** Set when someone taps a new-email alert: (account id, email id). The inbox opens that email once it has loaded. */
    var openRequest by mutableStateOf<Pair<String, String>?>(null)

    /** The one-time code the browser handed back after signing in there. Used once by the sign-in screen. */
    var linkCode by mutableStateOf<String?>(null)

    /** Text shared to Enveliq from another app: (subject, text). The inbox opens a new email with it once the person is signed in. */
    var shareRequest by mutableStateOf<Pair<String, String>?>(null)

    /** A "mailto:" link tapped in another app: (to, subject, body). Opens a new email with those filled in. */
    var mailtoRequest by mutableStateOf<Triple<String, String, String>?>(null)

    /** True while the app is locked and waiting for the fingerprint, face or PIN. */
    var locked by mutableStateOf(false)
    private var stoppedAt = 0L

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        Notifier.ensureChannels(this)
        MailWatcherService.start(this)          // only does anything when the person has alerts on and a kept sign-in
        val prefs = getSharedPreferences("enveliq", MODE_PRIVATE)
        Look.load(prefs)
        Pal.dark = when (Look.theme) {
            "light" -> false
            "dark" -> true
            else -> (resources.configuration.uiMode and android.content.res.Configuration.UI_MODE_NIGHT_MASK) == android.content.res.Configuration.UI_MODE_NIGHT_YES
        }
        setSecure(prefs.getBoolean("hide_in_recents", false))
        locked = prefs.getBoolean("app_lock", false) && canLock()
        readRequest(intent)
        addOnNewIntentListener { readRequest(it) }
        setContent {
            EnveliqTheme {
                if (locked) LockScreen(onUnlock = { unlock() }) else EnveliqApp(this)
            }
        }
    }

    private fun readRequest(intent: Intent?) {
        if (intent?.action == Intent.ACTION_SEND && intent.type?.startsWith("text/") == true) {
            val text = intent.getStringExtra(Intent.EXTRA_TEXT) ?: ""
            if (text.isNotBlank()) shareRequest = (intent.getStringExtra(Intent.EXTRA_SUBJECT) ?: "").take(300) to text.take(20000)
            return
        }
        val link = intent?.data
        if (link != null && link.scheme == "mailto" && (intent?.action == Intent.ACTION_SENDTO || intent?.action == Intent.ACTION_VIEW)) {
            val to = (link.schemeSpecificPart.substringBefore("?")).take(500)
            val subject = (try { link.getQueryParameter("subject") } catch (e: Exception) { null } ?: intent?.getStringExtra(Intent.EXTRA_SUBJECT) ?: "").take(300)
            val text = (try { link.getQueryParameter("body") } catch (e: Exception) { null } ?: intent?.getStringExtra(Intent.EXTRA_TEXT) ?: "").take(20000)
            mailtoRequest = Triple(to, subject, text)
            return
        }
        if (link != null && link.scheme == "enveliq" && link.host == "signin") {
            val code = link.getQueryParameter("code") ?: ""
            if (Regex("[A-Za-z0-9_-]{20,100}").matches(code)) linkCode = code
            return
        }
        val mail = intent?.getStringExtra(EXTRA_MAIL) ?: return
        val account = intent.getStringExtra(EXTRA_ACCOUNT) ?: return
        openRequest = account to mail
    }

    override fun onStop() {
        super.onStop()
        stoppedAt = SystemClock.elapsedRealtime()
    }

    override fun onStart() {
        super.onStart()
        // Locks again after the app has been out of sight for a minute.
        val prefs = getSharedPreferences("enveliq", MODE_PRIVATE)
        if (prefs.getBoolean("app_lock", false) && stoppedAt > 0 && SystemClock.elapsedRealtime() - stoppedAt > 60_000 && canLock()) locked = true
    }

    /** True when the phone has a fingerprint, face or PIN set up. The app never locks people out of a phone that has none. */
    fun canLock(): Boolean =
        BiometricManager.from(this).canAuthenticate(AUTH) == BiometricManager.BIOMETRIC_SUCCESS

    fun unlock() {
        if (!canLock()) {
            locked = false
            return
        }
        val prompt = BiometricPrompt(
            this, ContextCompat.getMainExecutor(this),
            object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                    locked = false
                }
            },
        )
        prompt.authenticate(
            BiometricPrompt.PromptInfo.Builder()
                .setTitle("Open Enveliq")
                .setSubtitle("Use your fingerprint, face or PIN")
                .setAllowedAuthenticators(AUTH)
                .build(),
        )
    }

    /** Hides the app's picture in the phone's recent-apps view, and stops screenshots. */
    fun setSecure(on: Boolean) {
        if (on) window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        else window.clearFlags(WindowManager.LayoutParams.FLAG_SECURE)
    }

    companion object {
        const val EXTRA_MAIL = "open_mail"
        const val EXTRA_ACCOUNT = "open_account"
        private const val AUTH = BiometricManager.Authenticators.BIOMETRIC_WEAK or BiometricManager.Authenticators.DEVICE_CREDENTIAL
    }
}
