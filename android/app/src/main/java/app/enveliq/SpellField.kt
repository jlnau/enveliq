package app.enveliq

import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.text.Editable
import android.text.InputType
import android.text.TextWatcher
import android.util.TypedValue
import android.view.Gravity
import android.widget.EditText
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.viewinterop.AndroidView

/**
 * A text box for writing. It is the phone's own text box (not Compose's), so the phone's spell checker works in it: misspelled
 * words are underlined and a tap offers the fix, as in every other app, and the keyboard's suggestions and auto-correct work too.
 * It looks like the other boxes in the app (a thin outline, the app's colours).
 */
@Composable
internal fun SpellField(value: String, onChange: (String) -> Unit, singleLine: Boolean, modifier: Modifier = Modifier, minLines: Int = 1) {
    val latest by rememberUpdatedState(onChange)
    val ink = Ink.toArgb()
    val muted = Muted.toArgb()
    val line = Line.toArgb()
    val accent = Blue.toArgb()
    AndroidView(
        modifier = modifier,
        factory = { ctx ->
            EditText(ctx).apply {
                inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_AUTO_CORRECT or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES or
                    (if (singleLine) 0 else InputType.TYPE_TEXT_FLAG_MULTI_LINE)
                if (singleLine) { maxLines = 1; isSingleLine = true } else { this.minLines = minLines; gravity = Gravity.TOP or Gravity.START }
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
                val pad = (14 * ctx.resources.displayMetrics.density).toInt()
                setPadding(pad, pad, pad, pad)
                setText(value)
                setSelection(text.length)
                addTextChangedListener(object : TextWatcher {
                    override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
                    override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
                    override fun afterTextChanged(s: Editable?) { latest(s?.toString() ?: "") }
                })
            }
        },
        update = { et ->
            et.setTextColor(ink)
            et.setHintTextColor(muted)
            et.highlightColor = (accent and 0x00FFFFFF) or 0x55000000
            et.background = GradientDrawable().apply {
                cornerRadius = 12f * et.resources.displayMetrics.density
                setStroke((1 * et.resources.displayMetrics.density).toInt().coerceAtLeast(1), line)
            }
            if (Build.VERSION.SDK_INT >= 29) {
                et.textCursorDrawable = GradientDrawable().apply { setColor(accent); setSize((2 * et.resources.displayMetrics.density).toInt().coerceAtLeast(2), 0) }
            }
            if (et.text.toString() != value) {
                et.setText(value)
                et.setSelection(et.text.length)
            }
        },
    )
}

/**
 * The box for a two-factor (authenticator app) code. It is the phone's own text box, marked as a one-time code, so password managers
 * such as Bitwarden recognise it and can fill it, and the keyboard offers to paste a code you have just copied.
 */
@Composable
internal fun CodeField(value: String, onChange: (String) -> Unit, onDone: () -> Unit, modifier: Modifier = Modifier) {
    val latest by rememberUpdatedState(onChange)
    val done by rememberUpdatedState(onDone)
    val ink = Ink.toArgb()
    val muted = Muted.toArgb()
    val line = Line.toArgb()
    val accent = Blue.toArgb()
    AndroidView(
        modifier = modifier,
        factory = { ctx ->
            EditText(ctx).apply {
                id = R.id.totp_code
                inputType = InputType.TYPE_CLASS_TEXT
                maxLines = 1
                isSingleLine = true
                hint = "Verification code"
                contentDescription = "Two-factor verification code"
                importantForAutofill = android.view.View.IMPORTANT_FOR_AUTOFILL_YES
                setAutofillHints("smsOTPCode", "oneTimeCode", "totp")
                imeOptions = android.view.inputmethod.EditorInfo.IME_ACTION_DONE
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 18f)
                val pad = (14 * ctx.resources.displayMetrics.density).toInt()
                setPadding(pad, pad, pad, pad)
                setText(value)
                setSelection(text.length)
                addTextChangedListener(object : TextWatcher {
                    override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
                    override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
                    override fun afterTextChanged(s: Editable?) { latest(s?.toString() ?: "") }
                })
                setOnEditorActionListener { _, action, _ ->
                    if (action == android.view.inputmethod.EditorInfo.IME_ACTION_DONE) { done(); true } else false
                }
                // Focus it straight away so the keyboard (with its paste suggestion) and the password manager are ready.
                post { requestFocus(); (ctx.getSystemService(android.view.inputmethod.InputMethodManager::class.java))?.showSoftInput(this, 0) }
            }
        },
        update = { et ->
            et.setTextColor(ink)
            et.setHintTextColor(muted)
            et.highlightColor = (accent and 0x00FFFFFF) or 0x55000000
            et.background = GradientDrawable().apply {
                cornerRadius = 12f * et.resources.displayMetrics.density
                setStroke((1 * et.resources.displayMetrics.density).toInt().coerceAtLeast(1), line)
            }
            if (Build.VERSION.SDK_INT >= 29) {
                et.textCursorDrawable = GradientDrawable().apply { setColor(accent); setSize((2 * et.resources.displayMetrics.density).toInt().coerceAtLeast(2), 0) }
            }
            if (et.text.toString() != value) {
                et.setText(value)
                et.setSelection(et.text.length)
            }
        },
    )
}
