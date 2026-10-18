# Choose your settings

The install file ([`install/docker-compose.yml`](../../install/docker-compose.yml)) has **three lines** you may need to change. They are marked `<-- CHANGE THIS`. Everything else stays as it is.

Read this page once, decide your answers, and then go back to your guide. Nothing here is permanent: you can change any of it later and redeploy.

- [Setting 1: the address you will type in your browser](#setting-1-the-address-you-will-type-in-your-browser)
- [Setting 2: the one-time setup code](#setting-2-the-one-time-setup-code)
- [Setting 3: the "plain http" switch](#setting-3-the-plain-http-switch)
- [The port line](#the-port-line)
- [Optional: let Enveliq unlock itself after a restart](#optional-let-enveliq-unlock-itself-after-a-restart)

## Setting 1: the address you will type in your browser

This is the web address you type to open Enveliq. In the file it is the line `ENVELIQ_PUBLIC_URL`. Enveliq only answers to this exact address, which is one of the ways it keeps strangers out.

Pick **one** row. If you are not sure, pick **A**.

| | Who can open it | What you put | The other two lines |
|---|---|---|---|
| **A. Only this computer** | Just you, on the computer that runs Enveliq. The safest. | `http://localhost:8765` | Leave both as they are. |
| **B. My home Wi-Fi** | Any phone or computer on your home network. | `http://` + your computer's number + `:8765`, for example `http://192.168.1.50:8765`. [How to find the number.](#how-to-find-your-computers-number) | Setting 3 = `1`. |
| **C. Anywhere, privately (recommended for families)** | Only your own devices, even away from home, with a padlock (https). Needs a free Tailscale account. | The `https://...ts.net` address Tailscale gives you. | Leave setting 3 as `""`. |
| **D. My own web address** | Anyone you allow, with a padlock (https). Needs a domain name and a reverse proxy. | `https://enveliq.example.com` | Leave setting 3 as `""`. |

For **C** and **D**, follow [How should I open Enveliq?](../ACCESS.md). It has step-by-step guides for Tailscale, Nginx Proxy Manager, Cloudflare Tunnel, Caddy, Traefik and Nginx.

**What you give up with B.** On a home network with plain `http`, nothing is padlocked, so someone who could watch your network traffic could read your password as you sign in. Email is still encrypted on its way to your mail provider and in storage. Passkeys and "Sign in with Microsoft" do **not** work on plain `http`. Never forward a port on your router to Enveliq. If any of that worries you, use C. More detail: [Opening Enveliq on your network](../NETWORK_ACCESS.md).

### How to find your computer's number

You need this only for option B. It looks like `192.168.1.50` (four numbers with dots).

- **Windows:** press the Windows key, type `cmd`, press Enter. Type `ipconfig` and press Enter. Look for **IPv4 Address**.
- **Mac:** open **System Settings**, **Wi-Fi**, click **Details** beside your network, and look for **IP address**.
- **Linux:** open a terminal and type `hostname -I`. The first number is the one.
- **A NAS (Synology, Unraid, TrueNAS):** it is shown on the NAS's own home or network page.

**Tip:** ask your router to always give this computer the same number (it is called a "DHCP reservation" or "static lease"). If the number changes, the address you set will stop working.

## Setting 2: the one-time setup code

In the file this is `ENVELIQ_SETUP_CODE`. The very first time you open Enveliq it asks for this code. It proves the person setting up Enveliq is you and not someone else who found the page.

1. Make up a code that is **long and random**: at least 20 letters and numbers. A password manager's "generate password" button is perfect. Or ask Docker to make one:

   ```
   docker run --rm alpine sh -c "head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n'; echo"
   ```

   It prints something like `9f2c1e7a4b6d03885c2e1f77a9b04d6e51c8a3f2d7b09e41`. Use that.
2. Replace `CHANGE-ME-make-this-long-and-random` in the file with your code, keeping the quote marks.
3. Write it down for a minute: you type it once, on the first screen.

After setup is finished the code does nothing and can be forgotten. You can delete the line afterwards.

> **If you leave the placeholder:** newer versions of Enveliq ignore the placeholder and make a random code themselves. Then see [How to find the setup code](troubleshooting.md#i-do-not-know-the-setup-code).

## Setting 3: the "plain http" switch

In the file this is `ENVELIQ_ALLOW_INSECURE_PUBLIC_URL`.

- Address **A**, **C** or **D**: leave it as `""` (two quote marks, nothing between).
- Address **B** (`http://192.168...`): change it to `"1"`. This tells Enveliq "yes, I know this is plain http, it is my own home network".

## The port line

In the file this is the line `- "8765:8765"`. You do not need to change it.

- It lets other devices on your network open Enveliq (address **B**, or a reverse proxy on another machine). Address **A** and **C** work with it too.
- To let **only the computer Enveliq runs on** open it, change it to `- "127.0.0.1:8765:8765"`.

Whichever you choose, **do not** forward port 8765 on your router. That would open it to the whole internet.

## Required: the vault key

Everything Enveliq keeps is locked with a **vault key**, and Enveliq unlocks itself with it after every restart. Make the key **before** you start Enveliq, and put it in the install file or `.env`:

1. Make one:

   ```
   docker run --rm alpine sh -c "head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'; echo"
   ```

2. Save it in your password manager **now**. Without it your data cannot be opened if the install file is ever lost.
3. In the install file, remove the `#` at the start of the `ENVELIQ_VAULT_KEY` line and paste your key between the quote marks (or put `ENVELIQ_VAULT_KEY=your-key` in the `.env` file next to it):

   ```
         ENVELIQ_VAULT_KEY: "9f2c...your key here..."
   ```

Anyone who can read your install file can read the key, so keep the file private. If you forget this step, the setup page tells you what to do. [The vault key guide](../VAULT_KEY.md) has more, including the stronger "key file" option.

## Ready?

Go back to your guide in [Install Enveliq](README.md).
