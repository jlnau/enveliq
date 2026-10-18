# Install Enveliq on a Raspberry Pi or another ARM computer

Enveliq's ready-made images are for ordinary 64-bit Intel and AMD computers. A Raspberry Pi (and other ARM computers, such as some NAS models) builds Enveliq on the spot instead. It takes 5 to 15 minutes longer, once.

**You need:** a Raspberry Pi 4 or 5 with at least **4 GB** of memory, a memory card or SSD, and **Raspberry Pi OS 64-bit** (also called "arm64"). The 32-bit version will not work. Check by typing `uname -m` in a terminal: it must say `aarch64`.

## Step 1. Get a terminal

If you are new to this, read ["What is a terminal?"](docker-compose.md#what-is-a-terminal) first. Everything below is typed into a terminal on the Pi, or over SSH.

## Step 2. Install Docker and Git

```
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
sudo apt install -y git
```

Then **log out and back in** (or reboot). **Check:** `docker compose version` prints a version.

## Step 3. Download Enveliq

```
git clone https://github.com/jlnau/enveliq.git
cd enveliq/install
```

## Step 4. Change the four lines

### Make your vault key (required)

The vault key is a long secret that locks everything Enveliq keeps. Enveliq will not finish setup without one. Make it now, **before** you start Enveliq. Use whichever way is easiest:

- **In a terminal** (on Mac or Linux): `openssl rand -hex 32`
- **In a terminal anywhere Docker runs, including Windows:**

  ```
  docker run --rm alpine sh -c "head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'; echo"
  ```

- **No terminal?** In your password manager (Bitwarden, 1Password and others) make a new password that is **64 characters, letters and numbers only**.

Either way you get one long line of letters and numbers. **Save it in your password manager right now.** If your install file is ever lost, this key is the only way to open your data again. Then, when you edit the install file below, paste the key between the quote marks on the line `ENVELIQ_VAULT_KEY: "PASTE-YOUR-VAULT-KEY-HERE"`.

1. Read [Choose your settings](choose-settings.md) and decide your answers.
2. Open the file:

   ```
   nano docker-compose.build.yml
   ```

3. Change the lines marked `<-- CHANGE THIS`. Keep the quote marks.
4. Save and leave: **Ctrl + O**, **Enter**, **Ctrl + X**.

## Step 5. Build and start

```
docker compose -f docker-compose.build.yml up -d --build
```

Be patient: the first build takes a while and prints a lot of text. **Check:** `docker compose -f docker-compose.build.yml ps` shows both `enveliq` and `enveliq-render` as `Up`.

## Step 6. Open Enveliq

Follow [step 5 of the Linux guide](docker-compose.md#step-5-open-enveliq), then [First-time setup](after-install.md).

## Updating later

```
cd ~/enveliq
git pull
cd install
docker compose -f docker-compose.build.yml up -d --build
```

Your data is kept. More in [Maintenance](maintenance.md). Wherever that page says `docker compose`, add `-f docker-compose.build.yml` after it.

## If something goes wrong

[Troubleshooting](troubleshooting.md). If the build runs out of memory, add a swap file or use a Pi with more memory.
