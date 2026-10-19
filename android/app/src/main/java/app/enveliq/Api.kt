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
            else -> "The request was not accepted (HTTP $code)."
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

    fun inbox(): List<Mail> {
        val accounts = JSONArray(call("GET", "/api/v1/accounts"))
        val out = ArrayList<Mail>()
        for (i in 0 until accounts.length()) {
            val a = accounts.getJSONObject(i)
            val method = a.str("auth_method")
            if (a.optBoolean("check_address", false)) continue
            if (method != "proton_bridge" && method != "imap") continue
            if (userId.isNotEmpty() && a.str("owner_user_id") != userId) continue
            val accountId = a.str("id")
            val messages = JSONArray(call("GET", "/api/v1/accounts/" + enc(accountId) + "/messages"))
            for (j in 0 until messages.length()) {
                val r = messages.getJSONObject(j)
                val state = r.str("state")
                if (state == "reviewed" || state == "archived") continue
                if (r.optBoolean("from_all_mail", false)) continue
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

    fun resolve(mail: Mail, outcome: Outcome) {
        call(
            "POST",
            "/api/v1/accounts/" + enc(mail.accountId) + "/messages/" + enc(mail.id) + "/resolve",
            JSONObject().put("outcome", outcome.api),
        )
    }

    /** The email's own words as plain text, fetched from the mailbox for this one request. Not stored. */
    fun originalText(mail: Mail): String {
        val r = JSONObject(call("GET", "/api/v1/accounts/" + enc(mail.accountId) + "/messages/" + enc(mail.id) + "/original"))
        return r.str("text").ifBlank { "(no text content)" }
    }
}
