# Privacy

How Enveliq treats personal information. The same summary is shown in the app at `/privacy`. This is a general summary, not legal advice.

## The short version

Enveliq is self-hosted. The author of the software never receives your email, your settings, your usage or anything else about you. The person who runs your copy (the **operator**) holds the data on their own server, so questions about it go to them.

## What the author collects

Nothing. There is no telemetry, analytics, advertising, tracking or crash reporting, and the pages load no fonts, scripts or images from other sites. The one optional thing is the new-version notice: about once a day your server asks GitHub for the number of the newest release, so administrators can be told when an update is out. It sends nothing about you or your mail, the author does not receive it, and an administrator can switch it off (see [New versions](UPDATES.md)).

## What your server stores

- Account details: user name, a password hash (Argon2id), two-factor and passkey details, and role.
- For each connected mailbox: its connection details and encrypted summaries and tasks for the emails under review. Email bodies and attachments are not stored. An original email is fetched from your mail provider only when you ask to view it, and is not kept.
- Emails you keep from a search (Found emails) are stored like any other email card: sender, subject, date and an encrypted summary, for 60 days or until Reviewed. The email itself is not stored. Searching itself stores nothing.
- Only if you switch on Fast search for a mailbox, an encrypted word list for that mailbox is also kept, so search is quick. It holds no email text, skips long numbers and long words, is deleted when you switch it off, and is not in backups or exports. See [Find any email](FIND_MAIL.md).
- If the address book is on: names and email addresses of people you read mail from, write to or import, never any email text. It is encrypted, only you can see it, and you can export it, remove people or delete it all in Settings, Address book. You can switch off remembering people, or the whole feature. An administrator can switch the feature off for everyone.
- Sent mail, pictures and attachments are read from your mail provider when you open them and are never stored. Attachments you add to a new email are held in the server's memory only until the email is sent. A PDF you view is drawn as page pictures in memory and the PDF itself is never sent to your browser.
- Encrypted audit events (who did what and when) and settings.
- Everything is encrypted with AES-256-GCM under a key unlocked by the vault key. See `SECURITY.md`.

## Your browser

One session cookie to keep you signed in. Your browser's local storage keeps your light or dark choice and view layout. Nothing else, and none of it is sent to the author.

## Where data can leave your server

Only where the operator switches it on: your mail provider (to read and act on your mail), a single sign-on provider, an AI service (email text is sent to it, so choose one you trust; a local server keeps it on your network), GitHub (a once-a-day check for the newest release number, which an administrator can switch off; nothing about you is sent), and reporting outputs such as Grafana, which carry counts and timings but never email content.

## Deleting data

Disconnecting a mailbox deletes the data kept for it. An administrator can remove a user. Resolving an item clears what was kept for it according to the outcome chosen.

## Australian law

The author is an individual in Australia and does not collect personal information through Enveliq. The Privacy Act 1988 (Cth) applies mainly to larger organisations and some others; if you run Enveliq for a business or organisation, check whether it applies to you. If it does, you, as operator, are the one holding the information.
- If Include read mail (before, All emails) is on, the sender, subject and date of the mail you have already read from the last 60 days are kept, encrypted, for up to 60 days (and deleted if the feature is switched off). An email is only summarised when you press Generate summary, which sends that email's text to your AI model.
