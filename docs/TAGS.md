# Tags

Enveliq shows the tags your email service already has on each email, lets you put a tag on an email or take it off, and lets you make a new tag. Every change is also made in your real mailbox, so Enveliq and your mail service always agree.

## What you see

- A tag on an email shows as a small label next to its subject (two at most in the list, all of them when the email is open).
- Every email in your inbox has a **Tags** button beside Reply, Snooze and Task. It opens a list of your tags with a tick box for each. Tick one to put it on this email, untick it to take it off. The change is made in your mailbox straight away.
- **Make a new tag**: write a name and press **Make tag**. It is made in your mailbox and put on this email.
- **Filter** (under the inbox options) has a **Tag: …** choice for each tag your inbox emails have, to show only those emails. Search also finds emails by their tags.
- On a phone the Tags window fills the screen, with **✕ Close** fixed at the top and the buttons at the bottom (see [Forms on a phone](INBOX.md)).
- Only emails still in your inbox can be tagged. Once an email is marked Reviewed, archived or binned it is no longer listed, so its tags are not shown.

## How each kind of mailbox keeps tags

| Mailbox | What a tag is | Notes |
| --- | --- | --- |
| Proton Mail (Bridge) | A label. Bridge shows each label as a folder called `Labels/<name>`. | Putting a label on copies the email into that folder, taking it off deletes only that copy. The email stays in your inbox either way. |
| Gmail | A label, read and changed on the message directly. | System labels (Inbox, Important, Sent and so on) are not shown. A label with a `/` in its name is a nested label and is shown as written. |
| iCloud, Yahoo, Fastmail, other IMAP | A keyword on the message. | Only some services keep your own keywords. If yours does not, Enveliq says so and cannot make new tags. Tag names here cannot have spaces. |
| Outlook, Hotmail, Microsoft 365 | Not supported. | Its categories cannot be reached this way. The Tags window says so. |

Tag names: up to 40 letters, digits, spaces and the signs `- _ . & + ( )`. Names that match one of your mail folders (Inbox, Archive, Trash, Sent and so on) are refused, and so is a name that only differs from an existing tag in capital letters.

## Staying in step

Enveliq reads the tags of your inbox emails after each automatic sync (every few minutes), so a tag you add in your mail app appears here, and one you remove disappears. For Proton Bridge this means looking through up to 60 label folders (the newest 300 emails in each); for Gmail and other services it is one request.

## Each person's own

Tags are read from, and changed in, your own mailbox only. Only the owner of a mailbox can use its tags; anyone else gets "not found".

## Switching it off

An administrator can switch **Tags** off for everyone (Administration, Features) and each person can switch it off for themselves (Settings). When off, nothing is read or changed and the buttons disappear.

## What is kept, and what to check

Only tag names are kept in Enveliq: a short list on each email's encrypted record, removed with the email. The tag list of a mailbox is read live each time the window opens and is not stored. Nothing is sent to the AI.

Proton and other services differ in small ways and this has been tested against pretend mail servers only. Try a tag on a throwaway email in your real mailbox first: put it on, check it in your mail app, take it off.

## Code

`backend/mail/tags.py` (how each kind of mailbox is read and changed, and the sync step), `backend/mail/tag_routes.py` (`/api/v1/accounts/{id}/tags` and `/api/v1/accounts/{id}/messages/{id}/tags`), the `tags` switch in `backend/mail/features.py`, the button, window and filter in `prototype/index.html`. Checks: `tests/test_tags.py`, `scripts/check_tags.mjs`.
