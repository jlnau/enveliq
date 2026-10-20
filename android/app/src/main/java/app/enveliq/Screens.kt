package app.enveliq

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.Modifier
import androidx.compose.ui.autofill.ContentType
import androidx.compose.ui.semantics.contentType
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@OptIn(ExperimentalComposeUiApi::class)
@Composable
fun SignInScreen(initialAddress: String, notice: String, linkCode: String?, onLinkUsed: () -> Unit, onDone: (EnveliqApi, String, Boolean) -> Unit) {
    val context = androidx.compose.ui.platform.LocalContext.current
    val linkPrefs = remember { context.getSharedPreferences("enveliq_link", android.content.Context.MODE_PRIVATE) }
    var address by remember { mutableStateOf(initialAddress.ifBlank { "https://" }) }
    var showPassword by remember { mutableStateOf(false) }
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var code by remember { mutableStateOf("") }
    var needsCode by remember { mutableStateOf(false) }
    var keep by remember { mutableStateOf(true) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }
    var api by remember { mutableStateOf<EnveliqApi?>(null) }
    var checking by remember { mutableStateOf(false) }
    var checkNote by remember { mutableStateOf("") }
    var checkOk by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    fun check() {
        if (checking) return
        checking = true
        checkNote = ""
        scope.launch {
            try {
                withContext(Dispatchers.IO) { EnveliqApi(address).checkConnection() }
                checkOk = true
                checkNote = "Enveliq answered at that address. You can sign in."
            } catch (e: ApiException) {
                checkOk = false
                checkNote = e.message ?: "Could not reach that address."
            } catch (e: Exception) {
                checkOk = false
                checkNote = "Could not reach that address."
            } finally {
                checking = false
            }
        }
    }

    fun openBrowser() {
        error = ""
        try {
            val client = EnveliqApi(address)
            val verifier = BrowserLink.newVerifier()
            linkPrefs.edit().putString("verifier", verifier).putString("address", address.trim()).putBoolean("keep", keep).putLong("at", System.currentTimeMillis()).apply()
            context.startActivity(android.content.Intent(android.content.Intent.ACTION_VIEW, android.net.Uri.parse(client.browserSignInUrl(BrowserLink.challengeOf(verifier)))))
        } catch (e: ApiException) {
            error = e.message ?: "That address is not right."
        } catch (e: Exception) {
            error = "No browser on this phone could open the page."
        }
    }

    // The browser handed a one-time code back: swap it (with the secret kept here) for a session.
    LaunchedEffect(linkCode) {
        val code = linkCode ?: return@LaunchedEffect
        val verifier = linkPrefs.getString("verifier", "") ?: ""
        val addr = linkPrefs.getString("address", "") ?: ""
        val keepIt = linkPrefs.getBoolean("keep", true)
        val fresh = System.currentTimeMillis() - linkPrefs.getLong("at", 0L) < 10 * 60 * 1000
        linkPrefs.edit().clear().apply()
        onLinkUsed()
        if (verifier.isEmpty() || addr.isEmpty() || !fresh) {
            error = "That sign-in took too long or did not start here. Please try again."
            return@LaunchedEffect
        }
        // Run in the screen's own scope: clearing linkCode (onLinkUsed) ends this effect, which would cancel the exchange half way.
        scope.launch {
            busy = true
            try {
                val client = EnveliqApi(addr)
                withContext(Dispatchers.IO) { client.exchangeLink(code, verifier, keepIt) }
                onDone(client, addr, keepIt)
            } catch (e: ApiException) {
                error = e.message ?: "That did not work."
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (e: Exception) {
                error = "Something went wrong. Please try again."
            } finally {
                busy = false
            }
        }
    }

    fun go() {
        if (busy) return
        busy = true
        error = ""
        scope.launch {
            try {
                val result = withContext(Dispatchers.IO) {
                    if (needsCode) {
                        api!!.code(code)
                    } else {
                        val client = EnveliqApi(address)
                        api = client
                        client.signIn(username, password, keep)
                    }
                }
                if (result is SignIn.NeedsCode) {
                    needsCode = true
                    code = ""
                } else {
                    password = ""
                    onDone(api!!, address.trim(), keep)
                }
            } catch (e: ApiException) {
                error = e.message ?: "That did not work."
            } catch (e: Exception) {
                error = "Something went wrong. Please try again."
            } finally {
                busy = false
            }
        }
    }

    Column(
        Modifier
            .fillMaxSize()
            .background(Navy)
            .systemBarsPadding()
            .imePadding(),
    ) {
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 22.dp)) {
            Text("Enveliq", color = Blue, fontSize = 40.sp, fontWeight = FontWeight.ExtraBold, modifier = Modifier.padding(top = 28.dp))
            Text("Turn email into clarity.", color = Ink, fontSize = 18.sp, modifier = Modifier.padding(top = 4.dp))
            if (notice.isNotEmpty()) Text(notice, color = Amber, fontSize = 15.sp, modifier = Modifier.padding(top = 14.dp))
            if (!needsCode) {
                Text("Your Enveliq address", color = Muted, fontSize = 14.sp, modifier = Modifier.padding(top = 12.dp, bottom = 6.dp))
                OutlinedTextField(
                    value = address,
                    // A pasted full address replaces the https:// that is already there instead of doubling it.
                    onValueChange = { address = it.replace(Regex("^https?://(?=https?://)", RegexOption.IGNORE_CASE), "") },
                    singleLine = true,
                    placeholder = { Text("https://enveliq.example.com") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
                    modifier = Modifier.fillMaxWidth(),
                )
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    TextButton(onClick = { check() }, enabled = !checking) { Text("Check connection", color = Blue, fontSize = 15.sp) }
                    if (checking) CircularProgressIndicator(Modifier.size(18.dp), color = Blue, strokeWidth = 2.dp)
                }
                if (checkNote.isNotEmpty()) Text(checkNote, color = if (checkOk) Green else Red, fontSize = 14.sp, lineHeight = 20.sp)
                Text("Username", color = Muted, fontSize = 14.sp, modifier = Modifier.padding(top = 16.dp, bottom = 6.dp))
                // The content types tell password managers such as Bitwarden which box is the username, the password and the code.
                OutlinedTextField(
                    value = username, onValueChange = { username = it }, singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Text, imeAction = ImeAction.Next),
                    modifier = Modifier.fillMaxWidth().semantics { contentType = ContentType.Username },
                )
                Text("Password", color = Muted, fontSize = 14.sp, modifier = Modifier.padding(top = 16.dp, bottom = 6.dp))
                OutlinedTextField(
                    value = password, onValueChange = { password = it }, singleLine = true,
                    visualTransformation = if (showPassword) VisualTransformation.None else PasswordVisualTransformation(),
                    trailingIcon = { TextButton(onClick = { showPassword = !showPassword }) { Text(if (showPassword) "Hide" else "Show", color = Blue, fontSize = 15.sp) } },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = ImeAction.Done),
                    modifier = Modifier.fillMaxWidth().semantics { contentType = ContentType.Password },
                )
            } else {
                Text("Enter your code", color = Ink, fontSize = 20.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 16.dp))
                Text(
                    "Open your authenticator app and type the 6 digit code. A recovery code works too.",
                    color = Muted, fontSize = 15.sp, lineHeight = 22.sp, modifier = Modifier.padding(top = 6.dp, bottom = 14.dp),
                )
                CodeField(code, { code = it }, onDone = { if (code.isNotBlank() && !busy) go() }, modifier = Modifier.fillMaxWidth())
            }
            if (!needsCode) {
                Row(Modifier.fillMaxWidth().padding(top = 18.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f).padding(end = 12.dp)) {
                        Text("Keep me signed in on this phone", color = Ink, fontSize = 16.sp)
                        Text("So you don't have to sign in each time. Sign out in Settings to forget it.", color = Muted, fontSize = 13.sp, lineHeight = 18.sp)
                    }
                    Switch(checked = keep, onCheckedChange = { keep = it })
                }
            }
            if (error.isNotEmpty()) {
                Text(error, color = Red, fontSize = 15.sp, modifier = Modifier.padding(top = 14.dp))
            }
            if (!needsCode) {
                OutlinedButton(
                    onClick = { openBrowser() },
                    enabled = !busy && address.trim().removePrefix("https://").removePrefix("http://").isNotBlank(),
                    modifier = Modifier.fillMaxWidth().padding(top = 18.dp).heightIn(min = 48.dp),
                    shape = RoundedCornerShape(14.dp),
                ) { Text("Sign in with a passkey or single sign-on", fontSize = 15.sp) }
                Text("Opens your browser to sign in there, then brings you back here.", color = Muted, fontSize = 13.sp, lineHeight = 18.sp, modifier = Modifier.padding(top = 6.dp))
            }
            Text(
                "The app only talks to your own server, over a secure connection, and never keeps your password.",
                color = Muted, fontSize = 13.sp, lineHeight = 19.sp, modifier = Modifier.padding(top = 18.dp, bottom = 12.dp),
            )
        }
        Row(
            Modifier.fillMaxWidth().background(Panel).padding(horizontal = 22.dp, vertical = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Button(
                onClick = { go() },
                enabled = !busy && (if (needsCode) code.isNotBlank() else address.trim().removePrefix("https://").removePrefix("http://").isNotBlank() && username.isNotBlank() && password.isNotBlank()),
                modifier = Modifier.weight(1f).height(52.dp),
                shape = RoundedCornerShape(14.dp),
                colors = ButtonDefaults.buttonColors(),
            ) {
                if (busy) CircularProgressIndicator(Modifier.size(22.dp), color = Ink, strokeWidth = 2.dp)
                else Text(if (needsCode) "Confirm" else "Sign in", fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
            }
        }
    }
}

