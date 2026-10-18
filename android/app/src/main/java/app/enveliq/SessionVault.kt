package app.enveliq

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Keeps the signed-in session between runs, only when the person chose "Keep me signed in on this device".
 * What is kept is the server's sign-in cookie, encrypted with a key that lives in the Android Keystore and never leaves the phone.
 * The password is never kept. Signing out (or the server refusing the session) removes it.
 */
object SessionVault {
    private const val ALIAS = "enveliq_session_key"
    private const val FILE = "enveliq_session"

    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore")
        store.load(null)
        (store.getKey(ALIAS, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(
            KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build()
        )
        return generator.generateKey()
    }

    fun save(context: Context, server: String, cookies: String) {
        if (cookies.isEmpty()) return
        try {
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.ENCRYPT_MODE, key())
            val sealed = cipher.doFinal(cookies.toByteArray(Charsets.UTF_8))
            context.getSharedPreferences(FILE, Context.MODE_PRIVATE).edit()
                .putString("server", server)
                .putString("iv", Base64.encodeToString(cipher.iv, Base64.NO_WRAP))
                .putString("data", Base64.encodeToString(sealed, Base64.NO_WRAP))
                .apply()
        } catch (_: Exception) {
            clear(context)
        }
    }

    /** The kept server address and cookies, or null when nothing is kept or it can no longer be read. */
    fun load(context: Context): Pair<String, String>? {
        val prefs = context.getSharedPreferences(FILE, Context.MODE_PRIVATE)
        val server = prefs.getString("server", null) ?: return null
        val iv = prefs.getString("iv", null) ?: return null
        val data = prefs.getString("data", null) ?: return null
        return try {
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, Base64.decode(iv, Base64.NO_WRAP)))
            val plain = cipher.doFinal(Base64.decode(data, Base64.NO_WRAP))
            Pair(server, String(plain, Charsets.UTF_8))
        } catch (_: Exception) {
            clear(context)
            null
        }
    }

    fun clear(context: Context) {
        context.getSharedPreferences(FILE, Context.MODE_PRIVATE).edit().clear().apply()
    }
}
