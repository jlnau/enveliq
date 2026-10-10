# Writing help

The AI can write a reply for you, or check one you wrote. It only ever **suggests**: you press Send.

## What people see

- **Settings, AI instructions, Writing help.** Off until you turn it on. When you do, the box already holds plain, friendly default instructions; keep them, change them or add to them. **Use the standard instructions** puts the default back. The instructions change style only, never the safety rules.
- **Reply box and New email box.** One button: **Write a reply for me** (New email: **Help me write**) when the box is empty, **Check my reply** (**Check my email**) when there is text.
- **A second box**, headed **Suggested by AI. Nothing here is sent.** It holds the suggestion and up to five short notes. **Accept** replaces what is in your box (**Put my version back** undoes it). **Copy**, **Try again** and **Close** are beside it. You can also select part of it and copy that.
- **Send check.** If you used writing help on that message, Send first shows the exact text and says whether it is AI wording or an unused suggestion, and warns about any gap left in [square brackets]. Replies written without writing help send straight away.
- **Administration, Features, Writing help** switches it off for everyone. People can switch it off for themselves too.

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
