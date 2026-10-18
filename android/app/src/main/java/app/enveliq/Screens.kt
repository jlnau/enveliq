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
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@Composable
fun StartScreen(notice: String, onSample: () -> Unit, onConnect: () -> Unit) {
    Column(
        Modifier
            .fillMaxSize()
            .background(Navy)
            .systemBarsPadding()
            .padding(28.dp)
            .verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.Center,
    ) {
        Text("Enveliq", color = Blue, fontSize = 44.sp, fontWeight = FontWeight.ExtraBold)
        Spacer(Modifier.height(6.dp))
        Text("Turn email into clarity.", color = Ink, fontSize = 20.sp)
        if (notice.isNotEmpty()) Text(notice, color = Amber, fontSize = 15.sp, modifier = Modifier.padding(top = 14.dp))
        Spacer(Modifier.height(28.dp))
        Text(
            "Your email, calmly sorted. One thing at a time, with a short summary of each email and the buttons you need.",
            color = Muted, fontSize = 16.sp, lineHeight = 24.sp,
        )
        Spacer(Modifier.height(32.dp))
        Button(
            onClick = onSample,
            modifier = Modifier.fillMaxWidth().height(54.dp),
            shape = RoundedCornerShape(14.dp),
        ) { Text("Look around with sample email", fontSize = 17.sp, fontWeight = FontWeight.SemiBold) }
        Text("Made-up email. Nothing to set up.", color = Muted, fontSize = 13.sp, modifier = Modifier.padding(top = 6.dp, bottom = 18.dp))
        OutlinedButton(
            onClick = onConnect,
            modifier = Modifier.fillMaxWidth().height(54.dp),
            shape = RoundedCornerShape(14.dp),
            border = BorderStroke(1.dp, Line),
        ) { Text("Sign in to my Enveliq", fontSize = 17.sp, color = Ink) }
        Text("Use your own Enveliq server.", color = Muted, fontSize = 13.sp, modifier = Modifier.padding(top = 6.dp))
    }
}

@Composable
fun SignInScreen(initialAddress: String, onBack: () -> Unit, onDone: (EnveliqApi, String, Boolean) -> Unit) {
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
        Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = onBack) { Text("‹ Back", color = Blue, fontSize = 16.sp) }
            Text("Sign in to my Enveliq", color = Ink, fontWeight = FontWeight.SemiBold, fontSize = 18.sp)
        }
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 22.dp)) {
            if (!needsCode) {
                Text("Your Enveliq address", color = Muted, fontSize = 14.sp, modifier = Modifier.padding(top = 12.dp, bottom = 6.dp))
                OutlinedTextField(
                    value = address, onValueChange = { address = it }, singleLine = true,
                    placeholder = { Text("https://enveliq.example.com") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
                    modifier = Modifier.fillMaxWidth(),
                )
                Text("Username", color = Muted, fontSize = 14.sp, modifier = Modifier.padding(top = 16.dp, bottom = 6.dp))
                OutlinedTextField(value = username, onValueChange = { username = it }, singleLine = true, modifier = Modifier.fillMaxWidth())
                Text("Password", color = Muted, fontSize = 14.sp, modifier = Modifier.padding(top = 16.dp, bottom = 6.dp))
                OutlinedTextField(
                    value = password, onValueChange = { password = it }, singleLine = true,
                    visualTransformation = PasswordVisualTransformation(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                    modifier = Modifier.fillMaxWidth(),
                )
            } else {
                Text("Enter your code", color = Ink, fontSize = 20.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 16.dp))
                Text(
                    "Open your authenticator app and type the 6 digit code. A recovery code works too.",
                    color = Muted, fontSize = 15.sp, lineHeight = 22.sp, modifier = Modifier.padding(top = 6.dp, bottom = 14.dp),
                )
                OutlinedTextField(
                    value = code, onValueChange = { code = it }, singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Text),
                    modifier = Modifier.fillMaxWidth(),
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
