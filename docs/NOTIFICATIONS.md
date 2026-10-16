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

## Choose which email alerts you receive

Under your own **Settings → Email alerts** (not Administration), you can switch new-email alerts on or off and choose **All new emails**, **Important people only**, or **Needs action only**. All new emails is the default filtering mode; new-email delivery itself retains its existing opt-in setting. Important people uses your existing Important people list; Needs action uses the message's existing action-required classification, without inventing a new classifier. If an email has not been classified as requiring action, it does not generate a Needs action alert.

Each connected mailbox has its own notification switch, enabled by default. Muting a mailbox stops new-email notifications from that mailbox but does not disconnect it, hide mail, disable tasks or change mail syncing. These settings are saved per person and apply across devices.

Your existing notification channels, channel permissions, privacy options and quiet hours continue to work exactly as before. Filtering is applied **before** a new-email alert is constructed, so a notification with one qualifying email opens that email; a notification with several qualifying emails opens the inbox.

## Back after opening a notification

On Android, opening an email from a notification and pressing Back returns to the Enveliq inbox, instead of leaving the application. If Enveliq was already showing another screen, Back returns to that screen where possible. The notification does not make duplicate history steps when a second notification is opened.

## New email alerts

Switch on **Tell me when new email arrives** in **Settings, Notifications** and Enveliq sends one short message each time it finds new email for you, to the places you chose under *Where to send reminders*. It is off until you switch it on.

When the mailbox uses AI summaries, the alert is sent once the new email is ready to read in your inbox (after its summary and its files' summaries), so it never points at an email you cannot see yet. Mail that arrives together is announced in one message.

* By default the message only says how many emails arrived ("2 new emails"). Under *Repeats, quiet hours and privacy*, **Show who a new email is from and its subject** adds the sender's name and the subject. Services such as ntfy or a chat app can read what you send them, so leave this off if you would rather your lock screen and those services learn nothing about your mail. Your own device's browser push is encrypted end to end.
* The email text, the sender's address and the summary are never sent.
* Quiet hours apply: nothing is sent during them, and the emails wait in your inbox.
* It speaks about mail Enveliq fetches by itself (Administration, Automatic sync). Mail you fetch by pressing **Sync mail** is not announced, because you are already looking at it, and neither is the first read of a mailbox you have just connected.
* Tapping the message opens Enveliq at that email when there is one, or at your inbox when there are several.

## The bell, and messages from Home Assistant and other services

At the top right of the inbox, beside the news-feed icon (on a phone the bell stays in the top bar and the news feeds are in the menu), a **bell** collects two things in one drop-down (a full-screen window on a phone):

* **Notes sent to you by other services** on your network, such as Home Assistant ("Washer finished"). Each shows its title, its text, where it came from and when. **Dismiss** removes one, **Mark all as read** and **Clear the list** do what they say. Only the newest 100 are kept.
* **Your chat messages** from the people who share this Enveliq (see [MESSAGES.md](MESSAGES.md)): a line saying how many are unread and from whom, with a **Read messages** button.

The number on the bell adds the unread notes and the unread chat messages. Opening the drop-down and closing it marks the notes as read; chat messages stay unread until you read them in Messages.

### How a service sends you a note

A step-by-step guide with Home Assistant is in [Notifications, webhooks and news feeds](install/notifications.md).

A service connects to Enveliq's **WebSocket door** at `/api/v1/inbound/ws` and sends short plain-text notes. It proves who it is with a **key that you make for yourself**. In the bell, open **Show how to connect Home Assistant or another service**, press **Make a key**, and copy the key (it is shown once, then never again; a new key replaces the old one, and **Remove my key** switches it off). The key belongs to you only: it can add notes to your own bell and nothing else.

1. Connect to `ws://YOUR-SERVER-IP:8765/api/v1/inbound/ws` on your own network (or `wss://your-address/api/v1/inbound/ws` from outside, if your proxy passes WebSockets through).
2. Send `{"type":"auth","token":"YOUR-KEY"}` first. Enveliq answers `{"type":"auth_ok"}`. (A client that can set headers may send `Authorization: Bearer YOUR-KEY` instead and skip this step.)
3. Send notes: `{"type":"notify","title":"Washer finished","message":"Empty it","source":"Home Assistant"}`. Enveliq answers `{"type":"ok"}` or `{"type":"error","message":"…"}` with the reason. `{"type":"ping"}` answers `{"type":"pong"}`; the door closes after two minutes of silence, so send a ping now and then.

Limits: a title up to 100 characters, a message up to 500, a source up to 40, 4,000 characters in one message, 30 notes a minute, and 5 open connections per person. Text is cleaned and shown only as plain text, never as a web page or a link, and the bell always says where a note came from.

### Or send a plain web request (webhook)

Some tools (Node-RED, n8n, Uptime Kuma, a Home Assistant `rest_command`) can send a web request but cannot keep a WebSocket open. For them there is a second door at `/api/v1/inbound/webhook`. It is available to everyone who is signed in: the same **Make a key** button in the bell makes the key, and the **Show how to connect** fold in the bell explains it.

Send a `POST` to `https://your-address/api/v1/inbound/webhook` (or `http://YOUR-SERVER-IP:8765/api/v1/inbound/webhook` on your own network) with the header `Authorization: Bearer YOUR-KEY` and a JSON body such as `{"title":"Washer finished","message":"Empty it","source":"Node-RED"}`. Enveliq answers `{"ok":true}`, or a plain reason: `401` the key is not accepted (missing, wrong, replaced, removed, or the person is switched off), `400` the note was not acceptable, `413` too big, `415` the body was not JSON, `429` too many (at most 30 notes a minute per person, shared with the WebSocket door), `503` Enveliq is locked.

The key is only read from the `Authorization` header, never from the address or the body. The note lands in the bell of the person who made the key, with the same limits and the same plain-text cleaning as the WebSocket door. Extra fields such as `priority` or `url` are ignored.

### It works over the local IP address

Cloudflare's protection sits in front of the public address and can stop a service from reaching it. The doors (the WebSocket and the webhook) therefore also answer on the machine's **local network address** (for example `192.168.1.50`), where Cloudflare is not involved. This is the one place Enveliq accepts a bare address instead of its public name, and only for this door and only for addresses on a private network (`192.168.x.x`, `10.x.x.x`, `172.16.x.x` to `172.31.x.x`, `fc00::/7` and this machine); every other page and every other address still needs the public name you set. To make the door reachable on your network, publish the port beyond the machine itself: set `ENVELIQ_PUBLISH=0.0.0.0` in `.env` (or the Arcane project's variables) and redeploy; see [NETWORK_ACCESS.md](NETWORK_ACCESS.md). A host name instead of an address (for example `enveliq.local`) must be listed in `ENVELIQ_ALLOWED_HOSTS`.

Server: `backend/mail/inbound.py`, `backend/mail/inbound_routes.py` (the WebSocket door, the webhook and `/api/v1/me/bell`), `backend/security.py` (`HostGuardMiddleware`). Checks: `tests/test_inbound.py`, `scripts/check_bell.mjs`.

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

## Testing one browser device

Every browser device you have turned notifications on for has its own **Test** button, which sends the test only to that device. If a device no longer accepts notifications it is removed and you are told, even when another device worked. A new-mail alert goes out as soon as each summarised email is visible.
