# Mute a conversation

Some email threads keep going and you no longer need them. **Mute conversation** stops the rest of a thread from coming back to you.

## Using it

Open an email, press the three dots at the right of its buttons, and choose **Mute conversation**. On Android the same item is in the three-dot menu under the summary. The email you are looking at is archived now. From then on, new replies in that conversation:

- go straight to **Archive** in your mailbox, so they never reach your inbox,
- do **not** send you an alert (they are filed before any alert is made), and
- are **not deleted**. They stay in your mailbox, and you can still find them there or with Search all my mail.

## Finding and unmuting

**Settings, Rules & calendar, Muted conversations** (and **Settings, Muted conversations** on Android) lists everything you muted, with the date and how many later replies were put in Archive. **Unmute** takes a conversation off the list, and new replies come to your inbox again. Replies that were already archived stay where they are.

## How it works

Enveliq remembers the message identifiers of the conversation (the email's own Message-ID and the ones in its References header). When a new email arrives whose identifiers match, it is archived at your mailbox the same way a mail rule does it. This works the same for Proton Bridge, IMAP and Microsoft mailboxes. It does not depend on any feature of the mail provider, so it behaves the same everywhere.

- Mail from your important people is never muted.
- You can keep up to 300 muted conversations.
- If your mailbox cannot be changed right now, the email stays where it is and Mute tells you so; nothing is half done.
- Only you can see or change your muted list. It is kept encrypted, holds only the subject line, a count and opaque identifiers (no email text and no addresses), is part of **Export my data**, and is removed with the person.

Routes: `POST /api/v1/accounts/{account}/messages/{message}/mute`, `GET /api/v1/me/muted`, `DELETE /api/v1/me/muted/{id}`.
