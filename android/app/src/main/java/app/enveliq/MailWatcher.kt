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

    /** Signing out forgets everything about alerts, so a different sign-in starts clean. */
    fun reset(c: Context) {
        setOn(c, false)
        setSeeded(c, false)
        setAlerted(c, emptyList())
    }

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
            if (!AlertPrefs.on(this) || SessionVault.load(this) == null) {
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
            if (!AlertPrefs.on(this)) break
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
                catchUp(api)
                listen(api, kept.first)
            } catch (e: ApiException) {
                if (e.code == 401) {
                    signedOut()
                    break
                }
            } catch (_: Exception) {
            }
            if (!running) break
            wait = if (System.currentTimeMillis() - started > 60_000) 15L else minOf(wait * 2, 300L)
            pause(wait)
        }
    }

    /** The server ended our session: say so once, plainly, and stop. */
    private fun signedOut() {
        SessionVault.clear(this)
        AlertPrefs.setOn(this, false)
        Notifier.simple(this, 2003, "Please sign in to Enveliq again", "Your new-email alerts stopped because you were signed out. Open Enveliq to sign in and turn them back on.")
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
            conn.inputStream.bufferedReader(Charsets.UTF_8).use { reader ->
                while (running) {
                    val line = reader.readLine() ?: break
                    if (line.startsWith("event:")) event = line.substring(6).trim()
                    else if (line.isEmpty()) {
                        if (event == "new") catchUp(api)
                        if (event == "reconnect") break
                        event = ""
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

    /** Looks at the inbox once and announces any email that is ready and has not had an alert yet. */
    private fun catchUp(api: EnveliqApi) {
        val mails = api.inbox()
        val alerted = AlertPrefs.alerted(this)
        if (!AlertPrefs.seeded(this)) {              // first time: what is already there is not new
            AlertPrefs.setAlerted(this, mails.map { it.id })
            AlertPrefs.setSeeded(this, true)
            return
        }
        val fresh = mails.filter { it.id !in alerted }
        if (fresh.isEmpty()) return
        alerted.addAll(fresh.map { it.id })
        AlertPrefs.setAlerted(this, alerted)
        Notifier.newMail(this, fresh, AlertPrefs.inQuietHours(this))
    }

    companion object {
        fun start(context: Context) {
            try {
                if (AlertPrefs.on(context) && SessionVault.load(context) != null) context.startForegroundService(Intent(context, MailWatcherService::class.java))
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
