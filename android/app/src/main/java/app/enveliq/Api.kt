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
                val rawFiles = r.optJSONArray("attachments")
                if (rawFiles != null) {
                    for (k in 0 until rawFiles.length()) {
                        val f = rawFiles.optJSONObject(k) ?: continue
                        files.add(Attachment(f.optInt("index", k), f.str("filename").ifBlank { "Attachment " + (k + 1) }, f.optLong("size_bytes", 0L), f.str("summary")))
                    }
                }
                val received = r.optLong("received_at", 0L)
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
                        mailbox = mailbox,
                        state = state,
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

    fun reply(mail: Mail, all: Boolean, text: String, from: String? = null): Sent = sentFrom(
        call(
            "POST", "/api/v1/accounts/" + enc(mail.accountId) + "/messages/" + enc(mail.id) + "/reply",
            JSONObject().put("body", text).put("kind", if (all) "reply_all" else "reply").also { if (from != null) it.put("from_address", from) },
        ),
    )

    fun forward(mail: Mail, to: List<String>, cc: List<String>, bcc: List<String>, text: String, from: String? = null): Sent = sentFrom(
        call(
            "POST", "/api/v1/accounts/" + enc(mail.accountId) + "/messages/" + enc(mail.id) + "/forward",
            JSONObject().put("to", JSONArray(to)).put("cc", JSONArray(cc)).put("bcc", JSONArray(bcc)).put("body", text).also { if (from != null) it.put("from_address", from) },
        ),
    )

    fun sendNew(accountId: String, to: List<String>, cc: List<String>, bcc: List<String>, subject: String, text: String, from: String? = null): Sent = sentFrom(
        call(
            "POST", "/api/v1/accounts/" + enc(accountId) + "/send",
            JSONObject().put("to", JSONArray(to)).put("cc", JSONArray(cc)).put("bcc", JSONArray(bcc)).put("subject", subject).put("body", text)
                .also { if (from != null) it.put("from_address", from) },
        ),
    )

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

    /** Asks the address whether it is an Enveliq that answers. Throws a plain-words [ApiException] when it does not. */
    fun checkConnection() {
        val r = JSONObject(call("GET", "/api/v1/health"))
        if (!r.optBoolean("ok", false)) throw ApiException("That address answered, but it does not look like Enveliq.")
    }

    /** The tags this mailbox has, or null when its mail service does not keep tags (or tags are switched off). */
    fun tagInfo(accountId: String): TagInfo? = try {
        val r = JSONObject(call("GET", "/api/v1/accounts/" + enc(accountId) + "/tags"))
        if (!r.optBoolean("supported", false)) null else TagInfo(r.optJSONArray("names").strings(), r.optBoolean("can_create", false))
    } catch (e: ApiException) {
        if (e.code == 401) throw e
        null
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
    fun download(mail: Mail, index: Int): ByteArray {
        val conn = URL(base + "/api/v1/accounts/" + enc(mail.accountId) + "/messages/" + enc(mail.id) + "/attachments/" + index).openConnection() as HttpURLConnection
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
