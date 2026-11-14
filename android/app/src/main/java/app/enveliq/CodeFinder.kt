package app.enveliq

import android.content.ClipData
import android.content.ClipDescription
import android.content.ClipboardManager
import android.content.Context
import android.os.PersistableBundle

/**
 * Finds a sign-in or verification code in an email's subject and AI summary (never the email body, which is not kept).
 * Same rule as the web app: it must look like a verification email, and the number must follow the word "code".
 */
object CodeFinder {
    private val looksLikeCodeEmail = Regex("""verification|security code|one[- ]time|login|log[- ]in|sign[- ]in|authentication|confirmation code|passcode|\botp\b|2fa|two[- ]factor""", RegexOption.IGNORE_CASE)
    private val hasCodeWord = Regex("""\b(?:code|passcode|pin|otp)\b""", RegexOption.IGNORE_CASE)
    private val afterCodeWord = Regex("""\b(?:code|passcode|pin|otp)\b[^0-9]{0,30}(\d{3}[ -]\d{3}(?!\d)|\d{4,8}(?![ -]?\d))""", RegexOption.IGNORE_CASE)
    private val sixDigits = Regex("""(?<![\d-])(\d{6})(?![ -]?\d)""")

    fun find(subject: String?, summary: String?): String? {
        val all = (subject ?: "") + " " + (summary ?: "")
        if (!looksLikeCodeEmail.containsMatchIn(all) || !hasCodeWord.containsMatchIn(all)) return null
        val m = afterCodeWord.find(all) ?: sixDigits.find(all) ?: return null
        return m.groupValues[1].replace(" ", "").replace("-", "")
    }

    /** Puts the code on the clipboard, marked sensitive so Android hides it from the clipboard preview. */
    fun copy(context: Context, code: String) {
        val clip = ClipData.newPlainText("Code", code)
        clip.description.extras = PersistableBundle().apply { putBoolean(ClipDescription.EXTRA_IS_SENSITIVE, true) }
        context.getSystemService(ClipboardManager::class.java).setPrimaryClip(clip)
    }
}
