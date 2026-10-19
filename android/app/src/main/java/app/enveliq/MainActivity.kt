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

    /** True while the app is locked and waiting for the fingerprint, face or PIN. */
    var locked by mutableStateOf(false)
    private var stoppedAt = 0L

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        Notifier.ensureChannels(this)
        MailWatcherService.start(this)          // only does anything when the person has alerts on and a kept sign-in
        val prefs = getSharedPreferences("enveliq", MODE_PRIVATE)
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
