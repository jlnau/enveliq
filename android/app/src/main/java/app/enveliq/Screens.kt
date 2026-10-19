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
import androidx.compose.foundation.layout.imePadding
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
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@OptIn(ExperimentalComposeUiApi::class)
@Composable
fun SignInScreen(initialAddress: String, notice: String, onDone: (EnveliqApi, String, Boolean) -> Unit) {
    var address by remember { mutableStateOf(initialAddress) }
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var code by remember { mutableStateOf("") }
    var needsCode by remember { mutableStateOf(false) }
    var keep by remember { mutableStateOf(true) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }
    var api by remember { mutableStateOf<EnveliqApi?>(null) }
    val scope = rememberCoroutineScope()

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
                    value = address, onValueChange = { address = it }, singleLine = true,
                    placeholder = { Text("https://enveliq.example.com") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
                    modifier = Modifier.fillMaxWidth(),
                )
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
                    visualTransformation = PasswordVisualTransformation(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = ImeAction.Done),
                    modifier = Modifier.fillMaxWidth().semantics { contentType = ContentType.Password },
                )
            } else {
                Text("Enter your code", color = Ink, fontSize = 20.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 16.dp))
                Text(
                    "Open your authenticator app and type the 6 digit code. A recovery code works too.",
                    color = Muted, fontSize = 15.sp, lineHeight = 22.sp, modifier = Modifier.padding(top = 6.dp, bottom = 14.dp),
                )
                OutlinedTextField(
                    value = code, onValueChange = { code = it }, singleLine = true,
                    placeholder = { Text("Verification code") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Text, imeAction = ImeAction.Done),
                    modifier = Modifier.fillMaxWidth().semantics { contentType = ContentType("2faAppOTP") },
                )
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
            Text(
                "Passkeys and single sign-on are coming to the app. Until then, use your password. The app only talks to your own server, over a secure connection, and never keeps your password.",
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
                enabled = !busy && (if (needsCode) code.isNotBlank() else address.isNotBlank() && username.isNotBlank() && password.isNotBlank()),
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
