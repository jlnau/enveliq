# Install Enveliq with Docker Compose on Linux

For a Linux computer or server (Ubuntu, Debian, Fedora and others), or a virtual machine. This guide starts from nothing: you do not need to have used Linux or Docker before.

**You need:** a Linux computer with internet, about 2 GB of free memory, and about 20 minutes. You need to be able to type commands on it, either by sitting at it or from another computer using SSH.

## The install file

This is the whole file. Copy it, or [download it](../../install/docker-compose.yml). [Step 3](#step-3-change-the-three-lines) shows the lines to change. The steps below start from nothing and put it on your computer.

<!-- include: install/docker-compose.yml -->

## What is a "terminal"?

A terminal is a window where you type commands. Everything in this guide that is in a grey box is a command: type it (or copy and paste it) and press **Enter**.

- If you are sitting at the Linux computer: open the **Terminal** program.
- If it is a server in a cupboard: from another computer, open a terminal (Windows: **Windows Terminal** or **PowerShell**; Mac: **Terminal**) and type `ssh YOUR-USERNAME@THE-SERVER'S-NUMBER`, for example `ssh sam@192.168.1.50`. Enter your password when asked. The letters you type for a password do not show: that is normal.

To paste in a terminal, use **Ctrl + Shift + V** (Linux, Windows Terminal) or **Command + V** (Mac).

## Step 1. Install Docker

If you already have Docker (`docker --version` prints a version number), skip to step 2.

1. Install it with Docker's own installer script:

   ```
   curl -fsSL https://get.docker.com | sudo sh
   ```

   (This is Docker's official script. If you would rather follow Docker's step-by-step page for your Linux, it is at <https://docs.docker.com/engine/install/>.)

2. Let your user run Docker without typing `sudo` every time:

   ```
   sudo usermod -aG docker $USER
   ```

3. **Log out and back in** (or close the terminal and open a new one, or reconnect with SSH). This step matters.
4. **Check:** type this. It should print a version number for both:

   ```
   docker --version
   docker compose version
   ```

## Step 2. Download the install file

```
mkdir -p ~/enveliq
cd ~/enveliq
curl -fsSL -o docker-compose.yml https://raw.githubusercontent.com/jlnau/enveliq/main/install/docker-compose.yml
```

**Check:** `ls` lists `docker-compose.yml`.

## Step 3. Change the four lines

### Make your vault key (required)

The vault key is a long secret that locks everything Enveliq keeps. Enveliq will not finish setup without one. Make it now, **before** you start Enveliq. Use whichever way is easiest:

- **In a terminal** (on Mac or Linux): `openssl rand -hex 32`
- **In a terminal anywhere Docker runs, including Windows:**

  ```
  docker run --rm alpine sh -c "head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'; echo"
  ```

- **No terminal?** In your password manager (Bitwarden, 1Password and others) make a new password that is **64 characters, letters and numbers only**.

Either way you get one long line of letters and numbers. **Save it in your password manager right now.** If your install file is ever lost, this key is the only way to open your data again. Then, when you edit the install file below, paste the key between the quote marks on the line `ENVELIQ_VAULT_KEY: "PASTE-YOUR-VAULT-KEY-HERE"`.

1. Open [Choose your settings](choose-settings.md), decide your answers, and come back.
2. Open the file in a simple editor called nano:

   ```
   nano docker-compose.yml
   ```

3. Use the arrow keys to move to each line marked `<-- CHANGE THIS` and change it. Keep the quote marks.
4. Save and leave: press **Ctrl + O**, then **Enter**, then **Ctrl + X**.

## Step 4. Start Enveliq

```
docker compose up -d
```

The first time it downloads Enveliq, which can take a few minutes.

**Check:** run `docker compose ps`. Both `enveliq` and `enveliq-render` say `Up` (the first may say `(healthy)` after a minute).

## Step 5. Open Enveliq

- If you chose address **A** and you are sitting at this computer, open <http://localhost:8765> in its browser.
- If you chose address **B**, open the address you chose on any device on your home network.
- If this is a server and you chose **A**, you can still reach it from your own computer. In a terminal **on your own computer** type this (change the user name and number to match yours), leave it open, and then open <http://localhost:8765> in your browser:

  ```
  ssh -L 8765:localhost:8765 sam@192.168.1.50
  ```

- For **C** (Tailscale) or **D** (a web address), follow [How should I open Enveliq?](../ACCESS.md).

You should see a **Set up Enveliq** page. Carry on with [First-time setup](after-install.md).

## Keep it running

Docker starts Enveliq again by itself after a restart (the file says `restart: unless-stopped`). Nothing else to do.

## If something goes wrong

See [Troubleshooting](troubleshooting.md).

## Next

[First-time setup](after-install.md), then [connect your email](after-install.md#step-4-connect-your-email).
