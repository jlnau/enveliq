# Enveliq for Android

A real Android app (not a web page in a frame), written in Kotlin with Jetpack Compose. It lives in the `android/` folder. It is not on the Play Store: you install the APK file yourself.

## Install it

**From a release (the normal way).** When you publish a GitHub Release, the **Build Android app** workflow builds the app and attaches `Enveliq-<version>.apk` (and its checksum, `.sha256`) to that release. Open the release on your phone, download the APK, and open it. Android asks to allow installing apps from your browser or Files app; allow it for that one app, then press **Install**. A new version installs over the old one.

**From a test build.** Every time the test branch `preview/vX.YY` changes the `android/` folder, the same workflow runs. Open **Actions**, **Build Android app**, the newest green run, and download **Enveliq-android-apk** under Artifacts (a zip with the APK inside; kept for 90 days). **Run workflow** starts a build by hand.

## Signing: nothing to set up

Android only installs an update over an app if both carry the same signature. GitHub keeps the signing key for you (in its cache), and a small weekly job on the main branch keeps it from expiring and makes it the same for test builds and releases. You do nothing.

If the key is ever lost (for example before the first build from `main`, or after GitHub clears its cache), Android says the app conflicts with the one already installed. Uninstall Enveliq once and install the new version. The app keeps almost nothing on the phone (your sign-in), so you lose nothing but one sign-in.

Optional, only if you later share the app with other people: add the four repository secrets `ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS` and `ANDROID_KEY_PASSWORD` (a key you make with `keytool` and keep safe). Builds are then signed with that key instead, and the workflow summary says "your own release key". Switching keys needs one uninstall and reinstall.

The app's version is the release tag (for example `v0.96` gives version `0.96`); test builds are named `0.96-preview`. Each build has a higher build number than the one before, so it installs as an update.

## What you can do

- **Sign in** opens the app: type your Enveliq's address, your username and password, and a code if you use two-factor. The boxes are marked as username, password and verification code, so a password manager such as Bitwarden can offer to fill them (turn on Bitwarden's autofill service in Android's settings). It then lists your inbox (the same email as the website, newest first), opens an email's summary and original text, and marks emails Reviewed, Archived or Binned for real. The address must start with `https://`, and your Enveliq must be reachable from the phone.
- **Tell me when new email arrives** (Settings) shows a quiet note when a new email's AI summary is done. The lock screen only says "New email" (or "3 new emails"); sender and subject show once the phone is unlocked. Android asks permission the first time. **Quiet hours** keep the note but without sound or buzz. Alerts work while the app is closed, and start again after the phone restarts or the app is updated. See "How new-email alerts work" below.
- **Send a test notification to this phone** shows what an alert looks like. On the lock screen it only says "New email"; the words show once the phone is unlocked. Android asks permission the first time.
- **Hide Enveliq in recent apps** hides the app's picture in the recent-apps view and stops screenshots.

## Not in the app yet

Passkeys and single sign-on, notes from Home Assistant and other services, task reminders, app lock, search, replying and sending, shipping, calendar and the other screens, and an in-app 'new version' button (it needs a public place to look for releases, because this repository is private). The plan for all of these is in the project's Android plan (phases 0 to 5). Settings, Administration and mailbox setup stay on the website.

## How new-email alerts work

- The server has one small stream for the app, `GET /api/v1/me/new-mail-events`. It only says which emails have just become ready (their AI summary is finished). It carries ids, never any text, and the server only ever lists the signed-in person's own email.
- The app holds one connection to that stream. The server sends one line a minute so the connection is not dropped; in between, the app does nothing. There is no polling.
- When the server says something is ready, the app fetches the inbox once, and shows an alert for each email it has not already told you about. It remembers only the ids it has announced (up to 400), so an email is never announced twice. The first time you turn alerts on, the email already in your inbox is not announced.
- No network, no connection: while the phone has no signal the app does not try, and it reconnects the moment a network returns. After a failed try it waits 15 seconds, then longer each time, up to 5 minutes.
- If the server signs the app out, the app stops and tells you once so you can sign in again.
- Android needs a small permanent note while an app keeps a connection open ("Enveliq is watching for new email"). It is silent and tucked away. Turning the setting off removes it.
- If the phone has been still for a long time, Android may pause background apps ("Doze") and alerts can come late. **Keep alerts on time** in Settings asks Android to let Enveliq run without that limit.

## Google's push service (optional)

By default the app keeps its own connection to your server (above). **Settings, Tell me when new email arrives** also offers a second choice, **Google's push service**: alerts arrive instantly, even when the phone has been still for hours, and the "watching" note disappears. The cost: Google is told that a notification was sent to your phone, and when. The message itself holds only the word "mail" (or "test") and a count. The sender, subject and summary never go through Google: the phone wakes up and asks your Enveliq for the details itself, then shows them only once the phone is unlocked.

There is nothing to set up on your server and nothing in Administration. The app sends the wake-up request through the shared Enveliq push relay (see [Push relay](PUSH_RELAY.md)), which holds the one Firebase key for the whole app. The choice only shows when this build of the app includes Google push and the relay address is built in.

Until you choose it the app never contacts Google: Firebase's automatic start-up and analytics are switched off. Switching back to the direct connection, turning alerts off, or signing out deletes the phone's Google address and removes the phone from your Enveliq.

**For whoever publishes the app, once:** deploy the relay ([Push relay](PUSH_RELAY.md)) and add the Firebase project's `google-services.json` to the GitHub repository as the encrypted secret `GOOGLE_SERVICES_JSON` (the **Build Android app** workflow writes it into the build).

Which emails alert you, quiet hours and the "important people only" filter are the same settings as for browser alerts (Settings, Alerts), because the app is one more place those alerts go. Switching on alerts in the app switches on **New email alerts** there. Only new-email alerts go to the app; task reminders use your other channels.

## Privacy

- No email is written to the phone. It is held in memory while on the screen. The only thing kept is your sign-in (below), and the server address you typed.
- Android backups are switched off, so nothing is copied to Google or a new phone.
- The app only talks to the address you typed, over HTTPS, and only trusts the server's real certificate.
- **Staying signed in.** On the sign-in screen, **Keep me signed in on this phone** (on to begin with) keeps your sign-in between runs, so the app opens straight to your inbox. What is kept is the server's sign-in cookie, encrypted with a key in the Android Keystore that never leaves the phone. Your password is never kept. How long it lasts is the same "keep me signed in" time your administrator set for the website. **Sign out** in Settings ends the session at the server and removes what was kept; if the server stops accepting it (you signed out elsewhere, or it ran out) the app asks you to sign in again. Turn the switch off to be asked every time.
- **Alerts** keep your sign-in on the phone (they need it to listen while the app is closed). The only extra things stored are the on/off switches, the quiet hours and the ids of emails already announced; no sender, subject or summary is written to the phone. Alerts go straight between your phone and your own Enveliq: no Google push service and no other company is involved.
- The app adds no analytics, no ads and no crash reporting.

## How it is built

`android/` is a Gradle project (`app/` holds the code). `Api.kt` talks to the same JSON routes the website uses; `Home.kt` and `Screens.kt` are the screens; `SessionVault.kt` keeps the sign-in encrypted; `Notifier.kt` makes the notifications; `Push.kt` is Google's push service (only when chosen); `MailWatcher.kt` is the background service that keeps the one connection and the alert settings; `Data.kt` holds the small data types. The **Build Android app** workflow compiles it with the Android SDK on a GitHub runner, signs it, and attaches the APK. Version 1 for everyone needs the server groundwork in the plan first (per-device tokens, a list of devices, the public API list in Cloudflare).
