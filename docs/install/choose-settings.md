# Choose your settings

Enveliq's install file ([`install/docker-compose.yml`](../../install/docker-compose.yml)) needs only one thing from you, the vault key, and it already has safe defaults for everything else. This page is for when you want to change those defaults, mainly to open Enveliq from your phone or another device. Each setting is read from the `.env` file next to the install file (for example `ENVELIQ_PUBLIC_URL=http://192.168.1.50:8765`), or from your panel's environment box.

**The only required setting is the vault key** ([Setting 4](#setting-4-the-vault-key-required)); your install guide already shows how. Everything else here is optional: read it only if you want to open Enveliq from your phone or another device. Nothing is permanent: you can change any of it later and redeploy.

- [Setting 1: the address you will type in your browser](#setting-1-the-address-you-will-type-in-your-browser)
- [Setting 2: the one-time setup code (optional)](#setting-2-the-one-time-setup-code-optional)
- [Setting 3: the "plain http" switch](#setting-3-the-plain-http-switch)
- [The port line](#the-port-line)
- [Setting 4: the vault key (required)](#setting-4-the-vault-key-required)

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

## Setting 2: the one-time setup code (optional)

**You can skip this setting.** The very first time you open Enveliq it asks for a setup code, which proves the person setting up Enveliq is you. Enveliq makes the code itself the first time it starts. Read it with:

```
docker exec enveliq cat /data/setup-code.txt
```

(In a control panel, open the `enveliq` container's **Console** and run `cat /data/setup-code.txt`. See [I do not know the setup code](troubleshooting.md#i-do-not-know-the-setup-code).)

If you would rather choose your own, put `ENVELIQ_SETUP_CODE=your-code` in the `.env` file: at least 20 random letters and numbers. After setup is finished the code does nothing and can be forgotten.

## Setting 3: the "plain http" switch

In the file this is `ENVELIQ_ALLOW_INSECURE_PUBLIC_URL`.

- Address **A**, **C** or **D**: leave it as `""` (two quote marks, nothing between).
- Address **B** (`http://192.168...`): change it to `"1"`. This tells Enveliq "yes, I know this is plain http, it is my own home network".

## The port line

In the file this is the line `- "8765:8765"`. You do not need to change it.

- It lets other devices on your network open Enveliq (address **B**, or a reverse proxy on another machine). Address **A** and **C** work with it too.
- To let **only the computer Enveliq runs on** open it, change it to `- "127.0.0.1:8765:8765"`.

Whichever you choose, **do not** forward port 8765 on your router. That would open it to the whole internet.

## Setting 4: the vault key (required)

Everything Enveliq keeps is locked with a **vault key**, and Enveliq unlocks itself with it after every restart. Make the key **before** you start Enveliq:

1. Make one:

   ```
   docker run --rm alpine sh -c "head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'; echo"
   ```

2. Save it in your password manager **now**. Without it your data cannot be opened if the install file is ever lost.
3. In the install file, find the line `ENVELIQ_VAULT_KEY: "${ENVELIQ_VAULT_KEY:-}"` and replace `${ENVELIQ_VAULT_KEY:-}` with your key (or put `ENVELIQ_VAULT_KEY=your-key` in a `.env` file next to the install file, as the [install page](README.md) does):

   ```
         ENVELIQ_VAULT_KEY: "9f2c...your key here..."
   ```

Anyone who can read your install file can read the key, so keep the file private. If you forget this step, the setup page tells you what to do. [The vault key guide](../VAULT_KEY.md) has more, including the stronger "key file" option.

## Ready?

Go back to your guide in [Install Enveliq](README.md).
