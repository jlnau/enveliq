# Reminders and notifications

Enveliq makes a task for every email that needs you (see **Tasks** in the inbox). Tasks always show in Enveliq under **Today**. If you also want a nudge on your phone or in a chat app, add one or more channels under **Settings, Reminders**.

Each channel has the same four steps: follow the short guide on its card, fill in the fields, press **Save and send a test**, and check that the test arrived. A card shows **Working** after a send succeeds and **Last send failed** with the reason if it does not.

## What gets sent

* A **morning summary** (default 08:00): how many things are due today.
* A **reminder** when a task is due, or when a new task for today appears after the summary.
* A **nudge** if a task is still open (default every 2 hours, at most 2 times).
* **Quiet hours** (default 21:00 to 07:00): nothing is sent; what was held goes out when they end.
* **Private mode**: switch off *Show task titles* and reminders only say that something is due.

Only the task title and a link back to Enveliq are sent, never the email text. If a send fails, Enveliq tries again after 5 minutes. A task that is done, removed or whose email was dealt with stops sending at once.

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
