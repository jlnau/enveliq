# Change log

Newest first. Each entry says what changed for people and which parts of the code it touches. The history of earlier versions is in [VERSION_HISTORY.md](VERSION_HISTORY.md).

## Unreleased

No changes recorded yet.

## v0.81 (2026-10-12)

**Mail rules.** "Archive new email from this sender", done for the person as mail arrives.

- `backend/mail/rules.py` (new): `Rules`, one encrypted vault record per person (`rules:<user id>`), at most 50 rules. A rule has a sender (one address, or a whole website written `@example.com`), optional words the subject must contain, and an action: **archive** or **mark reviewed**. There is deliberately no action that bins mail.
- `backend/mail/rules_routes.py` (new): `GET /api/v1/me/rules`, `POST /api/v1/me/rules`, `DELETE /api/v1/me/rules/{id}`. Signed-in people only, `no-store`, rate limited, one person never sees another's rules.
- `backend/mail/service.py`: a sync now tells the application which emails have just arrived (id, sender, subject, nothing else) through `on_new`. `backend/app.py`: `apply_rules` checks the owner's rules for each, skips mail from the owner's important people, and runs the same `resolve_message` code the Reviewed and Archive buttons use (the mailbox is changed first, then a card is kept for a few days). A rule failing never fails a sync; if the mailbox cannot be changed the rest are left where they are. The audit entry for such a change says `by: rule`.
- `backend/app.py`: the resolve endpoint's body moved into `resolve_message(...)` so the buttons and the rules share it. Behaviour of the buttons is unchanged.
- `backend/export.py`: part of **Export my data** (`rules`). Forgotten when a person is removed.
- `prototype/index.html`: an **Always archive these** button on an opened email (not for important people, not in the demo); `web/static/auth.js`: Settings, **Mail rules** (`rulesPage`).
- Docs: `README.md` and `docs/EMAIL_SERVICES.md` no longer say Enveliq changes the mailbox only on a button press; they name rules.
- Tests: `tests/test_rules.py` (the rules, limits, isolation, export, and applying them to a real sync: one sender, a whole website, subject words, reviewed, important people skipped, not applied to mail already there, other people's rules ignored), `scripts/check_rules.mjs`.
**"Keep me signed in on this device".** The sign-in page can now show a tick-box that keeps a person signed in for days instead of 30 minutes. An administrator decides whether it is offered and for how long (0 to 14 days, off by default) under Administration, Sign-in rules. It only works when Enveliq opens its own vault from a key file, because otherwise Enveliq locks itself after a while and signs everyone out anyway.

- `backend/security.py`: a session can carry its own `remember_seconds`; a remembered session lasts exactly that long from sign-in (no 30-minute idle timeout, no 12-hour cap). Only a fully signed-in session can be remembered, never one still waiting for a second factor or for setup.
- `backend/auth/users.py`, `backend/auth/routes.py`: new sign-in rule `remember_days` (0 to 14, checked on the server). The choice is carried through two-factor, passkey and single sign-on sign-ins, and the cookie lasts as long as the session.
- `backend/app.py`: `remember_seconds()` is 0 unless a vault key file or key is in use. `GET /api/v1/status` says only whether the tick-box is offered (`sign_in.remember`).
- `web/static/auth.js`: the tick-box on the sign-in page and a "Keep me signed in (days)" field in Sign-in rules, with a link to the vault key guide when no key file is set up.
- Tests: `tests/test_remember_me.py`, `scripts/check_remember_me.mjs`.

**No flash of sample data when you refresh.** On a real Enveliq, pressing the browser's refresh button no longer shows the sample page (the sample name, counts and version) for a split second before your own page appears.

- `prototype/index.html`: while the page starts up (`body.booting`), the frame (menu, buttons, logo, search) shows at once, but your name, role and initials, the greeting, the counts, the version label and the list stay hidden. If it takes more than half a second, a calm line says "Getting your inbox ready…". When there is no server behind the page (the demo or a hosted preview) it appears as soon as that is known, with no loading line, and if the server is slow to answer the page is shown anyway after six seconds.
- Tests: `scripts/check_no_sample_flash.mjs` (new, added to `.github/workflows/ci.yml`: the frame is there while the answer is slow, nothing personal or sample shows, the loading line only appears after a moment, then the signed-in person's name, greeting and version appear; preview appears at once; a server that never answers does not leave the page half empty).

**Shift + tick selects a whole range of emails.** Tick one email's box, then hold Shift and tick another one a few emails up or down the list, and every email between them is ticked too. Shift + untick clears the range the same way. Ticking without Shift works as before.

- `prototype/index.html`: the tick handler remembers the email ticked last and, when Shift is held, ticks or unticks every email between that one and the new one, in the order shown (so it follows any sorting or filter). **Clear selection** forgets the starting point, so a Shift + tick after it acts like a plain tick.
- Tests: `scripts/check_shift_select.mjs` (new, added to `.github/workflows/ci.yml`: down, up, carrying on, unticking a range, no earlier tick, and the bulk bar).


**Sample names and the publishing notes.** No change to how Enveliq works.

- The made-up second person in the preview, the tests and the guides is now called Cara (she was Beth), and the sample script list in the version history no longer names real-looking people.
- `SECURITY.md` ("Published images") and the v0.49 line in `docs/VERSION_HISTORY.md` now say that images are published when a GitHub Release is published, and that whether they can be pulled without signing in depends on the package's visibility.

**Install Enveliq as an app, open the exact email from a notification, and optional new-email alerts.** Reminders by browser push already existed; this makes them useful on a phone.

- `backend/app.py`: `GET /manifest.webmanifest` (new, no sign-in, the same for everyone) lets Android, iOS and desktop browsers install Enveliq (name, icon, standalone window). `manifest-src 'self'` is added to the page policies. `brand/web/` gains `enveliq-icon-192.png`, `enveliq-icon-512.png` and a maskable `enveliq-icon-maskable-512.png`, made from the logo. `prototype/index.html` and `web/auth.html` link the manifest and set a theme colour.
- `web/static/sw.js`: a tap on a notification now focuses an open Enveliq window and tells the inbox to move to the email (`postMessage`), navigates another open Enveliq page there, or opens a new window. Before, it only focused a window and never moved to the email. Only addresses on Enveliq's own origin are followed.
- `prototype/index.html`: the inbox reads `/?open=<mailbox id>:<email id>` (taken off the address bar at once so a refresh does not repeat it), opens that email in the right list (inbox, Snoozed, Reviewed or Archived) and scrolls to it. If the email is not in the list it reads the list again once, then says "That email is no longer in your list." It also listens for the service worker's message while the page is open.
- `backend/mail/mail_alerts.py` (new): `MailAlerts` builds and sends the new-email message. Settings `mail_on` (default off) and `mail_details` (default off) are added to each person's notification settings (`backend/mail/notify.py`, `notify_routes.py`). With details off the message says only how many emails arrived; with details on it adds the sender's display name and the subject (control characters removed, lengths cut). Never an address, never the summary, never email text. No message is sent during the person's quiet hours. One email opens that email; several open the inbox. High-priority mail is sent with high urgency.
- `backend/mail/scheduler.py`: `AutoSync` compares the stored emails before and after each mailbox's pass and sends one alert per person per pass for what is new and unread. The first read of a brand-new, empty mailbox is not announced, and mail fetched by the Sync button is not announced (the person is looking at it). `backend/mail/extra_channels.py`: the browser channel carries `path` when there is no public address.
- `web/static/auth.js`: Settings, Reminders gets **Tell me when new email arrives**, and, under *Nudges, quiet hours and privacy*, **Show who a new email is from and its subject**.
- Tests: `tests/test_mail_alerts.py` (new: wording, privacy defaults, quiet hours, links, service worker, manifest), additions to `tests/test_auto_sync.py` (a pass announces only new mail, settings default off, manifest and icons are public, policy), `scripts/check_notification_link.mjs` (new browser check, in CI: link opens the exact email on desktop and phone, a message from the service worker moves the page, other sites and other messages are ignored, the two new switches).
**A signature and saved replies.** The person's own text, kept for them, to reuse when they write.

- `backend/mail/saved_writing.py` (new): `SavedWriting`, one encrypted vault record per person (`saved:<user id>`) with one signature (up to 1000 characters) and up to 30 saved replies (a name of up to 60 characters and text of up to 3000). Control characters are removed and line breaks are tidied.
- `backend/mail/saved_writing_routes.py` (new): `GET /api/v1/me/saved`, `PUT /api/v1/me/saved/signature`, `POST /api/v1/me/saved/replies`, `PUT` and `DELETE /api/v1/me/saved/replies/{id}`. Signed-in people only, `no-store`, rate limited; one person never sees another's text.
- `backend/export.py`: part of **Export my data** (`signature_and_saved_replies`). `backend/app.py`: forgotten when a person is removed.
- `prototype/index.html`: the signature is put into the message box when New email or Reply opens, so it can be seen and changed (the cursor starts above it); a box with only the signature counts as empty (no "discard?" question, "Write your reply first"); a **Saved reply** chooser above the message inserts the text where the cursor is. The server sends exactly what is in the box and adds nothing of its own.
- `web/static/auth.js`, `auth.css`: Settings, **Signature & saved replies** (`savedPage`): edit the signature; add, edit and remove saved replies.
- Tests: `tests/test_saved_writing.py`, `scripts/check_saved_writing.mjs`.

**Important people.** A short list, kept by each person for themselves, of senders whose mail is shown first.

- `backend/mail/important.py` (new): `ImportantPeople`, one encrypted vault record per person (`important:<user id>`) holding addresses and optional names only, at most 200. Addresses are checked and lower-cased with the same rules as the address book.
- `backend/mail/important_routes.py` (new): `GET /api/v1/me/important`, `POST /api/v1/me/important` (add, or update the name), `POST /api/v1/me/important/remove`. Signed-in people only, `no-store`, rate limited, and each person only ever sees their own list.
- `backend/export.py`: the list is part of **Export my data** (`important_people`). `backend/app.py`: the list is forgotten when a person is removed.
- `prototype/index.html`: mail from an important person is sorted first with a stable sort, so the chosen order (newest first, and so on) is kept inside each group; a small "Important" label on the row; an **Important person** / **Not important** button inside an opened email; the same works in the demo, in memory only.
- `web/static/auth.js`: Settings, **Important people** (`importantPage`): the list, remove, and add by address and optional name.
- Tests: `tests/test_important_people.py` (add, update, remove, bad addresses, the limit, one person's list never visible to another, sign-in needed, encrypted storage, export, account removal), `scripts/check_important_people.mjs` (order, label, the button, the Settings page).

**A quick check before a new email goes.** A new email with no subject, or one that talks about an attachment when nothing is attached, now gets one calm question before it leaves.

- `prototype/index.html`: `sendWarnings(subject, body, fileCount)` and the "Before you send" window. It runs in `sendNew()` before the writing-help check. **Go back** (the one with the focus) returns to the email with the cursor in the subject; **Send anyway** sends. Escape means Go back.
- The attachment check looks for the words attach, attached, attaching, attachment, enclosed or enclosure in the message, ignoring lines that start with `>` (quoted text), and only when no file is attached.
- Nothing is sent to the server for the check, so it needs no backend change and behaves the same for Gmail, Microsoft, Proton and every other mailbox. Replies are not checked: their subject comes from the email being answered and they cannot carry attachments.
- Tests: `scripts/check_email_features.mjs` (no subject, Go back, Escape, Send anyway, attachment words with and without a file, a quoted line, an ordinary email).

## v0.80

**Five seconds to undo Reviewed, Archive and Bin, everywhere.** The Undo that phones had now covers every screen and several emails at once.

- `prototype/index.html`: `queueAction(list, status)` replaces the phone-only `phoneAction`. Every Reviewed, Archive and Bin (row buttons, an open email, the reading pane, the full-screen reader, swipes, keyboard shortcuts and the multi-select bar) hides the email(s) at once and sends the request to the mailbox only when `window.__undoMs` (5000 ms) is up. One bar per press ("Archived · 3 emails" for a multi-select); two quick presses give two waiting entries, the bar shows the newest, and Undo then shows the one before it.
- When the page is closed or hidden, waiting actions are sent straight away, all at once, with `keepalive` so the browser finishes them (on a desktop only when the page is closed; on a phone also when it goes out of sight, because a phone may freeze it). If the mailbox cannot be reached the emails come back with the error message, as before. `resolveRealBulk` (the old, immediate multi-select path and its "Marking reviewed…" button state) is removed.
- The Undo bar is centred and sized for any screen and sits above the "Undo send" bar when both show.
- Tests: `scripts/check_inbox_real_mail.mjs` (desktop Undo, multi-select Undo, the page closing, two in a row; the old "working" button state is replaced), `scripts/check_demo.mjs` (the demo's sample mail gets it too). Docs: new `docs/UNDO.md`. No server change.

## v0.79

**The public status page says less.** A read-only probe of the live site found that `GET /api/v1/status`, which needs no sign-in, told anyone the Enveliq version, the exact Argon2 settings, the public address and whether the vault unlocks itself from a key file.

- `backend/app.py`: `/api/v1/status` now returns only `initialized`, `unlocked`, `setup_required` and `sign_in` (password, passkeys, single sign-on), which the sign-in, setup and unlock pages use. While the vault is closed it also says `auto_unlock` and `auto_unlock_problem`, because the setup and unlock pages choose between a passphrase box and the key-file message from them. Once the vault is open those two are not sent.
- `GET /api/v1/system` (new): signed-in people only (`no-store`). It gives the version, cipher, key derivation, idle-lock time and the two "raw mail is never kept" flags. Administrators also get the public address, whether it unlocks itself, the Argon2 settings and the attachment preview mode.
- `prototype/index.html`: the page recognises a real server from the new status shape, and takes the version and the Security page's encryption line from `/api/v1/system`.
- Tests: `tests/test_status_minimal.py` (new: nothing technical before sign-in, `system` needs a sign-in, administrators see more than other people); `tests/test_key_file.py` and `tests/test_email_features.py` follow the move. The 21 browser checks that fake the server use the new shape.

## v0.78

**Licence changed to AGPL-3.0.** From this version Enveliq is released under the GNU Affero General Public Licence, version 3, instead of MIT, before the repository goes public.

- `LICENSE`: the MIT text is removed; the official AGPL-3.0 text is added from GitHub's licence template (so the wording is exactly the published licence).
- `README.md`, `docs/TERMS.md` and the in-app Terms of use (`web/static/auth.js`): say AGPL-3.0 in plain words. Using, changing and sharing it stays free; a person who changes it and lets others use their version over a network must share their changes under the same licence. Running it for yourself, your household or friends asks nothing more.
- No code behaviour changes.

## v0.77

**Help links go to the Enveliq website.** The links from the app to the step-by-step guides no longer point at GitHub.

- `web/static/auth.js`: guide links are now built by `guideUrl()` from the guide's file name (`AI_SUMMARIES.md`, `install/after-install.md#heading`) to its website address (`https://enveliq.app/docs/ai-summaries/`, `.../install/after-install/#heading`), using the same rule as `website/build.mjs`. They still open in a new tab, with `noopener noreferrer`, and only load when clicked. Three lines of wording that said "on GitHub" now say "on the Enveliq website" (`auth.js`, `welcome.js`).
- `prototype/index.html`: the plain-http warning's link to the access guide.
- `scripts/check_guide_links.mjs`: checks the new base address, that no page still links to GitHub (apart from the website's own GitHub button), that the file-name rule matches the website's rule, and that every guide and heading a link names exists.
- No data, sign-in or privacy behaviour changes. The 18 addresses were also checked against the built website.

## v0.76

**The demo.** A made-up copy of the inbox that anyone can open, published separately from the website.

- `demo/build.mjs` (new): reads `prototype/index.html` and makes three small changes: a banner saying the mail is made up and nothing is saved, the title "Enveliq demo", and the page's mode set to "preview" from the start so it never looks for a server. It writes `demo/dist` (the page and `brand/`) and a `_headers` file.
- `_headers` carries the demo's own strict rules: `connect-src 'none'`, `default-src 'none'`, scripts allowed only by their SHA-256 fingerprints (computed at build, so a changed script can never be forgotten), no framing, no referrer, `nosniff`, a locked-down Permissions-Policy.
- Built as its own Cloudflare Pages project (root `demo`, command `node build.mjs`, output `dist`, domain `demo.enveliq.app`), separate from the website, with no server, no sign-in and no data of any kind. Nothing in the running app changes.
- `website/src/home.html`: a "Try the demo" button.
- Tests: `scripts/check_demo.mjs` (added to CI; desktop and phone). Docs: new `docs/DEMO.md`.

## v0.75

**Backup and restore, and Export my data.** Administrators can back up, download and restore the vault; everyone can export their own data.

- `backend/backup.py` (new): `BackupManager` copies the vault with SQLite's own backup call into `backups/` in the data folder, as `enveliq-<date>-<time>-<manual|auto|before-restore>.sqlite3`, written as a private (mode 0600) `.partial` file, checked (`integrity_check` and a vault row) and then renamed. It never includes the key file. A background check every ten minutes makes the daily backup (once a day, only while the vault is unlocked), and old automatic ones are pruned (1 to 60 days, default 7); manual and before-restore copies are never pruned. At most 20 manual copies.
- Restore replaces `global_records`, `accounts`, `messages` and `users` from a backup inside one transaction. It first proves the backup belongs to this vault (its verifier decrypts with the master key in memory), refuses it if the restoring administrator is not in it, and saves a `before-restore` copy. `vault_meta` (the passphrase wrapping) and the audit events are left alone.
- `backend/backup_routes.py` (new): administrators only. `GET/POST /api/v1/admin/backups`, `PUT /admin/backups/settings`, `GET /admin/backups/{name}/download`, `DELETE /admin/backups/{name}`, `POST /admin/backups/{name}/restore` (the person's own password again through the sign-in limiter, plus the typed word; every session is ended afterwards). Names must match the exact pattern the manager writes, so a path can never be steered. Everything is audited without content; responses are `no-store`.
- `backend/export.py` (new) and `GET /api/v1/me/export`: one JSON download of the signed-in person's own data, chosen by the session, rate limited and audited. Secret fields are stripped by name as well as left out by design.
- `web/static/auth.js`, `auth.css`, `prototype/index.html`: Administration, Backup and restore (System group) and a **Your data** section in Settings, General.
- Tests: `tests/test_backup.py`, `scripts/check_backup.mjs` (added to CI; desktop and phone). Docs: new `docs/BACKUP.md`.

## v0.74

**Trips.** Flights, stays and hire cars are followed from the emails about them, put together into trips, and added to the person's calendar.

- `backend/mail/llm.py`: the summary may now carry `trips`, a list of at most six bookings (kind flight, stay or car; status booked, changed or cancelled; provider, reference, flight number or property name, places, start and end exactly as written). The prompt tells the model to copy, never to work out a date or time. Anything that is not a known kind with a start is dropped; every value is cut short.
- `backend/mail/trips.py` (new): `TripBook` files each leg as one booking in an encrypted per-person record (`trips:<user id>`). Code does everything else: dates are read from the words, a clock time is read only when there is one, a change updates the same booking (a changed date does not make a new one), an older email never overwrites newer facts, a cancellation greys a booking out, and bookings are grouped into trips by date (two days apart or less) with a flight home from where an earlier flight went joining its trip (within 45 days). The trip is named from its first booking. A trip is forgotten three days after it ends and a cancelled booking after a week.
- No email text, subject, sender address or link is kept. `backend/mail/service.py` files nothing from an email that carries a Be careful flag.
- `backend/mail/calsync.py`: the three calendar routes (private feed, CalDAV, Google Calendar) now also carry the bookings, using the same rebuild-from-the-list approach as tasks, so a removed, cancelled or finished booking leaves the calendar. A flight with a departure time is a timed entry using the clock times as written (no time zone is guessed); a stay covers its nights (the check-out day is not a night); a hire car covers its days. With "Keep titles private" the entry says only "Enveliq trip". The Home Assistant To-do list is for tasks and does not carry trips.
- `backend/mail/trips_routes.py` (new): `GET /api/v1/me/trips`, `PUT /me/trips/settings` (the calendar switch) and `POST /me/trips/{id}/remove`. Signed-in person only, rate limited, `no-store`, another person's id answers "not found".
- `backend/mail/features.py`, `extra_routes.py`, `web/static/auth.js`: a new feature switch, `travel`, for the administrator and for each person.
- `prototype/index.html`: the **Trips** menu entry (only when there is a trip), the Home card, the page and the calendar switch.
- Tests: `tests/test_trips.py`, `scripts/check_trips.mjs` (added to CI; desktop and phone; hostile text stays text). Docs: new `docs/TRIPS.md`, `docs/CALENDAR.md`, the tour and the home page.

## v0.73

**Subscriptions and free trials.** Renewals and free trials are followed from the emails about them, shown on Home and in a list, and announced a few days before.

- `backend/mail/llm.py`: the summary may now carry a `subscription` (kind, service, amount as written, period, renewal date as written, trial end as written, trial length in days). The prompt tells the model to copy, never to work out a date. Every value is cut to a short length and anything else is dropped.
- `backend/mail/subscriptions.py` (new): `SubBook` files the facts under one subscription per service in an encrypted per-person record (`subs:<user id>`). Code, not the model, does every date: a trial length is counted from the email's own date, a passed renewal is rolled forward by the billing period (month ends are kept), a receipt with no date gives an estimate one period on and says so, and an older email never overwrites newer facts. Dates far from the email are ignored. The day is the person's own, from their time zone.
- No email text, subject or sender address is kept. The one link is the home page of the sender's own domain, only when it is a plain public address and not a mail or payment service (`company_link`). `backend/mail/service.py` files nothing from an email that carries a Be careful flag.
- `backend/mail/subscriptions_routes.py` (new): `GET /api/v1/me/subscriptions`, `PUT /me/subscriptions/settings` (1 to 14 days) and `POST /me/subscriptions/{id}/{not_subscription|cancelled|keep}`. Signed-in person only, rate limited, `no-store`, another person's id answers "not found".
- `backend/mail/reminders.py`: one message per person for what is inside their number of days, sent once per coming date, after the morning time, never during quiet hours, with the service name left out when titles are private.
- `backend/mail/features.py`, `extra_routes.py`, `web/static/auth.js`: a new feature switch, `subscriptions`, for the administrator and for each person.
- `prototype/index.html`: the **Subscriptions** menu entry (only when there is something to follow), the Home **Coming up** card, the page, and the days setting.
- Tests: `tests/test_subscriptions.py`, new cases in `tests/test_notify.py`, `scripts/check_subscriptions.mjs` (added to CI; desktop and phone; hostile text stays text). Docs: new `docs/SUBSCRIPTIONS.md`, the tour and the home page.

## v0.72

**Search everywhere.** One search box that also reports what it finds in the other places Enveliq keeps things for this person.

- `prototype/index.html`: `searchMore()` builds an **Also found elsewhere** box above the list when the search has at least two letters. It looks in the emails the page already holds (Reviewed, Archived, Snoozed, or the inbox when another list is open), the person's tasks, orders and waiting notes, shows up to four of each, and says where each one is. A match opens the list or page it belongs to and clears the search. Everything is shown as text. Not shown on the Tasks, Sent, Shipping, Waiting and Messages pages, which are not email lists.
- Nothing new is stored and nothing new is asked of the server: it uses the cards, tasks, orders and notes the page already loaded for the signed-in person, and never looks at a mailbox or at email text. The empty list now says "Nothing in this view matches your search." when a search is on.
- Fix: the person's tasks were fetched before the page knew it was showing real mail, so they only appeared after the first minute. They are fetched after that now.
- Tests: `scripts/check_search_everywhere.mjs` (added to CI; desktop and phone; hostile text stays text). Docs: new `docs/SEARCH.md`, the tour.

## v0.71

**Snooze.** Set an email aside until a time you choose.

- `backend/models.py`: `snoozed_until` (a Unix time) on the stored message. `backend/mail/review.py`: a card kept after Reviewed or Archived drops it.
- `backend/mail/routes.py`, `service.py`: `POST /api/v1/accounts/{id}/messages/{id}/snooze` with `{"until": <Unix time>}`, or `null` to bring it back now. Owner only (anyone else gets "not found"). The time must be at least 30 seconds ahead and at most 366 days away. Only inbox emails can be snoozed (not kept Reviewed/Archived cards or quiet "All emails" entries). Only the stored record changes: the real mailbox is not touched. Audited with ids only.
- `prototype/index.html`: a **Snooze** button on each inbox email opens a small menu (Later today, Tomorrow, This weekend, Next week, Pick a date) with each time shown; the page works out the time in the person's own time zone. Snoozed emails are hidden from the inbox list and counts, listed under a new **Snoozed** entry (shown only while something is snoozed) with **Wake now**, and return at the top with *Back from snooze* when the time passes (a timer re-draws the list). On a phone the menu is a bottom panel with 44px choices.
- Tests: `tests/test_snooze.py`, `scripts/check_snooze.mjs` (added to CI; uses a fixed clock and the Melbourne time zone; desktop and phone). Docs: new `docs/SNOOZE.md`, the tour and front page.

## v0.70

**Forward to check.** Forward a suspicious email to a check address and get one line back.

- `backend/mail/checkbox.py` (new): `CheckBox` looks at one mailbox an administrator chose (recent unread mail only, at most 8 per pass, every 2 minutes while automatic checking is on). For an email from a listed person it reads the attached email (`message/rfc822`) once in memory and answers with `verdict()`: `Be careful: ` plus up to four reasons from the same plain rules as the Be careful flag, or `Nothing odd found. That does not prove it is safe.` An email that was not attached is judged by its links only, and the answer says it could not see the sender. An email with nothing to check gets a short how-to. Nothing from the forwarded email is stored or logged, and no AI is used.
- Safety rules in `eligible()`: only an exactly listed address is answered (anyone else is ignored, never answered); no answer when the provider's own result says the sender was forged (`dmarc=fail`); no answer to mailing lists, bulk mail, `Auto-Submitted`, auto-responders, `mailer-daemon`/`noreply` senders or the check address itself; every answer is sent as `Auto-Submitted: auto-replied` with `Precedence: bulk`; 10 answers a day per person and 60 a day for the address; the message is marked read before it is answered, so it can never be answered twice.
- `backend/mail/check_routes.py` (new): `GET/PUT /api/v1/admin/check-address`, administrators only. Only the administrator's own mailboxes can be chosen (anything else answers "not found"), only the administrator who chose it can change it, addresses are validated and de-duplicated (at most 50), and the change is audited without any address.
- `backend/mail/service.py`, `scheduler.py`, `backend/app.py`: the check mailbox is never read as an inbox. Sync and "All emails" refuse it (`check_address`, 409), automatic sync skips it, and the mailbox list marks it (`check_address`) so the page leaves it out.
- `web/static/auth.js`, `prototype/index.html`: Administration, **Forward to check** (mailbox, people who may use it, last look, a warning when automatic checking is off).
- Tests: `tests/test_checkbox.py`, `scripts/check_check_address.mjs` (added to CI; desktop and phone). Docs: `docs/SCAM_WARNING.md`, `SECURITY.md`, the tour and front page.

## v0.69

**Unsubscribe is hidden on an email marked Be careful.**

- `prototype/index.html`: `unsubHtml()` no longer offers the Unsubscribe button (or the old **Go anyway** step) when the email is flagged, on the card or in View original. One line says why. The click handler and extra step are removed. Ordinary emails are unchanged.
- `scripts/check_scam_warning.mjs`: checks that a flagged email has no Unsubscribe button or link at all, on the card and in View original, and that an ordinary newsletter keeps its button.
- Docs: `docs/SCAM_WARNING.md`, `SECURITY.md`.

## v0.68

**Where does this link go?** A list of the links in an email, with the website each one really goes to.

- `backend/mail/links.py` (new): lists up to 30 web links from the whole email (links in HTML and plain addresses in text), each with `label` (what the email calls it, up to 80 letters), `host` (where it really goes), `url` (only when it may be opened), `note` and `flagged`. Only plain public http(s) addresses can be opened, by the same rule as the Unsubscribe link (`unsub.safe_url`): no number addresses, private or internal names, odd ports or `user:password@` forms. Other links are listed with a short reason and no way to open them. `mailto:` and other kinds of link are left out. Enveliq never fetches a link.
- `backend/mail/scamcheck.py`: the per-link rules moved into `link_reason()` so the Be careful flag and the list say the same thing. No change to what is flagged.
- `backend/mail/parse.py`: `render_original` returns `links`. Nothing new is stored, and the list is not part of the saved message.
- `prototype/index.html`: **Links in this email** in View original (not for Sent). **Open…** asks "This goes to X. Open it in a new tab?" first; on an email marked Be careful the question says the email looked odd and the button reads **Open anyway**. The opened link is a plain anchor with `target="_blank"` and `rel="noopener noreferrer nofollow"`. The viewer strip now reads "Links open only when you choose".
- Tests: `tests/test_links.py`, `scripts/check_link_check.mjs` (added to CI; desktop and phone). Docs: `docs/SCAM_WARNING.md`, the tour and front page, pictures `docs/images/link-check*.png`.

## v0.67

**Is this really from them?** A plain line in View original about whether the sender was confirmed.

- `backend/mail/scamcheck.py`: `sender_check()` reads the **first** `Authentication-Results` header only (the receiving server adds its own at the top; anything the sender wrote sits below it, so a sender cannot vouch for itself). DMARC decides when present; without it, SPF and DKIM must both pass to be "confirmed", and failed SPF with no passing DKIM is "not confirmed". Otherwise "unknown", and the page says nothing. A new reason `reply_elsewhere` joins the Be careful flag when an email from a well-known name asks for replies at another website (`BRANDS`); any other Reply-To difference is only shown (`reply_differs`), never flagged. Alias services are ignored.
- `backend/mail/parse.py`: `render_original` returns `sender_check` (`result`, `detail`, `reply_differs`). Nothing new is stored.
- `prototype/index.html`: a **Sender** row in View original (green when confirmed, amber when not) and "(a different website from the sender)" on the Reply-To row.
- Tests: `tests/test_scamcheck.py` (header order, DMARC/SPF/DKIM combinations, Reply-To rules), `scripts/check_sender_check.mjs` (added to CI; desktop and phone). Docs: `docs/SCAM_WARNING.md`, the tour and front page.

## v0.66

**A "Be careful" flag** for emails that look like a scam, such as a fake delivery notice.

- `backend/mail/scamcheck.py` (new): plain code, no AI. Finds a link that names a well-known site but goes to another, a link to an IP number, a link to a look-alike or copied name (`paypa1`, `dhl-parcel`, unusual letters), a sender name that does not match its address, and a failed DMARC result from the person's own provider (`Authentication-Results`). A short list of well-known names with their real domains (`BRANDS`) is the only thing it compares against. Links that name some other site are not judged, because tracking links are everywhere in newsletters. Stores host names only, at most four reasons.
- `backend/models.py`: `ScamWarning` and `ScamReason`, and `scam_warning` on the stored message.
- `backend/mail/parse.py`: `AUTHENTICATION-RESULTS` is now one of the headers read at sync; `summarise_headers` returns `scam_warning` (headers only); `render_original` returns `warning` (headers and links, worked out when the email is opened, never stored there).
- `backend/mail/service.py`: sync and "All emails" store the header-level flag; summarising merges in the link-level flag from the body it is already reading.
- `prototype/index.html`: the **Be careful** label on the row, a calm note on the card and in View original (text only, never page code), and **Unsubscribe** on a flagged email asks once more (**Go anyway**).
- Phones: the note is shorter and tighter below 640px, the label sits beside the subject so it is never clipped, and `scripts/check_scam_warning.mjs` checks the phone layout (label on screen, no sideways scrolling).
- Website and docs: a new guide `docs/SCAM_WARNING.md` (with a desktop and a phone picture, `docs/images/scam-warning*.png`), a new row on the front page and in the tour (`website/src/images/scam-warning*.webp`), the guide added to the site's guide list, and the contrast audit now covers it. The pictures are made with `TOUR=1 SHOTS=<dir> node scripts/check_scam_warning.mjs` (example text instead of the hostile test text).
- Tests: `tests/test_scamcheck.py`, `scripts/check_scam_warning.mjs` (added to CI).

## v0.65

**Links from the app to the step-by-step guides**, and a safer setup code.

- `web/static/auth.js`: a small helper (`guide`, `guideNote`) that makes a link to a guide in `docs/` on GitHub (new tab, `noopener noreferrer`, loaded only when clicked). Added to the first-time setup page, the unlock page, two-factor setup, Administration (People, AI model, Microsoft sign-in, Agent chat, Reminders and Google Calendar, Reporting, Single sign-on), Settings (Mailboxes, Reminders, Calendar & to-do, Writing help). Text that named a `docs/` file now links to it.
- `web/static/welcome.js`: links in the setup guide (connect your email, choose the AI model, Proton Mail).
- `prototype/index.html`: the plain-http warning links to the access guide.
- `backend/app.py`: `usable_setup_code()`. A `ENVELIQ_SETUP_CODE` that contains "change-me" or is under 16 characters is ignored with a warning in the log, and a random code is made, so the placeholder in the install file can never be the real code.
- Tests: `tests/test_auth.py` (placeholder and short codes), `scripts/check_guide_links.mjs` (added to CI: every linked guide and heading exists).

## v0.64

**Writing help.** The AI can write a reply, or check one, and only ever suggests. Off until a person turns it on.

- `backend/mail/writehelp.py`: the per-person record (`writehelp:<user id>`: on or off, and the person's own writing instructions, up to 2,000 characters; the built-in generic instructions are used until they save their own), the fixed safety rules, the prompt (the email and the draft as data between markers) and the parsing of the answer into text (cut to 4,000 characters) and up to five short notes.
- `backend/mail/writehelp_routes.py`: `GET` and `PUT /api/v1/me/write-help`, `POST /api/v1/accounts/{id}/messages/{mid}/write-help` (the server fetches the original email itself, as View original does; attachments are never sent) and `POST /api/v1/me/write-help/new`. 12 requests a minute per person. The audit log records only that it was used.
- `backend/mail/features.py`: a new `write_help` feature (administrator switch and personal switch, like the others). Separately, each person must turn writing help on for themselves.
- `prototype/index.html`: the button and the "Suggested by AI" box in the reply and New email boxes; Accept, Put my version back, Copy, Try again, Close; the send check, shown only when writing help was used on that message.
- `web/static/auth.js`: **Settings, AI instructions** gets a Writing help section; **Administration, Features** has the new switch.
- Tests: `tests/test_writehelp.py`, `scripts/check_writehelp.mjs` (added to CI), `scripts/check_welcome_e2e.mjs` now counts nine feature switches.

## v0.63

**Administrators can edit saved shipping carriers.**

- Administrators can **edit** a saved carrier (`GET /api/v1/shipping/carriers` lists names with addresses, for administrators only; `PUT /api/v1/shipping/carriers/{id}` changes one). The same address rules apply, and editing is in the audit log.
- `prototype/index.html`: an **Edit** button on each shared carrier (administrators only) that reuses the add form.
- Tests: `tests/test_shipping.py`, `tests/test_shipping_carriers.py`, `scripts/check_shipping.mjs`.

## v0.62

**Shipping: Track all, Copy number, and carriers anyone can add.** No outside service is used and Enveliq still never contacts a carrier.

- `prototype/index.html`: **Track all (n)** on the Shipping page (up to 10 parcels still on their way, each opened in a new tab by an `https` link), **Copy number** on every card with a tracking number (falls back to a hidden box on plain http), **Add this carrier** on cards whose carrier has no link, and a folded **Carriers Enveliq can link to** box (list, add form, remove with a second press).
- `backend/mail/shipping.py`: five more built-in carriers (Couriers Please, TNT, DPD, Evri, Yodel; the links were written from the carriers' usual address patterns and could not be opened from the build environment, so check each once), and one shared household list (`ship:carriers`, at most 40) used by every person's Track link. `clean_template` accepts only an `https` address on a normal public host with exactly one `{number}`, and can find the number from an example typed by the person.
- `backend/mail/shipping_routes.py`: `POST /api/v1/shipping/carriers` and `DELETE /api/v1/shipping/carriers/{id}`; the person who added a carrier, or an administrator, may remove it. Both are written to the audit log (who and when, never the address).
- Tests: `tests/test_shipping.py`, new `tests/test_shipping_carriers.py`, `scripts/check_shipping.mjs` extended.

## v0.61

**Messages, first release** (plan: [docs/MESSAGES.md](MESSAGES.md)). One-to-one and small-group (up to 8) messages between people on the same Enveliq, a **Messages** entry in the sidebar with an unread count, a Home card ("Cara and Sam left you 2 messages"), a Profile switch **Show me in the people list**, and a **Messages** on/off switch in Administration, Features (and for each person under General settings).

- Backend: `backend/mail/messages.py` (store and rules), `backend/mail/messages_routes.py` (`/api/v1/messages/...`), `messages` added to `backend/mail/features.py` and `FeaturesBody`, `show_in_people` on `PATCH /me/profile` and `GET /me`, and the person's messages are removed when they are deleted (`delete_user_data` in `backend/app.py`).
- Pages: `prototype/index.html` (sidebar entry, Home card, Messages page, phone layout), `web/static/auth.js` (Profile switch, Features text).
- Tests: `tests/test_messages.py` (including that a person outside a conversation, and an administrator, get "not found"), `scripts/check_messages.mjs` (added to CI), `scripts/check_user_menu.mjs` updated.
- Left for the second release, as planned: the board, retention settings, the "tell me about new messages" reminder, and removing a conversation from your own list.

## v0.60

The Enveliq icon is back on the browser tab: `prototype/index.html` now has `<link rel="icon">` and `apple-touch-icon` pointing at the existing files under `/brand/`. Checked by `scripts/check_user_menu.mjs`.

## v0.59 (fresh start of the git history)

**A tidier menu, Profile settings and password rules.** Light mode, Settings and Administration now live in the menu that opens when you click your name (only Agent stays in the sidebar), with a new **Profile settings** item. The Profile page is all optional: name, email address, a line about you and a small round picture (shrunk on your device, checked on the server, kept encrypted; other people can only ever see your name, picture and that line). **Administration, Sign-in rules** has a new **Password requirements** card (minimum length, how many numbers, capital letters, small letters and symbols, and whether the username may appear in the password); the change-password and add-person boxes tell people the rules in plain words. Settings and Administration were reorganised into clear groups (You, Your mail, How it works for you, Help / People, Mail, AI, System), long pages fold their detail away, and the demo-only pages that did nothing in a real install were folded into one **Security & privacy** page. Plan for messaging between people: [docs/MESSAGES.md](MESSAGES.md).

Also in this version: the repository history was squashed to a single first commit; working rules (`CLAUDE.md`) now require a branch and pull request for every change.
