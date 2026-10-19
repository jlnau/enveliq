# Enveliq for Android

A real Android app (not a web page in a frame), written in Kotlin with Jetpack Compose. It lives in the `android/` folder. It is not on the Play Store: you install the APK file yourself. The newest one is always on the [download page](https://github.com/jlnau/enveliq/releases/latest) (this repository is public, so no sign-in is needed).

## Install it

**From a release (the normal way).** When you publish a GitHub Release, the **Build Android app** workflow builds the app and attaches `Enveliq-<version>.apk` (and its checksum, `.sha256`) to that release. Open the release on your phone, download the APK, and open it. Android asks to allow installing apps from your browser or Files app; allow it for that one app, then press **Install**. A new version installs over the old one.

**From a test build.** Every time the test branch `preview/vX.YY` changes the `android/` folder, the same workflow runs. Open **Actions**, **Build Android app**, the newest green run, and download **Enveliq-android-apk** under Artifacts (a zip with the APK inside; kept for 90 days). **Run workflow** starts a build by hand.

## Signing: nothing to set up

Android only installs an update over an app if both carry the same signature. GitHub keeps the signing key for you (in its cache), and a small weekly job on the main branch keeps it from expiring and makes it the same for test builds and releases. You do nothing.

If the key is ever lost (for example before the first build from `main`, or after GitHub clears its cache), Android says the app conflicts with the one already installed. Uninstall Enveliq once and install the new version. The app keeps almost nothing on the phone (your sign-in), so you lose nothing but one sign-in.

Optional, only if you later share the app with other people: add the four repository secrets `ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS` and `ANDROID_KEY_PASSWORD` (a key you make with `keytool` and keep safe). Builds are then signed with that key instead, and the workflow summary says "your own release key". Switching keys needs one uninstall and reinstall.

The app's version is the release tag (for example `v0.96` gives version `0.96`); test builds are named `0.96-preview`. Each build has a higher build number than the one before, so it installs as an update.

## What you can do

- **Sign in** opens the app: type your Enveliq's address, your username and password, and a code if you use two-factor. The boxes are marked as username, password and verification code, so a password manager such as Bitwarden can offer to fill them (turn on Bitwarden's autofill service in Android's settings). It then lists your inbox (the same email as the website, newest first), opens an email's summary and original text, and marks emails Reviewed, Archived or Binned for real. The address must start with `https://`, and your Enveliq must be reachable from the phone. The box starts with `https://` already filled in (pasting a whole address does not double it), and **Show** beside the password lets you check what you typed. Errors are in plain words, including a clear message when the address answers with a web page instead of Enveliq (usually a security layer such as Cloudflare Access: allow the `/api` path for the app). You can type it with or without `/api` on the end (`https://enveliq.example.com` or `https://enveliq.example.com/api`). The app only ever asks for addresses that start with `/api/v1/`, so if a security layer such as Cloudflare Access protects your site, you can allow just the `/api` path for the app (a Bypass rule for `/api`) and keep everything else, including the website itself, behind it. Enveliq's own sign-in (and two-factor, if you use it) still protects everything under `/api`.
- **Tell me when new email arrives** (Settings) shows a quiet note when a new email's AI summary is done. The lock screen only says "New email" (or "3 new emails"); sender and subject show once the phone is unlocked. Android asks permission the first time. **Quiet hours** keep the note but without sound or buzz. Alerts work while the app is closed, and start again after the phone restarts or the app is updated. See "How new-email alerts work" below.
- **Send a test notification to this phone** shows what an alert looks like. On the lock screen it only says "New email"; the words show once the phone is unlocked. Android asks permission the first time.
- **Hide Enveliq in recent apps** hides the app's picture in the recent-apps view and stops screenshots.

## Settings

Settings is a short list of topics: **Notifications**, **Swipe on an email**, **Appearance**, **Security**, **Open the next email**, **Blocked senders**, **Account** and **About**. Tap a topic to open its own page, with a Back button fixed at the top. On a page, switches turn things on and off with one tap on the whole row; a choice (for example what a swipe does, or how alerts reach the phone) opens one more page with a tick-list. Nothing needs long scrolling: longer explanations sit under the setting they belong to.

## Look, alerts and comfort

- **Appearance** (Settings): follow the phone's light or dark setting, or pick Light or Dark yourself; and a text size (Normal, Large, Extra large) that is added to Android's own text size. Rotating the phone or changing these no longer restarts the app, so you keep your place.
- **What to alert me about** (Settings, Notifications): all new email, only email that needs action, or only email from people on your important list. Email you are not alerted about still waits in your inbox. This is a setting, and "all new email" is the default.
- **Hide the watching note:** a button that opens Android's own switch for the small "watching" note (alerts keep working).
- **Alerts clear at once:** when an email is reviewed, archived or moved somewhere else, the server tells the phone and its alert is taken down straight away (the phone does not need to wait until the app next looks).
- **Mark unread:** open an email in the Reviewed view and tap **Mark unread**. The mailbox gets its unread mark back and the email returns to the inbox. Only emails you marked Reviewed can be marked unread (an archived email has moved to another folder). A Reviewed card keeps its pointer to the mailbox for this; an Archived card still drops it.
- **Check connection** on the sign-in screen says in plain words whether the address answers.
- **A welcome** after your first sign-in explains summaries, alerts and the lock in three short cards, with a button that goes straight to those settings. It shows once.
- **Screen reader:** every email row offers Mark reviewed, Archive and Move to Bin in TalkBack's actions menu (swiping is hard with a screen reader).

## Writing: who it comes from

When you have more than one address (a mailbox's own address and its aliases, from the mailbox's "send as" list), the writing screen shows **From** at the top. Tap it to pick another address. A reply or forward can only use the addresses of the mailbox the email arrived in; a new email can use any of your mailboxes. Your mailbox's own address is the default, and when it is picked the app sends nothing extra, so the mail service behaves exactly as before. The choice is kept in drafts.

## Beyond email
- **Tasks tab:** the website's task list. Done, Move, Not today, Remove, and Put back for finished ones.
- **More tab:** Notes and alerts, Messages, Shipping, Trips and calendar, News feeds. Shipping, trips and news are read-only here (set them up on the website); Messages can be read and answered; the bell can be dismissed.
- **Share to Enveliq:** use Android's Share menu on text in any app and choose Enveliq. A new email opens with the text in the body (and the shared title as the subject).
- **Wide screens:** from 720 dp wide (a tablet, or a phone on its side) the inbox and the open email show side by side.
- **Home-screen widget:** add "Enveliq" from the phone's widget list for a square that says how many emails are waiting. It shows the number only and is updated whenever the inbox loads; signing out clears it.

## Passkeys and single sign-on
On the sign-in screen, **Sign in with a passkey or single sign-on** opens your server's `/app-signin` page in the phone's browser. Sign in there the usual way; press **Open the Enveliq app** and the app finishes signing in (one-time code, two minutes, once, tied to a secret only the app holds). "Keep me signed in on this phone" is read when you press the button. After single sign-on the browser shows the inbox: go back to the app and press the button again, which now finishes straight away. The app registers the link `enveliq://signin` for this.

## Your devices and updates
Settings, Security, **Your devices** lists the places you are signed in and lets you sign another one out. Names come from the app ("Enveliq app on <phone model>") or, for a browser, a short guess such as "Chrome on Windows". Sign-ins you chose to keep across a restart are listed too. The list is yours alone. About, **Check for a new version** asks your own server (which checks GitHub once a day) for the newest release and, if it is newer than the app, offers to open its download page; the app never contacts GitHub itself. Installing is Android's own step. If an administrator switched the update notice off, the app says it has no answer.

## Tags, files, links and views

- **Tags:** on an opened email, **Choose tags** opens a full screen list with a search box at the top and tick boxes. Tick or untick several, then **Save tags** applies them together. The email's current tags start ticked, so nothing is lost. **Make the tag "..."** appears when what you typed does not exist yet (only if your mail service lets tags be made). Shown only if your mail service keeps tags.
- **Filter by tag:** in the inbox, the **Tags** control opens a full screen list of the tags on the emails you have, with how many emails each one has. Tap a tag to show only those emails. **Clear filter** (in that screen) or **Clear ✕** (next to the control) removes the filter.
- **Files with this email:** each file's size and the AI's note (labelled). **Save to my phone** asks where to save it. The file is fetched at that moment and not kept by the app.
- **Show the original email:** opens the email full screen as its sender made it: layout, colours, tables, pictures that came inside the email, and links. If an email has no formatted version, you see its plain text instead, and **Plain text** can always be chosen. Pictures that live on the internet are held back (they can tell the sender you opened the email) until you tap **Show pictures**. It uses the same safe copy the website shows: the server rebuilds the email from allowed parts only (no scripts, forms or frames), and the app shows it with JavaScript off, no file or storage access and no network until you allow pictures. Pinch to zoom.
- **Links:** every link, in the formatted email or the plain text, asks first and names the site it goes to. Unusual links (plain http, look-alike characters, bare numbers) get an extra warning.
- **Inbox, Reviewed, Archived:** the chips at the top switch views. Reviewed and Archived show what the server still keeps (a few days).
- **More than one mailbox:** a chip for each mailbox appears and filters the list.

## Added in version 0.97

- **Junk and Block sender.** On an opened email, **Send to Junk** moves it to your mailbox's own Junk or Spam folder (Undo works for a few seconds). **Block sender** does that and also makes a rule, so new email from that address goes to Junk from then on. The rule is only made after the Undo time has passed. People on your important list are never blocked. **Settings, Blocked senders** lists the blocked addresses, each with **Unblock**. It is the same rule the website uses (see [Junk mail](JUNK_MAIL.md) and [Mail rules](MAIL_RULES.md)).
- **Take care with this one.** When Enveliq's check finds something odd about an email (for example a sender name that does not match the address), a boxed note above the summary says why in plain words.
- **Unsubscribe from this sender.** Shown when the email carries an unsubscribe link or address. A web link asks first and names the site it goes to; a mail address opens a new email in your mail app. Enveliq never opens the link by itself.
- **Find any email** (More tab) searches all your mailboxes, old email too, and can include Junk. Results list sender, subject, date and mailbox; tap one to read its text. The email is fetched when you open it and is not kept. It uses the website's [Find any email](FIND_MAIL.md); an administrator can switch it off.
- **Attach files to a new email.** **Attach files** on a new email opens Android's file picker (up to 10 files, 10 MB together). The files are held in memory while you write and sent with the email; they are not saved on the phone. Replies and forwards work as on the website (a forward carries the original's files).
- **Signature.** The signature you saved on the website is put in the box when a new email starts, where you can change or remove it.
- **Pick from phone contacts** on a new email opens Android's contact picker. Only the one address you choose is handed over, so Enveliq does not need permission to read your contacts.
- **Links that start an email.** Tapping an email address or `mailto:` link in another app can offer Enveliq, and a new email opens with the address (and subject or text, if the link had them) filled in. Nothing is sent until you press Send.
- **Open the next email** (Settings): after you archive or mark reviewed the email you are reading, the next one in the list opens.
- **Get the Android app** (Settings, About) opens the download page, for this or another phone. The website's front page and Settings link to this guide, which has the download button.

