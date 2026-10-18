# Connecting Proton Mail Bridge

This guide assumes Bridge already runs as a service on the same machine as
Enveliq, listening on `127.0.0.1:1143` (IMAP) and `127.0.0.1:1025` (SMTP) and
signed in to your Proton account. Enveliq runs in Docker on that machine.

```text
Proton ── Bridge (127.0.0.1:1143 / :1025)
            │ socat forwarders, bound to 172.30.0.1 only
            ▼
        Enveliq container (its own Docker network 172.30.0.0/24)
```

Bridge stays on localhost. Two small forwarders expose it to the one Docker
network Enveliq lives on, the same pattern as any other container that needs it.

## What Enveliq does with Bridge

- **Sync** reads the *headers* of unread inbox mail (sender, subject, reply
  address, which address it was delivered to). It never downloads message bodies
  for syncing and never marks anything as read.
- **View email** fetches the original from Bridge at that moment and shows it,
  as the sender formatted it (colours, layout, tables, links and the pictures that
  travel inside the email), or as plain text if you prefer. Nothing is stored.
  Scripts, forms and anything that could load or run something are removed, and
  pictures from the internet stay hidden until you press **Show pictures**. See
  [Reading the original email](ORIGINAL_EMAIL.md).
- **Reply** goes to the Reply-To address, or From if there is none, exactly as
  received (so Proton Pass, SimpleLogin and similar reverse-alias addresses work).
  It is sent through Bridge from the address the email was delivered to when that
  address is one of the mailbox's sending identities; otherwise from the mailbox
  address. Forwarding aliases rely on the alias service rewriting the sender.
- **Mark reviewed / Archive / Bin** change the real mailbox first (mark read, move
  to `Archive`, move to `Trash`) and remove the item from Enveliq only if that
  worked.
- **Security:** Enveliq trusts only the certificate you export from Bridge
  (pinned, checked again by fingerprint) and sends no username or password until
  that check passes. Bridge must be on a private or local address, or on the
  administrator's allowlist.

## 1. Export Bridge's certificate

On the machine running Bridge (this is the same command as for Paperless; use a
separate copy so Enveliq does not depend on the Paperless folder):

```bash
mkdir -p /opt/enveliq
openssl s_client -starttls imap -connect 127.0.0.1:1143 -showcerts </dev/null 2>/dev/null \
  | openssl x509 -outform PEM > /opt/enveliq/proton-bridge.crt
chmod 644 /opt/enveliq/proton-bridge.crt
openssl x509 -in /opt/enveliq/proton-bridge.crt -noout -subject -dates
```

Do this **before** the first `docker compose up`: Docker turns a missing mount
path into an empty folder. Export it again if you reinstall Bridge or reset its
settings; a new certificate means the old one stops matching.

## 2. Start Enveliq

Make a vault key first, so Enveliq unlocks itself after restarts (see
`docs/VAULT_KEY.md`; keep a copy of it somewhere safe):

```bash
echo "ENVELIQ_VAULT_KEY=$(openssl rand -hex 32)" >> .env
docker compose up -d --build
docker compose exec enveliq cat /data/setup-code.txt
```

The compose file creates a Docker network named `enveliq` on `172.30.0.0/24`
with gateway `172.30.0.1`, mounts the certificate read-only, and tells Enveliq it
may contact only `172.30.0.1`. If that range clashes with another network
(`docker network ls`, then `docker network inspect NAME`), pick another range in
`docker-compose.yml` and use the new gateway everywhere below.

## 3. Add the forwarders

Create `/etc/systemd/system/proton-bridge-enveliq-imap.service`:

```ini
[Unit]
Description=Proton Bridge IMAP forwarder for Enveliq
After=protonmail-bridge.service docker.service
Requires=protonmail-bridge.service

[Service]
Type=simple
ExecStart=/usr/bin/socat TCP-LISTEN:1144,bind=172.30.0.1,fork,reuseaddr TCP:127.0.0.1:1143
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Create `/etc/systemd/system/proton-bridge-enveliq-smtp.service`:

```ini
[Unit]
Description=Proton Bridge SMTP forwarder for Enveliq
After=protonmail-bridge.service docker.service
Requires=protonmail-bridge.service

