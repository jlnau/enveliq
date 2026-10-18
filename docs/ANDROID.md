# Enveliq for Android (demo)

A real Android app (not a web page in a frame), written in Kotlin with Jetpack Compose. It lives in the `android/` folder. This first version is a **demo** you can try on your own phone. It is not on the Play Store and is not meant to be shared yet.

## Try it

1. On GitHub, open the **Actions** tab, then the **Build Android demo** workflow. (It runs by itself whenever the test branch `preview/vX.YY` changes the `android/` folder, and **Run workflow** starts it by hand.)
2. Open the newest green run. At the bottom, under **Artifacts**, download **Enveliq-demo-apk**. It is a zip with one file inside, `Enveliq-demo.apk`.
3. Unzip it on your phone (or copy the file there) and open the file. Android asks to allow installing apps from this source; allow it for that one app (your browser or Files). Press **Install**.
4. Open **Enveliq**.

A new build is signed with the same key as the one before, so it installs over the old one. If Android says the app "conflicts" with an existing one, uninstall Enveliq first, then install again.

## What you can do in the demo

- **Try the demo** shows six made-up emails. Open one to read its AI summary (labelled as the AI's), the task it found, and the original text. **Reviewed**, **Archive** and **Bin** sit fixed at the bottom; each has an **Undo** for a few seconds. The **Tasks** tab lists the tasks. **Settings** has the notification test.
- **Connect to my Enveliq** signs in to a real Enveliq with its address, your username and password, and a code if you use two-factor. It then lists your inbox (the same email as the website, newest first), opens an email's summary and original text, and marks emails Reviewed, Archived or Binned for real. The address must start with `https://`, and your Enveliq must be reachable from the phone.
- **Send a test notification to this phone** shows what an alert looks like. On the lock screen it only says "New email"; the words show once the phone is unlocked. Android asks permission the first time.
- **Hide Enveliq in recent apps** hides the app's picture in the recent-apps view and stops screenshots.

## Not in the demo yet

Passkeys and single sign-on, push notifications from your server, app lock, search, replying and sending, shipping, calendar and the other screens, and a signed release build. The plan for all of these is in the project's Android plan (phases 0 to 5). Settings, Administration and mailbox setup stay on the website.

## Privacy

- No email is written to the phone. It is held in memory while on the screen.
- Android backups are switched off, so nothing is copied to Google or a new phone.
- The app only talks to the address you typed, over HTTPS, and only trusts the server's real certificate.
- The signed-in session is held in memory only. Closing the app signs you out. Your password is not kept.
- The app adds no analytics, no ads and no crash reporting.

## How it is built

`android/` is a Gradle project (`app/` holds the code). `Api.kt` talks to the same JSON routes the website uses; `Home.kt` and `Screens.kt` are the screens; `Notifier.kt` makes the notifications; `Data.kt` holds the demo emails. The **Build Android demo** workflow compiles it with the Android SDK on a GitHub runner and attaches the APK. A debug signing key is used, so it is only for trying the app. Version 1 for everyone needs the server groundwork in the plan first (per-device tokens, a list of devices, the public API list in Cloudflare).
