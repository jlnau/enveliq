# Opening Enveliq on your network (no tunnel, no reverse proxy)

This is the quick option. For https (needed for passkeys and Outlook sign-in), start with [ACCESS.md](ACCESS.md).

By default Enveliq listens on the host's loopback only, so you reach it through an SSH tunnel or a
reverse proxy that adds https. If the machine is on a network you trust and you want to open it by
typing its address and port, you can turn that on. It is off until you do all three steps.

## Turn it on

In the `.env` file next to `docker-compose.yml` (in Arcane: the project's environment variables), set
the address of the machine that runs Enveliq. These three lines go together:

```
ENVELIQ_PUBLISH=0.0.0.0
ENVELIQ_PUBLIC_URL=http://192.168.1.50:8765
ENVELIQ_ALLOW_INSECURE_PUBLIC_URL=1
```

Replace `192.168.1.50` with the machine's own address. Then update and redeploy:

```
cd /opt/enveliq-app && git pull && docker build -t enveliq:local . && docker build -f Dockerfile.render -t enveliq-render:local .
```

Press Redeploy in Arcane (or `docker compose up -d`), and open `http://192.168.1.50:8765`.

Use the exact address you put in `ENVELIQ_PUBLIC_URL`. Enveliq only answers to that address (and
localhost). Opening it by another name, such as a different IP or a hostname you did not list, is
refused on purpose. To allow more names, add `ENVELIQ_ALLOWED_HOSTS` and `ENVELIQ_ALLOWED_ORIGINS`
(see `.env.example`).

## A local address for Home Assistant and other services

The WebSocket door (and its plain `POST` twin, the webhook) that lets Home Assistant and other services send notes to Enveliq (see [NOTIFICATIONS.md](NOTIFICATIONS.md)) also answers on the machine's private network address, such as `ws://192.168.1.50:8765/api/v1/inbound/ws` or `http://192.168.1.50:8765/api/v1/inbound/webhook`, even though you normally reach Enveliq by its public name behind Cloudflare. For that you only need `ENVELIQ_PUBLISH=0.0.0.0` (the first line above); `ENVELIQ_PUBLIC_URL` can stay your https name. Everything else on that address is still refused.

## What you give up

- **Nothing is encrypted on the wire.** Passwords, the sign-in cookie and the summaries shown in the
  browser can be read by anyone who can see traffic between the browser and the machine. Mail is still
  encrypted at rest and still reaches the mail provider over TLS.
- **Passkeys do not work.** Browsers only allow them on https or localhost. Use a password with an
  authenticator app (two-factor still works).
- **Microsoft sign-in does not work.** Microsoft only accepts an https redirect address (or localhost).
  Everything else, including app-password mailboxes and Proton Bridge, works as before.
- **Single sign-on** works only if your provider accepts an http redirect address.
- The Copy buttons may need you to select the text by hand, because browsers limit the clipboard to
  secure pages.

Keep the port closed to anything outside your network (no router port forward). If you later want
https, put a reverse proxy in front, set `ENVELIQ_PUBLIC_URL` to its https address, and remove the
three lines above.

## Turn it off again

Delete the three lines (or set `ENVELIQ_PUBLISH=127.0.0.1`) and redeploy.
