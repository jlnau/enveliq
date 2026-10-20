
# Enveliq Security

Enveliq is a self hosted AI email assistant designed to keep personal information private and give users control over their data.

Security is part of how Enveliq is built, not an optional feature. The application uses encrypted storage, individual user permissions, restricted AI processing and careful handling of external connections.

This document explains the security model, what information is stored, how it is protected and the limitations users should understand.

## Reporting a security vulnerability

If you discover a potential security vulnerability, please report it privately.

**[Report a security vulnerability](https://github.com/jlnau/enveliq/security/advisories/new)**

Do not open a public GitHub issue for security vulnerabilities.

Include the affected version, a description of the problem and steps to reproduce it where possible.

Never include real emails, passwords, authentication tokens, API keys or other personal information in reports.

For ordinary bugs and installation problems, use [GitHub Issues](https://github.com/jlnau/enveliq/issues/new/choose).

## Core security principles

The following requirements apply throughout Enveliq.

1. **Private data belongs to its owner.** Users can access only their own email, settings and personal records. Administrators do not automatically receive access to another person's information.
2. **Sensitive information is encrypted.** Credentials, email metadata, summaries and other retained personal information are encrypted before being written to the database.
3. **Original email content is not retained.** Raw email bodies and attachments are processed temporarily when required, rather than stored as permanent application data. Only if a person switches on the optional Fast search, an encrypted word list is also kept so search is quick. It holds no email text and is deleted when switched off (see Find any email below).
4. **Access is verified by the server.** Authentication, permissions and ownership checks never rely on information supplied by the browser alone.
5. **Email content is untrusted.** Email text, attachments, external feeds and AI responses are treated as untrusted input.
6. **AI cannot independently manage email.** AI summaries and writing assistance do not have tools or permission to send, delete or modify messages.
7. **Secrets are never returned after storage.** Passwords, provider credentials and API keys are not exposed through application responses or intentionally included in logs.
8. **External connections are restricted.** Network destinations are validated, and sensitive requests use authenticated and encrypted connections where required.
9. **No advertising or tracking.** Enveliq does not include telemetry, third party advertising or analytics scripts.
10. **Security must survive new features.** Changes must preserve these requirements rather than introduce exceptions for convenience.

## Authentication and user access

Enveliq manages authentication through its own server.

### Supported authentication

* Username and password
* Authenticator applications using TOTP
* Passkeys using WebAuthn
* Recovery codes
* OpenID Connect single sign on, including providers such as Authentik, Authelia and Keycloak

Passwords are protected using Argon2id.

Two factor authentication is required for administrators by default. Administrators can configure the authentication policy for other users.

Sessions use random authentication tokens in protected cookies. HTTPS sessions use secure cookie settings and additional browser protections.

Sign in attempts are rate limited to reduce automated attacks.

### Account isolation

Each user's data is protected by server enforced ownership checks.

This includes:

* Email and connected mailboxes
* AI summaries and tasks
* Contacts and saved replies
* Shipping and subscription information
* Trips and reminders
* Private messages and agent chats
* Notification settings
* Saved preferences and viewing state

Administrators can manage the application without automatically gaining access to other users' private data.

Requests for resources belonging to another user are refused.

### Session security

Ordinary sessions have an inactivity timeout and a maximum lifetime.

An optional Keep me signed in feature can provide longer sessions when enabled by an administrator and supported by the vault configuration.

Signing out, changing passwords, disabling accounts and other security events invalidate affected sessions.

## Encryption and data storage

Enveliq stores application data in an encrypted local vault backed by SQLite.

### Encryption

| Protection | Technology |
| --- | --- |
| Data encryption | AES 256 GCM |
| Passphrase key derivation | Argon2id |
| Master encryption key | Random 256 bit key |
| Account encryption | Separate data encryption keys |
| Authentication passwords | Argon2id |
| Recovery codes | Stored as cryptographic hashes |

Sensitive records are encrypted before being written to persistent storage.

Encryption keys are protected separately from the encrypted data.

### Vault unlocking

A new install must be given a vault key (`ENVELIQ_VAULT_KEY` or a key file) before first setup, and the setup page refuses to continue without one. Enveliq unlocks itself with it after every restart. The key is at least 32 characters, is never logged and is never sent to a browser.

Installs made before this rule can keep their typed passphrase (manual unlocking after a restart) or switch to a key with `python -m backend.vault_key adopt`.

Automatic unlocking is convenient for unattended servers, but the operator must protect the key and keep a copy somewhere safe: without it the data cannot be opened.

A key file should be stored securely, outside the application data volume, with restricted permissions.

**Important:** Encryption protects stored data, but cannot guarantee confidentiality against someone who has compromised the running server and obtained access to its encryption keys.

### Backups

Backups contain encrypted vault data.

Administrators can create, download and restore backups, subject to authentication and additional confirmation requirements.

Backup files do not automatically include the separate vault key file.

Protect backups and encryption keys carefully. Anyone who obtains both may be able to decrypt the stored information.

## Email privacy

Enveliq connects to existing email providers rather than replacing them.

Supported connections include standard IMAP services, Proton Mail through Proton Bridge and Microsoft accounts using the supported authentication methods.

### What Enveliq stores

Enveliq retains information necessary to provide its features, including:

* Sender and subject metadata
* AI summaries and classifications
* Tasks and reminders
* Shipping and subscription information
* Trip details
* Reply tracking information
* Tags and user preferences
* Selected attachment metadata and summaries

These records are encrypted.

Retention varies by feature. Some records are removed after an email is handled, while others remain for a limited period or until the user removes them.

### What Enveliq does not permanently store

* Original received email bodies
* Original email attachments
* Original attachment text extracted for AI processing
* Original email HTML as executable page content

When a user opens an original email, Enveliq retrieves it from the email provider and processes it temporarily.

Email previews do not automatically load remote images, which can contain tracking pixels.

### Sending and managing email

Email sending requires an explicit user action.

The AI may suggest wording but cannot independently send messages.

User configured mail rules can automatically archive or mark qualifying messages as reviewed. These rules cannot send, forward or delete email.

Mailbox actions are performed through the connected email provider, with server side ownership and permission checks.

## AI security and privacy

Enveliq supports locally hosted AI models and supported external AI providers.

The operator chooses where AI processing takes place.

### Local AI

When a compatible AI model runs on the user's own network, email content submitted for AI processing can remain within that environment.

This is suitable for privacy focused installations, homelabs and local AI infrastructure.

### Cloud AI

When a cloud AI provider is configured, relevant email content is transmitted to that provider for processing.

The provider's own privacy policies and data handling practices apply.

Enveliq requires acknowledgement when configuring cloud AI processing. Additional consent controls apply to cloud attachment summaries.

**Finding models.** The administrator-only "Find models" button asks the configured AI address for its list of model names. It follows the same address rules as the connection test (private addresses, the allowed-hosts list, fixed cloud addresses), sends no email text, and never returns the access key.

### AI processing restrictions

For Enveliq's built in email analysis and writing assistance:

* Email content is supplied as untrusted data.
* Instructions embedded inside emails must not be followed.
* AI responses are validated before use.
* AI responses cannot directly execute commands.
* AI does not receive mailbox credentials or encryption keys.
* AI cannot independently send, delete or modify emails.
* Generated content is identified as AI generated.

These controls reduce risks from malicious email content, but AI summaries may still contain mistakes or be influenced by misleading messages.

Users should review important information against the original email.

### Agent chat

Enveliq also supports a separate agent chat feature.

The standard chat does not receive access to a user's email, tasks or private settings.

Administrators can optionally connect an external agent through Own agent mode.

**Own agent mode has a different security boundary.** An external agent may have tools or permissions configured outside Enveliq. Enveliq does not automatically provide it with mailbox data, but cannot control what that external agent can do in its own environment.

Operators should connect only agents they trust and understand.

## Attachment security

Email attachments are treated as untrusted files.

Enveliq applies file type checks, size limits and restricted processing.

### Attachment previews

Supported image and document previews are processed without executing embedded document scripts.

PDF rendering uses a separate restricted container in the documented Docker deployment.

The rendering container has:

* No direct access to the encrypted vault
* No access to application credentials
* No persistent application data volume
* Restricted operating system permissions
* Resource and processing limits
* No general internet access

Attachments and preview data are processed temporarily rather than stored as permanent copies.

Running without the isolated rendering container provides weaker isolation and should not be treated as equivalent to the standard container deployment.

### Original email as the sender formatted it

"View original email" shows an email's own formatting, fetched from the mailbox on demand and never stored.

* The server rebuilds the HTML from an allowed list of tags and settings. Scripts, forms, frames, plug-ins, SVG and event handlers are removed, links keep only web and mail addresses, and style rules lose anything that can load a file or run code.
* The result is served from its own address with its own strict Content-Security-Policy: no scripts except one fixed script of ours (pinned by its hash), no forms, and pictures only from inside the email unless the person asks.
* The browser shows it in a sealed frame with no access to the person's session, storage or the page around it. A mistake in the cleaning alone could not run an email's script. Only this one page may be framed; every other answer stays unframeable.
* Pictures from the internet are not loaded unless the person presses Show pictures for that email, because they tell the sender the email was opened. Plain `http` pictures are never loaded.
* Links inside the formatted email are intercepted and open only after the person confirms where they go, as in the plain text view.
* It is the same sign-in, ownership and rate limit as the plain text view, and nothing about the email is kept.

### Attachment AI summaries

Supported attachments may be summarised using the configured AI model.

The application retains encrypted summary information rather than the original document or extracted text.

When cloud AI is used, attachment summarisation requires administrator approval before document text is transmitted externally.

## Browser and application security

Enveliq serves its application resources locally and does not load third party advertising, analytics or tracking scripts.

Browser protections include:

* Content Security Policy restrictions
* Cross site request protections
* Same origin validation
* Escaping of untrusted content
* Restricted handling of external links
* Protection against unsafe HTML execution
* No automatic loading of remote email images

Some existing application pages use inline scripts under a less restrictive Content Security Policy than the authentication pages. Further tightening remains a security improvement target.

### Links inside emails

Links contained in email are untrusted.

Enveliq validates supported external links, restricts unsafe destinations and requires user interaction before opening them. Before a link can be opened, the question shows its website and then its complete address, wrapped over as many lines as it needs and never shortened, so a long tracking address can be read in full first.

The application does not automatically visit websites referenced in email messages.

Opening an external website may still disclose information to that website, as with an ordinary email client.

## Network and integration security

Enveliq can communicate with external services when required for configured functionality.

Examples include:

* Email providers
* AI services
* Home Assistant
* Calendar services
* Notification providers
* Single sign on providers
* RSS feeds
* Reporting systems
* GitHub release checks

Connections are validated according to the requirements of each integration.

Sensitive connections use appropriate authentication and transport security.

Destination checks are designed to reduce risks such as server side request forgery and access to unintended internal services.

### Home Assistant and notifications

Home Assistant integrations and notifications operate through configured connections and permissions.

Notification credentials are stored encrypted.

Notification content follows user privacy settings and may be restricted to counts or general reminders.

External notification services can see whatever information is intentionally sent to them.

### External webhooks

Inbound webhooks and WebSocket connections use scoped authentication keys.

Keys belong to individual users and cannot be used as general account sessions.

They are intended for submitting permitted notification content, not reading email or modifying unrelated account data.

### Live email updates

Live updates use authenticated Server Sent Events.

Events notify a signed in client that something changed, without including email bodies, sender addresses, subjects or other private message content.

The browser retrieves updated information through the existing authenticated API.

## Logging and monitoring

Enveliq supports operational monitoring and reporting without intentionally including email content or credentials.

### Audit logging

Security relevant events may be recorded, including:

* Sign in and authentication activity
* Administrative changes
* Mailbox operations
* Security configuration changes
* Backup and restore actions
* Relevant feature and integration changes

Audit records are encrypted.

Logs must not include passwords, API keys, raw email bodies or other secrets.

### Monitoring integrations

Optional reporting systems can receive operational metrics, such as counts, timings and application status.

Monitoring destinations are configured by administrators and subject to network restrictions.

Reporting is designed to exclude email content.

## Updates and dependency security

Enveliq uses automated GitHub Actions checks to help detect regressions and security problems.

The documented checks include:

* Backend tests
* Browser security checks
* Container build and configuration checks
* Dependency vulnerability scanning

Dependencies are also monitored for updates.

Published container images are built through the project's release workflow.

Passing automated checks does not guarantee that software contains no vulnerabilities.

### Optional update checks

Enveliq can check GitHub approximately once per day for the latest published release.

The request is made by the server, not the user's browser.

It does not intentionally include email content, user accounts or installation data.

Administrators can disable this feature.

## Deployment recommendations

Security also depends on how Enveliq is deployed and maintained.

For a safer installation:

1. Use the official installation instructions.
2. Keep Enveliq and its dependencies updated.
3. Use HTTPS when accessing Enveliq remotely.
4. Do not forward Enveliq's application port directly through your router.
5. Use a trusted reverse proxy or private access solution such as Tailscale.
6. Enable two factor authentication.
7. Protect vault keys, backups and provider credentials.
8. Restrict access to the host and Docker environment.
9. Configure only integrations and AI services you trust.
10. Keep operating system and container security updates current.

See the [installation guides](docs/install/README.md), [network access documentation](docs/NETWORK_ACCESS.md) and [backup documentation](docs/BACKUP.md).

## Known limitations

Enveliq is designed with privacy and security in mind, but it is not represented as independently security certified.

Important limitations include:

* A compromised server or stolen vault keys may expose decrypted application data.
* A malicious or inaccurate email may influence an AI summary despite prompt and output controls.
* Cloud AI providers receive the content required for enabled AI processing.
* External notification and integration services receive information explicitly sent to them.
* Connected external agents may have capabilities outside Enveliq's control.
* Application security relies partly on the host system, container configuration and network environment.
* Some browser security policies can be strengthened further.
* Independent penetration testing and broader security assessments remain valuable.

No software can guarantee complete protection against every vulnerability or attack.

Security reports and responsible contributions are welcome.

## Further information

For more information about Enveliq's design, configuration and data handling:

* [Privacy policy](docs/PRIVACY.md)
* [Architecture](docs/ARCHITECTURE.md)
* [Installation guides](docs/install/README.md)
* [Network access](docs/NETWORK_ACCESS.md)
* [Backup and restore](docs/BACKUP.md)
* [Contributing](CONTRIBUTING.md)

For security concerns, use the [private vulnerability reporting form](https://github.com/jlnau/enveliq/security/advisories/new).

For general questions and bugs, use [GitHub Issues](https://github.com/jlnau/enveliq/issues).

## Include read mail (All emails) inbox window

The optional Include read mail view (called All emails before 0.98) retrieves inbox message headers from the last 60 days without a count cap. Enveliq keeps only the existing encrypted metadata and placeholder summary records in the vault. Original message bodies and attachments are not retained. This does not expand access beyond the signed in mailbox owner. The larger window can increase mailbox provider requests, encrypted metadata storage and loading time.

## Google Calendar: using an existing calendar

By default Enveliq asks Google only for `calendar.app.created`, so it can only touch a calendar it made itself. A person may instead choose "Use a calendar I already have", which asks for `calendar.events` and `calendar.calendarlist.readonly`. That is a wider permission: Enveliq could technically see and change events on every calendar of that account, and says so before the person connects. In this mode Enveliq lists only calendars the person can write to, and the server checks the chosen calendar against that list (the page cannot name any other). It only adds, moves and removes events it made itself (tracked by their ids), and it never deletes the calendar. Disconnecting removes only Enveliq's events and revokes the permission. The Google token stays write-only and encrypted in the vault. Connecting and picking are audited (`google_calendar_connected` with the mode, `google_calendar_picked`).

## Android app

The app signs in through the same server routes as the website, so every sign-in rule (two-factor, password rules, rate limits, disabled people) is still enforced by the server. It adds no new server routes. The server decides who may read what from the signed-in session; the app never says who it is. The password is never kept. If the person leaves "Keep me signed in on this phone" on, the server's session cookie (with the same lifetime the administrator allows for "keep me signed in" on the website) is kept encrypted with an AES-GCM key held in the Android Keystore, so the app opens signed in; otherwise the cookie lives in memory only. Signing out in the app ends the session at the server and deletes the kept cookie, and a session the server refuses is deleted. The server address is also saved. Email is held in memory while on screen and is never written to the phone; Android backups and device-to-device transfer are switched off; cleartext (non-HTTPS) traffic is refused and only the server's real certificate is trusted. The official app is signed in GitHub Actions with one permanent release key kept as encrypted repository secrets; the key is never in the repository, and a release of the official repository is refused if the secrets are missing. A build made without them (someone's own copy) uses a temporary key and says so in its summary. Each APK is attached to the release with a SHA-256 checksum. The app lock (fingerprint, face or PIN, through Android's BiometricPrompt) only gates opening the app on that phone; it is not a replacement for the server's sign-in, and it never locks anyone out of a phone that has no screen lock. The Reviewed and Archive buttons on an alert use the kept, encrypted sign-in and the same server route as the app, so the server still checks who is asking; the buttons are not shown on the lock screen, and the alert text itself stays private there. Writing email from the app uses the website's own reply, forward, send, address-list and draft routes, so every sending rule, rate limit and "undo send" time still applies and the server decides who may send from which mailbox; what you type is held in memory while the writing screen is open and nothing is saved on the phone (drafts you choose to keep live on the server, like the website's). The address can be typed with or without `/api` on the end; the app only ever calls `/api/v1/...`, so a site behind Cloudflare Access can leave just that path open for the app. The server still decides everything from the signed-in session, so opening `/api` does not weaken any sign-in rule. **Your devices** (`GET /api/v1/auth/devices`, `DELETE /api/v1/auth/devices/{id}`) needs a full session and works only on the signed-in person's own sign-ins: it lists a public device id, a plain name, the sign-in time and method, never a token, and an id that is not yours answers "not found". The name is taken from a header the app sets or from the browser's description, trimmed to printable characters and 80 long, and shown as plain text. **Check for a new version** (`GET /api/v1/app-update`) passes on only the version number and Enveliq's own release address that the server already accepted from GitHub; the phone makes no request to GitHub. The **Tasks**, **More** (bell, messages, shipping, trips, news) and **Share** features use the website's existing routes with the signed-in session, so each person sees only their own; none of it is saved on the phone. The home-screen widget stores one number (how many emails are waiting) in the app's private storage and shows only that number, never a sender, subject or summary; signing out clears it. Text shared to the app is held in memory until a new email opens with it and is never sent without the person pressing Send. **Passkeys on the phone**: the official app's signing fingerprint is built in (and `ENVELIQ_ANDROID_CERT_SHA256` can add the fingerprint of an app someone built with their own key), so the app can sign in with a passkey kept on the phone through Android's own passkey screen, using the same two server routes as the website (`/auth/passkeys/options` and `/auth/passkeys/verify`), so the challenge, the one-use sign-in step, rate limits, the check of whose passkey it is, the sign count and the required screen lock or fingerprint are all still enforced by the server. The server additionally accepts the app's own origin (`android:apk-key-hash:` plus the hash of the app's signing certificate, taken only from the built-in fingerprint and that setting) and only for signing in, never for adding a passkey. `/.well-known/assetlinks.json` is public by design and holds only the app's name and the public fingerprint of its signing certificate; it answers "not found" if no fingerprint is known. A passkey response the server will not accept sends the app to the browser sign-in, which has the same rules. **Sign in with a passkey or single sign-on** hands a session from the browser to the app without passing a password or cookie: a signed-in browser (full session, so every sign-in rule and second step has already been met) asks `POST /api/v1/auth/app-link` for a code tied to the SHA-256 fingerprint of a random secret the app made; the code lasts 120 seconds, is held in memory only, and is thrown away on its first use, right or wrong; `POST /api/v1/auth/app-link/exchange` needs the code and the secret (compared in constant time), is rate limited like password sign-in, refuses a disabled person, and makes an ordinary session that shows in Your devices. The code travels through the phone's link handler, so another app could read it, but cannot use it without the secret, which never leaves the app (it is kept in the app's private storage for at most 10 minutes while the browser is open, then deleted). The only link the app accepts is `enveliq://signin?code=...`, and the code is checked for its shape before use. The Cloudflare allow-list is not part of the app yet (see the Android plan). The **From** choice only sends an address the person's own mailbox lists (its own address or a "send as" alias); the server still checks it against that mailbox's identities and refuses anything else, so the app cannot send as someone else. **Show the original email** uses the website's `original/html` route: the server rebuilds the email from allowed parts only and serves it under its own strict policy; the app shows that page in a view with JavaScript off, no file, content or storage access, no cache and no network until the person taps Show pictures, and every link asks before it opens. Files saved from an email are fetched for that moment and written only where the person chooses. **Mark unread** (`POST .../messages/{id}/unread`) needs the owner's full session like Reviewed does, works only on an email that is in the Reviewed list, and changes only the unread mark in the person's own mailbox; to make this possible a Reviewed card keeps its locator (an IMAP number and mailbox id, a pointer, never text) for as long as the card is kept, while an Archived card still drops it. The live alert connection now also reports the ids of emails that are no longer waiting, which carries no text. The alert filter (all, needs action, important people) runs on the phone from the person's own list and sends nothing new to anyone.

**Android app, version 0.97 additions.** **Send to Junk** and **Block sender** use the website's own routes (`POST .../messages/{id}/resolve` with the outcome `junked`, and `POST /api/v1/me/rules` with the action `junked`): the server checks that the mailbox is the signed-in person's own, moves that one email into the mailbox's own Junk folder (a normal, recoverable move), and a block rule never acts on important people or on mail already in the inbox. The app makes the block rule only after the Undo time. **Find any email** uses the website's find routes: the server searches the person's own mailboxes only, hands the page a short-lived token (not a mailbox number), and fetches a found email's text only when it is opened; nothing of it is kept on the phone. **Attach files** reads only the files the person picks through Android's file picker, holds them in memory, sends them to the existing send route (the server re-checks the count, size and the sending mailbox) and never writes them to the phone. **Pick from phone contacts** uses Android's contact picker, which hands over a single chosen address and needs no contacts permission. The **signature** is read from the person's own saved writing. Links that start an email (`mailto:`) fill a new email in memory and never send it. The unsubscribe button opens a web link only after the person confirms the site named, and a mail address only as a new email the person must send. **Send later** keeps only the person's own words (addresses, subject, text) as one encrypted vault record per person until the email is sent or taken back; attachments are never kept, so an email with files cannot be scheduled. Only the owner of a mailbox can schedule from it, the list and the take-back route answer "not found" for anyone else, and the record is included in the person's export and removed when the person is deleted. Failed sends keep only the reason for 7 days. **Alerts for messages, notes, tasks and parcels** use an `other` event on the existing alert stream that carries only kind names (counts are compared on the server), never any text. **Installing an update from the app**: `GET /api/v1/app-update/apk` (signed-in people only) makes the server fetch the exact published release file from Enveliq's own GitHub releases, accept it only if it matches the SHA-256 published beside it, and pass it on; the phone never contacts GitHub, and Android still requires the same signing key and the person's confirmation. The permission to install apps is used only for that button. The **Get the Android app** links point at the public GitHub releases page and make no request when a page is viewed. **Your devices** is also on the website's Sign-in and security page, using the same routes.

**New-email alerts.** `GET /api/v1/me/new-mail-events` needs a full signed-in session (the same check as the website's live updates) and only reports the ids of the signed-in person's own finished, unread emails; it never sends a sender, subject, summary or any text, and it answers nothing for anyone else's mailbox. The app holds one connection to it, with no third-party push service, so no company besides the person's own server learns when mail arrives. Alerts need the sign-in to stay on the phone (still encrypted in the Android Keystore); signing out, or the server ending the session, stops the alerts and forgets the announced ids. On the lock screen an alert only says "New email"; the sender and subject show once the phone is unlocked. Quiet hours only silence the alert; nothing is held back on the server.

**Google push for the Android app (optional).** No Enveliq server holds a Firebase key, and nothing for it appears in Administration. A server sends a wake-up request to the shared push relay (a small Cloudflare Worker in `relay/`), which alone holds the Firebase service-account key as a Worker secret and talks to Google. A request holds only the phone's Google address, the kind ("mail" or "test") and a count: never a sender, subject, summary, account, name or any email text, so Google learns only that a notification went to a phone and when, and the relay learns the same plus which address it was for. The relay stores nothing, never logs or repeats the phone's address, rejects anything that is not exactly that shape, and the server only talks to it over https (the address is checked, and private addresses are not allowed unless the administrator lists them). A phone's Google address is stored encrypted in that person's own notification record (like browser devices), at most 5 per person, removed when the relay says the phone no longer has the app, when the person turns alerts off or switches to the direct connection, and when they sign out. The relay's address is not in the source code (it is added to the official images when they are built), and the Firebase API key is locked to the app's package and signing certificate, so a fork cannot use the publisher's relay or Firebase project. The routes need a full signed-in session. The app never contacts Google until the person chooses it (Firebase's automatic start-up and analytics are switched off), and the `google-services.json` file is kept out of the repository and written into the build from an encrypted secret. See [Push relay](docs/PUSH_RELAY.md).

## Original email shown in the reading panel

The View panel option "Show the original email" fetches the original from the mailbox for the email you opened, through the same server route, safe rebuild and strict page rules as "View original email" (scripts removed, pictures from the internet and links off until you choose). The page holds at most three originals in memory for a moment so a redraw does not fetch again; they are never written to the browser's storage or to Enveliq's vault, and are dropped when the option is turned off or another person signs in. Only the on/off choice is saved, in the person's own encrypted view settings.

## Junk Mail

**Junk Mail** reads the Junk or Spam folder of the person's own mailboxes and asks the configured AI model about each email.

- Only headers are read to list an email. The text is shown to the model once, between data markers, with the usual rules: the model gets no tools, treats the text as data, never decides anything else, and its answer (verdict, summary, reason) is checked, cut to safe lengths and labelled as the AI's.
- What is kept is one encrypted record per person: sender, subject, date, the AI's answer and the email's mailbox location. No email text. The location is never sent to the page; the page uses an opaque random id. Another person's id answers "not found". The record is capped (200 emails, 30 days), is part of Your data and is removed with the person.
- **View original email** from Junk Mail is stricter than the normal viewer: the server removes the links list, the unsubscribe address, the attachment list and the count of pictures from the internet, and the formatted copy is rebuilt with links turned into plain text, pictures from the internet never loaded, and scripts removed, under the same sealed-frame policy. The email is fetched when opened and not stored.
- **Not Junk** is the only change Enveliq makes at the mail service: it moves that one email to the Inbox and marks it unread. It is limited to the person's own mailbox, rate-limited, and recorded in the audit log without the subject or sender. Enveliq moves an email into Junk only when the person presses **Send to Junk** or **Block sender** (or has made a "send to Junk" rule for that sender, which acts only on new mail, never on important people), never deletes mail and never unsubscribes. A Junk move is a normal move of that one email within the person's own mailbox, recoverable from the Junk folder.
- It has its own switch for everyone (Administration) and for each person (Settings, General).

## Find any email

**Search all my mail** asks the person's own mail service to search their whole mailbox. It adds no copy of any email.

- The search words go only to the person's own mail service, over the connection Enveliq already uses. They are never logged, never sent to an AI model and never shown to an administrator. The audit log records only that a search happened.
- A search keeps only folder and message numbers, in server memory, for about 15 minutes. No email text. Results carry an opaque signed reference tied to the signed-in person and that one search; a reference that is not theirs, or is forged, answers "not found". Opening a result fetches the email then and does not store it.
- Searching never changes the mailbox. A search never holds the lock that syncing uses. Searches are limited (six a minute per person, four at once on the server, about three minutes per mailbox) and the words are length-limited and quoted safely before they reach the mail service.
- **Summarise Emails** (two or more ticked results, at most 100 at a time, six requests a minute) does the same for each ticked result through the same per-result checks: a result that is not the person's own, or is forged, answers "not found" for that one and the rest still go through.
- **Summarise** keeps one email as an ordinary encrypted card (sender, subject, date, summary) in Found emails for 60 days or until Reviewed. It is treated as quiet: no alert, not counted as unread, not touched by syncing. Reviewed removes the card and does not change the mailbox.
- **Fast search** is optional, per person and per mailbox, off by default, and needs a plain warning to be accepted. If it is on, an encrypted word list is kept: for each email, where it lives and which words it contains, with no email text. Numbers longer than 8 digits and words longer than 30 characters are skipped, and attachments are not indexed. It is one file per person sealed with AES-256-GCM under a key derived from the vault key, so it can only be read while Enveliq is unlocked, and it is dropped from memory when the vault locks. It is not in backups or exports, and it is deleted when switched off, when the mailbox is removed and when the person is removed. Honest limit: while Enveliq builds or uses the word list, or summarises an email, the text is briefly in the server's memory, as it already is for summaries. Someone with full control of the running server could read it then.

## New mailboxes start with AI summaries and Waiting for reply on

A mailbox you add starts with Check for new mail automatically, Write AI summaries and Follow sent mail for replies all ticked. This is a default, not a change to what is kept: only a short summary, or a one-line note for Waiting for reply, is stored, never the email, and the AI still gets no tools and treats email text as data. What changes is that, with the AI configured, the text of new mail and of each new sent email is shown to your AI model without a separate question for each mailbox. If your AI model is a cloud service, that text leaves your computer, so the add form and the mailbox's Edit page say so in plain words and each box can be unticked, which saves at once. Mailboxes that already exist keep the choices they had. The settings are saved by the server for the signed-in owner of the mailbox only, as before.


## Administration in the one Settings menu

The Administration group in the Settings menu, and its search results, are only built for signed-in administrators. This is a convenience: every Administration request is still checked on the server from the signed-in session, and anyone else gets "not found".
