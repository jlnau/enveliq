package app.enveliq

import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.net.CookieHandler
import java.net.CookieManager
import java.net.HttpCookie
import java.net.HttpURLConnection
import java.net.URI
import java.net.URL
import java.net.URLEncoder
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale
import javax.net.ssl.SSLException

/** The secret and its fingerprint for signing in through the browser (PKCE): only the fingerprint travels through the browser. */
object BrowserLink {
    fun newVerifier(): String {
        val bytes = ByteArray(32)
        java.security.SecureRandom().nextBytes(bytes)
        return android.util.Base64.encodeToString(bytes, android.util.Base64.URL_SAFE or android.util.Base64.NO_WRAP or android.util.Base64.NO_PADDING)
    }

    fun challengeOf(verifier: String): String {
        val digest = java.security.MessageDigest.getInstance("SHA-256").digest(verifier.toByteArray(Charsets.US_ASCII))
        return android.util.Base64.encodeToString(digest, android.util.Base64.URL_SAFE or android.util.Base64.NO_WRAP or android.util.Base64.NO_PADDING)
    }
}

class ApiException(message: String, val code: Int = 0) : Exception(message)

sealed class SignIn {
    object Done : SignIn()
    object NeedsCode : SignIn()
}

private fun JSONObject.str(key: String): String = if (isNull(key)) "" else optString(key)

private fun enc(value: String): String = URLEncoder.encode(value, "UTF-8").replace("+", "%20")

fun whenText(seconds: Long): String {
    if (seconds <= 0L) return ""
    val at = Instant.ofEpochSecond(seconds).atZone(ZoneId.systemDefault())
    val days = (System.currentTimeMillis() / 1000 - seconds) / 86400
    val pattern = if (days < 6) "EEE HH:mm" else "d MMM"
    return at.format(DateTimeFormatter.ofPattern(pattern, Locale.getDefault()))
}

/**
 * Talks to a real Enveliq over HTTPS, using the same sign-in and the same routes as the website.
 * The signed-in session is a cookie held in memory only: it is never written to the phone's storage.
 * The server decides who may read what; the app never says who it is.
 */
class EnveliqApi(address: String) {
    private val base: String = normalise(address)
    private var userId: String = ""

    init {
        if (CookieHandler.getDefault() == null) CookieHandler.setDefault(CookieManager())
    }

    companion object {
        fun normalise(address: String): String {
            var a = address.trim().trimEnd('/')
            if (a.isEmpty()) throw ApiException("Type the address of your Enveliq, for example https://enveliq.example.com")
            if (!a.contains("://")) a = "https://$a"
            if (!a.startsWith("https://")) throw ApiException("The address must start with https://. The app only talks to your server over a secure connection.")
            if (a.removePrefix("https://").isBlank()) throw ApiException("Type the address of your Enveliq after the https://, for example enveliq.example.com")
            // People may type the address with /api (or /api/v1) on the end, for example when only that path is open
            // through a security layer such as Cloudflare Access. The app adds /api/v1/... itself, so take it off.
            a = a.replace(Regex("/api(/v1)?$", RegexOption.IGNORE_CASE), "").trimEnd('/')
            return a
        }

        fun forgetSession() {
            val handler = CookieHandler.getDefault()
            if (handler is CookieManager) handler.cookieStore.removeAll()
        }
    }

    private fun detail(text: String, code: Int): String {
        try {
            val d = JSONObject(text).opt("detail")
            // A route the server does not have: it is an older Enveliq than this app.
            if (code == 404 && d == "Not Found") return "Your Enveliq server does not have this yet. Update the server to the newest version, then try again."
            if (d is String && d.isNotBlank()) return d
            if (d is JSONObject && d.str("message").isNotBlank()) return d.str("message")
        } catch (_: Exception) {
        }
        return when (code) {
            401 -> "You are not signed in."
            403 -> "That is not allowed."
            404 -> "Not found."
            429 -> "Too many tries. Wait a minute and try again."
            400, 422 -> "Something in that was not right. Check what you typed and try again."
            502, 503, 504 -> "Your Enveliq could not be reached just now. It may be restarting. Try again in a minute."
            else -> if (code >= 500) "Your Enveliq had a problem. Try again in a moment." else "That did not work. Please try again."
        }
    }

