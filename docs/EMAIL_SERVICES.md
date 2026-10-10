# Connecting Gmail, iCloud, Yahoo, Fastmail and other email services

Enveliq connects to your mailbox with an **app password**: a password your
email service makes for one app. You can cancel it at any time without changing
your real password. Nothing has to be registered with Google or anyone else for
these services. (Outlook, Hotmail and Microsoft 365 are the exception: see below.)

Open the **Setup guide** (or **Mailboxes**), choose your service, and follow the
steps shown for it. You can connect as many mailboxes as you like, from any mix
of services.

| Service | Server (reading / sending) | You need |
| --- | --- | --- |
| Gmail | imap.gmail.com:993 / smtp.gmail.com:465 | 2-Step Verification on, then an app password at myaccount.google.com/apppasswords |
| iCloud Mail | imap.mail.me.com:993 / smtp.mail.me.com:587 | Two-factor authentication on, then an app-specific password at account.apple.com |
| Yahoo Mail | imap.mail.yahoo.com:993 / smtp.mail.yahoo.com:465 | An app password from Yahoo's Account security page |
| Fastmail | imap.fastmail.com:993 / smtp.fastmail.com:465 | An app password with Mail access (Settings, Privacy & Security, Integrations) |
| Other (IMAP) | the names your provider gives | Your provider's IMAP and SMTP settings, and an app password if offered |
| Outlook, Hotmail, Microsoft 365 | outlook.office365.com:993 / smtp.office365.com:587 | An app registration made once by an administrator, then Sign in with Microsoft (MICROSOFT.md) |
| Proton Mail | through Proton Mail Bridge | see PROTON_BRIDGE.md |

**Outlook, Hotmail and Microsoft 365** do not accept passwords or app passwords from
other apps. People sign in on Microsoft's own page instead, which needs a small app
registration that you make once and enter under Administration, Microsoft sign-in.
It is free and takes about five minutes: see `MICROSOFT.md` for every step.

## What Enveliq does with the connection

Same as for Bridge: it reads only the sender, subject and date of unread mail,
fetches the full email only when you press View email (plain text, never saved),
and changes your mailbox only when you press Reviewed, Archive or Bin. Archive
moves to the folder the service marks as archive (Gmail: All Mail) and Bin to its
trash folder.

## Administrator notes

* By default Enveliq connects only to public mail servers on the standard
  secure ports, and always checks the server's certificate.
* A server on your own network, or on a non-standard port, must be listed in
  `ENVELIQ_MAIL_ALLOWED_HOSTS` (comma separated). When the list is set, only
  those servers are contacted. A private certificate authority is trusted with
  `ENVELIQ_MAIL_CA_FILE`.
* Adding a service for everyone: add an entry to `backend/mail/providers.py`
  (server names, ports, the page where the app password is made, and the steps).
  The setup guide reads that list from the server, so no page code changes.

## Problems

| Message | What to do |
| --- | --- |
| `login_failed` | Check the address, then make a new app password and paste it again. |
| `app_password_required` | The service wants an app password instead of your normal password. |
| `tls_failed` | The server's certificate could not be checked. Check the server name; for a private certificate authority see above. |
| `host_not_allowed` | The server is not public, or uses a non-standard port. See administrator notes. |
| `unreachable` | Check the server name and port and that this machine has internet access. |