/** Shown while the app is locked. Android asks for the fingerprint, face or PIN on its own; the button asks again if it was closed. */
@Composable
fun LockScreen(onUnlock: () -> Unit) {
    LaunchedEffect(Unit) { onUnlock() }
    Column(
        Modifier.fillMaxSize().background(Navy).systemBarsPadding().padding(horizontal = 22.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text("Enveliq", color = Blue, fontSize = 40.sp, fontWeight = FontWeight.ExtraBold)
        Text("Enveliq is locked.", color = Ink, fontSize = 18.sp, modifier = Modifier.padding(top = 6.dp, bottom = 24.dp))
        Button(onClick = onUnlock, modifier = Modifier.fillMaxWidth().height(52.dp), shape = RoundedCornerShape(14.dp)) {
            Text("Unlock", fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
        }
    }
}


/** Shown once, right after the first sign-in: a calm tour of the three things worth knowing. */
@Composable
fun WelcomeScreen(onDone: (openSettings: Boolean) -> Unit) {
    Column(Modifier.fillMaxSize().background(Navy).systemBarsPadding()) {
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 22.dp)) {
            Text("You're in.", color = Ink, fontSize = 32.sp, fontWeight = FontWeight.ExtraBold, modifier = Modifier.padding(top = 36.dp))
            Text("Three things worth knowing. You can change all of them later in Settings.", color = Muted, fontSize = 16.sp, lineHeight = 23.sp, modifier = Modifier.padding(top = 8.dp, bottom = 12.dp))
            WelcomeCard("✦", "Calm summaries", "Each email has a short summary, marked as written by the AI. It can be wrong, so open the original when it matters. Nothing is deleted until you choose Reviewed, Archive or Bin, and you can always Undo.")
            WelcomeCard("🔔", "Alerts, if you want them", "Enveliq can tell you when an email is ready, only for the emails that matter to you if you like. The lock screen only says \"New email\". Choose this in Settings, Notifications.")
            WelcomeCard("🔒", "A lock, if you want one", "Ask for your fingerprint, face or PIN to open Enveliq. Your email is never saved on this phone. Choose this in Settings, Security.")
        }
        Column(Modifier.fillMaxWidth().background(Panel).navigationBarsPadding().padding(horizontal = 22.dp, vertical = 12.dp)) {
            Button(onClick = { onDone(false) }, modifier = Modifier.fillMaxWidth().height(52.dp), shape = RoundedCornerShape(14.dp)) {
                Text("Go to my inbox", fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
            }
            OutlinedButton(
                onClick = { onDone(true) }, modifier = Modifier.fillMaxWidth().padding(top = 8.dp).height(48.dp),
                shape = RoundedCornerShape(14.dp), border = BorderStroke(1.dp, Line),
            ) { Text("Set up alerts and the lock", color = Ink) }
        }
    }
}

@Composable
private fun WelcomeCard(symbol: String, title: String, text: String) {
    androidx.compose.material3.Surface(
        color = Panel, shape = RoundedCornerShape(18.dp), border = BorderStroke(1.dp, Line),
        modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp),
    ) {
        Row(Modifier.padding(16.dp)) {
            Text(symbol, fontSize = 24.sp, modifier = Modifier.padding(end = 14.dp))
            Column {
                Text(title, color = Ink, fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
                Text(text, color = Muted, fontSize = 14.sp, lineHeight = 21.sp, modifier = Modifier.padding(top = 4.dp))
            }
        }
    }
}
