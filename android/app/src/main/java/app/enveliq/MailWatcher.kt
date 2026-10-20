package app.enveliq

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.ConnectivityManager
import android.net.Network
import android.os.Build
import android.os.IBinder
import java.net.CookieHandler
import java.net.CookieManager
import java.net.HttpURLConnection
import java.net.URL
import java.util.Calendar
import javax.net.ssl.SSLException

/** The person's choices for new-email alerts. Only switches and times: no email is ever kept here. */
object AlertPrefs {
    private const val FILE = "enveliq"
    private fun prefs(c: Context) = c.getSharedPreferences(FILE, Context.MODE_PRIVATE)

    fun on(c: Context) = prefs(c).getBoolean("mail_alerts", false)
    fun setOn(c: Context, v: Boolean) = prefs(c).edit().putBoolean("mail_alerts", v).apply()
    /** Which new email gets an alert: "all", "action" (only emails that need action) or "important" (only from people on the important list). */
    fun scope(c: Context): String = prefs(c).getString("alert_scope", "all") ?: "all"
    fun setScope(c: Context, v: String) = prefs(c).edit().putString("alert_scope", v).apply()
    fun quietOn(c: Context) = prefs(c).getBoolean("quiet_on", false)
    fun setQuietOn(c: Context, v: Boolean) = prefs(c).edit().putBoolean("quiet_on", v).apply()
    /** Minutes after midnight. */
    fun quietFrom(c: Context) = prefs(c).getInt("quiet_from", 22 * 60)
    fun quietTo(c: Context) = prefs(c).getInt("quiet_to", 7 * 60)
    fun setQuiet(c: Context, from: Int, to: Int) = prefs(c).edit().putInt("quiet_from", from).putInt("quiet_to", to).apply()

    fun inQuietHours(c: Context, now: Calendar = Calendar.getInstance()): Boolean {
        if (!quietOn(c)) return false
        val minute = now.get(Calendar.HOUR_OF_DAY) * 60 + now.get(Calendar.MINUTE)
        val from = quietFrom(c)
        val to = quietTo(c)
        return if (from == to) false else if (from < to) minute in from until to else minute >= from || minute < to
    }

    /** Which emails have already had an alert: only their ids, so one email is never announced twice. */
    fun alerted(c: Context): MutableSet<String> =
        prefs(c).getString("alerted", "")!!.split('\n').filter { it.isNotEmpty() }.toMutableSet()

    fun setAlerted(c: Context, ids: Collection<String>) =
        prefs(c).edit().putString("alerted", ids.toList().takeLast(400).joinToString("\n")).apply()

    fun seeded(c: Context) = prefs(c).getBoolean("alerted_seeded", false)
    fun setSeeded(c: Context, v: Boolean) = prefs(c).edit().putBoolean("alerted_seeded", v).apply()

    /** How alerts reach the phone: "direct" (the app keeps its own connection) or "google" (Google's push service wakes it). */
    fun mode(c: Context): String = prefs(c).getString("alert_mode", "direct") ?: "direct"
    fun setMode(c: Context, v: String) = prefs(c).edit().putString("alert_mode", v).apply()

    /** The id Enveliq gave this phone when it signed up for Google push (not Google's own address). */
    fun pushDevice(c: Context): String? = prefs(c).getString("push_device", null)
    fun setPushDevice(c: Context, id: String?) = prefs(c).edit().putString("push_device", id).apply()

    /** Signing out forgets everything about alerts, so a different sign-in starts clean. */
    fun reset(c: Context) {
        setOn(c, false)
        setSeeded(c, false)
        setAlerted(c, emptyList())
        setMode(c, "direct")
        setPushDevice(c, null)
        otherKinds.forEach { setKind(c, it.first, false) }
    }

