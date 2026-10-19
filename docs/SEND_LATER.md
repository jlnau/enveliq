# Send later

Write an email now and have Enveliq send it at a time you choose. In **New email**, **Reply** and **Forward**, press **Later** beside Send, then pick a time (this evening, tomorrow morning, Monday morning, or your own date and time). The message is not sent now.

## Where it waits

Waiting emails are listed under **Sent, Waiting to send** on the website, and **More, Waiting to send** in the Android app. Each shows who it is for, the subject and when it will go. **Take it back** removes it at once and puts your words back so you can change them.

## Rules

- The time must be at least 30 seconds ahead and at most 30 days away. You can have up to 20 waiting at once.
- It goes out from the mailbox you chose, at the time you chose, even if you are signed out or the page is closed. A reply waiting to go still marks the email as replied when it is sent.
- The usual send checks run when you schedule it (addresses, size), and again when it is sent.
- **Files cannot wait.** Enveliq never keeps attachments, so an email with files cannot be scheduled. Send it now, or schedule the words and attach nothing.
- If it cannot be sent (for example the mailbox refuses it), it stays in the list marked "Could not send", with the reason, for 7 days, so nothing disappears silently.
- Only the mailbox's owner can schedule from it, and each person sees only their own waiting emails. Administrators cannot read them.

## How it is kept

A waiting email is your own words (addresses, subject and text), kept encrypted inside the vault until it is sent or taken back, then deleted. It survives a restart of Enveliq. This is different from **Undo send** (see [Undo](UNDO.md)), which only holds an email for a few seconds in memory.

Routes: `GET /api/v1/me/scheduled`, `POST /api/v1/me/scheduled`, `DELETE /api/v1/me/scheduled/{id}`. A background job checks every 15 seconds. The backup export includes your waiting emails under "emails to send later".
