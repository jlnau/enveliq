# Enveliq security model

## Reporting a security problem

If you think you have found a weakness in Enveliq, please **do not** open a public issue. Use this repository's **Security** tab and choose **Report a vulnerability**, which sends your report privately to the maintainer. Say what you did, what you saw, and which version you were running. Please leave real email, passwords and keys out of the report. For ordinary bugs and questions, see [Troubleshooting](docs/install/troubleshooting.md) and open a normal issue.

## Security invariants

These rules are architecture requirements, not UI preferences.

1. **Enveliq authenticates people itself.** Identity comes only from a server-side session created by a verified sign-in (password plus second factor, passkey, or a verified OpenID Connect ID token). The browser never supplies its own user ID or administrator flag, and there is no default or development identity.
2. **Administrator does not mean mailbox reader.** A mailbox belongs to an Enveliq user. Admin rights control global infrastructure and AI configuration but do not automatically grant access to another user's private mail.
3. **Sensitive data is never persisted in plaintext.** Provider passwords, OAuth refresh tokens, AI API keys, mailbox addresses, subjects, summaries, task data and retained attachment summaries are encrypted before SQLite writes them.
4. **Raw mail bodies are not retained by default.** The retained message API intentionally has no raw body, HTML body or binary attachment fields.
5. **Raw attachments are not persistent application data.** Future attachment parsing must use a RAM-backed isolated worker and delete material immediately after extraction.
6. **Email content is hostile input.** The LLM gets no Home Assistant tools, shell, filesystem, arbitrary network access or secret access. It may only return a validated structured result.
7. **Secrets are write-only from the browser's perspective.** API responses never return passwords, OAuth refresh tokens or LLM API keys.
8. **No master encryption key is stored on disk.** A random master key is wrapped by an Argon2id-derived key. After restart someone with the vault passphrase must unlock the vault (separately from signing in) unless a future TPM/HSM/secrets-manager integration is configured.
9. **Logs must not contain message content or secrets.** Request bodies are never logged. A redaction filter provides another layer for accidental secret strings in application log messages.
10. **Network exposure is deny-by-default.** The server binds to `127.0.0.1` and refuses any other address unless told it sits behind a reverse proxy. The public URL must be `https://` (except localhost). Forwarded headers are ignored. Opening it on a trusted network over plain http is an explicit opt-in that needs three settings together (`ENVELIQ_PUBLISH`, `ENVELIQ_PUBLIC_URL`, `ENVELIQ_ALLOW_INSECURE_PUBLIC_URL`); it is never the default, the server logs a warning when it is on, and the trade-offs are in `docs/NETWORK_ACCESS.md`. The ready-made install file (`install/docker-compose.yml`) publishes `"8765:8765"`, so other devices on the network can reach the port; sign-in, the setup code and the https/plain-http rules are unchanged, and the file's comment shows `127.0.0.1:8765:8765` for a computer-only door. Never forward the port on a router.
11. **Email content is hostile in the browser too.** Every value that came from an email, a mailbox or a user is escaped before it is placed in the page. Nothing from an email is ever inserted as HTML.
12. **The server fails closed.** Every endpoint except status, health, setup, unlock and sign-in requires a signed-in session. Until first-run setup is completed with the one-time setup code, nothing else works.

## Accounts and sign-in (v0.17)

- **First run.** A one-time setup code is generated (or taken from `ENVELIQ_SETUP_CODE`) and written to `setup-code.txt` in the data folder with owner-only permissions; the log names the file but never prints the code. Setup creates the vault passphrase and the first administrator, then deletes the file. Setup can run only once.
- **Passwords.** Argon2id (OWASP parameters: 19 MiB, 2 iterations, 1 lane), self-describing hashes upgraded on sign-in when parameters change, at most two hashes computed at once. Unknown usernames take the same work and get the same error as wrong passwords. Minimum 12 characters.
- **Authenticator apps (TOTP).** RFC 6238 (verified against its test vectors), 30-second steps, one step of clock drift either way, and a used step can never be reused. The QR code is generated on the server so the secret never goes to a third-party QR service. The secret is stored only inside the encrypted user record.
- **Recovery codes.** Ten codes of about 50 bits each; only SHA-256 digests are stored; each works once.
- **Passkeys (WebAuthn).** Resident keys with user verification required, so a passkey sign-in counts as two factors. Bound to the exact public origin (look-alike sites cannot use them), challenges are single-use and expire in three minutes, and a signature counter that goes backwards (a cloned key) is rejected.
- **Single sign-on (OpenID Connect).** Authorization code flow with PKCE (S256), `state` and `nonce`; the provider's metadata issuer must match the configured issuer; ID tokens are verified against the provider's JWKS for signature, issuer, audience, expiry and nonce; `none` and HS* algorithms are refused; the provider and all its endpoints must use https. Accounts can be created automatically for allowed groups, administrator rights can follow a provider group, and an SSO identity is **never** attached to an existing account by matching email (a known account-takeover route). Users link SSO to their own account while signed in.
- **Second factor policy.** Required for administrators by default (or everyone, or optional). A user who must have one is held in an "enrol" state that can reach only the enrolment endpoints. The last second factor cannot be removed while the policy requires one. SSO sign-ins rely on the provider's own second factor.
- **Break-glass.** Administrators can always sign in with a password, even when password sign-in is limited to administrators, so a broken SSO provider cannot lock everyone out. The last active administrator cannot be demoted, disabled or deleted.
- **Sessions.** 64-byte random tokens in `HttpOnly`, `SameSite=Lax` cookies, `Secure` with the `__Host-` prefix on HTTPS, plus HSTS. New token on every sign-in (no fixation). 30-minute idle timeout, 12-hour maximum, 32 sessions at most. If an administrator turns on "Keep me signed in" (0 to 14 days, off by default, validated on the server) a person who ticks it at sign-in gets a session that lasts that many days instead; it is only given to a fully signed-in session (after any second factor), only while Enveliq opens its own vault from a key file, and the public status page reveals just whether the tick-box is offered. Only a remembered session is also written into the encrypted vault, under a SHA-256 hash of its token (never the token), with the person, the start time and the length; after a restart it is read back once the vault has opened from its key file, and it ends at its own limit. Ordinary sessions stay in memory only and end with a restart. Signing out, a password change, an administrator reset, disabling or deleting the person, and restoring a backup remove remembered sessions from the vault too, like any other session. The user record is re-read on every request, so disabling a user or changing their role takes effect immediately; password changes and admin resets sign out other sessions; locking the vault signs everyone out (a remembered sign-in comes back only when the vault opens again from its key file, which is the only mode in which it is offered).
- **Multi-step sign-in state** (pending second factor, passkey challenges, SSO state) lives in memory for at most ten minutes, is single-use, and allows five wrong codes before the password must be entered again.
- **Rate limits.** Password sign-in is limited per client and per username (10 per 5 minutes) with a global budget; setup and unlock have their own limits.
- **Cross-site protection.** SameSite cookies, an Origin allowlist, JSON-only request bodies, and a refusal of any state-changing request the browser labels `Sec-Fetch-Site: cross-site`.
- **Pages.** The sign-in, account and administration pages run under `default-src 'none'; script-src 'self'; style-src 'self'` with no inline code, and build every value into the page as text. The inbox page still uses inline code (see the recommendations below).
- **Storage.** User records (usernames, names, emails, password hashes, TOTP secrets, recovery digests, passkeys, SSO links) are encrypted under the vault master key. Signing in therefore needs the vault unlocked; unlocking does not sign anyone in.

## Tasks (v0.43)