    /** Other things worth a quiet note, each off until the person turns it on: "messages", "bell", "tasks", "shipping". */
    val otherKinds = listOf(
        "messages" to ("Messages" to "A note when someone sends you a message in Enveliq."),
        "bell" to ("Notes and alerts" to "A note when something new appears under the bell."),
        "tasks" to ("Tasks due today" to "A note when a task becomes due."),
        "shipping" to ("Parcels to confirm" to "A note when a parcel needs you to confirm it arrived."),
        "summary" to ("Daily summary" to "A note each morning with what is waiting for you."),
    )
    fun kindOn(c: Context, kind: String) = prefs(c).getBoolean("alert_kind_$kind", false)
    fun setKind(c: Context, kind: String, v: Boolean) = prefs(c).edit().putBoolean("alert_kind_$kind", v).apply()

    fun timeText(minutes: Int): String = "%02d:%02d".format(minutes / 60, minutes % 60)
}

/**
 * Keeps one quiet connection to the person's own Enveliq so a new email can be announced as soon as its AI summary is done.
 *
 * Built to be light on the battery:
 *  - one connection, no polling: the server sends a one-line heartbeat once a minute and the app does nothing in between;
 *  - while the phone has no network the app does not try at all, and it reconnects the moment a network returns;
 *  - after a failure it waits longer each time (15 seconds up to 5 minutes) instead of retrying hard;
 *  - the email list is only fetched when the server says something new is ready.
 */
class MailWatcherService : Service() {
    private val wake = java.util.concurrent.LinkedBlockingQueue<Unit>()
    @Volatile private var running = false
    @Volatile private var online = true
    @Volatile private var connection: HttpURLConnection? = null
    private var worker: Thread? = null
    private var callback: ConnectivityManager.NetworkCallback? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // Android insists that a service started as a foreground service says so straight away, so this comes first.
        Notifier.ensureChannels(this)
        val note = Notification.Builder(this, Notifier.CHANNEL_WATCH)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle("Enveliq is watching for new email")
            .setContentText("Quietly. Turn this off in Settings, New email alerts.")
            .setOngoing(true)
            .build()
        try {
            if (Build.VERSION.SDK_INT >= 34) startForeground(Notifier.WATCH_ID, note, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
            else startForeground(Notifier.WATCH_ID, note)
            if (!AlertPrefs.on(this) || AlertPrefs.mode(this) != "direct" || SessionVault.load(this) == null) {
                stopSelf()
                return START_NOT_STICKY
            }
            if (!running) {
                running = true
                watchNetwork()
                worker = Thread({ loop() }, "enveliq-watch").also { it.start() }
            }
        } catch (e: Exception) {
            // Alerts must never stop the app from opening: switch them off and say so, instead of crashing.
            running = false
            AlertPrefs.setOn(this, false)
            Notifier.simple(this, 2004, "New-email alerts are off", "Enveliq could not keep watching for new email on this phone. Open Settings in Enveliq to try again.")
            stopSelf()
            return START_NOT_STICKY
        }
        return START_STICKY
    }

    override fun onDestroy() {
        running = false
        callback?.let { (getSystemService(ConnectivityManager::class.java)).unregisterNetworkCallback(it) }
        connection?.disconnect()
        wake.offer(Unit)
        super.onDestroy()
    }

    private fun watchNetwork() {
        val manager = getSystemService(ConnectivityManager::class.java)
        online = try { manager.activeNetwork != null } catch (_: SecurityException) { true }
        val cb = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) {
                online = true
                wake.offer(Unit)
            }

