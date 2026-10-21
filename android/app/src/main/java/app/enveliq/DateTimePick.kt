package app.enveliq

import android.app.DatePickerDialog
import android.app.TimePickerDialog
import android.content.Context
import android.text.format.DateFormat
import android.widget.Toast
import java.util.Calendar
import java.util.Locale

/**
 * "Pick date and time" for Remind me later and Send later: the phone's own day picker, then its own time picker, in the phone's time zone.
 * Any time from a minute ahead to a year ahead is accepted. [onPicked] gets the time in milliseconds and words such as "on Tue 3 Nov at 4:45 pm".
 */
fun pickDateAndTime(context: Context, onPicked: (Long, String) -> Unit) {
    val now = Calendar.getInstance()
    val day = DatePickerDialog(context, { _, y, m, d ->
        val hour = now.get(Calendar.HOUR_OF_DAY)
        TimePickerDialog(context, { _, h, min ->
            val c = Calendar.getInstance()
            c.set(y, m, d, h, min, 0)
            c.set(Calendar.MILLISECOND, 0)
            val ms = c.timeInMillis
            if (ms < System.currentTimeMillis() + 60_000L) {
                Toast.makeText(context, "Pick a time that is still to come", Toast.LENGTH_LONG).show()
            } else {
                val pattern = DateFormat.getBestDateTimePattern(Locale.getDefault(), "EEE d MMM jmm")
                onPicked(ms, "on " + java.text.SimpleDateFormat(pattern, Locale.getDefault()).format(c.time))
            }
        }, if (hour < 23) hour + 1 else hour, 0, DateFormat.is24HourFormat(context)).show()
    }, now.get(Calendar.YEAR), now.get(Calendar.MONTH), now.get(Calendar.DAY_OF_MONTH))
    day.datePicker.minDate = System.currentTimeMillis() - 1000
    day.datePicker.maxDate = System.currentTimeMillis() + 365L * 86_400_000L
    day.show()
}