- **Files and their summaries.** An email's files are listed under the AI summary with the AI's note on each (labelled), or the reason a file was not read. **View** (or **Preview** for a picture) opens the same viewer as the website: PDF pages with zoom, pictures, tables and plain text, made by your server in memory. **Save to my phone** keeps a copy where you choose. Nothing is kept by Enveliq or the app.
- **A paperclip** beside the time on any email in the list that has files.
- **A cleaner main screen.** The top row is a menu button, the Enveliq logo, search, and your picture (or initials). Tap the picture for **Your account** (opens the website's account page) and **Settings**. The menu button opens Inbox, Tasks, Drafts, More and Settings, which no longer take space at the bottom. A thin row under it says where you are, with a filter button (Inbox, Reviewed, Archived) and a second button for needs action, mailbox and tags. Pull down to refresh. An open email fills the screen, and its bottom bar is symbols: a tick (Reviewed), an archive box, a bin and a clock (Remind me later).
- **Send later.** **Later** beside Send on a new email, reply or forward picks a time; **More, Waiting to send** lists and takes back what is waiting. Files cannot wait. See [Send later](SEND_LATER.md).
- **Attach files to replies and forwards**, as on the website. A forward keeps the files of the original unless you untick them.
- **Alerts for messages, notes and alerts, tasks due today and parcels to confirm.** **Settings, Notifications** has a switch for each, off until you turn it on. Direct mode only (not Google's push). The server's alert stream tells the app only *which kind* has something new, never any words, so the note says just "New message", "A task is due" and so on. They follow your quiet hours.
- **Install updates from inside the app.** **Settings, About, Install it**: the app downloads the new version through your own server (which checks it against its published checksum), then Android asks you to confirm. Android asks once to allow Enveliq to install apps. See [Updates](UPDATES.md).

## Not in the app

- **A calendar of events.** Trips and bookings are listed under More, Trips and calendar.
- **Settings, Administration and mailbox setup** stay on the website. Shipping, trips and news are read-only in the app (set them up on the website).

## How new-email alerts work

- The server has one small stream for the app, `GET /api/v1/me/new-mail-events`. It says which emails have just become ready (their AI summary is finished) and, about every 30 seconds, which other kinds (messages, notes, tasks, parcels) have grown. It carries ids and kind names, never any text, and the server only ever lists the signed-in person's own email.
- The app holds one connection to that stream. The server sends one line a minute so the connection is not dropped; in between, the app does nothing. There is no polling.
- When the server says something is ready, the app fetches the inbox once, and shows an alert for each email it has not already told you about. It remembers only the ids it has announced (up to 400), so an email is never announced twice. The first time you turn alerts on, the email already in your inbox is not announced.
- No network, no connection: while the phone has no signal the app does not try, and it reconnects the moment a network returns. After a failed try it waits 15 seconds, then longer each time, up to 5 minutes.
- If the server signs the app out, the app stops and tells you once so you can sign in again.
- Android needs a small permanent note while an app keeps a connection open ("Enveliq is watching for new email"). It is silent and tucked away. Turning the setting off removes it.
- If the phone has been still for a long time, Android may pause background apps ("Doze") and alerts can come late. **Keep alerts on time** in Settings asks Android to let Enveliq run without that limit.

## Google's push service (optional)

By default the app keeps its own connection to your server (above). **Settings, Tell me when new email arrives** also offers a second choice, **Google's push service**: alerts arrive instantly, even when the phone has been still for hours, and the "watching" note disappears. The cost: Google is told that a notification was sent to your phone, and when. The message itself holds only the word "mail" (or "test") and a count. The sender, subject and summary never go through Google: the phone wakes up and asks your Enveliq for the details itself, then shows them only once the phone is unlocked.

There is nothing to set up on your server and nothing in Administration. The app sends the wake-up request through the shared Enveliq push relay (see [Push relay](PUSH_RELAY.md)), which holds the one Firebase key for the whole app. The choice only shows when this build of the app includes Google push and your server's image was built with the relay address, which the official Enveliq images and app are. A fork or a build from source has neither, so it offers no Google push until its owner sets up their own relay.

Until you choose it the app never contacts Google: Firebase's automatic start-up and analytics are switched off. Switching back to the direct connection, turning alerts off, or signing out deletes the phone's Google address and removes the phone from your Enveliq.

**For whoever publishes the app, once:** deploy the relay ([Push relay](PUSH_RELAY.md)) and add the Firebase project's `google-services.json` to the GitHub repository as the encrypted secret `GOOGLE_SERVICES_JSON` (the **Build Android app** workflow writes it into the build).

Which emails alert you, quiet hours and the "important people only" filter are the same settings as for browser alerts (Settings, Alerts), because the app is one more place those alerts go. Switching on alerts in the app switches on **New email alerts** there. Only new-email alerts go to the app; task reminders use your other channels.

## New-email alerts: what you can do from the alert

- **Tap the alert** and Enveliq opens on that email.
- **Reviewed** and **Archive** buttons on the alert mark the email at your mailbox without opening the app (they show once the phone is unlocked, never on the lock screen).
- **The alert goes away by itself** when the email is no longer waiting (for example you reviewed it on the website or another phone). It is taken down when the app next checks, or when you open the app.
- Several new emails at once make one alert; tap it to open the inbox.

## Using the app

- **Swipe an email** right or left to Archive, Bin or mark it Reviewed (Settings, Swipe on an email; to begin with right is Archive and left is Bin, or choose Nothing to switch a side off). Every swipe can be undone for a few seconds.
- **Select several:** press and hold an email, tap more to add them, then Reviewed, Archive or Bin for all of them. **Select all** ticks everything in the list.
- **Search** your inbox (the Search button at the top): it looks at the sender, subject and summary of the emails already in your inbox. To search all your mail, use More, Find any email.
- **Remind me later** (on an opened email): put it away until in 3 hours, tomorrow morning or next Monday morning. It comes back in your inbox then, and the website shows it as snoozed too. Undo brings it back at once.
- **Reply, Reply all and Forward** are at the top of an opened email. The email you are answering is added underneath, as on the website.
- **New email:** the round pencil button on the inbox. In To, Cc and Bcc, suggestions from your address list appear as you type (if the address list is switched on in Enveliq). If you have more than one mailbox, you pick which one to send from.
- **Undo send:** if you have an "undo send" time in Settings on the website, a bar at the bottom says "Sending in … seconds" with **Undo**.
- **Drafts:** closing a half-written email offers to keep it. The **Drafts** tab lists them (kept for 14 days, the same drafts the website shows); tap one to carry on, or Delete it.
- The writing screen opens full screen, with Close at the top and **Send** and **Save draft** fixed at the bottom.
- **Pull down** on the inbox to refresh. The list keeps its place when you switch tabs.
- **Ask for my fingerprint, face or PIN** (Settings, Security): Enveliq asks for it when you open it, and again after it has been out of sight for a minute. It needs a screen lock to be set up in Android first; the app never locks you out of a phone that has none. This is a convenience on top of your sign-in, not a replacement for it.

## Android app to-do list

Done in version 0.95: https:// filled in, Show password, plainer errors, tap an alert to open the email, Reviewed/Archive buttons on the alert, alerts that clear themselves, pull to refresh, fingerprint/face/PIN lock.

Still to do. Everything the website does that makes sense on a phone, roughly in this order:

**Everyday email**
- **Email tags**: see, add and remove tags, and filter the inbox by tag.
- The rest of the website's actions: Task, mark unread (needs a way to see reviewed email first, so it comes with folders and views), and move.
- Attachments: their summaries, a View button (page pictures held in memory only) and Save or Share.
- Links in an email open only after a tap and a plain "this goes to …" check.
- Folders and views as on the website (Today, Needs attention, and your folders), and more than one mailbox.

**Wishes added after the first weeks of testing**
- **Attach files when writing** a new email, reply or forward (a photo or any file from the phone).
- **Unsubscribe button** on an email, using the website's existing unsubscribe.
- **Scam and sender warnings** in the original-email view, as on the website (look-alike senders, suspicious links).
- **Junk and block:** mark an email as junk and block a sender, in the Android app **and in Enveliq itself** (the website and server, not only the app).
- **Search all mail**, not just the inbox, as the website's search everywhere does.
- **Alerts only for the emails that matter:** a setting to alert only for "needs action" or important people.
- **Open the next email after archiving:** a setting users can switch on, for working through a pile without going back to the list.
- **Send later:** pick a time for an email to go (first check what the server supports).
- **Pick someone from the phone's contacts**, and let Enveliq handle "email this person" links from other apps.
- **A signature** added to emails you send.

**Beyond email** (each as its own screen, as on the website)
- Tasks in full, the bell (notes and messages), shipping, calendar, news feeds and chat messages.

**Alerts**
- One switch per kind of alert, and the optional "Hide the watching note" button.
- Alerts that clear the moment an email is reviewed elsewhere (today they clear when the app next checks; instant clearing needs the server to announce it).

**Look and comfort**
- Light and dark follow the phone's setting (today the app is dark).
- Bigger text and screen reader support checked screen by screen.
- A tablet and landscape layout.
- A home-screen widget showing how many emails are waiting.
- Share to Enveliq: send a link or a note from another app into a task.

**Account and safety**
- **Your devices** list on the website, so a lost phone can be signed out (needs the per-device token work on the server).
- Passkeys and single sign-on.
- "Check for an update" in About, and a "Check connection" button on the sign-in screen.
- A calm first-run welcome that explains notifications and the lock.

Anything here that adds a screen opens forms full screen with Close at the top and the buttons at the bottom, as the rest of Enveliq does on a phone.

## Privacy

- No email is written to the phone. It is held in memory while on the screen. The only thing kept is your sign-in (below), and the server address you typed.
- Android backups are switched off, so nothing is copied to Google or a new phone.
- The app only talks to the address you typed, over HTTPS, and only trusts the server's real certificate.
- **Staying signed in.** On the sign-in screen, **Keep me signed in on this phone** (on to begin with) keeps your sign-in between runs, so the app opens straight to your inbox. What is kept is the server's sign-in cookie, encrypted with a key in the Android Keystore that never leaves the phone. Your password is never kept. How long it lasts is the same "keep me signed in" time your administrator set for the website. **Sign out** in Settings ends the session at the server and removes what was kept; if the server stops accepting it (you signed out elsewhere, or it ran out) the app asks you to sign in again. Turn the switch off to be asked every time.
- **Alerts** keep your sign-in on the phone (they need it to listen while the app is closed). The only extra things stored are the on/off switches, the quiet hours and the ids of emails already announced; no sender, subject or summary is written to the phone. Alerts go straight between your phone and your own Enveliq: no Google push service and no other company is involved.
- The app adds no analytics, no ads and no crash reporting.

## How it is built

`android/` is a Gradle project (`app/` holds the code). `Api.kt` talks to the same JSON routes the website uses; `Home.kt` and `Screens.kt` are the screens; `SessionVault.kt` keeps the sign-in encrypted; `Notifier.kt` makes the notifications; `Push.kt` is Google's push service (only when chosen); `MailWatcher.kt` is the background service that keeps the one connection and the alert settings; `Data.kt` holds the small data types. The **Build Android app** workflow compiles it with the Android SDK on a GitHub runner, signs it, and attaches the APK. Version 1 for everyone needs the server groundwork in the plan first (per-device tokens, a list of devices, the public API list in Cloudflare).
