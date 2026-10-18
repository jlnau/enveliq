package app.enveliq

import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        Notifier.ensureChannels(this)
        val prefs = getSharedPreferences("enveliq", MODE_PRIVATE)
        setSecure(prefs.getBoolean("hide_in_recents", false))
        setContent {
            EnveliqTheme {
                EnveliqApp(this)
            }
        }
    }

    /** Hides the app's picture in the phone's recent-apps view, and stops screenshots. */
    fun setSecure(on: Boolean) {
        if (on) window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        else window.clearFlags(WindowManager.LayoutParams.FLAG_SECURE)
    }
}
