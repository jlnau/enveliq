# Settings reference: every environment variable

Enveliq reads a few settings from its install file (the `environment:` part of `docker-compose.yml`, or a `.env` file next to it). Most people only ever change three. Everything else here is optional, and almost all of it can also be set inside the app.

**Passwords, access keys and tokens do not belong here.** Mail passwords and AI keys are typed into the app and stored encrypted. The only secrets in this list are the setup code and the vault key, and both are explained below.

After you change a setting, restart Enveliq so it reads it: `docker compose up -d`.

## The three you set first

| Setting | What it does | Default |
| --- | --- | --- |
| `ENVELIQ_PUBLIC_URL` | The web address you type to open Enveliq. Passkeys, single sign-on and Microsoft sign-in are tied to it. It must start with `https://` unless it is `localhost`. | `http://localhost:8765` |
| `ENVELIQ_SETUP_CODE` | A one-time code you type on the very first screen to prove you are the person setting Enveliq up. 16 or more characters. A short one or one containing "change-me" is ignored, and a random one is written to `setup-code.txt` in the data folder instead. | made up for you |
| `ENVELIQ_ALLOW_INSECURE_PUBLIC_URL` | Set to `1` only if you open Enveliq with `http://` on a home network (not `localhost`). Passwords then travel unencrypted. See [Use it without https](NETWORK_ACCESS.md). | off |

## Where it listens

| Setting | What it does | Default |
| --- | --- | --- |
| `ENVELIQ_PORT` | The port Enveliq listens on inside its container. | `8765` |
| `ENVELIQ_BIND` | The address it listens on inside the container. The Docker image sets this for you. | `0.0.0.0` in Docker |
| `ENVELIQ_ALLOW_NON_LOOPBACK` | Allows listening on more than this computer. The Docker image sets it. Only safe behind HTTPS or on a network you trust. | `1` in Docker |
| `ENVELIQ_PUBLISH` | Used by the repository's `docker-compose.yml`: which address the port is published on. `0.0.0.0` opens it to your network. | `127.0.0.1` |
| `ENVELIQ_ALLOWED_HOSTS` | The host names Enveliq answers to, separated by commas. Worked out from `ENVELIQ_PUBLIC_URL`; you rarely need this. | from the public address |
| `ENVELIQ_PUSH_RELAY` | The address of the push relay that wakes the Enveliq Android app for Google push alerts (`https://...`). The official Enveliq images already have it; you only set it if you run your own relay (see `docs/PUSH_RELAY.md`). Empty means Google push is not offered. | empty (set in official images) |
| `ENVELIQ_ALLOWED_ORIGINS` | The origins the page may call from. Also worked out from the public address. | from the public address |
| `ENVELIQ_COOKIE_SECURE` | `1` or `0`: whether the sign-in cookie is marked secure. | `1` for `https://` addresses |
| `ENVELIQ_MAX_JSON_BYTES` | Largest request the server accepts, in bytes. | 1 MB |

## Your data and locking

| Setting | What it does | Default |
| --- | --- | --- |
| `ENVELIQ_DATA_DIR` | Where Enveliq keeps its encrypted data. In Docker this is the `enveliq-data` volume mounted at `/data`. | `/data` in Docker |
| `ENVELIQ_VAULT_KEY` | A 64-character key that lets Enveliq unlock itself after a restart. Make one with `openssl rand -hex 32` and keep a copy somewhere safe: without it the data cannot be opened. Leave it out to type a passphrase after each restart. See [Unlock by itself](VAULT_KEY.md). | not set |
| `ENVELIQ_VAULT_KEY_FILE` | The same, kept in a file outside the data volume. Wins over `ENVELIQ_VAULT_KEY` if both are set. | not set |
| `ENVELIQ_KEY_DIR` | Used by the repository's `docker-compose.yml`: the folder on your computer mounted at `/keys` for the key file. | `/opt/enveliq/keys` |
| `ENVELIQ_IDLE_LOCK_SECONDS` | Seconds with no activity before Enveliq locks itself. | `1800` |
| `ENVELIQ_SESSION_TTL_SECONDS` | Seconds before a sign-in session ends. | `1800` |

