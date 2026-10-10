# Install Enveliq

This page helps you pick the right guide. You do not need to know Linux or Docker. Every guide below tells you exactly what to click or type, one small step at a time.

**How long it takes:** about 15 to 30 minutes the first time.

## 1. What you need

| You need | Notes |
|---|---|
| A computer that can stay switched on | An old laptop or PC, a small "mini PC", a NAS (Synology, Unraid, TrueNAS), a Raspberry Pi 4 or 5, or a virtual machine. It does not have to be fast. **2 GB of free memory** is plenty. |
| Docker | A free program that runs Enveliq in its own sealed box, so it cannot mess up the rest of your computer. Each guide tells you how to get it if you do not have it. |
| An email account | Any of: Gmail, Outlook/Hotmail/Microsoft 365, iCloud, Yahoo, Fastmail, Proton Mail (with Proton Bridge), or any other service that supports IMAP. You connect it **after** installing. |
| (Optional) An AI model | Enveliq writes its summaries with an AI model. Use a cloud service (OpenAI, Anthropic, Google Gemini and others) or a model running on your own network. You can add this later, inside the app. |

You do **not** need a domain name, a credit card, or an account with us. Enveliq collects nothing and sends nothing anywhere you did not set up yourself.

## 2. Pick your guide

Choose the one that matches **what you already have**. If you are not sure, use the first row.

| What you have | Guide |
|---|---|
| **A Windows PC or a Mac** (the easiest way to try it) | [Docker Desktop on Windows or Mac](docker-desktop.md) |
| **A Linux computer or server** (Ubuntu, Debian and others), or a virtual machine | [Docker Compose on Linux](docker-compose.md) |
| **A Raspberry Pi** or another ARM computer | [Raspberry Pi and ARM](raspberry-pi.md) |
| **A Proxmox server** | [Proxmox](proxmox.md) |
| **Arcane** (a Docker control panel) | [Arcane](arcane.md) |
| **Portainer** (a Docker control panel) | [Portainer](portainer.md) |
| **Dockge** (a Docker control panel) | [Dockge](dockge.md) |
| **A Synology NAS** | [Synology](synology.md) |
| **Unraid** | [Unraid](unraid.md) |
| **TrueNAS SCALE** | [TrueNAS](truenas.md) |

Every guide uses the same ready-made install file: [`install/docker-compose.yml`](../../install/docker-compose.yml). Only three lines in it ever need changing, and [Choose your settings](choose-settings.md) explains each one in plain words. Read that page once; every guide links to it at the right moment.

## 3. After it is installed

1. [**First-time setup**](after-install.md): the one-time code, your administrator account, two-factor sign-in.
2. [**Connect your email**](after-install.md#step-4-connect-your-email) (Gmail, Outlook, iCloud, Yahoo, Proton and others).
3. [**Open Enveliq from your phone and other devices**](../ACCESS.md).
4. [**Turn on AI summaries**](../AI_SUMMARIES.md).
5. [**Back up, update and uninstall**](maintenance.md).

If anything goes wrong, [Troubleshooting](troubleshooting.md) lists the common problems and the fix for each.

## Good to know before you start

- **Images are for ordinary 64-bit Intel or AMD computers.** Raspberry Pi and other ARM computers build Enveliq themselves, which the [Raspberry Pi guide](raspberry-pi.md) walks through. Apple-silicon Macs run the ordinary image through Docker's built-in translation; if that gives trouble, use the Raspberry Pi guide's build method.
- **Your data stays on your computer.** Everything Enveliq keeps is encrypted in one Docker volume called `enveliq-data`. [Maintenance](maintenance.md) shows how to back it up.
- **You can undo everything.** Removing Enveliq removes only Enveliq.
