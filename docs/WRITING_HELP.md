# Writing help

The AI can write a reply for you, or check one you wrote. It only ever **suggests**: you press Send.

## What people see

- **Settings, AI instructions, Writing help.** Off until you turn it on. When you do, the box already holds plain, friendly default instructions; keep them, change them or add to them. **Use the standard instructions** puts the default back. The instructions change style only, never the safety rules.
- **Reply box and New email box.** One button: **Write a reply for me** (New email: **Help me write**) when the box is empty, **Check my reply** (**Check my email**) when there is text.
- **A second box**, headed **Suggested by AI. Nothing here is sent.** It holds the suggestion and up to five short notes. **Accept** replaces what is in your box (**Put my version back** undoes it). **Copy**, **Try again** and **Close** are beside it. You can also select part of it and copy that.
- **Send check.** If you used writing help on that message, Send first shows the exact text and says whether it is AI wording or an unused suggestion, and warns about any gap left in [square brackets]. Replies written without writing help send straight away.
- **Administration, Features, Writing help** switches it off for everyone. People can switch it off for themselves too.

## Quick AI Send

A button beside Send in the reply, forward and New email boxes (website and Android app). It proofreads and sends in one press: the AI corrects spelling, grammar, punctuation and formatting and **must not** change the meaning, the facts, the tone or the intent, add anything or shorten anything. There is no extra question: pressing it is the "yes".

- It has its own switch (Settings, Writing help, **Quick AI Send**) and is **off** until the person turns it on. It needs Writing help on and an AI model.
- The corrected text is only ever handed to the normal send route, so every sending rule, undo-send time and rate limit still applies. Your own box is never changed: if the AI cannot be reached, answers badly, or the send fails, nothing is sent and your draft is exactly as you left it, with a plain message.
- The server checks the AI's answer before using it: the numbers, web and email addresses and [brackets] must all still be there, and the length may not change by more than about 12%. If anything looks different it refuses (`quick_unsafe`) and nothing is sent. An empty draft is refused too.
- Route: `POST /api/v1/me/write-help/quick-fix` (returns `subject`, `text`, `changed`; sends nothing, stores nothing). It uses the writing style guide when one is on.

## Your writing style

Settings, Writing help, **Your writing style** (also in the Android app). Off until the person turns on **Learn my writing style**.

- Enveliq reads the person's 20 most recent sent emails from their own mailboxes and keeps **only the words the person wrote themselves**: quoted conversation, "On ... wrote:" parts, signatures, forwarded emails, links, addresses and attachments are cut away first. Those samples are kept apart from normal email indexing, in one small encrypted record per person, and are replaced at each refresh.
- The AI reads the samples as untrusted data (no tools) and writes a short guide: tone, vocabulary, sentence structure and habits. The guide is shown in Settings, where the person can read it and **edit** it. It is then added to Writing help and Quick AI Send.
- **Automatic** (the start): a new guide is made once a week from the latest 20. **Manual**: editing the guide switches this off, and nothing overwrites the person's words until **Update it every week** is turned back on. **Make it again now** makes one at once (4 an hour).
- Routes: `GET`/`PUT /api/v1/me/writing-style`, `POST /api/v1/me/writing-style/rebuild`. Code: `backend/mail/style.py`, `style_routes.py`. The weekly pass runs from the reminders tick.

## On the Android app

Writing help is the same on the phone: under the message there is **Write a reply for me** / **Help me write** / **Check my reply**, a "Suggested by AI" box (**Accept**, **Put my version back**, **Copy**, **Try again**, **Close**), the check before sending AI wording, **Quick AI Send** above the Send row, and Settings, **Writing help** with the switches, instructions and writing style. Code: `WritingHelp.kt`, `Compose.kt`.

## How it works

- `backend/mail/writehelp.py` holds the record, the fixed rules, the prompt and the answer parsing. `backend/mail/writehelp_routes.py` has the four routes.
- The model gets the email being answered and the draft as data, no tools, and rules that it must not follow instructions inside them, must not invent facts, and must leave a [bracket] where only the person can answer.
- Nothing is stored or logged except a small per-person record (on or off, your instructions). The audit log says only that it was used.
- Rate limit: 12 requests a minute per person. Time limit: 90 seconds.

## What cannot be promised

- The AI can still get things wrong or sound unlike you: that is why it is a labelled suggestion with a check before sending.
- It cannot know your answers (can you make Tuesday?), so it leaves a gap in [brackets].
- A model cannot be made immune to a hostile email. Its output is only ever shown, never acted on.

The plan this came from, with the mock-ups' decisions, is in `docs/EMAIL_ASSIST.md`. One-tap replies are a later release.