[Service]
Type=simple
ExecStart=/usr/bin/socat TCP-LISTEN:1026,bind=172.30.0.1,fork,reuseaddr TCP:127.0.0.1:1025
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Start them whenever Bridge starts (the same idea as your Paperless forwarder).
Create `/etc/systemd/system/protonmail-bridge.service.d/enveliq.conf`:

```ini
[Unit]
Wants=proton-bridge-enveliq-imap.service proton-bridge-enveliq-smtp.service
```

Then:

```bash
systemctl daemon-reload
systemctl enable --now proton-bridge-enveliq-imap.service proton-bridge-enveliq-smtp.service
ss -ltnp | grep -E '172.30.0.1:(1144|1026)'
```

The forwarders can use the same port numbers as your Paperless and n8n ones,
because each is bound to a different network gateway address. Anything on the
host can reach `172.30.0.1`, but it still needs the Bridge username and password.

## 4. Test the connection before adding the mailbox

Get the Bridge username and password (they are not your Proton login). Stop
Bridge's service first, as in your Bridge notes, run `protonmail-bridge -c`, type
`info`, then `exit` and start the service again.

```bash
docker compose exec enveliq python -m backend.mail.check \
  --host 172.30.0.1 --imap-port 1144 --smtp-port 1026 --user BRIDGE_USERNAME
```

It asks for the Bridge password (so it stays out of your shell history) and
prints one line each for IMAP and SMTP. Failures say which part is wrong:

| Message | Meaning |
| --- | --- |
| `unreachable` | Forwarder or Bridge is not running, or the address or port is wrong. |
| `certificate_mismatch` | The certificate in `/opt/enveliq/proton-bridge.crt` is not the one Bridge presents (or it has expired). Export it again and run `docker compose restart enveliq`. |
| `no_certificate` | The certificate file is missing from the container. Check the mount. |
| `login_failed` | Wrong Bridge username or password, or Bridge has lost its Proton session (see your Bridge recovery notes). |
| `host_not_allowed` | The address is not `172.30.0.1` (see `ENVELIQ_BRIDGE_ALLOWED_HOSTS`). |

## 5. Add the mailbox in Enveliq

The **Setup guide** (`/welcome`, linked in the menu) walks through this with a
help line under every field and tests the connection before saving. The table
below is the same information.

Sign in, open **Mailboxes** in the top bar (`/mailboxes`) and fill in:

| Field | Value |
| --- | --- |
| Bridge address | `172.30.0.1` |
| IMAP port / SMTP port | `1144` / `1026` |
| Bridge username / password | from `info` above |
| Mailbox email address | your Proton address |
| Also send from | other addresses on the Proton account you reply from when mail arrives there (optional) |

Then press **Check connection** and **Sync now**.

## Not in this version

- **Summaries.** The AI step is not connected yet, so synced items show a
  placeholder summary. Nothing from the message body is stored.
- **Automatic sync.** Enveliq also checks by itself every few minutes while it is unlocked (`ENVELIQ_SYNC_MINUTES`); the button fetches immediately.
- **Mail you read elsewhere** is dropped from the list the next time you sync
  (only Enveliq's saved summary is removed; nothing in your mailbox changes).
- **Folder names** are Bridge's standard `Archive` and `Trash`.
- **Attachments** are listed by name and size in the viewer but not opened.
- **Summaries, tasks and priorities** need the optional AI model: see
  `docs/AI_SUMMARIES.md`. Without it every item shows a placeholder summary.
- **Reviewed and Archived lists** keep Enveliq's summary card for a few days after
  you mark an email Reviewed or Archive it (your mailbox changes at once). Choose
  this under Settings, General; an administrator sets the longest allowed time.
