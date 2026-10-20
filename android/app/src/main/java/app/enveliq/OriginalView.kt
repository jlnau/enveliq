package app.enveliq

import android.annotation.SuppressLint
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * The original email, full screen. When the email has a formatted (HTML) version the app shows it as its sender made it: layout, colours,
 * tables, pictures that came inside the email, and links. Plain text is shown when there is no formatted version, or when the person asks.
 *
 * What keeps this safe: the server rebuilds the HTML from allowed parts only (no scripts, forms, frames or styles that load files).
 * The page here also runs with JavaScript off, no file or storage access, and no way to leave the page by itself:
 * every link asks first. Pictures from the internet stay blocked (they can tell the sender you opened the email) until you tap Show pictures.
 */
@Composable
internal fun OriginalScreen(mail: Mail, api: EnveliqApi, onClose: () -> Unit) {
    var info by remember(mail.id) { mutableStateOf<OriginalInfo?>(null) }
    var html by remember(mail.id) { mutableStateOf<String?>(null) }
    var images by remember(mail.id) { mutableStateOf(false) }
    var plain by remember(mail.id) { mutableStateOf(false) }
    var error by remember(mail.id) { mutableStateOf("") }
    var loading by remember(mail.id) { mutableStateOf(true) }
    var asking by remember(mail.id) { mutableStateOf<String?>(null) }

    LaunchedEffect(mail.id) {
        try {
            info = withContext(Dispatchers.IO) { api.originalInfo(mail) }
        } catch (e: ApiException) {
            error = e.message ?: "Could not open the original email."
            loading = false
        } catch (e: Exception) {
            error = "Could not open the original email."
            loading = false
        }
    }
    val known = info
    LaunchedEffect(known, images) {
        if (known == null) return@LaunchedEffect
        if (!known.hasHtml) {
            loading = false
            return@LaunchedEffect
        }
        loading = true
        error = ""
        try {
            html = withContext(Dispatchers.IO) { api.originalHtml(mail, images) }
        } catch (e: ApiException) {
            html = null
            plain = true          // the plain text is still there to read
            error = e.message ?: "Could not show the formatted email."
        } catch (e: Exception) {
            html = null
            plain = true
            error = "Could not show the formatted email."
        } finally {
            loading = false
        }
    }

    Dialog(onDismissRequest = onClose, properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        Column(Modifier.fillMaxSize().background(Navy).systemBarsPadding()) {
            Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                TextButton(onClick = onClose) { Text("‹ Back", color = Blue, fontSize = 16.sp) }
                Text(mail.subject, color = Ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
            }
            if (known != null && known.hasHtml) {
                Row(Modifier.padding(horizontal = 16.dp, vertical = 4.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    FilterChip(selected = !plain, onClick = { plain = false }, label = { Text("As sent") })
                    FilterChip(selected = plain, onClick = { plain = true }, label = { Text("Plain text") })
                }
                if (!plain && !images && known.remoteImages > 0) {
                    Surface(color = Panel, shape = RoundedCornerShape(12.dp), border = BorderStroke(1.dp, Line), modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 6.dp)) {
                        Row(Modifier.padding(start = 14.dp, end = 6.dp, top = 6.dp, bottom = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                            Text(
                                (if (known.remoteImages == 1) "1 picture from the internet is not shown." else "${known.remoteImages} pictures from the internet are not shown.") +
                                    " Loading them can tell the sender you opened this email.",
                                color = Muted, fontSize = 13.sp, lineHeight = 18.sp, modifier = Modifier.weight(1f),
                            )
                            TextButton(onClick = { images = true }) { Text("Show pictures", color = Blue) }
                        }
                    }
                }
            }
            Box(Modifier.weight(1f).fillMaxWidth()) {
                val page = html
                when {
                    error.isNotEmpty() && info == null -> Text(error, color = Red, fontSize = 15.sp, modifier = Modifier.padding(20.dp))
                    known == null || (loading && page == null && !plain) -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator(color = Blue) }
                    plain || page == null -> Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp)) {
                        if (error.isNotEmpty()) Text(error + " Showing the plain text.", color = Amber, fontSize = 13.sp, modifier = Modifier.padding(bottom = 8.dp))
                        Text(
                            if (known!!.hasHtml) "Plain text version" else "This email has no formatted version, so this is its plain text. Links and pictures are switched off.",
                            color = Muted, fontSize = 12.sp, modifier = Modifier.padding(bottom = 6.dp),
                        )
                        Surface(color = Color.White, shape = RoundedCornerShape(12.dp), modifier = Modifier.fillMaxWidth()) {
                            androidx.compose.foundation.text.selection.SelectionContainer {
                                Text(known!!.text, color = Color(0xFF1B2430), fontSize = 15.sp, lineHeight = 23.sp, modifier = Modifier.padding(16.dp))
                            }
                        }
                        LinksSection(known!!.text)
                        androidx.compose.foundation.layout.Spacer(Modifier.padding(bottom = 24.dp))
                    }
                    else -> HtmlPane(page, images, onLink = { asking = it }, modifier = Modifier.fillMaxSize())
                }
            }
        }
    }
    val target = asking
    if (target != null) LinkConfirm(target) { asking = null }
}

/** The email page itself. JavaScript is off, files and storage are closed, and no link can load by itself. */
@SuppressLint("SetJavaScriptEnabled")
@Composable
private fun HtmlPane(html: String, images: Boolean, onLink: (String) -> Unit, modifier: Modifier) {
    val link by rememberUpdatedState(onLink)
    AndroidView(
        modifier = modifier,
        factory = { context ->
            WebView(context).apply {
                setBackgroundColor(android.graphics.Color.WHITE)
                settings.javaScriptEnabled = false
                settings.allowFileAccess = false
                settings.allowContentAccess = false
                settings.domStorageEnabled = false
                settings.setGeolocationEnabled(false)
                settings.cacheMode = WebSettings.LOAD_NO_CACHE
                settings.mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
                settings.safeBrowsingEnabled = true
                settings.useWideViewPort = true
                settings.loadWithOverviewMode = true
                settings.setSupportZoom(true)
                settings.builtInZoomControls = true
                settings.displayZoomControls = false
                webViewClient = object : WebViewClient() {
                    override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                        link(request.url.toString())          // never opens by itself: the person is asked first
                        return true
                    }
                }
            }
        },
        update = { view ->
            view.settings.blockNetworkLoads = !images
            val key = (if (images) "1" else "0") + html.hashCode()
            if (view.tag != key) {
                view.tag = key
                view.loadDataWithBaseURL("about:blank", html, "text/html", "utf-8", null)
            }
        },
        onRelease = { it.destroy() },
    )
}
