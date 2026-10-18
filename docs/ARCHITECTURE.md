# Enveliq architecture

Enveliq is a standalone, self-hosted web service. Home Assistant is one way to run it and one of the things it connects to, not a requirement.

```
                 ┌─────────────────────────── your network ───────────────────────────┐
 Browser ──HTTPS──► Reverse proxy ──► Enveliq server (Docker / Linux / HA add-on)       │
 (phone, laptop)  │ Caddy / Traefik /   │  ├─ web app + sign-in pages                   │
                  │ NPM, TLS            │  ├─ API (/api/v1)                              │
                  │                     │  ├─ encrypted vault (SQLite, /data)            │
                  │                     │  ├─ mail sync + provider adapters  ──► IMAP / Proton Bridge / Gmail / Microsoft
                  │                     │  └─ AI pipeline (isolated)         ──► admin-chosen LLM
 Sign-in provider ◄─── OIDC ────────────┘                                                │
 (Authentik, Authelia, Keycloak…)                                                        │
 Home Assistant ──── HACS integration ──── scoped API token ──► Enveliq API              │
                  └──────────────────────────────────────────────────────────────────────┘
```

## Why standalone

- **Security isolation.** Enveliq holds mail credentials and processes hostile content. Home Assistant controls locks, alarms and cameras. Separate services keep a compromise of one from reaching the other.
- **Reach.** It runs anywhere containers run, including for people whose Home Assistant is a Docker install (which cannot use add-ons) and people without Home Assistant.
- **Provider sign-in.** Gmail and Microsoft OAuth, and OIDC single sign-on, need a stable public URL to return to.

## Components

| Component | What it is | Status |
| --- | --- | --- |
| Enveliq server | One Docker image: web app, API, vault, sign-in, (later) sync and AI pipeline | Sign-in and vault done; mail sync next |
| Home Assistant add-on | A thin wrapper that runs the same image under HA OS, with the sidebar panel through ingress | Planned |
| Home Assistant integration (HACS) | Connects HA to an Enveliq server with a scoped API token | Planned |

## Identity and sign-in

Enveliq has its own user accounts. Every account is one of:

- **Local**: username and password (Argon2id), optionally with an authenticator app (TOTP) and/or passkeys.
- **Single sign-on**: created automatically the first time an allowed person signs in through the configured OpenID Connect provider (Authentik, Authelia, Keycloak, Pocket ID, Zitadel, Kanidm…). See [SSO.md](SSO.md).

Rules:

- **First run** needs a one-time setup code from the server's data folder or log, so nobody who merely reaches the URL can claim the instance. Setup creates the first administrator and the vault's protection: the key from `ENVELIQ_VAULT_KEY` or a key file if one is set (Enveliq then unlocks itself after restarts), otherwise a typed passphrase.
- **Two-factor** is required for administrators by default (configurable: administrators / everyone / optional). Passkeys count as two factors because they require device verification (PIN or biometric). Each user gets ten one-time recovery codes.
- **Break-glass**: administrators can always sign in with a password, so a broken SSO provider cannot lock everyone out. Password sign-in for other users can be turned off.
- **No email matching**: an SSO identity is never attached to an existing account because the email matches. People link their own account while signed in.
- **Group rules**: optional allowed groups (who may sign in) and administrator groups (who becomes an admin, re-checked at each sign-in).
- **Sessions** are random tokens in `HttpOnly`, `SameSite=Lax` cookies (`Secure` and `__Host-` prefixed on HTTPS), held only in memory. Restarting or locking the vault signs everyone out.

## Vault and restarts

All user records (usernames, password hashes, TOTP secrets, passkeys, SSO links) and all mailbox data are encrypted under the vault's master key, which is itself wrapped by a key derived from the vault passphrase. After a restart the vault is locked: someone with the passphrase unlocks it at `/unlock`, then people sign in. A future option can unlock automatically from a TPM or an external secrets manager; the passphrase is never stored next to the database.

## Home Assistant integration (planned)

The integration talks to the Enveliq API with a **scoped, revocable API token** created by an Enveliq administrator. Proposed features:

- **Sensors** per person: items needing action, high-priority items, total in review.
- **Events** when a new item arrives (category and priority only), for automations such as flashing a light for urgent mail.
- **Actions** for automations and Assist: sync now, mark reviewed, archive.
- **To-do and calendar**: suggested tasks and appointments into HA's own lists.
- **Notifications** through HA scripts or notify services.
- **Dashboard card**: the review queue with summaries and Reviewed/Archive buttons, plus "Open in Enveliq" for the full email or a reply.

**Privacy rule:** Home Assistant stores entity states and attributes unencrypted in its history database and shows every entity to every HA user. The integration therefore exposes **counts only, never subjects or summaries**. The dashboard card fetches content live from Enveliq and shows it only to the person it belongs to.

## Deployment

- `docker-compose.yml` publishes the server on the host's loopback (`127.0.0.1:8765`) for a reverse proxy to terminate HTTPS. Set `ENVELIQ_PUBLIC_URL` to the proxy's `https://` address.
- The container runs as an unprivileged user with a read-only root filesystem, all capabilities dropped and `no-new-privileges`. Data lives in the `/data` volume.
- The server refuses an `http://` public URL other than localhost, refuses to listen on a non-loopback address unless told it is behind a proxy, and ignores `X-Forwarded-*` headers.

