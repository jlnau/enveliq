package app.enveliq

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.widget.RemoteViews

/**
 * A small home-screen square that says how many emails are waiting. It shows only that number, which the app saves each time the
 * inbox is loaded. No sender, subject or summary is ever put on the home screen. Tapping it opens the app.
 */
class WaitingWidget : AppWidgetProvider() {
    override fun onUpdate(context: Context, manager: AppWidgetManager, ids: IntArray) {
        for (id in ids) manager.updateAppWidget(id, views(context))
    }

    companion object {
        private const val KEY = "waiting_count"

        /** Remember the number and redraw every widget the person has placed. */
        fun update(context: Context, count: Int) {
            context.getSharedPreferences("enveliq", Context.MODE_PRIVATE).edit().putInt(KEY, count).apply()
            val manager = AppWidgetManager.getInstance(context)
            val ids = manager.getAppWidgetIds(ComponentName(context, WaitingWidget::class.java))
            if (ids.isNotEmpty()) for (id in ids) manager.updateAppWidget(id, views(context))
        }

        /** Forget the number (signing out), so the home screen does not keep showing it. */
        fun clear(context: Context) = update(context, -1)

        private fun views(context: Context): RemoteViews {
            val count = context.getSharedPreferences("enveliq", Context.MODE_PRIVATE).getInt(KEY, -1)
            val v = RemoteViews(context.packageName, R.layout.widget_waiting)
            v.setTextViewText(R.id.widget_count, if (count < 0) "-" else count.toString())
            v.setTextViewText(R.id.widget_label, if (count < 0) "Open Enveliq" else if (count == 1) "email waiting" else "emails waiting")
            val open = PendingIntent.getActivity(context, 0, Intent(context, MainActivity::class.java), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
            v.setOnClickPendingIntent(R.id.widget_root, open)
            return v
        }
    }
}
