# Change log

Newest first. Each entry says what changed for people and which parts of the code it touches. The history of earlier versions is in [VERSION_HISTORY.md](VERSION_HISTORY.md).

## Unreleased

**Clean up.** A new page, **Clean up** (left menu on the website, **More** in the Android app), lists the mailing lists that wrote to you in the last 60 days. For each one you can **Unsubscribe** (your own browser opens the sender's page; Enveliq never does), **Archive what's here** (asks first, marks read, deletes nothing, keeps email that has an open task, and has a 10-minute **Undo**), **Always archive new ones** (a normal Mail rule) or **Keep**. On a phone it steps through one sender at a time and the confirmation opens full screen. It has its own feature switch (Administration and Settings, Features), on by default. Only the list of kept senders is stored. Touches `backend/mail/senders.py`, `senders_routes.py`, `features.py`, `prototype/index.html`, `CleanUp.kt`, `docs/CLEAN_UP.md`.

**The daily summary.** The morning summary is now a fuller **daily summary** (Settings, Notifications). Besides the tasks due today it says how many parcels are out for delivery, how many sent emails are still waiting for a reply, and which subscriptions or free trials are coming up, in one message, from lists Enveliq already keeps (no AI, no email text, no subjects). Nothing is sent when there is nothing to say. A new switch, **Send new email in this summary instead** (off by default), counts new email in the summary instead of announcing each one; important people still come through at once. The Android app can show the summary as one quiet note and honours the switch. Touches `backend/mail/summary.py` (new), `reminders.py`, `mail_alerts.py`, `notify.py`, `notify_routes.py` (`GET /api/v1/me/summary`), `web/static/auth.js`, the Android app, `docs/NOTIFICATIONS.md` and `docs/ANDROID.md`.

**Push relay: it deploys itself.** A new GitHub workflow, **Deploy push relay**, puts the relay live whenever a change to `relay/` reaches `main` (after running the relay's own checks), or when started by hand, so nobody has to run `wrangler deploy` on a computer. It needs two repository secrets, `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`, added once (steps in `docs/PUSH_RELAY.md`); without them it only warns. Touches `.github/workflows/deploy-relay.yml`, `docs/PUSH_RELAY.md`, `SECURITY.md`.

**Push relay: a built-in rate limit.** The Google push relay now limits each visiting address to 60 requests a minute (`429` after that), so one address cannot flood it. It uses Cloudflare's own rate limiter, so no domain or Cloudflare rule is needed (the old advice to add a WAF rule does not work for a `workers.dev` address). Redeploy the Worker once with `cd relay && npx wrangler deploy`. Touches `relay/worker.js`, `relay/wrangler.toml`, `relay/test.mjs`, `docs/PUSH_RELAY.md`.

## v0.100 (2026-10-20)

**Android: one permanent signing key, so updates install.** Every earlier release was signed with a different key, so Android refused to update the app ("App not installed"). The official app is now signed with one permanent release key kept as repository secrets, and every version (test builds too) installs over the last one. Publishing a release of the official repository is refused when the secrets are missing, and the build shows the key's fingerprint. Phones that have an earlier version need one uninstall and reinstall. Touches `.github/workflows/build-android.yml`, `docs/ANDROID.md`, `SECURITY.md`.

**Passkeys on the phone work with no setting.** Enveliq now knows the official app's signing fingerprint and publishes `/.well-known/assetlinks.json` itself, so signing in with a passkey saved on the phone works for every install. `ENVELIQ_ANDROID_CERT_SHA256` is now only for someone who builds the app with their own key, and adds to the built-in one. Touches `backend/auth/passkeys.py`, `backend/app.py`, `docs/ANDROID.md`, `docs/ENVIRONMENT.md`, `SECURITY.md`, `tests/test_android_passkeys.py`.

## v0.99 (2026-10-20)

**Android: sign in with a passkey saved on the phone.** **Sign in with a passkey** now uses Android's own passkey screen, so a passkey kept in Bitwarden or Google Password Manager signs you in without opening the browser. If there is no passkey to use, or the server is not set up for it yet, it opens the browser as before (a passkey or single sign-on). To turn it on for the phone's own screen, set the new `ENVELIQ_ANDROID_CERT_SHA256` setting to the app's signing fingerprint (shown in the Android build summary) and check that `/.well-known/assetlinks.json` is reachable; the steps are in `docs/ANDROID.md`. With the setting empty nothing changes. Touches `backend/auth/passkeys.py`, `backend/app.py`, `android/` (`NativePasskey.kt`, `Api.kt`, `Screens.kt`, `build.gradle.kts`), `docs/ANDROID.md`, `docs/ENVIRONMENT.md`, `SECURITY.md`, `tests/test_android_passkeys.py`.

**Android: the inbox refreshes itself.** While the app is open on the inbox the list now reloads quietly about once a minute, and again as soon as you come back to the app, so something deleted on the website disappears without pulling down. It does not refresh while you have an email open, are writing, or have emails ticked, and does nothing while the app is out of sight. Touches `android/` (`Home.kt`), `docs/ANDROID.md`.

**Website: the sign-in page mentions the terms.** Under the password boxes it says "By signing in you agree to the terms of use and the privacy notice", with both as links, as the app does. Touches `web/static/auth.js`, `scripts/check_app_signin.mjs`, `docs/TERMS.md`.

**Wording and documents checked against the setup.** (1) The administrator description of the "include read mail" option now says 60 days (it still said 14) and uses the name **Include read mail**. (2) The privacy page, `SECURITY.md` and the guides say the same thing. (3) `docs/ANDROID.md` was brought up to date. Touches `web/static/auth.js`, `backend/mail/features.py`, `docs/PRIVACY.md`, `SECURITY.md`, `docs/ANDROID.md`.

**Android: small fixes.** (1) A task you add shows on the open email's task card straight away. (2) If the first check for "Include read mail" could not reach the server, it is checked again on the next refresh. (3) The two native text boxes (spell check and code box) keep the cursor where it was when the text is changed from outside, such as a signature being added. (4) With emails ticked in the list, **Back** now unticks them instead of leaving the app. The phone-width browser check now also covers the Include read mail panel. Touches `android/` (`Home.kt`, `TaskCard.kt`, `SpellField.kt`), `scripts/check_all_mail.mjs`.

**Android: terms and privacy are in the app.** (1) **Settings, About** now has **Terms of use**, **Privacy** and **Security**, which open the same pages as the website from your own server. (2) The sign-in screen says "By signing in you agree to the terms of use and the privacy notice", with both as links, just above the Sign in button. (3) The first time you are in on a phone, a short **Before you start** notice says that Enveliq is provided as it is with no warranty, that AI summaries can be wrong, to keep your own backups, and that an online AI service receives the text of emails it summarises. Press **I understand** to continue (or **Read the terms**). That choice is remembered on that phone only; nothing is sent to the server. Touches `android/` (`Screens.kt`, `Settings.kt`, `Home.kt`), `docs/ANDROID.md`, `docs/TERMS.md`.

## v0.98 (2026-10-20)

**Android: a nicer sign-in screen, with the two buttons fixed at the bottom.** The sign-in screen now shows the real Enveliq logo instead of plain text, with the form on one calm card (labelled boxes with soft outlines), a clear blue **Sign in** button fixed at the bottom, and under it, after a thin "or" line, **Sign in with a passkey** as a separate button with a key symbol (it still opens the browser, where a passkey or single sign-on both work), so it is not mistaken for the button that submits the details above. The words and the way sign-in works are unchanged. Touches `android/` (`Screens.kt`, `Chrome.kt`), `docs/ANDROID.md`.

**Android: the two-factor code box works with Bitwarden and the keyboard.** The code box on the sign-in screen is now the phone’s own text box, marked as a one-time code, so password managers such as Bitwarden recognise it as a two-factor code screen and can fill it, and the keyboard can offer to paste a code you have just copied. It is focused straight away (the keyboard opens) and the keyboard’s Done button confirms. Touches `android/` (`SpellField.kt`, `Screens.kt`, `res/values/ids.xml`), `docs/ANDROID.md`.

**Android: tags show in the inbox list.** Each email in the list now shows its tags as small chips under the summary (up to three, then +more). Emails with no tags take no extra space. Touches `android/` (`Home.kt`), `docs/ANDROID.md`.

**Android: the "Open this link?" box shows the whole link.** It used to say only which site the link goes to. It now also shows the full address exactly as it is in the email (wrapped, scrollable if very long, and you can select it), so you can see exactly what you are about to open. Touches `android/` (`Organise.kt`), `docs/ANDROID.md`.

**Android: spell check when writing an email.** The subject and message boxes now use the phone’s own text box, so misspelled words are underlined and a tap offers the fix, like in your other apps (it follows the phone’s spell-checker setting). Auto-correct and the keyboard’s suggestions work as normal. The boxes look the same as before. Touches `android/` (`SpellField.kt`, `Compose.kt`), `docs/ANDROID.md`.

**Android: new email glows softly, and read mail without a summary looks plain.** In the inbox, an email you have not yet opened in Enveliq has a thin blue edge and a faint blue wash (a quieter version of the website’s blue glow) and a bold subject. Opening it records that, here and on the website, so the glow goes away on both. With **Include read mail** on, read mail that has no summary yet is shown plainly (greyer, with "No summary yet" instead of a summary) so it is easy to tell from the emails that need you. Touches `android/` (`Home.kt`, `Api.kt`), `docs/ANDROID.md`.

**"All emails" is now "Include read mail", on the website and in the Android app.** The switch that added the mail you have already read (last 60 days, no email limit) is now a button, **Include read mail**, in the same place on the website (Inbox options). Press it and it opens a small box that says "Adds mail you’ve already read from the last 60 days. Summaries only when you ask." with the switch inside. The Android app has the same thing as a new envelope button on the thin row, next to the filter and tag buttons. It stays on until you switch it off, even after the app is closed (the website remembers it in your browser, the app on your phone). On Android, a read email shows "Summary not generated" with a **Generate summary** button, and the summary appears when it is ready. The same administrator and per-person feature switch still applies, and nothing else about what is kept changed. Touches `prototype/index.html`, `scripts/check_all_mail.mjs`, `android/` (`Home.kt`, `Api.kt`, `Data.kt`, `Chrome.kt`), `docs/INBOX.md`, `docs/ANDROID.md`.

**Android: Back clears the inbox filters.** When the inbox is filtered (Reviewed or Archived, needs action, a mailbox or a tag), Back now removes the filters and shows the whole inbox. Back from the unfiltered inbox is the last step and leaves the app, as before. Touches `android/` (`Home.kt`).

**Android: pinch to zoom now zooms where you pinch.** Zooming a picture or PDF used to grow from the top left corner. It now keeps the spot between your fingers in place, as you would expect, and double-tap and the + and − buttons zoom around the spot you tapped or the middle of the screen. Touches `android/` (`AttachmentViewer.kt`).

**Android: the notification bell is on the top row.** A bell sits next to search on the top row of every screen. It opens Notes and alerts and shows a small red dot when something is new. Touches `android/` (`Chrome.kt`, `Home.kt`, `More.kt`).

**Android: the task on an open email now matches the website.** The task card has a three-dot menu with **Move** (Later today, Tomorrow morning, This weekend, Next week, or Pick a day) and **Remove**, and says when it is due in the website's words: Today (with the time for a reminder), Tomorrow, a weekday or date, or "Waiting since". Your own tasks say "Your task", the AI's say "Task added", and a finished one has **Put back**. Touches `android/` (`TaskCard.kt`, `Home.kt`, `Api.kt`, `Data.kt`).

**Android: choose who a reply goes to, and write to several people.** Reply and Reply all now show To, Cc and Bcc and start with the people the website would pick (the sender; for Reply all, also the other people and everyone on Cc). You can take anyone off or add more. In every kind of email (new, reply, forward) each person becomes a small chip with a cross; type the next one and press Enter, a comma or a space, and names are suggested from your address list. Reply all is only offered when the email has people on Cc, as on the website. The three-dot menu on an open email also has **Important person** (or **Not an important person**) and **Always archive these**. Touches `android/` (`Compose.kt`, `Home.kt`, `Api.kt`, `Data.kt`).

**Android: the open email, rearranged.** (1) Pinch with two fingers to zoom a picture or PDF, scroll to move around, double-tap to go back to the original size. (2) The "Written by the AI" line under the summary is gone (the summary is still labelled "AI summary"). (3) Reply, Reply all and Forward are icons in one row directly under the summary, with a three-dot menu on the same row for Send to Junk, Block sender and Unsubscribe, and a small Show original email button just below. (4) A bar that is always at the bottom has icons for Bin, Archive, Reviewed, Tags, Remind me later and Add a task; Add a task opens a small popup with Today, Tomorrow, This weekend and Next week. (5) All the text can be selected and copied, and tapping the sender's address offers Copy. (6) Tags show as a slim row under the sender details, with no heading, and take no space when there are none. The Tags button now says why when tags cannot be loaded (for example Tags switched off, or the mailbox could not be reached), and only says the mail service does not keep tags when that is true. Touches `android/` (`Home.kt`, `Chrome.kt`, `AttachmentViewer.kt`, `OriginalView.kt`, `Organise.kt`, `Api.kt`).

## v0.97 (2026-10-19)

**Android: a slower, clearer swipe.** Swiping an email now slides it off, shows its symbol (tick, archive box or bin) growing on the coloured bar, then folds the gap closed before the Undo bar appears. Touches `android/` (`Home.kt`).

**Android: files and summaries on an email, with the website's viewer.** The app now shows each file with the AI's summary (it was reading the wrong field before, so nothing appeared), and **View** opens PDFs, pictures, tables and text in the same viewer as the website. Touches `android/` (`AttachmentViewer.kt`, `Api.kt`).

**Android: a cleaner main screen.** Menu, logo, search and your picture on one row; the bottom tabs moved into the menu; a thin row with the Inbox/Reviewed/Archived filter and a second filter button; pull down to refresh; symbols instead of words on the Reviewed, Archive and Bin buttons. Touches `android/` (`Home.kt`, `Chrome.kt`).

**Send later.** **Later** beside Send on a new email, reply or forward sends it at a time you choose (within 30 days). Waiting emails are listed under Sent, **Waiting to send** (website) and More, Waiting to send (Android) and can be taken back. They are kept encrypted in the vault, so they survive a restart; files cannot wait. Touches `backend/mail/scheduled.py`, `backend/mail/scheduled_routes.py`, `backend/app.py`, `backend/export.py`, `prototype/index.html`, `android/`, `tests/test_scheduled.py`, `scripts/check_send_later.mjs`, `docs/SEND_LATER.md`, `SECURITY.md`.

**Attach files to replies and forwards** (website and Android). A forward keeps the files of the original unless unticked and adds new ones. Touches `backend/mail/service.py`, `backend/mail/routes.py`, `prototype/index.html`, `android/`, `tests/test_attach_reply_forward.py`.

**Android: alerts for messages, notes and alerts, tasks and parcels.** Separate switches in Settings, Notifications (off by default, direct mode). The alert stream gains an `other` event that names only the kind. Touches `backend/mail/notify_routes.py`, `android/`, `tests/test_notify.py`, `docs/ANDROID.md`.

**Android: install updates from inside the app.** Settings, About, **Install it** downloads the new version through your own server, which checks it against the published checksum. The phone never contacts GitHub. Touches `backend/update_check.py`, `backend/app.py` (`GET /api/v1/app-update/apk`), `android/`, `tests/test_update_notice.py`, `docs/UPDATES.md`, `SECURITY.md`.

**Fix: signing in to the Android app with a passkey or single sign-on.** After pressing **Open the Enveliq app** in the browser, the app used to show "Something went wrong" and stay on the sign-in screen: the app cancelled its own sign-in half way. It now finishes the sign-in. The "Sign in with a passkey or single sign-on" button also no longer cuts its words off on a narrow phone. Touches `android/` (`Screens.kt`).

**Junk and Block sender.** On an opened email, **Send to Junk** moves it to your mailbox's own Junk or Spam folder (Undo works for a few seconds), and **Block sender** does that and also sends all new email from that address to Junk from then on. A new Mail rules action, **Send it to Junk**, does the same for a sender or words in the subject, and never touches your important people. Touches `backend/models.py`, `backend/mail/service.py`, `backend/mail/rules.py`, `prototype/index.html`, `web/static/auth.js`, `tests/test_rules.py`, `docs/JUNK_MAIL.md`, `docs/MAIL_RULES.md`, `SECURITY.md`.

**Android: Junk, Block sender and Blocked senders.** The same two buttons on an opened email, and **Settings, Blocked senders** to see and undo blocks. The block is made after the Undo time. Touches `android/`.

**Android: warnings and unsubscribe.** A boxed "Take care with this one" note shows why an email looks odd, and **Unsubscribe from this sender** appears when the email carries one (the link asks first). Touches `android/`.

**Android: Find any email.** More, Find any email searches all your mailboxes, old email and Junk too. Touches `android/`.

**Android: write better.** Attach files to a new email, your saved signature is put in the box, pick an address from the phone's contacts (no permission needed), and `mailto:` links from other apps open a new email in Enveliq. Touches `android/` (`Compose.kt`, `MainActivity.kt`, `Api.kt`, manifest).

**Android: open the next email.** A Settings switch: after you archive or mark reviewed the email you are reading, the next one opens. Touches `android/`.

**Your devices on the website.** The Sign-in and security page now lists where you are signed in and lets you sign another device out, as the Android app already did. Touches `web/static/auth.js`, `scripts/check_devices_page.mjs`, `.github/workflows/ci.yml`.

**Download the Android app.** A link on the website's front page and guide menu, in the website's Settings, and in the app (Settings, About, Get the Android app). They open the newest release page. Touches `website/`, `web/static/auth.js`, `prototype/index.html`, `android/`.

**Guides.** The Android guide is rewritten (it no longer says the repository is private or that features are missing that now exist), and the Android and Junk mail guides are now in the website's menu. Touches `docs/ANDROID.md`, `docs/JUNK_MAIL.md`, `website/build.mjs`, `.github/workflows/ci.yml` (comments).

**Fix: Junk Mail drops an email that is no longer there.** If an email had been moved or deleted since the page last looked, pressing View original email or Not Junk only said "no longer in Junk Mail" and the card stayed. Now the card is taken off the list at once (on the server and on the page). Touches `backend/mail/junk.py`, `backend/mail/junk_routes.py`, `prototype/index.html`, `tests/test_junk.py`, `docs/JUNK_MAIL.md`.

**Fix: "Show the original email" no longer sits in a small scrolling box.** Some emails (for example an invoice with fixed heights in its own styles) made the formatted view a short box with its own scrollbar. The formatted page now always takes the height of the whole email, so you scroll the window as you read it. Touches `backend/mail/htmlview.py`, `tests/test_htmlview.py`.

**Android: Back goes to the inbox.** Pressing Back on Tasks, Drafts, More or Settings now returns to the inbox; Back on the inbox leaves the app. When your server is older than the app and lacks a feature, the app now says the server needs updating instead of "Not Found". Touches `android/` (`Home.kt`, `Api.kt`).

**Android: beyond email.** (1) **Tasks** now shows your real task list (the same as the website: due today, upcoming, finished) with Done, Move (later today, tomorrow, the weekend, next week), Not today, Remove and Put back; tapping a task opens its email. (2) A new **More** tab opens **Notes and alerts** (the bell: read, dismiss, clear all), **Messages** (read and reply to your household's conversations), **Shipping** (parcels, delays, tracking link), **Trips and calendar** (upcoming bookings) and **News feeds** (read, refresh). Each uses the website's own route, so the server still decides what you may see, and a feature switched off on the website says so. (3) **Share to Enveliq:** share text from any app and it opens a new email with it, ready to address (nothing is sent until you press Send). (4) **Tablet and landscape:** on a wide screen the inbox and the open email sit side by side. (5) A **home-screen widget** shows how many emails are waiting (the number only). Nothing new on the server. Touches `android/` (new `More.kt`, `WaitingWidget.kt`, widget resources; `Home.kt`, `Compose.kt`, `MainActivity.kt`, `Api.kt`, `Data.kt`, manifest), `docs/ANDROID.md`, `SECURITY.md`.

**Android: sign in with a passkey or single sign-on.** The app's sign-in screen has **Sign in with a passkey or single sign-on**. It opens your server's sign-in page in the phone's browser (new page `/app-signin`), where you sign in the usual way (password and second step, passkey or single sign-on); the page then hands the app a one-time code and the app finishes signing in. The code lasts two minutes, works once, and is useless without a secret only the app holds (PKCE), so another app on the phone cannot use it. After single sign-on the browser lands on the inbox; go back to the app and press the button once more and it finishes at once. Every sign-in rule is still decided by the server. New routes `POST /api/v1/auth/app-link` and `POST /api/v1/auth/app-link/exchange`. If your site is behind Cloudflare Access, the browser page needs to be reachable in a browser (signing in to Access there is fine); the app itself still only uses `/api`. Touches `backend/auth/routes.py`, `backend/app.py`, `web/static/auth.js`, `scripts/check_app_signin.mjs`, `.github/workflows/ci.yml`, `tests/test_devices.py`, `android/`, `docs/ANDROID.md`, `SECURITY.md`.

**Android: Your devices, and a check for a new version.** Settings, Security, **Your devices** lists where you are signed in (each device has a plain name, such as "Enveliq app on Pixel 8" or "Chrome on Windows", and when it signed in) and lets you sign any other one out at once; you only ever see your own. About, **Check for a new version** tells you when a newer release is out and opens its download page (the app does not install itself: Android asks you to confirm the install). New routes `GET /api/v1/auth/devices`, `DELETE /api/v1/auth/devices/{id}` and `GET /api/v1/app-update`; sessions now carry a device name and a public id. Touches `backend/security.py`, `backend/auth/routes.py`, `backend/app.py`, `tests/test_devices.py`, `tests/test_update_notice.py`, `android/`, `docs/ANDROID.md`, `SECURITY.md`.

**Android: swipe, select several, search and remind me later.** Swipe an email right or left to Archive, Bin or mark it Reviewed (you choose each side in Settings, Swipe on an email, or switch a side off; Undo works as before). Press and hold an email to select several, then Reviewed, Archive or Bin for all of them, or Select all. **Search** looks through the emails in your inbox. **Remind me later** on an opened email puts it away until in 3 hours, tomorrow morning or next Monday morning (it uses the website's existing snooze, so it shows there as snoozed too); emails snoozed on the website no longer show in the app's inbox until their time. Touches `android/` (`Home.kt`, `Api.kt`), `docs/ANDROID.md`.

**Android: write email.** Reply, Reply all and Forward at the top of an opened email, and **New email** (the pencil button on the inbox). Suggestions from your address list appear as you type To, Cc and Bcc, you can pick the mailbox to send from, and the "undo send" bar shows how long you have to take it back. Closing a half-written email offers to keep it as a draft; the new **Drafts** tab lists the same drafts the website keeps (14 days). The writing screen opens full screen, with Send and Save draft fixed at the bottom. Nothing new on the server: the app uses the website's existing reply, forward, send, address list and drafts routes. Touches `android/` (new `Compose.kt`, `Home.kt`, `Api.kt`, `Data.kt`), `docs/ANDROID.md`.

**Android: alerts and comfort, and Mark unread.** (1) **Mark unread:** an email you marked Reviewed can be marked unread again (button in the Reviewed view in the app); the mailbox gets its unread mark back and the email returns to the inbox. A Reviewed card now keeps its pointer to the mailbox for this (an Archived card still drops it). New route `POST /api/v1/accounts/{id}/messages/{id}/unread`. (2) **What to alert me about:** all new email, only email that needs action, or only from important people. (3) **Appearance:** follow the phone's light and dark setting or choose, plus a text size. (4) **Alerts clear at once** when an email is reviewed or moved elsewhere: the live connection now also sends the ids of emails that are no longer waiting (`gone`). (5) **Hide the watching note** button, **Check connection** on sign-in, a one-time **welcome**, TalkBack actions on every email row, and the app no longer restarts when the phone is rotated. Touches `backend/app.py`, `backend/mail/{review,service,notify_routes}.py`, `tests/`, `android/`, `docs/ANDROID.md`, `SECURITY.md`.

**Android: Settings made over, From address, tag screens and the full email.** (1) **Settings** is now a short list of topics (Notifications, Swipe on an email, Security, Account, About); each opens its own page with switches, tick-lists and a fixed Back button, and a choice opens one more page. (2) **From:** when you have more than one address (a mailbox's own address and its "send as" aliases), the writing screen has a From picker for new emails, replies and forwards; replies and forwards use the mailbox the email arrived in; the mailbox's own address stays the default and is saved in drafts. (3) **Choose tags** opens a full screen window with a search box, a scrolling list with tick boxes and one Save, so several tags can be added and removed together; current tags start ticked. (4) The inbox tag chips are replaced by one **Tags** control that opens a full screen searchable list with email counts; tap a tag to filter, and Clear filter removes it. (5) **Show the original email** now shows the email as its sender formatted it (layout, colours, tables, embedded pictures, links) using the same safe rebuilt copy the website uses, with JavaScript off and no network until you tap Show pictures; plain text is shown when there is no formatted version or when chosen. Nothing new on the server. Touches `android/` (new `Settings.kt`, `OriginalView.kt`; `Compose.kt`, `Organise.kt`, `Home.kt`, `Api.kt`, `Data.kt`), `docs/ANDROID.md`, `SECURITY.md`.

**Android: tags, files, links and your Reviewed and Archived email.** On an opened email, **Tags** shows its tags and lets you put one on or take it off, or make a new one (only when your mail service keeps tags). **Files with this email** lists each attachment with its size and the AI's short note (labelled as written by the AI); **Save to my phone** fetches the file for that moment and saves it where you choose, and the app keeps nothing. Once you show the original email, **Links in this email** lists its links with where each really goes, and asks before opening one (with a warning for unusual ones). The inbox has **Inbox / Reviewed / Archived** views (the website keeps Reviewed and Archived mail for a few days), filter chips for each tag, and one chip per mailbox when you have more than one. Nothing new on the server. Touches `android/` (new `Organise.kt`, `Home.kt`, `Api.kt`, `Data.kt`), `docs/ANDROID.md`.

## v0.95 (2026-10-19)

**Enveliq for Android.** A real Android app (Kotlin and Jetpack Compose) in the new `android/` folder. You sign in to your own server with the same password and two-factor steps as the website, and the app lists, opens and marks email Reviewed, Archived or Bin, with Undo. It has the Reviewed, Archive and Bin buttons fixed at the bottom, a Tasks tab, its own notification channels and a test notification that keeps the lock screen generic, and a "Hide in recent apps" switch. A new workflow, **Build Android app**, builds and signs the installable file and attaches it to the run under Artifacts; when you publish a release it is also attached to the release as `Enveliq-<tag>.apk` with a checksum. There is nothing to set up for signing: GitHub keeps the signing key (a small weekly job keeps it alive), so each version installs over the last; your own key can be added later through four optional secrets. The app's version is the release tag. **Stays signed in:** "Keep me signed in on this phone" (on to begin with) keeps your sign-in, encrypted with a key in the Android Keystore, so the app opens straight to your inbox; Sign out removes it. Touches `android/` (new), `.github/workflows/build-android.yml` (new). See [Enveliq for Android](ANDROID.md).

**New-email alerts on Android.** In the app's Settings, **Tell me when new email arrives** makes the phone show a quiet "New email" note as soon as the AI has finished reading a new email (never before). The lock screen only says "New email"; the sender and subject show once the phone is unlocked. The app keeps one quiet connection to your own Enveliq: no polling, no Google. It does nothing while the phone has no signal and reconnects as soon as there is one, waits longer after each failed try (up to 5 minutes), and looks at the inbox only when the server says something is ready. **Quiet hours** (from and until) keep alerts without sound or buzz. A **Keep alerts on time** button lets Enveliq run without Android's battery limit if alerts ever come late. Alerts need the app to stay signed in, so turning them on keeps your sign-in on the phone; signing out turns them off. Android shows one small permanent note, "Enveliq is watching for new email", while this is on. Touches `backend/mail/notify_routes.py` (new `GET /api/v1/me/new-mail-events`), `tests/test_notify.py`, `android/` (`MailWatcher.kt` new, `Notifier.kt`, `Home.kt`, `AndroidManifest.xml`). See [Enveliq for Android](ANDROID.md).

**Android: fixes.** The app no longer crashes when new-email alerts are turned on (it was missing the permission to check the network connection), and the alerts service can no longer stop the app from opening: if it cannot start it switches itself off and tells you. The sample email is gone: the app opens straight to sign-in. The sign-in boxes are now marked as username, password and verification code so password managers such as Bitwarden recognise them. Touches `android/`. See [Enveliq for Android](ANDROID.md).

**Android: nicer sign-in and alerts.** The address box starts with `https://`, the password has a **Show** button, and errors are in plain words (including a clear message when a security layer such as Cloudflare Access answers instead of Enveliq). New-email alerts open that email when tapped, have **Reviewed** and **Archive** buttons (shown only once the phone is unlocked), and go away by themselves when the email is no longer waiting. The inbox can be pulled down to refresh and keeps its place. Settings, Security has **Ask for my fingerprint, face or PIN** (locks again after a minute out of sight; never locks out a phone without a screen lock). The remaining ideas are on the Android to-do list in [Enveliq for Android](ANDROID.md). Touches `android/` (new `MailActionReceiver.kt`; the app now uses AndroidX Biometric), `docs/ANDROID.md`, `SECURITY.md`.

**Android: address can end in /api.** In the app's sign-in you can type your Enveliq's address with or without `/api` on the end. The app only uses the `/api/v1/...` routes, so a site behind Cloudflare Access (or similar) can leave just `/api` open for the app while the website stays protected. Touches `android/.../Api.kt`, `docs/ANDROID.md`.

**Android: alerts through Google's push service (optional).** The app's Settings offers a second way to get new-email alerts: **Google's push service**. Alerts are instant, the "watching" note goes away, and nothing but "mail" and a count goes through Google (the phone asks your Enveliq for the sender and subject itself, and shows them only when unlocked). It needs no set-up on any Enveliq server and nothing in Administration: every server sends its wake-up requests to a small shared push relay (`relay/`, a Cloudflare Worker) that alone holds the Firebase key, so no Enveliq server ever holds one. Until chosen, the app never contacts Google. The app is another place the same new-email alerts go (so quiet hours and filters from Settings, Alerts apply), with a Send a test button, up to 5 phones, and removal when you sign out or switch back. New server routes `GET/POST /api/v1/me/notifications/android`, `POST .../{id}/test`, `DELETE .../{id}`. The relay address is not in the source code: the official release and preview images are built with it from the repository variable `ENVELIQ_PUSH_RELAY`, so a fork or source build offers no Google push until its owner sets up their own relay (`ENVELIQ_PUSH_RELAY`) and Firebase project. For the publisher: add the variable `ENVELIQ_PUSH_RELAY` and the GitHub secret `GOOGLE_SERVICES_JSON`. **The app's identity is now `app.enveliq` (it was `app.enveliq.android`), to match Firebase: install the new build and uninstall the old one.** Touches `backend/mail/fcm.py` (new), `extra_channels.py`, `notify_routes.py`, `mail_alerts.py`, `tests/test_notify.py`, `relay/` (new), `.github/workflows/`, `android/`. See [Enveliq for Android](ANDROID.md) and [Push relay](PUSH_RELAY.md).

**Show the original email in the reading panel.** The View panel has a new Reading tick box, **Show the original email**. When it is on, each email opened in the reading panel (inbox, Needs action and the other lists) shows its original straight away, between the Reply row and the email details. The Reply row moves up under the AI summary and attachments, the details move down, and the original scrolls inside its own box however long it is. It is the same safe copy as View original email, fetched when needed and never saved; a redraw of the page does not reload it. Touches `prototype/index.html`, `backend/mail/notify_routes.py` (the saved view gains `show_original`). See [Reading the original email](ORIGINAL_EMAIL.md).

**Ticked emails stay ticked while an AI summary runs.** When an AI summary finished, the page reloaded the list and untick everything you had selected. Reloads now keep the ticks on emails that are still in the list. Touches `prototype/index.html`. See [Inbox](INBOX.md).

**Tasks opens on the List view.** The first time (or when no choice has been remembered) the Tasks page shows List instead of Focus. Focus and Calendar are still there. Touches `prototype/index.html`. See [Inbox](INBOX.md).

**Google Calendar: make a new calendar or use one you already have.** Under Settings, Rules & calendar, Google Calendar (instant) now asks first: **Make a new calendar called "Enveliq tasks"** (as before, the narrow permission) or **Use a calendar I already have** (Google asks for a wider permission; you then pick one of your calendars from a list). Enveliq only adds and removes its own events in the calendar you pick and never deletes it. Administrators who want the second choice add two scopes in the Google console once (see [Calendar](CALENDAR.md), Step 7), and people reconnect. Touches `backend/mail/gcal.py`, `backend/mail/calsync.py`, `backend/mail/gcal_routes.py`, `web/static/auth.js`, `prototype/index.html`. See [Calendar](CALENDAR.md).

**Junk Mail.** A new Junk Mail page in the left menu lists what your mail services (Gmail, Microsoft, Proton and others) put in their Junk or Spam folders. The AI reads each email and says **Yes, it's junk** or **Needs review**, with a short summary and a line saying why, always labelled as the AI's. **View original email** opens it with links, pictures from the internet, files and anything that runs switched off. **Not Junk** moves the email to the Inbox at your mail service (and into your Enveliq inbox as new mail). It has its own switch under Features. Touches `backend/mail/junk.py` and `backend/mail/junk_routes.py` (new), `backend/mail/llm.py`, `backend/mail/htmlview.py`, `backend/mail/bridge.py`, `backend/mail/features.py`, `backend/export.py`, `backend/app.py`, `prototype/index.html`. See [Junk Mail](JUNK_MAIL.md). A mailbox that cannot be read is now named on the page with a plain reason, the AI settings saved in Administration are used, and an unexpected error is logged on the server. One junk email with a broken character in its sender name no longer stops the whole list from loading.

**Search all my mail results are now in the list, with Summarise Emails.** The results no longer open in a pop-up: they appear in the main list area where ordinary search results are. Each result has a tick box on its left (one at a time, Shift for a range, or Select all). When two or more are ticked, a **Summarise Emails** button above the results keeps them all and adds them to the AI summary queue. Touches `backend/mail/find_routes.py` (a new `POST /api/v1/find/results/keep`), `prototype/index.html`. See [Find any email](FIND_MAIL.md).

**Search all my mail runs by itself when Fast search is ready.** If every mailbox has Fast search on and finished, typing in the search box searches all your mail after a short pause and shows the results in the list. Otherwise the Search all my mail button stays. Touches `prototype/index.html`. See [Find any email](FIND_MAIL.md).

**Select all in the inbox list.** A Select all box next to "Recent emails" ticks every email in the list. It works with single ticks, Shift ticking and the Reviewed, Archive and Bin bar, on a computer and on a phone. Touches `prototype/index.html`. See [Inbox](INBOX.md).

**Phone: the selection bar in calm mode.** The Reviewed, Archive and Bin bar was laid out badly on a phone in calm mode; it now sits properly under the heading. Touches `prototype/index.html`.

## v0.94 (2026-10-18)

**Settings is now a full screen with one menu.** Pressing Settings opens a full-screen Settings. The left panel turns into the Settings menu: your own pages above a line, and below the line a group called Administration (only administrators see it). On a computer the menu is the same left panel as the inbox (same logo, spacing, buttons and footer); only the middle list changes. The top bar stays as it was, but its search box says "Search settings" and finds settings pages instead of email; press Enter to open the first match or Escape to clear it. The separate Administration item in the account menu is gone, because Administration now lives in the same menu. On a phone, Settings opens as a plain list of big rows (with its own search at the top); each page opens full screen with a Back button. The server still decides who may use Administration; the page only hides it. Touches `prototype/index.html`.

**Every Settings and Administration page, tidied.** Cards sit in two columns where there is room. Forms with a single Save button now save by themselves when you change something, so that button is gone; buttons that test a connection or store a key or password are kept. Long explanations fold behind "More about this" or "Read more", and step-by-step guides sit inside "Show the steps". In Administration the AI model tests and saves by itself. Touches `web/static/auth.js`, `web/static/welcome.js`, `web/static/auth.css`.

**General settings are now three short columns.** Undo send and "Keep them for" are plain drop-down lists instead of folds with number boxes, each Features option is a single tick with a short name (the long explanations fold away under "What each one does"), and Keyboard shortcuts fold away under "Show shortcuts". Everything still saves as you change it. Because "Keep them for" is now a list, it offers 7, 14, 30, 60, 90, 180 and 365 days, up to the limit your administrator allows.

**The inbox list stays where you scrolled it.** After you scrolled down the list, a refresh in the background could pull it back up to the highlighted email a few seconds later. It now only moves to the highlighted email when the highlight changes. Touches `prototype/index.html`.

**Settings and Administration, tidied.** Settings goes from 14 pages to 7 (Account, Mailboxes, People & writing, Rules & calendar, Alerts, General, Help) and Administration from 15 to 6 (People & sign-in, Mail, AI, Features, Notifications, System). Nothing is removed: each older page is now a section on the page where you would look for it, and older links still work. Sections sit side by side when there is room, so there is far less scrolling. Choices now save as you make them: your profile, the Features lists (yours and the administrator's), Undo send and the Reviewed and Archived lists save when you tick or change them, with a quiet "Saved ✓". Find models on the AI page now shows the models as buttons to tap. Touches `prototype/index.html`, `web/static/auth.js`, `web/static/welcome.js`, `web/static/auth.css`. See [Settings and Administration](SETTINGS.md).

**Links show their whole address before you open them.** When you press Open on a link, or press a link in an email, the question now shows the website and, under it, the complete address exactly as the link has it, on as many lines as it takes, so a very long tracking address can be read in full before you press Open it. Applies to the Links in this email list, links in the plain text and links in the formatted email. Touches `prototype/index.html`. See [Reading the original email](ORIGINAL_EMAIL.md).

**A calmer Mailboxes page.** Each mailbox is now a small card with its name, address, how it is doing, and two buttons: Sync now and Edit. Edit opens that mailbox's own page, where Check for new mail automatically, Write AI summaries and Follow sent mail for replies are plain checkboxes that save the moment you tick them (a quiet "Saved ✓" confirms it). The name saves when you leave the box and the label colour when you choose it. Diagnostics is folded away, and Remove sits at the bottom with a question first. New mailboxes start with all three switched on. Cards sit two across on a computer and one under another on a phone. Touches `web/static/auth.js`, `web/static/welcome.js`, `web/static/auth.css`. See [Proton Bridge](PROTON_BRIDGE.md) and [AI summaries](AI_SUMMARIES.md).

**The original email, as the sender made it.** View original email now shows the email with its own colours, layout, tables, links and the pictures that travel inside it, with a Plain text button always one tap away (and shown automatically when an email has no formatting). Scripts and forms are removed, pictures from the internet wait for a Show pictures button, and links still ask before opening. It works the same for Proton Mail, Gmail, Microsoft and other IMAP mailboxes. Touches `backend/mail/htmlview.py` (new), `backend/mail/routes.py`, `backend/mail/parse.py`, `backend/app.py` (the page may now show one sealed frame of its own), `prototype/index.html`. See [Reading the original email](ORIGINAL_EMAIL.md).

**View on an attachment opens the file.** The View button on a file under an email now opens that file in the picture or document viewer instead of the whole original email; Save and the email you were reading are untouched. Touches `prototype/index.html`.

**The email no longer jumps to the top on a phone.** Scrolling down in an open email stays put when the page refreshes in the background or something finishes loading. Touches `prototype/index.html`.

**Hover buttons in more places.** The Reviewed, Archive and Bin buttons that appear when the mouse is over an email now also appear in the reading-pane layout, and the Reviewed and Archived lists get a Remove from this list button, in the same place and style. Touches `prototype/index.html`.

**Search clears when you move on.** Choosing something from the menu now empties the inbox search box, so you no longer have to press the X to see the whole page again. Touches `prototype/index.html`.

**Find models.** On Administration, AI model (and the setup guide), a **Find models** button asks the AI server which models it has and lets you tap one to fill in the name, so nobody has to look it up. Administrators only; it follows the same address rules as the Test button, sends no email text and never returns the access key. Touches `backend/mail/llm.py`, `backend/mail/routes.py`, `web/static/welcome.js`.

**Find any email.** A new **Search all my mail** button under the inbox search box asks each connected mail service (Proton Bridge, Gmail, Microsoft and other IMAP services) to search the whole mailbox, every folder, and lists every match as sender, subject and date, newest first, with a total, per-mailbox progress and Cancel. **View original email** reads one; **Summarise** keeps that one email in a new **Found emails** page in the left menu for 60 days, or until Reviewed (which only removes it from the list and never changes the mailbox). Typed words are all required, "quoted" words must appear together, commas are ignored. Nothing a search finds is stored, and the search words are never logged. A new **Find any email** switch (administrator and per person) turns it off. Touches `backend/mail/find.py`, `find_routes.py`, `bridge.py` (folder-aware locations and search), `service.py`, `features.py`, `extra_routes.py`, `scheduler.py`, `prototype/index.html`, `docs/FIND_MAIL.md`, `SECURITY.md` and `docs/PRIVACY.md`.

**Fast search (optional).** In Settings, General, Fast search, a person can switch on, for one mailbox, a private encrypted word list so searching a very large mailbox (recommended for Proton Mail) is instant. It is off by default and needs a plain warning to be accepted. The list holds no email text, skips long numbers and words, is sealed with a key from the vault key, is left out of backups and exports, and is deleted when switched off, when the mailbox is removed and when the person is removed. Touches `backend/mail/find_index.py`, `backend/crypto_vault.py` (a derived key), `web/static/auth.js` and `auth.css`.

**Emails without a summary are tried again.** Unread emails that were shown without a summary (the AI was busy or did not answer, or they arrived before AI summaries were switched on) are now put back in the AI line after each mailbox check, with longer waits between tries and a limit of five. Their card now always has a **Generate summary** button and says plainly why a summary is missing: no AI model set up, summaries off for the mailbox, or the last reason it failed. Touches `backend/mail/service.py`, `extra_routes.py` (the queue answer carries a short notice), `prototype/index.html` and `docs/AI_SUMMARIES.md`.

**Password managers and the two-factor page.** The sign-in code box now carries the usual one-time-code hints (name, label, placeholder, no auto-capitalise) so password managers such as Bitwarden offer the authenticator code. The Vault key guide now uses `docker exec -it enveliq ...`, because some Docker Compose versions reject flags such as `-it` and `-m` on `docker compose exec`. Touches `web/static/auth.js`, `docs/VAULT_KEY.md` and `backend/vault_key.py`.

**A new install needs a vault key.** Setup no longer asks for a vault passphrase. Before first start, the install guides now tell people to make a key (`openssl rand -hex 32`, or a Docker command for Windows), save a copy in a password manager and put it in `.env` as `ENVELIQ_VAULT_KEY`. Without it, the setup page explains what to do and does not continue. Every install file (`install/docker-compose.yml`, `docker-compose.build.yml`) now has a fourth marked line for the key, and every install guide (Docker Desktop, Docker Compose, Raspberry Pi, Proxmox, Arcane, Portainer, Dockge, Synology, Unraid, TrueNAS) tells people to make it first. A key line left as the placeholder counts as no key. Installs that already use a passphrase keep working. Touches `backend/app.py`, `web/static/auth.js` and `auth.css`, `docs/VAULT_KEY.md`, the install guides, `docker-compose.yml`, `.env.example` and `SECURITY.md`.

**One-page, copy-and-paste install.** The install files now read the address, setup code, plain-http switch and vault key from a `.env` file (or a panel's environment box), with safe defaults, so nothing in the install file needs editing. The install page (`docs/install/README.md`) is one page with a single block that downloads the install file, makes the vault key into `.env` and starts Enveliq, for Mac, Linux and Windows PowerShell. Docker Desktop, Docker Compose and Raspberry Pi guides use the same `.env` step. The setup code no longer has to be invented: Enveliq makes one and the page says how to read it. Touches `install/docker-compose.yml`, `install/docker-compose.build.yml`, `README.md` and `docs/install/`.

## v0.93 (2026-10-16)

**Faster automatic checks.** The checks that run on each pull request now finish much sooner: the backend tests use cheap password and vault-key settings (one separate test still proves the real, full-strength settings), run on every processor at once, and the browser checks are split into three jobs that run side by side, with one "Browser checks" result that stands for all three. A pull request only runs the checks its changed files can affect. A push to `main` runs the quick set; the full set also runs every Monday morning, on every release and when started by hand. One generic workflow keeps `preview/vX.YY` level with `feat/vX.YY` and no longer builds the preview twice, replacing the two version-specific sync workflows. No change for people using Enveliq. Touches `.github/workflows/`, `tests/conftest.py`, `tests/test_kdf_strength.py`, `tests/test_hardening.py` and `requirements-dev.txt`.

**All emails now covers 60 days with no message count cap.** Turning on All emails fetches all inbox message headers from the past 60 days, without the previous 100 email limit. The Sent and other views are unchanged. Touches `backend/mail/service.py`, `backend/mail/bridge.py`, `prototype/index.html` and `docs/INBOX.md`.

**Pending email actions no longer interrupt another email you are reading.** When the five second Reviewed, Archive or Bin countdown finishes, Enveliq now updates only the email that action belongs to. A different email or original email viewer opened during the countdown stays open. Touches `prototype/index.html`, `scripts/check_undo_stays.mjs` and `docs/INBOX.md`.

## v0.92 (2026-10-16)

**Live mailbox changes across active browsers.** A new authenticated SSE stream updates the inbox when messages, tags, reviewed/archived/deleted state, mailbox folder locations or opened markers change. Auto-reconnect and a periodic fallback preserve continuity, while ordinary mailbox sync remains responsible for fetching provider mail. Touches `backend/mail/notify_routes.py`, `prototype/index.html` and tests. See `docs/INBOX.md`, `docs/ARCHITECTURE.md` and `SECURITY.md`.

**Personal new-email alert filters and mailbox muting.** In Settings → Email alerts, each person can select all mail, Important people, or Needs action notifications and mute notifications from individual connected mailboxes. Existing channels and quiet hours are unchanged. Filtering is performed on the server before sending. Touches `backend/mail/{notify.py,notify_routes.py,mail_alerts.py,scheduler.py}`, `backend/app.py`, `prototype/index.html`, tests and docs. See `docs/NOTIFICATIONS.md` and `SECURITY.md`.

**Attachment summaries stay in the selected email.** Opening or closing an attachment disclosure no longer clears the right hand reading pane. Touches `prototype/index.html` and `scripts/check_attachment_summaries.mjs`. See `docs/INBOX.md`.

**Consistent action feedback with an optional popup switch.** Success confirmations use the existing unobtrusive toast and matching icon styling. Tag additions and removals and inbox synchronisation report their actual results. The View panel offers **Show action confirmations**, enabled by default and remembered privately per person. Turning it off hides routine success messages, not errors, pending sending or Undo. Touches `prototype/index.html`, `backend/mail/notify_routes.py`, `scripts/check_inbox_real_mail.mjs` and `tests/test_notify.py`. See `docs/INBOX.md`.

**Return safely from Android email notifications.** A notification launch gives Back an inbox destination without closing Enveliq or changing ordinary navigation. Touches `prototype/index.html` and notification browser checks. See `docs/NOTIFICATIONS.md`.

**Remember inbox position and selected email.** The inbox keeps its scroll position on each device through navigation and refresh; the selected email is saved privately in the encrypted vault for that signed-in person. Touches `prototype/index.html`, `backend/mail/notify_routes.py`, `backend/app.py`, browser and backend tests. The saved selection is also cleared when a user is deleted. See `docs/INBOX.md` and `SECURITY.md`.

**Email action buttons are easier to spot.** Tag, Task, Reply and other controls inside an email have a fine oval outline without changing their size or spacing, in either appearance mode. Touches `prototype/index.html`, `scripts/check_back_button.mjs`. See `docs/INBOX.md`.

**Swipe to open and close the mobile sidebar.** On a phone, swipe in from the left screen edge to open the menu, and swipe left across the menu to close it. The browser or phone Back button also closes the menu without leaving the current page. Touches `prototype/index.html`, `scripts/check_back_button.mjs`. See `docs/INBOX.md`.

## v0.91 (2026-10-15)

**New guide: Notifications, webhooks and news feeds.** A plain-words page in the install guides (and on the website) that shows how to make a key, send a note with a webhook or a WebSocket, test it with `curl`, connect Home Assistant step by step (RESTful Command, a test, then an automation that forwards every new Home Assistant notification), rotate the key, and follow websites with news feeds. It uses only made-up example addresses and keys. Touches `docs/install/notifications.md`, `docs/install/README.md`, `docs/README.md`, `website/build.mjs`.

**Services can now send you a note with a plain web request (webhook).** Tools that cannot keep a WebSocket open (Node-RED, n8n, Uptime Kuma, a Home Assistant `rest_command`) can `POST` a JSON note to `/api/v1/inbound/webhook` with `Authorization: Bearer YOUR-KEY`. It is for everyone: the same key from the bell's **Show how to connect** fold, the same limits, and the note lands only in that person's bell. It also answers on the local network address. The fold in the bell now explains it. Touches `backend/mail/inbound_routes.py`, `backend/security.py`, `backend/app.py`, `prototype/index.html`. Tests in `tests/test_inbound.py` and `scripts/check_bell.mjs`. See `docs/NOTIFICATIONS.md`, `SECURITY.md`.

**The reading panel on the right is now the first view, and each person's view is remembered.** Someone who signs in for the first time starts with the **reading panel on the right**. After that, the layout, density, width, open-rows and preview choices are saved for that person on the server (encrypted), so they survive restarts, updates and a change of browser, and one person's choice is never copied to another. The right and bottom reading panels start with nothing selected and say "Nothing selected" with a few quick actions (such as Read emails and Open tasks), and they clear again after a refresh. Touches `backend/mail/notify_routes.py` (`GET` and `PUT /api/v1/me/mail-view`), `prototype/index.html`. Tests in `tests/test_notify.py`. See `docs/INBOX.md`.

**New emails glow blue until you open them, on every device.** An email you have not opened yet shows a soft blue glow. Which emails you have opened is kept per person on the server (encrypted) so it is the same on your phone and your computer, and it never changes anything in your mail provider (nothing is marked read there). Opening an email from a notification link counts as opening it. Touches `backend/mail/notify_routes.py` (`GET` and `POST /api/v1/me/mail-opened`), `prototype/index.html`. Tests in `tests/test_notify.py`.

**Phone and browser notifications are quicker and easier to test.** A new-mail alert is sent as soon as each summarised email is visible, instead of waiting for the whole batch. In Settings each registered browser device has its own **Test** button, so you can test one phone without notifying the others; a failed test is reported even when another device worked, and registering the same browser again keeps its working subscription. Touches `backend/mail/extra_channels.py`, `extra_routes.py`, `notify_routes.py` (`POST /api/v1/me/notifications/browser/{device_id}/test`). Tests in `tests/test_notify.py`.

**Deleting a person also clears their saved layout and opened-email list.** Touches `backend/app.py`. Test in `tests/test_inbound.py`.

**Maintenance: the test branch follows the version branch by itself.** `.github/workflows/sync-v091-preview.yml` copies each push on `feat/v0.91` to `preview/v0.91` (it refuses to overwrite anything not already on the version branch) and starts the preview build.

**The phone's top bar is less crowded, and an open email no longer looks zoomed in.** On a phone, **New email** (the pencil) and **News feeds** moved from the top bar into the menu, so the bell, Search and Sync always fit on the screen (Sync was being pushed off the right edge). Inside an open email, long words, addresses and the task line now wrap instead of widening the page, which is what made it look zoomed in; the browser is also told not to enlarge text on its own and a double tap no longer zooms. Touches `prototype/index.html`. Browser check `scripts/check_phone_width.mjs` (new); `check_email_features`, `check_phone_overlays` and `check_bell` updated. See `docs/INBOX.md`.

**You can choose the colour of each mailbox's label.** On the Mailboxes page, a **Label colour** drop-down on each mailbox (Automatic, Blue, Green, Orange, Pink, Red, Teal, Purple, Lime) sets the colour of the small label that shows which mailbox an email came from. Stored with the mailbox's settings as `color`; the server accepts only those names. Touches `web/static/auth.js`, `auth.css`, `backend/models.py`, `prototype/index.html`. Tests in `tests/test_hardening.py`, `scripts/check_mailbox_label.mjs` and `scripts/check_mailbox_e2e.mjs`. See `docs/INBOX.md`.

**You can rename a mailbox.** Press **Rename** on a mailbox on the Mailboxes page, type a new name and press **Save name**; the name changes everywhere it is shown, including the label on each email, and nothing else changes. Only the person who connected the mailbox can do it. Uses the existing `PATCH /api/v1/accounts/{id}`; touches `web/static/auth.js`. Tests in `tests/test_hardening.py`, browser check in `scripts/check_mailbox_e2e.mjs`. See `docs/INBOX.md`.

**Notification bell, and a WebSocket door for Home Assistant.** A bell at the top right, beside the news-feed icon, collects notes sent to you by Home Assistant and other services on your network, and your unread chat messages, in one drop-down (full screen on a phone). Services connect to a new WebSocket door with a key you make for yourself in the bell, and the door also works on the machine's local network address, so it still works when Cloudflare sits in front of the public address. See `docs/NOTIFICATIONS.md`, `docs/NETWORK_ACCESS.md` and `SECURITY.md`. A new library, `websockets`, is added to `requirements.txt`.

**A label shows which mailbox each email came from.** With more than one mailbox connected, every email in the list, and the open email, carries a small coloured label with the mailbox's name. With one mailbox there is no label. See `docs/INBOX.md`.

**On a phone, Back closes an open email.** An email open full screen now has its own step in the history, so the back button or gesture closes it and shows the list instead of leaving Enveliq. See `docs/INBOX.md`.

**Search in the Tags window, and a note about always tagging a sender.** When you have more than 8 tags, a search box at the top of the Tags window keeps only the tags that have the letters you type. A new note, "Always tag or filter this sender.", opens a small pop-up that explains this is done by making a filter at your email provider. See `docs/TAGS.md`.

**Search your tasks.** The Tasks page has a box to find tasks by typing part of their words. See `docs/INBOX.md`.

**News feed entries are removed after 14 days.** See `docs/NEWS_FEEDS.md`.

**Tags from your mail service.** Enveliq now shows the tags (labels) your mailbox already has on each email, with a **Tags** button on every inbox email to put a tag on or take it off, and to make a new tag. Each change is also made in the real mailbox: Proton labels, Gmail labels, or keywords on other services (Outlook is not supported). The Filter list gets a **Tag: …** choice and Search finds emails by tag. Tags are read again after each automatic sync, so changes made in your mail app show up here. Only tag names are kept, with the email's encrypted summary, and nothing goes to the AI. An administrator or each person can switch it off. New guide: [TAGS.md](TAGS.md). Touches `backend/mail/tags.py`, `tag_routes.py`, `service.py` (a step at the end of a sync), `models.py` (a `tags` list on an email), `features.py`, `prototype/index.html`.

**News feeds (RSS and Atom).** A feed icon at the top of the screen shows a number badge when a feed you follow has new entries. Press it to read their text in a pop-up (full screen on a phone), add a feed by pasting its address, remove one, or check now. Every person follows their own feeds; nobody else can see them. Enveliq reads the feeds from the server about every half hour through the same careful outbound path as reminders, keeps only a short plain-text version of the newest entries (encrypted), and shows feed text only as plain text. An administrator or each person can switch it off. New guide: [NEWS_FEEDS.md](NEWS_FEEDS.md). Touches `backend/mail/rss.py`, `rss_routes.py`, `outbound.py` (a variant that also returns reply headers, so redirects can be followed and checked by hand), `features.py`, `prototype/index.html`.

**On a phone, the email closes as soon as you press Reviewed, Archive or Bin.** Before, the full screen email stayed open until you pressed Close or the action finished. Now it closes at once and you are back in the list. The five-second **Undo** bar still shows, and Undo brings the email back. See `docs/INBOX.md`.

**Forms fill the screen on a phone.** The new Add a parcel form and the new Task form open full screen on a phone, with the title and a **✕ Close** button fixed at the top and the buttons fixed at the bottom, so they can always be reached. This is now a standing rule for every new form (`CLAUDE.md`).

**Add a parcel by hand on the Shipping page.** A new **Add a parcel** form takes who the parcel is from, a tracking number (if you have one) and where it is up to. You move it along yourself from its card, and **Remove** takes it off. See `docs/INBOX.md`.

**Back button stays inside Enveliq.** Going to another section (Sent, Reviewed, Tasks and so on) now adds a step to the browser's history, so Back, or a phone's back gesture, returns to the section you were in before instead of leaving the site. Forward works, and Back closes Settings if it is open. See `docs/INBOX.md`.

**A Task button on every email.** Even when the AI found no task, you can press **Task**, write what you want to remember (for example "ring the plumber when I get home"), pick a day and add it. It shows as **Your task** and does not finish by itself when you deal with the email; only you finish it. A small box for it opens above the full screen email on a phone, and the Snooze box there is now also shown above it (it was hidden underneath). See `docs/INBOX.md` and `SECURITY.md`.

**Project settings file.** A small `.claude/settings.json` is added so that commit messages and pull request descriptions carry no tool or author lines. Nothing changes in the app.

**New rules for pull requests.** Every pull request description now starts with a clear list of everything in it, and it never names an author (no person, no AI) anywhere in its text. See `CLAUDE.md` and `.github/PULL_REQUEST_TEMPLATE.md`.

## v0.90 (2026-10-14)

**On a phone, every email opens full screen.** Whichever layout is chosen, on a phone tapping an email now opens it on its own, filling the screen, with one **✕ Close** button. To read the next email you close this one and tap the next in the list. The layout you picked is kept for bigger screens. See `docs/INBOX.md`.

**Phone fix: the "Save this as a draft?" question now shows.** On a phone the writing window fills the screen, and the question was hidden underneath it, so pressing Close seemed to do nothing. The question (and the "Send this?" check and the send warning, which had the same fault) now appears above the window as a sheet from the bottom of the screen with wide buttons. See `docs/DRAFTS.md`.

**Replies always carry the original email.** A reply used to go out with only your words, so the person who got it could not see what you were answering. Now every Reply and Reply all has the sender's whole email quoted under your message ("On <date>, <name> wrote:" and the text, each line starting with ">"). It is fetched from your mailbox when you press Send and is never stored. A new button, **Put the original in my message**, adds that quoted text into the message box right away so you can edit or trim it; when you do that Enveliq does not add it again. See `docs/REPLY_FORWARD.md`.

**"Keep me signed in" now survives a restart.** Sign-ins were kept only in the server's memory, so every time Enveliq restarted (an update, a redeploy in Arcane, a reboot of the host) everyone was asked to sign in again, even with **Keep me signed in on this device** ticked and 14 days set. A sign-in made with that tick (by password, passkey or single sign-on) is now also kept inside the encrypted vault, under a hash of its code and never the code itself, so after a restart Enveliq opens its vault from the key file and you are still signed in until the days you chose are up. Ordinary sign-ins (no tick) still end at a restart. Signing out, changing your password, an administrator disabling or resetting you, and restoring a backup all end remembered sign-ins as before. See `docs/INBOX.md` and `docs/VAULT_KEY.md`.

**Drafts.** When you close a New email, Reply, Reply all or Forward window that has writing in it, Enveliq now asks **Save this as a draft?** (**Save as draft**, **Discard** or **Keep writing**). Saved drafts are on a new **Drafts** page (left menu, under More, with a count). **Continue writing** opens the draft again, on the email it answers for a reply or forward, and sending it removes it. While you write, the email is also saved to Drafts by itself every few seconds and once more when the page is closed, so closing the browser does not lose it; Discard deletes that copy. Drafts are kept on the server for 14 days after you last saved them. Attachments are not kept in a draft. See `docs/DRAFTS.md`.

**Side by side view: no circles, two things in Coming up.** In the Reading pane on the right layout, the Today and Coming up boxes no longer have the round tick buttons, so the words get the room, and Coming up now shows the soonest two things instead of one. Everything else is unchanged; use the Tasks page to mark things done.

Code and tests for the phone full-screen email: `prototype/index.html`, `scripts/check_phone_reader.mjs` (new, in CI). Code and tests for the phone fix: `prototype/index.html`, `scripts/check_drafts.mjs`. Code and tests for the quoted original: `backend/mail/parse.py`, `backend/mail/service.py`, `backend/mail/routes.py`, `prototype/index.html`, `tests/test_reply_all_forward.py`, `scripts/check_reply_all_forward.mjs`. Code and tests for the sign-in change: `backend/security.py`, `backend/app.py`, `backend/backup_routes.py`, `tests/test_remember_me.py`. Code and tests for Drafts: `backend/mail/drafts.py` (new), `backend/mail/drafts_routes.py` (new), `backend/app.py`, `backend/export.py`, `prototype/index.html`, `tests/test_drafts.py` (new), `scripts/check_drafts.mjs` (new, in CI), `scripts/check_split_reading.mjs`. Docs: `docs/DRAFTS.md` (new), `docs/INBOX.md`, `SECURITY.md`.

**Forward, Reply all, and Cc and Bcc on replies.** Every email now has a **Forward** button. An email that has people on Cc also has **Reply all** (and only then): it puts the sender and the other people the email was sent to in To, and everyone who was on Cc in Cc. The reply window now has To, Cc and Bcc boxes that take several addresses: type one and press Enter or Tab (or a comma) and it becomes a chip with an ×, like New email. Cc and Bcc are small text links that add their box when clicked. Forward starts with an empty To, adds the original email under your note (fetched from your mailbox when you send, never stored) and offers the original's files as chips you can take off. The window says "This goes to N people" when it goes to several, and after sending, the message says "to alice@example.com and 3 others". Undo send works for all of them and puts the people back. Replying to one person with nothing changed works exactly as before. To make Reply all possible, Enveliq now keeps the Cc and other To addresses of each email it reads (addresses only, no names, inside the encrypted vault); emails read before this version have none, so they show no Reply all.

Code and tests: `backend/models.py`, `backend/mail/parse.py`, `backend/mail/service.py`, `backend/mail/routes.py`, `backend/mail/outbox.py`, `prototype/index.html`, `tests/test_reply_all_forward.py` (new), `scripts/check_reply_all_forward.mjs` (new, in CI). Docs: `docs/REPLY_FORWARD.md` (new), `SECURITY.md`.

**The email on the right now reaches the top bar.** In the **Reading pane on the right** layout on a computer, the open email now fills the whole right side, from just under the search bar down to the bottom of the window, with **Reviewed**, **Archive** and **Bin** pinned along its bottom edge. Everything that used to sit above the list moves into a column on the left: the page title, the four counts (now one slim row), **Today** and **Coming up** (now side by side) and the **Recent emails** bar, so the list starts as high as before and shows more emails. In this view **Today** shows its first two things and **Coming up** shows only the soonest one, in a box of the same height and the same shade; **Coming up · N more** is a link to the Tasks page, not a fold with an arrow (everywhere else it still folds open and closed). In Calm mode, this view drops the Calm mode bar on top and the icon in Start here, makes the cards shorter, and moves Also important today under Later on the right (use the Calm mode switch in the left menu to turn Calm mode off). That left column scrolls by itself and the page no longer scrolls. It works the same on every page that shows emails (Needs action, Archived and the rest). Phones, tablets narrower than 900 pixels and the other layouts (Classic list, Reading pane below, Open full screen, Focus deck) are unchanged.

Code and tests: `prototype/index.html` (a new `#readDock` beside the list, the `split-read` class and its styles), `scripts/check_split_reading.mjs` (new, in CI), `scripts/check_inbox_real_mail.mjs` (looks for the panel in its new place). Docs: `docs/INBOX.md`.

## v0.89 (2026-10-14)

**The top of the inbox stays in view.** On a computer, the search / Sync mail / name bar and the "Recent emails" bar now stay at the top while you scroll a long list, so the controls are always in reach. Only the emails scroll. The top bar stays see-through, so the picture behind it always shows, and anything that scrolls up to it fades out softly instead of being cut off with a hard line. Phones are unchanged.

**Even gaps on the main screen.** On a computer, the gap between Coming up and Recent emails (and between the delivery, subscription, trip and reply cards) was bigger than the rest. All the boxes on the main screen now sit the same small distance apart.

**Simpler menu wording.** In the menu that opens when you click your name, **Settings** is now for everyone and opens your own settings (your profile is the first tab inside). The administrator item is called **Administration** and shows only for administrators. The extra "Profile settings" and "Manage users" items are gone; the Settings button in the left bar is unchanged.

**Clearer Microsoft sign-in steps.** The steps in Administration, Microsoft sign-in (and `docs/MICROSOFT.md`) now start with getting a free Azure account, with the App registrations link first, and follow what Microsoft's current screens show: the account type wording, the Authentication Settings tab, and adding the email, offline_access and openid permissions. They also say plainly that "Office 365 Exchange Online" will not be in the list in a new directory and is not needed.

**Bigger email and attachment windows, and clickable links.** The window that shows an original email, a PDF, a picture or another attachment now grows with your browser window instead of staying 960 by 820 pixels, and stays inside it, so a tall screen shows much more. PDF pages are drawn larger and fit the window. Web addresses in the text of an email can now be clicked: each one asks "This goes to <website>. Open it in a new tab?" first, and only addresses Enveliq has already checked (and that did not look odd) can be clicked. Phones are unchanged. Code and tests: `prototype/index.html`, `backend/mail/render.py` (pages drawn up to 1500 pixels instead of 1000; every other limit unchanged), `tests/test_render_service.py`, `scripts/check_viewer_size.mjs` (new, in CI). Docs: `docs/INBOX.md`, `docs/SCAM_WARNING.md`, `SECURITY.md`.

**The Sent page now looks like the other pages.** It was missing the "Back to My inbox" button, and its title was smaller, in a different place and font. Sent now uses the same page header as Archived and the rest: the Back button, then the title, then a line saying what the page is ("Your last 14 days of sent mail"). The page also keeps room for its scroll bar, so nothing shifts sideways when the emails finish loading.

**A cogwheel for Settings.** The Settings icon in the left menu was a sun. It is now the same standard cogwheel used in the menu under your name.

**A maintenance guide.** New `docs/MAINTENANCE.md` for the maintainer: what Enveliq relies on (the database is one SQLite file, with no separate server), a weekly, per-release, monthly and twice-a-year routine, the GitHub security alerts to switch on, and why the preview build's tools should be pinned to exact versions. Documentation only; nothing in the app changes.

**Nothing in the wrong place when you refresh quickly.** Refreshing used to show parts of the page for a split second before they had moved into place: the search box and the "?" button in their old spots, the Recent emails box out of position, and some menu buttons. Now only the background shows until everything is ready, then the whole page fades in together in its right place (a calm "Getting your inbox ready…" line still appears if it takes more than a moment). Phones get the same. The server was already telling the browser not to keep old copies of the page, so this was never an old file.

Code and tests: `scripts/check_no_flash.mjs` (new, in CI), `scripts/check_no_sample_flash.mjs`, `web/static/auth.js` (Microsoft steps), `prototype/index.html` (menu wording, sticky bars and spacing, desktop only), `scripts/check_sticky_header.mjs` and `scripts/check_main_gaps.mjs` (new, in CI), `docs/INBOX.md`.

## v0.88 (2026-10-14)

**A calmer, tidier inbox, and a new look for the website.** Calm mode is cosier: on a computer the **Start here** card is shorter with smaller buttons, fills the width when it is alone, and shows **Also important today** as a slim strip along its bottom edge. Every page other than My inbox has a **Back to My inbox** button, and its title is the page's name. Needs action and the other email pages show the same **Recent emails / Inbox options** panel as My inbox. **Closed** on Waiting for reply starts folded. The Tasks page uses the full width. **Open full screen** now sits beside the left menu, with normal-sized Reviewed, Archive and Bin buttons.

**Easier on a phone.** Press and hold an email to pick several, with the buttons under the "Recent emails" title. Swipe the Undo bar or the AI queue bar sideways to clear it out of the way (the AI keeps working). Panels have an arrow that opens and closes them: Coming up, Calm's Later, and More in the narrow left panel. The account menu has a **Customise** button, and the user button no longer disappears when the left panel is narrow.

**Header pictures and a plain logo.** The inbox header has a night-sky (dark) or daytime (light) backdrop, and the logo is plain. In light mode the Shipping, Subscriptions, Trips and Waiting for reply cards and the New email button now use light colours.

**The website has a light and dark switch.** A sun/moon button in the top bar switches the website between light and dark and remembers the choice on the visitor's own device (without it, the site follows the device setting). The dark colours match the app. Every picture on the website, in the guides and in the README was retaken in the new design, in both themes. The website now runs two small scripts from its own address (the guide search and this switch), and its security policy and wording say so. Nothing is sent anywhere.

Code and tests: `prototype/index.html` (all pages), `website/` (`src/style.css`, `src/theme.js`, `build.mjs`, `check.mjs`), `scripts/check_backdrop.mjs`, `check_phone_select.mjs`, `check_rail_and_folds.mjs`, `check_calm_layout.mjs`, `check_back_to_inbox.mjs` (all in CI), `scripts/retake_pictures.mjs` and `scripts/place_pictures.py` for retaking the pictures. Docs: `docs/INBOX.md`, `website/README.md`.

* Header backdrop, plain logo, Calm layout, navigation, phone selection and swipe, light mode fixes, and a new website and pictures by @jlnau in https://github.com/jlnau/enveliq/pull/80

## v0.87 (2026-10-13)

**A redesigned inbox, with less visual noise.** Calm mode is enabled by default for a new browser and can be turned off at any time. The desktop inbox has a more compact summary and task layout, while phones use smaller summaries and collapsible Today, Coming up, and other task sections. The left sidebar, account menu, and light theme have been refreshed. The account menu offers Dark, Light, and System themes. Inbox Options starts collapsed and expands to show the mailbox filters, sorting, and other controls. Transparent PNG profile pictures now keep their transparency on upload; pictures previously saved with a white JPEG background can be replaced by uploading the original PNG again.

**Attachment summaries remain visible with ad blockers.** The attachment list no longer uses naming that ad blockers mistake for advertising, so file rows and summaries remain visible when blocking is enabled.

<!-- Release notes generated using configuration in .github/release.yml at main -->

## What's Changed
### Other changes
* Keep attachment summaries visible with ad blockers enabled by @jlnau in https://github.com/jlnau/enveliq/pull/75
* Redesign the inbox with Calm mode, compact desktop and mobile layouts, improved navigation and themes, and transparent profile pictures by @jlnau in https://github.com/jlnau/enveliq/pull/76

**Full Changelog**: https://github.com/jlnau/enveliq/compare/v0.86...v0.87

## v0.86 (2026-10-12)

<!-- Release notes generated using configuration in .github/release.yml at main -->

## What's Changed
### Other changes
* Fix the broken QR code in authenticator-app setup by @jlnau in https://github.com/jlnau/enveliq/pull/64
* Never show a count of files with nothing beside it by @jlnau in https://github.com/jlnau/enveliq/pull/65
* Install file: publish port 8765:8765 by @jlnau in https://github.com/jlnau/enveliq/pull/66
* Docker Compose guide: show the install file first by @jlnau in https://github.com/jlnau/enveliq/pull/67
* Add a settings reference: every environment variable by @jlnau in https://github.com/jlnau/enveliq/pull/68
* Microsoft guide: explain the directory Microsoft now needs by @jlnau in https://github.com/jlnau/enveliq/pull/69
* Search the guides on the website by @jlnau in https://github.com/jlnau/enveliq/pull/70
* Calm mode: no numbers, softer colours, one task at a time by @jlnau in https://github.com/jlnau/enveliq/pull/71
* Show no sample emails on a blank install by @jlnau in https://github.com/jlnau/enveliq/pull/72
* Rename Settings Reminders to Notifications and make it two clear steps by @jlnau in https://github.com/jlnau/enveliq/pull/73


**Full Changelog**: https://github.com/jlnau/enveliq/compare/v0.85...v0.86

## v0.85 (2026-10-12)

<!-- Release notes generated using configuration in .github/release.yml at main -->

## What's Changed
### Other changes
* One AI queue: new mail waits for its summary and files by @jlnau in https://github.com/jlnau/enveliq/pull/62


**Full Changelog**: https://github.com/jlnau/enveliq/compare/v0.84...v0.85

## v0.84 (2026-10-12)

<!-- Release notes generated using configuration in .github/release.yml at main -->

## What's Changed
### Other changes
* Summarise attached files and list them under each email by @jlnau in https://github.com/jlnau/enveliq/pull/58


**Full Changelog**: https://github.com/jlnau/enveliq/compare/v0.83...v0.84

## v0.83 (2026-10-12)

<!-- Release notes generated using configuration in .github/release.yml at main -->

## What's Changed
### Other changes
* The paperclip shows on real mail by @jlnau in https://github.com/jlnau/enveliq/pull/53
* An email waiting out Undo stays in the list, greyed and pulsing by @jlnau in https://github.com/jlnau/enveliq/pull/52
* A guide for the inbox day to day, and the documentation gaps filled by @jlnau in https://github.com/jlnau/enveliq/pull/54
* Retake the website and guide pictures by @jlnau in https://github.com/jlnau/enveliq/pull/55
* Fix Prepare Release to collect merged PR notes automatically by @jlnau in https://github.com/jlnau/enveliq/pull/56


**Full Changelog**: https://github.com/jlnau/enveliq/compare/v0.82...v0.83

## v0.82 (2026-10-12)

**A notice when a new version is out.** Administrators now see a small card in the left panel when a newer Enveliq release has been published, with a link to the release notes on GitHub. Enveliq's server checks about once a day (never the browser); nothing about you is sent. It is on by default and an administrator can switch it off under Administration, Updates. This replaces the earlier statement that Enveliq makes no update check, so the privacy notes, the privacy pop-up and the README now mention it.
- `backend/update_check.py` (new): asks `api.github.com` for the latest published release in the background (8 second timeout, 200 KB limit, once a day, an hour's wait after a failure), accepts only a plain version number and a link under `https://github.com/jlnau/enveliq/releases/`, ignores drafts and pre-releases, compares versions as numbers and keeps the result in memory.
- `backend/app.py`, `backend/models.py`: `/api/v1/system` includes `update` for administrators only; `GET`/`PUT /api/v1/admin/update-notice` read and switch it (admin only, stored in the vault, audited as `update_notice_changed`). When it is off, no request is made.
- `prototype/index.html`, `web/static/auth.js`: the card above the line over Agent (a small icon when the panel is collapsed), which re-checks that the link is Enveliq's own releases page, and Administration, Updates with the switch.
- Docs: `docs/UPDATES.md` (new), `docs/PRIVACY.md`, `README.md`, the privacy pop-up, the website home page and `SECURITY.md` now describe the check.
- Tests: `tests/test_update_notice.py` (version comparison, what is accepted and refused, administrators only, off means no request, a failed check is quiet, audit), `tests/conftest.py` (no test ever contacts GitHub), `scripts/check_update_notice.mjs` (the card, its link, bad links ignored, the collapsed icon, the switch).

**Undo bars stack.** Each Reviewed, Archive or Bin now gets its own Undo bar, so you can still take back an earlier one after doing another. Several emails done together are still one bar.

- `prototype/index.html`: the single Undo bar is now a stack (`#undoBar` holds one `.undobar` per waiting action, newest at the bottom, drawn by `drawUndos()`). Each bar has its own Undo button and its own countdown line, which carries on from where it was when another bar is added. At most three show: a fourth action sends the oldest one straight away.
- Tests: `scripts/check_stacked_undo.mjs` (new; three in a row, newest at the bottom, no overlap on desktop or phone, Undo on the middle one, several emails as one bar, the three-bar limit, bars leaving one by one). `check_demo.mjs` and `check_inbox_real_mail.mjs` now look at the newest bar.
- Docs: `docs/UNDO.md`.

**The version number moves to the bottom of the left panel.** The version is now a small grey line under Terms, Privacy and Security instead of under the logo and tagline at the top. It is hidden when the panel is collapsed, like those links.

- `prototype/index.html`: `#brandVer` moves from the logo block into the bottom block of the left panel (`.side-foot`), styled as `.ver`. It is still filled from the signed-in `/api/v1/system` answer, and stays empty and hidden in the demo.
- Tests: `scripts/check_version_footer.mjs` (new; the version shows, sits under the links and the person's name, is gone from the top, hidden when collapsed, nothing left in the demo). `check_no_sample_flash.mjs` still passes.


**Row buttons show when you point at an email.** On a computer, the Reviewed, Archive and Bin buttons on an email in the list now appear only while the mouse is over that email, in the place of its date, and go away again when the mouse leaves. The list is calmer to look at. Tabbing to a button shows them too. Phones are unchanged (they swipe), and an opened email keeps its own buttons.

- `prototype/index.html`: for a mouse (`hover:hover`) on a screen wider than a phone, a closed row's `.qpair` is hidden until the row is hovered or has focus inside it. It is smaller (32 by 30) and fades in over the date, which fades out. The buttons stay in the page and keep working for the keyboard. The reading-pane layout and phones are left as they were.
- Tests: `scripts/check_hover_actions.mjs` (new; hidden by default, shown only for the row under the mouse, in the place of the date, inside the row, a button works, keyboard focus shows them, an opened email keeps its buttons, phones unchanged). `check_demo.mjs` and `check_inbox_real_mail.mjs` still pass.
- Docs: `docs/UNDO.md`.

**Undo bars stack.** Each Reviewed, Archive or Bin now gets its own Undo bar, so you can still take back an earlier one after doing another. Several emails done together are still one bar.

- `prototype/index.html`: the single Undo bar is now a stack (`#undoBar` holds one `.undobar` per waiting action, newest at the bottom, drawn by `drawUndos()`). Each bar has its own Undo button and its own countdown line, which carries on from where it was when another bar is added. At most three show: a fourth action sends the oldest one straight away.
- Tests: `scripts/check_stacked_undo.mjs` (new; three in a row, newest at the bottom, no overlap on desktop or phone, Undo on the middle one, several emails as one bar, the three-bar limit, bars leaving one by one). `check_demo.mjs` and `check_inbox_real_mail.mjs` now look at the newest bar.
- Docs: `docs/UNDO.md`.


**A paperclip on emails with attachments.** An email that has an attachment now shows a small paperclip under its date and time in the list, on a phone and on a computer.

- `prototype/index.html`: the row's date and time block gets a small paperclip (`.clip`) when the email has attachments. It says "Has an attachment", or "Has 2 attachments", to a screen reader and as a tooltip. Emails without attachments look as before.
- Tests: `scripts/check_attachment_clip.mjs` (new; paperclip present and absent, its label, under the date and lined up on the right, no sideways scrolling, on desktop and phone).

**Undo bars stack.** Each Reviewed, Archive or Bin now gets its own Undo bar, so you can still take back an earlier one after doing another. Several emails done together are still one bar.

- `prototype/index.html`: the single Undo bar is now a stack (`#undoBar` holds one `.undobar` per waiting action, newest at the bottom, drawn by `drawUndos()`). Each bar has its own Undo button and its own countdown line, which carries on from where it was when another bar is added. At most three show: a fourth action sends the oldest one straight away.
- Tests: `scripts/check_stacked_undo.mjs` (new; three in a row, newest at the bottom, no overlap on desktop or phone, Undo on the middle one, several emails as one bar, the three-bar limit, bars leaving one by one). `check_demo.mjs` and `check_inbox_real_mail.mjs` now look at the newest bar.
- Docs: `docs/UNDO.md`.

**Notifications show the Enveliq mark.** On Android, the small icon on an Enveliq notification (in the status bar and the notification's top line) is now Enveliq's own mark instead of the browser's logo. The large browser icon on the left of a notification is the browser's own and only changes if Enveliq is installed as an app.

- `web/static/sw.js`: notifications now name a `badge`, `/brand/enveliq-badge-96.png`.
- `brand/web/enveliq-badge-96.png` (new): the Enveliq mark in one colour on a clear background, 96 by 96, as Android expects for a status-bar icon.
- Tests: `tests/test_push.py` (the service worker names the small icon, and it is a 96 by 96 PNG with a clear background).
- Docs: `docs/NOTIFICATIONS.md`.

**Undo bars stack.** Each Reviewed, Archive or Bin now gets its own Undo bar, so you can still take back an earlier one after doing another. Several emails done together are still one bar.

- `prototype/index.html`: the single Undo bar is now a stack (`#undoBar` holds one `.undobar` per waiting action, newest at the bottom, drawn by `drawUndos()`). Each bar has its own Undo button and its own countdown line, which carries on from where it was when another bar is added. At most three show: a fourth action sends the oldest one straight away.
- Tests: `scripts/check_stacked_undo.mjs` (new; three in a row, newest at the bottom, no overlap on desktop or phone, Undo on the middle one, several emails as one bar, the three-bar limit, bars leaving one by one). `check_demo.mjs` and `check_inbox_real_mail.mjs` now look at the newest bar.
- Docs: `docs/UNDO.md`.

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