- Each person's tasks are one encrypted record (`tasks:<user id>`) under the vault master key: the title and detail the summary suggested, the sender's name, a date and the state. No email text, mailbox link or attachment is stored there, and nobody else can read or change it (every route works on the signed-in person's record only).
- A task is found again from its email by a hash of the mailbox and message ids, so one email can never make two tasks, and a task the person removed is not made again.
- Tasks are made by the server from summaries it already holds; the AI model gets no new tools or access. The title and detail are cleaned of control characters and shown only as text in the page.
- Time zones come from the browser but are accepted only if they are a real zone name; anything else means UTC.
- A person can add a task of their own to any email (`POST /api/v1/me/tasks`). The server accepts it only for an email in one of that person's own mailboxes (anything else answers "not found"), cleans the title of control characters, limits it to 300 characters and the date to the coming year, allows at most 200 open tasks of this kind, and rate-limits it like the other task routes. It is stored in the person's own encrypted task record with the rest; no email text is copied into it. It is shown only as text.

## Reminders and outgoing requests (v0.43)

- Each person's channel settings are one encrypted record (`notify:<user id>`). Tokens, topics and webhook addresses are write-only from the browser: the page is told only that one is saved, and a blank box keeps the old value. The administrator's choices (`notify_admin`) hold channel switches and the list of allowed local addresses.
- Reminders carry the task title (or just "something is due" in private mode) and a link to Enveliq, never email text.
- Every outgoing request goes through one function (`mail/outbound.py`): the address is resolved and checked first; addresses on a private network, loopback or 100.64/10 need an administrator to list them (`ENVELIQ_NOTIFY_ALLOWED_HOSTS` or Administration, Reminders); link-local (cloud metadata), unspecified and multicast addresses are never allowed; public addresses need https; the connection is made to the checked IP (certificate still checked against the name); no redirects, no proxy, 10 s timeout, 64 KB reply cap. Error messages never include the reply body.
- Channel endpoints are session-protected and rate-limited (tests 10/min). Reminders are sent only while the vault is unlocked.

## Browser push and reminder emails (v0.44)

- Web Push messages are encrypted with RFC 8291 (aes128gcm) and signed with VAPID (RFC 8292). The implementation is checked against the RFC 8291 example vector in the tests. The VAPID signing key is one random P-256 key kept in the vault. Each device's push address and keys are stored encrypted, shown to nobody, and never returned by the API; a device that the push service reports gone is forgotten. Push addresses must be public https addresses (the same outbound rules as everything else).
- The Email channel can only write to a mailbox the person owns. Its emails carry `X-Enveliq-Reminder`, an HMAC of the message id with a key from the vault, and a sync skips only messages whose mark verifies, so a hostile sender cannot hide mail by adding that header.

## Calendar and To-do mirrors (v0.44)

- Settings live in one encrypted record per person (`sync:<user id>`). The CalDAV password and the Home Assistant token are write-only from the browser.
- **The calendar feed `/calendar/<token>.ics` is an exception to "every endpoint needs a session"**, like `/metrics`: calendar apps cannot sign in. The token is 24 random bytes (192 bits), shown once, stored only as a SHA-256 hash in a vault index, can be replaced or switched off at any time, and the feed answers 503 while the vault is locked. Wrong tokens get 404 and are rate-limited (30 per minute across all callers); reads are limited to 120 per minute. It contains only task titles (optional), details (optional) and dates, never email text, and carries `no-store` and `noindex` headers.
- CalDAV and Home Assistant calls use the same outbound rules as reminders (`mail/outbound.py`). Enveliq only touches the events and items it created.
- All feed text is escaped and folded per RFC 5545, so a task title cannot add calendar fields.

## Profile and password rules (v0.59)

- **Profile.** Name, email address, a short "about you" line and a picture are all optional and live in the person's own encrypted user record. Text is cut to its limit and stripped of control characters. The email address is never shown to other people.
- **Picture.** The browser shrinks it to a small square JPEG first, and the server accepts only what the bytes really are (JPEG, PNG or WebP, at most 120 KB). SVG and anything else is refused, so a picture can never carry a script. It is served with `X-Content-Type-Options: nosniff`, a sandboxing `Content-Security-Policy`, and only to signed-in people; the only profile data other people can ever fetch is that picture.
- **Password rules.** The administrator sets a minimum length (8 to 128, default 12) and how many numbers, capital letters, small letters and symbols a new password needs, and whether it may contain the username. The server checks them every time a password is set, changed or reset, and again the rules are forced into a safe range so a damaged setting can never lock people out. Existing passwords keep working until they are next changed. Passwords are still hashed with Argon2id and never logged.
- **Messaging.** See "Messages (v0.61)" below.

## Messages (v0.61)

- **Kept apart and encrypted.** Each conversation is its own record in the encrypted vault (`msg:thread:<random id>`), plus a small per-person index (`msg:index:<user id>`) that lists only that person's conversations. Messages never share a record with mail, summaries or tasks, and the messaging code cannot read those.
- **The server decides who may read.** Every call is checked against the signed-in session. Someone who is not in a conversation, an administrator included, gets the same "Not found" as for an id that was never used. There is no endpoint that lists or reads other people's conversations. Ids are long random numbers and are checked for their shape before anything is looked up.
- **What others learn about you** is your name and picture (only if you have not hidden yourself from the people list). Never your username, email address, mail or settings. Hidden people can still write to, and be answered by, anyone.
- **Plain text.** Text is cut to 2,000 characters, control characters are removed, and the page shows it as text only (checked with hostile input). Each person is limited to 30 sends a minute.
- **Disabled and deleted people.** A disabled person cannot use Messages, and messages to them are refused. Deleting a person removes their messages and takes them out of every conversation. Switching Messages off (for everyone, or for yourself) hides it without deleting anything.
- **Audit log.** Messages write nothing to the audit log, and no message text is ever logged.
- **Honest limit.** Messages are encrypted in the vault like everything else, but not end-to-end between people, because the server must count and deliver them. Whoever holds the server and the vault key could read them, as with all of Enveliq's data. Messages are never sent to the AI model.

## Unsubscribe button (v0.50)

- The address comes from the email, so it is hostile input. `backend/mail/unsub.py` accepts only a plain `http` or `https` address with a real public host name and no user name or password, no unusual port, no IP number, no `localhost`, `.local`, `.lan`, `.home.arpa` or other private name, no spaces, quotes or angle brackets, and at most 2000 characters. `javascript:`, `data:` and `file:` addresses are dropped. A `mailto:` link keeps only the address and a subject.
- Why the private-name rule matters: pressing the button opens the address from the person's own browser, so a link to a router at 192.168.x.x could change a setting at home. Those links are never shown.
- Enveliq never fetches the address. The page checks it again, then shows a plain link with `target="_blank"` and `rel="noopener noreferrer nofollow"`, so the sender's page cannot reach back into Enveliq and receives no referrer. It is an anchor the person presses, never opened by script.
- Only the checked address, its host name and where it was found are stored with the encrypted message summary (from the List-Unsubscribe header at sync time). A link found in the text of a message is worked out when View original is opened, and is not stored.
- Opening the sender's page tells the sender that the address is live. That is the same as pressing the link in any mail app.

## Is this really from them? (v0.67)

- The sender result is read from the **first** `Authentication-Results` header only, which is the one the person's own provider adds on arrival. A sender can write its own header lines, but they sit below it, so they are ignored. Nothing the sender wrote can make an email show "confirmed".
- Plain code, no AI. Nothing new is stored: the result is worked out from the headers when View original is opened, and the existing Be careful flag keeps only a fixed sentence and a host name (see Be careful flag, v0.66).
- "Confirmed" means the provider says the email passed its checks. It does not mean the email is safe, and the page never says it is. When the provider adds no result, the page says nothing.
- A Reply-To on another website is shown but only flags an email from a well-known name, because small businesses often use a free mail address for replies.

## The demo (v0.76)

- The demo is a static copy of the inbox page with invented sample mail. It has no server, no sign-in, no mailbox, no AI and no storage of its own, and it holds no real data of any kind.
- It is its own Cloudflare Pages project, separate from the website and from any Enveliq install. Its Content-Security-Policy forbids every network connection (`connect-src 'none'`, `default-src 'none'`) and allows only its own scripts, each by a fingerprint computed at build time. It cannot be framed and sends no referrer.
- The build refuses to produce a page that loads a script from a file, so the fingerprints always cover everything that runs. A browser check fails if the demo asks for anything beyond its own page and pictures.

## New-version notice

- About once a day, while the vault is unlocked and an administrator has opened Enveliq, the **server** asks GitHub for the newest published release (`https://api.github.com/repos/jlnau/enveliq/releases/latest`). No browser makes this request. It carries no cookie, token, user, mailbox, install or version information beyond a fixed `User-Agent`, and has an 8-second timeout and a 200 KB size limit.
- Only a version number made of digits and dots, and a link that starts with `https://github.com/jlnau/enveliq/releases/` and uses only plain URL characters, are accepted from the answer, and the page checks both again before showing them. Drafts and pre-releases are ignored. Everything else is discarded, so nothing from the answer can put other text or links in a page.
- The result is kept in memory only. A failed check is silent and is retried after an hour.
- Only administrators receive it (in `/api/v1/system`); nobody else does, and the public status page does not mention it. An administrator can switch it off (`PUT /api/v1/admin/update-notice`, audited as `update_notice_changed`), after which no request is made. It is on by default.
- This replaces the earlier statement that Enveliq makes no update check. The privacy notes, the privacy pop-up and the README now say so. Tests never contact GitHub.

## Install as an app and new-email alerts

- `/manifest.webmanifest` and the three icons are public and the same for everyone (name, colours, icon addresses). They hold nothing about any person or mailbox. The page policies allow a manifest only from Enveliq itself (`manifest-src 'self'`).
- A notification can name one email (`/?open=<mailbox id>:<email id>`). Both ids are random and mean nothing without a signed-in session; the server still decides what the person may see, and an email that belongs to someone else, or is gone, answers "not found" and the page says it is no longer in the list. The service worker follows only addresses on Enveliq's own origin, and the page ignores a message that names another website.
- New-email alerts are off until each person switches them on. They go only to the channels that person set up, through the same outgoing-request rules as reminders. By default the message holds only a count. If the person also allows details, it holds the sender's display name and the subject (control characters removed, length cut), never the sender's address, the summary or any email text. Services such as ntfy or a chat app can read what is sent, so that second switch says so. Browser push is encrypted before it leaves Enveliq.
- Nothing is sent during the person's quiet hours, only while the vault is unlocked, and at most one message per person per automatic sync pass. A failed send never stops a sync. Nothing about the alert is stored, and the report feed gets no new fields.

## The paperclip

- **What is kept.** Two small facts per email, inside the encrypted vault with the rest of the record: whether it has attached files (yes or no) and, once known, how many. The raw-attachment rules above are unchanged. What else is kept about files is in the next section.
- **How it is found.** When mail is first fetched, only its headers are read, so the yes or no is a guess from the email's own `Content-Type` (a "mixed" email, or one that is a file itself). It can be wrong. When the AI summary is made the whole email is already being read in memory, so the exact count (not counting pictures that are part of the text) replaces the guess; nothing extra is fetched and nothing else is kept.
- **Who sees it.** Only the person whose mailbox it is, like the rest of the record. An email with no known files shows no paperclip.

## Summaries of attached files

- **What is kept.** For each file of an email, inside the encrypted vault with the rest of the record: its name, kind, size, page count and the AI's summary (a one-line summary and a few headed parts). The file, its text and the model's raw answers are never stored or logged. The raw-attachment rules above are unchanged. A file name can itself say something private, so it is kept only inside the vault and shown only to the person whose mailbox it is.
- **How it is done.** The email is fetched once in memory, each file is read (PDFs by the isolated render service when one is set up, otherwise by a resource-limited child process; Word files by reading the document text directly with no macros run), the text is summarised, and everything but the summary is dropped. Limits: 25 MB per file, 20 files per email, 60 MB per email, about 25 minutes per file; when a file is longer, the summary says how far it got.
- **Untrusted text.** A file's words are passed to the AI as data between markers, with the same rules as email text: the AI is told never to follow anything written in it, has no tools, and does not calculate or decide. Every summary is labelled as written by the AI.
- **Cloud AI.** With a cloud AI service this feature is **off** until an administrator turns it on and ticks a box confirming that the words of attached files will be sent to that company. A local AI server runs it by default. The choice and who made it are written to the audit log, and an administrator can turn it off at any time.
- **Who sees it.** Only the person whose mailbox it is. Administrators cannot read file summaries. A record you may not open answers "not found".
- **If the email is handled meanwhile** (marked Reviewed, archived or deleted), the work stops and writes nothing more.

## The AI queue and mail held until ready

- **What is held.** A new unread email of a mailbox that uses AI summaries is stored with a flag, `ai_pending`, inside the encrypted vault, and the list endpoint leaves it out until its summary and its files' summaries are done (or have failed for good). The server decides this from the stored record, never the page. Mail that has been handled (reviewed, archived, binned or archived by a rule) is never hidden by it.
- **What the line holds.** The queue holds only ids (mailbox, email, person) and a plain failure reason. It never holds email text, file text or summaries; the text is read, summarised and dropped inside the job. It lives in server memory, and one person's jobs are listed only to that person. New-mail jobs are not counted against the 50-waiting limit for the Generate summary button, because nobody pressed anything.
- **Never hidden for good.** Failed jobs release their email after a few tries, a switched-off AI or mailbox releases everything waiting, and a restart re-queues what was waiting at the next sync or inbox view.
- **Alerts.** A new-mail alert for held mail is sent only when the mail is ready, to the same channels and under the same rules as before, with one message for the whole batch. It still holds only a count (or sender name and subject if the person allowed it).
- **Interactive AI.** Write help and the Agent chat are not queued; the page only shows that an answer is on its way. Nothing about them is stored by this change.

## What the public status page says (v0.79)

- Before anyone signs in, `GET /api/v1/status` says only whether Enveliq is set up and unlocked and which sign-in methods exist, plus (only while the vault is closed) whether it unlocks itself from a key file and why that failed. It never says the version, the encryption settings or the public address, so the page does not help someone choose a known weakness to try.
- The version and technical detail are at `GET /api/v1/system` for signed-in people (administrators get the encryption settings, the public address and the key-file unlock state). Nothing about the vault key itself is ever returned.
- Hiding these details is a small extra, not a protection on its own: the encryption is the same either way, and its settings are in this repository.

## Backup and restore, and Export my data (v0.75)

- A backup is a copy of the vault file as it is stored, so it holds only ciphertext. It does not include the key file (which lives outside the data folder) and the passphrase is never written into it. Anyone who gets a backup still needs the passphrase or the key file. Files are written with owner-only permissions in a folder only the Enveliq user can open.
- Only administrators can make, list, download, delete or restore backups. Names are checked against the exact pattern Enveliq writes, so no other file can be named. Download is audited.
- Restoring needs the vault unlocked, the administrator's own password again (through the sign-in rate limit) and a typed confirmation. A backup from a different vault is refused, and so is one that does not contain the administrator doing it. A copy of the current vault is saved first, the sign-in history is kept, and every session is ended afterwards.
- A backup holds everyone's data in locked form. Whoever has a backup and the passphrase or key file can read it, so keep downloaded copies as carefully as the key itself. Making a backup does not give administrators any way to read other people's mail or messages through Enveliq.
- Export my data gives a person only their own records, chosen by the signed-in session on the server. It never includes passwords, tokens, API keys, authenticator or passkey secrets, the calendar link, or another person's mail, and the export is audited without its content.

## Trips (v0.74)

- The AI reads each email once, with the same instructions and limits as every summary, and only copies what the email says. It is told not to work out any date or time, and Enveliq does not use a date it did not read from the email's words and check itself. Nothing the AI returns is trusted: every value is cut to a short length, control characters are removed, only known kinds and statuses are accepted, at most six bookings are taken from one email and a date far from the email's own date is ignored.
- What is kept, per person, inside the encrypted vault: the kind, provider, booking reference, flight number or property name, places, start and end dates and times, and a mark for each email already filed. **No email text, subject, sender address or link is kept.** The server answers only for the signed-in person; another person's record answers "not found". Administrators cannot read it.
- An email that carries a Be careful flag is never filed, so a fake booking change cannot put a trip on Home or in a calendar.
- Enveliq never contacts an airline, a hotel or a rental company, and the page has no link to one.
- In the person's calendar (only the one they set up for tasks, and only while the Trips calendar switch is on) each booking is an event that holds the places and the booking reference, and only "Enveliq trip" when titles are private. Events are rebuilt from the current list, so a removed, cancelled or finished booking, or switching the calendar off, takes them out. The private feed address, CalDAV password and Google connection are the ones already described for tasks.
- An administrator can switch the feature off for everyone, and each person for themselves; while it is off nothing is filed and nothing goes in a calendar.

## Subscriptions and free trials (v0.73)

- The AI reads each email once, with the same instructions and limits as every summary, and only copies what the email says. It is told not to work out any date, and Enveliq does not use any date it did not work out itself. Nothing the AI returns is trusted: every value is cut to a short length, control characters are removed, only known kinds and billing periods are accepted, and a date far from the email's own date is ignored.
- What is kept, per person, inside the encrypted vault: the service name, the price as written, the billing period, the renewal and trial dates, whether it was cancelled, one web address and a mark for each email already filed. **No email text, subject or sender address is kept.** The server answers only for the signed-in person; another person's record answers "not found". Administrators cannot read it.
- An email that carries a Be careful flag is never filed, so a fake renewal notice cannot put a card on Home or send a reminder.
- The only link is the home page of the domain the email came from, and only when it is a plain public address (the same rule as the Unsubscribe link) that is not a mail or payment service. It is shown with the website's name and opens as a plain link in a new tab with `noopener noreferrer nofollow`. Enveliq never contacts the company.
- Reminders use the person's own reminder channels. With "Keep titles private" on, the message holds only a count. The service name is otherwise sent only to the channels the person set up.
- An administrator can switch the feature off for everyone, and each person for themselves; while it is off nothing is filed.

## Search everywhere (v0.72)

- The search runs in the page, over the cards, tasks, orders and notes that the server already sent to the signed-in person. Nothing new is asked of the server or stored, no mailbox is read, and email text is never searched. Another person's data is never in the page, so it cannot be found.
- Matches are drawn as text (escaped), never as page code.

## Snooze (v0.71)

- Snooze changes only Enveliq's own record of an email (a time stored with the other encrypted details). The real mailbox is not touched and nothing new is read from it.
- The server answers only for the mailbox's owner (anyone else gets "not found"), accepts only a time between 30 seconds and 366 days ahead, and refuses to snooze an email that is not in the inbox. Each change is audited with ids and time, never email text.

## Forward to check (v0.70)

- An administrator chooses one of their **own** mailboxes as the check address and lists who may use it. No other person's mailbox can be chosen. Only that administrator can change it. The check mailbox is not read as an inbox: it is not synced, nothing from it is kept for anyone, and it is hidden from the inbox page.
- **Only an exactly listed address is answered.** Everyone else is ignored and never answered, so the address cannot be used to send mail at strangers. A sender the provider says was forged (`dmarc=fail`) is ignored too. Mailing lists, bulk mail, other auto-replies and robot senders are ignored, and every answer is marked automatic (`Auto-Submitted`), so two robots cannot start a loop. Limits: 10 answers a day per person, 60 a day for the address. The message is marked read before it is answered, so it is never answered twice.
- The forwarded email is read once, in memory, and **never stored or logged**. The answer is a fixed sentence or the reasons the Be careful flag uses (host names, never the rest of a link). Plain code, no AI. The answer never says an email is safe: "Nothing odd found" is not a promise.
- Reading and answering use the mailbox's own login, the same as any mailbox in Enveliq. The settings change is written to the audit log without any address.

## Unsubscribe hidden on flagged emails (v0.69)

- On an email marked Be careful the page does not offer Unsubscribe at all, so a person cannot reveal the sender's address-check link by accident. This changes only what the page offers; the stored unsubscribe address and the rules that decide which address is safe to open (v0.5x, `unsub.safe_url`) are unchanged.

## Where does this link go? (v0.68)

- Plain code, no AI. The list is worked out from the whole email when View original is opened and is **not stored**; the stored message holds no link address.
- Enveliq never fetches or follows a link. A link opens only when the person presses **Open…**, sees the website it goes to, and presses the second button. It is a plain anchor with `target="_blank"` and `rel="noopener noreferrer nofollow"`, so the other page cannot reach back into Enveliq and receives no referrer.
- Only plain public web addresses can be opened (the same rule as the Unsubscribe link). Number addresses, private or internal names, odd ports, `user:password@` forms, `javascript:` and every other kind of link are listed with a reason, or left out, and have no way to open. The page checks the address again before it shows the button.
- The page shows the website name and what the email calls the link, never the rest of the address (which can hold a personal token). The address is in the response only so the button can work; it is sent only to the signed-in owner of the message, with the rest of the original.
- **Addresses in the email text.** In View original, a web address in the text is clickable only if it is exactly one of the links the server already vetted as openable and did not flag. A click only shows the same question ("This goes to <website>. Open it in a new tab?"); nothing opens until the second button, which is the same plain anchor with `target="_blank"` and `rel="noopener noreferrer nofollow"`. The text and the website name are put in the page as text, never as markup, and the address is checked again in the page before it is used. Addresses that were not vetted, and every address in an email marked Be careful, stay plain text. The text already showed these addresses in full, so nothing new is shown.
- Opening a link tells the sender's website that someone opened it, the same as in any mail app. On an email marked Be careful the page says the email looked odd and asks again.

## Be careful flag (v0.66)

- The flag is found by plain code in `backend/mail/scamcheck.py`. The AI is not asked and never decides: it only ever sees the email text, as before, and nothing it writes feeds the flag.
- The flag does not block, delete or hide anything. It adds a note in plain words and a second step on **Unsubscribe**. A flag can be wrong in either direction; the wording says what looks odd and does not say that an email is a scam.
- Only host names (such as `evil.example`) and a fixed sentence are stored, inside the encrypted message record, at most four per email. A whole link is never stored, because it can carry a private token. The email's text is not stored.
- Header checks run at sync from the headers already read, plus `Authentication-Results` (added to the fields fetched). Link checks run only when the email is already being read (summarising or View original); View original returns them without storing them.
- The reasons are shown as text in the page, never as markup. A reason that contains `<img onerror=...>` is shown as words and runs nothing (`scripts/check_scam_warning.mjs`).
- Enveliq still never opens, fetches or follows any link in an email. The only link it shows is the newsletter's own Unsubscribe link, behind the checks described under Unsubscribe button (v0.50).
- Not covered: a scam that uses only ordinary-looking links to a site that is not a well-known name, or text asking for money. This is a helper, not a guarantee.

## Shipping (v0.51)

- **What is kept.** One encrypted record per person (`ship:<user id>`): shop, order number, tracking number, carrier, a few words about the items, status, expected date, and the date and subject of each email that belonged to the order. No email text, no addresses, no attachments, and no message or mailbox ids (an email is remembered only as a short one-way hash, so the same email is not filed twice). Arrived orders are forgotten after 14 days, quiet ones after 90, and "Not an order" answers after 90.
- **No extra AI call.** The facts come from the same summary call as before. Nothing more is sent to the model, and nothing from the model is trusted: every value is cut to a short length, stripped of control characters and shown as plain text only.
- **Links.** The Track button comes only from a short fixed list of carrier addresses; the tracking number is the one part that varies and is limited to letters and digits. It opens from the person's own browser in a new tab with `rel="noopener noreferrer nofollow"`. Enveliq never contacts a carrier or a shop. The page shows a link only if it starts with `https://`.
- **Who can see it.** Only the signed-in person, over a session route with a rate limit and `Cache-Control: no-store`. Order ids are random and checked against a fixed pattern; another person's order is a 404. The administrator and the person can each switch it off, and when it is off nothing is read or kept.

- **Parcels typed in by hand.** `POST /api/v1/me/shipping` adds an order in the person's own `ship:<user id>` record, with the same limits as an order made from an email: the sender is cut to 60 characters and stripped of control characters, the tracking number must be 8 to 40 letters or digits and is not added twice, the status is one of four fixed words, and the list has the same cap as before. Changing the status or removing such an order works only on orders marked as entered by hand; for orders made from emails the server answers that the emails decide. Another person's order answers "not found".

## Tags (labels)

- **What is kept.** A list of tag names on each email's encrypted record (at most 20 per email, 40 characters each), removed with the email. The mailbox's own list of tags is read live when the Tags window opens and is not stored. No email text is read to do this, and tag names are not sent to the AI.
- **Who can use it.** Only the signed-in owner of the mailbox, over session routes with a rate limit and `Cache-Control: no-store`; another person's mailbox or email answers "not found". A switch off (administrator or person) answers "switched off". Bodies are strict (no extra fields, the on/off value must be a true boolean).
- **Changes in the real mailbox.** Adding or removing a tag is the only write, made over the mailbox's existing connection and rules (same destination checks, pinned certificate, one operation per mailbox at a time). Tag names are checked on the server (length, characters, no `/`, quotes or control characters, not a folder name such as Inbox or Trash) and sent to the mailbox quoted and encoded, so a name cannot add a command. Removing a Proton label deletes only the copy in that label's folder; the email itself is never moved or deleted by this feature.
- **Audit log.** Records that a tag was made, added or removed and on which email, never the tag's name.

## News feeds

- **What is kept.** One encrypted record per person (`rss:<user id>`): feed addresses and names, and for the newest 25 entries of each feed a title, up to 1,500 characters of plain text, a link, a date and a new flag. At most 20 feeds per person. No page is stored.
- **Who can see it.** Only the signed-in person, over session routes (`/api/v1/me/rss`) with rate limits (a tighter one on anything that contacts another site) and `Cache-Control: no-store`. Feed ids are random and checked against the person's own record; another person's feed answers "not found". Administrators cannot read feeds. The audit log records that a feed was added, never which.
- **Contacting other sites.** Only through `mail/outbound.py`: the address is resolved and pinned, private or loopback addresses need the administrator's local allow list, no proxy, a 10 second timeout, and the reply is cut at 512 KB. Redirects are followed by hand (at most 3) and each target is checked again, so a feed cannot send Enveliq to an address it would not call directly. The request carries no cookies or sign-in details.
- **Untrusted text.** A feed is written by a stranger. Documents with a document type or entity declarations are refused (the usual XML tricks); tags, scripts and control characters are removed, text is cut short, and it is shown only as plain text (the page escapes it). A link is kept only if it is an ordinary http(s) address with no user name, and opens with `rel="noopener noreferrer"`. The AI is not involved.
- **No third-party requests from the page.** The page never contacts a feed's site: the server does, and the person's own browser opens a link only when they press it.
- **Kept for 14 days.** An entry older than 14 days (by its own date, or the day it was first seen) is removed from the record on the next check, and only its short id is remembered so the site cannot bring it back.

## Notes from other services (the bell)

- **A key, not a cookie.** Another service (Home Assistant, for example) connects to the WebSocket door `/api/v1/inbound/ws` and shows a key the person made for themselves. The key is 32 random bytes, shown once when it is made and never sent back; only its SHA-256 hash is kept, in the encrypted vault. A new key replaces the old one at once, even on a connection that is already open, and removing it, disabling the person or deleting them stops it. A key belongs to one person and can only add notes to that person's own list: it cannot read mail, tasks, messages or anyone else's notes, and it is not a sign-in.
- **No browser power.** The door ignores cookies. A connection that carries an `Origin` header from a site Enveliq does not list is refused, so a web page on another site cannot use it. Wrong keys get the same short answer whatever the reason (unknown, replaced, disabled), and tries are rate limited per network address.
- **The local address exception.** Every page and API route only answers to the host names Enveliq was told about. The WebSocket door and the webhook `POST` alone also answer when the Host is an address on a private network (`192.168.x.x`, `10.x.x.x`, `172.16.x.x` to `172.31.x.x`, `fc00::/7`, this machine); link-local addresses (including cloud metadata addresses) and public addresses are refused. This lets a service on the same network reach Enveliq when the public name sits behind Cloudflare, without opening anything else on that address. The key is what protects the door; the address is not trusted.
- **Limits and untrusted text.** At most 4,000 characters per message (the server also refuses larger frames), 30 notes a minute per person, 5 open connections per person, 100 notes kept per person, and a connection that says nothing for two minutes is closed. A note is data from outside: control and direction-changing characters are removed, it is cut to its limits, stored as plain text in the person's own encrypted record (`inbox:<user id>`) and shown only as text (never as a page or a link), always labelled with where it came from.
- **The webhook door.** `POST /api/v1/inbound/webhook` takes the same key and adds the same kind of note, for tools that cannot hold a WebSocket open. The key is read only from the `Authorization: Bearer` header, never from the address (which would end up in logs) or the body. A missing, wrong, replaced, removed or disabled-person key all answer the same `401`; the body must be JSON (`415` otherwise) and at most 4,000 characters; it shares the 30-notes-a-minute limit per person with the WebSocket door and has its own limit per network address. Cookies are ignored, so a web page cannot use it for a signed-in person. On the local network address only this `POST` and the WebSocket door answer; every other route there is still refused. Tests in `tests/test_inbound.py`.
- **Audit log.** Records that a key was made or removed and by whom, never the key or the notes.
- **Dependency.** The `websockets` library (pinned) lets the server speak WebSocket.

## Shipping carriers added by the household (v0.62, editing v0.63)

- **One shared list.** Any signed-in person using Shipping can add a carrier (a name and a tracking-page address); everyone's Track links then use it. The list is one encrypted record (`ship:carriers`), at most 40 entries. The person who added a carrier, or an administrator, can remove it; only an administrator can see the saved addresses and edit a carrier (the same address rules are checked again); others get a refusal. Adding and removing are in the audit log (who and when, not the address). Only the carrier names, not the addresses or who added them, are sent to other people's pages.
- **What an address may be.** Checked on the server every time, and again whenever the list is read: `https` only, a normal public host name (no IP number, no `localhost` or private names, no port, no user name or password), no spaces, quotes or angle brackets, at most 300 characters, and exactly one `{number}` that is not part of the host name. So a shared carrier can only send the person's browser to a public website with the tracking number in the path or query. The tracking number is limited to letters and digits.
- **Still opened by the person's browser.** Enveliq never fetches these addresses. The page shows them only when they start with `https://`, in a new tab with `rel="noopener noreferrer nofollow"`. **Track all** simply presses the same links, up to 10 at a time.
- **Honest limit.** Everybody on this Enveliq can add a carrier that everybody else's Track button will use, so add only people you trust to use Shipping, as with the rest of a household tool.

## Shipping notes, links and your place (v0.53)

- **Notes.** A note on an order is plain text you type, cut to 500 characters, stored with the order in the same encrypted record and shown as text only. It is not sent to the AI model.
- **Links to emails.** Each matched email on an order carries only its short one-way hash. The page works out the same hash for the emails it already has in memory and, where one matches an email still in the inbox, makes the subject open that email. Nothing is looked up on the server and no message id is stored.
- **Your place after a refresh.** The page you are on is kept in the address bar (after #/). Which emails are open is kept in this tab's session storage as the mailbox and message ids; it is cleared when the tab closes and is never sent anywhere.

## Waiting for reply (v0.52)

- **Off until chosen.** A mailbox is only read when its owner switches Waiting for reply on for it (a plain warning is shown first), the person's own switch is on, the administrator's switch is on and an AI model is set up. Nothing in the Sent folder is read otherwise. Even then, only mail sent after the switch was turned on is shown to the model: the first look at a mailbox records what is already in Sent as old (as short one-way hashes) and reads none of it. A mailbox left unwatched for 7 days starts fresh the same way.
- **What the model sees.** Each newly sent email is shown to the configured AI model once, with one question, in the same way as a summary: the text is marked as data, control characters are removed, and the reply must be a small JSON answer (`waiting` true or false and a one-line `ask`) or it is ignored. Mail you sent to yourself, to more than ten people, or from Enveliq's own reminders is never shown to the model. If the model is a cloud service the email text goes there; that is why this is a separate, per-mailbox choice.
- **What is kept.** One encrypted record per person (`wait:<user id>`): for each note the mailbox id, the sent email's Message-ID (needed to recognise a reply), up to three recipients, the subject, the date, the one-line ask and the state. Never the email text. Emails already judged are remembered only as a short one-way hash for 30 days, so none is shown to the model twice. Closed notes are forgotten after 7 days, unanswered ones after 30.
- **By hand.** The person can press Follow for a reply on any email in the Sent page (any age). That one email is read from the mailbox and shown to the model once, on their request, and needs the same feature switch.
- **Replies.** The inbox is read for headers only (`In-Reply-To`, `References`) over the last 14 days. No inbox text is read or kept.
- **Who can see it.** Only the signed-in person, over session routes with a rate limit and `Cache-Control: no-store`. Note ids are random and checked against a fixed pattern; another person's note is a 404. Everything shown is plain text.

## Published images

- **When and what.** A job in the GitHub Actions workflow builds and publishes the two images (`enveliq` and `enveliq-render`) only when the maintainer publishes a **GitHub Release**, and only after the tests, browser checks, hardened-container check and dependency scan have all passed. The release tag must match the version in `backend/version.py`, or the job stops. Merging into `main` and opening pull requests never publish.
- **Credentials.** The job signs in with the run's own temporary `GITHUB_TOKEN`, with `packages: write` granted to that one job and nowhere else (the workflow default stays read-only). No long-lived publishing secret exists.
- **Who can pull.** The images are labelled with the repository they come from. Whether a person can pull them depends on the package's visibility on GitHub. If the packages are public, no sign-in is needed. If a package is private, the server needs a separate, read-only token (`read:packages` only), which is stored in the person's own control-panel settings (for example Arcane) and never in this repository.
- **Nothing secret in the image.** The images contain only the code that is in the repository; the vault key, setup code and all data come in at run time.

## Hermes chat (v0.46)

A plain chat with the AI model an administrator set up. It gives the model nothing but what the person types.

- **No reach into mail or settings.** The chat sends only the person's own messages and a fixed instruction. It never includes email text, summaries, tasks, addresses or settings, and the model has no tools, so it cannot read or change anything in Enveliq. Whatever the model replies is stored and shown as plain text (escaped, never page code, links not made clickable) and is never treated as an instruction.
- **Sessions and limits.** `GET /me/agent`, `POST /me/agent/messages`, `PATCH` and `DELETE /me/agent/chats/<id>` need a signed-in, unlocked session and are `no-store`. 20 messages per minute per person; a message is at most 2,000 characters; chat ids must match a fixed pattern; unknown fields are refused. A chat id only ever opens one of the caller's own chats.
- **Private saved chats.** One encrypted record per person (`agent:<user id>`) in the vault holding up to 40 chats of up to 100 messages each, never shared between people. A person can reopen, rename or delete any of their chats; deleting removes it at once. A message the model could not answer stays in its chat so nothing typed is lost. The model is shown only the newest 20 messages of the open chat, never another chat.
- **Own-agent mode (v0.47).** An administrator can switch the chat (Administration, Agent chat) from Enveliq's helper to the person's own agent. Enveliq then adds no instructions and sends only the chat messages, with a longer wait (three minutes) because an agent may use tools first. Enveliq still never includes email, tasks or settings, but it cannot limit what the agent itself can do, and everyone allowed uses the same agent. The setting is `agent_settings` in the vault, changed only through `PUT /admin/agent` (administrators only, audited), and the default is the helper mode, open to everyone. "Administrators only" is checked by the server on every chat request.
- **A separate agent address (v0.56).** Administration, Agent chat can give the chat its own address, model name and access key, used only in own-agent mode. It follows the same address rules as the AI model (a private address, or a host listed in `ENVELIQ_LLM_ALLOWED_HOSTS`; no redirects). The key is kept in the vault (`agent_settings`), is never returned by any request (the page only learns that one is saved), and is never written to the audit log. Changing it needs an administrator; the test button is rate limited.
- **Slow agents (v0.57).** The model is asked on a background thread, so a message returns at once (or after at most 20 seconds when the answer is quick) and the page checks back. Only one question per chat is open at a time (a second one is refused with HTTP 409), a question unanswered after four minutes is shown as failed, and the chat keeps only a short, plain failure sentence (never the model's raw reply or the address). Nothing about this changes what is sent to the agent.
- **Same AI rules.** It uses the same configured server and the same address and host rules as summaries, so it can only reach the places the administrator allowed (`ENVELIQ_LLM_ALLOWED_HOSTS` applies). The access key is never sent to the browser.

## Google Calendar (v0.45)

- Connection uses OAuth 2.0 authorisation code with PKCE and a one-use state held server-side (like Microsoft sign-in). The only scope is `calendar.app.created`: Enveliq can touch only calendars it made. The client secret (administrator) and each person's refresh token are stored encrypted, write-only, and revoked at Google when disconnected. All calls go to Google over https through `mail/outbound.py` as public addresses.
- Emails with an open task are protected from removal by sync and by the 14-day clean-up of listed mail.

## Cryptography

- Argon2id for passphrase-based key derivation (time cost 3, 64 MiB, 4 lanes), provided by `cryptography` and checked against the RFC 9106 test vector. The parameters are stored with the vault so they can be strengthened later. Only one derivation runs at a time, so bursts of unlock attempts cannot exhaust memory.
- AES-256-GCM for authenticated encryption.
- Random 256-bit master key.
- Random 256-bit per-account Data Encryption Key (DEK).
- Per-account DEKs are AES-GCM wrapped by the master key.
- Message records reuse the owning account DEK and unique nonces/AAD.
- Global administrator configuration and audit records are encrypted under the master key.
- SQLite `secure_delete=ON`, `synchronous=FULL`, and `temp_store=MEMORY`.
- SQLite/WAL database contains random identifiers, salts, nonces and ciphertext, not mailbox plaintext.
- The process runs with `umask 077`; the data directory must be owned by the service user and must not be a symlink.

## What remains intentionally unsolved in this prototype

This is a secure backend foundation, not a claim of a production security certification.

Before a stable release we still need:

- Home Assistant authenticated principal adapter replacing the development principal.
- Home Assistant custom integration authorization tests against real HA users.
- A Home Assistant AppArmor profile and hardened App manifest.
- SQLCipher whole-database encryption as an additional defence-in-depth layer if practical in the target image. Application-level encryption remains required even with SQLCipher.
- RAM-backed isolated attachment parsing worker with CPU, memory, time and file-size limits and no network.
- TLS/mTLS for any non-loopback internal service boundary.
- OAuth PKCE/state callback implementation for Gmail and Microsoft.
- SSRF-safe destination validation for custom IMAP and LLM endpoints at connection time (v0.13 validates the format of hosts and URLs; DNS-rebinding-safe checks belong in the provider adapters).
- Strict production CSP with separately bundled JS/CSS and no `unsafe-inline`.
- Fuzzing, DAST, CodeQL/Semgrep, secret and container scanning and an independent security review. (Dependency scanning runs in GitHub Actions since v0.18.)

## Recovery model

The initial product should use manual unlock after a backend restart. The unlock passphrase is never persisted. The master key is held only in process memory while unlocked and is overwritten on lock as far as Python permits.

A later unattended mode should use a TPM, HSM or external secrets vault. We should not achieve automatic restart by writing the unwrapping secret next to the encrypted database.

## Attachment architecture added in v0.8

Raw attachments are treated as hostile, transient input and are **never persistent application data**.

### Processing path

1. The provider adapter fetches the requested MIME part from the source mailbox.
2. A strict source-size limit is enforced before parsing. The initial design target is 25 MB per attachment.
3. The original bytes enter an isolated worker backed by RAM/tmpfs only. The worker has no Home Assistant API access, no provider credentials beyond the single fetch result, no shell integration, and no arbitrary outbound network access.
4. File type is verified from content rather than trusting the filename.
5. The worker extracts text for LLM analysis and/or creates a safe preview derivative.
6. Raw bytes are destroyed as soon as extraction/rendering completes.
7. Only encrypted attachment metadata and the encrypted AI summary remain with the review record.

### Viewer path

The frontend does not receive the original PDF/Office document by default.

- PDF: render pages in the isolated worker and send safe page images to the browser.
- JPEG/PNG/WebP: decode and re-encode before display, stripping metadata and non-image payloads.
- Plain text: validate/decode and render as escaped text.
- Office documents: show extracted text in v1. Direct Office-document rendering is not required for v1.
- HTML and SVG: never render as active document content.
- Executables and archives: not previewed.

Safe preview derivatives may live in a bounded **RAM-only preview lease** for up to five minutes so paging around a PDF does not repeatedly fetch and render the same page. The v0.8 `PreviewLeaseStore` defaults to a 10 MB per-preview limit and 64 MB global RAM cap. Evicted/expired buffers are overwritten before references are released as far as Python permits.

Browser responses for preview data must use `Cache-Control: no-store`, same-origin authorization, MIME allowlisting and `X-Content-Type-Options: nosniff`. Production CSP must not permit attachment-controlled script execution.

### Review-item resolution

When a review item becomes **Reviewed, Archived, Binned or Expired**:

- temporary preview leases for that message are purged;
- encrypted attachment metadata and summaries are deleted: for Binned and Expired the whole retained record goes; for Reviewed and Archived see "Reviewed and Archived lists" below;
- no attachment file needs deleting from Home Assistant storage because no original attachment was stored there;
- the original attachment continues to exist only wherever the source mail provider keeps the source email.

For Archive/Bin, provider action success must happen **before** the local retained review record is purged. This preserves retryability if a mail-provider action fails.

### Encrypted locator

A retained attachment may contain an opaque provider locator such as an IMAP MIME part identifier or provider attachment ID. That locator is encrypted inside the message record and is stripped from browser API responses. It is only used server-side to fetch the original attachment on demand while the review item remains active.


## Notification target security

Notification destinations are Home Assistant entity identifiers, not arbitrary URLs or executable commands.

For script delivery, only entities in the `script` domain are valid targets. For direct notification delivery, only Home Assistant `notify` services exposed through the authenticated HA integration are valid. The processing App does not execute shell commands and does not accept user-supplied webhook URLs as notification targets.

Notification payloads are constructed from validated application fields. Email content is treated as data and cannot select or alter the notification service/script target.


## Viewing the original email (v0.16)

The retained record holds only the encrypted summary and metadata (invariant 4). "View email" fetches the original from the mailbox at the moment it is opened, using the encrypted `source_locator`, and discards it when the viewer closes.

- The locator is encrypted at rest and stripped from every browser response.
- The original is shown as text. HTML is never rendered as active content, remote images are never loaded (they are commonly used as tracking pixels), and links are shown as text. A link opens only after the person chooses it and is shown where it goes (see Where does this link go?, v0.68).
- When HTML rendering is added later, it must be sanitised server-side and shown in a sandboxed frame with no scripts, no forms and a CSP that blocks remote loads.
- Nothing from the original is written to disk, logs or the vault.

## Drafts (v0.90)

A draft is an email a person started and has not sent. It is stored as one encrypted record per person (`drafts:<user id>`) under the vault's master key, like the signature and saved replies. It holds only what the person typed (kind, To/Cc/Bcc, subject, their own words) and which mailbox and email it answers. It never holds the original email's text or any attachment. Only the signed-in owner can list, change or delete their drafts (another person's draft id answers "not found"). While an email is open the page saves it as a draft every few seconds and when the page is closed (over the same signed-in, encrypted path; nothing is kept in the browser). Drafts are removed 14 days after the last save (the record is cleaned each time the list is read or a draft is saved), included in **Export my data** for that person only, and removed with the person. Line breaks and control characters are removed from the subject and addresses, and a draft is never sent by itself: sending goes through the normal send path and its checks. Responses are `Cache-Control: no-store`.

## Replying and aliases (v0.16)

Replies must work with alias services (Proton Pass, SimpleLogin, Firefox Relay, Apple Hide My Email, DuckDuckGo) and with multiple sending addresses.

**Who the reply goes to.** The Reply-To address if present, otherwise From, exactly as received, and only that address by default. **Reply all** (shown only when the original has people on Cc) adds the other people the email was sent to and everyone on Cc, from addresses saved when the email was read; the person can edit the list before sending. For an email that arrived through an alias service this is a long reverse-alias address; replying to it is what makes the service deliver the reply from the alias. Enveliq never shortens it or swaps it for the contact's real address.

**Who the reply comes from.**
1. If the email was delivered to one of the account's sending identities (for example a Proton custom-domain address or a Gmail "Send mail as" address), the reply comes from that address.
2. If it arrived through a forwarding alias, the reply comes from the mailbox's own address. The alias service rewrites the sender to the alias, so the recipient never sees the real address. Sending directly *as* the alias would bypass the service and fail or expose the mailbox.
3. Otherwise the reply comes from the mailbox's main address, and the composer says why.

The sending identities come from the provider at connection time (Proton Bridge address list, Gmail send-as list, Microsoft Graph). The backend must re-check at send time that the chosen From is one of them; the browser's choice is never trusted on its own.

**Safety rules for sending.**
- A person always presses Send. The LLM can suggest wording but has no ability to send, and email content can never trigger a send (invariant 6).
- Every value that goes into an outgoing header (To, From, Subject, In-Reply-To, References) is rejected if it contains CR, LF or NUL, which blocks header injection (for example a hidden `Bcc:` line in a crafted Reply-To). Enforced in `ReplyContext` today; the send path must enforce it again.
- In-Reply-To and References are set from the original's Message-ID so the reply threads correctly and reply detection can resolve the review item.
- **Other people's addresses (v0.90).** To make Reply all work, `ReplyContext` keeps the Cc and other To addresses of an email (at most 20 each, bare addresses without names, never our own addresses), inside the encrypted vault like the rest of the reply context. They are never sent to anyone but the signed-in owner of the mailbox, and are removed with the email. Addresses that do not look like email addresses, or contain line breaks, are dropped when saving so they can never stop a reply.
- **Replies quote the original (v0.90).** Every reply and Reply all carries the sender's whole email as quoted text under the person's words. The server fetches it from the mailbox when Send is pressed (or the person presses "Put the original in my message", which reads it the same way for that person only), builds the quote itself and does not store it or log it. The page can only say that the original is already in the message (`add_original`); it cannot supply the quoted text of another email, and the same ownership checks apply (a record the person may not open answers "not found").
- **Forward (v0.90).** The original is fetched from the mailbox when the person presses Send, quoted and attached by the server, and not stored. Forward, Reply all and Cc/Bcc recipients go through the same checks as New email: header-injection rejection, at most 50 people, repeats removed, Bcc only in the envelope, 10 files and 10 MB. A record the person may not open answers "not found", so another person cannot forward or reply to it. The audit log records the kind (`reply`, `reply_all`, `email_forwarded`) and the number of people, never an address or any text.
- Sending is rate-limited per user, and the provider keeps the sent copy in its Sent folder; Enveliq stores only an encrypted audit event (who, when, which item), never the reply text.
- Addresses that look like no-reply mailboxes produce a warning, not a block.

## Setup code (v0.65)

- **A weak setup code is never used.** If `ENVELIQ_SETUP_CODE` is empty, still contains the placeholder from the install file ("change-me"), or is shorter than 16 characters, Enveliq ignores it, writes a warning to its log, and makes a random code instead (written to `setup-code.txt` in the data folder, as before). This stops a guessable code from letting a stranger who can reach the page claim a new server.
- **Links to the guides** open GitHub in a new tab with `noopener noreferrer`. Nothing is requested from GitHub until a person clicks, so the "no third-party requests when a page is viewed" rule still holds.

## Writing help (v0.64)

- **The AI only suggests.** Nothing it writes is sent, saved to a mailbox or put in the person's reply box without a button press. Only the reply and send routes send mail, exactly as before.
- **What the model sees.** The email being answered (fetched by the server from the mailbox, cut to 6,000 characters, attachments never) and the person's draft, as data between markers with the rule never to follow instructions inside them. The model has no tools. The page never chooses what the model reads, and a mailbox that is not yours answers "not found".
- **Nothing is kept.** The email, the draft and the suggestion are not stored or logged. The audit log records only that it was used (who, when, which kind). The only thing saved is a small encrypted per-person record: on or off, and the person's own writing instructions. It is removed when the person is deleted.
- **Shown as text only**, labelled "Suggested by AI". Model output has control characters removed and is never treated as markup.
- **Off by default.** Each person must turn it on, and an administrator can switch the feature off for everyone. If the AI model is a cloud service the email and draft go to it; Settings says so plainly.
- **Honest limit.** A model cannot be made immune to a hostile email. What limits harm is that its output is only ever shown to the person, who presses Send, and who sees a check first when AI wording is involved.

## Security review — v0.13 (2026-10-08)

A full review of the backend, server configuration and UI prototype. Every finding below was first demonstrated with a working attack against v0.12, then fixed, and is now covered by a regression test in `tests/test_hardening.py` (UI: `scripts/check_prototype_injection.mjs`).

| # | Severity | Finding in v0.12 | Fix in v0.13 |
| --- | --- | --- | --- |
| 1 | Critical | Email subject, sender, summary, task text and attachment names were inserted into the UI as HTML. A crafted email could run script in the user's session (about 40 injectable fields). Inside Home Assistant this could act as the signed-in user. | All data escaped with `esc()` before it enters the page; browser test confirms no payload runs in any view. |
| 2 | High | `ENVELIQ_DEV_MODE=0` still used the development identity (an administrator), so "production" mode had no real authentication. | Backend refuses to start unless `ENVELIQ_DEV_MODE=1`. |
| 3 | High | Parallel wrong passphrases all got checked before the first failure was recorded (16 of 16 guesses accepted). | Attempts are counted before checking, atomically; per-client limit 5 and a global limit of 20 per 5 minutes. |
| 4 | High | Uvicorn trusted `X-Forwarded-For` from localhost, so any local process could rotate its apparent address and dodge the unlock limit. | `proxy_headers=False`; non-loopback bind refused unless explicitly allowed. |
| 5 | High | Disconnecting an account always crashed and rolled back, leaving the account, its encrypted credentials and messages in the database. | Checkpoint moved outside the delete transaction; messages deleted explicitly. |
| 6 | Medium | Validation errors (422) echoed submitted values, including passphrases and passwords. | Error bodies carry field location and message only. |
| 7 | Medium | `PATCH` with `"password": null` silently wiped the stored credential. | null means "unchanged"; credentials can be replaced but never cleared by PATCH. |
| 8 | Medium | Any signed-in user could lock the vault for everyone. | Locking is administrator-only. |
| 9 | Medium | Idle auto-lock left decrypted attachment previews in RAM, and the key stayed in memory until the next request. | Lock listeners wipe previews and sessions on every lock; a watchdog thread enforces the idle timeout. |
| 10 | Medium | Chunked request bodies bypassed the 1 MB limit; a malformed `Content-Length` crashed the request. | ASGI guard enforces the limit while streaming (413) and rejects bad headers (400). |
| 11 | Medium | The saved attachment policy was never applied to the RAM preview store. | Policy applied on save and after every unlock; disabling previews wipes them. |
| 12 | Medium | Default data directory was `/tmp/enveliq`, which another local user could pre-create or symlink. | Default is the project `data/` folder; foreign-owned or symlinked directories are refused. |
| 13 | Low | Account deletion left that account's previews in RAM. | Previews purged by account. |
| 14 | Low | Unauthenticated `/status` revealed preview activity (lease counts, bytes in RAM). | Moved to the admin attachment-policy endpoint. |
| 15 | Low | Unlimited concurrent sessions. | Capped at 32, plus a 12-hour absolute lifetime. |
| 16 | Low | Non-owners could tell a private mailbox from a missing one (403 vs 404), and household viewers saw server and login details. | Uniform 404; field allowlist with a reduced view for shared mailboxes. |
| 17 | Low | Free-form `suggested_task` / `attachment_summaries` dicts allowed raw content under arbitrary keys. | Typed, size-bounded models. |
| 18 | Low | Server hosts and LLM endpoints were unvalidated strings. | Hostname/IP and http(s)-URL validation (no credentials, other schemes or fragments). |
| 19 | Low | Preview store trusted the declared MIME type and had no owner check on reads. | Magic-byte check; `get_for_owner()` for all future preview reads. |

Other hardening in v0.13: JSON-only request bodies (415 otherwise), `Origin` allowlist, `Cross-Origin-Opener-Policy` and `Cross-Origin-Resource-Policy` headers, broader log redaction, IDs validated as UUIDs before lookup, `argon2-cffi` removed in favour of `cryptography`, test tools moved to `requirements-dev.txt`.

Checked and found sound: authenticated encryption with per-record associated data, secret fields never returned, cross-site form posts and DNS rebinding blocked, database files created owner-only, deeply nested JSON rejected cleanly.

### Proton Mail Bridge connection (v0.19)

- **Pinned certificate.** Bridge's self-signed certificate, exported by the administrator, is the only one trusted, and the peer certificate's SHA-256 is compared again after the handshake. STARTTLS is required; the username and password are sent only after both checks pass. There is no option to skip verification.
- **Destinations.** Bridge must be a private or loopback IP address, or a host on the administrator's exclusive allowlist (`ENVELIQ_BRIDGE_ALLOWED_HOSTS`); ports 1024-65535 only. The compose file sets the allowlist to the Enveliq network's gateway. Usernames are limited to plain address characters because IMAP clients send them unquoted.
- **No bodies stored.** Sync fetches header fields only, with `BODY.PEEK`, and marks nothing read. "View email" fetches the original on demand (10 MB limit), renders plain text in memory and returns it with `Cache-Control: no-store`. HTML, remote images, links and scripts never reach the browser; attachments are listed by name and size only.
- **Replies.** Recipient and threading headers come from the stored context; the From address must be the mailbox address or one of its listed sending identities, so a spoofed `Delivered-To` cannot pick a foreign sender. Header injection is blocked at the model and again by the mail library. Replies are limited to 20 per user per 10 minutes and 200 per hour overall.
- **Provider action first.** Mark reviewed, Archive and Bin change the real mailbox before the local record is removed; if Bridge fails the item stays.
- **Access.** Every Bridge endpoint is owner-only through `load_account()` (other users get the same 404 as for a mailbox that does not exist), syncs are one at a time per mailbox and rate limited, and errors shown to the browser are fixed messages that never contain server output or credentials.

### Inbox page with real mail (v0.20)

- **Same data, same limits.** The Inbox page reads the same owner-only endpoints as the Mailboxes page. Only the signed-in person's own Bridge mailboxes are listed; household members never see them. No new endpoint and no new stored field except the sent date (`received_at`, a number parsed from the Date header and ignored if unusable).
- **Text only.** Every value from the server (sender, subject, summary, original text, attachment names) goes through the page's `esc()` function before it enters HTML; the original email is shown in a `<pre>` as plain text. `scripts/check_inbox_real_mail.mjs` loads hostile values and fails if any code runs.
- **Provider action first.** Reviewed, Archive and Bin on the Inbox page call the resolve endpoint and change the item on screen only after the server confirms; a failure keeps the item and shows the reason. Reply sends only the typed text and the chosen sender; the server still enforces the allowed sender addresses and rate limits.
- **Unchanged.** The inbox page still runs under the looser page policy (inline script and style, no external connections) until it is split into bundled files; see the recommendations below.

### AI summaries (v0.21)

- **Opt-in twice.** Nothing is sent anywhere unless the administrator sets `ENVELIQ_LLM_URL` and `ENVELIQ_LLM_MODEL`, *and* the mailbox owner switches AI summaries on for that mailbox (`settings.ai_summaries`). The setting can be turned off again at any time.
- **Your own network only.** The AI server must be a private or loopback IP address, or a host on the administrator's exclusive list (`ENVELIQ_LLM_ALLOWED_HOSTS`). Redirects are not followed and system proxy settings are ignored, so a response cannot send Enveliq somewhere the host rules never approved. The status endpoint reports only whether a model is set up, never its address or key.
- **Text is not kept.** The email is fetched on demand (`BODY.PEEK`, nothing marked read), reduced to plain text and cut to 6,000 characters, sent to the model and dropped. Only the short result is stored (summary, category, priority, action flag, suggested task), encrypted like every other message field. Neither the text, the model's raw reply nor the API key is logged or put in an error message.
- **The email is hostile input.** It is placed between markers as data, the model is told never to follow instructions inside it, and any marker text inside the email is removed. The reply is only displayed: it is parsed as JSON, each field is cut to a safe length, category and priority come from fixed lists, and unknown fields are discarded. Nothing the model says can start an action, change a setting or open a link. A malicious email can still try to make its own summary misleading or its priority high; the summary is a convenience, and the original is one click away.
- **Use a model without tools.** Point Enveliq at a plain model server, not an agent that can run commands, change files or control devices. Even with the checks above, an agent with tools would be given text written by strangers.
- **Limits.** Owner-only endpoint, one mailbox operation at a time, 12 requests a minute per person, at most 20 emails per request. A model that is down stops the batch and changes nothing.

### Forgetting mail handled elsewhere (v0.23)

- **Read-only.** Sync asks Bridge for the list of unread inbox emails (`UID SEARCH UNSEEN`, no bodies) and deletes Enveliq's own saved summary of any email no longer on it. It never marks, moves or deletes anything in the mailbox.
- **Cautious.** Only items from the same mailbox generation (matching UIDVALIDITY) are compared, so a reset mailbox cannot wipe the list. A failed or interrupted search changes nothing.
- **Theme.** The light/dark choice is stored only in the browser (`localStorage`). The sign-in pages read it with an external script (`/static/theme.js`), so their strict policy is unchanged.

### Setting up AI in the app (v0.24)

- **Administrators only.** Viewing the saved address, saving, clearing and trying new settings need an administrator with a full session. Anyone signed in can see whether AI is set up and the model name, and test the saved settings.
- **Same address rules as before.** Whatever is typed in the app goes through the same check as the environment setting: http or https, no embedded credentials, and a private or local IP address unless the environment lists the host in `ENVELIQ_LLM_ALLOWED_HOSTS`. Settings from the environment win and cannot be overwritten from the app.
- **The key.** Stored only inside the encrypted vault, never returned by any endpoint, never logged. A saved key is only ever sent to the address it was saved with: testing or saving a different address without typing a key sends none.
- **Tests are limited.** Testing sends one made-up email and is rate limited (12 a minute per person). Failures are explained with fixed messages, not the server's reply.
- **Setup guide.** Built with the same text-only page code as the other account pages under the strict policy (no inline script or style); the Bridge password typed there goes only to the existing add-mailbox endpoint, and a mailbox that fails its connection test is deleted again.

### App-password email services (v0.25)

- **No shipped registrations.** Gmail, iCloud, Yahoo, Fastmail and other IMAP services are reached with an app password the person creates at their provider. Enveliq ships no Google or Microsoft application credentials. Outlook and Microsoft 365 need Microsoft's own sign-in: they work only if the administrator registers their own app and enters it (v0.35, see "Microsoft sign-in" below); until then they are listed as unavailable.
- **Encrypted, verified connections only.** Implicit TLS or STARTTLS, TLS 1.2 or newer, the certificate chain and host name checked against the system store (plus `ENVELIQ_MAIL_CA_FILE` if the administrator sets it). There is no plain-text mode and no option to skip verification. The password is sent only after the handshake succeeds; a certificate failure is reported as `tls_failed` and nothing is sent.
- **Where Enveliq will connect.** By default only public servers: names must be real host names, ports must be the standard secure ones (IMAP 993 or 143 with STARTTLS; SMTP 465 or 587), and the name must resolve only to public addresses at connect time (a name that points at a private or local address is refused, which also stops DNS tricks aimed at the home network). If the administrator sets `ENVELIQ_MAIL_ALLOWED_HOSTS` the list is exclusive: only those servers are contacted, on any port.
- **Same protections as Bridge.** Header-only sync with `BODY.PEEK`, text-only on-demand view, provider action before local change, sender checks and rate limits on replies, owner-only access. Archive and Bin use the folders the server marks with the standard special-use flags (Gmail's All Mail and Trash included), and the item stays if no such folder exists.
- **Passwords.** Stored encrypted per account like every other secret, never returned by any endpoint or logged. Provider spaces in an app password are removed in the browser before sending.
- **Messages.** Errors for these services are fixed messages (`login_failed`, `app_password_required`, `tls_failed`, `host_not_allowed`, `unreachable`) that never include server output.

### Automatic sync (v0.26)

- **Same operations as the button.** A background task runs the existing sync and summarise functions for each mailbox every `ENVELIQ_SYNC_MINUTES` (default 10). It adds no new access: the same destination rules, TLS checks, header-only fetch and per-mailbox lock apply, and a mailbox being synced by hand is skipped and retried a minute later.
- **Never keeps the vault open.** It runs only while the vault is unlocked, and its vault reads are marked passive so they do not reset the idle-lock timer. When the vault idle-locks, the task does nothing until someone unlocks it. A lock during a pass stops the pass.
- **Failures back off** (doubling, up to an hour) and are recorded in memory as a fixed error code only: no server output, address or credential. Status (`GET /api/v1/sync/status`) shows each person only their own mailboxes.
- **Opt-out and interval.** Per mailbox (`settings.auto_sync = false`). The interval (or off) is set by an administrator in the app (stored in the encrypted vault, audited) unless `ENVELIQ_SYNC_MINUTES` is set, which wins and cannot be changed from the app.

### Settings and Administration pop-ups (v0.27)

- **Same pages, same server checks.** The pop-ups show the existing account, mailbox, setup guide and administration pages. They call the same endpoints, so every administrator-only action is still checked on the server; hiding the Administration button for non-administrators is only the visible layer.
- **One small policy change on the inbox page.** Its script policy now also allows scripts from Enveliq itself (`script-src 'self' 'unsafe-inline'`) so it can load `/embed.js`, which is just `welcome.js` and `auth.js` joined into one module. Nothing from another site is allowed, there is still no `eval`, outside connections are still blocked and `frame-ancestors 'none'` (nobody can frame Enveliq) is unchanged. The pages are not put in frames: each is drawn into a shadow root inside the inbox page, so their styles stay separate. The text-only rule (no `innerHTML` with data) in those files is unchanged.
- **Tested.** `tests/test_embed.py` checks the module and that the policy stays otherwise tight; `scripts/check_welcome_e2e.mjs` opens both pop-ups in a browser and uses the real pages in them.

### Vault key unlock (v0.28)

Optional. `ENVELIQ_VAULT_KEY` (or `ENVELIQ_VAULT_KEY_FILE`, which wins if both are set) holds a random string of at least 32 characters that is used as the vault passphrase, so Argon2id still applies. It is never logged, shown or sent. Trade-offs: an environment variable is visible to anyone who can run `docker inspect`, so the file (outside the data volume, mode 0600, created without overwriting) is the stronger form. Either protects copied backups and disk images, not a fully compromised server. In this mode the idle lock and the Lock button are off. Failures are reported as fixed codes (`missing`, `unreadable`, `too_short`, `wrong`) and the vault stays locked. `python -m backend.vault_key adopt` and `use-passphrase` rewrap the master key without re-encrypting data. See `docs/VAULT_KEY.md`.

### Microsoft sign-in (v0.35)

- **Your own registration.** No application credentials are built in. An administrator enters their own client ID (and optionally a secret, kept encrypted and never returned) under Administration, Microsoft sign-in; only administrators can read or change it, and changes are audit-logged without values.
- **Authorisation code flow with PKCE (S256) and state.** A sign-in is started by a signed-in person; the verifier and state live only in the server's short-lived flow store (10 minutes, single use) keyed by an HttpOnly cookie. The return address needs that cookie, a matching state, and the same signed-in person who started it, otherwise nothing is created. The code is exchanged server-side; the browser never sees a token.
- **Tokens.** The refresh token is stored encrypted in the vault with the mailbox, never returned by any API (only a yes/no), never logged or reported. Access tokens are held in memory only and dropped when the vault locks. Microsoft's error text is never passed on: results are fixed codes with fixed wording. The ID token (received directly from Microsoft over https) is read only to learn which address signed in.
- **Fixed destinations.** The token endpoint is `login.microsoftonline.com` and mail goes only to `outlook.office365.com` (IMAP, TLS) and `smtp.office365.com` (STARTTLS), set in code. The server and port stored in the mailbox record are ignored for these mailboxes, so editing a mailbox cannot redirect a token elsewhere. Certificates are verified as for every other service.
- **Nothing half-made.** The new mailbox is tested (read and send) before it is kept; on any failure it is deleted and the person sees a plain reason.
- **Permissions asked for:** `IMAP.AccessAsUser.All`, `SMTP.Send`, `offline_access`, `openid`, `email`. No Graph access.

### Reporting: OpenTelemetry push and Grafana (v0.33)

- **Same rules as the other outputs.** The OpenTelemetry receiver address and the Grafana address are checked when saved and before every request with the same destination rules as Loki and webhooks (no loopback, link-local or metadata addresses, public needs https, connection pinned to the checked address, no redirects, 64 KiB answer limit, `ENVELIQ_REPORT_ALLOWED_HOSTS`). Grafana paths are fixed by the code (`/api/org`, `/api/datasources`, `/api/folders`, `/api/dashboards/db`, `/api/annotations`); the administrator supplies only the base address.
- **Secrets.** The Grafana service-account token and any receiver password or token live in the encrypted `reporting_config` record, are never returned (only yes/no), are sent only to their own address, and are dropped from memory when the vault locks. Nothing a server answers is passed on to the page: errors are fixed codes with fixed wording.
- **Content.** The pushed numbers are the same counts, timings and states as `/metrics` (no mail content). Dashboard markers use fixed wording chosen by the code (for example "Vault locked") plus, for sync problems, the mailbox label; they carry the tags `enveliq`, the event name and the instance name. A test feeds real-looking mail through and proves none of it reaches the markers or the push.
- **Least privilege.** Enveliq asks Grafana for only what it needs to install the dashboard and add markers. Use a dedicated service account (Editor role), never an administrator or someone's personal token; the token cannot be used to read Enveliq.

### Reporting (v0.32)

- **Off by default, administrators only.** Settings (`GET/PUT /api/v1/admin/reporting`, token, test) need an administrator with a full session and live in the encrypted global record `reporting_config`. Secrets (Loki password or token, webhook signing secret) are never returned (only yes/no) and are dropped from memory when the vault locks; changes are audit-logged without secrets.
- **No content by construction.** An event may only carry fields from a fixed list: numbers, booleans, opaque person ids, a mailbox label, and text that matches `[A-Za-z0-9_.:-]{1,64}` (codes such as `sync_failed`). Subjects, senders, addresses, summaries, names and anything a server replied cannot pass those filters, and `tests/test_reporting.py` feeds real-looking mail through sync and AI summaries and proves none of it appears in metrics, logs, Loki bodies or webhook bodies. Mailboxes are anonymous labels unless an administrator chooses names.
- **`/metrics`.** Off until switched on, needs a bearer token (random, shown once, stored as a SHA-256 hash, compared in constant time; making a new one revokes the old), failed attempts are rate limited, and it answers 503 while the vault is locked. Metric values are counts, timings and states only.
- **Outbound destinations.** Loki and webhook addresses are checked at save time and before every send: http or https only, no embedded credentials, the name is resolved and every address must be allowed (never loopback, link-local including cloud metadata, unspecified, multicast or reserved; public addresses need https), the connection goes to the checked address (no re-resolution), certificates are verified, redirects are never followed, answers are read up to 64 KiB, errors are fixed codes. `ENVELIQ_REPORT_ALLOWED_HOSTS` makes it an exclusive list. This keeps the feature from being used to reach services on the server itself or its cloud metadata address.
- **Never blocks.** Events are queued (2000, oldest dropped) and sent by a background thread; a failing or slow destination cannot slow requests, and a failure in reporting code cannot break an audited action.

### Cloud AI services (v0.31)

- **Fixed addresses.** `backend/mail/llm_providers.py` lists each cloud service with one https address. A cloud service is contacted only at exactly that address (no redirects, certificate verified, no proxy), whatever is typed; a lookalike or http address is refused (`host_not_allowed`). Servers on the owner's network keep the old rule (private or local IP unless the environment lists the host). If `ENVELIQ_LLM_ALLOWED_HOSTS` is set it applies to cloud services too.
- **Consent.** Mail text leaves the network, so the server refuses to save a cloud service unless the request confirms that the administrator understands the text of their email goes to that company (`cloud_consent`), and it needs an access key. The page shows the warning and the choice is recorded in the audit log (provider and cloud flag, never the key or any text). Testing sends only a made-up email.
- **Key handling.** The key stays in the encrypted vault, is never returned, is sent only to the address of the service it was saved for, and is not reused when the service changes. Anthropic's key goes in `x-api-key`; the others use `Authorization: Bearer`.
- **What is sent** is unchanged: the sender, subject and about 6,000 characters of plain text, inside the same untrusted-data wrapper, with the same fixed rules and reply validation. Per mailbox opt-in (`ai_summaries`) still applies.

### Built-in AI prompt (v0.30)

- **Two parts.** The prompt sent to the model is an editable part (the role and the summary guidance) followed by a fixed part that no setting can change: the email is untrusted data, never follow or reveal instructions, and the exact JSON reply format. A custom prompt replaces only the editable part, so it cannot remove the injection rule or alter what the application reads. The reply is still parsed and validated as before.
- **Who and how.** Only an administrator can read or change it (`GET/PUT /api/v1/admin/ai-prompt`); the server refuses a change unless the request says the risk was acknowledged, and a replacement must be 40 to 4000 characters (control characters removed). Clearing it restores the built-in prompt and needs no acknowledgement. It is stored in the encrypted global record and every change or reset is written to the audit log (no prompt text in the log).
- **Extra instructions** from administrators and people are unchanged: appended after the fixed part.

### Reviewed and Archived lists, and AI instructions (v0.29)

- **What is kept.** Unless the person turned it off (General settings), Reviewed and Archived leave a trimmed card behind for a few days: sender, subject, summary, task, priority and the reply context that were already stored. The link back to the mailbox message and all attachment details are removed at that moment, and preview leases are purged, so a kept card cannot fetch the email or an attachment. Binned items are deleted outright. No email text is stored, as before.
- **Mailbox first.** The real mailbox action still happens before anything local changes, and a failure leaves the item untouched.
- **How long.** Each person chooses the days; an administrator sets the maximum (default 14, at most 90) and it applies to existing cards at once. Cards past their time, or whose list the person switched off, are deleted when the list is read and on every automatic sync pass. A person can also remove a card by hand.
- **Preferences** are stored in the person's own encrypted user record, and the administrator's settings in an encrypted global record. Only an administrator can change the maximum or the shared AI instructions.
- **AI instructions.** The administrator's and the person's instructions are appended to the fixed system prompt (control characters removed, 2000 and 1000 characters at most), never to the part that holds the email. The fixed prompt still tells the model to ignore instructions inside an email and to answer in one fixed format, and the reply is still validated; a person's instructions only affect summaries of their own mail.

### Automated checks (v0.18)

Every push and pull request runs `.github/workflows/ci.yml`: the backend tests, the prototype escaping check and the sign-in browser flow, a Docker build started read-only with all capabilities dropped (health check and non-root user checked), and `pip-audit --strict` against `requirements.txt`. Actions are pinned to commit hashes and the workflow token is read-only. Dependabot proposes pip, Actions and Docker updates weekly, only for releases at least 14 days old.

The first scan found advisories in Starlette 0.50.0 (Host header used to rebuild `request.url`; `HTTPEndpoint` method lookup; Windows UNC paths in `StaticFiles`) and pyasn1 0.6.3 (three decoder denial-of-service bugs). Enveliq already rejected unknown Host headers and uses neither `HTTPEndpoint` nor Windows, but v0.18 upgrades to Starlette 1.6.0, FastAPI 0.141.1 and pyasn1 0.6.4, and a test keeps them at or above the fixed versions.

### Recommended next hardening (not yet implemented)

1. **Other providers.** Done for Proton Bridge (v0.19), app-password IMAP services (v0.25) and Microsoft accounts through the administrator's own app registration (v0.35). Gmail through Google's OAuth is not offered (app passwords work).
2. **Passphrase change and master-key rotation.** Re-wrap the master key without re-encrypting data; rotate per-account keys on demand.
3. **Strict CSP for the inbox page.** The sign-in pages already run without inline code. Move the inbox page's inline script and styles into bundled files so it can too.
4. **Audit log retention and viewer.** The encrypted audit log grows without limit and has no admin view.
5. **Pinned dependency hashes and code scanning.** `pip install --require-hashes`, plus CodeQL/Semgrep and secret scanning. (Done in v0.18: pip-audit on every push and Dependabot with a 14-day cooldown.)
6. **Scoped API tokens for Home Assistant**, revocable and limited to counts and actions, with tests that a token cannot read message content.
7. **Notify users of new sign-ins and security changes** (new passkey, two-factor turned off) by email or in the app.

## Optional email features (v0.37)

New email, the address book, Sent and attachment previews are each optional. They add no stored email content.

- **Switches.** An administrator turns each feature on or off for everyone (`/api/v1/admin/features`); each person can then turn off, for themselves, anything the administrator left on (`/api/v1/me/features`). A feature is in use only when both agree, and every endpoint checks this on the server (403), not only the page. Everything is on until someone switches it off.
- **All emails (last 14 days).** Off switch for the whole server (Administration, Features) and for each person; both must allow it. When on, `POST /accounts/{id}/inbox/recent` reads only the headers of the newest 100 inbox emails from the last 14 days (read-only `EXAMINE`; the mailbox is never changed) and keeps the sender, subject and date, with no email text, as ordinary encrypted retained entries marked `from_all_mail`. These entries are ignored by the unread-mail cleanup, are never summarised automatically, are dropped after 14 days, and are all deleted when the feature is switched off for the person. The email's text is read and sent to the AI model only when the person presses Generate summary, which needs a configured model and the feature to be on. Those requests go into a first-come, first-served in-memory line (`summary_queue.py`): one worker, one email at a time, at most 50 waiting per person, holding only ids. The line survives a page refresh or another device and is emptied by a server restart. Each person is limited to 20 listings and 120 line requests a minute.
- **Viewing PDFs and text attachments in the page.** A PDF is never sent to the browser. In the Docker setup it is drawn by a **separate locked-down container** (`enveliq-render`, built from `Dockerfile.render`): it sits alone with the main container on a private Docker network marked `internal` (no internet, nothing published to the host), is read-only, runs as its own user (10002) with every capability dropped and no-new-privileges, has no volumes (it cannot see the data folder, the vault or any key) and has no secrets in its environment. The main container has no PDF parser installed at all. It posts one PDF (up to 10 MB) to `ENVELIQ_RENDER_URL`, bypassing any proxy, and **treats the answer as untrusted**: the reply must be well-formed JSON of at most 20 pictures that are valid base64 beginning with the PNG signature, each at most 3 MB and 24 MB in all, before anything goes to the browser. Inside the viewer container poppler (`pdfinfo`, `pdftocairo`) reads the file from a pipe and writes PNG pages to a pipe (nothing touches a disk), in a child process with a 15 second CPU limit, 20 second wall-clock limit, 1 GB address-space limit, no permission to create files, and no environment; at most two PDFs are drawn at once, and each person is limited to 12 views a minute. Encrypted, broken, oversized or slow PDFs give a plain message. If a poppler flaw were exploited, the attacker would be inside a container that holds only that one PDF and has no way out. When `ENVELIQ_RENDER_URL` is not set (running the program directly, for development) the same drawing code runs as a limited child process of the main program instead: that mode is resource limiting only, not a sandbox, and is not used by the compose file. Text, CSV, TSV, JSON, Markdown and log files are decoded on the server (200 KB, control characters removed, CSV capped at 200 rows and 20 columns) and shown with `textContent`, never as HTML. Word, Excel, PowerPoint, HTML, scripts and archives are never opened. The result is served `Cache-Control: no-store`, only when the pictures-and-attachments switch is on, and is held in the browser's memory only while the viewer is open. Rebuild both images now and then to pick up poppler fixes.
- **New email.** Uses the same rules as replies: the From address must be the mailbox address or one of its listed sending identities; every header value is rejected if it contains CR, LF or NUL; at most 50 recipients, 10 attachments and 10 MB in total; the same per-person and global send limits and the same Undo send hold. Only `POST /accounts/{id}/send` accepts a large body (15 MB), and nothing else relaxes the 1 MB limit. Attachments exist only in memory while the request is handled or the email waits in the Undo send queue; if the person presses Undo they are handed back to that person's browser (so they stay attached) and the server's copy is dropped. Bcc recipients are used for delivery and never written into the message headers. The audit event records who and when, never the text, recipients or file names.
- **Address book.** Names and email addresses only, one encrypted record per person (`contacts:<user id>`) under the vault's master key, never shared between people, at most 5,000 entries, addresses validated and names stripped of control characters and angle brackets. Entries come from senders Enveliq has read, people written to, and an imported vCard that the browser parses and previews before anything is sent to the server. Remembering automatically can be switched off by the person. Deleting one person or the whole book is always allowed, even when the feature is switched off.
- **Sent.** A read-only view of the Sent folder (opened with EXAMINE, never changed), limited to the last 14 days and the newest 100, fetched when the page is opened, returned with `Cache-Control: no-store` and never stored. The folder is found by its special-use flag or usual names; Proton Bridge uses `Sent`. Whether a sent email appears there depends on the mail provider saving a copy.
- **Pictures and attachments.** The email is fetched from the mailbox for each request and the bytes are returned from memory with `Cache-Control: no-store` and `X-Content-Type-Options: nosniff`. Only PNG, JPEG, GIF and WebP can be previewed, and only when the request asks for a preview; SVG, PDF and everything else is sent as a download (`application/octet-stream`, `Content-Disposition: attachment`) and never rendered by the page. The page's policy allows `img-src blob:` for these previews and nothing else new. Pictures loaded from the internet are still never loaded (tracking pixels, server-side request risk); the page only says how many were left out. Pictures that are part of the message itself show automatically when previews are on, up to six small ones.

## Important people

A short list of the sender addresses a person wants to see first.

- **What is kept.** Email addresses and optional names that the person typed or chose, nothing from any email. One encrypted record per person (`important:<user id>`) under the vault's master key, at most 200 entries.
- **Who can see it.** Only that person. The server takes the person from the signed-in session, never from the page; one person's list is never returned to another. Administrators have no route to it.
- **What the server does with it.** Nothing. It never reads mail to apply it: the page sorts the person's own list on the person's own screen.
- **Your data.** It is part of Export my data, and it is forgotten when the person is removed.
- Requests are validated (`extra: forbid`, address pattern, length), rate limited and `no-store`.

## Signature and saved replies

A person's own signature and short pieces of text to reuse.

- **What is kept.** Only text the person typed: one signature and up to 30 saved replies. One encrypted record per person (`saved:<user id>`) under the vault's master key. No email text is stored.
- **Who can see it.** Only that person, from the signed-in session. Administrators have no route to it.
- **What the server does with it.** Nothing. The page puts the signature and chosen replies into the message box; what is sent is exactly what the person sees in the box and presses Send on, through the same checks as every message. The AI is never given it unless the person asks for writing help on text that contains it.
- **Your data.** It is part of Export my data and is forgotten when the person is removed.
- Requests are validated (`extra: forbid`, length limits, id pattern), control characters are removed, requests are rate limited and `no-store`.

## Mail rules

Rules are the first thing Enveliq does to a mailbox by itself, so they are deliberately small.

- **What a rule can do.** Archive, or mark as reviewed. Nothing else. No rule can bin, delete, send or forward anything.
- **What it looks at.** Only the sender address and subject of mail that has just arrived, the same two fields Enveliq already reads to build its list. It never reads an email body.
- **What it never touches.** Mail already in the inbox (a rule is applied only to mail that arrives after the rule exists), and mail from the person's own important people. A rule belongs to one person and applies only to that person's mailboxes.
- **How it acts.** Through the same code as the Reviewed and Archive buttons: the mailbox is changed first, and only if that works is a card kept for a few days (the person's usual setting). If the mailbox cannot be changed the email simply stays in the inbox. The audit log notes `by: rule`.
- **What is kept.** Senders and subject words the person chose, one encrypted record per person (`rules:<user id>`), at most 50. Part of Export my data; forgotten when the person is removed. Only that person can read or change them.
- Requests are validated (`extra: forbid`, address and website patterns, length limits, id pattern), rate limited and `no-store`.

## Saved layout and opened emails

Each person's saved layout (`mail-view-v1:<person>`) and the list of emails they have opened (`enveliq-opened-v1:<person>`, only mailbox and email ids) are kept in the encrypted vault and are read and written only for the signed-in person, from the session, never from anything the page sends. The "opened" route answers "not found" unless the mailbox belongs to that person and the email exists. Neither record holds any email text, and opening an email never changes its state at the mail provider. Both are cleared when a person is deleted. The per-device browser test route needs a session, is limited to ten tests a minute, and only reaches the caller's own registered devices.


## Action feedback preferences

The optional Show action confirmations preference is stored with the signed-in person's existing view preferences in the encrypted vault. It contains only a Boolean setting and is never shared between people. Turning it off never disables security or operational errors, Undo controls or pending sending states.

## Selected email continuity

The last selected email is kept as its mailbox identifier and message identifier in the signed-in person's encrypted vault record. The server validates ownership before saving it and does not store an email body or attachment. Scroll positions remain in browser session storage, scoped to the current user, and are not sent to the server.
