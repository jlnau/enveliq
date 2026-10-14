# Drafts

## What you will see
- **Saved by itself.** While you write a New email, Reply, Reply all or Forward, Enveliq saves it to Drafts every few seconds (once there is something worth keeping), and once more when you close or leave the page. So closing the browser does not lose your words: the draft is waiting on the Drafts page. A small line under the writing says when it was last saved.
- When you close a **New email**, **Reply**, **Reply all** or **Forward** window that has something written in it (with the ×, **Cancel**, the Escape key or a click outside), Enveliq asks **Save this as a draft?** with three choices: **Save as draft**, **Discard** (which also deletes the copy that was saved by itself) and **Keep writing**. Nothing is asked if you have not written or changed anything.
- A saved draft appears on the **Drafts** page (in the left menu, under More, with a number showing how many you have). Each draft shows what kind it is, who it is for, the subject, the first lines, and how many days are left.
- **Continue writing** opens the draft in the same window you left, with the people, subject and words back. A reply, Reply all or Forward opens on the email it answers. If that email is no longer in your list, the draft opens as a New email instead. Saving again replaces the draft. Sending it removes it from Drafts.
- **Delete** asks once more ("Delete this draft?") before it deletes.
- A draft is kept for **14 days after you last saved it**, then it is removed. It is kept on the server, so it is still there if you close the browser or switch device.
- Attachments are **not** kept in a draft. If a New email has attachments when you save it, Enveliq says so; add them again when you continue. A forward's original files are fetched again when you send.
- Closing an opened draft without changing anything asks nothing. Once you change a draft it is saved over by itself, so Discard on a changed draft deletes the draft.
- **On a phone** the writing window fills the screen, so the question appears as a sheet from the bottom of the screen with three wide buttons: **Save as draft**, **Discard** and **Keep writing**. The "Send this?" check and the send warning appear the same way.

## How it works
- Drafts are stored on the server as one encrypted record per person (`drafts:<user id>`), like the signature and saved replies. Only that person can read them; the Drafts page shows only your own.
- A draft holds what you typed: the kind, who it is for (To, Cc, Bcc), the subject and your words, and which mailbox and email it answers. It never holds the original email's text. Sending still goes through the normal checks, so a draft is just text until you press Send.
- `GET /api/v1/me/drafts`, `POST /api/v1/me/drafts`, `PUT /api/v1/me/drafts/{id}`, `DELETE /api/v1/me/drafts/{id}`. At most 50 drafts, 100,000 characters each, 50 people per list. Line breaks and control characters are removed from the subject and addresses. Drafts older than 14 days are removed from the record the next time the list is read or a draft is saved, which happens each time the page opens.
- Drafts are part of **Export my data** and are removed when a person is removed.

## Where the code is
`backend/mail/drafts.py`, `backend/mail/drafts_routes.py`, `backend/app.py`, `backend/export.py`, `prototype/index.html` (the Drafts page and the question). Tests: `tests/test_drafts.py`, `scripts/check_drafts.mjs`.
