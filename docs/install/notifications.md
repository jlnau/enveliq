# Notifications and connecting other services

Enveliq has a **notifications list** (the bell at the top of the screen). Besides new-email alerts, other services on your network can send short notes into it, such as "The washer has finished" from Home Assistant. You can also follow websites with **news feeds** (RSS).

This page shows how to set each one up. Take your time: nothing here changes your email, and you can switch any of it off again.

**What you need first:** Enveliq is installed and you can sign in ([First-time setup](after-install.md)).

## The three ways to bring things in

| I want to... | Use | Where it shows |
|---|---|---|
| Send a note from a tool that can make a web request (Home Assistant, Node-RED, n8n, Uptime Kuma, a script) | [**Webhook**](#send-a-note-with-a-webhook) | The bell |
| Send notes from a tool that keeps a live connection open | [**WebSocket**](#send-notes-over-a-websocket) | The bell |
| Follow a website, blog or news site | [**News feed (RSS)**](#follow-websites-with-news-feeds-rss) | The feed icon (on a phone: the menu, then **News feeds**) |

The webhook and the WebSocket use the same key. Every person makes their own key, and a key only ever adds notes to that person's own list. It cannot read email, tasks or anyone else's notes.

## Step 1. Make your key

1. Open Enveliq and press the **bell** at the top of the screen.
2. Open **Show how to connect Home Assistant or another service**.
3. Press **Make a key**.
4. Press **Copy** and paste the key somewhere safe for the next few minutes. **Enveliq shows it only once.** It starts with `evq_`.

Good to know:

- Making a new key **replaces the old one at once**. Anything still using the old key stops working.
- **Remove my key** switches the key off.
- Treat the key like a password. Do not paste it into a chat, an email or a screenshot. If you ever do, make a new key.

## Step 2. Let your service reach Enveliq

The service has to be able to open Enveliq's address.

- **On your home network**, use the local address of the computer that runs Enveliq, for example `http://192.168.1.50:8765` (your number will be different; [how to find it](choose-settings.md#how-to-find-your-computers-number)). The install file must publish the port to your network: this is the "My home Wi-Fi" choice in [Choose your settings](choose-settings.md), where setting 3 (`ENVELIQ_PUBLISH`) is `0.0.0.0`. Redeploy after changing it. The local address works for notes even if your public address sits behind Cloudflare or a similar service.
- **From outside**, use your normal `https://` address. A service behind some protection services may be blocked, so the local address is the more reliable choice for things in your own home.
- Do **not** forward port 8765 on your router.
- If the service runs in Docker too (as Home Assistant often does), `localhost` means the service's own box. Use your computer's number instead.

## Send a note with a webhook

A webhook is one web request, sent whenever something happens.

- **Address:** `http://192.168.1.50:8765/api/v1/inbound/webhook` (replace the number with yours, or use your `https://` address)
- **Method:** `POST`
- **Header:** `Authorization: Bearer evq_YOUR-KEY-GOES-HERE`
- **Body (JSON):** `{"title": "Washer finished", "message": "Empty it", "source": "Laundry"}`

Only `title` or `message` is needed (at least one). `source` is optional and says where the note came from.

### Test it from a computer

On a computer with `curl` (Mac, Linux, or Windows 10 and later in a terminal), run this with your own address and key:

```
curl -X POST "http://192.168.1.50:8765/api/v1/inbound/webhook" \
  -H "Authorization: Bearer evq_YOUR-KEY-GOES-HERE" \
  -H "Content-Type: application/json" \
  -d '{"title": "Test note", "message": "Hello from my computer"}'
```

You should see `{"ok":true}`, and "Test note" appears in your bell within a moment.

### What the answers mean

| Answer | What it means | What to do |
|---|---|---|
| `200` `{"ok":true}` | The note arrived. | Nothing. |
| `401` | The key is missing, wrong or replaced. | Check the word `Bearer` and the key, or make a new key. |
| `400` | The note could not be used (empty, or too long). | A title can be up to 100 characters, a message up to 500, a source up to 40. |
| `413` | The request was too big. | Send less than 4,000 characters. |
| `415` | The request was not JSON. | Add `Content-Type: application/json`. |
| `429` | Too many notes. | The limit is 30 a minute. Wait a minute. |
| `503` | Enveliq is locked. | Unlock it, then try again. |
| Nothing at all, or "refused" | The service cannot reach Enveliq. | Check the address, the port and `ENVELIQ_PUBLISH` (Step 2). |

The key goes only in the `Authorization` header. Enveliq never reads it from the address or the body.

## Add it to Home Assistant

This sends every new Home Assistant notification (the ones under its own bell) to Enveliq. It uses Home Assistant's built-in **RESTful Command**, so nothing needs installing.

### A. Keep the key in secrets

In Home Assistant, open the File editor and edit `/config/secrets.yaml`. Add one line (the word `Bearer`, a space, then your key):

```
enveliq_authorization: "Bearer evq_YOUR-KEY-GOES-HERE"
```

### B. Add the command

Edit `/config/configuration.yaml` and add this at the bottom:

```
rest_command:
  enveliq_notification:
    url: "http://192.168.1.50:8765/api/v1/inbound/webhook"
    method: POST
    headers:
      Authorization: !secret enveliq_authorization
    content_type: "application/json"
    payload: >-
      {
        "title": {{ title | to_json }},
        "message": {{ message | to_json }},
        "source": "Home Assistant"
      }
    timeout: 15
```

If the file already has a `rest_command:` section, add only the `enveliq_notification:` part under it. Do not make a second `rest_command:` section.

### C. Load it

1. In Home Assistant go to **Developer tools, then YAML**, and press **Check configuration**.
2. Under the reload options choose **RESTful Commands**. You do not need to restart Home Assistant.

### D. Test it first

1. Go to **Developer tools, then Actions**.
2. Switch to **YAML mode** and paste:

```
action: rest_command.enveliq_notification
data:
  title: "Home Assistant connected"
  message: "This is a test note from Home Assistant."
```

3. Press **Perform action**, then open the bell in Enveliq. You should see the note.

### E. Send every new Home Assistant notification

Once the test works:

1. Go to **Settings, then Automations & scenes, then Create automation, then Create new automation**.
2. Open the three-dot menu and choose **Edit in YAML**.
3. Paste:

```
alias: Send Home Assistant notifications to Enveliq
description: Sends each new Home Assistant notification to Enveliq.
triggers:
  - trigger: persistent_notification
    update_type:
      - added
conditions: []
actions:
  - action: rest_command.enveliq_notification
    data:
      title: >-
        {{ trigger.notification.title | default('Home Assistant', true) }}
      message: >-
        {{ trigger.notification.message | default('', true) }}
mode: queued
max: 20
```

4. Save it and make sure it is switched on.

### F. Check it works by itself

In **Developer tools, then Actions**, run:

```
action: persistent_notification.create
data:
  title: "Automatic test"
  message: "This should appear in Enveliq by itself."
```

It should show in Home Assistant's bell and, a moment later, in Enveliq's.

Only **new** notifications are sent. Ones that already existed are not copied, and dismissing one in Home Assistant does not dismiss the copy in Enveliq.

### G. Rotate the key

If the key was ever shown anywhere it should not have been (a chat, a screenshot), make a new key in Enveliq (Step 1), update `secrets.yaml`, and reload **RESTful Commands**. The old key stops working the moment the new one is made.

## Send notes over a WebSocket

Some tools keep a live connection open instead. Connect to `ws://192.168.1.50:8765/api/v1/inbound/ws` (or `wss://your-address/api/v1/inbound/ws` from outside, if your proxy passes WebSockets through) and send:

1. `{"type":"auth","token":"evq_YOUR-KEY-GOES-HERE"}`. Enveliq answers `{"type":"auth_ok"}`.
2. `{"type":"notify","title":"Washer finished","message":"Empty it"}`. Enveliq answers `{"type":"ok"}`.
3. `{"type":"ping"}` now and then. The connection closes after two minutes of silence.

The limits are the same as for the webhook and shared with it.

## Follow websites with news feeds (RSS)

News feeds are the other direction: Enveliq reads a website for you.

1. Press the **feed icon** at the top (on a phone: the menu at the top left, then **News feeds**).
2. Paste the **feed address** of the website. It usually ends in `/feed`, `/rss` or `.xml`; many sites show an RSS icon.
3. Press **Add feed**.

New entries are counted on the badge and shown in the pop-up. What a feed already holds when you add it is the starting point, so only entries that appear later count as new. Each person follows their own feeds, and nobody else can see them.

A feed on your own network (such as a home server's feed) is refused unless an administrator allows it in **Administration, Reminders**. If you can, use the webhook for things at home and RSS for websites.

More: [News feeds](../NEWS_FEEDS.md).

## If a note does not arrive

1. Run the `curl` test above from a computer. If that works, Enveliq is fine and the problem is in the other service.
2. `401`: make a new key and use it everywhere.
3. No answer: check the address and port, and that the port is published to your network (Step 2). Services in Docker cannot use `localhost` for another box.
4. Check the exact words: `Authorization: Bearer evq_…` has the word `Bearer` and one space.
5. Still stuck? See [Troubleshooting](troubleshooting.md).

## More

- [Reminders and notifications](../NOTIFICATIONS.md): browser and phone alerts, Telegram, Discord, Slack and the other channels Enveliq can send to.
- [Use it without https](../NETWORK_ACCESS.md): reaching Enveliq by its local address.
- [News feeds](../NEWS_FEEDS.md)
