# Enveliq for Android

A real Android app (not a web page in a frame), written in Kotlin with Jetpack Compose. It lives in the `android/` folder. It is not on the Play Store: you install the APK file yourself.

## Install it

**From a release (the normal way).** When you publish a GitHub Release, the **Build Android app** workflow builds the app and attaches `Enveliq-<version>.apk` (and its checksum, `.sha256`) to that release. Open the release on your phone, download the APK, and open it. Android asks to allow installing apps from your browser or Files app; allow it for that one app, then press **Install**. A new version installs over the old one.

**From a test build.** Every time the test branch `preview/vX.YY` changes the `android/` folder, the same workflow runs. Open **Actions**, **Build Android app**, the newest green run, and download **Enveliq-android-apk** under Artifacts (a zip with the APK inside; kept for 90 days). **Run workflow** starts a build by hand.

## Signing: set up once

Android only installs an update over an app if both were signed with the same key. Builds are signed with your own release key when four repository secrets exist. Make the key once, on your computer (it needs Java's `keytool` and `openssl`):

1. Run `bash android/make-signing-key.sh`. It writes `enveliq-release.jks` and prints four values.
2. **Keep `enveliq-release.jks` and its password safe** (a password manager). If the key is lost, every phone has to uninstall the app before a new version can be installed. Never put the file in the repository.
3. In GitHub, open **Settings, Secrets and variables, Actions** and add the four secrets it printed: `ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`. (The script also prints ready-made `gh secret set` lines.)
4. Run the workflow again. Its summary says "Signed with your release key".

Until the secrets exist, builds are still made, signed with a temporary debug key. They work for trying the app, but the first release-signed build will not install over a debug-signed one: uninstall the app once, then install the new one.

The app's version is the release tag (for example `v0.96` gives version `0.96`); test builds are named `0.96-preview`. Each build has a higher build number than the one before, so it installs as an update.

## What you can do

- **Look around with sample email** shows six made-up emails (nothing to set up). Open one to read its AI summary (labelled as the AI's), the task it found, and the original text. **Reviewed**, **Archive** and **Bin** sit fixed at the bottom; each has an **Undo** for a few seconds. The **Tasks** tab lists the tasks. **Settings** has the notification test.
- **Sign in to my Enveliq** signs in to a real Enveliq with its address, your username and password, and a code if you use two-factor. It then lists your inbox (the same email as the website, newest first), opens an email's summary and original text, and marks emails Reviewed, Archived or Binned for real. The address must start with `https://`, and your Enveliq must be reachable from the phone.
- **Send a test notification to this phone** shows what an alert looks like. On the lock screen it only says "New email"; the words show once the phone is unlocked. Android asks permission the first time.
- **Hide Enveliq in recent apps** hides the app's picture in the recent-apps view and stops screenshots.

## Not in the app yet

Passkeys and single sign-on, notifications from your server, app lock, search, replying and sending, shipping, calendar and the other screens, and an in-app 'new version' button (it needs a public place to look for releases, because this repository is private). The plan for all of these is in the project's Android plan (phases 0 to 5). Settings, Administration and mailbox setup stay on the website.

## Privacy

- No email is written to the phone. It is held in memory while on the screen. The only thing kept is your sign-in (below), and the server address you typed.
- Android backups are switched off, so nothing is copied to Google or a new phone.
- The app only talks to the address you typed, over HTTPS, and only trusts the server's real certificate.
- **Staying signed in.** On the sign-in screen, **Keep me signed in on this phone** (on to begin with) keeps your sign-in between runs, so the app opens straight to your inbox. What is kept is the server's sign-in cookie, encrypted with a key in the Android Keystore that never leaves the phone. Your password is never kept. How long it lasts is the same "keep me signed in" time your administrator set for the website. **Sign out** in Settings ends the session at the server and removes what was kept; if the server stops accepting it (you signed out elsewhere, or it ran out) the app asks you to sign in again. Turn the switch off to be asked every time.
- The app adds no analytics, no ads and no crash reporting.

## How it is built

`android/` is a Gradle project (`app/` holds the code). `Api.kt` talks to the same JSON routes the website uses; `Home.kt` and `Screens.kt` are the screens; `SessionVault.kt` keeps the sign-in encrypted; `Notifier.kt` makes the notifications; `Data.kt` holds the sample emails. The **Build Android app** workflow compiles it with the Android SDK on a GitHub runner, signs it, and attaches the APK. Version 1 for everyone needs the server groundwork in the plan first (per-device tokens, a list of devices, the public API list in Cloudflare).