            override fun onLost(network: Network) {
                online = manager.activeNetwork != null
                if (!online) connection?.disconnect()
            }
        }
        callback = cb
        manager.registerDefaultNetworkCallback(cb)
    }

    private fun pause(seconds: Long) {
        wake.poll(seconds, java.util.concurrent.TimeUnit.SECONDS)
    }

    private fun loop() {
        try {
            watch()
        } catch (_: Throwable) {
            AlertPrefs.setOn(this, false)
        }
        stopSelf()
    }

    private fun watch() {
        var wait = 15L
        while (running) {
            if (!AlertPrefs.on(this) || AlertPrefs.mode(this) != "direct") break
            if (!online) {                     // no network: sleep until the network callback wakes us
                wake.poll(30, java.util.concurrent.TimeUnit.MINUTES)
                continue
            }
            val kept = SessionVault.load(this)
            if (kept == null) break
            val started = System.currentTimeMillis()
            try {
                val api = EnveliqApi(kept.first)
                api.restore(kept.second)
                Alerts.catchUp(this, api)
                listen(api, kept.first)
            } catch (e: ApiException) {
                if (e.code == 401) {
                    Alerts.signedOut(this)
                    break
                }
            } catch (_: Exception) {
            }
            if (!running) break
            wait = if (System.currentTimeMillis() - started > 60_000) 15L else minOf(wait * 2, 300L)
            pause(wait)
        }
    }

    private fun listen(api: EnveliqApi, server: String) {
        val conn = URL(EnveliqApi.normalise(server) + "/api/v1/me/new-mail-events").openConnection() as HttpURLConnection
        connection = conn
        try {
            conn.connectTimeout = 15000
            conn.readTimeout = 150_000                   // the server sends a line every minute; silence for this long means the connection is dead
            conn.setRequestProperty("Accept", "text/event-stream")
            val code = conn.responseCode
            if (code == 401 || code == 403) throw ApiException("signed out", 401)
            if (code >= 400) throw ApiException("The server did not accept the connection.", code)
            var event = ""
            var data = ""
            conn.inputStream.bufferedReader(Charsets.UTF_8).use { reader ->
                while (running) {
                    val line = reader.readLine() ?: break
                    if (line.startsWith("event:")) event = line.substring(6).trim()
                    else if (line.startsWith("data:")) data = line.substring(5).trim()
                    else if (line.isEmpty()) {
                        if (event == "new") Alerts.catchUp(this, api)
                        if (event == "gone") Alerts.gone(this, data)
                        if (event == "other") Alerts.other(this, data, api)
                        if (event == "reconnect") break
                        event = ""
                        data = ""
                    }
                }
            }
        } catch (e: SSLException) {
            throw ApiException("certificate")
        } finally {
            conn.disconnect()
            connection = null
        }
    }

    companion object {
        fun start(context: Context) {
            try {
                if (AlertPrefs.on(context) && AlertPrefs.mode(context) == "direct" && SessionVault.load(context) != null) context.startForegroundService(Intent(context, MailWatcherService::class.java))
            } catch (_: Exception) {
                // Android may refuse to start it right now (for example from the background). The next time the app opens will try again.
            }
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, MailWatcherService::class.java))
        }
    }
}

/** Starts the watcher again after the phone restarts or the app is updated, if the person has alerts on. */
class WatcherStarter : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED || intent.action == Intent.ACTION_MY_PACKAGE_REPLACED) MailWatcherService.start(context)
    }
}

/** What the app does when it learns that new email may be ready, however it learned it (its own connection, or Google's push). */
object Alerts {
    /** Looks at the inbox once and announces any email that is ready and has not had an alert yet. */
    fun catchUp(context: Context, api: EnveliqApi) {
        val mails = api.inbox()
        val alerted = AlertPrefs.alerted(context)
        if (!AlertPrefs.seeded(context)) {              // first time: what is already there is not new
            AlertPrefs.setAlerted(context, mails.map { it.id })
            AlertPrefs.setSeeded(context, true)
            return
        }
        Notifier.clearGone(context, mails.map { it.id }, alerted)       // reviewed somewhere else: take its alert down
        val fresh = mails.filter { it.id !in alerted }
        if (fresh.isEmpty()) return
        alerted.addAll(fresh.map { it.id })
        AlertPrefs.setAlerted(context, alerted)
        // Everything new is remembered as announced, but only what the person asked to hear about makes a sound.
        // When the person chose "new email in the daily summary instead", only their important people are announced one by one.
        val digest = try { api.dailySummary().optBoolean("digest", false) } catch (e: ApiException) { if (e.code == 401) throw e else false }
        val toTell = when (if (digest) "important" else AlertPrefs.scope(context)) {
            "action" -> fresh.filter { it.needsAction }
            "important" -> {
                val people = try { api.importantAddresses() } catch (e: ApiException) { if (e.code == 401) throw e else emptySet() }
                fresh.filter { it.address.lowercase() in people }
            }
            else -> fresh
        }
        if (toTell.isEmpty()) return
        Notifier.newMail(context, toTell, AlertPrefs.inQuietHours(context))
    }

