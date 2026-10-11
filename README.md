<p align="center">
  <img src="brand/enveliq-logo-full.png" alt="Enveliq" width="360">
</p>

<h3 align="center">Turn email into clarity.</h3>

<p align="center">
  A private email assistant that runs on your own computer.<br>
  It reads your inbox for you, tells you what needs a reply, and keeps everything else out of your way.
</p>

<p align="center">
  <a href="docs/install/README.md"><b>Install it</b></a> ·
  <a href="#what-you-get">What you get</a> ·
  <a href="#install">Install options</a> ·
  <a href="#questions">Questions</a> ·
  <a href="docs/README.md">All guides</a>
</p>

<p align="center"><img src="docs/images/home.png" alt="The Enveliq home page: a short list of email, and a card asking whether a parcel has arrived" width="760"></p>

---

## Why Enveliq?

Email piles up. Most of it does not matter, but a few messages do: the bill due on Friday, the school form, the parcel that has not arrived, the question someone is waiting for you to answer. Finding those few means opening every message.

Enveliq does that sorting for you, calmly and in plain words, and **it does it on your own computer, not in somebody else's cloud.**

- **Know what needs you.** Each email gets a short summary and a clear label. Things that need action are pulled to the top. The rest can wait.
- **Nothing falls through the cracks.** Enveliq keeps a list of tasks it found in your email, parcels on their way, and emails where you are still waiting for an answer.
- **Calm by design.** Plain words, no clutter and big, clear buttons. It was designed to be easy on anyone who finds a full inbox stressful.
- **Private by design.** Your email is never copied into Enveliq. It stores only short, encrypted summaries, on your own machine. There is no account with us, no tracking and no ads. [How that works](#your-privacy)
- **For the whole household.** Everyone gets their own sign-in and their own private view. Nobody, administrators included, can read another person's mail.
- **You choose the AI.** Use a cloud AI service, or run one on your own network so that nothing leaves your home.

## What you get

| | |
|---|---|
| **Summaries** | A one or two line summary of every email, written by the AI you choose and always labelled as AI. |
| **Needs action** | Emails that want something from you float to the top. |
| **Tasks** | Things to do, found in your email, with due dates. You can send them to your calendar or to-do list. |
| **Shipping** | Your online orders followed from the emails you get, with a simple "Did it arrive?" |
| **Waiting for reply** | Reminds you of emails you sent that nobody has answered. |
| **Attachments** | Summaries of PDFs and other attachments, and a safe preview. The files themselves are never kept. |
| **Writing help** | Optional. The AI suggests a reply, or checks one you wrote. It only suggests: you decide what is sent. |
| **Reminders** | Gentle nudges by browser notification, email or Home Assistant. |
| **Messages** | A small private chat between the people in your household. |
| **Be careful flag** | A calm note on an email that looks like a scam, in plain words, so you do not have to judge. |
| **Unsubscribe** | One button to leave a mailing list, when the sender allows it. |
| **Many mailboxes** | Gmail, Outlook and Microsoft 365, iCloud, Yahoo, Fastmail, Proton Mail (through Proton Bridge) and any other IMAP service. Replies work with alias services such as Proton Pass and SimpleLogin. |

<p align="center">
  <img src="docs/images/shipping.png" alt="The Shipping page, with an order shown as Ordered, Shipped, Out for delivery and Delivered" width="48%">
  <img src="docs/images/writing-help.png" alt="The reply box, with a suggestion from the AI labelled 'Suggested by AI'" width="48%">
</p>

*The pictures use made-up example data.*

## Install

You do **not** need to know Linux or Docker. Every guide below tells you exactly what to click or type, one small step at a time. Plan on about 15 to 30 minutes.

**The short version** (Windows, Mac or Linux, with [Docker](https://www.docker.com/get-started/) installed):

1. Download [`install/docker-compose.yml`](install/docker-compose.yml).
2. Open it in any text editor and change the three lines marked `<-- CHANGE THIS` ([what to put](docs/install/choose-settings.md)).
3. Start it with `docker compose up -d`, then open **http://localhost:8765**.

**Pick the guide that matches what you have:**

| What you have | Guide |
|---|---|
| A Windows PC or a Mac | [**Docker Desktop**](docs/install/docker-desktop.md) (the easiest way to try it) |
| A Linux computer or server | [**Docker Compose on Linux**](docs/install/docker-compose.md) |
| A Raspberry Pi | [**Raspberry Pi and ARM**](docs/install/raspberry-pi.md) |
| A Proxmox server | [**Proxmox**](docs/install/proxmox.md) |
| Arcane | [**Arcane**](docs/install/arcane.md) |
| Portainer | [**Portainer**](docs/install/portainer.md) |
| Dockge | [**Dockge**](docs/install/dockge.md) |
| A Synology NAS | [**Synology**](docs/install/synology.md) |
| Unraid | [**Unraid**](docs/install/unraid.md) |
| TrueNAS SCALE | [**TrueNAS**](docs/install/truenas.md) |

Not sure? Start at [**Install Enveliq**](docs/install/README.md), which also lists what you need. Something not working? See [**Troubleshooting**](docs/install/troubleshooting.md).

## After you install

1. [**First-time setup**](docs/install/after-install.md): the one-time code, your administrator account and two-factor sign-in.
2. [**Connect your email**](docs/install/after-install.md#step-4-connect-your-email).
3. [**Turn on AI summaries**](docs/AI_SUMMARIES.md).
4. [**Open Enveliq on your phone**](docs/ACCESS.md) from anywhere, privately, with Tailscale or your own web address.
5. [**Add the other people in your home**](docs/install/after-install.md).
6. [**Update, back up and uninstall**](docs/install/maintenance.md).

## Your privacy

- **Raw emails and attachments are never stored.** Enveliq keeps only short summaries and structured results, encrypted.
- **Everything is locked in an encrypted vault** (AES-256-GCM, with the key protected by Argon2id) on your own machine.
- **One person's mail is never visible to another person**, and administrators run Enveliq without reading anyone's mail.
- **Email is treated as untrusted.** The AI is told that email text is only data, is given no tools, and never decides or calculates anything. Anything the AI wrote is labelled as AI.
- **Strong sign-in.** Passwords use Argon2id, with authenticator-app and passkey two-factor, recovery codes and single sign-on (Authentik, Authelia, Keycloak or any OpenID Connect service).
- **No telemetry, no third-party requests.** The pages load nothing from other websites, and the author receives no data.

The full details are in [SECURITY.md](SECURITY.md) and the plain-language [privacy notes](docs/PRIVACY.md).

## Questions

<details>
<summary><b>Is it free?</b></summary>

Yes. Enveliq is free, open-source software under the [MIT licence](LICENSE). You may need to pay for an AI service if you choose a cloud one; running a model on your own network costs nothing.
</details>

<details>
<summary><b>Do I need an AI account?</b></summary>

Enveliq works best with an AI model to write the summaries. You can use a cloud service (OpenAI, Anthropic, Google Gemini and others) or a model on your own network. You can install first and add the AI later. See [AI summaries](docs/AI_SUMMARIES.md).
</details>

<details>
<summary><b>Can the AI see my email?</b></summary>

The AI you choose reads an email in order to write its summary. With a cloud AI service, that email text goes to that service, under its own privacy terms. If that matters to you, use a model running on your own network and nothing leaves your home. Enveliq itself keeps only the summary.
</details>

<details>
<summary><b>Can it send or delete my email?</b></summary>

It can send a reply, but only when you press Send. It never sends, deletes or changes anything on its own, and the AI cannot do any of those things.
</details>

<details>
<summary><b>Do I have to open it to the internet?</b></summary>

No, and by default you should not. You can use it on one computer, on your home network, or privately from anywhere with a free [Tailscale](docs/ACCESS.md) account. Never forward a port on your router to Enveliq.
</details>

<details>
<summary><b>What if I forget my password or lose my phone?</b></summary>

Two-factor sign-in gives you ten one-time recovery codes. Keep them somewhere safe. See [First-time setup](docs/install/after-install.md) and [Troubleshooting](docs/install/troubleshooting.md).
</details>

<details>
<summary><b>Which computers does it run on?</b></summary>

Any computer that can run Docker: Windows, Mac, Linux, a NAS, a mini PC, a Proxmox server or a Raspberry Pi 4 or 5. The ready-made images are for ordinary 64-bit Intel or AMD computers; ARM computers build their own, which the [Raspberry Pi guide](docs/install/raspberry-pi.md) shows.
</details>

<details>
<summary><b>How do I get help, or report a problem?</b></summary>

Start with [Troubleshooting](docs/install/troubleshooting.md). If that does not solve it, open an issue on this page. Please do not paste real email, passwords or keys into an issue. To report a security problem, see [SECURITY.md](SECURITY.md).
</details>

## More guides

All the guides are listed, by what you want to do, in the [**documentation index**](docs/README.md). Some popular ones:
[Opening Enveliq from outside your home](docs/ACCESS.md) ·
[Single sign-on](docs/SSO.md) ·
[Outlook and Microsoft 365](docs/MICROSOFT.md) ·
[Proton Mail](docs/PROTON_BRIDGE.md) ·
[Calendar and to-do lists](docs/CALENDAR.md) ·
[Reminders](docs/NOTIFICATIONS.md) ·
[Writing help](docs/WRITING_HELP.md) ·
[The Be careful flag](docs/SCAM_WARNING.md).

## Version history

<details>
<summary><b>What changed recently</b> (latest five versions)</summary>

- **v0.66**: **A "Be careful" flag for emails that look like a scam.** When an email looks odd, such as a link that says paypal.com but goes somewhere else, a link to a number instead of a website name, a link that copies a well-known name, a sender called "PayPal" writing from an unrelated address, or a sender your email provider could not confirm, its row gets a small **Be careful** label and its card gets a calm note in plain words that lists exactly what looks odd. Nothing is blocked and nothing is judged for you. On a flagged email the **Unsubscribe** button asks once more first, because unsubscribing from a scam tells the sender your address is real. The checks are plain code, never the AI, and only website names are ever kept, never a whole link. Ordinary newsletters with tracking links are deliberately left alone. See [docs/SCAM_WARNING.md](docs/SCAM_WARNING.md).
- **v0.65**: **Help is one click away.** Wherever Enveliq asks you to set something up, there is now a link to the step-by-step guide on GitHub, which opens in a new tab: first-time setup, unlocking, two-factor sign-in, adding people, the AI model, connecting a mailbox (Gmail, iCloud, Yahoo, Outlook and Microsoft 365, Proton Mail), Google Calendar and other calendars, reminders, the Hermes agent, reporting, single sign-on, writing help, and the warning that shows when a page is not encrypted. Pointers that used to say "see docs/... in the Enveliq folder" are now links. A setup code that is still the placeholder from the install file, or shorter than 16 characters, is ignored and a random one is made instead.
- **v0.64**: **Writing help.** The reply box and the New email box get a button: **Write a reply for me** when the box is empty, **Check my reply** when you have written something. The AI reads your words and, for a reply, the email you are answering, and shows its suggestion in a separate box labelled **Suggested by AI** that says nothing in it is sent. **Accept** copies it into your box (with **Put my version back**), or you can select just the parts you like and copy them across; **Try again** and **Copy** are there too. What is in your own box is what gets sent. If you used writing help on a message, pressing Send first shows a short check with the exact text, and warns about any gap left in [square brackets]; ordinary replies are not slowed. It is **off until you turn it on** in **Settings, AI instructions**, where a box of plain, friendly default writing instructions is ready for you to keep, change or add to. **Administration, Features** has a Writing help switch. Nothing the AI sees or writes is stored or logged. See [docs/WRITING_HELP.md](docs/WRITING_HELP.md).
- **v0.63**: **Administrators can edit saved shipping carriers.** In Shipping, under *Carriers Enveliq can link to*, an administrator now sees **Edit** next to each shared carrier and can fix its name or tracking-page address (the same address rules as when adding). Everyone else sees no change.
- **v0.62**: **Shipping: Track all, Copy number and carriers you can add.** When two or more parcels are on their way, **Track all** opens each one in its carrier's own page (if only one opens, allow pop-ups for Enveliq). Every parcel with a tracking number has a **Copy number** button. The built-in carrier list grew (Couriers Please, TNT, DPD, Evri, Yodel), and when a parcel's carrier has no link, **Add this carrier** lets anyone teach Enveliq its tracking page: paste the address from the carrier's website with `{number}` where the tracking number goes (or type the parcel's number and Enveliq finds it). A carrier added by one person is available to everyone; the person who added it, or an administrator, can remove it. Enveliq still never contacts a carrier: your own browser opens the page.

The full list is in [docs/VERSION_HISTORY.md](docs/VERSION_HISTORY.md), and a more technical one is in the [change log](docs/CHANGELOG.md).
</details>

Current version: **v0.66**

## For developers

<details>
<summary><b>Run without Docker, tests and repository layout</b></summary>

### Run without Docker

```bash
pip install -r requirements.txt
python run.py
```

It listens on `http://localhost:8765` and keeps its data in `data/`. Without `ENVELIQ_SETUP_CODE` the setup code is written to `data/setup-code.txt` (and the server log tells you where).

### Build the image yourself

```bash
cp .env.example .env            # set ENVELIQ_PUBLIC_URL to your address
docker compose up -d --build
docker compose exec enveliq cat /data/setup-code.txt
```

The repository's own `docker-compose.yml` builds from the source here. The ready-made install file for everyone else is [`install/docker-compose.yml`](install/docker-compose.yml). Architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

### Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

Browser checks need Node.js and Playwright with Chromium (`npm install playwright && npx playwright install chromium`):

```bash
node scripts/check_prototype_injection.mjs   # hostile email content cannot run code in the inbox page
scripts/run_signin_e2e.sh                     # setup, authenticator app, passkeys, sign-in, admin pages
```

The full list of checks is in `.github/workflows/ci.yml`.

### Repository layout

| Path | What it is |
| --- | --- |
| `backend/` | Python/FastAPI server: encrypted vault, mailbox and message API, attachment preview store |
| `backend/auth/` | Accounts, passwords, TOTP, recovery codes, passkeys, OpenID Connect, sign-in API |
| `backend/mail/` | Mail fetching, AI summaries, tasks, shipping, writing help, reminders |
| `web/` | Sign-in, Settings and Administration pages (strict Content Security Policy) |
| `prototype/index.html` | The main inbox page |
| `install/` | Ready-made install files for everyone who is not building from source |
| `tests/` | Test suite (`pytest -q`) |
| `scripts/` | Browser checks and helper scripts |
| `docs/` | Guides: [index](docs/README.md) |
| `brand/` | Enveliq logo files |
| `Dockerfile`, `docker-compose.yml` | Container image and the source-building compose setup |
| `SECURITY.md`, `SECURITY_TEST_RESULTS.md` | Security model, review findings and latest test run |

</details>

## Licence

Enveliq is free, open-source software under the MIT licence ([LICENSE](LICENSE)). There is no telemetry and the author receives no data. Plain-language [terms of use](docs/TERMS.md) and [privacy notes](docs/PRIVACY.md) are also shown in the app, and are general summaries, not legal advice.
