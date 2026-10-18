# Install Enveliq

One page, about five minutes. You do not need to know Linux or Docker.

## 1. What you need

- A computer that can stay switched on (a spare PC, mini PC, NAS, or a Mac or Windows PC to try it). 2 GB of free memory.
- **Docker.** On Windows or Mac install [Docker Desktop](https://www.docker.com/products/docker-desktop/) (accept the defaults, start it, wait for **Engine running**). On Linux run `curl -fsSL https://get.docker.com | sh`.
- An email account to connect afterwards (Gmail, Outlook, iCloud, Yahoo, Fastmail, Proton with Proton Bridge, or any IMAP service).

Raspberry Pi and other ARM computers build Enveliq themselves: see [Raspberry Pi](raspberry-pi.md).

## 2. Install: copy, paste, done

Open a terminal (on Windows, **PowerShell**), paste this whole block and press Enter. It downloads the install file, makes your **vault key**, and starts Enveliq.

**Mac or Linux**

```
mkdir enveliq && cd enveliq
curl -fsSL https://raw.githubusercontent.com/jlnau/enveliq/main/install/docker-compose.yml -o docker-compose.yml
echo "ENVELIQ_VAULT_KEY=$(openssl rand -hex 32)" > .env
docker compose up -d
```

**Windows (PowerShell)**

```
mkdir enveliq; cd enveliq
curl.exe -fsSL https://raw.githubusercontent.com/jlnau/enveliq/main/install/docker-compose.yml -o docker-compose.yml
$b = New-Object byte[] 32; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
"ENVELIQ_VAULT_KEY=" + (($b | ForEach-Object { $_.ToString("x2") }) -join "") | Out-File -Encoding ascii .env
docker compose up -d
```

The first time it downloads Enveliq, which takes a few minutes.

## 3. Save your vault key

The vault key locks everything Enveliq keeps and unlocks it after every restart. It is in the `.env` file you just made. **Copy it into your password manager now.** If that file is ever lost, the key is the only way to open your data again.

```
cat .env          # Windows: type .env
```

## 4. Open Enveliq

Open <http://localhost:8765> in your browser. It asks for a **setup code** once. Read it with:

```
docker exec enveliq cat /data/setup-code.txt
```

Then follow [First-time setup](after-install.md): your administrator account and two-factor sign-in. If the page says it needs a vault key instead, see [Troubleshooting](troubleshooting.md#setup-says-it-needs-a-vault-key).

## Using a control panel or a NAS instead?

You can paste the same install file into your panel. The only thing to set is the vault key: make one with the commands above (or have your password manager make a 64-character password of letters and numbers), then put it in the `ENVELIQ_VAULT_KEY` line, or in the panel's environment box. The guides show where to click:

[Docker Desktop](docker-desktop.md) · [Docker Compose on Linux](docker-compose.md) · [Arcane](arcane.md) · [Portainer](portainer.md) · [Dockge](dockge.md) · [Synology](synology.md) · [Unraid](unraid.md) · [TrueNAS](truenas.md) · [Proxmox](proxmox.md) · [Raspberry Pi](raspberry-pi.md)

## Open it from your phone or another device (optional)

By default Enveliq opens only on the computer it runs on. To open it from your phone or over the internet, see [Choose your settings](choose-settings.md) and [How should I open Enveliq?](../ACCESS.md).

## After it is installed

1. [**First-time setup**](after-install.md): the one-time code, your administrator account, two-factor sign-in.
2. [**Connect your email**](after-install.md#step-4-connect-your-email) (Gmail, Outlook, iCloud, Yahoo, Proton and others).
3. [**Open Enveliq from your phone and other devices**](../ACCESS.md).
4. [**Turn on AI summaries**](../AI_SUMMARIES.md).
5. [**Notifications, webhooks and news feeds**](notifications.md): let Home Assistant and other services send notes, and follow websites.
6. [**Back up, update and uninstall**](maintenance.md).

If anything goes wrong, [Troubleshooting](troubleshooting.md) lists the common problems and the fix for each.

## Good to know before you start

- **Images are for ordinary 64-bit Intel or AMD computers.** Raspberry Pi and other ARM computers build Enveliq themselves, which the [Raspberry Pi guide](raspberry-pi.md) walks through. Apple-silicon Macs run the ordinary image through Docker's built-in translation; if that gives trouble, use the Raspberry Pi guide's build method.
- **Your data stays on your computer.** Everything Enveliq keeps is encrypted in one Docker volume called `enveliq-data`. [Maintenance](maintenance.md) shows how to back it up.
- **You can undo everything.** Removing Enveliq removes only Enveliq.