## Email

| Setting | What it does | Default |
| --- | --- | --- |
| `ENVELIQ_SYNC_MINUTES` | Minutes between checks for new mail. At least 2; `0` turns it off. A value here overrides the one in Administration, Automatic sync. | `10` |
| `ENVELIQ_MAIL_ALLOWED_HOSTS` | If set, Enveliq contacts only these mail servers (IMAP and SMTP names, separated by commas). They may be on your own network. If empty, only public mail servers on the standard secure ports are used. See [Email services](EMAIL_SERVICES.md). | empty |
| `ENVELIQ_MAIL_CA_FILE` | An extra certificate to trust for a mail server with a private certificate authority. | not set |
| `ENVELIQ_BRIDGE_ALLOWED_HOSTS` | Proton Mail Bridge hosts Enveliq may contact. If empty, any private or local address is allowed. The repository's `docker-compose.yml` sets it from `ENVELIQ_BRIDGE_HOST`. | empty |
| `ENVELIQ_BRIDGE_CA_FILE` | The certificate exported from Bridge. Enveliq trusts only this one. See [Proton Mail](PROTON_BRIDGE.md). | `/etc/enveliq/proton-bridge.crt` |
| `ENVELIQ_BRIDGE_HOST`, `ENVELIQ_BRIDGE_CERT` | Used by the repository's `docker-compose.yml`: the Bridge machine's address, and where its certificate is on your computer. | `172.30.0.1`, `/opt/enveliq/proton-bridge.crt` |
| `ENVELIQ_RENDER_URL` | Where the PDF drawing and reading program is. Keep it as the install file has it: `http://enveliq-render:8766`. | set in the install file |
| `ENVELIQ_RENDER_PORT` | The port that program listens on (it is a separate container). | `8766` |

## AI

All of these can be set in the app instead (Administration, AI model). If you set them here, they win over the app. See [AI summaries](AI_SUMMARIES.md).

| Setting | What it does | Default |
| --- | --- | --- |
| `ENVELIQ_LLM_URL` | The address of your AI model, for example `http://192.168.1.10:8088/v1/chat/completions`. Leave empty to keep AI off. | empty |
| `ENVELIQ_LLM_MODEL` | The model's name. | empty |
| `ENVELIQ_LLM_API_KEY` | Only if the server wants a key. | empty |
| `ENVELIQ_LLM_PROVIDER` | Only for a cloud service: `openai`, `anthropic`, `gemini`, `openrouter`, `groq`, `mistral`, `xai`, `deepseek` or `together`. Leave out for a server on your network. | empty |
| `ENVELIQ_LLM_ALLOWED_HOSTS` | If set, only these AI hosts are contacted. If empty, any private or local address is allowed. | empty |

## Sign-in, reminders and reporting

| Setting | What it does | Default |
| --- | --- | --- |
| `ENVELIQ_OIDC_ALLOW_HTTP` | `1` allows a single sign-on provider that uses `http://`. Not recommended. | `0` |
| `ENVELIQ_NOTIFY_ALLOWED_HOSTS` | Services on your own network that reminders, calendars and to-do lists may call (host names, addresses or networks, separated by commas). Anything else on a private network is refused. | empty |
| `ENVELIQ_VAPID_SUBJECT` | The contact address sent with browser push notifications. | made up for you |
| `ENVELIQ_REPORT_ALLOWED_HOSTS` | If set, reports (for Grafana and others) may only be sent to these hosts. | empty |
| `ENVELIQ_CHECK_PASSWORD` | Used only by the command-line mailbox check tool, so it does not ask. | not set |

## Not sure which ones you need?

Start with the install file and [Choose your settings](install/choose-settings.md). The three at the top are enough for most homes.