    /** The server says more messages, notes, tasks or parcels are waiting. It sends only which kinds, never any words. */
    fun other(context: Context, data: String, api: EnveliqApi? = null) {
        try {
            val kinds = org.json.JSONObject(data).optJSONArray("kinds") ?: return
            val names = AlertPrefs.otherKinds.toMap()
            for (i in 0 until kinds.length()) {
                val kind = kinds.optString(i)
                if (!AlertPrefs.kindOn(context, kind)) continue
                if (kind == "summary") {
                    val text = (if (api != null) summaryText(api) else null) ?: continue
                    Notifier.other(context, kind, text, AlertPrefs.inQuietHours(context))
                    continue
                }
                val text = names[kind]?.second ?: continue
                Notifier.other(context, kind, text, AlertPrefs.inQuietHours(context))
            }
        } catch (_: Exception) {
        }
    }

    /** One plain line made from the daily summary's numbers, for example "2 tasks due · 1 parcel out for delivery". No names, no subjects. Null when there is nothing to say. */
    private fun summaryText(api: EnveliqApi): String? {
        val s = try { api.dailySummary() } catch (_: Exception) { return null }
        fun n(key: String, one: String, many: String): String? = s.optInt(key, 0).let { if (it <= 0) null else "$it ${if (it == 1) one else many}" }
        val parts = listOfNotNull(
            n("tasks", "task due", "tasks due"), n("unread", "unread email", "unread emails"), n("waiting", "reply still waited for", "replies still waited for"),
            n("parcels", "parcel out for delivery", "parcels out for delivery"), n("coming", "subscription coming up", "subscriptions coming up"),
        )
        return if (parts.isEmpty()) null else parts.joinToString(" · ")
    }

    /** The server says these emails are no longer waiting (reviewed or moved somewhere else): take their alerts down at once. */
    fun gone(context: Context, data: String) {
        try {
            val ids = org.json.JSONObject(data).optJSONArray("ids") ?: return
            val manager = context.getSystemService(android.app.NotificationManager::class.java)
            for (i in 0 until ids.length()) {
                val id = ids.optJSONObject(i)?.optString("m", "") ?: ""
                if (id.isEmpty()) continue
                Notifier.clearOne(context, id)
            }
            if (manager.activeNotifications.none { it.id >= 3000 && it.id < 3000 + 0x10000 }) manager.cancel(Notifier.GROUP_ID)
        } catch (_: Exception) {
        }
    }

    /** Signs in with the kept session and checks once. Used when Google's push wakes the app. Never throws. */
    fun checkNow(context: Context) {
        val kept = SessionVault.load(context) ?: return
        try {
            val api = EnveliqApi(kept.first)
            api.restore(kept.second)
            catchUp(context, api)
        } catch (e: ApiException) {
            if (e.code == 401) signedOut(context)
        } catch (_: Exception) {
        }
    }

    /** The server ended our session: say so once, plainly, and stop. */
    fun signedOut(context: Context) {
        SessionVault.clear(context)
        AlertPrefs.reset(context)
        Notifier.simple(context, 2003, "Please sign in to Enveliq again", "Your new-email alerts stopped because you were signed out. Open Enveliq to sign in and turn them back on.")
    }
}
