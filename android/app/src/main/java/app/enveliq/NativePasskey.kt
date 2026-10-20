package app.enveliq

import android.content.Context
import androidx.credentials.CredentialManager
import androidx.credentials.GetCredentialRequest
import androidx.credentials.GetPublicKeyCredentialOption
import androidx.credentials.PublicKeyCredential
import androidx.credentials.exceptions.GetCredentialCancellationException

/**
 * Signing in with a passkey that is kept on this phone (Bitwarden, Google Password Manager and others), through Android's own
 * passkey screen. It works when the server lists this app as trusted (docs/ANDROID.md, "Passkeys on the phone"). When it does not
 * work for any reason other than the person closing the screen, the caller opens the browser instead.
 */
object NativePasskey {
    sealed class Result {
        class Got(val json: String) : Result()
        object Cancelled : Result()
        object Unavailable : Result()
    }

    suspend fun get(context: Context, optionsJson: String): Result {
        return try {
            val manager = CredentialManager.create(context)
            val request = GetCredentialRequest(listOf(GetPublicKeyCredentialOption(optionsJson)))
            val credential = manager.getCredential(context, request).credential
            if (credential is PublicKeyCredential) Result.Got(credential.authenticationResponseJson) else Result.Unavailable
        } catch (e: GetCredentialCancellationException) {
            Result.Cancelled
        } catch (e: kotlinx.coroutines.CancellationException) {
            throw e
        } catch (e: Exception) {
            Result.Unavailable       // no passkey saved, this app not trusted by the server yet, or no passkey service: use the browser
        }
    }
}