## Roadmap

1. Mail provider adapters: Proton Bridge (IMAP + SMTP), generic IMAP with app passwords, and Microsoft (OAuth sign-in, then XOAUTH2 over IMAP and SMTP: `mail/microsoft.py`, `mail/microsoft_routes.py`). Gmail through OAuth is not planned.
2. Connect the inbox page to the API (it still shows sample data) and split it into bundled files so it can run under the same strict CSP as the sign-in pages.
3. AI pipeline in an isolated worker.
4. Home Assistant API tokens, HACS integration and the add-on wrapper.

## Reporting (v0.32)

`backend/reporting/` turns activity into counts, timings and security events for Grafana and others. `Reporter` receives events from three places: the audit log (a hook on `SecureVault.audit`), `MailService` (sync and AI request timings) and app start. Every event passes a field allow-list before it touches a counter or a queue, so no email content can be reported. Counters live in an in-memory Prometheus-style registry served at `GET /metrics` (bearer token, hashed in the vault); state gauges (unread by mailbox, priority, category) are computed from the vault at scrape time. A background thread delivers queued events to the outputs an administrator switched on (JSON log lines, Loki push, signed webhook) through `reporting/net.py`, which checks every destination and connects to the checked address. Settings are in the encrypted global record `reporting_config`. See `docs/REPORTING.md`.

v0.33 adds two outputs. `Reporter.otlp_payload` renders the same registry as OpenTelemetry JSON and pushes it on a timer (`otlp.interval`). `reporting/grafana.py` talks to Grafana's HTTP API with a service-account token: connection check, data source list, folder, dashboard install (`reporting/enveliq-dashboard.json` is the single source; `docs/grafana/` carries an identical copy) and annotations, which `Reporter` queues for a short list of key events with fixed wording.


## Live email updates

Authenticated clients connect to `GET /api/v1/me/mail-events` through same-origin Server-Sent Events. The stream checks an owner-scoped fingerprint of encrypted-vault message metadata and opened indicators; no message content, sender, subject, account names or secrets are sent in events. Changed events instruct the existing mail client to re-fetch using normal user-scoped API calls. Browser EventSource reconnects automatically, while a periodic fallback and page visibility/network wake-up recover missed updates. The client retains selected-message identity and scroll offset during refresh. The stream does not itself trigger provider mailbox synchronization; the existing server sync scheduler continues to do so.

### Android alert stream

`GET /api/v1/me/new-mail-events` is a second, much smaller stream for the Android app. It needs the same full session. Every 5 seconds (sharing a 4-second per-person cache) it compares the person's set of finished, unread emails (`ready_mail`: stored, not from All Mail, not waiting for the AI) with what it had, and sends `event: new` with only `{"count", "ids": [{"a": account, "m": message}]}` for the new ones. It sends a comment line once a minute (below Cloudflare's idle limit) so the connection stays open without waking the phone often. The app then fetches the inbox through the normal user-scoped routes. See `docs/ANDROID.md`.

## Junk Mail (v0.95)

- `backend/mail/junk.py`: `JunkBook`. One encrypted per-person record `junk:<user id>` (outside the retained messages, so junk never reaches the inbox, reminders, Found emails or the summary queue). `refresh` reads each mailbox's junk folder (IMAP `\Junk` flag, else Spam/Junk names; always Spam on Proton Bridge) read-only, headers only; `classify` shows a few emails at a time to the model (`Summariser.judge_junk`); `not_junk` selects the folder read-write, marks the email unread, moves it to `INBOX` (IMAP MOVE, or COPY and expunge) and syncs the mailbox.
- `backend/mail/junk_routes.py`: `/api/v1/junk` list, `refresh`, `check`, `{id}/original`, `{id}/original/html`, `{id}/not-junk`, all behind the `junk_mail` switch. The mailbox location never leaves the server.
- `backend/mail/htmlview.py`: `no_links` mode (a link becomes a span, no address kept).
- Page: `prototype/index.html` (`junkNav`, `#junkPage`, `renderJunkPage`).

## Find any email (v0.94)

- `backend/mail/find.py`: turns the typed words into IMAP criteria (`TEXT`, or Gmail's `X-GM-RAW`), picks the folders (the "all mail" folder if the service has one, otherwise every normal folder; Spam and Bin only when asked) and runs a search as a short-lived job in server memory. A job keeps folder and message numbers only. Each mailbox searches on its own thread with a long socket timeout, a separate lock (never the sync lock) and a cancel that shuts the socket. Results are ordered newest first by reading the dates of the newest 100 per folder.
- `backend/mail/find_routes.py`: `/api/v1/find/...` start, progress and results, cancel, open original, keep, and the Fast search switches.
- `backend/mail/find_index.py`: the optional word list. An in-memory SQLite full-text index (no copy of the text), serialised, compressed and sealed per person with a key from `vault.derive_key`, loaded after unlock and dropped when the vault locks. A background thread per mailbox builds it newest first in small throttled batches and keeps it current.
- Message locations gain a folder (`FOLDER|<name>|<validity>|<uid>`); old `INBOX|validity|uid` locations are unchanged and read the same way.
- Kept results reuse the quiet `from_all_mail` entries and add `found_until`, so sync, alerts and unread counts already ignore them.