    private fun call(method: String, path: String, body: JSONObject? = null): String {
        val conn = URL(base + path).openConnection() as HttpURLConnection
        try {
            conn.requestMethod = method
            conn.connectTimeout = 15000
            conn.readTimeout = 30000
            conn.setRequestProperty("Accept", "application/json")
            // Lets "Your devices" show a plain name for this phone.
            conn.setRequestProperty("X-Enveliq-Device", "Enveliq app on " + android.os.Build.MODEL.take(40))
            if (body != null) {
                conn.doOutput = true
                conn.setRequestProperty("Content-Type", "application/json")
                conn.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            }
            val code = conn.responseCode
            val stream = if (code >= 400) conn.errorStream else conn.inputStream
            val text = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() } ?: ""
            // A web page instead of an answer: usually a security layer (for example Cloudflare Access) in front of the site.
            if (text.trimStart().startsWith("<")) {
                throw ApiException("That address did not answer like Enveliq. If your site is behind a security layer such as Cloudflare Access, allow the /api path for the app.")
            }
            if (code >= 400) throw ApiException(detail(text, code), code)
            return text
        } catch (e: ApiException) {
            throw e
        } catch (e: SSLException) {
            throw ApiException("The server's security certificate was not accepted, so the app did not connect.")
        } catch (e: IOException) {
            throw ApiException("Could not reach your Enveliq. Check the address and your connection.")
        } finally {
            conn.disconnect()
        }
    }

    private fun finish(response: JSONObject): SignIn = when (response.str("next")) {
        "mfa" -> SignIn.NeedsCode
        "done" -> {
            userId = response.optJSONObject("user")?.str("id") ?: ""
            SignIn.Done
        }
        else -> throw ApiException("This account has to finish setting up on the website first.")
    }

    fun signIn(username: String, password: String, keep: Boolean): SignIn {
        val body = JSONObject().put("username", username.trim()).put("password", password).put("remember", keep)
        return finish(JSONObject(call("POST", "/api/v1/auth/login", body)))
    }

    /** The page in the phone's browser where the person signs in the usual way (passkey, single sign-on, two-factor) and is handed back to the app. */
    fun browserSignInUrl(challenge: String): String = "$base/app-signin?c=" + enc(challenge)

    /** Swaps the one-time code the browser handed back, with the secret only this app knows, for a normal session. */
    fun exchangeLink(code: String, verifier: String, keep: Boolean): SignIn {
        val body = JSONObject().put("code", code).put("verifier", verifier).put("remember", keep)
        return finish(JSONObject(call("POST", "/api/v1/auth/app-link/exchange", body)))
    }

    fun code(code: String): SignIn = finish(JSONObject(call("POST", "/api/v1/auth/mfa", JSONObject().put("code", code.trim()))))

    /** The server's own sign-in cookies for this address, to be kept (encrypted) when the person asked to stay signed in. */
    fun sessionCookies(): String {
        val handler = CookieHandler.getDefault() as? CookieManager ?: return ""
        val out = JSONArray()
        for (c in handler.cookieStore.get(URI(base))) {
            out.put(JSONObject().put("name", c.name).put("value", c.value))
        }
        return if (out.length() == 0) "" else out.toString()
    }

    /** Puts kept cookies back, then asks the server whether the session still works. Throws with code 401 when it does not. */
    fun restore(cookies: String) {
        val handler = CookieHandler.getDefault() as? CookieManager ?: return
        val uri = URI(base)
        val list = JSONArray(cookies)
        for (i in 0 until list.length()) {
            val item = list.getJSONObject(i)
            val cookie = HttpCookie(item.str("name"), item.str("value"))
            cookie.domain = uri.host
            cookie.path = "/"
            cookie.secure = true
            cookie.isHttpOnly = true
            handler.cookieStore.add(uri, cookie)
        }
        val me = JSONObject(call("GET", "/api/v1/me"))
        userId = me.str("id")
    }

    /** Tells the server to end this session. Best effort: the app forgets it either way. */
    fun signOut() {
        try {
            call("POST", "/api/v1/auth/logout", JSONObject())
        } catch (_: Exception) {
        }
    }

    private fun JSONArray?.strings(): List<String> {
        if (this == null) return emptyList()
        val out = ArrayList<String>()
        for (i in 0 until length()) { val t = optString(i, ""); if (t.isNotBlank()) out.add(t) }
        return out
    }

    /** [view] is "inbox" (still to look at), "reviewed" or "archived". */
    fun inbox(view: String = "inbox"): List<Mail> {
        val accounts = JSONArray(call("GET", "/api/v1/accounts"))
        val out = ArrayList<Mail>()
        for (i in 0 until accounts.length()) {
            val a = accounts.getJSONObject(i)
            val method = a.str("auth_method")
            if (a.optBoolean("check_address", false)) continue
            if (method != "proton_bridge" && method != "imap") continue
            if (userId.isNotEmpty() && a.str("owner_user_id") != userId) continue
            val accountId = a.str("id")
            val mailbox = a.str("display_name").ifBlank { a.str("email_address") }
            val messages = JSONArray(call("GET", "/api/v1/accounts/" + enc(accountId) + "/messages"))
            for (j in 0 until messages.length()) {
                val r = messages.getJSONObject(j)
                val state = r.str("state")
                if (view == "inbox") {
                    if (state == "reviewed" || state == "archived") continue
                } else if (state != view) {
                    continue
                }
                if (r.optBoolean("from_all_mail", false)) continue
                val snoozedUntil = r.optDouble("snoozed_until", 0.0)
                if (view == "inbox" && snoozedUntil * 1000 > System.currentTimeMillis()) continue        // snoozed: it comes back when the time is up
                val files = ArrayList<Attachment>()
                val rawFiles = r.optJSONArray("attachment_summaries")
                if (rawFiles != null) {
                    for (k in 0 until rawFiles.length()) {
                        val f = rawFiles.optJSONObject(k) ?: continue
                        val parts = ArrayList<Pair<String, String>>()
                        f.optJSONArray("parts")?.let { arr ->
                            for (q in 0 until arr.length()) arr.optJSONObject(q)?.let { parts.add(it.str("title") to it.str("text")) }
                        }
                        files.add(
                            Attachment(
                                f.optInt("index", k), f.str("filename").ifBlank { "Attachment " + (k + 1) }, f.optLong("size_bytes", 0L), f.str("summary"),
                                mime = f.str("mime_type"), state = f.str("state"), note = f.str("note"), reason = f.str("reason"),
                                parts = parts, pages = f.optInt("pages", 0),
                            ),
                        )
                    }
                }
                val received = r.optLong("received_at", 0L)
                val warnReasons = ArrayList<String>()
                r.optJSONObject("scam_warning")?.optJSONArray("reasons")?.let { arr ->
                    for (k in 0 until arr.length()) {
                        val t = arr.optJSONObject(k)?.str("text") ?: arr.optString(k)
                        if (t.isNotBlank()) warnReasons.add(t)
                    }
                }
                val unsub = r.optJSONObject("unsubscribe")
                val task = r.optJSONObject("suggested_task")
                val taskTitle = task?.str("title") ?: ""
                out.add(
                    Mail(
                        id = r.str("id"),
                        accountId = accountId,
                        sender = r.str("sender_display").ifBlank { r.str("sender_address").ifBlank { "Unknown sender" } },
                        address = r.str("sender_address"),
                        subject = r.str("subject").ifBlank { "(no subject)" },
                        summary = r.str("summary"),
                        whenText = whenText(received),
                        needsAction = r.optBoolean("action_required", false),
                        taskTitle = taskTitle.ifBlank { null },
                        taskDue = task?.str("due")?.ifBlank { null },
                        received = received,
                        tags = r.optJSONArray("tags").strings(),
                        attachments = files,
                        hasFiles = files.isNotEmpty() || r.optBoolean("has_attachments", false),
                        mailbox = mailbox,
                        state = state,
                        scamReasons = warnReasons,
                        unsubUrl = unsub?.str("url")?.ifBlank { null },
                        unsubMailto = unsub?.str("mailto")?.ifBlank { null },
                        unsubSubject = unsub?.str("subject") ?: "",
                    )
                )
            }
        }
        out.sortByDescending { it.received }
        return out
    }

    /** Whether the administrator has set up Google push, so the app can offer it. */
    fun pushAvailable(): Boolean = JSONObject(call("GET", "/api/v1/me/notifications/android")).optBoolean("available", false)

    /** Tells Enveliq this phone's Google push address. Also switches on "New email alerts" for this person. Returns the id Enveliq gave the phone. */
    fun registerPush(token: String, label: String, replaces: String?): String {
        val body = JSONObject().put("token", token).put("label", label).put("alerts", true)
        if (replaces != null) body.put("replaces", replaces)
        return JSONObject(call("POST", "/api/v1/me/notifications/android", body)).str("id")
    }

    fun testPush(id: String) {
        call("POST", "/api/v1/me/notifications/android/" + enc(id) + "/test", JSONObject())
    }

    fun unregisterPush(id: String) {
        call("DELETE", "/api/v1/me/notifications/android/" + enc(id))
    }

    /** Keeps an email out of the inbox until [untilSeconds] (a Unix time), or brings it back now when null. */
    fun snooze(mail: Mail, untilSeconds: Double?) {
        val body = JSONObject()
        if (untilSeconds == null) body.put("until", JSONObject.NULL) else body.put("until", untilSeconds)
        call("POST", "/api/v1/accounts/" + enc(mail.accountId) + "/messages/" + enc(mail.id) + "/snooze", body)
    }

    private fun JSONObject.people(key: String): List<String> {
        val a = optJSONArray(key) ?: return emptyList()
        return (0 until a.length()).map { a.optString(it) }.filter { it.isNotBlank() }
    }

    private fun sentFrom(text: String): Sent {
        val r = JSONObject(text)
        val queued = r.optBoolean("queued", false)
        val left = if (queued) (r.optDouble("send_at", 0.0) - r.optDouble("now", 0.0)).toInt().coerceAtLeast(0) else 0
        return Sent(queued, r.str("id"), left)
    }

    /** The mailboxes this person can send from (the same ones the inbox reads). */
    fun mailboxes(): List<Mailbox> {
        val accounts = JSONArray(call("GET", "/api/v1/accounts"))
        val out = ArrayList<Mailbox>()
        for (i in 0 until accounts.length()) {
            val a = accounts.getJSONObject(i)
            val method = a.str("auth_method")
            if (a.optBoolean("check_address", false)) continue
            if (method != "proton_bridge" && method != "imap") continue
            if (userId.isNotEmpty() && a.str("owner_user_id") != userId) continue
            out.add(Mailbox(a.str("id"), a.str("display_name").ifBlank { a.str("email_address") }))
        }
        return out
    }

    /** Every address the person can send from: each mailbox's own address first, then its aliases. */
    fun fromOptions(): List<FromOption> {
        val accounts = JSONArray(call("GET", "/api/v1/accounts"))
        val out = ArrayList<FromOption>()
        for (i in 0 until accounts.length()) {
            val a = accounts.getJSONObject(i)
            val method = a.str("auth_method")
            if (a.optBoolean("check_address", false)) continue
            if (method != "proton_bridge" && method != "imap") continue
            if (userId.isNotEmpty() && a.str("owner_user_id") != userId) continue
            val id = a.str("id")
            val own = a.str("email_address")
            val label = a.str("display_name").ifBlank { own }
            val seen = HashSet<String>()
            if (own.isNotBlank() && seen.add(own.lowercase())) out.add(FromOption(id, own, label, true))
            val extra = a.optJSONObject("settings")?.optJSONArray("send_identities").strings()
            extra.forEach { if (seen.add(it.lowercase())) out.add(FromOption(id, it, label, false)) }
        }
        return out
    }

    private fun filesJson(files: List<PickedFile>): JSONArray = JSONArray(files.map {
        JSONObject().put("name", it.name).put("type", it.type).put("data", android.util.Base64.encodeToString(it.bytes, android.util.Base64.NO_WRAP))
    })

    fun reply(mail: Mail, all: Boolean, text: String, from: String? = null, files: List<PickedFile> = emptyList()): Sent = sentFrom(
        call(
            "POST", "/api/v1/accounts/" + enc(mail.accountId) + "/messages/" + enc(mail.id) + "/reply",
            JSONObject().put("body", text).put("kind", if (all) "reply_all" else "reply").also { if (from != null) it.put("from_address", from) }
                .also { if (files.isNotEmpty()) it.put("files", filesJson(files)) },
        ),
    )

    fun forward(mail: Mail, to: List<String>, cc: List<String>, bcc: List<String>, text: String, from: String? = null, files: List<PickedFile> = emptyList()): Sent = sentFrom(
        call(
            "POST", "/api/v1/accounts/" + enc(mail.accountId) + "/messages/" + enc(mail.id) + "/forward",
            JSONObject().put("to", JSONArray(to)).put("cc", JSONArray(cc)).put("bcc", JSONArray(bcc)).put("body", text).also { if (from != null) it.put("from_address", from) }
                .also { if (files.isNotEmpty()) it.put("files", filesJson(files)) },
        ),
    )

    fun sendNew(accountId: String, to: List<String>, cc: List<String>, bcc: List<String>, subject: String, text: String, from: String? = null, files: List<PickedFile> = emptyList()): Sent = sentFrom(
        call(
            "POST", "/api/v1/accounts/" + enc(accountId) + "/send",
            JSONObject().put("to", JSONArray(to)).put("cc", JSONArray(cc)).put("bcc", JSONArray(bcc)).put("subject", subject).put("body", text)
                .also { if (from != null) it.put("from_address", from) }
                .also { body ->
                    if (files.isNotEmpty()) body.put("files", JSONArray(files.map {
                        JSONObject().put("name", it.name).put("type", it.type).put("data", android.util.Base64.encodeToString(it.bytes, android.util.Base64.NO_WRAP))
                    }))
                },
        ),
    )

    /** Keeps the email at the server and sends it from the person's own mailbox at [atSeconds] (Unix time). Files cannot wait. */
    fun scheduleSend(kind: String, accountId: String, messageId: String?, to: List<String>, cc: List<String>, bcc: List<String>, subject: String, text: String, from: String?, atSeconds: Double): String {
        val body = JSONObject().put("kind", kind).put("account_id", accountId).put("to", JSONArray(to)).put("cc", JSONArray(cc)).put("bcc", JSONArray(bcc))
            .put("subject", subject).put("body", text).put("send_at", atSeconds)
        if (messageId != null) body.put("message_id", messageId)
        if (from != null) body.put("from_address", from)
        return JSONObject(call("POST", "/api/v1/me/scheduled", body)).str("id")
    }

    fun waiting(): List<Waiting> {
        val arr = JSONObject(call("GET", "/api/v1/me/scheduled")).optJSONArray("items") ?: return emptyList()
        return (0 until arr.length()).mapNotNull { i ->
            val o = arr.optJSONObject(i) ?: return@mapNotNull null
            Waiting(o.str("id"), o.str("subject").ifBlank { "(no subject)" }, o.str("to"), o.optInt("people", 1), o.optDouble("send_at", 0.0).toLong(), o.str("state"), o.str("error"))
        }
    }

    fun cancelWaiting(id: String) { call("DELETE", "/api/v1/me/scheduled/" + enc(id)) }

    /** The signature the person saved on the website, or empty. */
    fun signature(): String = JSONObject(call("GET", "/api/v1/me/saved")).str("signature")

    /** Takes back an email that is still waiting out its "undo send" time. */
    fun cancelSend(outboxId: String) {
        call("DELETE", "/api/v1/me/outbox/" + enc(outboxId))
    }

    /** People from the address list whose name or address contains [q]. */
    fun contacts(q: String): List<Contact> {
        val items = JSONObject(call("GET", "/api/v1/me/contacts?q=" + enc(q))).optJSONArray("items") ?: return emptyList()
        return (0 until items.length()).map { items.getJSONObject(it) }.map { Contact(it.str("name"), it.str("address")) }.filter { it.address.isNotBlank() }
    }

    private fun draftFrom(r: JSONObject) = Draft(
        id = r.str("id"), kind = r.str("kind"), accountId = r.str("account_id"), messageId = r.str("message_id"),
        to = r.people("to"), cc = r.people("cc"), bcc = r.people("bcc"), subject = r.str("subject"), body = r.str("body"),
        fromAddress = r.str("from_address"),
    )

    fun drafts(): List<Draft> {
        val items = JSONObject(call("GET", "/api/v1/me/drafts")).optJSONArray("items") ?: return emptyList()
        return (0 until items.length()).map { draftFrom(items.getJSONObject(it)) }
    }

    /** Creates a draft (when [id] is null) or replaces one. */
    fun saveDraft(id: String?, d: Draft): Draft {
        val body = JSONObject().put("kind", d.kind).put("to", JSONArray(d.to)).put("cc", JSONArray(d.cc)).put("bcc", JSONArray(d.bcc))
            .put("subject", d.subject).put("body", d.body)
        if (d.accountId.isNotBlank()) body.put("account_id", d.accountId)
        if (d.messageId.isNotBlank()) body.put("message_id", d.messageId)
        if (d.fromAddress.isNotBlank()) body.put("from_address", d.fromAddress)
        val text = if (id == null) call("POST", "/api/v1/me/drafts", body) else call("PUT", "/api/v1/me/drafts/" + enc(id), body)
        return draftFrom(JSONObject(text))
    }

    fun deleteDraft(id: String) {
        call("DELETE", "/api/v1/me/drafts/" + enc(id))
    }

    /** The addresses on the person's important list, in lower case. */
    fun importantAddresses(): Set<String> {
        val items = JSONObject(call("GET", "/api/v1/me/important")).optJSONArray("items") ?: return emptySet()
        return (0 until items.length()).map { items.getJSONObject(it).str("address").lowercase() }.filter { it.isNotBlank() }.toSet()
    }

    /** Puts the unread mark back on an email that was marked Reviewed. */
    fun markUnread(mail: Mail) {
        call("POST", "/api/v1/accounts/" + enc(mail.accountId) + "/messages/" + enc(mail.id) + "/unread")
    }

    /** Where the person is signed in. */
    fun devices(): List<DeviceInfo> {
        val items = JSONObject(call("GET", "/api/v1/auth/devices")).optJSONArray("items") ?: return emptyList()
        return (0 until items.length()).map {
            val o = items.getJSONObject(it)
            DeviceInfo(o.str("id"), o.str("label").ifBlank { "A device" }, o.optDouble("signed_in_at", 0.0).toLong(), o.optBoolean("current", false))
        }
    }

    fun signDeviceOut(id: String) {
        call("DELETE", "/api/v1/auth/devices/" + enc(id))
    }

    /** The newest published release as (version, page address), or null when the server has none to offer. */
    fun latestRelease(): Pair<String, String>? {
        val latest = JSONObject(call("GET", "/api/v1/app-update")).optJSONObject("latest") ?: return null
        val v = latest.str("version")
        val u = latest.str("url")
        return if (v.isBlank() || !u.startsWith("https://github.com/")) null else v to u
    }

    /** Fetches the newest app from the person's own server (which checked it against its published checksum) into [dest]. Returns whether the file matches the checksum the server named. */
    fun downloadUpdate(dest: java.io.File): Boolean {
        val conn = URL(base + "/api/v1/app-update/apk").openConnection() as HttpURLConnection
        try {
            conn.connectTimeout = 15000
            conn.readTimeout = 120000
            val code = conn.responseCode
            if (code >= 400) {
                val text = conn.errorStream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() } ?: ""
                throw ApiException(detail(text, code), code)
            }
            val expected = conn.getHeaderField("X-Enveliq-Sha256")?.lowercase() ?: ""
            val digest = java.security.MessageDigest.getInstance("SHA-256")
            conn.inputStream.use { input ->
                dest.outputStream().use { out ->
                    val buf = ByteArray(64 * 1024)
                    while (true) {
                        val n = input.read(buf)
                        if (n < 0) break
                        digest.update(buf, 0, n)
                        out.write(buf, 0, n)
                    }
                }
            }
            return expected.length == 64 && digest.digest().joinToString("") { "%02x".format(it) } == expected
        } catch (e: ApiException) {
            throw e
        } catch (e: IOException) {
            throw ApiException("The download did not finish. Check your connection and try again.")
        } finally {
            conn.disconnect()
        }
    }

    // ---------- beyond email: tasks, bell, shipping, trips, news and messages ----------

    private fun JSONObject.list(key: String): List<JSONObject> {
        val a = optJSONArray(key) ?: return emptyList()
        return (0 until a.length()).mapNotNull { a.optJSONObject(it) }
    }

    fun myTasks(): List<MyTask> = JSONObject(call("GET", "/api/v1/me/tasks?tz=" + enc(java.util.TimeZone.getDefault().id))).list("tasks").map {
        MyTask(it.str("id"), it.str("account_id"), it.str("message_id"), it.str("title"), it.str("sender"), it.str("priority"), it.str("due"),
            it.optInt("days", 0), it.str("state"), it.optBoolean("manual", false))
    }

    /** Adds a task of your own for this email. [on] is a date, YYYY-MM-DD. */
    fun addTask(mail: Mail, title: String, on: String) {
        call("POST", "/api/v1/me/tasks", JSONObject().put("account_id", mail.accountId).put("message_id", mail.id).put("title", title).put("on", on))
    }

    /** action: done, reopen, remove, not_today, or move (with [to] one of later_today, tomorrow, weekend, next_week). */
    fun taskAct(id: String, action: String, to: String? = null) {
        val body = if (to != null) JSONObject().put("to", to) else null
        call("POST", "/api/v1/me/tasks/" + enc(id) + "/" + action, body)
    }

    fun bell(): List<BellNote> = JSONObject(call("GET", "/api/v1/me/bell")).list("items").map {
        BellNote(it.str("id"), it.str("title"), it.str("message"), it.str("source"), it.optDouble("at", 0.0).toLong(), it.optBoolean("unread", false))
    }
    fun bellRead() { call("POST", "/api/v1/me/bell/read") }
    fun bellDismiss(id: String) { call("DELETE", "/api/v1/me/bell/" + enc(id)) }
    fun bellClear() { call("DELETE", "/api/v1/me/bell") }

    fun shipping(): Section<Order> {
        val r = JSONObject(call("GET", "/api/v1/me/shipping"))
        return Section(r.optBoolean("enabled", false), r.list("orders").map {
            Order(it.str("id"), it.str("shop"), it.str("items"), it.str("status"), it.str("expected_text").ifBlank { it.str("expected") },
                it.optBoolean("delayed", false), it.optDouble("delivered_at", 0.0) > 0, it.optBoolean("needs_confirm", false), it.str("track_url"))
        })
    }

    fun trips(): Section<Trip> {
        val r = JSONObject(call("GET", "/api/v1/me/trips"))
        return Section(r.optBoolean("enabled", false), r.list("trips").map { t ->
            Trip(t.str("title"), t.str("start"), t.str("end"), t.str("state"), t.optBoolean("cancelled", false), t.list("bookings").map { b ->
                Booking(b.str("kind"), b.str("provider"), b.str("detail"), b.str("from"), b.str("to"), b.str("start"), b.str("start_time"), b.str("reference"), b.str("status") == "cancelled")
            })
        })
    }

    private fun feedsOf(r: JSONObject): Section<Feed> = Section(r.optBoolean("enabled", false), r.list("feeds").map { f ->
        Feed(f.str("id"), f.str("title"), f.str("error"), f.optInt("new", 0), f.list("items").map { i ->
            FeedItem(i.str("title"), i.str("text"), i.str("link"), i.optDouble("at", 0.0).toLong(), i.optBoolean("new", false))
        })
    })
    fun news(): Section<Feed> = feedsOf(JSONObject(call("GET", "/api/v1/me/rss")))
    fun newsRefresh(): Section<Feed> = feedsOf(JSONObject(call("POST", "/api/v1/me/rss/refresh")))
    fun newsSeen() { call("POST", "/api/v1/me/rss/seen") }

    fun threads(): List<Chat> = JSONObject(call("GET", "/api/v1/messages/threads")).list("threads").map {
        val last = it.optJSONObject("last")
        Chat(it.str("id"), it.str("title"), it.optInt("unread", 0), if (last == null) "" else (if (last.optBoolean("mine", false)) "You: " else "") + last.str("text"),
            it.optDouble("updated", 0.0).toLong(), it.optBoolean("muted", false))
    }

    fun thread(id: String): List<ChatMessage> {
        val msgs = JSONObject(call("GET", "/api/v1/messages/threads/" + enc(id))).list("messages").map {
            ChatMessage(it.str("id"), it.str("name"), it.optBoolean("mine", false), it.optDouble("at", 0.0).toLong(), it.str("text"), it.optBoolean("deleted", false))
        }
        try { call("POST", "/api/v1/messages/threads/" + enc(id) + "/read") } catch (e: ApiException) { /* not worth failing the page */ }
        return msgs
    }

    fun sendChat(id: String, text: String) { call("POST", "/api/v1/messages/threads/" + enc(id) + "/messages", JSONObject().put("text", text)) }

    /** Asks the address whether it is an Enveliq that answers. Throws a plain-words [ApiException] when it does not. */
    fun checkConnection() {
        val r = JSONObject(call("GET", "/api/v1/health"))
        if (!r.optBoolean("ok", false)) throw ApiException("That address answered, but it does not look like Enveliq.")
    }

    /** The tags this mailbox has, or null when its mail service does not keep tags (or tags are switched off). */
    /** The tags this mailbox offers, or null when the mail service does not keep tags. Any other problem is thrown, so it can be said plainly. */
    fun tagInfo(accountId: String): TagInfo? {
        val r = JSONObject(call("GET", "/api/v1/accounts/" + enc(accountId) + "/tags"))
        return if (!r.optBoolean("supported", false)) null else TagInfo(r.optJSONArray("names").strings(), r.optBoolean("can_create", false))
    }

    fun createTag(accountId: String, name: String) {
        call("POST", "/api/v1/accounts/" + enc(accountId) + "/tags", JSONObject().put("name", name))
    }

    /** Puts a tag on the email or takes it off. Gives back the email's tags as they are now. */
    fun setTag(mail: Mail, name: String, on: Boolean): List<String> {
        val r = JSONObject(call("PUT", "/api/v1/accounts/" + enc(mail.accountId) + "/messages/" + enc(mail.id) + "/tags", JSONObject().put("name", name).put("on", on)))
        return r.optJSONArray("tags").strings()
    }

    /** A file from the email, fetched from the mailbox for this one request. The app does not keep it. */
    fun download(mail: Mail, index: Int, preview: Boolean = false): ByteArray {
        val conn = URL(base + "/api/v1/accounts/" + enc(mail.accountId) + "/messages/" + enc(mail.id) + "/attachments/" + index + (if (preview) "?preview=true" else "")).openConnection() as HttpURLConnection
        try {
            conn.connectTimeout = 15000
            conn.readTimeout = 60000
            val code = conn.responseCode
            if (code >= 400) {
                val text = conn.errorStream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() } ?: ""
                throw ApiException(detail(text, code), code)
            }
            return conn.inputStream.use { it.readBytes() }
        } catch (e: ApiException) {
            throw e
        } catch (e: IOException) {
            throw ApiException("Could not get the file. Check your connection and try again.")
        } finally {
            conn.disconnect()
        }
    }

    /** A readable copy of a file (PDF pages as pictures, a table, or text), made by the server in memory. Nothing is kept. Same route as the website's viewer. */
    fun viewAttachment(mail: Mail, index: Int): JSONObject =
        JSONObject(call("GET", "/api/v1/accounts/" + enc(mail.accountId) + "/messages/" + enc(mail.id) + "/attachments/" + index + "/view"))

    /** Who is signed in (name and picture version), for the top bar. */
    fun me(): Me {
        val o = JSONObject(call("GET", "/api/v1/me"))
        val name = o.str("display_name").ifBlank { o.str("username") }
        val initials = name.split(Regex("\\s+")).mapNotNull { it.firstOrNull()?.toString() }.joinToString("").take(2).uppercase().ifBlank { "?" }
        return Me(o.str("id"), name, initials, o.str("avatar_v"))
    }

    /** The person's own picture, or null when they have none. */
    fun avatar(me: Me): ByteArray? {
        if (me.avatarVersion.isBlank()) return null
        val conn = URL(base + "/api/v1/users/" + enc(me.id) + "/avatar?v=" + enc(me.avatarVersion)).openConnection() as HttpURLConnection
        return try {
            conn.connectTimeout = 15000
            conn.readTimeout = 30000
            if (conn.responseCode >= 400) null else conn.inputStream.use { it.readBytes() }
        } catch (_: Exception) {
            null
        } finally {
            conn.disconnect()
        }
    }

    fun findStart(query: String, includeJunk: Boolean): FindProgress =
        findProgressOf(JSONObject(call("POST", "/api/v1/find/searches", JSONObject().put("query", query).put("include_junk", includeJunk))))

    fun findProgress(id: String): FindProgress = findProgressOf(JSONObject(call("GET", "/api/v1/find/searches/" + enc(id))))

    private fun findProgressOf(r: JSONObject): FindProgress {
        val notes = ArrayList<String>()
        val boxes = r.optJSONArray("mailboxes")
        if (boxes != null) for (i in 0 until boxes.length()) {
            val m = boxes.optJSONObject(i) ?: continue
            if (m.str("message").isNotBlank()) notes.add(m.str("label") + ": " + m.str("message"))
        }
        return FindProgress(r.str("id"), r.optBoolean("done", false) || r.optBoolean("cancelled", false), r.optInt("listed", 0), notes)
    }

    /** One page (25) of results. Returns the rows and whether there are more. */
    fun findPage(id: String, offset: Int): Pair<List<FoundRow>, Boolean> {
        val r = JSONObject(call("GET", "/api/v1/find/searches/" + enc(id) + "/results?offset=" + offset))
        val arr = r.optJSONArray("rows")
        val rows = ArrayList<FoundRow>()
        if (arr != null) for (i in 0 until arr.length()) {
            val o = arr.optJSONObject(i) ?: continue
            rows.add(FoundRow(o.str("token"), o.str("from_name").ifBlank { o.str("from_address") }, o.str("subject"), o.str("date"), o.str("account"), o.str("folder")))
        }
        return rows to r.optBoolean("more", false)
    }

    fun findCancel(id: String) {
        try { call("DELETE", "/api/v1/find/searches/" + enc(id)) } catch (e: Exception) { }
    }

    /** The plain text of a found email. Fetched now and not kept. */
    fun findOriginal(token: String): String =
        JSONObject(call("GET", "/api/v1/find/results/" + enc(token) + "/original")).str("text").ifBlank { "(no text content)" }

    /** From now on, new email from this address goes straight to the mailbox's Junk folder. The server keeps important people safe. */
    fun blockSender(address: String) {
        call("POST", "/api/v1/me/rules", JSONObject().put("sender", address).put("subject", "").put("action", "junked"))
    }

    /** The rules this person has made: id, what to match, and what happens. */
    fun rules(): List<Rule> {
        val arr = JSONObject(call("GET", "/api/v1/me/rules")).optJSONArray("rules") ?: return emptyList()
        return (0 until arr.length()).mapNotNull { i ->
            val r = arr.optJSONObject(i) ?: return@mapNotNull null
            Rule(r.str("id"), r.str("sender"), r.str("subject"), r.str("action"))
        }
    }

    fun deleteRule(id: String) {
        call("DELETE", "/api/v1/me/rules/" + enc(id))
    }

    fun resolve(mail: Mail, outcome: Outcome) {
        call(
            "POST",
            "/api/v1/accounts/" + enc(mail.accountId) + "/messages/" + enc(mail.id) + "/resolve",
            JSONObject().put("outcome", outcome.api),
        )
    }

    /** The email as the server describes it: its plain text, and whether a formatted (HTML) version exists. */
    fun originalInfo(mail: Mail): OriginalInfo {
        val r = JSONObject(call("GET", "/api/v1/accounts/" + enc(mail.accountId) + "/messages/" + enc(mail.id) + "/original"))
        return OriginalInfo(r.str("text").ifBlank { "(no text content)" }, r.optBoolean("has_html", false), r.optInt("remote_images", 0))
    }

    /** The email as its sender formatted it, rebuilt by the server from allowed parts only. Pictures from the internet come only when [images] is true. */
    fun originalHtml(mail: Mail, images: Boolean): String {
        val url = base + "/api/v1/accounts/" + enc(mail.accountId) + "/messages/" + enc(mail.id) + "/original/html" + if (images) "?images=true" else ""
        val conn = URL(url).openConnection() as HttpURLConnection
        try {
            conn.connectTimeout = 15000
            conn.readTimeout = 60000
            val code = conn.responseCode
            if (code >= 400) {
                val text = conn.errorStream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() } ?: ""
                throw ApiException(if (code == 404) "This email has no formatted version." else detail(text, code), code)
            }
            return conn.inputStream.bufferedReader(Charsets.UTF_8).use { it.readText() }
        } catch (e: ApiException) {
            throw e
        } catch (e: IOException) {
            throw ApiException("Could not open the email. Check your connection and try again.")
        } finally {
            conn.disconnect()
        }
    }

    /** The email's own words as plain text, fetched from the mailbox for this one request. Not stored. */
    fun originalText(mail: Mail): String {
        val r = JSONObject(call("GET", "/api/v1/accounts/" + enc(mail.accountId) + "/messages/" + enc(mail.id) + "/original"))
        return r.str("text").ifBlank { "(no text content)" }
    }
}
