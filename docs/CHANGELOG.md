# Change log

Newest first. Each entry says what changed for people and which parts of the code it touches. The history of earlier versions is in [VERSION_HISTORY.md](VERSION_HISTORY.md).

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

**Messages, first release** (plan: [docs/MESSAGES.md](MESSAGES.md)). One-to-one and small-group (up to 8) messages between people on the same Enveliq, a **Messages** entry in the sidebar with an unread count, a Home card ("Beth and Sam left you 2 messages"), a Profile switch **Show me in the people list**, and a **Messages** on/off switch in Administration, Features (and for each person under General settings).

- Backend: `backend/mail/messages.py` (store and rules), `backend/mail/messages_routes.py` (`/api/v1/messages/...`), `messages` added to `backend/mail/features.py` and `FeaturesBody`, `show_in_people` on `PATCH /me/profile` and `GET /me`, and the person's messages are removed when they are deleted (`delete_user_data` in `backend/app.py`).
- Pages: `prototype/index.html` (sidebar entry, Home card, Messages page, phone layout), `web/static/auth.js` (Profile switch, Features text).
- Tests: `tests/test_messages.py` (including that a person outside a conversation, and an administrator, get "not found"), `scripts/check_messages.mjs` (added to CI), `scripts/check_user_menu.mjs` updated.
- Left for the second release, as planned: the board, retention settings, the "tell me about new messages" reminder, and removing a conversation from your own list.

## v0.60

The Enveliq icon is back on the browser tab: `prototype/index.html` now has `<link rel="icon">` and `apple-touch-icon` pointing at the existing files under `/brand/`. Checked by `scripts/check_user_menu.mjs`.

## v0.59 (fresh start of the git history)

**A tidier menu, Profile settings and password rules.** Light mode, Settings and Administration now live in the menu that opens when you click your name (only Agent stays in the sidebar), with a new **Profile settings** item. The Profile page is all optional: name, email address, a line about you and a small round picture (shrunk on your device, checked on the server, kept encrypted; other people can only ever see your name, picture and that line). **Administration, Sign-in rules** has a new **Password requirements** card (minimum length, how many numbers, capital letters, small letters and symbols, and whether the username may appear in the password); the change-password and add-person boxes tell people the rules in plain words. Settings and Administration were reorganised into clear groups (You, Your mail, How it works for you, Help / People, Mail, AI, System), long pages fold their detail away, and the demo-only pages that did nothing in a real install were folded into one **Security & privacy** page. Plan for messaging between people: [docs/MESSAGES.md](MESSAGES.md).

Also in this version: the repository history was squashed to a single first commit; working rules (`CLAUDE.md`) now require a branch and pull request for every change.
