# Reminders and notifications

In Settings this page is called **Notifications** (it used to be called Reminders). It has two steps: **1. Where should notifications go?** (your phone, a chat app, email and so on) and **2. What should I tell you about?** (the morning summary, things that are due, and new email). A line at the top says where notifications reach you right now.

Enveliq makes a task for every email that needs you (see **Tasks** in the inbox). Tasks always show in Enveliq under **Today**. If you also want a nudge on your phone or in a chat app, add one or more channels under **Settings, Notifications**.

Each channel has the same four steps: follow the short guide on its card, fill in the fields, press **Save and send a test**, and check that the test arrived. A card shows **Working** after a send succeeds and **Last send failed** with the reason if it does not.

## What gets sent

* A **morning summary** (default 08:00): how many things are due today.
* A **reminder** when a task is due, or when a new task for today appears after the summary.
* A **nudge** if a task is still open (default every 2 hours, at most 2 times).
* **Quiet hours** (default 21:00 to 07:00): nothing is sent; what was held goes out when they end.
* **Private mode**: switch off *Show task titles* and reminders only say that something is due.

Only the task title and a link back to Enveliq are sent, never the email text. If a send fails, Enveliq tries again after 5 minutes. A task that is done, removed or whose email was dealt with stops sending at once.

## New email alerts

Switch on **Tell me when new email arrives** in **Settings, Notifications** and Enveliq sends one short message each time it finds new email for you, to the places you chose under *Where to send reminders*. It is off until you switch it on.

When the mailbox uses AI summaries, the alert is sent once the new email is ready to read in your inbox (after its summary and its files' summaries), so it never points at an email you cannot see yet. Mail that arrives together is announced in one message.

* By default the message only says how many emails arrived ("2 new emails"). Under *Repeats, quiet hours and privacy*, **Show who a new email is from and its subject** adds the sender's name and the subject. Services such as ntfy or a chat app can read what you send them, so leave this off if you would rather your lock screen and those services learn nothing about your mail. Your own device's browser push is encrypted end to end.
* The email text, the sender's address and the summary are never sent.
* Quiet hours apply: nothing is sent during them, and the emails wait in your inbox.
* It speaks about mail Enveliq fetches by itself (Administration, Automatic sync). Mail you fetch by pressing **Sync mail** is not announced, because you are already looking at it, and neither is the first read of a mailbox you have just connected.
* Tapping the message opens Enveliq at that email when there is one, or at your inbox when there are several.

## Install Enveliq as an app

On Android (Chrome or Edge) open Enveliq at its `https://` address, open the browser menu and choose **Install app** (or **Add to Home screen**). Enveliq then has its own icon and opens in its own window. On an iPhone or iPad use **Share, Add to Home Screen**; that is also what lets an iPhone receive browser notifications. On a computer, Chrome and Edge show an install icon in the address bar.

Then, under **Where to send reminders**, press **Turn on for this device** on the phone. Tapping a notification opens Enveliq at the email it is about, even if the app was closed.

On Android, a notification shows two icons. The small one (in the status bar and the notification's top line) is Enveliq's own mark. The large round one on the left is the browser's own app icon: it only becomes Enveliq's logo if Enveliq is installed as an app, as above.

Notifications and installing need the `https://` address you use for Enveliq (set in `ENVELIQ_PUBLIC_URL`); a plain `http://` address on your network is not enough. Phones can also use ntfy or Home Assistant instead, see the table below.

## Channels

| Channel | You need | Notes |
| --- | --- | --- |
| This device (browser) | Chrome, Edge, Firefox or Safari, and an `https://` address (or localhost) | Press **Turn on for this device** and choose Allow. Up to 5 devices. On an iPhone or iPad add Enveliq to the Home Screen first. Messages are encrypted before they leave Enveliq; the browser's own push service (Google, Mozilla, Apple, Microsoft) only passes them on. |
| Email | One of your own mailboxes in Enveliq | A short email to yourself. Only your own mailboxes are accepted, and Enveliq marks these emails so it never makes a task or summary from them. |
| ntfy | The ntfy phone app and a long random topic name | Works with the free ntfy.sh or your own server. Anyone who knows the topic can read it, so make it long. |
| Gotify | Your Gotify server and an application token | Usually on your own network, see below. |
| Home Assistant | Address, long-lived access token and a notify service such as `notify.mobile_app_your_phone` | Settings, People, Security, Long-lived access tokens. Find the service name in Developer tools, Actions. |
| Discord | A channel webhook (channel settings, Integrations, Webhooks) | Messages never ping @everyone. |
| Telegram | A bot from @BotFather and your chat id | Press Start in the bot first, otherwise it cannot message you. |
| Slack | An app with Incoming Webhooks | |
| Pushover | User key and an application token | Paid app, one-off price. |
| Matrix | Homeserver, access token, room id | |
| Webhook | Any address that accepts JSON | Body: `{"title", "message", "priority", "url"}`. Use it for Node-RED, n8n or a Home Assistant webhook. |

Secrets (tokens, webhook addresses) are write-only: after you save them the page shows *Saved* and never shows them again. Leave the box blank to keep what is saved. They are stored encrypted in the vault.

## Services on your own network

Enveliq refuses to call addresses on your own network (192.168.x.x, 10.x.x.x, localhost and so on) unless an administrator listed them. This stops a typed address from being used to probe your network. To allow your ntfy, Gotify or Home Assistant:

* In Enveliq: **Administration, Reminders, Allowed addresses**, one per line, for example `192.168.1.0/24` or `homeassistant.local`; or
* In `.env` (or the Arcane project's environment): `ENVELIQ_NOTIFY_ALLOWED_HOSTS=192.168.1.0/24,homeassistant.local`. The compose file passes it through.

Plain `http://` is only accepted for allowed local addresses; anything on the internet must use `https://`. Link-local addresses (including cloud metadata addresses) are never allowed. Connections go to the address that was checked, follow no redirects, time out after 10 seconds and read at most 64 KB.

The administrator can also switch individual channels off for everyone (**Administration, Reminders**).

## If a test fails

* *That address is on your own network*: ask your administrator to allow it (above).
* *Could not reach it*: check the address and that Enveliq's container can reach it (same Docker network or routable LAN).
* *The secure connection could not be trusted*: the certificate does not match the name; use the name on the certificate or a trusted certificate.
* Nothing arrives but the test says sent: check the app's own settings (phone do-not-disturb, topic spelled the same).

Reminders are only sent while Enveliq is unlocked, because tasks live in the encrypted vault. After a restart, unlock it as usual.
